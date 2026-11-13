from datetime import datetime

import pytest
from django.test import Client

from apps.workspace.models import Stretch, Transcript
from apps.workspace.worked import CLOCKIFY, hours, kept

pytestmark = pytest.mark.django_db

JSON = "application/json"
CHAT = "5bd35ed2-cbe6-4cab-9778-7e292e258673"
OTHER = "0244db82-f45d-4599-bad9-2c61f5d5463c"
HERE = "-work-ponistra"


def at(text: str) -> datetime:
    return datetime.fromisoformat(f"{text}+00:00")


def ms(text: str) -> int:
    return int(at(text).timestamp() * 1000)


def span(began: str, ended: str):
    return (at(began), at(ended))


def day(listed: dict, wanted: str) -> dict:
    return next(each for each in listed["days"] if each["day"] == wanted)


def test_chats_of_one_project_join_across_a_short_pause_and_projects_each_count_in_full():
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    kept(HERE, OTHER, "ponistra", 10, [span("2026-11-12T09:15:00", "2026-11-12T10:00:00")])
    kept("-work-dida", CHAT, "dida", 10, [span("2026-11-12T09:30:00", "2026-11-12T11:00:00")])
    kept(HERE, "1", "ponistra", 10, [span("2026-11-12T10:15:01", "2026-11-12T10:30:00")])
    worked = day(hours(), "2026-11-12")
    assert worked["projects"] == {"ponistra": 2 * 3600 + 15 * 60 - 1, "dida": 5400}
    assert worked["total"] == 2 * 3600 + 15 * 60 - 1 + 5400
    assert worked["wall"] == 3 * 3600


def test_a_moment_alone_counts_as_the_least_block():
    kept(HERE, CHAT, "", 10, [span("2026-11-12T08:00:00", "2026-11-12T08:00:00")])
    assert day(hours(), "2026-11-12")["projects"] == {"": 120}


def test_a_block_counts_on_the_installations_day_it_began():
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T22:50:00", "2026-11-12T23:30:00")])
    listed = hours()
    assert [each["day"] for each in listed["days"]] == ["2026-11-12"]
    assert listed["days"][0]["projects"] == {"ponistra": 2400}


def test_a_transcript_read_again_counts_once_and_grows_where_it_was_read_to():
    first = [span("2026-11-12T08:00:00", "2026-11-12T08:30:00")]
    kept(HERE, CHAT, "ponistra", 100, first)
    kept(HERE, CHAT, "ponistra", 100, first)
    kept(HERE, CHAT, "ponistra", 200, [span("2026-11-12T08:40:00", "2026-11-12T09:00:00")])
    assert list(Stretch.objects.values_list("began", "ended")) == [
        span("2026-11-12T08:00:00", "2026-11-12T09:00:00")
    ]
    kept(HERE, CHAT, "ponistra", None, [span("2026-11-12T07:00:00", "2026-11-12T07:10:00")])
    assert Transcript.objects.get().read == 200
    assert Stretch.objects.count() == 2


def test_clockify_stands_for_its_projects_day_and_the_transcripts_for_the_rest():
    kept(CLOCKIFY, "a1", "dvokut", None, [span("2026-10-01T08:00:00", "2026-10-01T10:00:00")])
    kept(HERE, CHAT, "dvokut", 10, [span("2026-10-01T09:00:00", "2026-10-01T12:00:00")])
    kept(HERE, OTHER, "ponistra", 10, [span("2026-10-01T09:00:00", "2026-10-01T09:30:00")])
    kept(HERE, "1", "dvokut", 10, [span("2026-10-02T09:00:00", "2026-10-02T09:30:00")])
    listed = hours("2026-10")
    assert day(listed, "2026-10-01")["projects"] == {"dvokut": 7200, "ponistra": 1800}
    assert day(listed, "2026-10-02")["projects"] == {"dvokut": 1800}
    assert listed["months"] == [
        {
            "month": "2026-10",
            "projects": {"dvokut": 9000, "ponistra": 1800},
            "total": 10800,
            "wall": 9000,
        }
    ]


def test_one_month_is_shown_by_day_the_latest_unless_named():
    kept(HERE, CHAT, "ponistra", 10, [span("2026-10-12T08:00:00", "2026-10-12T09:00:00")])
    kept(HERE, OTHER, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    assert [each["day"] for each in hours()["days"]] == ["2026-11-12"]
    assert [each["day"] for each in hours("2026-10")["days"]] == ["2026-10-12"]
    assert hours("2025-01")["month"] == "2026-11"
    assert [each["month"] for each in hours()["months"]] == ["2026-11", "2026-10"]


def test_the_workspace_says_what_it_found_and_hears_how_far_it_read(client, settings):
    settings.WORKSPACE_TOKEN = "token"
    sent = {
        "transcripts": [
            {
                "namespace": HERE,
                "session": CHAT,
                "project": "ponistra",
                "read": 4096,
                "stretches": [[ms("2026-11-12T08:00:00"), ms("2026-11-12T08:30:00.250")]],
            },
            {
                "namespace": CLOCKIFY,
                "session": "6a0c367570fe28c08131ed2d",
                "project": "taskstreamer",
                "read": None,
                "stretches": [[ms("2026-05-04T08:00:00"), ms("2026-05-04T09:00:00")]],
            },
        ]
    }
    worked = "/api/workspace/worked"
    response = client.post(worked, sent, JSON, HTTP_AUTHORIZATION="Bearer token")
    assert response.status_code == 204
    assert client.get(worked, HTTP_AUTHORIZATION="Bearer token").json() == {
        "read": {f"{HERE}/{CHAT}": 4096}
    }
    assert Stretch.objects.get(transcript__namespace=HERE).ended == at("2026-11-12T08:30:00.250")


@pytest.mark.parametrize(
    "transcript, error",
    [
        ({"namespace": "/work", "session": CHAT, "stretches": []}, "invalid_namespace"),
        ({"namespace": HERE, "session": "../x", "stretches": []}, "invalid_session"),
        (
            {"namespace": HERE, "session": CHAT, "project": "a/b", "stretches": []},
            "invalid_project",
        ),
        ({"namespace": HERE, "session": CHAT, "read": -1, "stretches": []}, "invalid_read"),
        ({"namespace": HERE, "session": CHAT, "stretches": [[2, 1]]}, "invalid_stretches"),
        ({"namespace": HERE, "session": CHAT, "stretches": [[1, 2.5]]}, "invalid_stretches"),
        ({"namespace": HERE, "session": CHAT, "stretches": [[1]]}, "invalid_stretches"),
    ],
)
def test_what_the_workspace_says_is_checked_before_any_is_kept(client, settings, transcript, error):
    settings.WORKSPACE_TOKEN = "token"
    response = client.post(
        "/api/workspace/worked",
        {"transcripts": [transcript]},
        JSON,
        HTTP_AUTHORIZATION="Bearer token",
    )
    assert (response.status_code, response.json()) == (400, {"error": error})
    assert not Transcript.objects.exists()


def test_only_the_workspaces_token_reaches_what_it_measured(client, settings):
    settings.WORKSPACE_TOKEN = "token"
    assert client.get("/api/workspace/worked").status_code == 403
    assert client.get("/api/workspace/worked", HTTP_AUTHORIZATION="Bearer x").status_code == 403
    settings.WORKSPACE_TOKEN = ""
    assert client.get("/api/workspace/worked", HTTP_AUTHORIZATION="Bearer ").status_code == 403


def test_the_owner_alone_reads_the_hours(api, settings):
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    settings.WORKSPACE = "owner@example.com"
    assert api.get("/api/workspace/hours").status_code == 403
    settings.WORKSPACE = api.user.email
    assert api.get("/api/workspace/hours?month=2026-13").json() == {"error": "invalid_month"}
    listed = api.get("/api/workspace/hours?month=2026-11").json()
    assert listed["days"][0]["projects"] == {"ponistra": 3600}
    assert Client().get("/api/workspace/hours").status_code in (401, 403)
