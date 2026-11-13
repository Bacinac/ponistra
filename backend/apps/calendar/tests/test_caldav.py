import pytest

from apps.calendar import events, taking
from apps.calendar.ical import Found
from apps.calendar.models import Calendar, Event
from apps.calendar.tests.test_recurrence import at

pytestmark = pytest.mark.django_db

PROPS = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" '
    'xmlns:a="http://apple.com/ns/ical/"><d:prop><d:current-user-principal/>'
    "<c:calendar-home-set/><d:resourcetype/><d:displayname/><a:calendar-color/><d:sync-token/>"
    "<d:getetag/><d:current-user-privilege-set/></d:prop></d:propfind>"
)
SYNC = (
    '<?xml version="1.0"?><d:sync-collection xmlns:d="DAV:" '
    'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:sync-token>{}</d:sync-token>'
    "<d:sync-level>1</d:sync-level><d:prop><d:getetag/><c:calendar-data/></d:prop>"
    "</d:sync-collection>"
)
QUERY = (
    '<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    '<d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
    '<c:comp-filter name="VEVENT"><c:time-range start="{}" end="{}"/></c:comp-filter>'
    "</c:comp-filter></c:filter></c:calendar-query>"
)
ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//phone//EN\r\nBEGIN:VEVENT\r\nUID:p-1\r\n"
    "DTSTAMP:20261026T100000Z\r\nDTSTART;TZID=Europe/Zagreb:20261105T160000\r\n"
    "DTEND;TZID=Europe/Zagreb:20261105T170000\r\nSUMMARY:S telefona\r\n"
    "RRULE:FREQ=DAILY;COUNT=3\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:p-1\r\n"
    "RECURRENCE-ID;TZID=Europe/Zagreb:20261106T160000\r\nDTSTAMP:20261026T100000Z\r\n"
    "DTSTART;TZID=Europe/Zagreb:20261106T180000\r\nDTEND;TZID=Europe/Zagreb:20261106T190000\r\n"
    "SUMMARY:S telefona kasnije\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)


def path(calendar) -> str:
    return f"/dav/calendars/{calendar.owner_id}/{calendar.pk}/"


def dav(client, method, where, body="", **headers):
    return client.generic(method, where, body, content_type="application/xml", **headers)


def token(text: str) -> str:
    return text[text.index("<d:sync-token>") + 14 : text.index("</d:sync-token>")]


def test_the_phone_finds_the_calendars_from_the_principal(phone, owner, own):
    principal = dav(phone, "PROPFIND", f"/dav/principals/{owner.pk}/", PROPS, HTTP_DEPTH="0")
    text = principal.content.decode()
    assert f"<d:href>/dav/calendars/{owner.pk}/</d:href>" in text
    home = dav(phone, "PROPFIND", f"/dav/calendars/{owner.pk}/", PROPS, HTTP_DEPTH="1")
    text = home.content.decode()
    assert home.status_code == 207
    assert f"<d:href>{path(own)}</d:href>" in text
    assert "<cal:calendar />" in text and "<d:displayname>Moj</d:displayname>" in text
    assert "<apple:calendar-color>#0E7A83FF</apple:calendar-color>" in text
    assert "<d:write />" in text
    stranger = dav(phone, "PROPFIND", f"/dav/calendars/{owner.pk + 1}/", PROPS, HTTP_DEPTH="1")
    assert stranger.status_code == 404


def test_an_organisations_calendar_is_read_only_for_the_phone(phone, owner, account):
    held = Calendar.objects.create(
        owner=owner, kind=Calendar.Kind.ORGANISATION, name="Brezik", account=account
    )
    text = dav(phone, "PROPFIND", path(held), PROPS, HTTP_DEPTH="0").content.decode()
    assert "<d:read />" in text and "<d:write />" not in text
    refused = phone.put(path(held) + "n.ics", ICS, content_type="text/calendar")
    assert refused.status_code == 403
    assert dav(phone, "DELETE", path(held)).status_code == 403


def test_a_series_the_phone_puts_is_kept_whole_and_given_back(phone, own):
    where = path(own) + "p-1.ics"
    made = phone.put(where, ICS, content_type="text/calendar", HTTP_IF_NONE_MATCH="*")
    assert made.status_code == 201
    master = Event.objects.get(href="p-1.ics", master__isnull=True)
    assert master.rrule == "FREQ=DAILY;COUNT=3" and master.overrides.count() == 1
    again = phone.put(where, ICS, content_type="text/calendar", HTTP_IF_NONE_MATCH="*")
    assert again.status_code == 412
    got = phone.get(where)
    assert got.status_code == 200 and got["ETag"] == f'"{master.revision}"'
    assert got.content.count(b"BEGIN:VEVENT") == 2
    # Without the override the row for it goes; a wrong etag is refused.
    shorter = ICS[: ICS.index("BEGIN:VEVENT\r\nUID:p-1\r\nRECURRENCE-ID")] + "END:VCALENDAR\r\n"
    stale = phone.put(where, shorter, content_type="text/calendar", HTTP_IF_MATCH='"0"')
    assert stale.status_code == 412
    changed = phone.put(where, shorter, content_type="text/calendar", HTTP_IF_MATCH=got["ETag"])
    assert changed.status_code == 204
    assert Event.objects.get(pk=master.pk).overrides.count() == 0
    other = phone.put(path(own) + "other.ics", ICS, content_type="text/calendar")
    assert other.status_code == 409
    broken = phone.put(
        path(own) + "b.ics", "BEGIN:VCALENDAR\r\nhello", content_type="text/calendar"
    )
    assert broken.status_code == 415


def test_the_phone_asks_for_a_window_and_gets_the_series_that_touch_it(phone, own):
    events.made(
        own,
        Found(
            summary="Tjedni",
            starts=at("2026-01-05T09:00+01:00"),
            ends=at("2026-01-05T10:00+01:00"),
            zone="Europe/Zagreb",
            rrule="FREQ=WEEKLY",
        ),
    )
    events.made(
        own,
        Found(summary="Jednom", starts=at("2026-02-01T09:00Z"), ends=at("2026-02-01T10:00Z")),
    )
    inside = dav(phone, "REPORT", path(own), QUERY.format("20260601T000000Z", "20260701T000000Z"))
    assert inside.content.count(b"<d:response>") == 1 and b"SUMMARY:Tjedni" in inside.content
    both = dav(phone, "REPORT", path(own), QUERY.format("20260101T000000Z", "20260301T000000Z"))
    assert both.content.count(b"<d:response>") == 2


def test_the_phone_follows_changes_by_the_sync_token(phone, own):
    first = events.made(
        own,
        Found(summary="Prvi", starts=at("2026-02-01T09:00Z"), ends=at("2026-02-01T10:00Z")),
    )
    initial = dav(phone, "REPORT", path(own), SYNC.format(""))
    assert initial.status_code == 207 and initial.content.count(b"<d:response>") == 1
    held = token(initial.content.decode())
    second = events.made(
        own,
        Found(summary="Drugi", starts=at("2026-02-02T09:00Z"), ends=at("2026-02-02T10:00Z")),
    )
    events.deleted(first)
    since = dav(phone, "REPORT", path(own), SYNC.format(held)).content.decode()
    assert since.count("<d:response>") == 2
    assert f"{path(own)}{first.href}</d:href><d:status>HTTP/1.1 404" in since
    assert f"{path(own)}{second.href}</d:href><d:propstat>" in since
    assert (
        dav(phone, "REPORT", path(own), SYNC.format("urn:x-ponistra:sync:9999")).status_code == 403
    )
    assert dav(phone, "REPORT", path(own), SYNC.format("nonsense")).status_code == 403


def test_a_new_calendar_shows_up_in_the_home_with_the_next_colour(phone, owner, own):
    second = taking.own(owner.pk, "Drugi")
    assert second.color == 1
    text = dav(phone, "PROPFIND", f"/dav/calendars/{owner.pk}/", PROPS, HTTP_DEPTH="1").content
    assert text.count(b"<cal:calendar />") == 2
