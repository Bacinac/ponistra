"""What a file shows of what it holds, from its bytes and its name, whichever source keeps it: an
archive's entries, a message with its attachments, a card's people, a calendar's events, and a
picture the browser cannot show drawn whole. The readings run in the reader (D51), an archive's
in the converter (D23); `of` and `part` are the backend's side."""

import base64
import re
import struct
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from apps.blobs import store

from . import archives, client

MESSAGE_NAMES = {"eml", "mht", "mhtml"}
# A message's own headers, one of which it opens with when nothing else names its kind.
HEADERS = re.compile(
    rb"(?:return-path|received|from|to|subject|date|message-id|mime-version|delivered-to|x-[\w-]+)"
    rb":[ \t]",
    re.IGNORECASE,
)
# A picture of a card larger than this is left out: the glance shows it at 48 pixels.
PHOTO = 256 * 1024
# What a card or a calendar file shows of its people and events; the rest is counted.
MOST = 500
# Seconds between 1601 and 1970, FILETIME's epoch and Unix's.
FILETIME = 11_644_473_600


@dataclass(frozen=True)
class Part:
    data: bytes | BinaryIO
    name: str
    media_type: str
    # Shown in place, a picture rather than a file taken out.
    shown: bool = False


def kind_of(media_type: str, name: str, head: bytes) -> str | None:
    """How the file is shown: `picture`, `archive`, `message`, `outlook`, `cards` or `events`;
    None for a file shown as it is, or not at all."""
    if media_type in store.PICTURES:
        return "picture"
    if media_type in store.ARCHIVES:
        return "archive"
    if media_type == store.OUTLOOK:
        return "outlook"
    if media_type == "text/vcard":
        return "cards"
    if media_type == "text/calendar":
        return "events"
    if media_type == store.TEXT and _message(name, head):
        return "message"
    return None


def _message(name: str, head: bytes) -> bool:
    if PurePosixPath(name).suffix.lower().lstrip(".") in MESSAGE_NAMES:
        return True
    return bool(HEADERS.match(head.lstrip()))


def _sniffed(path: Path) -> str:
    with path.open("rb") as file:
        sample = file.read(store.SAMPLE)
    media_type = store.sniff(sample)
    if sample.startswith(store.OLE):
        return store.sniff_ole(path) or media_type
    return media_type


def _head(path: Path) -> bytes:
    with path.open("rb") as file:
        return file.read(4096)


def of(
    path: Path,
    name: str,
    prefix: str,
    media_type: str | None = None,
    password: str | None = None,
) -> dict | None:
    """What the file shows, its kind under `kind`; None for a file of no such kind. `prefix` is
    the address its parts are served under, `part` each one's name after it; an archive that
    asks for a password raises `archives.Locked`."""
    media_type = media_type or _sniffed(path)
    kind = kind_of(media_type, name, _head(path))
    if kind is None:
        return None
    if kind == "picture":
        return {"kind": kind, "whole": f"{prefix}whole"}
    if kind == "archive":
        return {"kind": kind, **archives.listed(path, name, password)}
    return {"kind": kind, **client.ask("shown", path, shape=kind, prefix=prefix)}


def part(
    path: Path,
    name: str,
    number: str,
    media_type: str | None = None,
    password: str | None = None,
) -> Part | None:
    """One part of what the file shows: an archive's entry, a message's attachment, a picture
    drawn whole; None where it holds no such part."""
    media_type = media_type or _sniffed(path)
    kind = kind_of(media_type, name, _head(path))
    if kind == "picture" and number == "whole":
        drawn = client.ask("whole", path)
        return Part(drawn, f"{PurePosixPath(name).stem}.png", "image/png", shown=True)
    if kind == "archive":
        found = archives.entry(path, name, number, password)
        return None if found is None else Part(found[1], found[0], _typed(found[0]))
    if kind in ("message", "outlook"):
        found = client.ask("shown_part", path, shape=kind, part=number)
        if found is None:
            return None
        return Part(found["data"], found["name"], found["type"], found.get("inline", False))
    return None


def _typed(name: str) -> str:
    import mimetypes

    return mimetypes.guess_type(name)[0] or store.UNKNOWN


# In the reader.


def read(path: Path, kind: str, prefix: str) -> dict:
    if kind == "message":
        return _eml(path, prefix)
    if kind == "outlook":
        return _msg(path)
    if kind == "cards":
        return _cards(path)
    return _events(path)


def taken(path: Path, kind: str, number: str) -> dict | None:
    if kind == "message":
        return _eml_part(path, number)
    return _msg_part(path, number)


def _eml(path: Path, prefix: str) -> dict:
    from apps.mail import imap, mime, safe

    parsed = mime.parsed(path.read_bytes())
    parts = mime.described(parsed)
    inline = {each["cid"]: f"{prefix}{each['part']}" for each in parts["inline"]}
    html, text, remote = None, None, False
    if shown := parts.get("html"):
        data = mime.raw(parsed, shown["part"]) or b""
        markup = imap.decoded(data, shown["encoding"], shown["charset"])
        html, remote = safe.cleaned(markup, inline, None)
    elif shown := parts.get("plain"):
        data = mime.raw(parsed, shown["part"]) or b""
        text = imap.decoded(data, shown["encoding"], shown["charset"])
    return {
        "subject": mime.header(parsed, "Subject"),
        "from": mime.header(parsed, "From"),
        "to": mime.header(parsed, "To"),
        "cc": mime.header(parsed, "Cc"),
        "date": _dated(mime.header(parsed, "Date")),
        "html": html,
        "text": text,
        "remote": remote,
        "attachments": [
            {"part": each["part"], "name": each["name"] or each["part"], "type": each["type"]}
            | {"size": each["size"]}
            for each in parts["attachments"]
        ],
    }


def _dated(header: str) -> str | None:
    from email.utils import parsedate_to_datetime

    try:
        moment = parsedate_to_datetime(header)
    except TypeError, ValueError, IndexError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).isoformat()


def _eml_part(path: Path, number: str) -> dict | None:
    from apps.mail import imap, mime

    parsed = mime.parsed(path.read_bytes())
    parts = mime.described(parsed)
    for each in parts["attachments"]:
        if each["part"] == number:
            data = imap.content(mime.raw(parsed, number) or b"", each["encoding"])
            return {"data": data, "name": each["name"] or number, "type": each["type"]}
    for each in parts["inline"]:
        if each["part"] == number and each["type"] in store.IMAGES:
            data = imap.content(mime.raw(parsed, number) or b"", each["encoding"])
            name = f"{number}.{store.IMAGES[each['type']]}"
            return {"data": data, "name": name, "type": each["type"], "inline": True}
    return None


# An Outlook message keeps each property in a stream named by its id and type (MS-OXMSG).
UNICODE, STRING8, BINARY = "001F", "001E", "0102"
SYSTIME = 0x0040


def _msg(path: Path) -> dict:
    import olefile

    with olefile.OleFileIO(path) as container:
        streams = {"/".join(each) for each in container.listdir()}

        def value(storage: str, prop: str, codepage: str = "cp1252") -> str:
            for kind, encoding in ((UNICODE, "utf-16-le"), (STRING8, codepage)):
                stream = f"{storage}__substg1.0_{prop}{kind}"
                if stream in streams:
                    return container.openstream(stream).read().decode(encoding, "replace")
            return ""

        codepage = _codepage(_properties(container, "", 32).get(0x3FDE))
        recipients: dict[int, list[str]] = {1: [], 2: []}
        attachments = []
        for storage in sorted({each.split("/")[0] for each in streams if "/" in each}):
            if storage.startswith("__recip_version1.0_"):
                named = value(f"{storage}/", "3001", codepage)
                address = value(f"{storage}/", "39FE", codepage) or value(
                    f"{storage}/", "3003", codepage
                )
                role = _properties(container, f"{storage}/", 8).get(0x0C15, 1)
                shown = f"{named} <{address}>" if named and address and named != address else named
                recipients.setdefault(role, []).append(shown or address)
            elif storage.startswith("__attach_version1.0_"):
                data = f"{storage}/__substg1.0_3701{BINARY}"
                if data not in streams:
                    continue
                attachments.append(
                    {
                        "part": storage.rpartition("#")[2],
                        "name": value(f"{storage}/", "3707", codepage)
                        or value(f"{storage}/", "3704", codepage)
                        or storage.rpartition("#")[2],
                        "type": value(f"{storage}/", "370E", codepage)
                        or "application/octet-stream",
                        "size": container.get_size(data),
                    }
                )
        sender = value("", "0C1A", codepage)
        address = value("", "5D01", codepage) or value("", "0C1F", codepage)
        html, remote = None, False
        if f"__substg1.0_1013{BINARY}" in streams:
            from apps.mail import safe

            markup = container.openstream(f"__substg1.0_1013{BINARY}").read()
            html, remote = safe.cleaned(markup.decode(codepage, "replace"), {}, None)
        moment = _properties(container, "", 32).get(0x0039)
        return {
            "subject": value("", "0037", codepage),
            "from": f"{sender} <{address}>"
            if sender and address and sender != address
            else sender or address,
            "to": "; ".join(recipients.get(1, [])) or value("", "0E04", codepage),
            "cc": "; ".join(recipients.get(2, [])) or value("", "0E03", codepage),
            "date": moment,
            "html": html,
            "text": None if html else value("", "1000", codepage),
            "remote": remote,
            "attachments": attachments,
        }


def _codepage(found) -> str:
    if not isinstance(found, int) or found in (0, 1200):
        return "cp1252"
    if found == 65001:
        return "utf-8"
    import codecs

    try:
        return codecs.lookup(f"cp{found}").name
    except LookupError:
        return "cp1252"


def _properties(container, storage: str, header: int) -> dict[int, object]:
    """The fixed-length properties of a storage: integers, and times as ISO text."""
    stream = f"{storage}__properties_version1.0"
    if not container.exists(stream):
        return {}
    raw = container.openstream(stream).read()[header:]
    found: dict[int, object] = {}
    for at in range(0, len(raw) - 15, 16):
        kind, prop = struct.unpack_from("<HH", raw, at)
        if kind == 0x0003:
            found[prop] = struct.unpack_from("<i", raw, at + 8)[0]
        elif kind == SYSTIME:
            ticks = struct.unpack_from("<Q", raw, at + 8)[0]
            if ticks:
                moment = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=ticks // 10)
                found[prop] = moment.isoformat()
    return found


def _msg_part(path: Path, number: str) -> dict | None:
    import olefile

    if not re.fullmatch(r"[0-9A-Fa-f]{8}", number):
        return None
    storage = f"__attach_version1.0_#{number.upper()}/"
    with olefile.OleFileIO(path) as container:
        data = f"{storage}__substg1.0_3701{BINARY}"
        if not container.exists(data):
            return None

        def value(prop: str) -> str:
            for kind, encoding in ((UNICODE, "utf-16-le"), (STRING8, "cp1252")):
                stream = f"{storage}__substg1.0_{prop}{kind}"
                if container.exists(stream):
                    return container.openstream(stream).read().decode(encoding, "replace")
            return ""

        return {
            "data": container.openstream(data).read(),
            "name": value("3707") or value("3704") or number,
            "type": value("370E") or "application/octet-stream",
        }


def text(path: Path) -> str:
    """The text of a file, in the encoding its bytes tell."""
    from apps.blobs.text import encoding_of

    raw = path.read_bytes()
    return raw.decode(encoding_of(raw), "replace")


def _cards(path: Path) -> dict:
    from apps.contacts import vcard

    read, count = vcard.filed(text(path))
    people = []
    for card in read[:MOST]:
        photo = card.photo if card.photo and len(card.photo) <= PHOTO else None
        kind = store.sniff(photo[:1024]) if photo else None
        people.append(
            {
                "name": vcard.shown_name(card.fields, card.points),
                "organisation": card.fields["organisation"],
                "title": card.fields["title"],
                "points": [
                    {"kind": p["kind"], "label": p["label"], "value": p["value"]}
                    for p in card.points
                ],
                "photo": f"data:{kind};base64,{base64.b64encode(photo).decode()}"
                if photo and kind in store.IMAGES and kind != "image/svg+xml"
                else None,
            }
        )
    return {"people": people, "count": count}


def _events(path: Path) -> dict:
    from icalendar import Calendar

    from apps.imports.reading import Unreadable

    try:
        calendar = Calendar.from_ical(text(path))
    except ValueError as error:
        raise Unreadable(str(error)) from None
    found = list(calendar.walk("VEVENT"))
    events = []
    for each in found[:MOST]:
        starts = each["DTSTART"].dt if "DTSTART" in each else None
        ends = each["DTEND"].dt if "DTEND" in each else None
        events.append(
            {
                "summary": str(each.get("SUMMARY", "")),
                "location": str(each.get("LOCATION", "")),
                "description": str(each.get("DESCRIPTION", ""))[:2000],
                "all_day": isinstance(starts, date) and not isinstance(starts, datetime),
                "start": starts.isoformat() if starts else None,
                "end": ends.isoformat() if ends else None,
                "repeats": "RRULE" in each,
                "organizer": _address(each.get("ORGANIZER")),
            }
        )
    events.sort(key=lambda event: event["start"] or "")
    return {"name": str(calendar.get("X-WR-CALNAME", "")), "events": events, "count": len(found)}


def _address(prop) -> str:
    if prop is None:
        return ""
    named = prop.params.get("CN", "")
    address = str(prop).removeprefix("mailto:").removeprefix("MAILTO:")
    return f"{named} <{address}>" if named else address
