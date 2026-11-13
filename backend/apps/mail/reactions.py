"""Emoji reactions to a message: a reply that carries one emoji for the message it answers, as
Gmail sends them (https://developers.google.com/workspace/gmail/reactions/format) and RFC 9078
describes them. A reaction is kept as the message it is, and shown on the message it answers
while the user has that one."""

import json
import re
from email.message import Message as Parsed

from django.db.models import Q

from apps.core.emoji import qualified

from . import imap, mime
from .mime import header
from .models import Message, Role

MESSAGE_ID = re.compile(r"<[^<>\s]+>")
# Gmail's bounds: no reaction where a message went to more people, nor more of them per person.
MOST = 20
UNREACHABLE = (Role.DRAFTS,)
# A reaction shown on the message it answers rather than as a message of its own.
ATTACHED = Q(reacts_to__isnull=False)


def of(message: Parsed, described: dict) -> tuple[str, str]:
    """The emoji the message reacts with and the Message-ID of the message it reacts to; empty
    unless it is a reaction to exactly one message."""
    found = described.get("reaction")
    answered = MESSAGE_ID.findall(header(message, "In-Reply-To"))
    if found is None or len(answered) != 1:
        return "", ""
    data = mime.raw(message, found["part"]) or b""
    text = imap.decoded(data, found["encoding"], found["charset"] or "utf-8")
    if found["type"] == mime.REACTION:
        try:
            given = json.loads(text)
        except ValueError:
            return "", ""
        if not isinstance(given, dict) or type(given.get("version")) is not int:
            return "", ""
        emoji = qualified(given.get("emoji")) if given["version"] == 1 else ""
    else:
        emoji = qualified(text.strip())
    return (emoji, answered[0]) if emoji else ("", "")


def target(owner_id: int, message_id: str) -> Message | None:
    found = Message.objects.filter(owner_id=owner_id, message_id=message_id, reaction="")
    return found.order_by("pk").first()


def attach(message: Message) -> None:
    """Puts the reactions that came before the message they answer on it."""
    if message.reaction or not message.message_id:
        return
    waiting = Message.objects.filter(
        owner_id=message.owner_id, reacts_to=None, in_reply_to=message.message_id
    ).exclude(reaction="")
    waiting.update(reacts_to=message)


def people(message: Message) -> list[str]:
    """The addresses the message went to, each once."""
    found = {(each.get("address") or "").lower() for each in [*message.to, *message.cc]}
    return sorted(found - {""})


def offered(message: Message, own: set[str], parsed: Parsed) -> bool:
    """Whether the user may react to the message: a message of people they write with, not of a
    mailing list nor one they were only blind copied on."""
    went = people(message)
    sender = (message.sender.get("address") or "").lower()
    return (
        not message.reaction
        and bool(MESSAGE_ID.fullmatch(message.message_id))
        and message.folder.role not in UNREACHABLE
        and not header(parsed, "List-Id")
        and not header(parsed, "List-Unsubscribe")
        and len(went) <= MOST
        and (sender in own or bool(own.intersection(went)))
    )


def mine(message: Message, own: set[str]) -> int:
    """How many reactions the user gave the message."""
    return sum(
        (sender.get("address") or "").lower() in own
        for sender in message.reactions.values_list("sender", flat=True)
    )


def grouped(message: Message, own: set[str]) -> list[dict]:
    """The message's reactions by emoji, first given first, each with who gave it and whether
    the user is among them."""
    found: dict[str, dict] = {}
    given: dict[str, set[str]] = {}
    for emoji, sender in message.reactions.order_by("date", "pk").values_list("reaction", "sender"):
        each = found.setdefault(emoji, {"emoji": emoji, "people": [], "mine": False})
        address = (sender.get("address") or "").lower()
        each["mine"] = each["mine"] or address in own
        if address not in given.setdefault(emoji, set()):
            given[emoji].add(address)
            each["people"].append(sender.get("name") or sender.get("address") or "")
    return list(found.values())
