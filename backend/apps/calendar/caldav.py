"""The user's calendars over CalDAV (RFC 4791, RFC 6578), which an iPhone reads by itself and
an Android phone through DAVx5: each of the user's own calendars written both ways, an
organisation's read only; changes found by revision. The calendars of the shared mailboxes the
user reaches stand in the same home, named with the mailbox, read only where the user's role
only reads."""

from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from django.db.models import Max
from django.http import HttpResponse, HttpResponseNotFound
from django.utils.http import http_date, parse_etags

from apps.access.models import RANK, Role
from apps.content import palette
from apps.dav.protocol import (
    Bad,
    Properties,
    answer,
    apple,
    asked,
    bare,
    cal,
    common,
    cs,
    d,
    dav,
    depth,
    element,
    href,
    member,
    multistatus,
    parsed,
    privileges,
    quoted,
    refused,
    unpatched,
    unsupported,
)
from apps.mail import sharing
from apps.mail.models import Account

from . import events, ical, recurrence
from .models import Calendar, Event, Gone

TOKEN = "urn:x-ponistra:sync:"
ICAL = "text/calendar; charset=utf-8; component=VEVENT"
LARGEST = 10 * 1024 * 1024
HREF = 255
WRITE = ("read", "write", "write-content", "bind", "unbind")
REPORTS = (cal("calendar-multiget"), cal("calendar-query"), d("sync-collection"))
FAR = datetime(1900, 1, 1, tzinfo=UTC), datetime(2200, 1, 1, tzinfo=UTC)


def home(user) -> str:
    return f"/dav/calendars/{user.pk}/"


def path(user, calendar: Calendar) -> str:
    return f"/dav/calendars/{user.pk}/{calendar.pk}/"


def reach(user) -> dict[int, Role]:
    """Whose calendars the user holds, each with the user's role in them: their own, and those of
    the shared mailboxes they reach."""
    return {**({} if user.visitor else sharing.roles(user)), user.pk: Role.OWN}


def calendars_of(reached: dict[int, Role]):
    return Calendar.objects.filter(owner__in=reached).select_related("owner").order_by("pk")


def writable(calendar: Calendar, reached: dict[int, Role]) -> bool:
    return not calendar.read_only and RANK[reached[calendar.owner_id]] >= RANK[Role.EDIT]


def named(user, calendar: Calendar, name: str) -> str:
    """The calendar's name as the phone lists it: a shared mailbox's with the mailbox's beside it,
    unless it already bears it."""
    box = calendar.owner.first_name
    return name if calendar.owner_id == user.pk or name == box else f"{name} ({box})"


def homes(user) -> Properties:
    """What the user's principal says of where their calendars are and whom they are: their own
    addresses, and those of the shared mailboxes they write from, as they organize the mailbox's
    meetings."""
    writing = [pk for pk, role in reach(user).items() if RANK[role] >= RANK[Role.EDIT]]
    accounts = Account.objects.order_by("pk").values_list("address", flat=True)
    addresses = [
        user.email,
        *accounts.filter(owner=user),
        *accounts.filter(owner__in=writing).exclude(owner=user),
    ]
    return {
        cal("calendar-home-set"): lambda: [href(home(user))],
        cal("calendar-user-address-set"): lambda: [
            href(f"mailto:{each}") for each in dict.fromkeys(addresses) if each
        ],
    }


def _revision(calendar: Calendar) -> int:
    return max(
        calendar.events.aggregate(last=Max("revision"))["last"] or 0,
        calendar.gone.aggregate(last=Max("revision"))["last"] or 0,
    )


def _etag(event: Event) -> str:
    return f'"{event.revision}"'


def _home(user) -> Properties:
    return {
        **common(user),
        d("resourcetype"): lambda: [element(d("collection"))],
        d("displayname"): lambda: "Ponistra",
        d("current-user-privilege-set"): lambda: privileges("read"),
    }


def _color(calendar: Calendar) -> str:
    colors = palette.calendars()
    return f"{colors[calendar.color % len(colors)]}FF".upper()


def _components() -> list[ET.Element]:
    made = element(cal("comp"))
    made.set("name", "VEVENT")
    return [made]


def _calendar(user, calendar: Calendar, revision: int, write: bool) -> Properties:
    return {
        **common(user),
        d("resourcetype"): lambda: [element(d("collection")), element(cal("calendar"))],
        d("displayname"): lambda: named(user, calendar, calendar.name),
        cal("calendar-description"): lambda: named(user, calendar, calendar.name),
        apple("calendar-color"): lambda: _color(calendar),
        cal("supported-calendar-component-set"): _components,
        d("sync-token"): lambda: f"{TOKEN}{revision}",
        cs("getctag"): lambda: f"{TOKEN}{revision}",
        d("current-user-privilege-set"): lambda: privileges(*(WRITE if write else ("read",))),
        d("supported-report-set"): lambda: [
            element(d("supported-report"), element(d("report"), element(name))) for name in REPORTS
        ],
        cal("max-resource-size"): lambda: str(LARGEST),
    }


def _resource(event: Event) -> Properties:
    return {
        d("getetag"): lambda: _etag(event),
        d("getcontenttype"): lambda: ICAL,
        d("resourcetype"): lambda: [],
        d("getlastmodified"): lambda: http_date(event.changed_at.timestamp()),
    }


def _with_data(event: Event) -> Properties:
    return {**_resource(event), cal("calendar-data"): lambda: events.written(event)}


def _masters(calendar: Calendar):
    return calendar.events.filter(master__isnull=True).order_by("pk")


class Held:
    """A calendar as the user signed in holds it, at the path it has in their home."""

    def __init__(self, user, calendar: Calendar, write: bool):
        self.user, self.calendar, self.write = user, calendar, write
        self.path = path(user, calendar)

    def properties(self) -> Properties:
        return _calendar(self.user, self.calendar, _revision(self.calendar), self.write)


def _found(user, pk: int, number: str) -> Held | None:
    if int(pk) != user.pk or not number.isdigit():
        return None
    reached = reach(user)
    found = calendars_of(reached).filter(pk=int(number)).first()
    return None if found is None else Held(user, found, writable(found, reached))


def _propfound(request, held: Held) -> HttpResponse:
    names = asked(parsed(request))
    found = [answer(held.path, held.properties(), names)]
    if depth(request):
        found += [
            answer(held.path + each.href, _resource(each), names)
            for each in _masters(held.calendar)
        ]
    return multistatus(found)


def _multiget(held: Held, root) -> HttpResponse:
    names = asked(root)
    wanted = [member(each.text or "", held.path) for each in root.iter(d("href"))]
    found = {
        each.href: each
        for each in _masters(held.calendar).filter(href__in=[w for w in wanted if w])
    }
    responses = []
    for given, name in zip(root.iter(d("href")), wanted, strict=True):
        if name in found:
            responses.append(answer(held.path + name, _with_data(found[name]), names))
        else:
            responses.append(bare(given.text or "", 404, "Not Found"))
    return multistatus(responses)


def _moment(raw: str | None, default: datetime) -> datetime:
    if not raw:
        return default
    try:
        return datetime.strptime(raw.strip(), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise Bad from None


def _window(root) -> tuple[datetime, datetime] | None:
    """The time range the query's VEVENT filter asks for; None where it asks for every event."""
    filters = root.find(cal("filter"))
    if filters is None:
        return None
    for comp in filters.iter(cal("comp-filter")):
        if comp.get("name", "").upper() == "VEVENT":
            if (span := comp.find(cal("time-range"))) is not None:
                return _moment(span.get("start"), FAR[0]), _moment(span.get("end"), FAR[1])
    return None


def _query(held: Held, root) -> HttpResponse:
    names = asked(root)
    window = _window(root)
    responses = []
    for each in _masters(held.calendar).prefetch_related("overrides"):
        if window is not None and not recurrence.occurrences(
            each, list(each.overrides.all()), *window
        ):
            continue
        responses.append(answer(held.path + each.href, _with_data(each), names))
    return multistatus(responses)


def _synced(held: Held, root) -> HttpResponse:
    calendar = held.calendar
    given = (root.findtext(d("sync-token")) or "").strip()
    since = 0
    if given:
        number = given.removeprefix(TOKEN)
        if not given.startswith(TOKEN) or not number.isdigit():
            return refused(403, element(d("valid-sync-token")))
        since = int(number)
    now = _revision(calendar)
    if since > now:
        return refused(403, element(d("valid-sync-token")))
    names = asked(root)
    changed = _masters(calendar).filter(revision__gt=since, revision__lte=now).order_by("revision")
    responses = [answer(held.path + each.href, _with_data(each), names) for each in changed]
    if since:
        live = _masters(calendar).values("href")
        gone = (
            Gone.objects.filter(calendar=calendar, revision__gt=since, revision__lte=now)
            .exclude(href__in=live)
            .values_list("href", flat=True)
            .distinct()
        )
        responses += [bare(held.path + each, 404, "Not Found") for each in gone]
    return multistatus(responses, element(d("sync-token"), text=f"{TOKEN}{now}"))


def _reported(request, held: Held) -> HttpResponse:
    root = parsed(request)
    if root is None:
        raise Bad
    if root.tag == cal("calendar-multiget"):
        return _multiget(held, root)
    if root.tag == cal("calendar-query"):
        return _query(held, root)
    if root.tag == d("sync-collection"):
        return _synced(held, root)
    return refused(403, element(d("supported-report")))


@dav
def calendars_home(request, user, pk):
    if int(pk) != user.pk:
        return HttpResponseNotFound()
    if request.method == "PROPPATCH":
        return unpatched(request, home(user))
    if request.method != "PROPFIND":
        return unsupported()
    names = asked(parsed(request))
    found = [answer(home(user), _home(user), names)]
    if depth(request):
        reached = reach(user)
        for each in calendars_of(reached):
            listed = Held(user, each, writable(each, reached))
            found.append(answer(listed.path, listed.properties(), names))
    return multistatus(found)


@dav
def calendar(request, user, pk, number):
    found = _found(user, pk, number)
    if found is None:
        return HttpResponseNotFound()
    match request.method:
        case "PROPFIND":
            return _propfound(request, found)
        case "REPORT":
            return _reported(request, found)
        case "PROPPATCH":
            return unpatched(request, found.path)
        case "DELETE" | "MKCALENDAR" | "MKCOL":
            return HttpResponse(status=403)
    return unsupported()


def _failed_precondition(request, found: Event | None) -> bool:
    if match := request.headers.get("If-Match"):
        tags = parse_etags(match)
        if found is None or ("*" not in tags and _etag(found) not in tags):
            return True
    if none := request.headers.get("If-None-Match"):
        tags = parse_etags(none)
        if found is not None and ("*" in tags or _etag(found) in tags):
            return True
    return False


def _put(request, held: Held, name: str, found: Event | None) -> HttpResponse:
    calendar = held.calendar
    given = request.read(LARGEST + 1)
    if len(given) > LARGEST:
        return refused(413, element(cal("max-resource-size")))
    text = given.decode("utf-8-sig", errors="replace")
    try:
        written = ical.parsed(text)
    except ical.Malformed:
        if "BEGIN:VEVENT" not in text and ("BEGIN:VTODO" in text or "BEGIN:VJOURNAL" in text):
            return refused(403, element(cal("supported-calendar-component")))
        return refused(415, element(cal("valid-calendar-data")))
    if found is not None:
        for each in written:
            each.uid = found.uid
        events.replaced(found, written)
        return HttpResponse(status=204)
    uid = written[0].uid
    if uid and (other := _masters(calendar).filter(uid=uid).first()):
        return refused(409, element(cal("no-uid-conflict"), href(quoted(held.path + other.href))))
    made = events.made(calendar, written[0], href=name)
    for each in written[1:]:
        events.made(calendar, each, master=made)
    return HttpResponse(status=201)


@dav
def resource(request, user, pk, number, name):
    held = _found(user, pk, number)
    if held is None or len(name) > HREF:
        return HttpResponseNotFound()
    found = _masters(held.calendar).filter(href=name).first()
    if request.method in ("PUT", "DELETE"):
        if not held.write:
            return HttpResponse(status=403)
        if _failed_precondition(request, found):
            return HttpResponse(status=412)
    match request.method:
        case "GET" | "HEAD":
            if found is None:
                return HttpResponseNotFound()
            return HttpResponse(
                events.written(found), content_type=ICAL, headers={"ETag": _etag(found)}
            )
        case "PROPFIND":
            if found is None:
                return HttpResponseNotFound()
            return multistatus([answer(held.path + name, _resource(found), asked(parsed(request)))])
        case "PUT":
            return _put(request, held, name, found)
        case "DELETE":
            if found is None:
                return HttpResponseNotFound()
            events.deleted(found)
            return HttpResponse(status=204)
    return unsupported()
