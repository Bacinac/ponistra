"""An organisation's calendar on HCL Domino beside what its Traveler gives (S4-3a). Traveler
puts a meeting into a device's calendar only once it is answered, and tells of an invitation by
a notice whose calendar part it breaks (the text of a Java byte array). The invitations still
awaiting the user's answer are read from their mail file's calendar, which the same sign-in
opens through Domino's URL commands; each stands in the account's calendar under the uid
Traveler gives the meeting once answered, and the meeting takes its place then."""

import base64
import http.client
import json
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesHeaderParser
from logging import getLogger
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.blobs.store import path_of
from apps.core.api import Refused
from apps.mail.imap import Failed
from apps.mail.models import Account, Arrival, Message

from . import events, ical
from .ical import Found
from .models import Calendar, Event, Feed, Gone, Invitation
from .recurrence import as_day, day_instant

log = getLogger(__name__)

# Traveler's UID of a meeting is Outlook's GlobalObjId around the Notes ApptUNID, which the
# notice of an invitation bears as its own UNID.
GLOBAL_ID = "040000008200E00074C5B7101A82E00800000000646C6F747573C301000000000000000010000000"
# X-IBM-NOTICEICON of an invitation's notice.
INVITATION = "133"
STANDING = "notes-"
BEHIND = timedelta(days=31)
AHEAD = timedelta(days=366)
PAGE = 500
TIMEOUT = 30
HEAD = 64 * 1024
MOMENT = re.compile(r"(\d{8})(?:T(\d{6})(?:,\d+)?(Z|[+-]\d{2}(?::?\d{2})?))?")


@dataclass
class Place:
    """The user's mail file: its server's host and its path there."""

    host: str
    path: str


def standing(event: Event) -> bool:
    """Whether the event is an invitation of the mail file standing in for the meeting."""
    return event.href.startswith(STANDING)


def noted(message: Message, files: list[tuple[dict, bytes]]) -> None:
    """Keeps the notice of an invitation Traveler delivers, by the uid its meeting will bear."""
    account = message.account
    if account is None or account.protocol != Account.Protocol.ACTIVESYNC:
        return
    with path_of(message.raw_id).open("rb") as raw:
        head = raw.read(HEAD).split(b"\r\n\r\n", 1)[0].split(b"\n\n", 1)[0]
    headers = BytesHeaderParser(policy=policy.default).parsebytes(head)
    unid = str(headers.get("X-IBM-UNID", "")).strip().upper()
    if (
        headers.get("X-IBM-FORM") != "Notice"
        or str(headers.get("X-IBM-NOTICEICON", "")).strip() != INVITATION
        or len(unid) != 32
    ):
        return
    Invitation.objects.get_or_create(
        message=message,
        defaults={
            "owner_id": message.owner_id,
            "method": Invitation.Method.REQUEST,
            "uid": GLOBAL_ID + unid,
        },
    )


def _get(host: str, path: str, username: str, password: str) -> tuple[int, str, bytes]:
    # Only towards a host the installation names in PONISTRA_MAIL_PLAIN_HOSTS.
    if urlsplit(f"//{host}").hostname in settings.MAIL_PLAIN_HOSTS:
        connection = http.client.HTTPConnection(host, timeout=TIMEOUT)
    else:
        connection = http.client.HTTPSConnection(
            host, timeout=TIMEOUT, context=ssl.create_default_context()
        )
    login = base64.b64encode(f"{username}:{password}".encode()).decode()
    try:
        connection.request("GET", path, headers={"Authorization": f"Basic {login}"})
        response = connection.getresponse()
        return response.status, response.headers.get("Server", ""), response.read()
    except OSError, http.client.HTTPException:
        raise Failed("notes_unreachable") from None
    finally:
        connection.close()


def _read(host: str, path: str, username: str, password: str) -> dict:
    """The JSON a Domino URL command gives."""
    status, _, data = _get(host, path, username, password)
    try:
        if status != 200:
            raise ValueError(status)
        return json.loads(data)
    except ValueError:
        raise Failed("notes_unreachable") from None


def _entries(given: dict | None) -> list[dict]:
    return (given or {}).get("viewentry", [])


def _values(entry: dict, name: str) -> list[str]:
    for column in entry["entrydata"]:
        if column["@name"] != name:
            continue
        for kind in ("text", "datetime", "number"):
            if kind in column:
                return [column[kind]["0"]]
            if f"{kind}list" in column:
                return [each["0"] for each in column[f"{kind}list"][kind]]
    return []


def _first(entry: dict, name: str) -> str:
    return next(iter(_values(entry, name)), "")


def _view(view: str, key: str) -> str:
    return (
        f"/names.nsf/{quote(view)}?ReadViewEntries&outputformat=JSON&Count=1&StartKey={quote(key)}"
    )


def _one(given: dict) -> dict:
    return next(iter(_entries(given)), {"entrydata": []})


def place(host: str, username: str, password: str, address: str) -> Place | None:
    """Where the user's mail file is, as the directory on their Traveler's server has it; None
    where that server is not Domino."""
    status, server, data = _get(host, _view("($Users)", address), username, password)
    if "domino" not in server.lower():
        return None
    try:
        if status != 200:
            raise ValueError(status)
        person = _one(json.loads(data))
    except ValueError:
        raise Failed("notes_unreachable") from None
    if address.lower() not in {each.lower() for each in _values(person, "$38")}:
        raise Failed("notes_unreachable")
    named, file = _first(person, "MailServer"), _first(person, "MailFile")
    found = _one(_read(host, _view("($Servers)", named), username, password))
    mail_host = _first(found, "SMTPFullHostDomain")
    if not file or _first(found, "ServerName") != named or not mail_host:
        raise Failed("notes_unreachable")
    path = "/" + file.replace("\\", "/").lstrip("/")
    if not path.lower().endswith(".nsf"):
        path += ".nsf"
    return Place(mail_host, quote(path))


def _moment(raw: str) -> tuple[datetime, bool]:
    """A Domino time (20261029T100000,00+01) as an instant, or a date as its day."""
    found = MOMENT.fullmatch(raw.strip())
    if found is None or (found[2] is not None and found[3] is None):
        raise ValueError(raw)
    day, clock, offset = found.groups()
    if clock is None:
        return day_instant(datetime.strptime(day, "%Y%m%d").date()), True
    moment = datetime.strptime(day + clock, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if offset != "Z":
        digits = offset[1:].replace(":", "")
        shift = timedelta(hours=int(digits[:2]), minutes=int(digits[2:] or 0))
        moment -= shift if offset[0] == "+" else -shift
    return moment, False


def _calendar(host: str, path: str, username: str, password: str) -> dict[str, list[dict]]:
    """The entries of the mail file's calendar from a month ago to a year ahead, by UNID."""
    now = timezone.now()
    since = (now - BEHIND).astimezone(UTC).strftime("%Y%m%dT%H%M%S,00+00")
    until = (now + AHEAD).astimezone(UTC).strftime("%Y%m%dT%H%M%S,00+00")
    found: dict[str, list[dict]] = {}
    seen = set()
    while True:
        given = _read(
            host,
            f"{path}/($Calendar)?ReadViewEntries&outputformat=JSON&KeyType=time&Count={PAGE}"
            f"&StartKey={quote(since)}&UntilKey={quote(until)}",
            username,
            password,
        )
        page = _entries(given)
        for entry in page:
            starts, ends = _values(entry, "$144"), _values(entry, "$146")
            for start, end in zip(starts, ends, strict=False):
                if (entry["@unid"], start) in seen:
                    continue
                seen.add((entry["@unid"], start))
                found.setdefault(entry["@unid"].upper(), []).append(
                    {"start": start, "end": end, "texts": _values(entry, "$147")}
                )
        if len(page) < PAGE:
            return found
        last = _first(page[-1], "$134")
        if not last or last == since:
            return found
        since = last


def _found(uid: str, instances: list[dict], message: Message) -> Found:
    first = min(instances, key=lambda each: _moment(each["start"])[0])
    starts, all_day = _moment(first["start"])
    ends, _ = _moment(first["end"] or first["start"])
    if all_day and ends <= starts:
        ends = day_instant(as_day(starts) + timedelta(days=1))
    texts = first["texts"]
    sender = message.sender or {}
    rdates = []
    for each in instances:
        moment, _ = _moment(each["start"])
        if moment != starts:
            rdates.append(as_day(moment).isoformat() if all_day else moment.isoformat())
    return Found(
        uid=uid,
        summary=texts[0] if texts else message.subject,
        location=texts[1] if len(texts) > 2 else "",
        all_day=all_day,
        starts=starts,
        ends=max(ends, starts),
        rdates=sorted(rdates),
        busy=False,
        organizer={"name": sender.get("name", ""), "email": sender.get("address", "").lower()},
        response="needs-action",
    )


def _feed_of(account: Account) -> Feed | None:
    return (
        Feed.objects.filter(account=account, followed=True, calendar__isnull=False)
        .select_related("calendar")
        .order_by("pk")
        .first()
    )


@transaction.atomic
def _held(calendar: Calendar, account: Account, entries: dict[str, list[dict]]) -> None:
    known = {
        each.uid: each
        for each in Invitation.objects.filter(
            message__account=account, method=Invitation.Method.REQUEST, uid__startswith=GLOBAL_ID
        ).select_related("message")
    }
    held = calendar.events.filter(master__isnull=True)
    answered = set(held.exclude(href__startswith=STANDING).values_list("uid", flat=True))
    standing_in = {each.uid: each for each in held.filter(href__startswith=STANDING)}
    wanted = {}
    for unid, instances in entries.items():
        uid = GLOBAL_ID + unid
        if uid in known and uid not in answered:
            wanted[uid] = _found(uid, instances, known[uid].message)
    for uid, event in standing_in.items():
        if uid not in wanted:
            events.deleted(event)
    for uid, found in wanted.items():
        event = standing_in.get(uid)
        if event is None:
            events.made(calendar, found, href=f"{STANDING}{uid[-32:]}.ics")
        else:
            found.response = event.response
            if any(getattr(event, name) != value for name, value in found.fields.items()):
                events.saved(event, found)
        Invitation.objects.filter(pk=known[uid].pk).update(event=ical.described(found))


def followed(host: str, username: str, password: str, account: Account) -> None:
    """The invitations of the user's mail file awaiting their answer, held in the account's
    calendar as the mail file has them; a mail file that cannot be read is told on the feed."""
    feed = _feed_of(account)
    if feed is None:
        return
    try:
        found = place(host, username, password, account.address)
        if found is None:
            return
        entries = _calendar(found.host, found.path, username, password)
    except Failed as failed:
        log.warning("calendar: the mail file of account %s was not read", account.pk)
        Feed.objects.filter(pk=feed.pk).update(error=failed.code)
        return
    _held(feed.calendar, account, entries)
    Feed.objects.filter(pk=feed.pk, error="notes_unreachable").update(error="")


def notice_of(event: Event) -> tuple[str, str]:
    """The folder and the item of the notice the invitation came by, which the server answers."""
    arrival = (
        Arrival.objects.filter(
            message__invitation__uid=event.uid,
            message__owner_id=event.calendar.owner_id,
            source__account=event.calendar.account,
        )
        .exclude(item="")
        .select_related("source")
        .order_by("-pk")
        .first()
    )
    if arrival is None:
        raise Refused(409, "notice_gone")
    return arrival.source.server_id, arrival.item


def answered(event: Event, href: str) -> None:
    """The meeting the server gives once its invitation is answered takes the invitation's
    place, which the phones are told is gone."""
    Gone.objects.create(owner_id=event.calendar.owner_id, calendar=event.calendar, href=event.href)
    Event.objects.filter(pk=event.pk).update(href=href)
    event.href = href
