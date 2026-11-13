import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from apps.calendar import taking
from apps.calendar.models import Booking, Resource
from apps.mail.models import Away
from apps.users.models import User

pytestmark = pytest.mark.django_db

ZONE = "zone=Europe/Zagreb"


def event(client, pk=None, **data):
    body = json.dumps(data)
    if pk is None:
        return client.post(f"/api/calendar/events?{ZONE}", body, content_type="application/json")
    return client.patch(f"/api/calendar/events/{pk}?{ZONE}", body, content_type="application/json")


def free(client, start, end, **query):
    asked = "&".join(f"{key}={value}" for key, value in query.items())
    return client.get(f"/api/calendar/free?{ZONE}&start={start}&end={end}&{asked}").json()


@pytest.fixture
def room():
    return Resource.objects.create(name="Velika dvorana", kind="room", capacity=12, place="2. kat")


@pytest.fixture
def ana():
    user = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71", first_name="Ana")
    taking.own(user.pk, "Ana")
    return user


def test_an_administrator_keeps_the_rooms_and_everyone_sees_the_ones_in_use(signed_in, owner):
    made = signed_in.post(
        "/api/calendar/resources",
        json.dumps({"name": "Projektor", "kind": "equipment"}),
        content_type="application/json",
    )
    assert made.status_code == 403
    owner.is_staff = True
    owner.save()
    made = signed_in.post(
        "/api/calendar/resources",
        json.dumps({"name": "Projektor", "kind": "equipment"}),
        content_type="application/json",
    )
    assert made.status_code == 201
    pk = made.json()["id"]
    twice = signed_in.post(
        "/api/calendar/resources",
        json.dumps({"name": "Projektor", "kind": "equipment"}),
        content_type="application/json",
    )
    assert twice.status_code == 409 and twice.json()["error"] == "resource_name_taken"
    retired = signed_in.patch(
        f"/api/calendar/resources/{pk}",
        json.dumps({"active": False, "place": "Ormar"}),
        content_type="application/json",
    )
    assert retired.json()["active"] is False and retired.json()["place"] == "Ormar"
    listed = signed_in.get("/api/calendar/resources").json()["resources"]
    assert [each["name"] for each in listed] == ["Projektor"]
    owner.is_staff = False
    owner.save()
    assert signed_in.get("/api/calendar/resources").json()["resources"] == []
    assert signed_in.get(
        "/api/calendar/free?start=2026-11-03T09:00&end=2026-11-03T10:00"
    ).json() == {
        "people": {},
        "away": {},
        "resources": {},
    }


def test_a_room_is_booked_by_the_event_and_not_twice_for_one_moment(signed_in, own, room, ana):
    first = event(
        signed_in,
        calendar=own.pk,
        summary="Kolegij",
        start="2026-11-03T09:00",
        end="2026-11-03T10:00",
        resources=[room.pk],
    )
    assert first.status_code == 201 and first.json()["resources"] == [room.pk]
    assert free(signed_in, "2026-11-03T09:30", "2026-11-03T11:00", resources=room.pk) == {
        "people": {},
        "away": {},
        "resources": {str(room.pk): "busy"},
    }
    assert free(signed_in, "2026-11-03T10:00", "2026-11-03T11:00", resources=room.pk)[
        "resources"
    ] == {str(room.pk): "free"}
    colleague = signed_in.__class__()
    colleague.force_login(ana)
    theirs = colleague.get("/api/calendar").json()["calendars"][0]["id"]
    clash = event(
        colleague,
        calendar=theirs,
        summary="Prezentacija",
        start="2026-11-03T09:30",
        end="2026-11-03T10:30",
        resources=[room.pk],
    )
    assert clash.status_code == 409 and clash.json()["error"] == "resource_taken"
    assert not Booking.objects.filter(event__summary="Prezentacija").exists()
    later = event(
        colleague,
        calendar=theirs,
        summary="Prezentacija",
        start="2026-11-03T10:00",
        end="2026-11-03T11:00",
        resources=[room.pk],
    )
    assert later.status_code == 201
    window = colleague.get(
        f"/api/calendar/events?{ZONE}&from=2026-11-03&to=2026-11-03&resources={room.pk}"
    ).json()
    assert [(each["by"], each["summary"], each["start"]) for each in window["bookings"]] == [
        ("Ivo Bošković", "Kolegij", "2026-11-03T09:00:00+01:00"),
        ("Ana", "Prezentacija", "2026-11-03T10:00:00+01:00"),
    ]
    moved = event(signed_in, first.json()["id"], start="2026-11-03T09:30", end="2026-11-03T10:30")
    assert moved.status_code == 409
    freed = event(signed_in, first.json()["id"], resources=[])
    assert freed.status_code == 200 and freed.json()["resources"] == []
    moved = event(signed_in, first.json()["id"], start="2026-11-03T09:30", end="2026-11-03T10:30")
    assert moved.status_code == 200


def test_a_series_holds_the_room_each_week_and_one_occurrence_can_let_it_go(
    signed_in, own, room, ana
):
    weekly = event(
        signed_in,
        calendar=own.pk,
        summary="Tjedni",
        start="2026-11-02T08:00",
        end="2026-11-02T09:00",
        rrule="FREQ=WEEKLY;COUNT=10",
        resources=[room.pk],
    ).json()
    assert free(signed_in, "2026-11-16T08:30", "2026-11-16T09:30", resources=room.pk)[
        "resources"
    ] == {str(room.pk): "busy"}
    this = signed_in.patch(
        f"/api/calendar/events/{weekly['id']}?{ZONE}&scope=this&recurrence_id=2026-11-16T08:00",
        json.dumps({"resources": []}),
        content_type="application/json",
    )
    assert this.status_code == 200 and this.json()["resources"] == []
    assert free(signed_in, "2026-11-16T08:30", "2026-11-16T09:30", resources=room.pk)[
        "resources"
    ] == {str(room.pk): "free"}
    assert free(signed_in, "2026-11-23T08:30", "2026-11-23T09:30", resources=room.pk)[
        "resources"
    ] == {str(room.pk): "busy"}
    kept = signed_in.patch(
        f"/api/calendar/events/{weekly['id']}?{ZONE}&scope=this&recurrence_id=2026-11-23T08:00",
        json.dumps({"summary": "Tjedni, dulji", "end": "2026-11-23T10:00"}),
        content_type="application/json",
    )
    assert kept.status_code == 200 and kept.json()["resources"] == [room.pk]
    following = signed_in.patch(
        f"/api/calendar/events/{weekly['id']}?{ZONE}&scope=following&recurrence_id=2026-12-07T08:00",
        json.dumps({"start": "2026-12-07T11:00", "end": "2026-12-07T12:00"}),
        content_type="application/json",
    )
    assert following.status_code == 200 and following.json()["resources"] == [room.pk]
    assert free(signed_in, "2026-12-14T11:00", "2026-12-14T12:00", resources=room.pk)[
        "resources"
    ] == {str(room.pk): "busy"}


def test_colleagues_of_the_installation_show_as_busy_by_their_own_calendars(signed_in, own, ana):
    colleague = signed_in.__class__()
    colleague.force_login(ana)
    theirs = colleague.get("/api/calendar").json()["calendars"][0]["id"]
    event(
        colleague,
        calendar=theirs,
        summary="Zauzeta",
        start="2026-11-03T09:00",
        end="2026-11-03T10:00",
    )
    event(
        colleague,
        calendar=theirs,
        summary="Slobodna, samo podsjetnik",
        start="2026-11-03T14:00",
        end="2026-11-03T15:00",
        busy=False,
    )
    asked = "ana@example.com,Ivo@Example.com,nobody@example.org"
    assert free(signed_in, "2026-11-03T09:30", "2026-11-03T10:30", people=asked)["people"] == {
        "ana@example.com": "busy",
        "ivo@example.com": "free",
        "nobody@example.org": "unknown",
    }
    assert free(signed_in, "2026-11-03T14:00", "2026-11-03T15:00", people="ana@example.com")[
        "people"
    ] == {"ana@example.com": "free"}
    mine = event(
        signed_in, calendar=own.pk, summary="Moj", start="2026-11-03T09:00", end="2026-11-03T10:00"
    ).json()
    assert free(signed_in, "2026-11-03T09:00", "2026-11-03T10:00", people="ivo@example.com")[
        "people"
    ] == {"ivo@example.com": "busy"}
    apart = free(
        signed_in,
        "2026-11-03T09:00",
        "2026-11-03T10:00",
        people="ivo@example.com",
        **{"except": mine["id"]},
    )
    assert apart["people"] == {"ivo@example.com": "free"}


def test_the_first_times_everyone_and_the_room_are_free_are_offered(signed_in, own, ana, room):
    colleague = signed_in.__class__()
    colleague.force_login(ana)
    theirs = colleague.get("/api/calendar").json()["calendars"][0]["id"]
    event(colleague, calendar=theirs, summary="A", start="2030-06-03T08:00", end="2030-06-03T10:00")
    event(signed_in, calendar=own.pk, summary="B", start="2030-06-03T10:30", end="2030-06-03T11:00")
    event(
        colleague,
        calendar=theirs,
        summary="Dvorana",
        start="2030-06-03T11:00",
        end="2030-06-03T12:00",
        busy=False,
        resources=[room.pk],
    )
    asked = {"people": "ana@example.com,nobody@example.org", "resources": room.pk, "offers": 1}
    found = free(signed_in, "2030-06-03T09:00", "2030-06-03T10:00", **asked)
    assert found["people"]["nobody@example.org"] == "unknown"
    assert [each["start"][:16] for each in found["offers"]] == [
        "2030-06-03T12:00",
        "2030-06-03T13:00",
        "2030-06-03T14:00",
        "2030-06-03T15:00",
        "2030-06-04T08:00",
        "2030-06-04T09:00",
    ]
    assert found["offers"][0]["end"] == "2030-06-03T13:00:00+02:00"
    Away.objects.create(
        owner=ana,
        starts_at=datetime(2030, 6, 4, tzinfo=ZoneInfo("Europe/Zagreb")),
        ends_at=datetime(2030, 6, 5, tzinfo=ZoneInfo("Europe/Zagreb")),
    )
    found = free(signed_in, "2030-06-03T15:30", "2030-06-03T17:30", **asked)
    assert [each["start"][:16] for each in found["offers"]][:3] == [
        "2030-06-03T12:00",
        "2030-06-03T14:00",
        "2030-06-05T08:00",
    ]
    assert "offers" not in free(signed_in, "2030-06-03T09:00", "2030-06-03T10:00")
