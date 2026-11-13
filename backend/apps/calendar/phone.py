"""The user's calendars as the phone's own Calendar app holds them (D26): each series as CalDAV
gives it, in JSON, read by the revision the phone read last and written back at the revision of
the series it read. An organisation's calendar is read only, as over CalDAV. What the phone
changes of a meeting the user organizes reaches its attendees as the web app's change does, and
the user's answer to one they are asked to reaches whoever asked. The calendars of the shared
mailboxes the user reaches come beside their own, named with the mailbox, written as the mailbox
where the user's role writes and read only where it only reads."""

import copy
from datetime import UTC, date, datetime, timedelta

from django.db import transaction
from django.db.models import Max, Prefetch
from django.http import HttpResponse, JsonResponse

from apps.content import palette
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database

from . import events, ical, invitations, recurrence
from .caldav import calendars_of, named, reach, writable
from .models import Calendar, Event, Gone
from .views import LONGEST, NAME, NOTE, TEXT, describe_calendar, reminders_of, rule_of

HREF = 255
# A series with more occurrences changed on their own than this is no phone's.
MOST_PARTS = 1000
DAYS_OFF = (*Event.DayOff.values, ical.MOVED)


def _phone(request) -> None:
    if request.device is None:
        raise Refused(403, "app_password_required")


def _millis(moment: datetime) -> int:
    return round(moment.timestamp() * 1000)


def _instant(given) -> datetime:
    if not isinstance(given, int) or isinstance(given, bool):
        raise Refused(400, "invalid_event")
    try:
        return datetime.fromtimestamp(given / 1000, UTC)
    except OverflowError, OSError, ValueError:
        raise Refused(400, "invalid_event") from None


def _dated_millis(given: str) -> int:
    """An RDATE or EXDATE as `ical` keeps it, as the instant the phone holds: an all-day one at
    its midnight UTC, as Android holds an all-day event."""
    if len(given) == 10:
        return _millis(recurrence.day_instant(date.fromisoformat(given)))
    return _millis(datetime.fromisoformat(given))


def _dated_text(given, all_day: bool) -> str:
    moment = _instant(given)
    return moment.date().isoformat() if all_day else moment.isoformat()


def _owner(calendar: Calendar) -> str:
    """The address the user has in the calendar, by which the phone knows which attendee they are
    and whether they organize a meeting."""
    return calendar.account.address if calendar.account_id else calendar.owner.email


def _latest(calendar: Calendar) -> int:
    return max(
        calendar.events.aggregate(last=Max("revision"))["last"] or 0,
        calendar.gone.aggregate(last=Max("revision"))["last"] or 0,
    )


def _calendar(user, pk) -> tuple[Calendar, bool]:
    """The calendar the user holds on the phone, and whether they write it."""
    reached = reach(user)
    found = calendars_of(reached).select_related("account").filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    return found, writable(found, reached)


def _written(user, pk) -> Calendar:
    calendar, write = _calendar(user, pk)
    if not write:
        raise Refused(403, "read_only")
    return calendar


def _part(found: ical.Found, response: str) -> dict:
    return {
        "recurrence_id": _millis(found.recurrence_id) if found.recurrence_id else None,
        "summary": found.summary,
        "location": found.location,
        "description": found.description,
        "all_day": found.all_day,
        "starts": _millis(found.starts),
        "ends": _millis(found.ends),
        "zone": found.zone,
        "rrule": found.rrule,
        "rdates": [_dated_millis(each) for each in found.rdates],
        "exdates": [_dated_millis(each) for each in found.exdates],
        "status": found.status,
        "busy": found.busy,
        "private": found.private,
        "organizer": found.organizer,
        "attendees": found.attendees,
        "reminders": found.reminders,
        "response": response,
        "day_off": found.day_off,
    }


def _series(master: Event) -> dict:
    """The series as the phone holds it: its master, the occurrences changed on their own, and
    each occurrence its way with days off moves, as CalDAV writes them out."""
    overrides = sorted(master.overrides.all(), key=lambda each: (each.recurrence_id, each.pk))
    responses = {each.recurrence_id: each.response for each in overrides}
    return {
        "href": master.href,
        "revision": master.revision,
        "parts": [
            _part(each, responses.get(each.recurrence_id, master.response))
            for each in ical.told(master, overrides)
        ],
    }


def _masters(calendar: Calendar):
    return calendar.events.filter(master__isnull=True).prefetch_related(
        Prefetch("overrides", queryset=Event.objects.select_related("calendar"))
    )


def _listed(user, calendar: Calendar, write: bool, colors: list[str]) -> dict:
    described = describe_calendar(calendar)
    return {
        "id": calendar.pk,
        "name": named(user, calendar, described["name"]),
        "read_only": not write,
        "color": colors[calendar.color % len(colors)],
        "owner": _owner(calendar),
        "revision": _latest(calendar),
    }


@api("GET", device=True)
def phone_calendars(request):
    """The user's calendars as the phone lists them, each with the revision it has reached, so
    the phone reads only those that changed."""
    _phone(request)
    reached = reach(request.user)
    colors = palette.calendars()
    listed = [
        _listed(request.user, each, writable(each, reached), colors)
        for each in calendars_of(reached).select_related("account")
    ]
    return JsonResponse({"calendars": listed})


@api("GET", device=True)
def phone_calendar(request, pk):
    """A calendar's series as the phone holds them: every one, or those changed since the
    revision the phone read last and the hrefs of those deleted since, and the revision it now
    holds. A revision the calendar never reached, as after a restore, is refused (410), and the
    phone reads the whole calendar again."""
    _phone(request)
    calendar, _ = _calendar(request.user, pk)
    since = request.GET.get("since", "0")
    if not since.isdigit():
        raise Refused(400, "invalid_since")
    since, now = int(since), _latest(calendar)
    if since > now:
        raise Refused(410, "since_unknown")
    changed = _masters(calendar).filter(revision__gt=since, revision__lte=now)
    gone = []
    if since:
        gone = list(
            Gone.objects.filter(calendar=calendar, revision__gt=since, revision__lte=now)
            .exclude(href__in=calendar.events.filter(master__isnull=True).values("href"))
            .values_list("href", flat=True)
            .distinct()
        )
    return JsonResponse(
        {
            "revision": now,
            "events": [_series(each) for each in changed.order_by("revision")],
            "gone": gone,
        }
    )


def _text(raw: dict, name: str, most: int) -> str:
    given = raw.get(name) or ""
    if not isinstance(given, str):
        raise Refused(400, "invalid_event")
    return given.strip()[:most]


def _zone(raw) -> str:
    named = ical.zone_named(raw if isinstance(raw, str) else "")
    return "" if named in ("", "UTC", "Etc/UTC", "GMT", "Etc/GMT") else named


def _found_of(raw) -> tuple[ical.Found, list | None]:
    """A part of a series as the phone wrote it, and the attendees it lists, checked when the
    user arranges the meeting."""
    if not isinstance(raw, dict):
        raise Refused(400, "invalid_event")
    found = ical.Found()
    given = raw.get("recurrence_id")
    found.recurrence_id = None if given is None else _instant(given)
    found.all_day = raw.get("all_day") is True
    found.starts, found.ends = _instant(raw.get("starts")), _instant(raw.get("ends"))
    if found.all_day:
        first = found.starts.date()
        found.starts = recurrence.day_instant(first)
        found.ends = recurrence.day_instant(max(found.ends.date(), first + timedelta(days=1)))
    else:
        found.zone = _zone(raw.get("zone"))
    if found.ends < found.starts or found.ends - found.starts > timedelta(days=LONGEST):
        raise Refused(400, "invalid_end")
    found.summary = _text(raw, "summary", NAME)
    found.location = _text(raw, "location", TEXT)
    found.description = _text(raw, "description", NOTE)
    found.rrule = rule_of(raw.get("rrule"))
    for name in ("rdates", "exdates"):
        listed = raw.get(name) or []
        if not isinstance(listed, list):
            raise Refused(400, "invalid_event")
        setattr(found, name, [_dated_text(each, found.all_day) for each in listed])
    found.status = raw.get("status") if raw.get("status") in Event.Status.values else "confirmed"
    found.busy = raw.get("busy") is not False
    found.private = raw.get("private") is True
    found.reminders = reminders_of(raw.get("reminders"))
    found.response = raw.get("response") if isinstance(raw.get("response"), str) else ""
    found.day_off = raw.get("day_off") if raw.get("day_off") in DAYS_OFF else ""
    attendees = raw.get("attendees")
    return found, attendees if isinstance(attendees, list) else None


def _arranged_here(master: Event | None) -> bool:
    """Whether the user arranges the series: a new one, a meeting they organize or a plain
    event; else they are asked to it, and who comes stays as the organizer set it."""
    return (
        master is None
        or master.response == invitations.ORGANIZER
        or not (master.response or master.attendees)
    )


def _given(user, pk, href: str, data: dict) -> tuple[Calendar, Event | None, list, list]:
    """The calendar, the series the phone writes over (None for a new one) and what it wrote,
    refused when the series changed since the revision the phone read."""
    calendar = _written(user, pk)
    if not href or len(href) > HREF:
        raise Refused(400, "invalid_href")
    found = calendar.events.filter(master__isnull=True, href=href).first()
    revision = data.get("revision")
    if revision is not None and (not isinstance(revision, int) or isinstance(revision, bool)):
        raise Refused(400, "invalid_revision")
    if found is None and revision is not None:
        raise Refused(404, "not_found")
    if found is not None and found.revision != revision:
        raise Refused(412, "changed")
    parts = data.get("parts")
    if not isinstance(parts, list) or not parts or len(parts) > MOST_PARTS:
        raise Refused(400, "invalid_event")
    read = [_found_of(each) for each in parts]
    try:
        kept = ical.settled([each for each, _ in read])
    except ical.Malformed:
        raise Refused(400, "invalid_event") from None
    listed = {id(each): attendees for each, attendees in read}
    return calendar, found, kept, [listed[id(each)] for each in kept]


def _stored(master: Event | None, at: datetime | None) -> Event | None:
    if master is None or at is None:
        return master
    return master.overrides.select_related("calendar").filter(recurrence_id=at).first()


def _answers(master: Event | None, given: list[ical.Found]) -> list[tuple[Event, str]]:
    """The user's answers the phone changed on the parts PONISTRA keeps, of a meeting they are
    asked to."""
    if _arranged_here(master):
        return []
    found = []
    for each in given:
        stored = _stored(master, each.recurrence_id)
        if stored is not None and each.response in invitations.RESPONSES:
            if each.response != stored.response:
                found.append((stored, each.response))
    return found


def _occurrence(master: Event, at: datetime) -> Event:
    """The occurrence at the instant as it stood, where attendees know it to be."""
    stood = _stored(master, at) or events.stand_in(master, recurrence.placed(master, at))
    stood.uid, stood.recurrence_id, stood.master = master.uid, at, master
    return stood


def _saved(
    user, calendar: Calendar, href: str, found: Event | None, given: list, attendees: list
) -> tuple[Event, list[invitations.Notice], list[tuple[Event, str]]]:
    """The series written as the phone gave it, with what only PONISTRA holds kept; the notices
    its attendees are owed, and the user's answers to tell on occurrences the phone changed on
    its own."""
    if found is not None:
        found = Event.objects.select_related("calendar").get(pk=found.pk)
    here = _arranged_here(found)
    asked = {each.recurrence_id: each.response for each in given}
    before = copy.copy(found)
    priors = {}
    if found is not None and here:
        priors = {each.recurrence_id: _occurrence(found, each.recurrence_id) for each in given[1:]}
    for each, listed in zip(given, attendees, strict=True):
        base = _stored(found, each.recurrence_id) or found
        if base is None:
            each.organizer, each.response = {}, ""
        else:
            each.uid = found.uid
            each.conference, each.extra, each.sequence = base.conference, base.extra, base.sequence
            each.organizer, each.response = base.organizer, base.response
            if not here:
                each.attendees = base.attendees
                continue
        invitations.arranged(user, each, base, invitations.given({"attendees": listed or []}))
    with transaction.atomic():
        if found is None:
            master = events.made(calendar, given[0], href=href)
            for each in given[1:]:
                events.made(calendar, each, master=master)
        else:
            master = events.replaced(found, given)
    master = Event.objects.select_related("calendar").get(pk=master.pk)
    overrides = list(master.overrides.select_related("calendar").order_by("recurrence_id", "pk"))
    if not here:
        later = [
            (each, asked[each.recurrence_id])
            for each in overrides
            if asked.get(each.recurrence_id) in invitations.RESPONSES
            and asked[each.recurrence_id] != each.response
        ]
        return master, [], later
    notices = invitations.changes(user, before, master, [master, *overrides])
    for each in overrides:
        if (prior := priors.get(each.recurrence_id)) is not None:
            notices += invitations.changes(user, prior, each, [each])
    return master, notices, []


def _language(given) -> str:
    return given if given in invitations.WORDED else "en"


def _removed(user, pk, href: str, revision: str) -> list[invitations.Notice]:
    calendar = _written(user, pk)
    found = calendar.events.filter(master__isnull=True, href=href).first()
    if found is None:
        raise Refused(404, "not_found")
    if revision != str(found.revision):
        raise Refused(412, "changed")
    notices = invitations.withdrawn(calendar.owner, found)
    events.deleted(found)
    return notices


@api("PUT", "DELETE", device=True)
async def phone_event(request, pk, href):
    """A series the phone wrote, under the href the phone chose for a new one: written over only
    at the revision the phone read, and refused (412) when it changed since, as PONISTRA holds
    the truth and the phone reads the calendar again. The user's answers the phone changed are
    told first, so a server that does not take one leaves the series as it was. In a shared
    mailbox's calendar the mailbox organizes and answers."""
    _phone(request)
    if request.method == "DELETE":
        notices = await database(_removed)(request.user, pk, href, request.GET.get("revision", ""))
        await invitations.told(_language(request.GET.get("language")), notices)
        return HttpResponse(status=204)
    data = body(request)
    language = _language(data.get("language"))
    calendar, found, given, attendees = await database(_given)(request.user, pk, href, data)
    owner = calendar.owner
    for event, response in await database(_answers)(found, given):
        await invitations.answered(owner, event, response, language)
    master, notices, later = await database(_saved)(owner, calendar, href, found, given, attendees)
    for event, response in later:
        await invitations.answered(owner, event, response, language)
    await invitations.told(language, notices)
    served = await database(lambda: _series(_masters(calendar).get(pk=master.pk)))()
    return JsonResponse(served, status=201 if found is None else 200)
