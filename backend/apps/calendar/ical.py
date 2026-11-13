"""iCalendar (RFC 5545) read and written: what a phone PUTs and a personal account's CalDAV
gives, and what a phone reads back. A series is one VCALENDAR: its master and, after it, each
occurrence changed on its own."""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from logging import getLogger
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone
from icalendar import Alarm, Calendar, vCalAddress, vRecur, vText
from icalendar import Event as Component
from icalendar.timezone.windows_to_olson import WINDOWS_TO_OLSON

from . import workdays
from .models import Event
from .recurrence import (
    TOLD_YEARS,
    as_day,
    day_instant,
    days_off,
    instant,
    local,
    occurrences,
    rule_text,
    zone_of,
)

log = getLogger(__name__)

PRODID = "-//PONISTRA//EN"
# How a series treats days off (Event.DayOff) on its master, and MOVED on each occurrence it
# moved, which PONISTRA writes out itself for any other calendar to show.
DAY_OFF = "X-PONISTRA-DAY-OFF"
MOVED = "moved"
HANDLED = {
    DAY_OFF,
    "UID",
    "DTSTART",
    "DTEND",
    "DURATION",
    "RRULE",
    "RDATE",
    "EXDATE",
    "RECURRENCE-ID",
    "SUMMARY",
    "LOCATION",
    "DESCRIPTION",
    "STATUS",
    "TRANSP",
    "CLASS",
    "ORGANIZER",
    "ATTENDEE",
    "SEQUENCE",
    "DTSTAMP",
    "CREATED",
    "LAST-MODIFIED",
}
STATUSES = {"CONFIRMED": "confirmed", "TENTATIVE": "tentative", "CANCELLED": "cancelled"}
METHODS = {"REQUEST": "request", "CANCEL": "cancel", "REPLY": "reply", "COUNTER": "counter"}
ROLES = {
    "REQ-PARTICIPANT": "required",
    "OPT-PARTICIPANT": "optional",
    "CHAIR": "chair",
    "NON-PARTICIPANT": "informed",
}
PARTSTATS = {
    "NEEDS-ACTION": "needs-action",
    "ACCEPTED": "accepted",
    "DECLINED": "declined",
    "TENTATIVE": "tentative",
    "DELEGATED": "declined",
}
# A reminder further ahead than this is a mistake of a converter, not a wish.
FARTHEST = 4 * 7 * 24 * 60
# Where a meeting is joined: RFC 7986's property, then what Teams and Google write instead.
CONFERENCES = ("CONFERENCE", "X-MICROSOFT-SKYPETEAMSMEETINGURL", "X-GOOGLE-CONFERENCE")
# Where an invitation gives its way in only in words: each service's link to join, not the others
# its text carries beside it (Zoom's .ics of a series, its invitation page, its local numbers).
MEETINGS = (
    r"(?:[\w-]+\.)?zoom(?:gov)?\.us/(?:j|w|my|s|wc/join)/",
    r"teams\.(?:microsoft\.com|live\.com|cloud\.microsoft)/(?:l/meetup-join|meet)/",
    r"meet\.google\.com/[a-z]+-[a-z]+-[a-z]+\b",
    r"[\w-]+\.webex\.com/(?:meet/|join/|wbxmjs/joinservice/|[\w.-]+/j\.php)",
    r"meet\.goto\.com/",
    r"(?:global|app)\.gotomeeting\.com/join/",
    r"meet\.jit\.si/\w",
    r"whereby\.com/\w",
    r"join\.skype\.com/",
)


class Malformed(ValueError):
    pass


@dataclass
class Found:
    """An event as an iCalendar gave it, in PONISTRA's terms."""

    uid: str = ""
    recurrence_id: datetime | None = None
    summary: str = ""
    location: str = ""
    conference: str = ""
    description: str = ""
    all_day: bool = False
    starts: datetime = field(default_factory=lambda: datetime.now(UTC))
    ends: datetime = field(default_factory=lambda: datetime.now(UTC))
    zone: str = ""
    rrule: str = ""
    rdates: list[str] = field(default_factory=list)
    exdates: list[str] = field(default_factory=list)
    day_off: str = ""
    status: str = "confirmed"
    busy: bool = True
    private: bool = False
    organizer: dict = field(default_factory=dict)
    attendees: list[dict] = field(default_factory=list)
    reminders: list[int] = field(default_factory=list)
    response: str = ""
    sequence: int = 0
    extra: list[str] = field(default_factory=list)

    @property
    def fields(self) -> dict:
        return {name: getattr(self, name) for name in FIELDS}


FIELDS = [
    "summary",
    "location",
    "conference",
    "description",
    "all_day",
    "starts",
    "ends",
    "zone",
    "rrule",
    "rdates",
    "exdates",
    "day_off",
    "status",
    "busy",
    "private",
    "organizer",
    "attendees",
    "reminders",
    "response",
    "sequence",
    "extra",
]


def described(found: Found) -> dict:
    """What an invitation says of its meeting, as it is kept with the invitation."""
    return {
        "summary": found.summary,
        "location": found.location,
        "all_day": found.all_day,
        "start": found.starts.isoformat(),
        "end": found.ends.isoformat(),
        "zone": found.zone,
        "rrule": found.rrule,
        "status": found.status,
        "organizer": found.organizer,
        "attendees": found.attendees,
    }


def zone_named(name: str) -> str:
    """The IANA name of a zone a source names, Windows names among them; "" where none is."""
    if not name:
        return ""
    try:
        return ZoneInfo(name).key
    except ZoneInfoNotFoundError, ValueError:
        return WINDOWS_TO_OLSON.get(name, "")


def _zone(moment: datetime) -> str:
    found = moment.tzinfo
    if found is None:
        return settings.TIME_ZONE
    if isinstance(found, ZoneInfo):
        return found.key if found.key != "UTC" else ""
    name = getattr(found, "key", None) or getattr(found, "zone", None) or ""
    named = zone_named(str(name))
    if not named and found.utcoffset(moment) == timedelta(0):
        return ""
    return named or settings.TIME_ZONE


def _instant(moment: datetime, zone: str) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone_of(zone))
    return moment.astimezone(UTC)


def _dated_text(given, all_day: bool, zone: str) -> str:
    if isinstance(given, datetime):
        if all_day:
            return _instant(given, zone).date().isoformat()
        return _instant(given, zone).isoformat()
    if all_day:
        return given.isoformat()
    return (
        datetime(given.year, given.month, given.day, tzinfo=zone_of(zone))
        .astimezone(UTC)
        .isoformat()
    )


def _address(value) -> str:
    return str(value).removeprefix("mailto:").removeprefix("MAILTO:").strip().lower()


def _attendee(value) -> dict:
    params = getattr(value, "params", {})
    return {
        "email": _address(value),
        "name": str(params.get("CN", "")).strip(),
        "status": PARTSTATS.get(
            str(params.get("PARTSTAT", "NEEDS-ACTION")).upper(), "needs-action"
        ),
        "role": ROLES.get(str(params.get("ROLE", "REQ-PARTICIPANT")).upper(), "required"),
    }


def _listed(component: Component, name: str) -> list:
    given = component.get(name)
    if given is None:
        return []
    return given if isinstance(given, list) else [given]


def _reminders(component: Component) -> list[int]:
    found = []
    for alarm in component.walk("VALARM"):
        trigger = alarm.get("TRIGGER")
        action = str(alarm.get("ACTION", "DISPLAY")).upper()
        if trigger is None or action == "EMAIL":
            continue
        value = trigger.dt
        if not isinstance(value, timedelta):
            continue
        if str(trigger.params.get("RELATED", "START")).upper() == "END":
            continue
        minutes = -int(value.total_seconds() // 60)
        if 0 <= minutes <= FARTHEST and minutes not in found:
            found.append(minutes)
    return sorted(found)


def web(value) -> str:
    """The value if it is a web link, else nothing."""
    given = str(value or "").strip()
    return given if given.startswith(("https://", "http://")) else ""


def meeting_in(*texts: str) -> str:
    """The first link among the texts that joins a meeting, a meeting of PONISTRA's among them."""
    ours = re.escape(settings.PUBLIC_URL.split("://", 1)[-1]) + r"/meet/[0-9a-f-]{36}\b"
    link = re.compile(rf"https?://(?:{'|'.join((*MEETINGS, ours))})[^\s<>\"']*", re.IGNORECASE)
    for text in texts:
        for found in link.finditer(text):
            given = found[0].rstrip(".,;:!?)]")
            if len(given) <= Event._meta.get_field("conference").max_length:
                return given
    return ""


def _conference(component: Component) -> str:
    links = (web(each) for name in CONFERENCES for each in _listed(component, name))
    return next((each for each in links if each), "")


def _extra(component: Component, conference: str) -> list[str]:
    """The lines PONISTRA keeps without showing them: a meeting's other ways in (a phone number)
    among them, but not the conference it shows, which the event's own field writes."""
    kept = []
    for name, value in component.property_items(recursive=False):
        if name in HANDLED or name in ("BEGIN", "END"):
            continue
        if name == "CONFERENCE" and str(value).strip() == conference:
            continue
        try:
            kept.append(str(component.content_line(name, value)))
        except Exception:
            log.warning("calendar: property %s could not be kept", name)
    return kept


def _found(component: Component) -> Found:
    start = component.start
    end = component.end
    found = Found(uid=str(component.get("UID", "")).strip())
    found.all_day = not isinstance(start, datetime)
    if found.all_day:
        if isinstance(end, datetime):
            end = end.date()
        if end <= start:
            end = start + timedelta(days=1)
        found.starts, found.ends = day_instant(start), day_instant(end)
    else:
        found.zone = _zone(start)
        found.starts = _instant(start, found.zone)
        if not isinstance(end, datetime):
            end = datetime(end.year, end.month, end.day, tzinfo=start.tzinfo)
        found.ends = max(_instant(end, found.zone), found.starts)
    if (recurrence_id := component.get("RECURRENCE-ID")) is not None:
        given = recurrence_id.dt
        if found.all_day:
            found.recurrence_id = day_instant(
                given.date() if isinstance(given, datetime) else given
            )
        elif isinstance(given, datetime):
            found.recurrence_id = _instant(given, found.zone)
        else:
            found.recurrence_id = _instant(datetime(given.year, given.month, given.day), found.zone)
    if rules := component.rrules:
        found.rrule = rules[0].to_ical().decode()
    found.rdates = [_dated_text(start, found.all_day, found.zone) for start, _ in component.rdates]
    found.exdates = [_dated_text(each, found.all_day, found.zone) for each in component.exdates]
    day_off = str(component.get(DAY_OFF, "")).strip().lower()
    found.day_off = day_off if day_off in (*Event.DayOff.values, MOVED) else ""
    found.summary = str(component.get("SUMMARY", "")).strip()
    found.location = str(component.get("LOCATION", "")).strip()
    found.conference = _conference(component)
    found.description = str(component.get("DESCRIPTION", "")).strip()
    found.status = STATUSES.get(str(component.get("STATUS", "")).upper(), "confirmed")
    found.busy = str(component.get("TRANSP", "OPAQUE")).upper() != "TRANSPARENT"
    found.private = str(component.get("CLASS", "PUBLIC")).upper() in ("PRIVATE", "CONFIDENTIAL")
    if (organizer := component.get("ORGANIZER")) is not None and _address(organizer):
        found.organizer = {
            "email": _address(organizer),
            "name": str(getattr(organizer, "params", {}).get("CN", "")).strip(),
        }
    found.attendees = [_attendee(each) for each in _listed(component, "ATTENDEE") if _address(each)]
    found.reminders = _reminders(component)
    try:
        found.sequence = max(int(component.get("SEQUENCE", 0)), 0)
    except TypeError, ValueError:
        found.sequence = 0
    found.extra = _extra(component, found.conference)
    return found


def imip(text: str) -> tuple[str, list[Found]]:
    """What a calendar in the mail asks (RFC 6047, `METHODS`; "" where it asks nothing) and the
    events of the one meeting it names: the master first where it comes, then the occurrences
    changed on their own, which a change or a cancellation may name alone. Days off are the
    organizer's: what they moved or skipped stays as they wrote it."""
    method, found = _read(text)
    for each in found:
        each.day_off = ""
    return method, found


def _read(text: str) -> tuple[str, list[Found]]:
    try:
        calendar = Calendar.from_ical(text)
    except Exception as failed:
        raise Malformed(str(failed)) from None
    method = METHODS.get(str(calendar.get("METHOD", "")).upper(), "")
    events = [each for each in calendar.walk("VEVENT")]
    if not events:
        raise Malformed("no event")
    try:
        found = [_found(each) for each in events]
    except Malformed:
        raise
    except Exception as failed:
        raise Malformed(str(failed)) from None
    uids = {each.uid for each in found}
    if len(uids) != 1 or not found[0].uid and len(found) > 1:
        raise Malformed("more than one event")
    found.sort(key=lambda each: each.recurrence_id is not None)
    if sum(each.recurrence_id is None for each in found) > 1:
        raise Malformed("more than one master")
    return method, found


def parsed(text: str) -> list[Found]:
    """The events of the iCalendar: the master first, then the occurrences changed on their own.
    More than one series in it is malformed, as a calendar resource holds one."""
    _, found = _read(text)
    return settled(found)


def settled(found: list[Found]) -> list[Found]:
    """The series as a phone gives it back, the master first: what PONISTRA wrote out of the
    series' way with days off comes back as that way alone."""
    master = found[0]
    if master.recurrence_id is not None:
        raise Malformed("no master")
    if master.day_off == MOVED:
        master.day_off = ""
    if master.day_off == Event.DayOff.SKIPPED:
        working = workdays.days().working
        master.exdates = [each for each in master.exdates if working(_day_of(each, master.zone))]
    overrides = [each for each in found[1:] if each.day_off != MOVED]
    for each in overrides:
        each.day_off = ""
    return [master, *overrides]


def closed(text: str, today: date) -> list[tuple[date, date, str]]:
    """The days each event of an iCalendar takes from the start of this year for TOLD_YEARS, as
    its first and last day with its summary: what an administrator takes as days the organisation
    closes. A series gives each of its occurrences; a cancelled or nameless one gives nothing."""
    try:
        found = [_found(each) for each in Calendar.from_ical(text).walk("VEVENT")]
    except Exception as failed:
        raise Malformed(str(failed)) from None
    since = day_instant(date(today.year, 1, 1))
    until = day_instant(date(today.year + TOLD_YEARS, 1, 1))
    by_uid: dict[str, list[Event]] = {}
    for each in found:
        made = Event(**{**each.fields, "day_off": ""})
        made.recurrence_id = each.recurrence_id
        by_uid.setdefault(each.uid or str(id(each)), []).append(made)
    spans = set()
    for events in by_uid.values():
        masters = [each for each in events if each.recurrence_id is None]
        overrides = [each for each in events if each.recurrence_id is not None]
        if not masters:
            masters, overrides = overrides, []
        for master in masters:
            for each in occurrences(master, overrides, since, until):
                shown = each.shown
                if shown.status == Event.Status.CANCELLED or not shown.summary:
                    continue
                if shown.all_day:
                    first = as_day(each.start)
                    last = max(as_day(each.end) - timedelta(days=1), first)
                else:
                    zone = zone_of(shown.zone or master.zone)
                    first = each.start.astimezone(zone).date()
                    last = max(
                        (each.end - timedelta(microseconds=1)).astimezone(zone).date(), first
                    )
                spans.add((first, last, shown.summary[:200]))
    return sorted(spans)


def _day_of(given: str, zone: str) -> date:
    if len(given) == 10:
        return date.fromisoformat(given)
    return datetime.fromisoformat(given).astimezone(zone_of(zone)).date()


def _on_clock(event: Event, moment: datetime, master: Event) -> datetime | date:
    if master.all_day:
        return as_day(moment)
    return moment.astimezone(zone_of(master.zone))


def _dated(event: Event, given: str) -> datetime | date | None:
    try:
        if len(given) == 10:
            parsed_date = date.fromisoformat(given)
            if event.all_day:
                return parsed_date
            return datetime(
                parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=zone_of(event.zone)
            )
        moment = datetime.fromisoformat(given)
    except ValueError:
        return None
    return local(event, instant(event, moment))


def _component(event: Event, master: Event, now: datetime) -> Component:
    made = Component()
    made.add("UID", event.uid)
    made.add("DTSTAMP", now)
    made.add("DTSTART", local(event, event.starts))
    made.add("DTEND", local(event, event.ends))
    if event.recurrence_id is not None:
        made.add("RECURRENCE-ID", _on_clock(event, event.recurrence_id, master))
    if event.rrule:
        made.add("RRULE", vRecur.from_ical(rule_text(event)))
    for name, given in (("RDATE", event.rdates), ("EXDATE", event.exdates)):
        dated = [found for each in given if (found := _dated(event, each)) is not None]
        if dated:
            made.add(name, dated)
    if event.recurrence_id is None and event.rrule and event.day_off:
        made.add(DAY_OFF, event.day_off.upper())
    for name, value in (
        ("SUMMARY", event.summary),
        ("LOCATION", event.location),
        ("DESCRIPTION", event.description),
    ):
        if value:
            made.add(name, value)
    if event.conference:
        made.add(
            "CONFERENCE",
            event.conference,
            parameters={"VALUE": "URI", "FEATURE": ["AUDIO", "VIDEO"]},
        )
    made.add("STATUS", event.status.upper())
    if not event.busy:
        made.add("TRANSP", "TRANSPARENT")
    if event.private:
        made.add("CLASS", "PRIVATE")
    if email := event.organizer.get("email"):
        organizer = vCalAddress(f"mailto:{email}")
        if name := event.organizer.get("name"):
            organizer.params["CN"] = vText(name)
        made.add("ORGANIZER", organizer)
    for each in event.attendees:
        attendee = vCalAddress(f"mailto:{each.get('email', '')}")
        if name := each.get("name"):
            attendee.params["CN"] = vText(name)
        attendee.params["CUTYPE"] = vText("INDIVIDUAL")
        attendee.params["ROLE"] = vText(
            next(
                (key for key, value in ROLES.items() if value == each.get("role")),
                "REQ-PARTICIPANT",
            )
        )
        attendee.params["PARTSTAT"] = vText(
            next(
                (key for key, value in PARTSTATS.items() if value == each.get("status")),
                "NEEDS-ACTION",
            )
        )
        made.add("ATTENDEE", attendee)
    made.add("SEQUENCE", event.sequence)
    made.add("CREATED", event.created_at or now)
    made.add("LAST-MODIFIED", event.changed_at or now)
    for line in event.extra:
        try:
            kept = Component.from_ical(f"BEGIN:VEVENT\r\n{line}\r\nEND:VEVENT")
        except Exception:
            continue
        for name, value in kept.property_items(recursive=False):
            if name not in ("BEGIN", "END"):
                made.add(name, value, encode=False)
    for minutes in event.reminders:
        alarm = Alarm()
        alarm.add("ACTION", "DISPLAY")
        alarm.add("DESCRIPTION", event.summary or "Ponistra")
        alarm.add("TRIGGER", -timedelta(minutes=minutes))
        made.add_component(alarm)
    return made


def _whole(master: Event, overrides: list[Event], now: datetime) -> list[Component]:
    """The series: its master, the occurrences changed on their own, and what its way with days
    off does as a calendar without PONISTRA's rule is told it, the occurrences skipped taken from
    the master and each one moved written on its own."""
    made = [_component(each, master, now) for each in (master, *overrides)]
    changed = {each.recurrence_id for each in overrides}
    duration = master.ends - master.starts
    skipped = []
    for at, to in days_off(master):
        began = instant(master, at)
        if began in changed:
            continue
        if to is None:
            skipped.append(at)
            continue
        moved = Event(
            **{name: getattr(master, name) for name in FIELDS},
            uid=master.uid,
            recurrence_id=began,
            created_at=master.created_at,
            changed_at=master.changed_at,
        )
        moved.rrule, moved.rdates, moved.exdates = "", [], []
        moved.starts = instant(master, to)
        moved.ends = moved.starts + duration
        made.append(_component(moved, master, now))
        made[-1].add(DAY_OFF, MOVED.upper())
    if skipped:
        made[0].add("EXDATE", skipped)
    return made


def told(master: Event, overrides: list[Event]) -> list[Found]:
    """The series as `written` gives it, in PONISTRA's terms."""
    return [_found(each) for each in _whole(master, overrides, timezone.now())]


def written(master: Event, overrides: list[Event]) -> str:
    calendar = Calendar()
    calendar.add("PRODID", PRODID)
    calendar.add("VERSION", "2.0")
    calendar.add("CALSCALE", "GREGORIAN")
    for each in _whole(master, overrides, timezone.now()):
        calendar.add_component(each)
    years = {each.starts.year for each in (master, *overrides)}
    calendar.add_missing_timezones(
        first_date=date(min(years) - 1, 1, 1), last_date=date(max(years) + 10, 1, 1)
    )
    return calendar.to_ical().decode()


def replied(event: Event, attendee: dict, now: datetime) -> str:
    """The user's answer as iMIP carries it to the organizer: the meeting named, the one attendee
    answering with how they stand."""
    master = event.master or event
    calendar = Calendar()
    calendar.add("PRODID", PRODID)
    calendar.add("VERSION", "2.0")
    calendar.add("METHOD", "REPLY")
    made = Component()
    made.add("UID", event.uid)
    made.add("DTSTAMP", now)
    made.add("DTSTART", local(event, event.starts))
    made.add("DTEND", local(event, event.ends))
    if event.recurrence_id is not None:
        made.add("RECURRENCE-ID", _on_clock(event, event.recurrence_id, master))
    if event.summary:
        made.add("SUMMARY", event.summary)
    if email := event.organizer.get("email"):
        organizer = vCalAddress(f"mailto:{email}")
        if name := event.organizer.get("name"):
            organizer.params["CN"] = vText(name)
        made.add("ORGANIZER", organizer)
    answering = vCalAddress(f"mailto:{attendee['email']}")
    if name := attendee.get("name"):
        answering.params["CN"] = vText(name)
    answering.params["PARTSTAT"] = vText(
        next(key for key, value in PARTSTATS.items() if value == attendee["status"])
    )
    made.add("ATTENDEE", answering)
    made.add("SEQUENCE", event.sequence)
    calendar.add_component(made)
    calendar.add_missing_timezones(
        first_date=date(event.starts.year - 1, 1, 1), last_date=date(event.starts.year + 10, 1, 1)
    )
    return calendar.to_ical().decode()


def _calendar_with(method: str, parts: list[Component], years: set[int]) -> str:
    calendar = Calendar()
    calendar.add("PRODID", PRODID)
    calendar.add("VERSION", "2.0")
    calendar.add("METHOD", method)
    for each in parts:
        calendar.add_component(each)
    calendar.add_missing_timezones(
        first_date=date(min(years) - 1, 1, 1), last_date=date(max(years) + 10, 1, 1)
    )
    return calendar.to_ical().decode()


def requested(master: Event, parts: list[Event], now: datetime) -> str:
    """The meeting as iMIP asks the attendees to it: the whole series, or the one occurrence
    changed on its own."""
    whole = parts[0].recurrence_id is None
    return _calendar_with(
        "REQUEST",
        _whole(parts[0], parts[1:], now)
        if whole
        else [_component(each, master, now) for each in parts],
        {each.starts.year for each in parts},
    )


def cancelled(event: Event, master: Event, to: list[dict], now: datetime) -> str:
    """The meeting, or its one occurrence, as iMIP takes it back from the attendees named: the
    organizer's next sequence, so that it outranks what they hold."""
    made = _component(event, master, now)
    made["STATUS"] = vText("CANCELLED")
    made["SEQUENCE"] = event.sequence + 1
    del made["ATTENDEE"]
    for each in to:
        attendee = vCalAddress(f"mailto:{each.get('email', '')}")
        if name := each.get("name"):
            attendee.params["CN"] = vText(name)
        made.add("ATTENDEE", attendee)
    return _calendar_with("CANCEL", [made], {event.starts.year})
