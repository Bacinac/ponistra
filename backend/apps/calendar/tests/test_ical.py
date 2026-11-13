import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from django.conf import settings

from apps.calendar import events, ical

pytestmark = pytest.mark.django_db

PHONE = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple//EN\r\n"
    "BEGIN:VTIMEZONE\r\nTZID:Europe/Zagreb\r\nBEGIN:STANDARD\r\nDTSTART:19701025T030000\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\nTZOFFSETFROM:+0200\r\nTZOFFSETTO:+0100\r\n"
    "END:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:19700329T020000\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\nTZOFFSETFROM:+0100\r\nTZOFFSETTO:+0200\r\n"
    "END:DAYLIGHT\r\nEND:VTIMEZONE\r\n"
    "BEGIN:VEVENT\r\nUID:abc-1\r\nDTSTAMP:20261001T100000Z\r\n"
    "DTSTART;TZID=Europe/Zagreb:20261102T090000\r\nDTEND;TZID=Europe/Zagreb:20261102T100000\r\n"
    "SUMMARY:Sastanak\r\nLOCATION:Soba 3\r\nDESCRIPTION:Dnevni red\\nTočka 1\r\n"
    "RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=5\r\nEXDATE;TZID=Europe/Zagreb:20261116T090000\r\n"
    "STATUS:TENTATIVE\r\nTRANSP:TRANSPARENT\r\nCLASS:PRIVATE\r\nSEQUENCE:2\r\n"
    "ORGANIZER;CN=Ivo:mailto:ivo@example.com\r\n"
    "ATTENDEE;CN=Ana;ROLE=OPT-PARTICIPANT;PARTSTAT=ACCEPTED:mailto:ana@firma.test\r\n"
    "X-APPLE-TRAVEL-ADVISORY-BEHAVIOR:AUTOMATIC\r\n"
    "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nDESCRIPTION:Podsjetnik\r\nEND:VALARM\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:abc-1\r\nRECURRENCE-ID;TZID=Europe/Zagreb:20261109T090000\r\n"
    "DTSTAMP:20261001T100000Z\r\nDTSTART;TZID=Europe/Zagreb:20261109T140000\r\n"
    "DTEND;TZID=Europe/Zagreb:20261109T150000\r\nSUMMARY:Sastanak kasnije\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def test_a_phones_series_is_read_whole_and_written_back_the_same(own):
    master, override = ical.parsed(PHONE)
    assert master.uid == "abc-1" and master.recurrence_id is None
    assert master.starts == datetime(2026, 11, 2, 8, tzinfo=UTC) and master.zone == "Europe/Zagreb"
    assert set(master.rrule.split(";")) == {"FREQ=WEEKLY", "BYDAY=MO", "COUNT=5"}
    assert master.exdates == ["2026-11-16T08:00:00+00:00"]
    assert (master.status, master.busy, master.private, master.sequence) == (
        "tentative",
        False,
        True,
        2,
    )
    assert master.description == "Dnevni red\nTočka 1"
    assert master.organizer == {"email": "ivo@example.com", "name": "Ivo"}
    assert master.attendees == [
        {"email": "ana@firma.test", "name": "Ana", "role": "optional", "status": "accepted"}
    ]
    assert master.reminders == [15]
    assert master.extra == ["X-APPLE-TRAVEL-ADVISORY-BEHAVIOR:AUTOMATIC"]
    assert override.recurrence_id == datetime(2026, 11, 9, 8, tzinfo=UTC)
    assert override.summary == "Sastanak kasnije"

    kept = events.made(own, master)
    events.made(own, override, master=kept)
    written = events.written(kept)
    again = ical.parsed(written)
    assert [each.fields for each in again] == [master.fields, override.fields]
    assert "X-APPLE-TRAVEL-ADVISORY-BEHAVIOR:AUTOMATIC" in written
    assert "BEGIN:VTIMEZONE" in written and "TRIGGER:-PT15M" in written


def test_the_dates_a_series_adds_are_read_as_their_starts_a_period_among_them():
    text = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:r1\r\n"
        "DTSTART:20261103T080000Z\r\nDTEND:20261103T090000Z\r\nRRULE:FREQ=WEEKLY;COUNT=3\r\n"
        "RDATE:20261224T080000Z\r\nRDATE;VALUE=PERIOD:20261226T080000Z/PT1H\r\n"
        "EXDATE:20261110T080000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    (found,) = ical.parsed(text)
    assert found.rdates == ["2026-12-24T08:00:00+00:00", "2026-12-26T08:00:00+00:00"]
    assert found.exdates == ["2026-11-10T08:00:00+00:00"]


def test_an_all_day_event_and_a_floating_one_keep_their_days():
    text = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:d1\r\n"
        "DTSTART;VALUE=DATE:20261224\r\nDTEND;VALUE=DATE:20261227\r\nSUMMARY:Božić\r\n"
        "RRULE:FREQ=YEARLY;UNTIL=20301231\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    (found,) = ical.parsed(text)
    assert found.all_day and found.starts == datetime(2026, 12, 24, tzinfo=UTC)
    assert found.ends == datetime(2026, 12, 27, tzinfo=UTC)
    assert found.rrule == "FREQ=YEARLY;UNTIL=20301231"


def test_what_is_not_a_calendar_is_refused():
    with pytest.raises(ical.Malformed):
        ical.parsed("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n")
    with pytest.raises(ical.Malformed):
        ical.parsed("hello")


def _single(*lines: str) -> str:
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\nBEGIN:VEVENT\r\nUID:meet-1\r\n"
        "DTSTAMP:20261001T100000Z\r\nDTSTART:20261102T090000Z\r\nDTEND:20261102T100000Z\r\n"
        "SUMMARY:Kolegij\r\n"
        + "".join(f"{line}\r\n" for line in lines)
        + "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )


def test_a_meeting_is_joined_by_the_conference_its_invitation_names_and_written_as_the_standard_one(
    own,
):
    [found] = ical.parsed(
        _single(
            "CONFERENCE;VALUE=URI;FEATURE=PHONE;LABEL=Telefon:tel:+38512345678",
            "CONFERENCE;VALUE=URI;FEATURE=AUDIO,VIDEO:https://ponistra.example.com/meet/a1",
        )
    )
    assert found.conference == "https://ponistra.example.com/meet/a1"
    assert found.extra == ["CONFERENCE;FEATURE=PHONE;LABEL=Telefon;VALUE=URI:tel:+38512345678"]
    kept = events.made(own, found)
    [again] = ical.parsed(events.written(kept))
    assert again.fields == found.fields

    kept.conference = ""
    kept.save()
    written = events.written(kept)
    assert "meet/a1" not in written and "tel:+38512345678" in written


def test_a_teams_or_google_meeting_is_joined_by_the_link_their_own_property_carries():
    [teams] = ical.parsed(
        _single("X-MICROSOFT-SKYPETEAMSMEETINGURL:https://teams.microsoft.com/l/meetup-join/19")
    )
    [google] = ical.parsed(_single("X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij"))
    [neither] = ical.parsed(_single("LOCATION:Soba 3"))
    assert teams.conference == "https://teams.microsoft.com/l/meetup-join/19"
    assert google.conference == "https://meet.google.com/abc-defg-hij"
    assert neither.conference == ""


ZOOM = "https://us02web.zoom.us/j/89495449551?pwd=YjPudsCwwislgJUQzkNNafkHcSUPYC.1"
ZOOM_SERIES = (
    "Download and import the following iCalendar (.ics) files to your calendar system.\n"
    "Weekly: https://us02web.zoom.us/meeting/tZ0pfuysqj/ics?icsToken=DIngYf&meetingMasterEventId=LO\n"
    f"Join Zoom Meeting\n{ZOOM}\n\n"
    "Find your local number: https://us02web.zoom.us/u/kc3FmCso1W"
)


def test_an_invitation_giving_its_meeting_only_in_words_is_joined_by_the_link_that_joins_it(own):
    kept = events.made(own, ical.Found(summary="Tehnološki sastanak", description=ZOOM_SERIES))
    ours = f"{settings.PUBLIC_URL}/meet/{uuid.uuid4()}"
    assert kept.conference == ZOOM
    assert ical.meeting_in("Soba 3", f"Pridružite se ({ours}).") == ours
    assert ical.meeting_in("https://meet.google.com/abc-defg-hij?hs=1, Soba 3") == (
        "https://meet.google.com/abc-defg-hij?hs=1"
    )
    assert (
        ical.meeting_in("https://example.com/j/1", "https://zoom.us/meetings/1/invitations") == ""
    )


def test_a_way_in_its_words_gave_follows_them_and_one_given_apart_stays(own):
    kept = events.made(own, ical.Found(summary="Kolegij", description=ZOOM_SERIES))
    teams = "https://teams.microsoft.com/l/meetup-join/19"
    moved = events.saved(kept, replace(events.found_of(kept), description=f"Teams: {teams}"))
    assert moved.conference == teams
    gone = events.saved(moved, replace(events.found_of(moved), description="Soba 3"))
    assert gone.conference == ""
    given = events.saved(gone, replace(events.found_of(gone), conference=ZOOM))
    again = events.saved(given, replace(events.found_of(given), description=f"Teams: {teams}"))
    assert again.conference == ZOOM


def series_with_days_off(own, day_off: str) -> ical.Found:
    found = ical.Found(
        summary="Kolegij",
        starts=datetime(2026, 1, 1, 8, tzinfo=UTC),
        ends=datetime(2026, 1, 1, 9, tzinfo=UTC),
        zone="Europe/Zagreb",
        rrule="FREQ=MONTHLY;COUNT=6",
        exdates=["2026-06-01T07:00:00+00:00"],
        day_off=day_off,
    )
    events.made(own, found)
    return found


def test_days_off_reach_a_phone_as_dates_taken_out_and_come_back_as_the_way_alone(own):
    found = series_with_days_off(own, "skip")
    written = events.written(own.events.get())
    assert "X-PONISTRA-DAY-OFF:SKIP" in written
    assert "EXDATE;TZID=Europe/Zagreb:20260101T090000,20260201T090000" in written
    master, *overrides = ical.parsed(written)
    assert overrides == []
    assert master.day_off == "skip" and master.exdates == found.exdates


def test_days_off_reach_a_phone_as_occurrences_moved_and_come_back_as_the_way_alone(own):
    found = series_with_days_off(own, "after")
    written = events.written(own.events.get())
    assert "X-PONISTRA-DAY-OFF:AFTER" in written
    assert written.count("X-PONISTRA-DAY-OFF:MOVED") == 4
    assert "RECURRENCE-ID;TZID=Europe/Zagreb:20260501T090000" in written
    assert "DTSTART;TZID=Europe/Zagreb:20260504T090000" in written
    assert [each.fields for each in ical.parsed(written)] == [found.fields]

    _, invited = ical.imip(written)
    assert [each.day_off for each in invited] == [""] * 5
    assert [each.starts.date().isoformat() for each in invited[1:]] == [
        "2026-01-02",
        "2026-02-02",
        "2026-03-02",
        "2026-05-04",
    ]
