"""Who and what is taken when: the people of this installation by the events of their calendars,
the rooms and resources by the events booked on them. Nothing of anyone outside the installation
is known, and nothing of an event but that it fills the time."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.core.api import Refused
from apps.mail import absence
from apps.mail.models import Away

from . import recurrence, workdays
from .models import Booking, Event, Resource

FREE, BUSY, UNKNOWN = "free", "busy", "unknown"
# How far ahead a booking is checked against the others: a series without an end would run for
# ever, and a room booked a year ahead is a year's notice for whoever clashes with it.
AHEAD = timedelta(days=366)
MOST_RESOURCES = 50
# A meeting is offered on the half hours of the working day, the first few within two months.
STEP = timedelta(minutes=30)
SEARCHED = timedelta(days=62)
MOST_OFFERS = 6


def _masters(rows):
    """The series of the events given, each once and fresh: an override stands for its series."""
    wanted = {(each.master_id or each.pk) for each in rows}
    return (
        Event.objects.filter(pk__in=wanted)
        .select_related("calendar__owner")
        .prefetch_related("overrides", "bookings", "overrides__bookings")
    )


def _of(master: Event, apart: int | None) -> bool:
    return apart is not None and apart in {master.pk, *(each.pk for each in master.overrides.all())}


def _happening(master: Event, since: datetime, until: datetime) -> list[recurrence.Occurrence]:
    found = recurrence.occurrences(master, list(master.overrides.all()), since, until)
    return [each for each in found if each.shown.status != Event.Status.CANCELLED]


def _fills(occurrence: recurrence.Occurrence) -> bool:
    return occurrence.shown.busy and occurrence.shown.response != "declined"


def _addressed(wanted: set[str]) -> tuple[list, dict[int, set[str]]]:
    """The people of this installation among the addresses, and which of them each answers to."""
    users = list(
        get_user_model()
        .objects.filter(Q(email__in=wanted) | Q(mail_accounts__address__in=wanted))
        .prefetch_related("mail_accounts")
        .distinct()
    )
    addressed = defaultdict(set)
    for user in users:
        for address in (user.email, *(each.address for each in user.mail_accounts.all())):
            if address.lower() in wanted:
                addressed[user.pk].add(address.lower())
    return users, addressed


def away(emails: set[str], since: datetime, until: datetime) -> dict[str, datetime]:
    """Of the addresses, those of people away for any of the time, with when they come back."""
    users, addressed = _addressed({each.lower() for each in emails})
    back = absence.overlapping([each.pk for each in users], since, until)
    return {address: back[pk] for pk in back for address in addressed[pk]}


def _held(owners: list[int], since: datetime, until: datetime, apart: int | None) -> dict:
    """For each owner, the times between the instants their calendars fill, apart from the event
    named (any row of its series)."""
    found = {each: [] for each in owners}
    rows = Event.objects.filter(
        Q(rrule__gt="") | Q(rdates__len__gt=0) | Q(ends__gt=since),
        calendar__owner__in=owners,
        master__isnull=True,
        starts__lt=until,
    ).exclude(status=Event.Status.CANCELLED)
    for master in _masters(rows):
        if _of(master, apart):
            continue
        found[master.calendar.owner_id] += [
            (each.start, each.end) for each in _happening(master, since, until) if _fills(each)
        ]
    return found


def people(emails: set[str], since: datetime, until: datetime, apart: int | None) -> dict:
    """Each address: free or busy between the instants, or unknown where it is nobody of this
    installation. The event `apart` (any row of its series) counts against no one."""
    wanted = {each.lower() for each in emails}
    users, addressed = _addressed(wanted)
    found = dict.fromkeys(wanted, UNKNOWN)
    for pk, held in _held([each.pk for each in users], since, until, apart).items():
        for address in addressed[pk]:
            found[address] = BUSY if held else FREE
    return found


def taken(resources, since: datetime, until: datetime, apart: int | None) -> dict[int, list]:
    """For each resource, when it is booked between the instants (start, end, occurrence), apart
    from the event named."""
    found = {each.pk: [] for each in resources}
    rows = Booking.objects.filter(resource__in=resources).select_related("event")
    for master in _masters([each.event for each in rows]):
        if _of(master, apart):
            continue
        booked_on = {
            row.pk: {each.resource_id for each in row.bookings.all()}
            for row in (master, *master.overrides.all())
        }
        for occurrence in _happening(master, since, until):
            for resource_id in booked_on.get(occurrence.shown.pk, set()):
                if resource_id in found:
                    found[resource_id].append((occurrence.start, occurrence.end, occurrence))
    return found


def resources(wanted, since: datetime, until: datetime, apart: int | None) -> dict[int, str]:
    return {pk: BUSY if held else FREE for pk, held in taken(wanted, since, until, apart).items()}


def booked(event: Event, chosen: list[Resource]) -> None:
    """The event booked on exactly the resources chosen; Refused where one of them is already
    taken at a time the event happens."""
    Booking.objects.filter(event=event).exclude(resource__in=chosen).delete()
    for each in chosen:
        Booking.objects.get_or_create(event=event, resource=each)
    if not chosen:
        return
    master = Event.objects.prefetch_related("overrides").get(pk=event.master_id or event.pk)
    since, until = event.starts, event.starts + AHEAD
    own = [
        (each.start, each.end)
        for each in recurrence.occurrences(master, list(master.overrides.all()), since, until)
        if each.shown.pk == event.pk
    ]
    held = taken(chosen, since, until, master.pk)
    for resource in chosen:
        for start, end, _ in held[resource.pk]:
            if any(recurrence._overlaps(began, over, start, end) for began, over in own):
                raise Refused(409, "resource_taken")


def chosen(data: dict) -> list[Resource] | None:
    """The resources the interface put on the event, or None where it sent nothing of them."""
    if "resources" not in data:
        return None
    given = data["resources"]
    if (
        not isinstance(given, list)
        or len(given) > MOST_RESOURCES
        or not all(isinstance(each, int) for each in given)
    ):
        raise Refused(400, "invalid_resource")
    found = list(Resource.objects.filter(pk__in=given, active=True))
    if len(found) != len(set(given)):
        raise Refused(400, "invalid_resource")
    return found


def wanted(raw: str):
    return Resource.objects.filter(pk__in=[int(e) for e in raw.split(",") if e.isdigit()])


def offers(
    emails: set[str], owners: list[int], wanted, length: timedelta, since: datetime, apart
) -> list[tuple[datetime, datetime]]:
    """The first times from `since`, on the installation's working days and within its working
    hours, at which the people of the addresses, the owners and the resources are all free for
    the length, apart from the event named. Nobody outside the installation is known, so nobody
    outside holds a time."""
    users, _ = _addressed({each.lower() for each in emails})
    owners = list({*owners, *(each.pk for each in users)})
    until = since + SEARCHED
    blocked = [held for each in _held(owners, since, until, apart).values() for held in each]
    blocked += [
        (start, end)
        for each in taken(wanted, since, until, apart).values()
        for start, end, _ in each
    ]
    blocked += list(
        Away.objects.filter(owner__in=owners, starts_at__lt=until, ends_at__gt=since).values_list(
            "starts_at", "ends_at"
        )
    )
    blocked = sorted((start, end) for start, end in blocked if end > start)
    days = workdays.days()
    clock = timezone.get_default_timezone()
    found: list[tuple[datetime, datetime]] = []
    day = since.astimezone(clock).date()
    while day <= until.astimezone(clock).date() and len(found) < MOST_OFFERS:
        if days.working(day):
            opens = datetime.combine(day, days.opens, clock).astimezone(UTC)
            closes = datetime.combine(day, days.closes, clock).astimezone(UTC)
            at = _on_step(opens, max(opens, since))
            while at + length <= closes and len(found) < MOST_OFFERS:
                clash = next(
                    (end for start, end in blocked if start < at + length and end > at), None
                )
                if clash is None:
                    found.append((at, at + length))
                    clash = at + length
                at = _on_step(opens, clash)
        day += timedelta(days=1)
    return found


def _on_step(opens: datetime, moment: datetime) -> datetime:
    """The first half hour of the day from the opening at or after the moment."""
    return opens + -((opens - moment) // STEP) * STEP
