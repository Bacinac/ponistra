from datetime import UTC, datetime

import pytest

from apps.calendar import events, recurrence
from apps.calendar.ical import Found

pytestmark = pytest.mark.django_db


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def weekly(own, **more):
    found = Found(
        summary="Sastanak",
        starts=at("2026-03-23T09:00+01:00"),
        ends=at("2026-03-23T10:00+01:00"),
        zone="Europe/Zagreb",
        rrule="FREQ=WEEKLY;COUNT=4",
    )
    for name, value in more.items():
        setattr(found, name, value)
    return events.made(own, found)


def test_a_weekly_series_keeps_its_wall_time_across_the_change_to_summer_time(own):
    master = weekly(own)
    found = recurrence.occurrences(master, [], at("2026-03-01T00:00Z"), at("2026-05-01T00:00Z"))
    assert [each.start.isoformat() for each in found] == [
        "2026-03-23T08:00:00+00:00",
        "2026-03-30T07:00:00+00:00",
        "2026-04-06T07:00:00+00:00",
        "2026-04-13T07:00:00+00:00",
    ]
    assert all(each.recurrence_id == each.start for each in found)


def test_a_day_left_out_and_one_changed_on_its_own_take_their_places(own):
    master = weekly(own, exdates=["2026-03-30T07:00:00+00:00"])
    moved = events.made(
        own,
        Found(
            uid=master.uid,
            recurrence_id=at("2026-04-06T07:00Z"),
            summary="Pomaknut",
            starts=at("2026-04-08T14:00+02:00"),
            ends=at("2026-04-08T15:00+02:00"),
            zone="Europe/Zagreb",
        ),
        master=master,
    )
    found = recurrence.occurrences(
        master, [moved], at("2026-03-01T00:00Z"), at("2026-05-01T00:00Z")
    )
    assert [(each.start.isoformat(), each.shown.summary, each.moved) for each in found] == [
        ("2026-03-23T08:00:00+00:00", "Sastanak", False),
        ("2026-04-08T12:00:00+00:00", "Pomaknut", True),
        ("2026-04-13T07:00:00+00:00", "Sastanak", False),
    ]
    # The window holds only the moved one's new place.
    inside = recurrence.occurrences(
        master, [moved], at("2026-04-07T00:00Z"), at("2026-04-09T00:00Z")
    )
    assert [each.shown.summary for each in inside] == ["Pomaknut"]


def test_an_all_day_yearly_event_falls_on_its_day_whatever_the_zone(own):
    master = events.made(
        own,
        Found(
            summary="Rođendan",
            all_day=True,
            starts=recurrence.day_instant(datetime(1974, 9, 22).date()),
            ends=recurrence.day_instant(datetime(1974, 9, 23).date()),
            rrule="FREQ=YEARLY",
        ),
    )
    found = recurrence.occurrences(master, [], at("2026-09-01T00:00Z"), at("2026-10-01T00:00Z"))
    assert [
        (recurrence.as_day(each.start).isoformat(), recurrence.as_day(each.end).isoformat())
        for each in found
    ] == [("2026-09-22", "2026-09-23")]
    assert recurrence.first_after(master, at("2026-01-01T00:00Z")) == at("2026-09-22T00:00Z")


def test_an_until_given_as_a_day_ends_the_series_after_that_day(own):
    master = weekly(own, rrule="FREQ=WEEKLY;UNTIL=20260406")
    found = recurrence.occurrences(master, [], at("2026-03-01T00:00Z"), at("2026-05-01T00:00Z"))
    assert len(found) == 3
    assert recurrence.rule_text(master) == "FREQ=WEEKLY;UNTIL=20260406T215959Z"


def monthly(own, day_off, rrule="FREQ=MONTHLY;COUNT=12"):
    return weekly(
        own,
        starts=at("2026-01-01T09:00+01:00"),
        ends=at("2026-01-01T10:00+01:00"),
        rrule=rrule,
        day_off=day_off,
    )


def days(found) -> list[str]:
    zone = recurrence.zone_of("Europe/Zagreb")
    return [each.start.astimezone(zone).strftime("%m-%d %H:%M") for each in found]


@pytest.mark.parametrize(
    "day_off, held",
    [
        (
            "",
            ["01-01", "02-01", "03-01", "04-01", "05-01", "06-01"],
        ),
        (
            "skip",
            ["04-01", "06-01"],
        ),
        (
            "after",
            ["01-02", "02-02", "03-02", "04-01", "05-04", "06-01"],
        ),
        (
            "before",
            ["12-31", "01-30", "02-27", "04-01", "04-30", "06-01"],
        ),
    ],
)
def test_an_occurrence_on_a_weekend_or_a_holiday_is_held_skipped_or_moved(own, day_off, held):
    master = monthly(own, day_off, "FREQ=MONTHLY;COUNT=6")
    found = recurrence.occurrences(master, [], at("2025-12-01T00:00Z"), at("2026-12-31T00:00Z"))
    assert days(found) == [f"{each} 09:00" for each in held]
    by_rule = [f"{month:02}-01" for month in range(1, 7)]
    assert [each.recurrence_id.strftime("%m-%d") for each in found] == (
        ["04-01", "06-01"] if day_off == "skip" else by_rule
    )


def test_a_moved_occurrence_shows_in_the_window_it_moved_into(own):
    after = monthly(own, "after")
    assert days(
        recurrence.occurrences(after, [], at("2026-08-02T00:00Z"), at("2026-08-10T00:00Z"))
    ) == ["08-03 09:00"]
    before = monthly(own, "before")
    assert days(
        recurrence.occurrences(before, [], at("2026-07-30T00:00Z"), at("2026-08-01T00:00Z"))
    ) == ["07-31 09:00"]


def test_an_occurrence_moved_onto_another_one_goes_into_it(own):
    for day_off in ("after", "before"):
        master = weekly(
            own,
            starts=at("2026-10-30T09:00+01:00"),
            ends=at("2026-10-30T10:00+01:00"),
            rrule="FREQ=DAILY;COUNT=4",
            day_off=day_off,
        )
        found = recurrence.occurrences(master, [], at("2026-10-29T00:00Z"), at("2026-11-05T00:00Z"))
        assert days(found) == ["10-30 09:00", "11-02 09:00"]


def test_an_all_day_series_moves_by_days(own):
    master = events.made(
        own,
        Found(
            summary="Inventura",
            all_day=True,
            starts=recurrence.day_instant(datetime(2026, 12, 25).date()),
            ends=recurrence.day_instant(datetime(2026, 12, 26).date()),
            rrule="FREQ=YEARLY;COUNT=2",
            day_off="after",
        ),
    )
    found = recurrence.occurrences(master, [], at("2026-12-01T00:00Z"), at("2028-01-31T00:00Z"))
    assert [
        (recurrence.as_day(each.start).isoformat(), recurrence.as_day(each.end).isoformat())
        for each in found
    ] == [("2026-12-28", "2026-12-29"), ("2027-12-27", "2027-12-28")]
    assert recurrence.days_off(master) == [
        (datetime(2026, 12, 25).date(), datetime(2026, 12, 28).date()),
        (datetime(2027, 12, 25).date(), datetime(2027, 12, 27).date()),
    ]
