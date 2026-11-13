"""The people the user's mail was written to or by (`Correspondent`), and whom the user may be
writing to as they type an address."""

import re
from collections.abc import Iterable

from django.db import connection
from django.db.models import F, TextField, Value
from django.db.models.functions import Concat

from apps.search.pdf import folded
from apps.search.text import Folded

from .models import Account, Message, Role

# Most whom the user may mean, whom they wrote to most first.
MOST = 8
UNCOUNTED = {Role.DRAFTS, Role.JUNK}
# Addresses that take no answer, however much of the user's mail comes from them.
UNANSWERED = r"^(no-?reply|do-?not-?reply|mailer-daemon)\M"

NOTED = """
INSERT INTO mail_correspondent (owner_id, address, name, written, heard, last, sent_from_id,
    reached_id)
VALUES {rows}
ON CONFLICT (owner_id, address) DO UPDATE SET
    written = mail_correspondent.written + EXCLUDED.written,
    heard = mail_correspondent.heard + EXCLUDED.heard,
    name = CASE
        WHEN EXCLUDED.name <> '' AND (EXCLUDED.last >= mail_correspondent.last
            OR mail_correspondent.name = '') THEN EXCLUDED.name
        ELSE mail_correspondent.name
    END,
    sent_from_id = CASE
        WHEN EXCLUDED.sent_from_id IS NOT NULL AND (EXCLUDED.last >= mail_correspondent.last
            OR mail_correspondent.sent_from_id IS NULL) THEN EXCLUDED.sent_from_id
        ELSE mail_correspondent.sent_from_id
    END,
    reached_id = CASE
        WHEN EXCLUDED.reached_id IS NOT NULL AND (EXCLUDED.last >= mail_correspondent.last
            OR mail_correspondent.reached_id IS NULL) THEN EXCLUDED.reached_id
        ELSE mail_correspondent.reached_id
    END,
    last = greatest(mail_correspondent.last, EXCLUDED.last)
"""


def own(owner_id: int) -> dict[str, int]:
    """The user's accounts by their address."""
    accounts = Account.objects.filter(owner_id=owner_id).values_list("address", "pk")
    return {address.lower(): pk for address, pk in accounts}


def of(message: Message, mine: dict[str, int], role: str) -> dict[tuple[str, bool], str]:
    """Whom the message counts, each by address and whether the user wrote to them, with the
    name it gives them: those it went to when the user wrote it, else who wrote it."""
    if role in UNCOUNTED:
        return {}
    written = message.sender.get("address", "").lower() in mine
    people = [*message.to, *message.cc] if written else [message.sender, *message.reply_to]
    found = {}
    for each in people:
        address = each.get("address", "").lower()
        local, _, domain = address.rpartition("@")
        if local and domain:
            found[address, written] = found.get((address, written)) or each.get("name", "")
    return found


def noted(message: Message, people: dict[tuple[str, bool], str], mine: dict[str, int]) -> None:
    """Counts the message for its people, with the account it went from when the user wrote it,
    else the account it came to."""
    if not people:
        return
    sent_from = mine.get(message.sender.get("address", "").lower())
    rows = [
        (
            message.owner_id,
            address,
            name,
            int(written),
            int(not written),
            message.date,
            sent_from if written else None,
            None if written else message.account_id,
        )
        for (address, written), name in people.items()
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            NOTED.format(rows=", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows))),
            [value for row in rows for value in row],
        )


def kept(message: Message, role: str) -> None:
    """Notes the people of a message just kept."""
    mine = own(message.owner_id)
    noted(message, of(message, mine, role), mine)


def counted(messages: Iterable[Message], mine: dict[str, int], before: dict[int, dict]) -> None:
    """Notes the people the messages count now that they did not before they changed."""
    for message in messages:
        now = of(message, mine, message.folder.role)
        noted(
            message,
            {each: name for each, name in now.items() if each not in before[message.pk]},
            mine,
        )


def matching(user, typed: str) -> list[dict]:
    """The user's correspondents a word of whose name or address begins with what they typed."""
    words = folded(typed).replace("đ", "d").split()
    if not words:
        return []
    found = user.mail_correspondents.alias(
        words=Folded(Concat(F("name"), Value(" "), F("address"), output_field=TextField()))
    )
    for word in words:
        found = found.filter(words__regex=rf"\m{re.escape(word)}")
    found = found.exclude(address__regex=UNANSWERED).order_by("-written", "-heard", "-last")
    return [{"name": each.name, "address": each.address} for each in found[:MOST]]
