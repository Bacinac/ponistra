import json
from datetime import UTC, datetime

import pytest
from django.test import Client

from apps.calendar import events, taking
from apps.calendar.ical import Found
from apps.calendar.models import Calendar, Event
from apps.calendar.tests.test_invitations import ORGANIZER, carried, delivered, inbox, mailed
from apps.calendar.tests.test_recurrence import at
from apps.users.app_passwords import digest, made
from apps.users.models import AppPassword

pytestmark = pytest.mark.django_db

__all__ = ["delivered", "inbox"]


@pytest.fixture
def handset(owner):
    secret = made()
    AppPassword.objects.create(user=owner, name="Samsung SM-S926B", digest=digest(secret))
    return Client(enforce_csrf_checks=True, headers={"Authorization": f"Bearer {secret}"})


def millis(text: str) -> int:
    return round(at(text).timestamp() * 1000)


def kolegij(own, **more) -> Event:
    given = {
        "summary": "Kolegij",
        "starts": at("2026-11-03T09:00:00+01:00"),
        "ends": at("2026-11-03T10:00:00+01:00"),
        "zone": "Europe/Zagreb",
        "conference": "https://meet.example.com/kolegij",
    }
    return events.made(own, Found(**{**given, **more}), href="kolegij.ics")


def written(handset, own, href, parts, revision=None, status=200):
    answer = handset.put(
        f"/api/device/calendars/{own.pk}/{href}",
        json.dumps({"revision": revision, "language": "hr", "parts": parts}),
        content_type="application/json",
    )
    assert answer.status_code == status, answer.content
    return answer.json() if answer.content else None


def test_the_phone_lists_the_calendars_with_how_far_each_has_come(owner, own, handset):
    event = kolegij(own)
    taking.own(owner.pk, "Obitelj")
    listed = handset.get("/api/device/calendars").json()["calendars"]
    assert [(each["name"], each["read_only"], each["owner"]) for each in listed] == [
        ("Moj", False, "ivo@example.com"),
        ("Obitelj", False, "ivo@example.com"),
    ]
    assert listed[0]["revision"] == event.revision and listed[1]["revision"] == 0
    assert all(each["color"].startswith("#") for each in listed)


def test_only_the_phones_own_app_reads_the_calendars_this_way(signed_in):
    assert signed_in.get("/api/device/calendars").status_code == 403


def test_the_phone_reads_the_whole_calendar_then_what_changed_since(own, handset):
    first = kolegij(own, rrule="FREQ=WEEKLY;COUNT=3", reminders=[15])
    whole = handset.get(f"/api/device/calendars/{own.pk}").json()
    ((series,),) = [whole["events"]]
    assert (series["href"], series["revision"], whole["gone"]) == (
        "kolegij.ics",
        first.revision,
        [],
    )
    (part,) = series["parts"]
    assert part["recurrence_id"] is None and part["zone"] == "Europe/Zagreb"
    assert part["starts"] == millis("2026-11-03T09:00:00+01:00")
    assert (part["rrule"], part["reminders"], part["summary"]) == (
        "FREQ=WEEKLY;COUNT=3",
        [15],
        "Kolegij",
    )
    since = whole["revision"]
    assert handset.get(f"/api/device/calendars/{own.pk}?since={since}").json()["events"] == []

    override = Found(
        summary="Kolegij u velikoj sobi",
        starts=at("2026-11-10T11:00:00+01:00"),
        ends=at("2026-11-10T12:00:00+01:00"),
        zone="Europe/Zagreb",
        recurrence_id=at("2026-11-10T09:00:00+01:00"),
    )
    events.made(own, override, master=first)
    events.deleted(events.made(own, Found(summary="Ručak"), href="rucak.ics"))
    changed = handset.get(f"/api/device/calendars/{own.pk}?since={since}").json()
    ((series,),) = [changed["events"]]
    assert [each["summary"] for each in series["parts"]] == ["Kolegij", "Kolegij u velikoj sobi"]
    assert series["parts"][1]["recurrence_id"] == millis("2026-11-10T09:00:00+01:00")
    assert changed["gone"] == ["rucak.ics"] and changed["revision"] > since
    assert (
        handset.get(f"/api/device/calendars/{own.pk}?since={changed['revision'] + 1}").status_code
        == 410
    )


def test_the_phone_makes_an_event_under_its_own_href(own, handset):
    part = {
        "recurrence_id": None,
        "summary": "Zubar",
        "all_day": False,
        "starts": millis("2026-11-05T15:00:00+01:00"),
        "ends": millis("2026-11-05T15:30:00+01:00"),
        "zone": "Europe/Zagreb",
        "rrule": "",
        "rdates": [],
        "exdates": [],
        "status": "confirmed",
        "busy": True,
        "private": False,
        "attendees": [],
        "reminders": [30, 30, 10],
        "response": "",
    }
    served = written(handset, own, "zubar.ics", [part], status=201)
    event = Event.objects.get(href="zubar.ics")
    assert (event.summary, event.zone, event.reminders, event.organizer) == (
        "Zubar",
        "Europe/Zagreb",
        [10, 30],
        {},
    )
    assert event.uid.endswith("@ponistra") and served["revision"] == event.revision


def test_an_all_day_event_keeps_its_days_and_its_exceptions(own, handset):
    part = {
        "summary": "Godišnji",
        "all_day": True,
        "starts": millis("2026-12-21T00:00:00+00:00"),
        "ends": millis("2026-12-21T00:00:00+00:00"),
        "rrule": "FREQ=DAILY;COUNT=5",
        "exdates": [millis("2026-12-23T00:00:00+00:00")],
    }
    served = written(handset, own, "godisnji.ics", [part], status=201)
    event = Event.objects.get(href="godisnji.ics")
    assert (event.all_day, event.exdates) == (True, ["2026-12-23"])
    assert event.ends - event.starts == datetime(2026, 1, 2, tzinfo=UTC) - datetime(
        2026, 1, 1, tzinfo=UTC
    )
    assert served["parts"][0]["exdates"] == [millis("2026-12-23T00:00:00+00:00")]


def test_the_phone_writes_over_only_the_revision_it_read_and_what_only_ponistra_holds_stays(
    own, handset
):
    event = kolegij(own, extra=["X-OWN:1"])
    series = handset.get(f"/api/device/calendars/{own.pk}").json()["events"][0]
    part = {**series["parts"][0], "summary": "Kolegij uprave", "location": "Ured"}
    served = written(handset, own, "kolegij.ics", [part], revision=series["revision"])
    held = Event.objects.get(pk=event.pk)
    assert (held.summary, held.location, held.conference, held.extra) == (
        "Kolegij uprave",
        "Ured",
        "https://meet.example.com/kolegij",
        ["X-OWN:1"],
    )
    written(handset, own, "kolegij.ics", [part], revision=series["revision"], status=412)
    written(handset, own, "nema.ics", [part], revision=served["revision"], status=404)


def test_a_series_moved_by_its_days_off_comes_back_as_its_rule_alone(own, handset):
    master = kolegij(
        own,
        starts=at("2026-12-18T09:00:00+01:00"),
        ends=at("2026-12-18T10:00:00+01:00"),
        rrule="FREQ=WEEKLY;COUNT=4",
        day_off="after",
    )
    series = handset.get(f"/api/device/calendars/{own.pk}").json()["events"][0]
    moved = [each for each in series["parts"] if each["day_off"] == "moved"]
    assert moved and series["parts"][0]["day_off"] == "after"
    written(handset, own, "kolegij.ics", series["parts"], revision=series["revision"])
    held = Event.objects.get(pk=master.pk)
    assert held.day_off == "after" and held.overrides.count() == 0


def test_the_phone_deletes_only_the_revision_it_read(own, handset):
    event = kolegij(own)
    url = f"/api/device/calendars/{own.pk}/kolegij.ics"
    assert handset.delete(f"{url}?revision={event.revision - 1}").status_code == 412
    assert handset.delete(f"{url}?revision={event.revision}").status_code == 204
    assert not Event.objects.filter(pk=event.pk).exists()
    assert handset.delete(f"{url}?revision={event.revision}").status_code == 404


def test_an_organisations_calendar_is_read_only_on_the_phone(owner, account, handset):
    calendar = Calendar.objects.create(
        owner=owner, kind=Calendar.Kind.ORGANISATION, name="Brezik", account=account
    )
    events.made(calendar, Found(summary="Kolegij"), href="k.ics")
    listed = handset.get("/api/device/calendars").json()["calendars"]
    assert [(each["read_only"], each["owner"]) for each in listed] == [(True, account.address)]
    part = handset.get(f"/api/device/calendars/{calendar.pk}").json()["events"][0]["parts"][0]
    answer = handset.put(
        f"/api/device/calendars/{calendar.pk}/k.ics",
        json.dumps({"revision": None, "parts": [part]}),
        content_type="application/json",
    )
    assert answer.status_code == 403


def test_a_meeting_the_user_calls_on_the_phone_reaches_its_attendees(
    own, inbox, handset, delivered
):
    part = {
        "summary": "Kolegij",
        "starts": millis("2026-11-03T09:00:00+01:00"),
        "ends": millis("2026-11-03T10:00:00+01:00"),
        "zone": "Europe/Zagreb",
        "attendees": [
            {"email": "ivo@example.com", "name": "Ivo", "status": "accepted"},
            {"email": ORGANIZER, "name": "Ana", "status": "needs-action"},
        ],
    }
    served = written(handset, own, "kolegij.ics", [part], status=201)
    event = Event.objects.get(href="kolegij.ics")
    assert (event.response, [each["email"] for each in event.attendees]) == (
        "organizer",
        [ORGANIZER],
    )
    assert [each[1]["Subject"] for each in delivered] == ["Poziv: Kolegij"]
    delivered.clear()

    moved = {**served["parts"][0], "starts": millis("2026-11-03T11:00:00+01:00")}
    moved["ends"] = millis("2026-11-03T12:00:00+01:00")
    written(handset, own, "kolegij.ics", [moved], revision=served["revision"])
    assert [each[1]["Subject"] for each in delivered] == ["Ažurirano: Kolegij"]
    assert carried(delivered[0][1])[1] == "REQUEST"


def test_the_users_answer_on_the_phone_reaches_whoever_asked(owner, inbox, handset, delivered):
    mailed(inbox, "REQUEST")
    event = Event.objects.get()
    calendar = event.calendar
    series = handset.get(f"/api/device/calendars/{calendar.pk}").json()["events"][0]
    part = series["parts"][0]
    assert (part["response"], part["organizer"]["email"]) == ("needs-action", ORGANIZER)
    answered = {**part, "response": "accepted", "attendees": [], "summary": "Moj kolegij"}
    served = written(handset, calendar, event.href, [answered], revision=series["revision"])
    held = Event.objects.get(pk=event.pk)
    assert (held.response, held.organizer["email"], held.summary) == (
        "accepted",
        ORGANIZER,
        "Moj kolegij",
    )
    assert [each["email"] for each in held.attendees] == ["ivo@example.com"]
    assert served["parts"][0]["response"] == "accepted"
    ((_, message),) = delivered
    assert message["Subject"] == "Prihvaćeno: Kolegij"
