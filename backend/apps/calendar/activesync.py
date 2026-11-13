"""An ActiveSync account's calendars (D15, S4): each calendar folder of its hierarchy is an
organisation calendar here, read and refreshed by Sync as its mail is, never changed. A reply
to its invitation goes back through the server (S4-3)."""

import base64
import struct
from datetime import UTC, date, datetime, timedelta
from functools import cache
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction

from apps.mail.activesync.client import Session
from apps.mail.activesync.wbxml import Element
from apps.mail.activesync.wbxml import element as e
from apps.mail.imap import Failed
from apps.mail.models import Account

from . import events, notes, taking
from .ical import Found, web
from .models import Calendar, Feed
from .recurrence import as_day, day_instant, zone_of

# MS-ASCMD 2.2.3.186.3: the default calendar folder, and one the user made.
KINDS = {"8", "13"}
WINDOW = 100
OPTIONS = e(
    "AirSync:Options",
    # Traveler's own window is the weeks ahead; 0 is the whole calendar.
    e("AirSync:FilterType", "0"),
    e(
        "AirSyncBase:BodyPreference",
        e("AirSyncBase:Type", "1"),
        e("AirSyncBase:TruncationSize", "32768"),
    ),
)
# MS-ASCAL: DayOfWeek is a mask, Sunday first.
DAYS = [(1, "SU"), (2, "MO"), (4, "TU"), (8, "WE"), (16, "TH"), (32, "FR"), (64, "SA")]
ATTENDEE_STATUS = {"2": "tentative", "3": "accepted", "4": "declined"}
RESPONSES = {"1": "organizer", "2": "tentative", "3": "accepted", "4": "declined"}
CANCELLED = {"5", "7", "13", "15"}
USER_RESPONSES = {"accepted": "1", "tentative": "2", "declined": "3"}
# The zones a server's TIME_ZONE_INFORMATION is matched against, the installation's first.
ZONES = [
    "Europe/Zagreb",
    "Europe/London",
    "Europe/Dublin",
    "Europe/Lisbon",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Rome",
    "Europe/Vienna",
    "Europe/Prague",
    "Europe/Warsaw",
    "Europe/Budapest",
    "Europe/Belgrade",
    "Europe/Athens",
    "Europe/Helsinki",
    "Europe/Kyiv",
    "Europe/Bucharest",
    "Europe/Sofia",
    "Europe/Istanbul",
    "Europe/Moscow",
    "Atlantic/Azores",
    "Atlantic/Reykjavik",
    "Africa/Cairo",
    "Africa/Johannesburg",
    "Africa/Lagos",
    "Africa/Nairobi",
    "Asia/Dubai",
    "Asia/Tehran",
    "Asia/Karachi",
    "Asia/Kolkata",
    "Asia/Dhaka",
    "Asia/Bangkok",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Australia/Perth",
    "Australia/Adelaide",
    "Australia/Sydney",
    "Pacific/Auckland",
    "America/Sao_Paulo",
    "America/Argentina/Buenos_Aires",
    "America/Halifax",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Phoenix",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
]


def held(account: Account, changes: Element | None, whole: bool) -> None:
    """Keeps the account's calendars as its hierarchy says they are now: `whole` where it
    listed every folder, else what changed since."""
    listed = set()
    for change in changes or ():
        server_id = change.text("ServerId")
        if change.name in ("Add", "Update") and change.text("Type") in KINDS:
            listed.add(server_id)
            calendar, _ = Calendar.objects.update_or_create(
                account=account,
                server_id=server_id,
                defaults={
                    "owner_id": account.owner_id,
                    "kind": Calendar.Kind.ORGANISATION,
                    "name": change.text("DisplayName") or account.address,
                },
                create_defaults={
                    "owner_id": account.owner_id,
                    "kind": Calendar.Kind.ORGANISATION,
                    "name": change.text("DisplayName") or account.address,
                    "color": account.color % taking.colors(),
                },
            )
            Feed.objects.update_or_create(
                account=account,
                server_id=server_id,
                defaults={"name": calendar.name, "calendar": calendar},
            )
        elif change.name in ("Add", "Update", "Delete"):
            account.calendars.filter(server_id=server_id).delete()
            account.calendar_feeds.filter(server_id=server_id).delete()
    if whole:
        account.calendars.exclude(server_id__in=listed).delete()
        account.calendar_feeds.exclude(server_id__in=listed).delete()


def _shape(zone: ZoneInfo, year: int) -> tuple[int, int, int, int]:
    """The zone's standard and summer offsets in minutes and the months summer time starts and
    ends, 0 where it has none."""
    day, offsets = date(year, 1, 1), []
    while day.year == year:
        moment = datetime(day.year, day.month, day.day, 12, tzinfo=zone)
        offsets.append((day.month, int(moment.utcoffset().total_seconds() // 60)))
        day += timedelta(days=1)
    standard, summer = min(offset for _, offset in offsets), max(offset for _, offset in offsets)
    if standard == summer:
        return standard, summer, 0, 0
    starts = ends = 0
    for (_, before), (month, after) in zip(offsets, offsets[1:], strict=False):
        if after == summer and before != summer:
            starts = month
        elif after == standard and before != standard:
            ends = month
    return standard, summer, starts, ends


@cache
def zone_named(blob: str) -> str:
    """The IANA zone whose offsets and summer-time months are those of the server's
    TIME_ZONE_INFORMATION; "" (UTC) where none of the known ones are."""
    try:
        raw = base64.b64decode(blob)
        bias = struct.unpack_from("<i", raw, 0)[0]
        standard_date = struct.unpack_from("<8H", raw, 68)
        standard_bias = struct.unpack_from("<i", raw, 84)[0]
        daylight_date = struct.unpack_from("<8H", raw, 152)
        daylight_bias = struct.unpack_from("<i", raw, 168)[0]
    except struct.error, ValueError:
        return ""
    standard = -(bias + standard_bias)
    summer = -(bias + daylight_bias) if daylight_date[1] else standard
    wanted = (
        (standard, summer, daylight_date[1], standard_date[1])
        if daylight_date[1]
        else (standard, summer, 0, 0)
    )
    if wanted == (0, 0, 0, 0):
        return ""
    year = datetime.now(UTC).year
    for name in [settings.TIME_ZONE, *ZONES]:
        if _shape(ZoneInfo(name), year) == wanted:
            return name
    return ""


def _moment(raw: str) -> datetime | None:
    for shape in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw.strip(), shape).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _days(mask: str) -> list[str]:
    try:
        bits = int(mask)
    except ValueError:
        return []
    return [name for bit, name in DAYS if bits & bit]


def _position(week: str) -> str:
    """ActiveSync counts the week of the month 1 to 5, 5 meaning the last."""
    return "-1" if week == "5" else week or "1"


def rrule(recurrence: Element, zone: str) -> str:
    """The folder's Recurrence (MS-ASCAL 2.2.2.35) as an RRULE."""
    kind = recurrence.text("Type")
    interval = recurrence.text("Interval", "1") or "1"
    days = _days(recurrence.text("DayOfWeek", "0"))
    week = recurrence.text("WeekOfMonth")
    parts = []
    match kind:
        case "0":
            parts.append(f"FREQ=WEEKLY;BYDAY={','.join(days)}" if days else "FREQ=DAILY")
        case "1":
            parts.append("FREQ=WEEKLY")
            if days:
                parts.append(f"BYDAY={','.join(days)}")
        case "2":
            parts.append(f"FREQ=MONTHLY;BYMONTHDAY={recurrence.text('DayOfMonth', '1')}")
        case "3":
            parts.append(f"FREQ=MONTHLY;BYDAY={','.join(days)};BYSETPOS={_position(week)}")
        case "5":
            month, day = recurrence.text("MonthOfYear", "1"), recurrence.text("DayOfMonth", "1")
            parts.append(f"FREQ=YEARLY;BYMONTH={month};BYMONTHDAY={day}")
        case "6":
            month = recurrence.text("MonthOfYear", "1")
            parts.append(
                f"FREQ=YEARLY;BYMONTH={month};BYDAY={','.join(days)};BYSETPOS={_position(week)}"
            )
        case _:
            return ""
    if interval != "1":
        parts.append(f"INTERVAL={interval}")
    if count := recurrence.text("Occurrences"):
        parts.append(f"COUNT={count}")
    elif until := recurrence.text("Until"):
        if (moment := _moment(until)) is not None:
            parts.append(f"UNTIL={moment:%Y%m%dT%H%M%SZ}")
    if (first := recurrence.text("FirstDayOfWeek")) and first.isdigit() and 0 <= int(first) <= 6:
        parts.append(f"WKST={DAYS[int(first)][1]}")
    return ";".join(parts)


def _text(data: Element, name: str) -> str:
    return data.text(name, "").strip()


def _attendees(data: Element) -> list[dict]:
    found = []
    for each in data.findall("Attendees/Attendee"):
        email = each.text("Email").strip().lower()
        if not email:
            continue
        found.append(
            {
                "email": email,
                "name": each.text("Name").strip(),
                "status": ATTENDEE_STATUS.get(each.text("AttendeeStatus"), "needs-action"),
                "role": {"2": "optional", "3": "resource"}.get(
                    each.text("AttendeeType"), "required"
                ),
            }
        )
    return found


def _times(
    data: Element, all_day: bool, zone: str, start_name: str = "StartTime"
) -> tuple[datetime, datetime] | None:
    starts, ends = _moment(data.text(start_name)), _moment(data.text("EndTime"))
    if starts is None:
        return None
    if ends is None or ends < starts:
        ends = starts
    if all_day:
        # Exchange keeps an all-day event as the midnights of the user's zone, in UTC.
        first = as_day(starts.astimezone(zone_of(zone)))
        last = as_day(ends.astimezone(zone_of(zone)))
        if last <= first:
            last = first + timedelta(days=1)
        return day_instant(first), day_instant(last)
    return starts, ends


def found(data: Element) -> tuple[Found, list[Found], list[str]]:
    """The event as PONISTRA reads it, the occurrences changed on their own, and the ones
    deleted from the series."""
    zone = zone_named(_text(data, "TimeZone")) if _text(data, "TimeZone") else ""
    all_day = _text(data, "AllDayEvent") == "1"
    master = Found(uid=_text(data, "UID"), all_day=all_day, zone=zone)
    times = _times(data, all_day, zone)
    if times is None:
        raise ValueError("no start")
    master.starts, master.ends = times
    _fill(master, data)
    if (recurrence := data.find("Recurrence")) is not None:
        master.rrule = rrule(recurrence, zone)
    overrides, exdates = [], []
    for exception in data.findall("Exceptions/Exception"):
        original = _moment(exception.text("ExceptionStartTime"))
        if original is None:
            continue
        if all_day:
            original = day_instant(as_day(original.astimezone(zone_of(zone))))
        if exception.text("Deleted") == "1":
            exdates.append(original.date().isoformat() if all_day else original.isoformat())
            continue
        changed = Found(uid=master.uid, recurrence_id=original, all_day=all_day, zone=zone)
        for name in (
            "summary",
            "location",
            "conference",
            "description",
            "busy",
            "private",
            "status",
            "attendees",
            "reminders",
            "organizer",
            "response",
        ):
            setattr(changed, name, getattr(master, name))
        changed.starts, changed.ends = _times(exception, all_day, zone) or (
            original,
            original + (master.ends - master.starts),
        )
        _fill(changed, exception, master)
        overrides.append(changed)
    return master, overrides, exdates


def _fill(found: Found, data: Element, master: Found | None = None) -> None:
    """The event's details from the element: for an exception, those it gives, the master's
    standing for the rest."""
    given = {child.name for child in data}
    if "Subject" in given:
        found.summary = _text(data, "Subject")
    if "Location" in given:
        location = data.find("Location")
        found.location = (
            location.text("DisplayName")
            if location is not None and location.children
            else _text(data, "Location")
        ).strip()
    if "OnlineMeetingExternalLink" in given:
        found.conference = web(_text(data, "OnlineMeetingExternalLink"))
    if "Body" in given:
        found.description = data.text("Body/Data").strip()
    if "BusyStatus" in given:
        found.busy = _text(data, "BusyStatus") not in ("0", "4")
    if "Sensitivity" in given:
        found.private = _text(data, "Sensitivity") in ("2", "3")
    if "MeetingStatus" in given:
        found.status = "cancelled" if _text(data, "MeetingStatus") in CANCELLED else "confirmed"
    if "OrganizerEmail" in given and (email := _text(data, "OrganizerEmail").lower()):
        found.organizer = {"email": email, "name": _text(data, "OrganizerName")}
    if "Attendees" in given:
        found.attendees = _attendees(data)
    if "ResponseType" in given:
        found.response = RESPONSES.get(
            _text(data, "ResponseType"),
            "needs-action" if _text(data, "ResponseType") == "5" else "",
        )
    if "Reminder" in given:
        found.reminders = (
            [int(_text(data, "Reminder"))] if _text(data, "Reminder").isdigit() else []
        )
    if "Categories" in given:
        names = [
            each.string.strip()
            for each in data.findall("Categories/Category")
            if each.string.strip()
        ]
        if names:
            found.extra = [f"CATEGORIES:{','.join(name.replace(',', '\\,') for name in names)}"]


def href_of(server_id: str) -> str:
    return f"{quote(server_id, safe='')}.ics"


def server_id_of(href: str) -> str:
    return unquote(href.removesuffix(".ics"))


def _sync(feed: Feed, key: str, *more: Element) -> Element:
    return e(
        "AirSync:Sync",
        e(
            "AirSync:Collections",
            e(
                "AirSync:Collection",
                e("AirSync:SyncKey", key),
                e("AirSync:CollectionId", feed.server_id),
                *more,
            ),
        ),
    )


def _answered_as(found: list[Found], ours: set[str]) -> None:
    """The user among the attendees as they answered: Notes keeps an attendee's answer with the
    chair only, so Traveler lists the user as never answering whatever they did."""
    for each in found:
        if each.response in ("accepted", "tentative", "declined", "needs-action"):
            each.attendees = [
                dict(attendee, status=each.response) if attendee["email"] in ours else attendee
                for attendee in each.attendees
            ]


@transaction.atomic
def _applied(calendar: Calendar, commands: list[Element]) -> None:
    ours = {
        each.lower()
        for each in Account.objects.filter(owner_id=calendar.owner_id).values_list(
            "address", flat=True
        )
    }
    for command in commands:
        server_id = command.text("ServerId")
        if not server_id:
            continue
        href = href_of(server_id)
        existing = calendar.events.filter(href=href, master__isnull=True).first()
        if command.name == "Delete":
            if existing is not None:
                events.deleted(existing)
            continue
        data = command.find("ApplicationData")
        if data is None:
            continue
        try:
            master, overrides, exdates = found(data)
        except ValueError:
            continue
        master.exdates = exdates
        _answered_as([master, *overrides], ours)
        if not master.uid:
            master.uid = server_id
        if existing is None:
            existing = calendar.events.filter(uid=master.uid, master__isnull=True).first()
            if existing is not None and notes.standing(existing):
                notes.answered(existing, href)
            elif existing is not None and existing.href != href:
                # The folder lists the same event twice (an invitation taken again): one stays.
                continue
        if existing is None:
            made = events.made(calendar, master, href=href)
            for each in overrides:
                events.made(calendar, each, master=made)
        else:
            events.replaced(existing, [master, *overrides])


def caught_up(client: Session, feed: Feed) -> None:
    """Takes what the server has new, changed and gone in the folder."""
    calendar = feed.calendar
    if calendar is None:
        return
    while True:
        more = ()
        if feed.key:
            window = e("AirSync:WindowSize", str(WINDOW))
            more = (e("AirSync:GetChanges", "1"), window, OPTIONS)
        answer = client.command("Sync", _sync(feed, feed.key or "0", *more))
        collection = answer.find("Collections/Collection")
        if collection is None:
            return
        status = collection.text("Status")
        if status == "3":
            # The server no longer knows the key: the folder comes again from nothing, each event
            # replacing the one it is.
            Feed.objects.filter(pk=feed.pk).update(key="")
            feed.key = ""
            continue
        if status != "1":
            raise Failed("activesync_unreachable")
        commands = collection.find("Commands")
        if commands is not None:
            _applied(calendar, list(commands))
        feed.key = collection.text("SyncKey")
        Feed.objects.filter(pk=feed.pk).update(key=feed.key, error="")
        if more and collection.find("MoreAvailable") is None:
            return


def responded(
    client: Session, collection: str, request: str, response: str, occurrence: datetime | None
) -> None:
    """Answers the meeting on the organisation's server, which tells its organizer: the item of
    the folder that holds it, the calendar's meeting or the inbox's request; one occurrence of
    a series where the event is one."""
    asked = [
        e("MeetingResponse:UserResponse", USER_RESPONSES[response]),
        e("MeetingResponse:CollectionId", collection),
        e("MeetingResponse:RequestId", request),
    ]
    if occurrence is not None:
        instance = occurrence.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        asked.append(e("MeetingResponse:InstanceId", instance))
    answer = client.command(
        "MeetingResponse",
        e("MeetingResponse:MeetingResponse", e("MeetingResponse:Request", *asked)),
    )
    if answer.text("Result/Status") != "1":
        raise Failed("activesync_refused")


@transaction.atomic
def wiped(account: Account) -> None:
    """The organisation's calendars go when its administrator wipes the device."""
    account.calendars.all().delete()
    account.calendar_feeds.all().delete()
