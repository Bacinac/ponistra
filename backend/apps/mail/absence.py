"""Answering while the user is away (D40, RFC 3834). Each message that reaches them in the period
is judged as it is taken; the answer leaves from the loop of what happens at its own time, so that
no sync waits on a mail server. Once per sender in the period."""

from datetime import datetime
from email.message import EmailMessage
from email.message import Message as Parsed
from email.utils import parseaddr

from django.utils import timezone

from apps.chat.conversations import name_of
from apps.chat.models import Conversation, Member

from . import automatic, correspondents, mime
from .models import Away, AwayAnswer, Message

SUBJECT = "Auto: "


def _destination(parsed: Parsed, message: Message) -> str:
    """Where RFC 3834 sends an answer: the return path. A server that does not hand that over,
    as ActiveSync does not, leaves the sender."""
    given = mime.header(parsed, "Return-Path")
    return parseaddr(given)[1] if given else message.sender.get("address", "")


def noted(message: Message, parsed: Parsed) -> None:
    """Puts the answer to a message that just came in among those to go, if it is to have one."""
    now = timezone.now()
    away = Away.objects.filter(owner_id=message.owner_id, starts_at__lte=now, ends_at__gt=now)
    away = away.first()
    if (
        away is None
        or message.automatic
        or message.reaction
        or message.account_id is None
        or automatic.asks_no_answer(parsed)
    ):
        return
    mine = set(correspondents.own(message.owner_id))
    named = {(each.get("address") or "").lower() for each in [*message.to, *message.cc]}
    address = _destination(parsed, message).lower()
    if not named & mine or "@" not in address or address in mine or automatic.robot(address):
        return
    AwayAnswer.objects.get_or_create(away=away, address=address, defaults={"message": message})


def now_away(users) -> dict[int, datetime]:
    """When each of the users who are away comes back."""
    now = timezone.now()
    return dict(
        Away.objects.filter(owner__in=users, starts_at__lte=now, ends_at__gt=now).values_list(
            "owner_id", "ends_at"
        )
    )


def overlapping(users, since: datetime, until: datetime) -> dict[int, datetime]:
    """When each of the users away for any of the time between the instants comes back."""
    return dict(
        Away.objects.filter(owner__in=users, starts_at__lt=until, ends_at__gt=since).values_list(
            "owner_id", "ends_at"
        )
    )


def in_talk(user, conversation) -> list[dict]:
    """Who of the others in a conversation of a few people is away now, when the user is in it."""
    around = Member.objects.filter(
        conversation_id=conversation,
        conversation__kind__in=(Conversation.Kind.DIRECT, Conversation.Kind.GROUP),
    )
    if not around.filter(user=user).exists():
        return []
    others = [each.user for each in around.exclude(user=user).select_related("user")]
    back = now_away([each.pk for each in others])
    return [{"name": name_of(each), "ends_at": back[each.pk]} for each in others if each.pk in back]


def wording(away: Away) -> str:
    return "\n\n".join(filter(None, (away.text_hr.strip(), away.text_en.strip())))


def marked(answer: EmailMessage) -> EmailMessage:
    answer["Auto-Submitted"] = "auto-replied"
    answer["X-Auto-Response-Suppress"] = "All"
    return answer


def titled(subject: str) -> str:
    return subject if subject.startswith(SUBJECT) else SUBJECT + subject
