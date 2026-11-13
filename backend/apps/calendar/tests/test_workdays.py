from datetime import date

import pytest

from apps.calendar import ical, recurrence
from apps.calendar.models import Closure, Event
from apps.calendar.tests.test_recurrence import at, days, weekly
from apps.calendar.tests.test_views import listed, sent

pytestmark = pytest.mark.django_db


@pytest.fixture
def administrator(signed_in, owner):
    owner.is_staff = True
    owner.save()
    return signed_in


def wednesdays(own, day_off):
    return weekly(
        own,
        starts=at("2026-11-11T09:00+01:00"),
        ends=at("2026-11-11T10:00+01:00"),
        rrule="FREQ=WEEKLY;COUNT=3",
        day_off=day_off,
    )


def test_the_country_and_its_region_say_which_days_are_holidays(administrator, own):
    master = wednesdays(own, "skip")

    def held():
        return days(
            recurrence.occurrences(master, [], at("2026-11-01T00:00Z"), at("2026-12-01T00:00Z"))
        )

    assert held() == ["11-11 09:00", "11-25 09:00"]
    assert sent(administrator, "patch", "/api/calendar/workdays", country="DE").status_code == 200
    assert held() == ["11-11 09:00", "11-18 09:00", "11-25 09:00"]
    saxony = sent(administrator, "patch", "/api/calendar/workdays", country="de", subdivision="SN")
    assert saxony.json()["country"] == "DE" and saxony.json()["subdivision"] == "SN"
    assert held() == ["11-11 09:00", "11-25 09:00"]
    assert administrator.get("/api/calendar/days-off?from=2026-11-14&to=2026-11-20").json() == {
        "days_off": ["2026-11-14", "2026-11-15", "2026-11-18"]
    }
    shown = listed(administrator, "2026-11-01", "2026-11-30")["holidays"]
    assert shown == [
        {"date": "2026-11-18", "hr": "Buß- und Bettag", "en": "Repentance and Prayer Day"}
    ]


def test_the_administrator_alone_chooses_a_country_the_library_knows(administrator, owner):
    shown = administrator.get("/api/calendar/workdays").json()
    assert shown["country"] == "HR" and shown["subdivision"] == ""
    assert shown["countries"]["HR"] == [] and ["BY", "Bayern"] in shown["countries"]["DE"]
    assert {"hr": "Božić", "en": "Christmas Day"}.items() <= next(
        each for each in shown["holidays"] if each["date"].endswith("-12-25")
    ).items()
    refused = sent(administrator, "patch", "/api/calendar/workdays", country="XX")
    assert refused.json()["error"] == "invalid_country"
    refused = sent(administrator, "patch", "/api/calendar/workdays", country="HR", subdivision="BY")
    assert refused.json()["error"] == "invalid_subdivision"
    owner.is_staff = False
    owner.save()
    assert administrator.get("/api/calendar/workdays").status_code == 403
    assert sent(administrator, "patch", "/api/calendar/workdays", country="DE").status_code == 403


def test_a_closure_moves_a_series_and_a_phone_hears_of_it(administrator, own):
    master = wednesdays(own, "after")
    single = weekly(own, rrule="")
    revisions = {each.pk: each.revision for each in Event.objects.all()}
    made = sent(
        administrator,
        "post",
        "/api/calendar/closures",
        closures=[{"first": "2026-11-18", "last": "2026-11-20", "name": "Kolektivni godišnji"}],
    )
    assert made.status_code == 201
    pk = made.json()["closures"][0]["id"]
    after = {each.pk: each.revision for each in Event.objects.all()}
    assert after[master.pk] > revisions[master.pk] and after[single.pk] == revisions[single.pk]
    found = recurrence.occurrences(master, [], at("2026-11-01T00:00Z"), at("2026-12-01T00:00Z"))
    assert days(found) == ["11-11 09:00", "11-23 09:00", "11-25 09:00"]
    shown = listed(administrator, "2026-11-01", "2026-11-30")["holidays"]
    assert [each["hr"] for each in shown if each["date"] == "2026-11-18"] == [
        "Dan sjećanja na žrtve Domovinskog rata i Dan sjećanja na žrtvu Vukovara i Škabrnje",
        "Kolektivni godišnji",
    ]
    assert [each["date"] for each in shown] == [
        "2026-11-01",
        "2026-11-18",
        "2026-11-18",
        "2026-11-19",
        "2026-11-20",
    ]
    assert shown[3] == {
        "date": "2026-11-19",
        "hr": "Kolektivni godišnji",
        "en": "Kolektivni godišnji",
    }
    moved = sent(administrator, "patch", f"/api/calendar/closures/{pk}", last="2026-11-19")
    assert moved.json() == {
        "id": pk,
        "first": "2026-11-18",
        "last": "2026-11-19",
        "name": "Kolektivni godišnji",
    }
    found = recurrence.occurrences(master, [], at("2026-11-01T00:00Z"), at("2026-12-01T00:00Z"))
    assert days(found) == ["11-11 09:00", "11-20 09:00", "11-25 09:00"]
    assert administrator.delete(f"/api/calendar/closures/{pk}").status_code == 204
    assert administrator.get("/api/calendar/workdays").json()["closures"] == []


@pytest.mark.parametrize(
    "closure",
    [
        {"first": "2026-11-20", "last": "2026-11-18", "name": "Unatrag"},
        {"first": "2026-11-18", "last": "2026-11-18", "name": "  "},
        {"first": "18.11.2026", "last": "2026-11-18", "name": "Datum"},
        "Kolektivni",
    ],
)
def test_a_closure_needs_its_days_in_order_and_a_name(administrator, closure):
    refused = sent(administrator, "post", "/api/calendar/closures", closures=[closure])
    assert refused.status_code == 400 and refused.json()["error"] == "invalid_closure"
    assert not Closure.objects.exists()


ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:leave
DTSTART;VALUE=DATE:20260803
DTEND;VALUE=DATE:20260815
SUMMARY:Kolektivni godišnji
END:VEVENT
BEGIN:VEVENT
UID:day
DTSTART;VALUE=DATE:20261224
DTEND;VALUE=DATE:20261225
RRULE:FREQ=YEARLY;COUNT=3
EXDATE;VALUE=DATE:20271224
SUMMARY:Badnjak
END:VEVENT
BEGIN:VEVENT
UID:day
RECURRENCE-ID;VALUE=DATE:20281224
DTSTART;VALUE=DATE:20281222
DTEND;VALUE=DATE:20281223
SUMMARY:Badnjak
END:VEVENT
BEGIN:VEVENT
UID:called-off
DTSTART;VALUE=DATE:20261231
DTEND;VALUE=DATE:20270101
STATUS:CANCELLED
SUMMARY:Stara godina
END:VEVENT
BEGIN:VEVENT
UID:evening
DTSTART;TZID=Europe/Zagreb:20261105T170000
DTEND;TZID=Europe/Zagreb:20261106T000000
SUMMARY:Inventura
END:VEVENT
BEGIN:VEVENT
UID:long-gone
DTSTART;VALUE=DATE:20190101
DTEND;VALUE=DATE:20190102
SUMMARY:Davno
END:VEVENT
END:VCALENDAR
"""


def test_an_icalendar_gives_the_days_its_events_take():
    assert ical.closed(ICS, date(2026, 10, 28)) == [
        (date(2026, 8, 3), date(2026, 8, 14), "Kolektivni godišnji"),
        (date(2026, 11, 5), date(2026, 11, 5), "Inventura"),
        (date(2026, 12, 24), date(2026, 12, 24), "Badnjak"),
        (date(2028, 12, 22), date(2028, 12, 22), "Badnjak"),
    ]
    with pytest.raises(ical.Malformed):
        ical.closed("BEGIN:VCALENDAR\nnonsense", date(2026, 10, 28))


def test_the_administrator_reads_a_file_and_takes_the_days_not_yet_kept(administrator):
    Closure.objects.create(
        first=date(2026, 8, 3), last=date(2026, 8, 14), name="Kolektivni godišnji"
    )
    read = sent(administrator, "post", "/api/calendar/closures/read", ics=ICS)
    assert [each["name"] for each in read.json()["closures"]] == ["Inventura", "Badnjak", "Badnjak"]
    assert not Closure.objects.filter(name="Badnjak").exists()
    refused = sent(administrator, "post", "/api/calendar/closures/read", ics="nonsense")
    assert refused.status_code == 400 and refused.json()["error"] == "invalid_ics"


def test_the_working_hours_bound_the_times_offered(administrator, own):
    assert administrator.get("/api/calendar/workdays").json()["opens"] == "08:00"
    for wrong in ({"opens": "11:00", "closes": "09:00"}, {"opens": "9", "closes": "10:30"}):
        refused = sent(administrator, "patch", "/api/calendar/workdays", **wrong)
        assert refused.status_code == 400 and refused.json()["error"] == "invalid_hours"
    hours = sent(administrator, "patch", "/api/calendar/workdays", opens="09:00", closes="10:30")
    assert hours.status_code == 200 and hours.json()["closes"] == "10:30"
    asked = "zone=Europe/Zagreb&offers=1"
    found = administrator.get(
        f"/api/calendar/free?{asked}&start=2030-06-07T13:00&end=2030-06-07T14:00"
    ).json()["offers"]
    assert [each["start"][:16] for each in found] == [
        "2030-06-07T09:00",
        "2030-06-10T09:00",
        "2030-06-11T09:00",
        "2030-06-12T09:00",
        "2030-06-13T09:00",
        "2030-06-14T09:00",
    ]
    longer = administrator.get(
        f"/api/calendar/free?{asked}&start=2030-06-07T09:00&end=2030-06-07T11:00"
    ).json()["offers"]
    assert longer == []
