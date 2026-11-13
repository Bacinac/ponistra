"""Events taken from a personal account (D15, S4): each item once, into one of the user's own
calendars, and ours afterwards."""

from django.db import transaction

from apps.content import palette

from . import events
from .ical import Found
from .models import Calendar, Taken, ordered


def colors() -> int:
    return len(palette.calendars())


def next_color(owner_id: int) -> int:
    return Calendar.objects.filter(owner_id=owner_id).count() % colors()


def own(owner_id: int, name: str) -> Calendar:
    """A new calendar of the user's own, in the next colour."""
    return Calendar.objects.create(owner_id=owner_id, name=name[:200], color=next_color(owner_id))


@transaction.atomic
def taken(
    account,
    kind: str,
    source: str,
    item: str,
    calendar: Calendar,
    found: list[Found],
    data,
    feed=None,
) -> bool:
    """Puts the item's event into the calendar; whether it was new. An event the calendar
    already holds by its UID is not put in twice, and the item is still counted as taken."""
    owner_id = calendar.owner_id
    ordered(owner_id)
    item = item[:500]
    if Taken.objects.filter(owner_id=owner_id, kind=kind, source=source, item=item).exists():
        return False
    taking = Taken(
        owner_id=owner_id,
        account=account,
        kind=kind,
        source=source,
        item=item,
        data=data,
        feed=feed,
    )
    master = found[0]
    if master.uid and not calendar.events.filter(uid=master.uid, master__isnull=True).exists():
        made = events.made(calendar, master)
        for each in found[1:]:
            if each.recurrence_id is not None:
                events.made(calendar, each, master=made)
        taking.event = made
    taking.save()
    return taking.event_id is not None
