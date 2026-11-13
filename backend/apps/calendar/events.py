"""Events kept and given back (D15, S4): one row a single event or a series' master, one more
for each occurrence changed on its own. Every change takes the next revision under the owner's
lock, by which a phone asks what changed since."""

import uuid
from dataclasses import replace
from datetime import datetime

from django.db import transaction

from . import ical
from .models import Calendar, Event, Gone, ordered, revised

SCOPES = ("this", "following", "all")


def series(event: Event) -> tuple[Event, list[Event]]:
    """The event's master and the occurrences changed on their own, in order."""
    master = event.master or event
    return master, list(master.overrides.order_by("recurrence_id", "pk"))


def written(event: Event) -> str:
    master, overrides = series(event)
    return ical.written(master, overrides)


def _fields(found: ical.Found) -> dict:
    """The found's fields, the way in online taken from its words where nothing else gives one."""
    return {
        **found.fields,
        "conference": found.conference or ical.meeting_in(found.location, found.description),
    }


def found_of(event: Event) -> ical.Found:
    """The event's fields as a Found, to be saved changed."""
    return ical.Found(
        uid=event.uid,
        recurrence_id=event.recurrence_id,
        **{name: getattr(event, name) for name in ical.FIELDS},
    )


def stand_in(master: Event, at: datetime) -> Event:
    """The occurrence at the instant as a row of its own, for a change to lie over."""
    made = Event(**{name: getattr(master, name) for name in ical.FIELDS})
    made.starts, made.ends = at, at + (master.ends - master.starts)
    made.rrule, made.rdates, made.exdates = "", [], []
    return made


def revise(*events: Event) -> None:
    """The events changed take the next revisions, in one order with every other change."""
    pks = [each.pk for each in events if each.pk]
    if pks:
        Event.objects.filter(pk__in=pks).update(revision=revised())


@transaction.atomic
def made(
    calendar: Calendar, found: ical.Found, href: str = "", master: Event | None = None
) -> Event:
    """A new event in the calendar: a single one or a master, or with `master` one occurrence of
    it changed on its own."""
    ordered(calendar.owner_id)
    uid = found.uid or (master.uid if master else f"{uuid.uuid4()}@ponistra")
    event = Event.objects.create(
        calendar=calendar,
        uid=uid,
        href=master.href if master else href or f"{uuid.uuid4().hex}.ics",
        master=master,
        recurrence_id=found.recurrence_id if master else None,
        **_fields(found),
    )
    if master:
        revise(master)
    return event


@transaction.atomic
def saved(event: Event, found: ical.Found) -> Event:
    """The event as the found has it. A way in its words gave follows the words: a form, a phone
    or a server handing it back unchanged only hands back what it read."""
    ordered(event.calendar.owner_id)
    worded = event.conference in f"{event.location}\n{event.description}"
    if event.conference and worded and found.conference == event.conference:
        found = replace(found, conference="")
    for name, value in _fields(found).items():
        setattr(event, name, value)
    event.save()
    revise(event, event.master or event)
    return Event.objects.get(pk=event.pk)


@transaction.atomic
def replaced(master: Event, found: list[ical.Found]) -> Event:
    """The series as a phone PUT it back: the master with these fields, and exactly these
    occurrences changed on their own."""
    ordered(master.calendar.owner_id)
    saved(master, found[0])
    kept = []
    for each in found[1:]:
        override = master.overrides.filter(recurrence_id=each.recurrence_id).first()
        if override is None:
            override = made(master.calendar, each, master=master)
        else:
            saved(override, each)
        kept.append(override.pk)
    master.overrides.exclude(pk__in=kept).delete()
    revise(master)
    return Event.objects.get(pk=master.pk)


@transaction.atomic
def deleted(event: Event) -> None:
    """The event goes: a master with its occurrences, and its name is kept for the phones; an
    occurrence changed on its own goes back into its series."""
    calendar = event.calendar
    ordered(calendar.owner_id)
    if event.master_id:
        master = event.master
        event.delete()
        revise(master)
        return
    event.delete()
    Gone.objects.create(owner_id=calendar.owner_id, calendar=calendar, href=event.href)
