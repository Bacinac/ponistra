import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.utils import timezone

from .pdf import folded

FILTER = re.compile(r'(?:^|(?<=\s))([^\s:"]+):("[^"]*"?|\S*)')
KEYS = {
    "vrsta": "kind",
    "kind": "kind",
    "od": "from",
    "from": "from",
    "racun": "account",
    "account": "account",
    "mapa": "folder",
    "folder": "folder",
    "datum": "date",
    "date": "date",
    "izmjena": "changed",
    "changed": "changed",
    "ima": "has",
    "has": "has",
}
KINDS = {
    "posta": "mail",
    "mail": "mail",
    "razgovor": "conversation",
    "razgovori": "conversation",
    "chat": "conversation",
    "conversation": "conversation",
    "conversations": "conversation",
    "dokument": "document",
    "dokumenti": "document",
    "document": "document",
    "documents": "document",
    "datoteka": "file",
    "datoteke": "file",
    "file": "file",
    "files": "file",
    "mapa": "folder",
    "mape": "folder",
    "folder": "folder",
    "folders": "folder",
    "poveznica": "link",
    "poveznice": "link",
    "link": "link",
    "links": "link",
    "dogadaj": "event",
    "dogadaji": "event",
    "event": "event",
    "events": "event",
    "zadatak": "task",
    "zadaci": "task",
    "task": "task",
    "tasks": "task",
    "osoba": "person",
    "osobe": "person",
    "ljudi": "person",
    "kontakt": "person",
    "kontakti": "person",
    "person": "person",
    "people": "person",
    "contact": "person",
    "contacts": "person",
    "sef": "vault",
    "vault": "vault",
    "verzija": "version",
    "verzije": "version",
    "povijest": "version",
    "version": "version",
    "versions": "version",
    "history": "version",
}
NODE_KINDS = (None, "document", "file", "folder", "link")
HAS = {
    "privitak": "attachment",
    "privitke": "attachment",
    "privici": "attachment",
    "attachment": "attachment",
    "attachments": "attachment",
}
ROLES = {
    "pristigla": "inbox",
    "inbox": "inbox",
    "skice": "drafts",
    "drafts": "drafts",
    "poslano": "sent",
    "sent": "sent",
    "arhiva": "archive",
    "archive": "archive",
    "nezeljena": "junk",
    "junk": "junk",
    "spam": "junk",
    "smece": "trash",
    "trash": "trash",
    "odgodeno": "snoozed",
    "snoozed": "snoozed",
}
LAST = {
    "tjedan": 7,
    "week": 7,
    "mjesec": 30,
    "month": 30,
    "godina": 365,
    "year": 365,
}
LAST_NAMES = {7: "week", 30: "month", 365: "year"}
DAY = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\.?")
MONTH = re.compile(r"(\d{1,2})\.(\d{4})\.?")
ISO = re.compile(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?")


@dataclass
class Period:
    """From the start of the first day it names to the end of the last, in local time."""

    start: datetime | None
    end: datetime | None
    changed: bool


@dataclass
class Asked:
    """The words left to search for, and what the filters among them narrow it to."""

    text: str
    filters: list[dict] = field(default_factory=list)
    kind: str | None = None
    sender: list[str] = field(default_factory=list)
    account: list[str] = field(default_factory=list)
    folder: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    period: Period | None = None
    attachment: bool = False

    @property
    def invalid(self) -> bool:
        return any("error" in each for each in self.filters)

    @property
    def narrowed(self) -> bool:
        return bool(self.filters)

    @property
    def documents(self) -> bool:
        """Whether a document can meet the filters."""
        return self.kind in NODE_KINDS and not self.mailbox

    @property
    def versions(self) -> bool:
        """Whether a version of a document can meet the filters: only when asked for by kind,
        since what a document says now its versions say too."""
        return self.kind == "version" and not self.mailbox

    @property
    def mail(self) -> bool:
        """Whether a message can meet the filters."""
        return self.kind in (None, "mail")

    @property
    def mailbox(self) -> bool:
        """Whether a filter speaks of a mailbox, which only a message can meet."""
        return bool(self.account or self.roles or self.attachment)

    @property
    def conversations(self) -> bool:
        """Whether a message of a conversation can meet the filters."""
        return self.kind in (None, "conversation") and not self.mailbox and not self.folder

    @property
    def events(self) -> bool:
        """Whether an event can meet the filters: a sender is its organiser or a guest."""
        return self.kind in (None, "event") and not self.mailbox and not self.folder

    @property
    def tasks(self) -> bool:
        return self.kind in (None, "task") and not (self.mailbox or self.folder or self.sender)

    @property
    def people(self) -> bool:
        """Whether a person can meet the filters; a person has no date."""
        if self.kind not in (None, "person") or self.period is not None:
            return False
        return not (self.mailbox or self.folder or self.sender)


def _word(value: str) -> str:
    return folded(value).replace("đ", "d")


def _one[T](words: dict[str, T], value: str) -> T | None:
    """The one meaning the value names, whole or as the start of its words."""
    typed = _word(value)
    if not typed:
        return None
    if typed in words:
        return words[typed]
    found = {meaning for word, meaning in words.items() if word.startswith(typed)}
    return found.pop() if len(found) == 1 else None


def _day(value: str) -> tuple[date, date] | None:
    """The first and the last day the value names: a day, a month or a year."""
    try:
        if found := DAY.fullmatch(value):
            day = date(int(found[3]), int(found[2]), int(found[1]))
            return day, day
        if found := MONTH.fullmatch(value):
            first = date(int(found[2]), int(found[1]), 1)
        elif found := ISO.fullmatch(value):
            year, month, day = found[1], found[2], found[3]
            if day:
                given = date(int(year), int(month), int(day))
                return given, given
            if not month:
                return date(int(year), 1, 1), date(int(year), 12, 31)
            first = date(int(year), int(month), 1)
        else:
            return None
    except ValueError:
        return None
    following = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, following - timedelta(days=1)


def _local(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, datetime.min.time()))


def period(value: str, changed: bool, now: datetime) -> tuple[Period, dict] | None:
    """The period the value names, as the filter the box shows: the last days, a day, a month,
    a year, or a range of them with `..`, open at either end."""
    days = _one(LAST, value)
    if days is not None:
        return Period(now - timedelta(days=days), None, changed), {"last": LAST_NAMES[days]}
    first, ranged, last = value.partition("..")
    if not ranged:
        last = first
    since = _day(first) if first else None
    until = _day(last) if last else None
    if (first and since is None) or (last and until is None) or not (since or until):
        return None
    start = since and since[0]
    end = until and until[1]
    if start and end and start > end:
        return None
    return (
        Period(start and _local(start), end and _local(end + timedelta(days=1)), changed),
        {"from": start and start.isoformat(), "to": end and end.isoformat()},
    )


def asked(q: str, now: datetime | None = None) -> Asked:
    """The words of the box, and each filter typed among them, where it stands in the box and
    what it narrows to, or why it cannot."""
    now = now or timezone.now()
    found = Asked(text="")
    kept, at = [], 0
    for typed in FILTER.finditer(q):
        key = KEYS.get(_word(typed[1]))
        if key is None:
            continue
        kept.append(q[at : typed.start()])
        at = typed.end()
        value = typed[2].strip('"').strip()
        shown = {"key": key, "token": typed[0], "start": typed.start(), "end": typed.end()}
        shown["raw"] = typed[2]
        found.filters.append(shown)
        if not value:
            shown["error"] = "empty"
        elif key == "kind":
            kind = _one(KINDS, value)
            if kind is None:
                shown["error"] = "invalid_kind"
            else:
                shown["value"] = found.kind = kind
        elif key == "has":
            if _one(HAS, value) is None:
                shown["error"] = "invalid_has"
            else:
                shown["value"] = "attachment"
                found.attachment = True
        elif key in ("date", "changed"):
            given = period(value, key == "changed", now)
            if given is None:
                shown["error"] = "invalid_date"
            else:
                found.period, shown["value"] = given
        elif key == "folder" and (role := _one(ROLES, value)):
            shown["value"] = value
            shown["role"] = role
            found.roles.append(role)
        else:
            shown["value"] = value
            {"from": found.sender, "account": found.account, "folder": found.folder}[key].append(
                value
            )
    kept.append(q[at:])
    found.text = " ".join(" ".join(kept).split())
    return found
