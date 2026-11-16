from datetime import datetime

import pytest
from django.test import Client

from apps.actions.models import ActionRun
from apps.workspace.models import Limits, Spend, Stretch, Transcript
from apps.workspace.spend import summed
from apps.workspace.worked import CLOCKIFY, Found, Spent, hours, kept

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
        "read": {f"{HERE}/{CHAT}": 4096},
        "last": {},
        "removal": None,
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


def spent(hour: str, model: str = "claude-opus-5-5", tokens: int = 1000) -> Spent:
    return Spent(at(hour), model, 1, tokens, tokens, tokens, tokens)


def tokens(**where) -> int:
    return sum(Spend.objects.filter(**where).values_list("input", flat=True))


def test_tokens_count_once_from_where_the_reading_began_at_the_mark():
    hour = "2026-11-12T08:00:00"
    kept(HERE, CHAT, "ponistra", 100, [], Found(origin=0, last="msg_1", spent=[spent(hour)]))
    # Told again after its answer was lost: the reading began before the mark.
    kept(HERE, CHAT, "ponistra", 100, [], Found(origin=0, last="msg_1", spent=[spent(hour)]))
    kept(HERE, CHAT, "ponistra", 200, [], Found(origin=100, last="msg_2", spent=[spent(hour)]))
    assert tokens() == 2000
    transcript = Transcript.objects.get()
    assert (transcript.read, transcript.last, transcript.chat) == (200, "msg_2", CHAT)


def test_a_copy_counts_its_tokens_only_for_a_transcript_not_known_before():
    kept(HERE, CHAT, "ponistra", None, [], Found(spent=[spent("2026-11-12T08:00:00")]))
    kept(HERE, CHAT, "ponistra", None, [], Found(spent=[spent("2026-11-12T08:00:00")]))
    assert tokens() == 1000


def test_an_agents_tokens_belong_to_its_chat_and_each_round_keeps_its_own():
    agent = f"{CHAT}-a327d22ee4ed4e98f"
    hour = "2026-11-12T08:00:00"
    kept(HERE, CHAT, "ponistra", 10, [], Found(chat=CHAT, title="Izvoz", spent=[spent(hour)]))
    kept(HERE, agent, "ponistra", 10, [], Found(chat=CHAT, round="r1", spent=[spent(hour)]))
    shown = summed("2026-11")
    assert [(each["chat"], each["title"], each["input"]) for each in shown["chats"]] == [
        (CHAT, "Izvoz", 2000)
    ]
    assert [(each["round"], each["input"]) for each in shown["rounds"]] == [("r1", 1000)]


def test_the_spend_is_worth_the_apis_prices_and_names_the_models_without_one():
    kept(
        HERE,
        CHAT,
        "ponistra",
        10,
        [],
        Found(
            spent=[
                Spent(at("2026-11-12T08:00:00"), "claude-opus-5-5", 3, 1_000_000, 0, 0, 0),
                spent("2026-11-12T09:00:00", "claude-fable-5-2"),
            ]
        ),
    )
    ActionRun.objects.create(action="text.summarise", target={}, cost="0.25")
    shown = summed()
    [month] = [each for each in shown["months"] if each["month"] == "2026-11"]
    assert (month["worth"], month["unpriced"], month["turns"]) == (4.0, ["claude-fable-5-2"], 4)
    assert [each["name"] for each in shown["models"]] == ["claude-opus-5-5", "claude-fable-5-2"]
    assert day(shown, "2026-11-12")["worth"] == 4.0


def test_the_week_reads_as_percent_per_dollar_spent_in_its_window():
    kept(
        HERE,
        CHAT,
        "ponistra",
        10,
        [],
        Found(spent=[Spent(at("2026-11-12T08:00:00"), "claude-opus-5-5", 1, 1_000_000, 0, 0, 0)]),
    )
    week = {"kind": "week", "name": None, "percent": 20, "resets": "2026-11-15T09:00:00+00:00"}
    session = {"kind": "session", "name": None, "percent": 5, "resets": "2026-11-12T12:00:00+00:00"}
    Limits.objects.create(at=at("2026-11-12T10:00:00"), windows=[session, week])
    shown = summed("2026-11")
    assert shown["rate"] == 5.0
    assert shown["limits"] == [{"at": "2026-11-12T10:00:00+00:00", "session": 5, "week": 20}]


@pytest.mark.parametrize(
    "spent, error",
    [
        ([{"hour": 1, "model": "claude-opus-5-5"}], "invalid_spent"),
        ([{"hour": 3_600_000, "model": "a b"}], "invalid_spent"),
        ([{"hour": 3_600_000, "model": "m", "input": -1}], "invalid_spent"),
        ([{"hour": 3_600_000, "model": "m"}, {"hour": 3_600_000, "model": "m"}], "invalid_spent"),
    ],
)
def test_the_tokens_told_are_checked(client, settings, spent, error):
    settings.WORKSPACE_TOKEN = "token"
    sent = {"transcripts": [{"namespace": HERE, "session": CHAT, "stretches": [], "spent": spent}]}
    response = client.post("/api/workspace/worked", sent, JSON, HTTP_AUTHORIZATION="Bearer token")
    assert (response.status_code, response.json()) == (400, {"error": error})


def test_the_workspace_keeps_the_limits_each_time_they_change(client, settings):
    settings.WORKSPACE_TOKEN = "token"
    week = {"kind": "week", "name": None, "percent": 41, "resets": "2026-11-15T09:00:00Z"}
    limits = {"at": "2026-11-12T10:00:00.000Z", "windows": [week], "credits": None}
    for given in (limits, limits, {**limits, "windows": [{"kind": "year"}]}):
        response = client.post(
            "/api/workspace/changed", {"limits": given}, JSON, HTTP_AUTHORIZATION="Bearer token"
        )
        assert response.status_code == 204
    [kept_limits] = Limits.objects.all()
    assert kept_limits.windows[0]["percent"] == 41


def test_only_the_owner_reads_the_spend(api, settings):
    settings.WORKSPACE = "owner@example.com"
    assert api.get("/api/workspace/spend").status_code == 403
    settings.WORKSPACE = api.user.email
    assert api.get("/api/workspace/spend?month=2026-11").json()["month"] == "2026-11"
    assert api.get("/api/workspace/spend?month=11").status_code == 400
