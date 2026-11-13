import json
from datetime import date, datetime

import httpx2
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.core.sealed import seal
from apps.workspace import sheets
from apps.workspace.models import Removal, Sheet, Written
from apps.workspace.worked import kept

pytestmark = pytest.mark.django_db

JSON = "application/json"
OWNER = "owner@example.com"
CHAT = "5bd35ed2-cbe6-4cab-9778-7e292e258673"
HERE = "-work-ponistra"
LABEL = "Razvoj aplikacija"
NOW = datetime.fromisoformat("2026-11-14T09:00:00+00:00")


def at(text: str) -> datetime:
    return datetime.fromisoformat(f"{text}+00:00")


def span(began: str, ended: str):
    return (at(began), at(ended))


class Clockify:
    """Clockify's time entries of one user, as its API answers them."""

    def __init__(self, entries=None):
        self.entries = list(entries or [])
        self.asked: list[tuple[str, str]] = []
        self.made = 0

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path.removeprefix("/api/v1")
        self.asked.append((request.method, path))
        if path == "/user":
            return httpx2.Response(200, json={"id": "u1", "activeWorkspace": "w1"})
        if path == "/workspaces/w1/projects":
            return httpx2.Response(
                200, json=[{"id": "p1", "name": "Ponistra"}, {"id": "p2", "name": "Dida"}]
            )
        if path == "/workspaces/w1/user/u1/time-entries":
            began = datetime.fromisoformat(request.url.params["start"])
            ended = datetime.fromisoformat(request.url.params["end"])
            return httpx2.Response(
                200,
                json=[
                    each
                    for each in self.entries
                    if began <= datetime.fromisoformat(each["timeInterval"]["start"]) < ended
                ],
            )
        if request.method == "POST" and path == "/workspaces/w1/time-entries":
            given = json.loads(request.content)
            self.made += 1
            entry = {
                "id": f"new{self.made}",
                "description": given["description"],
                "projectId": given["projectId"],
                "timeInterval": {"start": given["start"], "end": given["end"]},
            }
            self.entries.append(entry)
            return httpx2.Response(201, json=entry)
        if request.method == "DELETE" and path.startswith("/workspaces/w1/time-entries/"):
            gone = path.rsplit("/", 1)[1]
            self.entries = [each for each in self.entries if each["id"] != gone]
            return httpx2.Response(200, json={})
        return httpx2.Response(404)


def entry(pk: str, project: str, start: str, end: str, description: str = LABEL) -> dict:
    return {
        "id": pk,
        "description": description,
        "projectId": project,
        "timeInterval": {"start": f"{start}Z", "end": f"{end}Z"},
    }


@pytest.fixture
def served(monkeypatch):
    def serve(answer):
        monkeypatch.setattr(
            sheets, "client", lambda: httpx2.Client(transport=httpx2.MockTransport(answer))
        )
        return answer

    return serve


@pytest.fixture
def now(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


def clockify_sheet(**given) -> Sheet:
    return Sheet.objects.create(
        kind=Sheet.Kind.CLOCKIFY,
        key=seal(sheets.SEALED, "secret"),
        space="w1",
        account="u1",
        offered=[{"id": "p1", "name": "Ponistra"}, {"id": "p2", "name": "Dida"}],
        projects={"ponistra": "p1", "dida": "p2"},
        label=LABEL,
        since=date(2026, 11, 1),
        **given,
    )


def test_a_day_is_written_once_it_settled_as_one_entry_a_project(served, now):
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    kept(HERE, "b", "ponistra", 10, [span("2026-11-12T10:00:00", "2026-11-12T10:30:00")])
    kept("-work-dida", CHAT, "dida", 10, [span("2026-11-13T08:00:00", "2026-11-13T08:30:00")])
    kept("-work-porat", CHAT, "porat", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    kept(HERE, "c", "ponistra", 10, [span("2026-11-14T07:00:00", "2026-11-14T08:00:00")])
    clockify = served(Clockify())
    sheet = clockify_sheet()
    assert sheets.write(sheet) == {"written": 2, "left": 0, "error": None}
    assert sorted(
        (
            each["projectId"],
            each["timeInterval"]["start"],
            each["timeInterval"]["end"],
            each["description"],
        )
        for each in clockify.entries
    ) == [
        ("p1", "2026-11-12T08:00:00Z", "2026-11-12T09:30:00Z", f"{LABEL} — ponistra"),
        ("p2", "2026-11-13T08:00:00Z", "2026-11-13T08:30:00Z", f"{LABEL} — dida"),
    ]
    clockify.asked.clear()
    assert sheets.write(sheet) == {"written": 0, "left": 0, "error": None}
    assert clockify.asked == []


def test_a_day_is_written_again_when_it_changed_and_what_others_entered_stays(served, now):
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    clockify = served(
        Clockify(
            [
                entry("old", "p1", "2026-11-12T08:00:00", "2026-11-12T08:20:00"),
                entry("hand", "p1", "2026-11-12T12:00:00", "2026-11-12T13:00:00", "Sastanak"),
                entry("help", "x9", "2026-11-12T14:00:00", "2026-11-12T15:00:00"),
            ]
        )
    )
    sheet = clockify_sheet()
    sheets.write(sheet)
    assert sorted(each["id"] for each in clockify.entries) == ["hand", "help", "new1"]
    kept(HERE, CHAT, "ponistra", 20, [span("2026-11-12T09:10:00", "2026-11-12T09:40:00")])
    sheets.write(sheet)
    assert sorted(each["id"] for each in clockify.entries) == ["hand", "help", "new2"]
    assert Written.objects.get().entries == ["new2"]


def test_an_entry_already_there_as_measured_is_kept(served, now):
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    clockify = served(
        Clockify(
            [
                entry(
                    "same",
                    "p1",
                    "2026-11-12T08:00:00",
                    "2026-11-12T09:00:00",
                    f"{LABEL} — ponistra",
                )
            ]
        )
    )
    sheets.write(clockify_sheet())
    assert [method for method, _ in clockify.asked] == ["GET"]
    assert Written.objects.get().entries == ["same"]


def test_days_before_the_first_and_a_block_still_growing_wait(served, monkeypatch):
    kept(HERE, CHAT, "ponistra", 10, [span("2026-10-30T08:00:00", "2026-10-30T09:00:00")])
    kept(HERE, "b", "ponistra", 10, [span("2026-11-12T22:30:00", "2026-11-12T23:05:00")])
    monkeypatch.setattr(timezone, "now", lambda: at("2026-11-12T23:10:00"))
    clockify = served(Clockify())
    sheet = clockify_sheet()
    assert sheets.write(sheet)["written"] == 0
    monkeypatch.setattr(timezone, "now", lambda: at("2026-11-12T23:30:00"))
    assert sheets.write(sheet)["written"] == 1
    assert [each["timeInterval"]["start"] for each in clockify.entries] == ["2026-11-12T22:30:00Z"]


def test_clockifys_budget_stops_a_write_that_goes_on_later(served, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at("2026-11-30T09:00:00"))
    for number in range(1, 17):
        kept(
            HERE,
            f"s{number}",
            "ponistra",
            10,
            [span(f"2026-11-{number:02}T08:00:00", f"2026-11-{number:02}T09:00:00")],
        )
    served(Clockify())
    sheet = clockify_sheet()
    assert sheets.write(sheet) == {"written": 14, "left": 2, "error": "sheet_busy"}
    assert Sheet.objects.get().error == "sheet_busy"


def test_taskstreamer_gets_each_block_of_the_days_due(served, now):
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    kept(HERE, "b", "ponistra", 10, [span("2026-11-12T10:00:00", "2026-11-12T10:30:00")])
    sent = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["Authorization"] == "ApiKey tsk_secret"
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json={"created": 2, "replaced": 0, "locked_days": []})

    served(answer)
    sheet = Sheet.objects.create(
        kind=Sheet.Kind.TASKSTREAMER,
        key=seal(sheets.SEALED, "tsk_secret"),
        address="https://ts.example.com",
        person="ivo@example.com",
        projects={"ponistra": "Ponistra"},
        label=LABEL,
        since=date(2026, 11, 1),
    )
    assert sheets.write(sheet)["written"] == 1
    assert sent == [
        {
            "user": "ivo@example.com",
            "days": ["2026-11-12"],
            "sessions": [
                {
                    "project": "Ponistra",
                    "start": "2026-11-12T09:00:00+01:00",
                    "end": "2026-11-12T10:00:00+01:00",
                    "description": f"{LABEL} — ponistra",
                },
                {
                    "project": "Ponistra",
                    "start": "2026-11-12T11:00:00+01:00",
                    "end": "2026-11-12T11:30:00+01:00",
                    "description": f"{LABEL} — ponistra",
                },
            ],
        }
    ]


def test_the_month_compared_with_what_clockify_holds(served, now):
    kept(HERE, CHAT, "ponistra", 10, [span("2026-11-12T08:00:00", "2026-11-12T09:00:00")])
    kept(HERE, "b", "ponistra", 10, [span("2026-11-14T08:00:00", "2026-11-14T08:30:00")])
    served(
        Clockify(
            [
                entry("old", "p1", "2026-11-12T08:00:00", "2026-11-12T08:20:00"),
                entry("hand", "p1", "2026-11-12T12:00:00", "2026-11-12T13:00:00", "Sastanak"),
            ]
        )
    )
    compared = sheets.compared(clockify_sheet(), "2026-11")
    assert compared["days"] == [
        {
            "day": "2026-11-14",
            "state": "open",
            "projects": [{"project": "p1", "measured": 1800, "own": 0, "others": 0}],
        },
        {
            "day": "2026-11-12",
            "state": "differs",
            "projects": [{"project": "p1", "measured": 3600, "own": 1200, "others": 3600}],
        },
    ]


@pytest.fixture
def owner(settings):
    settings.WORKSPACE = OWNER
    settings.WORKSPACE_URL = ""
    user = get_user_model().objects.create_user(email=OWNER, password="x")
    client = Client()
    client.force_login(user)
    return client


def test_the_owner_keeps_a_clockify_sheet_found_by_its_key(owner, served):
    served(Clockify())
    given = {
        "key": "secret",
        "label": LABEL,
        "since": "2026-11-01",
        "nightly": False,
        "projects": {"ponistra": "p1", "porat": "p2"},
        "excluded": ["porat"],
    }
    answer = owner.put("/api/workspace/sheets/clockify", json.dumps(given), content_type=JSON)
    assert answer.status_code == 200, answer.content
    shown = answer.json()
    assert shown["projects"] == {"ponistra": "p1"}
    assert shown["offered"] == [{"id": "p2", "name": "Dida"}, {"id": "p1", "name": "Ponistra"}]
    assert "key" not in shown
    sheet = Sheet.objects.get()
    assert (sheet.space, sheet.account, sheet.nightly) == ("w1", "u1", False)
    unknown = {**given, "projects": {"ponistra": "nowhere"}}
    del unknown["key"]
    answer = owner.put("/api/workspace/sheets/clockify", json.dumps(unknown), content_type=JSON)
    assert answer.json()["error"] == "invalid_sheet_projects"


def test_a_refused_key_is_not_kept(owner, served):
    served(lambda request: httpx2.Response(401))
    given = {"key": "wrong", "label": LABEL, "since": "2026-11-01", "nightly": True}
    answer = owner.put("/api/workspace/sheets/clockify", json.dumps(given), content_type=JSON)
    assert (answer.status_code, answer.json()["error"]) == (400, "sheet_refused")
    assert not Sheet.objects.exists()


def test_a_taskstreamer_without_the_time_sheets_door_is_kept_waiting(owner, served):
    served(lambda request: httpx2.Response(404))
    given = {
        "key": "tsk_secret",
        "address": "https://ts.example.com",
        "person": "ivo@example.com",
        "label": LABEL,
        "since": "2026-11-01",
        "nightly": False,
    }
    answer = owner.put("/api/workspace/sheets/taskstreamer", json.dumps(given), content_type=JSON)
    assert answer.json()["error"] == "sheet_missing"


def test_the_removal_of_transcripts_is_told_to_the_workspace(owner, settings):
    answer = owner.patch("/api/workspace/sheets", json.dumps({"after": 7}), content_type=JSON)
    assert answer.json()["removal"] == 7
    settings.WORKSPACE_TOKEN = "token"
    told = Client().get("/api/workspace/worked", HTTP_AUTHORIZATION="Bearer token")
    assert told.json()["removal"] == 7
    owner.patch("/api/workspace/sheets", json.dumps({"after": None}), content_type=JSON)
    assert Removal.objects.get().after is None
    answer = owner.patch("/api/workspace/sheets", json.dumps({"after": -1}), content_type=JSON)
    assert answer.json()["error"] == "invalid_removal"


def test_only_the_owner_sees_the_sheets(owner, settings):
    settings.WORKSPACE = "someone@example.com"
    assert owner.get("/api/workspace/sheets").status_code == 403
