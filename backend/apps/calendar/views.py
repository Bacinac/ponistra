"""The user's calendars (D15, S4): the calendars they keep and the ones their organisations
show them, and what happens when, the series expanded here so the interface only reads."""

import copy
import re
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.contacts import cards
from apps.contacts.models import Contact
from apps.contacts.vcard import shown_name
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.journal import entries
from apps.journal.entries import Kind
from apps.mail import sharing
from apps.mail.models import Account
from apps.mail.servers import known_as
from apps.users.accounts import administrator

from . import availability, ical, invitations, recurrence, taking, workdays
from . import events as kept
from .ical import FIELDS, Found, web
from .models import Booking, Calendar, Closure, Event, Feed, Gone, Resource, Taken, ordered

BIRTHDAY = re.compile(r"^(\d{4}|-)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
NAME = 200
TEXT = 2000
NOTE = 20000
RULE = 500
LONGEST = 366
REMINDERS = 10
FARTHEST = 4 * 7 * 24 * 60
COUNT = re.compile(r";?(COUNT|UNTIL)=[^;]*")

CALENDAR = sharing.owned_by(Calendar)
EVENT = sharing.owned_by(Event, "calendar__owner_id")
FEED = sharing.owned_by(Feed, "account__owner_id")
IN_CALENDAR = sharing.sent_from(Calendar, "calendar")


def concerned(key: str) -> set[int] | None:
    """Whom a change to the calendar concerns: its owner, and those a mailbox owning it is shared
    with (`live`)."""
    owner = Calendar.objects.filter(pk=int(key)).values_list("owner_id", flat=True).first()
    return set() if owner is None else sharing.concerned(str(owner))


def zone_of(name) -> str:
    try:
        return ZoneInfo(name).key if name else settings.TIME_ZONE
    except ZoneInfoNotFoundError, TypeError, ValueError:
        raise Refused(400, "invalid_zone") from None


def _account(calendar: Calendar) -> Account | None:
    if calendar.account_id:
        return calendar.account
    fed = next(iter(calendar.feeds.all()), None)
    return fed.account if fed else None


def describe_calendar(calendar: Calendar) -> dict:
    found = _account(calendar)
    account = known_as(found) if found else None
    named_by_address = found is not None and calendar.name.casefold() == found.address.casefold()
    return {
        "id": calendar.pk,
        "name": account if named_by_address else calendar.name,
        "color": calendar.color,
        "kind": calendar.kind,
        "read_only": calendar.read_only,
        "account": account,
    }


def _failed(user) -> list[dict]:
    found = (
        Feed.objects.filter(account__owner=user)
        .exclude(error="")
        .values_list("account__label", "account__address", "error")
    )
    return [
        {"account": label or address, "error": error}
        for label, address, error in dict.fromkeys(found)
    ]


def dropped(calendar: Calendar) -> None:
    """Deletes the calendar; one fed from an account is left unfollowed at its provider, and
    what was taken through it is forgotten, so following it again takes its events again."""
    with transaction.atomic():
        feeds = list(calendar.feeds.all())
        Taken.objects.filter(feed__in=feeds).delete()
        Feed.objects.filter(pk__in=[each.pk for each in feeds]).update(followed=False, key="")
        calendar.delete()


def _unfollowed(user) -> list[dict]:
    found = (
        Feed.objects.filter(account__owner=user, followed=False)
        .select_related("account")
        .order_by("account__address", "name")
    )
    return [{"id": each.pk, "name": each.name, "account": known_as(each.account)} for each in found]


@api("POST")
@sharing.boxed(of=FEED)
def feed(request, pk):
    """Follows a dropped calendar of an account again: it is back at once, its events with the
    next taking."""
    feeds = Feed.objects.filter(pk=pk, account__owner=request.user)
    found = feeds.select_related("account").first()
    if found is None:
        raise Refused(404, "not_found")
    if found.calendar_id is None:
        found.calendar = taking.own(request.user.pk, found.name or found.account.address)
    found.followed = True
    found.save(update_fields=["calendar", "followed"])
    return JsonResponse(describe_calendar(found.calendar), status=201)


def _own(user, pk) -> Calendar:
    found = Calendar.objects.select_related("account").filter(owner=user, pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


def _named(data: dict, calendar: Calendar) -> None:
    if "name" in data:
        name = str(data.get("name") or "").strip()[:NAME]
        if not name:
            raise Refused(400, "name_required")
        calendar.name = name
    if "color" in data:
        try:
            calendar.color = int(data["color"]) % taking.colors()
        except TypeError, ValueError:
            raise Refused(400, "invalid_color") from None


def _role(request):
    """The person's role in the shared mailbox the request acts in; none in their own."""
    if request.user == request.person:
        return None
    return sharing.role_in(request.person, request.user.pk)


@api("GET", "POST")
@sharing.boxed()
def calendars(request):
    user = request.user
    if request.method == "POST":
        data = body(request)
        made = taking.own(user.pk, str(data.get("name") or "").strip() or "Kalendar")
        _named(data, made)
        made.save()
        return JsonResponse(describe_calendar(made), status=201)
    found = (
        Calendar.objects.filter(owner=user)
        .select_related("account")
        .prefetch_related("feeds__account")
        .order_by("pk")
    )
    role = _role(request)
    described = [describe_calendar(each) for each in found]
    if role == sharing.READ:
        described = [{**each, "read_only": True} for each in described]
    return JsonResponse(
        {
            "calendars": described,
            "role": role,
            "next_color": taking.next_color(user.pk),
            "unfollowed": _unfollowed(user),
            "failed": _failed(user),
            "zone": settings.TIME_ZONE,
        }
    )


@api("PATCH", "DELETE")
@sharing.boxed(of=CALENDAR)
def calendar(request, pk):
    found = _own(request.user, pk)
    if request.method == "DELETE":
        if found.read_only:
            raise Refused(403, "read_only")
        dropped(found)
        return HttpResponse(status=204)
    data = body(request)
    if found.read_only and "name" in data:
        raise Refused(403, "read_only")
    _named(data, found)
    found.save()
    return JsonResponse(describe_calendar(found))


def _day(raw, what: str) -> date:
    try:
        return date.fromisoformat(str(raw))
    except TypeError, ValueError:
        raise Refused(400, f"invalid_{what}") from None


def _moment(raw, zone: str, what: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(raw))
    except TypeError, ValueError:
        raise Refused(400, f"invalid_{what}") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=recurrence.zone_of(zone))
    return parsed.astimezone(UTC)


def _described(event: Event, zone: str) -> dict:
    master = event.master or event
    return {
        "id": event.pk,
        "calendar": event.calendar_id,
        "master": event.master_id,
        "recurrence_id": recurrence.shown(event.recurrence_id, master.all_day, zone)
        if event.recurrence_id
        else None,
        "summary": event.summary,
        "location": event.location,
        "conference": event.conference,
        "description": event.description,
        "all_day": event.all_day,
        "start": recurrence.shown(event.starts, event.all_day, zone),
        "end": recurrence.shown(event.ends, event.all_day, zone, end=True),
        "zone": event.zone,
        "rrule": master.rrule,
        "day_off": master.day_off,
        "exdates": master.exdates,
        "status": event.status,
        "busy": event.busy,
        "private": event.private,
        "organizer": event.organizer,
        "attendees": event.attendees,
        "response": event.response,
        "reminders": event.reminders,
        "read_only": event.calendar.read_only,
        "resources": sorted(each.resource_id for each in event.bookings.all()),
        "changed_at": event.changed_at,
    }


def _conference(raw) -> str:
    given = str(raw or "").strip()
    if given and (len(given) > TEXT or not web(given)):
        raise Refused(400, "invalid_conference")
    return given


def rule_of(raw) -> str:
    rule = str(raw or "").strip().upper()[:RULE]
    if not rule:
        return ""
    rule = rule.removeprefix("RRULE:")
    try:
        rrulestr(rule, dtstart=datetime(2026, 1, 1))
    except ValueError, TypeError, KeyError:
        raise Refused(400, "invalid_rrule") from None
    return rule


def reminders_of(raw) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise Refused(400, "invalid_reminders")
    found = []
    for each in raw[:REMINDERS]:
        try:
            minutes = int(each)
        except TypeError, ValueError:
            raise Refused(400, "invalid_reminders") from None
        if 0 <= minutes <= FARTHEST:
            found.append(minutes)
    return sorted(set(found))


def _found(data: dict, before: Event | None, zone: str) -> Found:
    """An event as the interface sent it, over what the row held before where it sent only
    part."""
    found = Found()
    if before is not None:
        for name in FIELDS:
            setattr(found, name, getattr(before, name))
    if "zone" in data or before is None:
        found.zone = zone_of(data.get("zone") or zone)
    if "all_day" in data:
        found.all_day = bool(data["all_day"])
    if "start" in data or "end" in data or "all_day" in data:
        start = data.get("start", recurrence.shown(found.starts, found.all_day, found.zone))
        end = data.get("end", recurrence.shown(found.ends, found.all_day, found.zone, end=True))
        if found.all_day:
            first, last = _day(start, "start"), _day(end, "end")
            if last < first or last - first > timedelta(days=LONGEST):
                raise Refused(400, "invalid_end")
            found.starts = recurrence.day_instant(first)
            found.ends = recurrence.day_instant(last + timedelta(days=1))
        else:
            found.starts = _moment(start, found.zone, "start")
            found.ends = _moment(end, found.zone, "end")
            if found.ends < found.starts or found.ends - found.starts > timedelta(days=LONGEST):
                raise Refused(400, "invalid_end")
    for name, most in (("summary", NAME), ("location", TEXT), ("description", NOTE)):
        if name in data:
            setattr(found, name, str(data.get(name) or "").strip()[:most])
    if "conference" in data:
        found.conference = _conference(data["conference"])
    if "rrule" in data:
        found.rrule = rule_of(data["rrule"])
    if "day_off" in data:
        if data["day_off"] not in Event.DayOff.values:
            raise Refused(400, "invalid_day_off")
        found.day_off = data["day_off"]
    if "status" in data:
        if data["status"] not in ("confirmed", "tentative", "cancelled"):
            raise Refused(400, "invalid_status")
        found.status = data["status"]
    for name in ("busy", "private"):
        if name in data:
            setattr(found, name, bool(data[name]))
    if "reminders" in data:
        found.reminders = reminders_of(data["reminders"])
    if before is not None:
        found.sequence = before.sequence + 1
    return found


def _window(request, zone: str) -> tuple[datetime, datetime, date, date]:
    first = _day(request.GET.get("from"), "from")
    last = _day(request.GET.get("to"), "to")
    if last < first or last - first > timedelta(days=LONGEST):
        raise Refused(400, "invalid_to")
    clock = ZoneInfo(zone)
    since = datetime(first.year, first.month, first.day, tzinfo=clock).astimezone(UTC)
    until = datetime.combine(last + timedelta(days=1), datetime.min.time(), clock).astimezone(UTC)
    return since, until, first, last


def _occurrence(found: recurrence.Occurrence, zone: str) -> dict:
    shown = found.shown
    return {
        "event": shown.pk,
        "master": found.master.pk,
        "calendar": shown.calendar_id,
        "recurrence_id": recurrence.shown(found.recurrence_id, found.master.all_day, zone)
        if found.recurrence_id
        else None,
        "summary": shown.summary,
        "location": shown.location,
        "conference": shown.conference,
        "all_day": shown.all_day,
        "start": recurrence.shown(found.start, shown.all_day, zone),
        "end": recurrence.shown(found.end, shown.all_day, zone, end=True),
        "status": shown.status,
        "busy": shown.busy,
        "private": shown.private,
        "recurring": bool(found.master.rrule or found.master.rdates),
        "moved": found.moved,
        "response": shown.response,
        "attendees": len(shown.attendees),
    }


def _birthdays(user, first: date, last: date) -> list[dict]:
    """Whose birthday falls in the days, from the address book, with the age where the year is
    known."""
    found = []
    for contact in (
        Contact.objects.filter(owner=user, group=False)
        .exclude(birthday="")
        .select_related("entry")
        .prefetch_related("points")
    ):
        match = BIRTHDAY.match(contact.birthday)
        if not match:
            continue
        year, month, day = match.groups()
        for each in range(first.year, last.year + 1):
            try:
                when = date(each, int(month), int(day))
            except ValueError:
                when = date(each, 3, 1)
            if first <= when <= last:
                shown = cards.card(contact, photo=False)
                found.append(
                    {
                        "date": when.isoformat(),
                        "contact": contact.pk,
                        "name": shown_name(shown.fields, shown.points),
                        "age": each - int(year) if year != "-" else None,
                    }
                )
    found.sort(key=lambda each: (each["date"], each["name"]))
    return found


def _language(data: dict) -> str:
    return data.get("language") if data.get("language") in invitations.INVITING else "en"


def _created(request) -> tuple[dict, list[invitations.Notice], str]:
    zone = zone_of(request.GET.get("zone") or request.headers.get("X-Zone"))
    return created_event(request.user, zone, body(request))


def created_event(user, zone: str, data: dict) -> tuple[dict, list[invitations.Notice], str]:
    """A new event in one of the user's calendars, with the notices its attendees are owed."""
    calendar = _own(user, data.get("calendar"))
    if calendar.read_only:
        raise Refused(403, "read_only")
    found = _found(data, None, zone)
    if not found.summary:
        raise Refused(400, "summary_required")
    invitations.arranged(user, found, None, invitations.given(data))
    resources = availability.chosen(data)
    with transaction.atomic():
        made = kept.made(calendar, found)
        availability.booked(made, resources or [])
    return _described(made, zone), invitations.changes(user, None, made, [made]), _language(data)


def occurrences_of(visible, since: datetime, until: datetime, zone: str) -> list[dict]:
    """Each occurrence of the calendars' events in the window, as the interface shows it."""
    found = []
    masters = (
        Event.objects.filter(calendar__in=visible, master__isnull=True)
        .select_related("calendar")
        .prefetch_related("overrides")
    )
    for master in masters:
        for each in recurrence.occurrences(master, list(master.overrides.all()), since, until):
            found.append(_occurrence(each, zone))
    found.sort(key=lambda each: (each["start"], each["end"], each["event"]))
    return found


def _listed(request) -> JsonResponse:
    user = request.user
    zone = zone_of(request.GET.get("zone") or request.headers.get("X-Zone"))
    since, until, first, last = _window(request, zone)
    visible = Calendar.objects.filter(owner=user)
    if given := request.GET.get("calendars"):
        wanted = [int(each) for each in given.split(",") if each.isdigit()]
        visible = visible.filter(pk__in=wanted)
    found = occurrences_of(visible, since, until, zone)
    bookings = []
    if asked := request.GET.get("resources"):
        for pk, held in availability.taken(availability.wanted(asked), since, until, None).items():
            for start, end, each in held:
                shown = each.shown
                by = each.master.calendar.owner
                bookings.append(
                    {
                        "resource": pk,
                        "start": recurrence.shown(start, shown.all_day, zone),
                        "end": recurrence.shown(end, shown.all_day, zone, end=True),
                        "all_day": shown.all_day,
                        "by": by.get_full_name() or by.email,
                        "summary": "" if shown.private else shown.summary,
                    }
                )
    bookings.sort(key=lambda each: (each["start"], each["end"]))
    days = workdays.days()
    return JsonResponse(
        {
            "events": found,
            "bookings": bookings,
            "holidays": [
                {"date": day.isoformat(), "hr": hr, "en": en}
                for day, hr, en in days.named(first, last)
            ],
            "days_off": [day.isoformat() for day in days.off(first, last)],
            "birthdays": _birthdays(user, first, last),
        }
    )


@api("GET", "POST")
@sharing.boxed(of=IN_CALENDAR)
async def events(request):
    if request.method == "GET":
        return await database(_listed)(request)
    made, notices, language = await database(_created)(request)
    await invitations.told(language, notices)
    return JsonResponse(made, status=201)


def _loaded(user, pk) -> Event:
    found = (
        Event.objects.select_related("calendar", "master")
        .filter(pk=pk, calendar__owner=user)
        .first()
    )
    if found is None:
        raise Refused(404, "not_found")
    return found


def _scope(request) -> str:
    scope = request.GET.get("scope", "this")
    if scope not in kept.SCOPES:
        raise Refused(400, "invalid_scope")
    return scope


def _at(raw, master: Event, zone: str) -> datetime:
    """The occurrence the interface means, by the start its series gave it."""
    if not raw:
        raise Refused(400, "recurrence_id_required")
    if master.all_day:
        return recurrence.day_instant(_day(raw, "recurrence_id"))
    return _moment(raw, zone, "recurrence_id")


def _recurrence_id(request, master: Event, zone: str) -> datetime:
    return _at(request.GET.get("recurrence_id") or body(request).get("recurrence_id"), master, zone)


def _exdate(master: Event, moment: datetime) -> str:
    if master.all_day:
        return recurrence.as_day(moment).isoformat()
    return moment.astimezone(UTC).isoformat()


def _ended_before(master: Event, split: datetime) -> str:
    """The master's rule ending with the last occurrence before the instant."""
    rule = COUNT.sub("", master.rrule).strip(";")
    if master.all_day:
        return f"{rule};UNTIL={recurrence.as_day(split) - timedelta(days=1):%Y%m%d}"
    return f"{rule};UNTIL={split - timedelta(seconds=1):%Y%m%dT%H%M%SZ}"


def _remaining(master: Event, split: datetime, rule: str) -> str:
    """The rule for the series going on from the split: the master's COUNT, where the rule keeps
    it, less what the first series keeps."""
    match = re.search(r"COUNT=(\d+)", master.rrule)
    if not match or match.group(0) not in rule.split(";"):
        return rule
    at = recurrence.local(master, split)
    if master.all_day:
        at = datetime(at.year, at.month, at.day)
    before = sum(1 for each in recurrence.series(master) if each < at)
    return COUNT.sub("", rule).strip(";") + f";COUNT={max(int(match.group(1)) - before, 1)}"


def _kept(master: Event, split: datetime, after: bool) -> list[str]:
    return [
        each
        for each in master.exdates
        if (dated := recurrence.dated(master, each)) is not None
        and (recurrence.instant(master, dated) >= split) == after
    ]


@transaction.atomic
def _split(master: Event, split: datetime, found: Found | None) -> Event | None:
    """The series cut before the instant: the master keeps what came before; the rest goes on as
    a new series with the fields given, or goes entirely when none are."""
    ordered(master.calendar.owner_id)
    first = recurrence.first_after(master, master.starts)
    if first is not None and first >= split:
        if found is None:
            kept.deleted(master)
            return None
        kept.saved(master, found)
        return master
    rest = None
    if found is not None:
        found.exdates = _kept(master, split, after=True)
        found.uid = ""
        rest = kept.made(master.calendar, found)
        shift = found.starts - split
        for each in master.overrides.filter(recurrence_id__gte=split):
            each.master = rest
            each.uid = rest.uid
            _along(each, master, shift, found.ends - found.starts)
            each.save()
    else:
        master.overrides.filter(recurrence_id__gte=split).delete()
    master.rrule = _ended_before(master, split)
    master.exdates = _kept(master, split, after=False)
    master.save()
    kept.revise(master)
    return rest


@transaction.atomic
def _moved(master: Event, target: Calendar) -> None:
    """The event, its series with it, into another of the user's calendars."""
    ordered(target.owner_id)
    Gone.objects.create(owner_id=target.owner_id, calendar=master.calendar, href=master.href)
    Event.objects.filter(pk=master.pk).update(calendar=target)
    master.overrides.update(calendar=target)
    kept.revise(master, *master.overrides.all())


def _parts(event: Event) -> list[Event]:
    """What a notice of the event carries: the series whole, or the one occurrence."""
    if event.master_id:
        return [event]
    master, overrides = kept.series(event)
    return [master, *overrides]


def _occurrence_of(master: Event, at: datetime) -> Event:
    """The occurrence the rule gives at the instant, where the attendees know it to be."""
    stood = master.overrides.filter(recurrence_id=at).first() or kept.stand_in(
        master, recurrence.placed(master, at)
    )
    stood.uid, stood.recurrence_id, stood.master = master.uid, at, master
    return stood


def _changed(request, pk) -> tuple[dict | None, list[invitations.Notice], str]:
    user = request.user
    zone = zone_of(request.GET.get("zone") or request.headers.get("X-Zone"))
    found = _loaded(user, pk)
    if found.calendar.read_only:
        raise Refused(403, "read_only")
    recurring = found.master_id is None and bool(found.rrule or found.rdates)
    scope = _scope(request) if recurring else "all"
    if request.method == "DELETE":
        language = _language(request.GET)
        if scope == "all":
            notices = invitations.withdrawn(user, found)
            kept.deleted(found)
            return None, notices, language
        at = _recurrence_id(request, found, zone)
        before = copy.copy(found)
        if scope == "following":
            whole = invitations.withdrawn(user, found)
            _split(found, at, None)
            if not Event.objects.filter(pk=pk).exists():
                return None, whole, language
            after = _loaded(user, pk)
            return None, invitations.changes(user, before, after, _parts(after)), language
        notices = invitations.withdrawn(user, _occurrence_of(found, at))
        found.overrides.filter(recurrence_id=at).delete()
        found.exdates = [*found.exdates, _exdate(found, at)]
        found.save()
        kept.revise(found)
        return None, notices, language
    data = body(request)
    language = _language(data)
    attendees = invitations.given(data)
    resources = availability.chosen(data)
    if "calendar" in data and data["calendar"] != found.calendar_id:
        if found.master_id:
            raise Refused(400, "invalid_calendar")
        target = _own(user, data["calendar"])
        if target.read_only:
            raise Refused(403, "read_only")
        try:
            _moved(found, target)
        except IntegrityError:
            raise Refused(409, "uid_conflict") from None
        found = _loaded(user, pk)
    before = copy.copy(found)
    if scope == "this":
        at = _recurrence_id(request, found, zone)
        override = found.overrides.filter(recurrence_id=at).first()
        prior = copy.copy(override) if override else _occurrence_of(found, at)
        changed = _found(data, override or kept.stand_in(found, at), zone)
        changed.recurrence_id = at
        changed.rrule, changed.rdates, changed.exdates = "", [], []
        invitations.arranged(user, changed, prior, attendees)
        with transaction.atomic():
            if override is None:
                override = kept.made(found.calendar, changed, master=found)
            else:
                kept.saved(override, changed)
            _booked(override, resources, prior)
        after = _loaded(user, override.pk)
        notices = invitations.changes(user, prior, after, [after])
        return _described(after, zone), notices, language
    if scope == "following":
        at = _recurrence_id(request, found, zone)
        prior = _occurrence_of(found, at)
        changed = _found(data, kept.stand_in(found, at), zone)
        changed.rrule = _remaining(found, at, changed.rrule if "rrule" in data else found.rrule)
        invitations.arranged(user, changed, prior, attendees)
        with transaction.atomic():
            rest = _split(found, at, changed)
            _booked(rest, resources, found)
        after = _loaded(user, rest.pk)
        notices = invitations.changes(user, before, after, _parts(after))
        if rest.pk != pk:
            first = _loaded(user, pk)
            notices += invitations.changes(user, before, first, _parts(first))
        return _described(after, zone), notices, language
    changed = _found(data, found, zone)
    if found.master_id:
        changed.recurrence_id = found.recurrence_id
        changed.rrule, changed.rdates, changed.exdates = "", [], []
    elif recurring and data.get("recurrence_id") and ("start" in data or "end" in data):
        at = _at(data["recurrence_id"], found, zone)
        timed = _found(data, kept.stand_in(found, at), zone)
        changed.starts = found.starts + (timed.starts - _occurrence_of(found, at).starts)
        changed.ends = changed.starts + (timed.ends - timed.starts)
    invitations.arranged(user, changed, found, attendees)
    with transaction.atomic():
        if recurring and changed.starts != found.starts:
            _shifted(found, changed, changed.starts - found.starts)
        kept.saved(found, changed)
        _booked(found, resources, found)
    after = _loaded(user, pk)
    notices = invitations.changes(user, before, after, _parts(after))
    return _described(after, zone), notices, language


def _booked(event: Event, resources: list[Resource] | None, before: Event) -> None:
    """The event on the resources the interface chose, or on those the row it grew from had:
    its own, or its master's where the occurrence stood in for the master until now."""
    if resources is None:
        held = Booking.objects.filter(event=before.pk or before.master_id).select_related(
            "resource"
        )
        resources = [each.resource for each in held]
    availability.booked(event, resources)


@api("GET", "PATCH", "DELETE")
@sharing.boxed(of=EVENT)
async def event(request, pk):
    if request.method == "GET":
        return await database(_shown)(request, pk)
    payload, notices, language = await database(_changed)(request, pk)
    await invitations.told(language, notices)
    if payload is None:
        return HttpResponse(status=204)
    return JsonResponse(payload)


def _shown(request, pk) -> JsonResponse:
    zone = zone_of(request.GET.get("zone") or request.headers.get("X-Zone"))
    described = _described(_loaded(request.user, pk), zone)
    if _role(request) == sharing.READ:
        described["read_only"] = True
    return JsonResponse(described)


@api("POST")
@sharing.boxed(of=EVENT)
async def response(request, pk):
    """The user's answer to a meeting they are asked to: accepted, tentative or declined, told
    to whoever asked and kept on the event."""
    data = body(request)
    given = data.get("response")
    if given not in invitations.RESPONSES:
        raise Refused(400, "invalid_response")
    language = data.get("language") if data.get("language") in invitations.WORDED else "en"
    found = await database(_loaded)(request.user, pk)
    await invitations.answered(request.user, found, given, language)
    return await database(_shown)(request, pk)


def _shifted(master: Event, changed: Found, shift: timedelta) -> None:
    """A series moved as a whole takes its exceptions along: each occurrence changed on its own
    and each left out keeps its place in the series."""
    changed.exdates = [
        _exdate(master, recurrence.instant(master, dated) + shift)
        for each in master.exdates
        if (dated := recurrence.dated(master, each)) is not None
    ]
    for each in master.overrides.all():
        _along(each, master, shift, changed.ends - changed.starts)
        each.save(update_fields=["recurrence_id", "starts", "ends"])


def _along(override: Event, master: Event, shift: timedelta, duration: timedelta) -> None:
    """An occurrence changed on its own follows the series' new place, and takes its new time
    too unless it was moved to a time of its own."""
    kept_time = (
        override.starts == override.recurrence_id
        and override.ends - override.starts == master.ends - master.starts
    )
    override.recurrence_id = override.recurrence_id + shift
    if kept_time:
        override.starts = override.recurrence_id
        override.ends = override.starts + duration


def _resource(resource: Resource) -> dict:
    return {
        "id": resource.pk,
        "name": resource.name,
        "kind": resource.kind,
        "capacity": resource.capacity,
        "place": resource.place,
        "active": resource.active,
    }


def _filled(resource: Resource, data: dict) -> None:
    if "name" in data:
        resource.name = str(data.get("name") or "").strip()[:200]
        if not resource.name:
            raise Refused(400, "resource_name_required")
    if "kind" in data:
        if data["kind"] not in Resource.Kind.values:
            raise Refused(400, "invalid_kind")
        resource.kind = data["kind"]
    if "capacity" in data:
        given = data["capacity"]
        if given is not None and (not isinstance(given, int) or given < 0 or given > 100000):
            raise Refused(400, "invalid_capacity")
        resource.capacity = given or None
    if "place" in data:
        resource.place = str(data.get("place") or "").strip()[:200]
    if "active" in data:
        resource.active = bool(data["active"])


@api("GET", "POST")
def resources(request):
    """The rooms and resources of the installation: everyone reads the ones in use, an
    administrator keeps them."""
    if request.method == "GET":
        found = Resource.objects.all()
        if not request.user.is_staff:
            found = found.filter(active=True)
        return JsonResponse({"resources": [_resource(each) for each in found]})
    administrator(request)
    made = Resource()
    data = body(request)
    _filled(made, {"name": "", **data})
    try:
        with transaction.atomic():
            made.save()
    except IntegrityError:
        raise Refused(409, "resource_name_taken") from None
    entries.wrote(
        Kind.SETTING_CHANGED, request=request, setting="resource", change="added", name=made.name
    )
    return JsonResponse(_resource(made), status=201)


@api("PATCH", "DELETE")
def resource(request, pk):
    administrator(request)
    found = Resource.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        found.delete()
        entries.wrote(
            Kind.SETTING_CHANGED,
            request=request,
            setting="resource",
            change="removed",
            name=found.name,
        )
        return HttpResponse(status=204)
    _filled(found, body(request))
    try:
        with transaction.atomic():
            found.save()
    except IntegrityError:
        raise Refused(409, "resource_name_taken") from None
    entries.wrote(
        Kind.SETTING_CHANGED, request=request, setting="resource", change="changed", name=found.name
    )
    return JsonResponse(_resource(found))


def _workdays(today: date) -> dict:
    days = workdays.days()
    return {
        "country": days.country,
        "subdivision": days.subdivision,
        "opens": days.opens.strftime("%H:%M"),
        "closes": days.closes.strftime("%H:%M"),
        "countries": {
            each: [list(region) for region in workdays.subdivisions(each)]
            for each in workdays.COUNTRIES
        },
        "holidays": [
            {"date": day.isoformat(), "hr": hr, "en": en}
            for day, hr, en in replace(days, closed={}).named(today, today + timedelta(days=365))
        ],
        "closures": [_closure(each) for each in Closure.objects.all()],
    }


def _closure(closure: Closure) -> dict:
    return {
        "id": closure.pk,
        "first": closure.first.isoformat(),
        "last": closure.last.isoformat(),
        "name": closure.name,
    }


def _closure_of(data, kept: Closure | None = None) -> Closure:
    if not isinstance(data, dict):
        raise Refused(400, "invalid_closure")
    made = kept or Closure()
    if "first" in data or kept is None:
        made.first = _day(data.get("first"), "closure")
    if "last" in data or kept is None:
        made.last = _day(data.get("last"), "closure")
    if "name" in data or kept is None:
        made.name = str(data.get("name") or "").strip()
    if not 0 < len(made.name) <= 200 or made.last < made.first:
        raise Refused(400, "invalid_closure")
    return made


@api("GET")
def days_off(request):
    """The installation's days off between two days, for a calendar that shows no events."""
    _, _, first, last = _window(request, "UTC")
    return JsonResponse({"days_off": [day.isoformat() for day in workdays.days().off(first, last)]})


@api("GET", "PATCH")
def working_days(request):
    """Where the installation works, whose holidays are its days off, and the days it closes
    besides: the administrator keeps them, and every series that minds days off follows."""
    administrator(request)
    today = timezone.localdate()
    if request.method == "GET":
        return JsonResponse(_workdays(today))
    data = body(request)
    if "opens" in data or "closes" in data:
        opens, closes = _clock(data.get("opens")), _clock(data.get("closes"))
        if opens is None or closes is None or closes <= opens:
            raise Refused(400, "invalid_hours")
        workdays.hours(request.user, opens, closes)
        entries.wrote(
            Kind.SETTING_CHANGED,
            request=request,
            setting="hours",
            opens=opens.strftime("%H:%M"),
            closes=closes.strftime("%H:%M"),
        )
        return JsonResponse(_workdays(today))
    country = str(data.get("country") or "").upper()
    subdivision = str(data.get("subdivision") or "")
    if country not in workdays.COUNTRIES:
        raise Refused(400, "invalid_country")
    if subdivision and subdivision not in workdays.COUNTRIES[country]:
        raise Refused(400, "invalid_subdivision")
    workdays.changed(request.user, country=country, subdivision=subdivision)
    entries.wrote(
        Kind.SETTING_CHANGED,
        request=request,
        setting="workdays",
        country=country,
        subdivision=subdivision,
    )
    return JsonResponse(_workdays(today))


def _clock(raw) -> time | None:
    if not isinstance(raw, str) or not re.fullmatch(r"\d{2}:\d{2}", raw):
        return None
    try:
        return time.fromisoformat(raw)
    except ValueError:
        return None


@api("POST")
def closures(request):
    administrator(request)
    given = body(request).get("closures")
    if not isinstance(given, list) or not given:
        raise Refused(400, "invalid_closure")
    made = [_closure_of(each) for each in given]
    with transaction.atomic():
        Closure.objects.bulk_create(made)
        workdays.changed(request.user)
        entries.wrote(
            Kind.SETTING_CHANGED,
            request=request,
            setting="closures",
            change="added",
            name=", ".join(each.name for each in made)[:200],
        )
    return JsonResponse({"closures": [_closure(each) for each in made]}, status=201)


@api("PATCH", "DELETE")
def closure(request, pk):
    administrator(request)
    found = Closure.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    with transaction.atomic():
        if request.method == "DELETE":
            found.delete()
        else:
            _closure_of(body(request), found).save()
        workdays.changed(request.user)
        entries.wrote(
            Kind.SETTING_CHANGED,
            request=request,
            setting="closures",
            change="removed" if request.method == "DELETE" else "changed",
            name=found.name,
        )
    if request.method == "DELETE":
        return HttpResponse(status=204)
    return JsonResponse(_closure(found))


# A calendar of the organisation's days off for ten years holds a few hundred; more is a calendar
# of something else.
MOST_CLOSURES = 1000


@api("POST")
def closures_read(request):
    """The days an iCalendar file's events take, for the administrator to choose which the
    organisation closes; nothing is kept."""
    administrator(request)
    text = body(request).get("ics")
    if not isinstance(text, str):
        raise Refused(400, "invalid_ics")
    try:
        found = ical.closed(text, timezone.localdate())
    except ical.Malformed:
        raise Refused(400, "invalid_ics") from None
    if len(found) > MOST_CLOSURES:
        raise Refused(400, "too_many_closures")
    kept = set(Closure.objects.values_list("first", "last", "name"))
    return JsonResponse(
        {
            "closures": [
                {"first": first.isoformat(), "last": last.isoformat(), "name": name}
                for first, last, name in found
                if (first, last, name) not in kept
            ]
        }
    )


@api("GET")
@sharing.boxed()
def free(request):
    """Who of the people named and which of the resources is free between the instants: for
    the meeting being arranged, apart from the event it already is. Asked for offers, also the
    first times of the same length from that day on at which the user, they and the resources
    all are."""
    zone = zone_of(request.GET.get("zone") or request.headers.get("X-Zone"))
    since = _moment(request.GET.get("start"), zone, "start")
    until = _moment(request.GET.get("end"), zone, "end")
    if until <= since or until - since > timedelta(days=LONGEST):
        raise Refused(400, "invalid_end")
    apart = int(given) if (given := request.GET.get("except", "")).isdigit() else None
    emails = {
        each.strip().lower() for each in request.GET.get("people", "").split(",") if each.strip()
    }
    wanted = Resource.objects.filter(
        pk__in=[int(e) for e in request.GET.get("resources", "").split(",") if e.isdigit()]
    )
    found = {
        "people": availability.people(emails, since, until, apart) if emails else {},
        "away": availability.away(emails, since, until) if emails else {},
        "resources": {
            str(pk): state
            for pk, state in availability.resources(wanted, since, until, apart).items()
        },
    }
    if "offers" in request.GET:
        day = since.astimezone(timezone.get_default_timezone()).date()
        begun = datetime.combine(day, datetime.min.time(), timezone.get_default_timezone())
        found["offers"] = [
            {
                "start": recurrence.shown(start, False, zone),
                "end": recurrence.shown(end, False, zone),
            }
            for start, end in availability.offers(
                emails,
                [request.user.pk],
                wanted,
                until - since,
                max(begun, timezone.now()),
                apart,
            )
        ]
    return JsonResponse(found)
