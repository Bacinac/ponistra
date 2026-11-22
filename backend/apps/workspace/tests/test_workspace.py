import base64
import json
from functools import partial
from uuid import UUID

import httpx2
import pytest
from anyio import create_task_group, move_on_after
from asgiref.sync import async_to_sync
from django.test import Client
from django.utils import timezone

from apps.blobs.tests.uploads import uploaded
from apps.collab import live
from apps.core.asyncdb import database
from apps.documents.printing import compact
from apps.documents.tests.test_views import create
from apps.meetings.tests.test_rings import Tab, colleague_cookie
from apps.users import sessions
from apps.users.models import User
from apps.users.sessions import CONFIRMED
from apps.workspace.models import Aside, Command
from apps.workspace.views import CONFIRMED_FOR, OPEN_FOR, OPENED

pytestmark = pytest.mark.django_db

JSON = "application/json"


@pytest.fixture
def owner(api, settings):
    settings.WORKSPACE = api.user.email
    return api


def test_the_owner_opens_the_workspace_and_the_door_lets_them_through(owner):
    assert owner.get("/api/workspace/door").status_code == 403
    assert owner.post("/api/workspace/opened", {}, JSON).json() == {"ok": True}
    assert owner.get("/api/workspace/door").status_code == 204


def test_the_workspace_opens_under_a_confirmation_of_the_working_day(owner):
    session = owner.session
    session[CONFIRMED] = (timezone.now() - CONFIRMED_FOR).isoformat()
    session.save()
    refused = owner.post("/api/workspace/opened", {}, JSON)
    assert (refused.status_code, refused.json()) == (403, {"error": "confirm_required"})
    session = owner.session
    session[CONFIRMED] = (timezone.now() - sessions.CONFIRMED_FOR * 6).isoformat()
    session.save()
    assert owner.post("/api/workspace/opened", {}, JSON).json() == {"ok": True}


def test_an_opened_workspace_closes_after_its_hours(owner):
    owner.post("/api/workspace/opened", {}, JSON)
    session = owner.session
    session[OPENED] = (timezone.now() - OPEN_FOR).isoformat()
    session.save()
    assert owner.get("/api/workspace/door").status_code == 403


def test_signing_out_closes_the_workspace(owner):
    owner.post("/api/workspace/opened", {}, JSON)
    owner.post("/api/auth/logout", {}, JSON)
    assert owner.get("/api/workspace/door").status_code == 403


def test_nobody_but_the_owner_opens_it_administrators_included(api, settings):
    api.user.is_staff = api.user.is_superuser = True
    api.user.save()
    settings.WORKSPACE = "owner@example.com"
    refused = api.post("/api/workspace/opened", {}, JSON)
    assert (refused.status_code, refused.json()) == (403, {"error": "not_the_owner"})
    assert api.get("/api/workspace/door").status_code == 403


def test_without_a_workspace_nobody_opens_it(api, settings):
    settings.WORKSPACE = ""
    assert api.post("/api/workspace/opened", {}, JSON).status_code == 403


def test_the_door_refuses_a_browser_signed_out(client):
    assert client.get("/api/workspace/door").status_code == 403


def test_the_app_knows_whether_the_user_holds_the_workspace_and_where(owner, settings):
    def workspace():
        return owner.get("/api/auth/session").json()["user"]["workspace"]

    assert workspace() == {"url": "/code/", "here": True}
    settings.WORKSPACE_URL = "https://code.example.com"
    assert workspace() == {"url": "https://code.example.com", "here": False}
    settings.WORKSPACE = "owner@example.com"
    assert workspace() is None


def test_a_workspace_elsewhere_is_not_opened_through_this_door(owner, settings):
    settings.WORKSPACE_URL = "https://code.example.com"
    refused = owner.post("/api/workspace/opened", {}, JSON)
    assert (refused.status_code, refused.json()) == (403, {"error": "not_the_owner"})
    session = owner.session
    session[OPENED] = timezone.now().isoformat()
    session.save()
    assert owner.get("/api/workspace/door").status_code == 403


LISTED = {
    "projects": [{"name": None, "path": "/work", "chats": [], "rounds": []}],
    "restart": None,
    "host": {
        "at": "2026-11-12T15:50:00.000Z",
        "load": 2.4,
        "cpus": 12,
        "memory": {"total": 64_000_000_000, "available": 16_000_000_000},
        "swap": None,
        "disk": {"total": 800_000_000_000, "free": 40_000_000_000},
        "error": None,
    },
}


@pytest.fixture
def workspace(settings, monkeypatch):
    """The workspace's answers, and the requests it was sent."""
    settings.WORKSPACE_TOKEN = "token"
    asked = []

    def answered(request):
        asked.append(request)
        status, answer = workspace.answer
        if isinstance(answer, Exception):
            raise answer
        return httpx2.Response(status, json=answer)

    workspace.answer = (200, LISTED)
    workspace.asked = asked
    monkeypatch.setattr(
        "apps.workspace.views.httpx2.AsyncClient",
        partial(httpx2.AsyncClient, transport=httpx2.MockTransport(answered)),
    )
    return workspace


def test_the_owner_reads_the_projects_with_the_workspaces_token(owner, workspace):
    response = owner.get("/api/workspace/projects")
    assert response.json() == {
        **LISTED,
        "projects": [{**project, "plan": None, "aside": False} for project in LISTED["projects"]],
    }
    [asked] = workspace.asked
    assert (asked.method, str(asked.url)) == ("GET", "http://workspace:8081/ponistra/projects")
    assert asked.headers["Authorization"] == "Bearer token"


def test_a_workspace_elsewhere_is_asked_at_its_own_address(owner, settings, workspace):
    settings.WORKSPACE_URL = "https://code.example.com/"
    assert owner.get("/api/workspace/projects").status_code == 200
    assert [str(each.url) for each in workspace.asked] == [
        "https://code.example.com/ponistra/projects"
    ]


def test_the_owner_has_the_limits_measured_before_the_projects_are_listed(owner, workspace):
    assert owner.get("/api/workspace/projects?measured").status_code == 200
    [asked] = workspace.asked
    assert str(asked.url) == "http://workspace:8081/ponistra/projects?measured=1"


def test_nobody_but_the_owner_reads_the_projects(api, settings):
    settings.WORKSPACE = "owner@example.com"
    settings.WORKSPACE_TOKEN = "token"
    response = api.get("/api/workspace/projects")
    assert response.status_code == 403
    assert response.json() == {"error": "not_the_owner"}


def test_a_workspace_without_a_token_says_it_is_not_linked(owner, settings):
    settings.WORKSPACE_TOKEN = ""
    response = owner.get("/api/workspace/projects")
    assert response.status_code == 503
    assert response.json()["error"] == "workspace_not_linked"


@pytest.mark.parametrize(
    "answer", [(200, httpx2.ConnectError("no route")), (500, {"error": "unread"})]
)
def test_a_workspace_that_does_not_answer_is_reported(owner, workspace, answer):
    workspace.answer = answer
    response = owner.get("/api/workspace/projects")
    assert response.status_code == 502
    assert response.json()["error"] == "workspace_unreachable"


ROUND = "ponistra-20261111-1428"
SESSION = "b73e6843-731b-4bca-bcf1-154fcb205dba"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256))


def test_the_owner_reads_a_chat_through_the_workspace(owner, workspace):
    said = {"id": SESSION, "title": "Pult", "state": "idle", "waitingFor": None, "said": []}
    workspace.answer = (200, said)
    assert owner.get(f"/api/workspace/chats/{SESSION}").json() == said
    assert [each.url.path for each in workspace.asked] == [f"/ponistra/chats/{SESSION}"]
    assert owner.get("/api/workspace/chats/projects").status_code == 400


def test_the_owner_reads_a_chat_on_from_a_place_in_its_transcript(owner, workspace):
    workspace.answer = (200, {"id": SESSION, "said": [], "earlier": None})
    owner.get(f"/api/workspace/chats/{SESSION}?before=700")
    owner.get(f"/api/workspace/chats/{SESSION}?from=700")
    assert [dict(each.url.params) for each in workspace.asked] == [
        {"before": "700"},
        {"from": "700"},
    ]
    assert owner.get(f"/api/workspace/chats/{SESSION}?before=-1").status_code == 400
    assert len(workspace.asked) == 2


@pytest.mark.parametrize(
    ("given", "sent"),
    [
        ({"kind": "start", "round": ROUND}, {"round": ROUND}),
        ({"kind": "consolidate", "round": ROUND}, {"round": ROUND}),
        ({"kind": "auto", "round": ROUND, "text": "off"}, {"round": ROUND, "text": "off"}),
        ({"kind": "say", "session": SESSION, "text": " bok "}, {"session": SESSION, "text": "bok"}),
        ({"kind": "answer", "session": SESSION, "text": "no"}, {"session": SESSION, "text": "no"}),
        (
            {"kind": "answer", "session": SESSION, "text": '{"Pushati?": "Pushaj"}'},
            {"session": SESSION, "text": '{"Pushati?": "Pushaj"}'},
        ),
        ({"kind": "archive", "session": SESSION}, {"session": SESSION}),
        ({"kind": "stop", "session": SESSION}, {"session": SESSION}),
        (
            {"kind": "move", "session": SESSION, "round": ROUND},
            {"session": SESSION, "round": ROUND},
        ),
        ({"kind": "close", "session": SESSION}, {"session": SESSION}),
        ({"kind": "open", "session": SESSION}, {"session": SESSION}),
        (
            {"kind": "rename", "session": SESSION, "text": " Izvoz "},
            {"session": SESSION, "text": "Izvoz"},
        ),
        (
            {"kind": "model", "session": SESSION, "text": "sonnet"},
            {"session": SESSION, "text": "sonnet"},
        ),
        (
            {"kind": "chat", "folder": "/work/alpha", "text": "nastavi"},
            {"folder": "/work/alpha", "text": "nastavi"},
        ),
        (
            {"kind": "chat", "folder": "/work/alpha", "text": "nastavi", "model": "fable"},
            {"folder": "/work/alpha", "text": "nastavi", "model": "fable"},
        ),
        (
            {"kind": "chat", "folder": "/work/alpha", "text": "pregledaj", "model": None},
            {"folder": "/work/alpha", "text": "pregledaj"},
        ),
        (
            {
                "kind": "chat",
                "folder": "/work/alpha",
                "text": "pregledaj",
                "when": {"on": "time", "at": "2026-11-16T03:30:00+01:00", "every": "day"},
            },
            {
                "folder": "/work/alpha",
                "text": "pregledaj",
                "when": {"on": "time", "at": "2026-11-16T02:30:00+00:00", "every": "day"},
            },
        ),
        (
            {"kind": "start", "round": ROUND, "when": {"on": "below", "percent": 40, "pause": 90}},
            {"round": ROUND, "when": {"on": "below", "percent": 40, "pause": 90}},
        ),
        (
            {"kind": "start", "round": ROUND, "when": {"on": "round", "round": "drugi.krug"}},
            {"round": ROUND, "when": {"on": "round", "round": "drugi.krug"}},
        ),
        ({"kind": "cancel", "round": ROUND}, {"round": ROUND}),
        ({"kind": "cancel", "text": "42"}, {"text": "42"}),
    ],
)
def test_each_command_is_kept_and_handed_to_the_workspace(owner, workspace, given, sent):
    workspace.answer = (200, {"state": "sent"})
    answer = owner.post("/api/workspace/commands", given, JSON).json()
    command = Command.objects.get()
    assert (answer["id"], answer["kind"], answer["state"]) == (command.pk, given["kind"], "sent")
    [asked] = workspace.asked
    assert (asked.method, asked.url.path) == ("POST", "/ponistra/commands")
    assert json.loads(asked.content) == {
        "id": command.pk,
        "kind": given["kind"],
        "auto": False,
        **sent,
    }
    assert owner.get("/api/workspace/commands").json()["commands"] == [answer]


def test_a_new_chat_keeps_the_session_the_workspace_gave_it(owner, workspace):
    workspace.answer = (200, {"state": "done", "session": SESSION})
    given = {"kind": "chat", "folder": "/work/alpha", "text": "nastavi"}
    answer = owner.post("/api/workspace/commands", given, JSON).json()
    assert (answer["session"], answer["state"]) == (SESSION, "done")


def test_a_message_the_workspace_took_back_is_cancelled_at_once(owner, workspace):
    workspace.answer = (200, {"state": "done"})
    said = owner.post(
        "/api/workspace/commands", {"kind": "say", "session": SESSION, "text": "x"}, JSON
    ).json()
    cancel = {"kind": "cancel", "text": str(said["id"])}
    assert owner.post("/api/workspace/commands", cancel, JSON).json()["state"] == "done"
    assert (Command.objects.get(pk=said["id"]).state, Command.objects.get(pk=said["id"]).error) == (
        "failed",
        "cancelled",
    )


def test_a_message_already_read_stays_as_it_was(owner, workspace):
    workspace.answer = (200, {"state": "done"})
    said = owner.post(
        "/api/workspace/commands", {"kind": "say", "session": SESSION, "text": "x"}, JSON
    ).json()
    workspace.answer = (409, {"error": "already_read"})
    cancel = {"kind": "cancel", "text": str(said["id"])}
    assert owner.post("/api/workspace/commands", cancel, JSON).json()["error"] == "already_read"
    assert Command.objects.get(pk=said["id"]).state == "done"


def test_a_message_carries_the_images_the_owner_uploaded(owner, workspace):
    workspace.answer = (200, {"state": "sent"})
    png = uploaded(owner, PNG)["sha256"]
    given = {"kind": "say", "session": SESSION, "text": "Što je ovo?", "images": [png]}
    answer = owner.post("/api/workspace/commands", given, JSON).json()
    assert answer["images"] == 1
    [asked] = workspace.asked
    assert json.loads(asked.content)["images"] == [
        {"media_type": "image/png", "data": base64.b64encode(PNG).decode()}
    ]


def test_a_message_carries_no_file_but_an_image_of_its_own(owner, workspace):
    colleague = Client()
    colleague.force_login(User.objects.create_user("kolega@example.com", "Kamen-Most-Rijeka-72"))
    text = uploaded(owner, b"plain words")["sha256"]
    theirs = uploaded(colleague, PNG + b"theirs")["sha256"]
    for sha256 in (text, theirs):
        given = {"kind": "say", "session": SESSION, "text": "x", "images": [sha256]}
        response = owner.post("/api/workspace/commands", given, JSON)
        assert (response.status_code, response.json()) == (400, {"error": "invalid_images"})
    assert workspace.asked == []


@pytest.mark.parametrize(
    ("given", "error"),
    [
        ({"kind": "delete"}, "invalid_command"),
        ({"kind": "start", "round": "krug jedan"}, "invalid_round"),
        ({"kind": "push"}, "invalid_session"),
        ({"kind": "say", "session": "../projects", "text": "x"}, "invalid_session"),
        ({"kind": "say", "session": SESSION, "text": "  "}, "invalid_text"),
        ({"kind": "answer", "session": SESSION, "text": "maybe"}, "invalid_text"),
        ({"kind": "answer", "session": SESSION, "text": '{"Pushati?": " "}'}, "invalid_text"),
        ({"kind": "answer", "session": SESSION, "text": '["Pushaj"]'}, "invalid_text"),
        ({"kind": "rename", "session": SESSION, "text": "dva\nretka"}, "invalid_text"),
        ({"kind": "rename", "session": SESSION, "text": "x" * 101}, "invalid_text"),
        ({"kind": "auto", "round": ROUND, "text": "sometimes"}, "invalid_text"),
        ({"kind": "model", "session": SESSION, "text": "Opus 5.5"}, "invalid_model"),
        ({"kind": "model", "text": "opus"}, "invalid_session"),
        ({"kind": "move", "session": SESSION}, "invalid_round"),
        ({"kind": "move", "round": ROUND}, "invalid_session"),
        ({"kind": "chat", "folder": "work", "text": "nastavi"}, "invalid_folder"),
        (
            {"kind": "chat", "folder": "/work/alpha", "text": "x", "model": "Opus 5.5"},
            "invalid_model",
        ),
        ({"kind": "chat", "folder": "/work/alpha", "text": "x", "model": 5}, "invalid_model"),
        ({"kind": "say", "session": SESSION, "text": "x", "images": "a"}, "invalid_images"),
        ({"kind": "say", "session": SESSION, "text": "x", "images": ["0" * 64]}, "invalid_images"),
        ({"kind": "say", "session": SESSION, "text": "x", "images": ["x"]}, "invalid_images"),
        ({"kind": "start", "round": ROUND, "when": {"on": "rain"}}, "invalid_when"),
        ({"kind": "start", "round": ROUND, "when": {"on": "below", "percent": 0}}, "invalid_when"),
        ({"kind": "start", "round": ROUND, "when": {"on": "red", "pause": 101}}, "invalid_when"),
        (
            {"kind": "start", "round": ROUND, "when": {"on": "time", "at": "2026-11-16T03:30"}},
            "invalid_when",
        ),
        (
            {
                "kind": "start",
                "round": ROUND,
                "when": {"on": "time", "at": "2026-11-16T03:30:00Z", "every": "day"},
            },
            "invalid_when",
        ),
        ({"kind": "cancel", "text": "x"}, "invalid_text"),
    ],
)
def test_a_command_is_asked_only_what_it_knows(owner, workspace, given, error):
    response = owner.post("/api/workspace/commands", given, JSON)
    assert (response.status_code, response.json()) == (400, {"error": error})
    assert workspace.asked == []
    assert not Command.objects.exists()


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        ((409, {"error": "workspace_busy"}), "workspace_busy"),
        ((404, {"error": "no_round"}), "no_round"),
        ((500, {"error": "unread"}), "workspace_unreachable"),
    ],
)
def test_a_command_the_workspace_refuses_is_kept_as_failed(owner, workspace, answer, error):
    workspace.answer = answer
    response = owner.post("/api/workspace/commands", {"kind": "start", "round": ROUND}, JSON)
    assert (response.status_code, response.json()["state"]) == (200, "failed")
    assert Command.objects.get().error == error


@pytest.mark.parametrize(
    "given",
    [
        {"kind": "push", "round": ROUND},
        {"kind": "push", "session": SESSION},
        {"kind": "restart"},
    ],
)
def test_a_push_or_restart_waits_for_the_owner_to_confirm_within_a_working_day(
    owner, workspace, given
):
    workspace.answer = (200, {"state": "taken"})
    session = owner.session
    session[CONFIRMED] = (timezone.now() - CONFIRMED_FOR).isoformat()
    session.save()
    response = owner.post("/api/workspace/commands", given, JSON)
    assert (response.status_code, response.json()) == (403, {"error": "confirm_required"})
    assert workspace.asked == []
    session = owner.session
    session[CONFIRMED] = (timezone.now() - sessions.CONFIRMED_FOR * 6).isoformat()
    session.save()
    assert owner.post("/api/workspace/commands", given, JSON).json()["state"] == "taken"


def test_nobody_but_the_owner_asks_the_workspace(api, settings, workspace):
    settings.WORKSPACE = "owner@example.com"
    given = {"kind": "start", "round": ROUND}
    assert api.post("/api/workspace/commands", given, JSON).status_code == 403
    assert api.get("/api/workspace/commands").status_code == 403
    assert api.get(f"/api/workspace/chats/{SESSION}").status_code == 403
    assert workspace.asked == []


def test_the_workspace_reports_how_its_commands_went_and_never_takes_one_back(client, settings):
    settings.WORKSPACE_TOKEN = "token"
    sent, taken = (Command.objects.create(kind=Command.Kind.SAY) for _ in range(2))
    taken.state = Command.State.DONE
    taken.save()
    outcomes = [
        {"id": sent.pk, "state": "failed", "error": "chat_busy"},
        {"id": taken.pk, "state": "taken"},
        {"id": "x", "state": "done"},
    ]
    response = client.post(
        "/api/workspace/changed",
        {"commands": outcomes},
        JSON,
        HTTP_AUTHORIZATION="Bearer token",
    )
    assert response.status_code == 204
    sent.refresh_from_db()
    taken.refresh_from_db()
    assert (sent.state, sent.error, taken.state) == ("failed", "chat_busy", "done")


def test_a_chat_waiting_on_a_condition_names_each_session_it_starts(client, settings):
    settings.WORKSPACE_TOKEN = "token"
    waiting = Command.objects.create(kind=Command.Kind.CHAT, state=Command.State.WAITING)
    started = "0244db82-f45d-4599-bad9-2c61f5d5463c"
    for state in ("waiting", "done"):
        client.post(
            "/api/workspace/changed",
            {"commands": [{"id": waiting.pk, "state": state, "session": started}]},
            JSON,
            HTTP_AUTHORIZATION="Bearer token",
        )
    waiting.refresh_from_db()
    assert (waiting.state, waiting.session) == ("done", started)


def _plan(api, title):
    page = uploaded(api, f"<!doctype html><html><body>{title}</body></html>".encode())["sha256"]
    return create(api, "file", title, blob=page, extension="html")


def test_each_project_is_shown_the_board_of_its_plan(owner, workspace):
    alpha = _plan(owner, "Plan Alpha")
    opus = _plan(owner, "Plan OPUS")
    _plan(owner, "Planovi")
    names = ["alpha", "opus-library", "alphabet", None]
    workspace.answer = (
        200,
        {"projects": [{"name": name, "path": f"/work/{name}"} for name in names], "restart": None},
    )
    plans = [project["plan"] for project in owner.get("/api/workspace/projects").json()["projects"]]
    assert plans == [
        None,
        {"title": "Plan Alpha", "path": f"/p/{compact(UUID(alpha))}"},
        None,
        {"title": "Plan OPUS", "path": f"/p/{compact(UUID(opus))}"},
    ]


def test_a_plan_the_owner_cannot_read_is_not_shown(owner, workspace):
    other = Client()
    other.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71"))
    _plan(other, "Plan Alpha")
    workspace.answer = (200, {"projects": [{"name": "alpha", "path": "/work/alpha"}]})
    assert owner.get("/api/workspace/projects").json()["projects"][0]["plan"] is None


def test_the_projects_stand_by_name_as_croatian_orders_it_the_general_one_first(owner, workspace):
    names = ["žaba", "čelik", None, "Dida", "cvijet", "zeta"]
    workspace.answer = (
        200,
        {"projects": [{"name": name, "path": f"/work/{name}"} for name in names], "restart": None},
    )
    listed = owner.get("/api/workspace/projects").json()["projects"]
    assert [project["name"] for project in listed] == [
        None,
        "cvijet",
        "čelik",
        "Dida",
        "zeta",
        "žaba",
    ]


def _listed(owner, workspace, **alpha):
    workspace.answer = (
        200,
        {
            "projects": [
                {"name": "alpha", "path": "/work/alpha", "chats": [], "rounds": [], **alpha},
                {"name": "beta", "path": "/work/beta", "chats": [], "rounds": []},
            ]
        },
    )
    return {
        project["name"]: project["aside"]
        for project in owner.get("/api/workspace/projects").json()["projects"]
    }


def _ran(when):
    return [{"id": "a", "at": when.isoformat().replace("+00:00", "Z")}]


def test_a_project_put_under_others_stays_there_until_something_in_it_runs(owner, workspace):
    before = timezone.now()
    put = owner.post("/api/workspace/projects", {"name": "alpha", "aside": True}, JSON)
    assert put.status_code == 204
    assert _listed(owner, workspace, chats=_ran(before)) == {"alpha": True, "beta": False}
    ran = _ran(timezone.now())
    assert _listed(owner, workspace, chats=ran) == {"alpha": False, "beta": False}
    assert _listed(owner, workspace, chats=ran) == {"alpha": False, "beta": False}
    owner.post("/api/workspace/projects", {"name": "alpha", "aside": True}, JSON)
    assert _listed(owner, workspace, chats=ran) == {"alpha": True, "beta": False}


def test_a_round_begun_in_a_project_under_others_brings_it_back(owner, workspace):
    owner.post("/api/workspace/projects", {"name": "alpha", "aside": True}, JSON)
    begun = {"created": timezone.now().isoformat(), "coordinator": {"at": None}, "chats": []}
    assert _listed(owner, workspace, rounds=[begun]) == {"alpha": False, "beta": False}


def test_the_owner_brings_a_project_back_from_others(owner, workspace):
    owner.post("/api/workspace/projects", {"name": "alpha", "aside": True}, JSON)
    back = owner.post("/api/workspace/projects", {"name": "alpha", "aside": False}, JSON)
    assert back.status_code == 204
    assert not Aside.objects.exists()
    assert _listed(owner, workspace) == {"alpha": False, "beta": False}


@pytest.mark.parametrize(
    ("given", "error"),
    [
        ({"aside": True}, "invalid_name"),
        ({"name": "", "aside": True}, "invalid_name"),
        ({"name": "../alpha", "aside": True}, "invalid_name"),
        ({"name": "alpha"}, "invalid_aside"),
        ({"name": "alpha", "aside": "yes"}, "invalid_aside"),
    ],
)
def test_only_a_project_named_and_put_one_way_or_the_other_is_moved(owner, given, error):
    refused = owner.post("/api/workspace/projects", given, JSON)
    assert (refused.status_code, refused.json()) == (400, {"error": error})


def test_nobody_but_the_owner_moves_a_project(api, settings):
    settings.WORKSPACE = "owner@example.com"
    moved = api.post("/api/workspace/projects", {"name": "alpha", "aside": True}, JSON)
    assert moved.status_code == 403
    assert not Aside.objects.exists()


@pytest.mark.parametrize("token", ["", "Bearer wrong", "token"])
def test_the_workspace_tells_of_a_change_only_with_its_token(client, settings, token):
    settings.WORKSPACE_TOKEN = "token"
    response = client.post("/api/workspace/changed", HTTP_AUTHORIZATION=token)
    assert response.status_code == 403


def test_without_a_token_no_change_is_heard(client, settings):
    settings.WORKSPACE_TOKEN = ""
    assert client.post("/api/workspace/changed", HTTP_AUTHORIZATION="Bearer ").status_code == 403


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_change_in_the_workspace_reaches_its_owners_tabs(settings):
    cookie, _, ana = await colleague_cookie()
    settings.WORKSPACE = ana.email
    settings.WORKSPACE_TOKEN = "token"
    async with create_task_group() as tg:
        tg.start_soon(live.listen)
        tab = Tab(cookie, tg)
        await tab.state()

        def told():
            return Client().post("/api/workspace/changed", HTTP_AUTHORIZATION="Bearer token")

        assert (await database(told)()).status_code == 204
        heard = set()
        with move_on_after(5):
            while "workspace" not in heard:
                heard.update((await tab.state()).get("areas", []))
        assert "workspace" in heard
        tg.cancel_scope.cancel()


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_project_put_under_others_reaches_its_owners_tabs():
    cookie, _, ana = await colleague_cookie()
    async with create_task_group() as tg:
        tg.start_soon(live.listen)
        tab = Tab(cookie, tg)
        await tab.state()
        await database(Aside.objects.create)(owner=ana, name="alpha")
        heard = set()
        with move_on_after(5):
            while "workspace" not in heard:
                heard.update((await tab.state()).get("areas", []))
        assert "workspace" in heard
        tg.cancel_scope.cancel()


FILE = {"folder": "/work/ponistra", "path": "backend/app.py"}
HASHED = "a" * 64


def test_the_owner_lists_a_folder_of_a_project_through_the_workspace(owner, workspace):
    listed = {"path": "backend", "entries": [{"name": "app.py", "kind": "file", "size": 4}]}
    workspace.answer = (200, listed)
    response = owner.get("/api/workspace/files", {"folder": "/work/ponistra", "path": "backend"})
    assert response.json() == listed
    [asked] = workspace.asked
    assert asked.url.path == "/ponistra/files"
    assert dict(asked.url.params) == {"folder": "/work/ponistra", "path": "backend"}
    assert asked.headers["Authorization"] == "Bearer token"


def test_the_owner_reads_a_file_and_writes_it_while_it_is_unchanged(owner, workspace):
    workspace.answer = (200, {"kind": "text", "text": "x = 1\n", "hash": HASHED})
    assert owner.get("/api/workspace/file", FILE).json()["text"] == "x = 1\n"
    workspace.answer = (200, {"hash": "b" * 64})
    given = {**FILE, "text": "x = 2\n", "hash": HASHED}
    assert owner.post("/api/workspace/file", given, JSON).json() == {"hash": "b" * 64}
    read, written = workspace.asked
    assert read.url.path == "/ponistra/files/read"
    assert (written.method, written.url.path) == ("POST", "/ponistra/files/write")
    assert json.loads(written.content) == given


@pytest.mark.parametrize(
    "answer",
    [(409, {"error": "changed"}), (403, {"error": "outside"}), (413, {"error": "too_large"})],
)
def test_the_workspace_refusing_a_file_says_why(owner, workspace, answer):
    workspace.answer = answer
    response = owner.post("/api/workspace/file", {**FILE, "text": "", "hash": HASHED}, JSON)
    assert (response.status_code, response.json()) == answer


def test_a_refused_token_is_a_fault_of_the_link_not_of_the_file(owner, workspace):
    workspace.answer = (403, {"error": "refused"})
    response = owner.get("/api/workspace/file", FILE)
    assert (response.status_code, response.json()) == (502, {"error": "workspace_unreachable"})


@pytest.mark.parametrize(
    "given, error",
    [
        ({"path": "a"}, "invalid_folder"),
        ({"folder": "work", "path": "a"}, "invalid_folder"),
        ({**FILE, "hash": HASHED}, "invalid_text"),
        ({**FILE, "text": "", "hash": "abc"}, "invalid_hash"),
        ({**FILE, "path": "a\0b", "text": "", "hash": HASHED}, "invalid_path"),
    ],
)
def test_a_file_is_asked_only_what_it_knows(owner, workspace, given, error):
    response = owner.post("/api/workspace/file", given, JSON)
    assert (response.status_code, response.json()) == (400, {"error": error})
    assert workspace.asked == []


def test_a_file_is_written_only_by_an_owner_who_confirmed_within_a_working_day(owner, workspace):
    session = owner.session
    session[CONFIRMED] = (timezone.now() - CONFIRMED_FOR).isoformat()
    session.save()
    response = owner.post("/api/workspace/file", {**FILE, "text": "", "hash": HASHED}, JSON)
    assert (response.status_code, response.json()) == (403, {"error": "confirm_required"})
    assert workspace.asked == []


def test_nobody_but_the_owner_reaches_the_files(api, settings, workspace):
    settings.WORKSPACE = "owner@example.com"
    assert api.get("/api/workspace/files", {"folder": "/work"}).status_code == 403
    assert api.get("/api/workspace/file", FILE).status_code == 403
    assert api.get("/api/workspace/file/raw", FILE).status_code == 403
    assert workspace.asked == []


async def collected(response) -> bytes:
    return b"".join([part async for part in response.streaming_content])


def test_the_owner_downloads_a_file_as_the_workspace_sends_it(owner, settings, monkeypatch):
    settings.WORKSPACE_TOKEN = "token"
    sent = bytes(range(256)) * 10

    def answered(request):
        assert request.url.path == "/ponistra/files/raw"
        return httpx2.Response(200, content=sent, headers={"content-length": str(len(sent))})

    monkeypatch.setattr(
        "apps.workspace.views.httpx2.AsyncClient",
        partial(httpx2.AsyncClient, transport=httpx2.MockTransport(answered)),
    )
    response = owner.get("/api/workspace/file/raw", FILE)
    assert response.status_code == 200
    assert async_to_sync(collected)(response) == sent
    assert response["Content-Disposition"] == 'attachment; filename="app.py"'
    assert response["Content-Length"] == str(len(sent))


ON_HOST = {"host": "mlaka", "path": "srv/app.conf"}
HOSTS = {
    "hosts": [
        {
            "name": "mlaka",
            "address": "192.0.2.11",
            "port": 22,
            "user": "root",
            "path": "/srv",
            "key": "ponistra_ed25519",
        }
    ],
    "keys": [{"name": "ponistra_ed25519", "type": "ssh-ed25519", "comment": "", "public": "k"}],
    "made": "ponistra_ed25519",
}
HOST = dict(HOSTS["hosts"][0])


def test_a_hosts_folder_is_asked_by_its_name_beside_the_path(owner, workspace):
    workspace.answer = (200, {"path": "srv", "entries": []})
    response = owner.get("/api/workspace/files", {"host": "mlaka", "path": "srv"})
    assert response.json() == {"path": "srv", "entries": []}
    [asked] = workspace.asked
    assert dict(asked.url.params) == {"host": "mlaka", "path": "srv"}


def test_a_hosts_file_is_written_with_the_host_beside_the_path(owner, workspace):
    workspace.answer = (200, {"hash": "b" * 64})
    given = {**ON_HOST, "text": "x\n", "hash": HASHED}
    assert owner.post("/api/workspace/file", given, JSON).json() == {"hash": "b" * 64}
    [written] = workspace.asked
    assert (written.method, written.url.path) == ("POST", "/ponistra/files/write")
    assert dict(written.url.params) == {"host": "mlaka"}
    assert json.loads(written.content) == {"path": "srv/app.conf", "text": "x\n", "hash": HASHED}


@pytest.mark.parametrize(
    "error", ["ssh_key_refused", "host_unreachable", "host_unknown", "host_key_changed"]
)
def test_a_host_that_cannot_be_reached_says_why(owner, workspace, error):
    workspace.answer = (409, {"error": error})
    response = owner.get("/api/workspace/files", {"host": "mlaka", "path": ""})
    assert (response.status_code, response.json()) == (409, {"error": error})


@pytest.mark.parametrize("host", ["", "-oProxyCommand=x", "a b", "a" * 64])
def test_a_host_is_asked_only_by_a_name_its_config_can_hold(owner, workspace, host):
    response = owner.get("/api/workspace/files", {"host": host, "path": ""})
    assert (response.status_code, response.json()) == (400, {"error": "invalid_host"})
    assert workspace.asked == []


def test_the_owner_reads_the_hosts_and_the_keys(owner, workspace):
    workspace.answer = (200, HOSTS)
    assert owner.get("/api/workspace/hosts").json() == HOSTS
    [asked] = workspace.asked
    assert (asked.method, asked.url.path) == ("GET", "/ponistra/hosts")


def test_a_host_is_saved_in_the_place_of_the_one_it_was(owner, workspace):
    workspace.answer = (200, HOSTS)
    given = {**HOST, "was": "old"}
    assert owner.post("/api/workspace/hosts", given, JSON).json() == HOSTS
    [asked] = workspace.asked
    assert (asked.method, asked.url.path) == ("POST", "/ponistra/hosts")
    assert json.loads(asked.content) == given


@pytest.mark.parametrize(
    "given, error",
    [
        ({**HOST, "name": "-x"}, "invalid_host"),
        ({**HOST, "was": "a b"}, "invalid_host"),
        ({**HOST, "address": "-oProxyCommand=x"}, "invalid_host_address"),
        ({**HOST, "address": "a b"}, "invalid_host_address"),
        ({**HOST, "port": 0}, "invalid_host_port"),
        ({**HOST, "port": True}, "invalid_host_port"),
        ({**HOST, "port": "22"}, "invalid_host_port"),
        ({**HOST, "user": "root\nHost *"}, "invalid_host_user"),
        ({**HOST, "path": "/srv\nProxyCommand x"}, "invalid_path"),
        ({**HOST, "key": "../id"}, "invalid_host_key"),
    ],
)
def test_a_host_holds_only_what_its_entry_can_say(owner, workspace, given, error):
    response = owner.post("/api/workspace/hosts", given, JSON)
    assert (response.status_code, response.json()) == (400, {"error": error})
    assert workspace.asked == []


def test_a_host_is_removed_by_its_name(owner, workspace):
    workspace.answer = (200, {**HOSTS, "hosts": []})
    response = owner.delete("/api/workspace/hosts?name=mlaka")
    assert response.json()["hosts"] == []
    [asked] = workspace.asked
    assert (asked.url.path, json.loads(asked.content)) == (
        "/ponistra/hosts/remove",
        {"name": "mlaka"},
    )


def test_the_workspace_makes_its_own_key(owner, workspace):
    workspace.answer = (200, HOSTS)
    assert owner.post("/api/workspace/hosts/key", {}, JSON).json() == HOSTS
    workspace.answer = (409, {"error": "key_exists"})
    response = owner.post("/api/workspace/hosts/key", {}, JSON)
    assert (response.status_code, response.json()) == (409, {"error": "key_exists"})


@pytest.mark.parametrize(
    "method, path",
    [
        ("post", "/api/workspace/hosts"),
        ("delete", "/api/workspace/hosts?name=mlaka"),
        ("post", "/api/workspace/hosts/key"),
    ],
)
def test_hosts_change_only_for_an_owner_who_confirmed_within_a_working_day(
    owner, workspace, method, path
):
    session = owner.session
    session[CONFIRMED] = (timezone.now() - CONFIRMED_FOR).isoformat()
    session.save()
    response = getattr(owner, method)(path, HOST, JSON)
    assert (response.status_code, response.json()) == (403, {"error": "confirm_required"})
    assert workspace.asked == []


def test_nobody_but_the_owner_reaches_the_hosts(api, settings, workspace):
    settings.WORKSPACE = "owner@example.com"
    assert api.get("/api/workspace/hosts").status_code == 403
    assert api.post("/api/workspace/hosts", HOST, JSON).status_code == 403
    assert api.post("/api/workspace/hosts/key", {}, JSON).status_code == 403
    assert api.get("/api/workspace/files", {"host": "mlaka"}).status_code == 403
    assert workspace.asked == []
