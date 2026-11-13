"""When a series happens (RFC 5545): its rule unfolded on the wall clock of its zone, the dates
added to and taken from it, and the occurrences changed on their own in their place. The browser
only draws what this gives."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import takewhile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rruleset, rrulestr

from . import workdays
from .models import Event

# The most occurrences unfolded for one event in one window, against a rule that never ends.
MOST = 2000
# The most days an occurrence moves to reach a working day, past the longest run of days off: a
# collective leave with the weekends and holidays about it.
FURTHEST_MOVE = 62
# How many years ahead a phone or an invitation is told where days off put a series, as no
# calendar but PONISTRA works it out from the rule.
TOLD_YEARS = 10
UNTIL = re.compile(r"UNTIL=([0-9TZ]+)")


@dataclass(frozen=True)
class Occurrence:
    """One time an event happens: `shown` is the row with its details, the master or an override
    in its place; `recurrence_id` is the start the master's series gave it, None for a single
    event."""

    shown: Event
    master: Event
    start: datetime
    end: datetime
    recurrence_id: datetime | None

    @property
    def moved(self) -> bool:
        return self.shown is not self.master


def zone_of(name: str):
    try:
        return ZoneInfo(name) if name else UTC
    except ZoneInfoNotFoundError:
        return UTC


def as_day(moment: datetime) -> date:
    """The day an all-day event's instant stands for."""
    return moment.astimezone(UTC).date()


def day_instant(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def shown(moment: datetime, all_day: bool, zone: str, end: bool = False) -> str:
    """An instant as the interface shows it: the day of an all-day event, its last day for the
    end, else the time on the user's clock."""
    if all_day:
        day = as_day(moment)
        return (day - timedelta(days=1) if end else day).isoformat()
    return moment.astimezone(zone_of(zone)).isoformat()


def local(event: Event, moment: datetime) -> datetime | date:
    """The instant on the event's clock: a day for an all-day event, else the wall time."""
    if event.all_day:
        return as_day(moment)
    return moment.astimezone(zone_of(event.zone))


def instant(event: Event, given: datetime | date) -> datetime:
    """A time on the event's clock as an instant."""
    if isinstance(given, datetime):
        if given.tzinfo is None:
            given = given.replace(tzinfo=zone_of(event.zone))
        return given.astimezone(UTC)
    return day_instant(given)


def rule_text(event: Event) -> str:
    """The event's RRULE with its UNTIL on the event's clock, as dateutil wants it beside the
    start: a date for an all-day series, a UTC instant for a timed one."""

    def until(match: re.Match) -> str:
        raw = match.group(1)
        if event.all_day:
            return f"UNTIL={raw[:8]}"
        if raw.endswith("Z") or len(raw) == 8:
            if len(raw) == 8:
                day = datetime.strptime(raw, "%Y%m%d").replace(tzinfo=zone_of(event.zone))
                last = (day + timedelta(days=1, seconds=-1)).astimezone(UTC)
                return f"UNTIL={last:%Y%m%dT%H%M%SZ}"
            return match.group(0)
        floating = datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=zone_of(event.zone))
        return f"UNTIL={floating.astimezone(UTC):%Y%m%dT%H%M%SZ}"

    return UNTIL.sub(until, event.rrule)


def dated(event: Event, given: str) -> datetime | date | None:
    """An RDATE or EXDATE as kept, on the event's clock."""
    try:
        parsed = date.fromisoformat(given) if len(given) == 10 else datetime.fromisoformat(given)
    except ValueError:
        return None
    if event.all_day:
        return (
            parsed
            if isinstance(parsed, date) and not isinstance(parsed, datetime)
            else as_day(instant(event, parsed))
        )
    if isinstance(parsed, datetime):
        return instant(event, parsed).astimezone(zone_of(event.zone))
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=zone_of(event.zone))


def _naive(given: datetime | date) -> datetime:
    """An all-day series counts in naive midnights."""
    if isinstance(given, datetime):
        return given.replace(tzinfo=None)
    return datetime(given.year, given.month, given.day)


def series(event: Event) -> rruleset | None:
    """The set of starts the master's rule, RDATEs and EXDATEs give; None for a single event."""
    if not event.rrule and not event.rdates:
        return None
    start = local(event, event.starts)
    made = rruleset()
    if event.all_day:
        start = _naive(start)
    if event.rrule:
        made.rrule(rrulestr(rule_text(event), dtstart=start, forceset=False))
    else:
        made.rdate(start)
    for given in event.rdates:
        if (found := dated(event, given)) is not None:
            made.rdate(_naive(found) if event.all_day else found)
    for given in event.exdates:
        if (found := dated(event, given)) is not None:
            made.exdate(_naive(found) if event.all_day else found)
    return made


def _starts(rules: rruleset, first: datetime, last: datetime) -> list[datetime]:
    """The starts from `first` to `last` inclusive, no more than MOST of them, unfolded one by one
    so that a rule repeating by the second never unfolds whole."""
    return list(takewhile(lambda each: each <= last, rules.xafter(first, count=MOST, inc=True)))


def _instant_of(event: Event, start: datetime) -> datetime:
    """A start the series gives, naive midnight for an all-day one, as an instant."""
    return instant(event, start.date() if event.all_day else start)


def _placed(event: Event, starts: list[datetime]) -> list[tuple[datetime, datetime | None]]:
    """Each start the rule gives with where the event's way with days off puts it: on itself, on
    the nearest working day before or after, or nowhere when it is skipped or would fall where
    another occurrence already is."""
    working = workdays.days().working if event.day_off and starts else None
    placed = []
    for start in starts:
        to: datetime | None = start
        if working and not working(start.date()):
            to = None
            if event.day_off != Event.DayOff.SKIPPED:
                step = timedelta(days=-1 if event.day_off == Event.DayOff.BEFORE else 1)
                to = next(
                    (
                        start + step * distance
                        for distance in range(1, FURTHEST_MOVE + 1)
                        if working((start + step * distance).date())
                    ),
                    None,
                )
        placed.append((start, to))
    taken = {start for start, to in placed if to == start}
    kept = []
    for start, to in placed:
        if to is not None and to != start:
            if to in taken:
                to = None
            else:
                taken.add(to)
        kept.append((start, to))
    return kept


def days_off(master: Event) -> list[tuple[datetime | date, datetime | date | None]]:
    """The occurrences the master's way with days off moves or skips, on its clock, for TOLD_YEARS
    after its last change: each one's start by the rule and where it goes, None when skipped."""
    rules = series(master)
    if rules is None or not master.day_off:
        return []
    start = local(master, master.starts)
    horizon = (master.changed_at or master.starts) + timedelta(days=365 * TOLD_YEARS)
    if master.all_day:
        first, last = _naive(start), _naive(as_day(horizon))
    else:
        first, last = start, horizon.astimezone(zone_of(master.zone))
    return [
        (
            given.date() if master.all_day else given,
            None if to is None else to.date() if master.all_day else to,
        )
        for given, to in _placed(master, _starts(rules, first, last))
        if to != given
    ]


def _overlaps(start: datetime, end: datetime, since: datetime, until: datetime) -> bool:
    return start < until and (end > since or (end == start and start >= since))


def occurrences(
    master: Event, overrides: list[Event], since: datetime, until: datetime
) -> list[Occurrence]:
    """Every time the event happens between the instants, the overrides in their places and the
    ones moved into the window among them."""
    duration = master.ends - master.starts
    by_id = {each.recurrence_id: each for each in overrides}
    found: list[Occurrence] = []
    seen: set[datetime] = set()
    rules = series(master)
    if rules is None:
        if _overlaps(master.starts, master.ends, since, until):
            found.append(Occurrence(master, master, master.starts, master.ends, None))
    else:
        if master.all_day:
            first = _naive(as_day(since) - duration)
            last = _naive(as_day(until) + timedelta(days=1))
        else:
            zone = zone_of(master.zone)
            first = (since - duration).astimezone(zone)
            last = until.astimezone(zone)
        margin = timedelta(days=FURTHEST_MOVE if master.day_off else 0)
        for start, placed in _placed(master, _starts(rules, first - margin, last + margin)):
            began = _instant_of(master, start)
            seen.add(began)
            if (changed := by_id.get(began)) is not None:
                if _overlaps(changed.starts, changed.ends, since, until):
                    found.append(Occurrence(changed, master, changed.starts, changed.ends, began))
            elif placed is not None:
                at = _instant_of(master, placed)
                if _overlaps(at, at + duration, since, until):
                    found.append(Occurrence(master, master, at, at + duration, began))
    for changed in overrides:
        if changed.recurrence_id in seen or changed.recurrence_id is None:
            continue
        if _overlaps(changed.starts, changed.ends, since, until):
            found.append(
                Occurrence(changed, master, changed.starts, changed.ends, changed.recurrence_id)
            )
    found.sort(key=lambda each: (each.start, each.end))
    return found


def placed(master: Event, at: datetime) -> datetime:
    """Where the master's way with days off puts the occurrence its rule gives at the instant."""
    if not master.day_off:
        return at
    reach = timedelta(days=FURTHEST_MOVE + 1)
    return next(
        (
            each.start
            for each in occurrences(master, [], at - reach, at + reach)
            if each.recurrence_id == at
        ),
        at,
    )


def first_after(master: Event, moment: datetime) -> datetime | None:
    """The master's first occurrence starting at or after the instant, by its rule alone."""
    rules = series(master)
    if rules is None:
        return master.starts if master.starts >= moment else None
    at = _naive(as_day(moment)) if master.all_day else moment.astimezone(zone_of(master.zone))
    start = rules.after(at, inc=True)
    if start is None:
        return None
    return instant(master, start.date() if master.all_day else start)
