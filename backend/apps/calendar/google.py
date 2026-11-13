"""A Google account's calendars through Google's CalDAV (D15, S4), signed in as its mail is.
With an app password only the older address answers; the newer one wants a sign-in through
Google. Each calendar is taken once into one of the user's own, its new events only."""

import urllib.parse
from logging import getLogger
from xml.etree import ElementTree as ET

from apps.dav import client
from apps.dav.protocol import cal as c
from apps.dav.protocol import d, element
from apps.mail.imap import Failed
from apps.mail.models import Account

from . import ical, taking
from .models import Feed, Taken

ROOT = "https://www.google.com"
PAGE = 100
# Google's own generated events, its contacts' birthdays: PONISTRA draws those from the
# contacts it has.
GENERATED = "unknownorganizer@calendar.google.com"
log = getLogger(__name__)


def _home(account: Account) -> str:
    return f"/calendar/dav/{urllib.parse.quote(account.username, safe='@')}/"


def _asked(authorization: str, method: str, path: str, body: ET.Element, depth: str) -> ET.Element:
    return client.asked("calendar", authorization, method, ROOT + path, body, depth)


def feeds(account: Account, authorization: str) -> list[Feed]:
    """The account's calendars as Google lists them now, each by its path; a new one gets a
    calendar of the user's own named as Google names it. Google's virtual calendars, the
    holidays among them, are left to it."""
    listed = []
    wanted = client.wanted(d("resourcetype"), d("displayname"))
    for path, held in client.found(_asked(authorization, "PROPFIND", _home(account), wanted, "1")):
        if held.find(f"{d('resourcetype')}/{c('calendar')}") is None or "@virtual/" in path:
            continue
        name = held.findtext(d("displayname"), "").strip()
        listed.append((path, account.address if name == account.username else name or path))
    for server_id, name in listed:
        feed, made = Feed.objects.get_or_create(
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


def _changed(authorization: str, feed: Feed) -> tuple[list[str], str]:
    """The paths changed since the feed's token, and the token now; every path where the
    server no longer knows the token."""
    asked = element(
        d("sync-collection"),
        element(d("sync-token"), text=feed.key),
        element(d("sync-level"), text="1"),
        element(d("prop"), element(d("getetag"))),
    )
    try:
        answer = _asked(authorization, "REPORT", feed.server_id, asked, "0")
    except Failed as failed:
        if not feed.key or failed.code != "calendar_refused":
            raise
        asked.find(d("sync-token")).text = ""
        answer = _asked(authorization, "REPORT", feed.server_id, asked, "0")
    paths = [
        path for path, _ in client.found(answer) if not path.endswith("/") and path.endswith(".ics")
    ]
    return paths, (answer.findtext(d("sync-token")) or "").strip()


def generated(found: list[ical.Found]) -> bool:
    master = found[0]
    return (
        master.organizer.get("email") == GENERATED
        and master.all_day
        and master.rrule.startswith("FREQ=YEARLY")
    )


def caught_up(account: Account, authorization: str, feed: Feed) -> int:
    """Takes the events new in the calendar since its token; how many were taken."""
    paths, token = _changed(authorization, feed)
    given = Taken.objects.filter(
        owner_id=account.owner_id, kind=Taken.Kind.GOOGLE, source=account.address
    )
    before = set(given.filter(item__in=paths).values_list("item", flat=True))
    new, count = [path for path in paths if path not in before], 0
    for start in range(0, len(new), PAGE):
        asked = element(
            c("calendar-multiget"),
            element(d("prop"), element(c("calendar-data"))),
            *(element(d("href"), text=path) for path in new[start : start + PAGE]),
        )
        for path, held in client.found(_asked(authorization, "REPORT", feed.server_id, asked, "1")):
            text = held.findtext(c("calendar-data"), "")
            if not text:
                continue
            try:
                found = ical.parsed(text)
            except ical.Malformed as malformed:
                log.warning("calendar: %s gave %s unread: %s", account.address, path, malformed)
                continue
            if generated(found):
                continue
            if taking.taken(
                account,
                Taken.Kind.GOOGLE,
                account.address,
                path,
                feed.calendar,
                found,
                {"ical": text},
                feed=feed,
            ):
                count += 1
    Feed.objects.filter(pk=feed.pk).update(key=token, error="")
    return count


def taken(account: Account) -> int:
    """Takes the account's new events from each of its calendars; how many were taken."""
    authorization = client.authorization(account)
    return sum(caught_up(account, authorization, feed) for feed in feeds(account, authorization))
