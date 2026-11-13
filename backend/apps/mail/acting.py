"""What is done to mail (D14): each action the registry names on messages, carried out in
Ponistra only, whether the list, the reader or an outside agent asks for it. A rule is made by
one, blocking the senders or always moving their mail; triage asks the model where each message
goes, and the user moves what of it they accept."""

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import Q, QuerySet
from django.db.models.fields.json import KT
from django.utils import timezone

from apps.ai.model import Choice, Prompt
from apps.core.api import Refused
from apps.retention import kept as retention

from . import forgetting, snoozing, sorting
from .models import Folder, Message, Role, Rule

TRIAGE = "mail.triage"
TRIAGE_MODEL = "claude-sonnet-5-5"
# What the model reads of each message it sorts, and how many it sorts at once.
TRIAGED_TEXT = 600
TRIAGED = 50
# The folders triage may send mail to by their role, made the first time mail goes there.
TRIAGED_ROLES = (Role.ARCHIVE, Role.JUNK)


@dataclass(frozen=True)
class Acting:
    """Whose mail the action is done to, who does it, and whether the messages are taken out of
    Junk, which unblocks their senders."""

    owner: object
    person: object
    from_junk: bool = False


def moment(given) -> datetime:
    parsed = None
    if isinstance(given, str):
        try:
            parsed = datetime.fromisoformat(given)
        except ValueError:
            pass
    if parsed is None or parsed.tzinfo is None:
        raise Refused(400, "invalid_at")
    return parsed


def ahead(given) -> datetime:
    at = moment(given)
    if at <= timezone.now():
        raise Refused(400, "invalid_at")
    return at


def destination(user, to) -> Folder:
    """The folder the messages go to: one of the user's by its id, or the one of the role, made
    if the user has none yet."""
    if to == Role.SNOOZED:
        raise Refused(400, "invalid_to")
    if to in Role.values:
        return Folder.objects.get_or_create(owner=user, role=to, defaults={"name": to})[0]
    open_to = user.mail_folders.filter(account=None).exclude(role=Role.SNOOZED)
    found = open_to.filter(pk=to).first() if type(to) is int else None
    if found is None:
        raise Refused(400, "invalid_to")
    return found


def _marked(**values):
    def mark(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
        return found.update(**values)

    return mark


seen = _marked(seen=True)
unseen = _marked(seen=False)
flagged = _marked(flagged=True)
unflagged = _marked(flagged=False)
unawait = _marked(awaited_until=None)


def move(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    to = destination(acting.owner, parameters["to"])
    with transaction.atomic():
        if to.role == Role.INBOX and acting.from_junk:
            sorting.unblocked(acting.owner.pk, found)
        return found.update(folder=to, snoozed_until=None, unanswered=False)


def snooze(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    return snoozing.put_away(acting.owner.pk, found, ahead(parameters["at"]))


def unsnooze(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    return snoozing.returned(acting.owner.pk, found.filter(folder__role=Role.SNOOZED))


def await_(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    expecting = found.filter(Q(folder__role=Role.SENT) | Q(unanswered=True))
    return expecting.update(awaited_until=ahead(parameters["at"]), unanswered=False)


def delete(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    retention.refuse_mail(acting.owner.pk, found)
    return forgetting.forgotten(acting.owner.pk, found)


def _senders(found: QuerySet[Message], by: str) -> set[str]:
    """The senders of the messages as a rule names them: by their address, or by the domain they
    write from."""
    addresses = {
        each.strip().lower()
        for each in found.values_list(KT("sender__address"), flat=True)
        if each and "@" in each
    }
    return addresses if by == "address" else {each.rpartition("@")[2] for each in addresses}


def _ruled(acting: Acting, found: QuerySet[Message], to: Folder, by: str) -> int:
    """Sends the mail of the messages' senders to the folder from now on, and moves there what of
    it the user has already; how many messages it moved."""
    senders = _senders(found, by)
    if not senders:
        raise Refused(400, "invalid_senders")
    moved = 0
    with transaction.atomic():
        for sender in sorted(senders):
            made = Rule.objects.update_or_create(
                owner=acting.owner, sender=sender, defaults={"folder": to}
            )[0]
            moved += sorting.applied(made)
    return moved


def block(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    return _ruled(acting, found, destination(acting.owner, Role.JUNK), parameters["by"])


def always(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    to = destination(acting.owner, parameters["to"])
    if to.role in (Role.SENT, Role.DRAFTS):
        raise Refused(400, "invalid_to")
    return _ruled(acting, found, to, parameters["by"])


TRIAGE_INSTRUCTION = """You sort a person's e-mail into their folders. For each message, by who \
wrote it, its subject and how it begins, choose the one folder it belongs in, or none where it \
should stay in the inbox: what needs the person's answer or attention stays. Junk is for \
unwanted bulk mail and scams, Archive for what is done or only for the record. Name only the \
folders listed, by their id."""


def triaged_into(owner) -> list[Folder]:
    """The folders triage sorts the owner's mail into: their own, but where mail is sent from,
    waits to come back or is thrown away, and Archive and Junk even before they have them."""
    own = list(
        owner.mail_folders.filter(account=None)
        .exclude(role__in=(Role.INBOX, Role.SENT, Role.DRAFTS, Role.SNOOZED, Role.TRASH))
        .order_by("name", "pk")
    )
    had = {each.role for each in own}
    return own + [Folder(name=role, role=role) for role in TRIAGED_ROLES if role not in had]


def _where(folder: Folder) -> str:
    return str(folder.pk) if folder.pk else folder.role


def _line(message: Message) -> str:
    sender = message.sender or {}
    named = f"{sender.get('name', '')} <{sender.get('address', '')}>".strip()
    text = " ".join(message.text.split())[:TRIAGED_TEXT]
    return f"[{message.pk}] From: {named}\nSubject: {message.subject}\n{text}"


def triage(acting: Acting, messages: list[Message], parameters: dict) -> Prompt:
    """What the model is asked to sort the messages into the owner's folders."""
    if len(messages) > TRIAGED:
        raise Refused(413, "too_many")
    folders = triaged_into(acting.owner)
    named = [f"{_where(each)}: {each.name}" for each in folders]
    content = "Folders:\n" + "\n".join(named) + "\n\nMessages:\n\n"
    content += "\n\n".join(_line(each) for each in messages)
    places = [_where(each) for each in folders]
    answer = {
        "type": "object",
        "properties": {
            "sorted": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "message": {"enum": [each.pk for each in messages]},
                        "folder": {"enum": [*places, None]},
                    },
                    "required": ["message", "folder"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["sorted"],
        "additionalProperties": False,
    }
    chosen = Choice("Where each message goes, none where it stays in the inbox.", answer)
    return Prompt(TRIAGE_INSTRUCTION, content, {"sorted": chosen}, effort="low", steps=3)


def proposed(acting: Acting, answer: dict) -> list[dict]:
    """The moves the model proposes, each message once, to a folder of the owner's by its id or
    one of the roles triage makes."""
    places = {_where(each) for each in triaged_into(acting.owner)}
    found: dict[int, str] = {}
    for each in answer.get("sorted", []):
        if each.get("folder") in places and each.get("message") not in found:
            found[each["message"]] = each["folder"]
    return [
        {"message": message, "to": int(to) if to.isdigit() else to} for message, to in found.items()
    ]
