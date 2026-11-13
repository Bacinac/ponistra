"""A Microsoft account's calendars through Graph (D15, S4), consented to at the account's
sign-in: each calendar's delta followed from where it was left, its new events only, into one
of the user's own calendars."""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from apps.mail import signin
from apps.mail.imap import Failed
from apps.mail.models import Account

from . import ical, recurrence, taking
from .models import Event, Feed, Taken

GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = 20
PAGE = 100
# How far ahead a series' cancelled occurrences are looked for.
AHEAD = timedelta(days=3 * 365)
DAYS = {
    "sunday": "SU",
    "monday": "MO",
    "tuesday": "TU",
    "wednesday": "WE",
    "thursday": "TH",
    "friday": "FR",
    "saturday": "SA",
}
INDEXES = {"first": "1", "second": "2", "third": "3", "fourth": "4", "last": "-1"}
RESPONSES = {
    "accepted": "accepted",
    "tentativelyAccepted": "tentative",
    "declined": "declined",
    "organizer": "organizer",
    "notResponded": "needs-action",
}


class Gone(Exception):
    """Graph no longer knows the delta link."""


def _get(token: str, url: str) -> dict | None:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": f"odata.maxpagesize={PAGE}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as refused:
        if refused.code == 404:
            return None
        if refused.code == 410:
            raise Gone from None
        if refused.code in (401, 403):
            raise Failed("calendar_refused") from None
        raise Failed("calendar_unreachable") from None
    except OSError, ValueError:
        raise Failed("calendar_unreachable") from None


def feeds(account: Account, token: str) -> list[Feed]:
    """The account's calendars as Graph lists them now, those it lets the user write: its
    birthdays and holidays are its own derivations, which PONISTRA draws itself."""
    page = _get(token, f"{GRAPH}/me/calendars") or {}
    listed = [
        (each["id"], each.get("name") or account.address)
        for each in page.get("value", [])
        if each.get("id") and each.get("canEdit", True)
    ]
    for server_id, name in listed:
        feed, _ = Feed.objects.get_or_create(
            account=account, server_id=server_id, defaults={"name": name}
        )
        if feed.calendar is None and feed.followed:
            feed.calendar = taking.own(account.owner_id, name)
            feed.save(update_fields=["calendar"])
    account.calendar_feeds.exclude(server_id__in=[each for each, _ in listed]).delete()
    return list(
        account.calendar_feeds.filter(followed=True, calendar__isnull=False)
        .select_related("calendar")
        .order_by("server_id")
    )


def _moment(given: dict | None) -> datetime | None:
    if not given or not given.get("dateTime"):
        return None
    text = given["dateTime"][:26].rstrip("Z")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    zone = ical.zone_named(given.get("timeZone", "UTC")) or "UTC"
    return moment.replace(tzinfo=recurrence.zone_of(zone)).astimezone(UTC)


def rrule(given: dict, zone: str) -> str:
    """Graph's recurrence as an RRULE."""
    pattern, span = given.get("pattern") or {}, given.get("range") or {}
    days = [DAYS[each] for each in pattern.get("daysOfWeek") or [] if each in DAYS]
    index = INDEXES.get(pattern.get("index", "first"), "1")
    parts = []
    match pattern.get("type"):
        case "daily":
            parts.append("FREQ=DAILY")
        case "weekly":
            parts.append("FREQ=WEEKLY")
            if days:
                parts.append(f"BYDAY={','.join(days)}")
        case "absoluteMonthly":
            parts.append(f"FREQ=MONTHLY;BYMONTHDAY={pattern.get('dayOfMonth', 1)}")
        case "relativeMonthly":
            parts.append(f"FREQ=MONTHLY;BYDAY={','.join(days)};BYSETPOS={index}")
        case "absoluteYearly":
            month, day = pattern.get("month", 1), pattern.get("dayOfMonth", 1)
            parts.append(f"FREQ=YEARLY;BYMONTH={month};BYMONTHDAY={day}")
        case "relativeYearly":
            month = pattern.get("month", 1)
            parts.append(f"FREQ=YEARLY;BYMONTH={month};BYDAY={','.join(days)};BYSETPOS={index}")
        case _:
            return ""
    if (interval := pattern.get("interval") or 1) != 1:
        parts.append(f"INTERVAL={interval}")
    if span.get("type") == "numbered" and span.get("numberOfOccurrences"):
        parts.append(f"COUNT={span['numberOfOccurrences']}")
    elif span.get("type") == "endDate" and span.get("endDate"):
        parts.append(f"UNTIL={span['endDate'].replace('-', '')}")
    if first := DAYS.get(pattern.get("firstDayOfWeek", "")):
        parts.append(f"WKST={first}")
    return ";".join(parts)


def found(given: dict) -> ical.Found:
    made = ical.Found(uid=(given.get("iCalUId") or given.get("id") or "").strip())
    made.all_day = bool(given.get("isAllDay"))
    made.zone = ical.zone_named(given.get("originalStartTimeZone") or "")
    starts, ends = _moment(given.get("start")), _moment(given.get("end"))
    if starts is None:
        raise ValueError("no start")
    if made.all_day:
        first = recurrence.as_day(starts)
        last = recurrence.as_day(ends) if ends else first + timedelta(days=1)
        if last <= first:
            last = first + timedelta(days=1)
        made.starts, made.ends = recurrence.day_instant(first), recurrence.day_instant(last)
    else:
        made.starts, made.ends = starts, max(ends or starts, starts)
    made.summary = (given.get("subject") or "").strip()
    made.location = ((given.get("location") or {}).get("displayName") or "").strip()
    made.conference = ical.web((given.get("onlineMeeting") or {}).get("joinUrl"))
    body = given.get("body") or {}
    if body.get("contentType") == "text":
        made.description = (body.get("content") or "").strip()
    else:
        made.description = (given.get("bodyPreview") or "").strip()
    made.status = "cancelled" if given.get("isCancelled") else "confirmed"
    made.busy = given.get("showAs", "busy") not in ("free", "workingElsewhere")
    made.private = given.get("sensitivity") in ("private", "confidential")
    organizer = (given.get("organizer") or {}).get("emailAddress") or {}
    if organizer.get("address"):
        made.organizer = {
            "email": organizer["address"].strip().lower(),
            "name": (organizer.get("name") or "").strip(),
        }
    for each in given.get("attendees") or []:
        address = (each.get("emailAddress") or {}).get("address") or ""
        if "@" not in address:
            continue
        made.attendees.append(
            {
                "email": address.strip().lower(),
                "name": (each["emailAddress"].get("name") or "").strip(),
                "status": RESPONSES.get(
                    (each.get("status") or {}).get("response", ""), "needs-action"
                ),
                "role": {"optional": "optional", "resource": "resource"}.get(
                    each.get("type", ""), "required"
                ),
            }
        )
    made.response = RESPONSES.get((given.get("responseStatus") or {}).get("response", ""), "")
    if given.get("isReminderOn") and isinstance(given.get("reminderMinutesBeforeStart"), int):
        made.reminders = [given["reminderMinutesBeforeStart"]]
    if given.get("type") == "seriesMaster" and given.get("recurrence"):
        made.rrule = rrule(given["recurrence"], made.zone)
    if names := [each for each in given.get("categories") or [] if each]:
        made.extra = [f"CATEGORIES:{','.join(name.replace(',', '\\,') for name in names)}"]
    return made


def _series(token: str, given: dict, master: ical.Found) -> list[ical.Found]:
    """The master with its occurrences changed on their own, and the cancelled ones taken out
    of its rule."""
    quoted = urllib.parse.quote(given["id"], safe="")
    overrides = []
    page = _get(token, f"{GRAPH}/me/events/{quoted}/exceptionOccurrences") or {}
    for each in page.get("value", []):
        original = _moment({"dateTime": each.get("originalStart", ""), "timeZone": "UTC"})
        if original is None:
            continue
        try:
            changed = found(each)
        except ValueError:
            continue
        changed.uid, changed.rrule = master.uid, ""
        changed.recurrence_id = (
            recurrence.day_instant(recurrence.as_day(original)) if master.all_day else original
        )
        overrides.append(changed)
    first, last = master.starts, min(master.starts + AHEAD, datetime.now(UTC) + AHEAD)
    window = f"startDateTime={first:%Y-%m-%dT%H:%M:%SZ}&endDateTime={last:%Y-%m-%dT%H:%M:%SZ}"
    url = f"{GRAPH}/me/events/{quoted}/instances?{window}&$select=originalStart,type"
    kept = set()
    while url:
        page = _get(token, url)
        if page is None:
            kept = None
            break
        for each in page.get("value", []):
            if moment := _moment({"dateTime": each.get("originalStart", ""), "timeZone": "UTC"}):
                kept.add(
                    recurrence.day_instant(recurrence.as_day(moment)) if master.all_day else moment
                )
        url = page.get("@odata.nextLink", "")
    if kept is not None:
        transient = Event(**master.fields)
        expected = recurrence.occurrences(transient, [], first, last)
        master.exdates = [
            each.start.date().isoformat() if master.all_day else each.start.isoformat()
            for each in expected
            if each.recurrence_id not in kept
            and each.recurrence_id not in {over.recurrence_id for over in overrides}
        ]
    return [master, *overrides]


def _start(feed: Feed) -> str:
    return f"{GRAPH}/me/calendars/{urllib.parse.quote(feed.server_id, safe='')}/events/delta"


def caught_up(account: Account, token: str, feed: Feed) -> int:
    """Takes the events new in the calendar since its delta link; how many were taken."""
    count, url = 0, feed.key or _start(feed)
    while True:
        try:
            page = _get(token, url)
        except Gone:
            if url == _start(feed):
                raise Failed("calendar_unreachable") from None
            url = _start(feed)
            continue
        if page is None:
            raise Failed("calendar_unreachable")
        for given in page.get("value", []):
            if "@removed" in given or not given.get("id"):
                continue
            if given.get("type") in ("occurrence", "exception"):
                continue
            item = given["id"]
            if Taken.objects.filter(
                owner_id=account.owner_id,
                kind=Taken.Kind.MICROSOFT,
                source=account.address,
                item=item[:500],
            ).exists():
                continue
            try:
                master = found(given)
            except ValueError:
                continue
            series = _series(token, given, master) if master.rrule else [master]
            kept = {key: value for key, value in given.items() if not key.startswith("@")}
            if taking.taken(
                account,
                Taken.Kind.MICROSOFT,
                account.address,
                item,
                feed.calendar,
                series,
                kept,
                feed=feed,
            ):
                count += 1
        if next_page := page.get("@odata.nextLink"):
            url = next_page
            continue
        feed.key = page.get("@odata.deltaLink", "")
        Feed.objects.filter(pk=feed.pk).update(key=feed.key, error="")
        return count


def taken(account: Account) -> int:
    """Takes the account's new events from each of its calendars; how many were taken."""
    token = signin.graph(account)
    return sum(caught_up(account, token, feed) for feed in feeds(account, token))
