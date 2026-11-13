import base64
import struct
from xml.etree import ElementTree as ET

import pytest

from apps.calendar import activesync, google, graph, sync
from apps.calendar.models import Calendar, Event, Feed, Taken
from apps.core import sealed
from apps.mail import signin
from apps.mail.activesync.wbxml import element as e
from apps.mail.imap import Failed
from apps.mail.models import Account
from apps.mail.tests.eas import appointment, everything

pytestmark = pytest.mark.django_db


def zone_blob(bias=-60, daylight=True) -> str:
    """A TIME_ZONE_INFORMATION as Traveler sends Central European Time."""
    standard = (0, 10, 0, 5, 3, 0, 0, 0) if daylight else (0,) * 8
    summer = (0, 3, 0, 5, 2, 0, 0, 0) if daylight else (0,) * 8
    raw = struct.pack("<i", bias) + b"\0" * 64 + struct.pack("<8H", *standard)
    raw += struct.pack("<i", 0) + b"\0" * 64 + struct.pack("<8H", *summer)
    raw += struct.pack("<i", -60 if daylight else 0)
    return base64.b64encode(raw).decode()


def test_the_zone_blob_is_matched_to_an_iana_zone():
    assert activesync.zone_named(zone_blob()) == "Europe/Zagreb"
    assert activesync.zone_named(zone_blob(bias=0, daylight=False)) == ""
    assert activesync.zone_named("nonsense") == ""


def test_a_traveler_calendar_is_an_organisations_calendar_refreshed_read_only(account, box):
    box.put(
        "4",
        appointment(
            UID="trav-1",
            Subject="Kolegij",
            Location="Soba 1",
            OnlineMeetingExternalLink="https://meet.example.com/kolegij",
            TimeZone=zone_blob(),
            StartTime="20261102T080000Z",
            EndTime="20261102T090000Z",
            AllDayEvent="0",
            BusyStatus="2",
            Recurrence=[
                e("Calendar:Type", "1"),
                e("Calendar:Interval", "1"),
                e("Calendar:DayOfWeek", "2"),
                e("Calendar:Occurrences", "4"),
            ],
            Exceptions=[
                e(
                    "Calendar:Exception",
                    e("Calendar:ExceptionStartTime", "20261109T080000Z"),
                    e("Calendar:Deleted", "1"),
                ),
                e(
                    "Calendar:Exception",
                    e("Calendar:ExceptionStartTime", "20261116T080000Z"),
                    e("Calendar:StartTime", "20261116T130000Z"),
                    e("Calendar:EndTime", "20261116T140000Z"),
                    e("Calendar:Subject", "Kolegij kasnije"),
                ),
            ],
        ),
    )
    everything(account)
    held = Calendar.objects.get()
    assert (held.kind, held.name, held.read_only) == ("organisation", "Calendar", True)
    master = Event.objects.get(master__isnull=True)
    assert master.summary == "Kolegij" and master.zone == "Europe/Zagreb"
    assert master.rrule == "FREQ=WEEKLY;BYDAY=MO;COUNT=4"
    assert master.exdates == ["2026-11-09T08:00:00+00:00"]
    assert [(each.summary, each.conference) for each in master.overrides.all()] == [
        ("Kolegij kasnije", "https://meet.example.com/kolegij")
    ]
    assert Feed.objects.get().key not in ("", "0")
    box.items["4"].clear()
    everything(account)
    assert Event.objects.count() == 0
    assert Calendar.objects.filter(pk=held.pk).exists()


def test_a_wiped_account_takes_its_calendars_away(account, box):
    box.put(
        "4",
        appointment(UID="t", Subject="X", StartTime="20261102T080000Z", EndTime="20261102T090000Z"),
    )
    everything(account)
    assert Event.objects.count() == 1
    activesync.wiped(account)
    assert Calendar.objects.count() == 0 and Event.objects.count() == 0


@pytest.fixture
def gmail(owner):
    return Account.objects.create(
        owner=owner,
        address="ime@gmail.com",
        username="ime@gmail.com",
        secret=sealed.seal("mail", "abcd efgh ijkl mnop"),
        imap_host="imap.gmail.com",
    )


HOME = "/calendar/dav/ime@gmail.com/"
EVENTS = f"{HOME}events/"
ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:{uid}\r\nDTSTAMP:20261001T000000Z\r\n"
    "DTSTART:20261105T090000Z\r\nDTEND:20261105T100000Z\r\nSUMMARY:{summary}\r\n{more}"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
)


class Google:
    def __init__(self, items: dict[str, str]):
        self.items = items
        self.asked = []

    def __call__(self, authorization, method, path, body, depth):
        self.asked.append((authorization, method, path, depth))
        hrefs = [each.text for each in body.iter("{DAV:}href")]
        if method == "PROPFIND":
            return ET.fromstring(
                '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                f"<d:response><d:href>{HOME}</d:href><d:propstat><d:prop><d:resourcetype>"
                "<d:collection/></d:resourcetype></d:prop><d:status>HTTP/1.1 200 OK</d:status>"
                f"</d:propstat></d:response><d:response><d:href>{EVENTS}</d:href><d:propstat>"
                "<d:prop><d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                "<d:displayname>ime@gmail.com</d:displayname></d:prop><d:status>HTTP/1.1 200 OK"
                f"</d:status></d:propstat></d:response><d:response><d:href>{HOME}@virtual/h/"
                "</d:href><d:propstat><d:prop><d:resourcetype><d:collection/><c:calendar/>"
                "</d:resourcetype><d:displayname>Blagdani</d:displayname></d:prop>"
                "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>"
            )
        if body.tag.endswith("sync-collection"):
            token = body.findtext("{DAV:}sync-token") or ""
            if token == "old":
                raise Failed("calendar_refused")
            listed = (
                list(self.items)
                if token != "t1"
                else [k for k in self.items if k.startswith("new")]
            )
            responses = "".join(
                f'<d:response><d:href>{EVENTS}{k}.ics</d:href><d:propstat><d:prop><d:getetag>"1"</d:getetag>'
                "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
                for k in listed
            )
            return ET.fromstring(
                f'<d:multistatus xmlns:d="DAV:">{responses}<d:sync-token>t1</d:sync-token>'
                "</d:multistatus>"
            )
        responses = "".join(
            f"<d:response><d:href>{href}</d:href><d:propstat><d:prop><c:calendar-data>"
            f"{self.items[href.removeprefix(EVENTS).removesuffix('.ics')]}</c:calendar-data>"
            "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
            for href in hrefs
        )
        return ET.fromstring(
            f'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">{responses}'
            "</d:multistatus>"
        )


def test_a_google_calendar_is_taken_once_into_a_calendar_of_the_users_own(gmail, monkeypatch):
    server = Google(
        {
            "a1": ICS.format(uid="a1", summary="Sastanak", more=""),
            "b2": ICS.format(
                uid="b2",
                summary="Rođendan",
                more="ORGANIZER:mailto:unknownorganizer@calendar.google.com\r\nRRULE:FREQ=YEARLY\r\n",
            ).replace(
                "DTSTART:20261105T090000Z\r\nDTEND:20261105T100000Z",
                "DTSTART;VALUE=DATE:20261105\r\nDTEND;VALUE=DATE:20261106",
            ),
        }
    )
    monkeypatch.setattr(google, "_asked", server)
    assert google.taken(gmail) == 1
    own = Calendar.objects.get()
    assert (own.kind, own.name, own.read_only) == ("own", "ime@gmail.com", False)
    assert [each.summary for each in own.events.all()] == ["Sastanak"]
    assert Feed.objects.get().key == "t1"
    basic = base64.b64encode(b"ime@gmail.com:abcd efgh ijkl mnop").decode()
    assert {each[0] for each in server.asked} == {f"Basic {basic}"}
    server.items["new3"] = ICS.format(uid="n3", summary="Novi", more="")
    assert google.taken(gmail) == 1
    assert Taken.objects.filter(kind=Taken.Kind.GOOGLE).count() == 2
    # The event taken is ours now: a change here is not undone by the next pass.
    own.events.filter(uid="a1").update(summary="Naš")
    assert google.taken(gmail) == 0
    assert own.events.get(uid="a1").summary == "Naš"


def test_a_google_token_the_server_forgot_starts_the_calendar_over(gmail, monkeypatch):
    server = Google({"a1": ICS.format(uid="a1", summary="Sastanak", more="")})
    monkeypatch.setattr(google, "_asked", server)
    google.taken(gmail)
    Feed.objects.update(key="old")
    assert google.taken(gmail) == 0
    assert Feed.objects.get().key == "t1"


G = "https://graph.microsoft.com/v1.0"


class Graph:
    def __init__(self, pages: dict):
        self.pages = pages

    def __call__(self, token, url):
        prefix = max((each for each in self.pages if url.startswith(each)), key=len, default=None)
        if prefix is None:
            raise AssertionError(url)
        if isinstance(self.pages[prefix], Exception):
            raise self.pages[prefix]
        return self.pages[prefix]


@pytest.fixture
def outlook(owner, monkeypatch):
    monkeypatch.setattr(signin, "graph", lambda account: "token")
    return Account.objects.create(
        owner=owner,
        address="ime@outlook.com",
        username="ime@outlook.com",
        login=Account.Login.MICROSOFT,
        secret=sealed.seal("mail", "refresh"),
        imap_host="outlook.office365.com",
    )


def test_a_microsoft_calendars_series_comes_with_its_exceptions(outlook, monkeypatch):
    series = {
        "id": "S1",
        "iCalUId": "s1@outlook",
        "subject": "Tjedni",
        "type": "seriesMaster",
        "start": {"dateTime": "2026-11-02T09:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-11-02T10:00:00.0000000", "timeZone": "UTC"},
        "originalStartTimeZone": "Central Europe Standard Time",
        "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/19%3ameeting"},
        "recurrence": {
            "pattern": {"type": "weekly", "interval": 1, "daysOfWeek": ["monday"]},
            "range": {"type": "numbered", "numberOfOccurrences": 4, "startDate": "2026-11-02"},
        },
    }
    pages = {
        f"{G}/me/calendars": {
            "value": [
                {"id": "C1", "name": "Kalendar", "canEdit": True},
                {"id": "B", "name": "Birthdays", "canEdit": False},
            ]
        },
        f"{G}/me/calendars/C1/events/delta": {
            "value": [
                series,
                {"id": "O1", "type": "occurrence", "subject": "Tjedni"},
                {"id": "E1", "type": "exception", "subject": "Tjedni kasnije"},
                {"id": "X", "@removed": {}},
            ],
            "@odata.deltaLink": "delta-1",
        },
        f"{G}/me/events/S1/exceptionOccurrences": {
            "value": [
                {
                    "id": "E1",
                    "subject": "Tjedni kasnije",
                    "type": "exception",
                    "originalStart": "2026-11-09T09:00:00Z",
                    "start": {"dateTime": "2026-11-09T14:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-11-09T15:00:00.0000000", "timeZone": "UTC"},
                }
            ]
        },
        f"{G}/me/events/S1/instances": {
            "value": [
                {"originalStart": "2026-11-02T09:00:00Z", "type": "occurrence"},
                {"originalStart": "2026-11-09T09:00:00Z", "type": "exception"},
                {"originalStart": "2026-11-23T09:00:00Z", "type": "occurrence"},
            ]
        },
    }
    monkeypatch.setattr(graph, "_get", Graph(pages))
    assert graph.taken(outlook) == 1
    own = Calendar.objects.get()
    assert own.name == "Kalendar" and own.kind == "own"
    master = own.events.get(master__isnull=True)
    assert master.rrule == "FREQ=WEEKLY;BYDAY=MO;COUNT=4" and master.zone == "Europe/Budapest"
    assert master.exdates == ["2026-11-16T09:00:00+00:00"]
    assert master.conference == "https://teams.microsoft.com/l/meetup-join/19%3ameeting"
    assert [each.summary for each in master.overrides.all()] == ["Tjedni kasnije"]
    assert Feed.objects.get().key == "delta-1"
    pages["delta-1"] = graph.Gone()
    assert graph.taken(outlook) == 0


def test_a_failing_source_is_noted_on_its_feed(gmail, monkeypatch):
    def refused(*args):
        raise Failed("calendar_refused")

    monkeypatch.setattr(google, "_asked", refused)
    sync._taken(gmail)
    assert Feed.objects.get(server_id="").error == "calendar_refused"
