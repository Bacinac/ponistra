import json

import jwt
import pytest

from apps.calendar import taking
from apps.meetings.livekit import KEY
from apps.meetings.models import Meeting
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )


@pytest.fixture
def signed_in(client, owner):
    client.force_login(owner)
    return client


def sent(client, method, path, **data):
    return getattr(client, method)(path, json.dumps(data), content_type="application/json")


def test_a_meeting_is_a_room_at_a_link_of_the_installation(signed_in, owner, settings):
    made = sent(signed_in, "post", "/api/meetings", title="  Dogovor   o ponudi ")
    assert made.status_code == 201
    meeting = Meeting.objects.get()
    assert made.json() == {
        "id": str(meeting.id),
        "title": "Dogovor o ponudi",
        "link": f"{settings.PUBLIC_URL}/meet/{meeting.id}",
        "conversation": str(meeting.conversation_id),
    }
    assert meeting.organizer == owner
    untitled = sent(signed_in, "post", "/api/meetings", title=" ")
    assert (untitled.status_code, untitled.json()["title"]) == (201, "")
    missing = signed_in.get("/api/meetings/0b7f6b3e-0000-4000-8000-000000000001")
    assert (missing.status_code, missing.json()) == (404, {"error": "no_meeting"})


def test_each_joining_is_a_participant_of_its_own_in_that_room_only(signed_in, settings):
    meeting = Meeting.objects.made("Kolegij")
    keys = [
        jwt.decode(
            signed_in.post(f"/api/meetings/{meeting.id}/join").json()["token"],
            settings.LIVEKIT_SECRET,
            algorithms=["HS256"],
        )
        for _ in range(2)
    ]
    assert {key["iss"] for key in keys} == {KEY}
    assert {key["name"] for key in keys} == {"Ivo Bošković"}
    assert keys[0]["sub"] != keys[1]["sub"]
    assert keys[0]["video"] == {
        "room": str(meeting.id),
        "roomJoin": True,
        "canPublish": True,
        "canSubscribe": True,
        "canPublishData": True,
    }
    assert "roomAdmin" not in keys[0]["video"]


def test_a_meeting_is_named_as_the_users_own_event_names_it_and_says_who_is_in(signed_in, owner):
    meeting = Meeting.objects.made("Sastanak")
    shown = signed_in.get(f"/api/meetings/{meeting.id}").json()
    assert (shown["title"], shown["present"]) == ("Sastanak", [])

    calendar = taking.own(owner.pk, "Moj")
    made = sent(
        signed_in,
        "post",
        "/api/calendar/events",
        calendar=calendar.pk,
        summary="Kolegij uprave",
        start="2026-11-02T09:00",
        end="2026-11-02T10:00",
        zone="Europe/Zagreb",
        conference=meeting.link,
    )
    assert made.status_code == 201 and made.json()["conference"] == meeting.link
    assert signed_in.get(f"/api/meetings/{meeting.id}").json()["title"] == "Kolegij uprave"


def test_an_event_takes_only_a_web_link_as_its_conference(signed_in, owner):
    calendar = taking.own(owner.pk, "Moj")
    refused = sent(
        signed_in,
        "post",
        "/api/calendar/events",
        calendar=calendar.pk,
        summary="Kolegij",
        start="2026-11-02T09:00",
        end="2026-11-02T10:00",
        conference="javascript:alert(1)",
    )
    assert refused.json() == {"error": "invalid_conference"}


def test_meetings_say_so_when_livekit_does_not_answer(signed_in, settings):
    settings.LIVEKIT_URL = "http://127.0.0.1:9"
    meeting = Meeting.objects.made("Kolegij")
    answer = signed_in.get(f"/api/meetings/{meeting.id}")
    assert (answer.status_code, answer.json()) == (503, {"error": "meetings_unavailable"})


def test_a_meeting_is_only_for_those_signed_in(client):
    meeting = Meeting.objects.made("Kolegij")
    assert client.get(f"/api/meetings/{meeting.id}").status_code == 401
    assert client.post(f"/api/meetings/{meeting.id}/join").status_code == 401
