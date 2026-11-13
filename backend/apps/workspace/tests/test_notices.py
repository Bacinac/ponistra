from functools import partial

import httpx2
import pytest
from django.test import Client

from apps.push import notices
from apps.push.models import Notice
from apps.push.tests.test_push import person, subscribed
from apps.workspace.models import Command, Seen
from apps.workspace.notices import AUTO, compared, due, limited, told

pytestmark = pytest.mark.django_db

CHAT = "5bd35ed2-cbe6-4cab-9778-7e292e258673"
OTHER = "0244db82-f45d-4599-bad9-2c61f5d5463c"
LEAD = "b8b1624c-1f70-428c-9547-ebeb01097019"
ROUND = "ponistra-20261111-1647"
TREE = "4b825dc642cb6eb9a060e54bf8d69288fbe4904"


def member(id, state, at="2026-11-11T16:00:00Z", title="Obavijesti kruga"):
    waiting = "input needed" if state == "waiting" else None
    return {"id": id, "name": None, "title": title, "state": state, "waitingFor": waiting, "at": at}


def listed(*chats, started="2026-11-11T15:50:00Z", rounds=True, gate=None, lead=None, **round):
    round = {
        "id": ROUND,
        "created": "2026-11-11T15:47:50Z",
        "started": started,
        "coordinator": lead or member(LEAD, "idle", title="Koordinator"),
        "chats": list(chats),
        **round,
    }
    return [
        {
            "name": "ponistra",
            "path": "/work/ponistra",
            "chats": [],
            "rounds": [round] if rounds else [],
            "gate": gate,
        }
    ]


def events(before, projects):
    return [data for data, _ in compared(before, projects)[1]]


def test_a_chat_waiting_is_told_once_and_again_only_when_it_waits_anew():
    shown, _ = compared({}, listed(member(CHAT, "working"), member(OTHER, "idle")))
    waiting = listed(member(CHAT, "waiting"), member(OTHER, "idle"))
    assert events(shown, waiting) == [
        {"event": "waiting", "project": "ponistra", "chat": "Obavijesti kruga", "session": CHAT}
    ]
    shown, _ = compared(shown, waiting)
    assert events(shown, waiting) == []
    again = listed(member(CHAT, "waiting", at="2026-11-11T16:05:00Z"), member(OTHER, "idle"))
    assert len(events(shown, again)) == 1


def test_the_coordinator_waiting_is_told_too():
    projects = listed(member(CHAT, "working"))
    projects[0]["rounds"][0]["coordinator"] = member(LEAD, "waiting", title="Koordinator")
    assert events({}, projects) == [
        {"event": "waiting", "project": "ponistra", "chat": "Koordinator", "session": LEAD}
    ]


def test_a_round_is_ready_once_every_chat_of_it_has_finished():
    shown, _ = compared({}, listed(member(CHAT, "working"), member(OTHER, "idle")))
    finished = listed(member(CHAT, "idle"), member(OTHER, "closed"))
    assert events(shown, finished) == [{"event": "ready", "project": "ponistra", "round": ROUND}]
    shown, _ = compared(shown, finished)
    assert events(shown, finished) == []


@pytest.mark.parametrize(
    "chats, started",
    [
        ([member(None, "new"), member(OTHER, "idle")], "2026-11-11T15:50:00Z"),
        ([member(CHAT, "idle")], None),
        ([], "2026-11-11T15:50:00Z"),
    ],
)
def test_a_round_not_started_or_with_a_chat_not_begun_is_not_ready(chats, started):
    assert events({}, listed(*chats, started=started)) == []


def test_a_round_gone_from_the_list_was_consolidated():
    shown, _ = compared({}, listed(member(CHAT, "idle")))
    assert events(shown, listed(rounds=False)) == [
        {"event": "consolidated", "project": "ponistra", "round": ROUND}
    ]


def test_a_failed_check_is_told_once_per_run_and_a_passed_one_never():
    def gate(outcome, at, failed=None):
        night = {"tree": TREE, "outcome": outcome, "at": at, "pushed": True, "failed": failed}
        return {"checked": None, "pushed": None, "browser": None, "night": night, "running": []}

    failed = listed(rounds=False, gate=gate("failed", "2026-11-11T02:30:00Z", 3))
    assert events({}, failed) == [{"event": "night", "project": "ponistra", "failed": 3}]
    shown, _ = compared({}, failed)
    assert events(shown, failed) == []
    assert events(shown, listed(rounds=False, gate=gate("passed", "2026-11-12T02:30:00Z"))) == []
    next_night = listed(rounds=False, gate=gate("failed", "2026-11-12T02:30:00Z"))
    assert len(events(shown, next_night)) == 1


def heard(event, at="2026-11-11T17:00:00Z", **said):
    lead = member(LEAD, "idle", title="Koordinator")
    return {**lead, "heard": {"event": event, "at": at, "message": None, "said": None, **said}}


def test_the_coordinator_is_heard_each_time_it_answers_or_asks():
    shown, _ = compared({}, listed(member(CHAT, "working")))
    answered = listed(member(CHAT, "working"), lead=heard("stop", said="Krug je zelen."))
    assert events(shown, answered) == [
        {
            "event": "said",
            "project": "ponistra",
            "chat": "Koordinator",
            "session": LEAD,
            "text": "Krug je zelen.",
        }
    ]
    shown, _ = compared(shown, answered)
    assert events(shown, answered) == []
    asking = heard("notification", at="2026-11-11T17:05:00Z", message="Claude needs your input")
    assert events(shown, listed(member(CHAT, "working"), lead=asking))[0]["event"] == "asks"


@pytest.mark.parametrize(
    ("lead", "round", "before", "consolidates"),
    [
        ("idle", {}, [], True),
        ("idle", {"auto": False}, [], False),
        ("working", {}, [], False),
        ("idle", {"asked": "objedini"}, [], False),
        ("idle", {}, [ROUND], False),
    ],
)
def test_a_round_consolidates_itself_once_its_chats_have_just_finished(
    lead, round, before, consolidates
):
    projects = listed(member(CHAT, "idle"), lead=member(LEAD, lead, title="Koordinator"), **round)
    assert due({"ready": before}, projects) == ([ROUND] if consolidates else [])


RESETS = "2026-11-15T21:00:00.000Z"


def usage(week, fable=4, credits=None, error=None, resets=RESETS):
    return {
        "at": "2026-11-12T12:20:00.000Z",
        "windows": [
            {"kind": "session", "name": None, "percent": 99, "resets": "2026-11-12T15:00:00.000Z"},
            {"kind": "week", "name": None, "percent": week, "resets": resets},
            {"kind": "model", "name": "Fable", "percent": fable, "resets": resets},
        ],
        "credits": credits,
        "error": error,
    }


def test_a_weekly_limit_past_its_mark_is_told_once_a_window_and_the_session_never():
    shown, told = limited({}, usage(81))
    assert [data for data, _ in told] == [
        {"event": "limit", "window": "week", "name": None, "percent": 81}
    ]
    assert limited({"limits": shown}, usage(95)) == (shown, [])
    _, told = limited({"limits": shown}, usage(85, resets="2026-11-22T21:00:00.000Z"))
    assert [data["percent"] for data, _ in told] == [85]
    assert limited({}, usage(79)) == ([], [])


def test_a_model_past_its_limit_spending_credits_is_told_both():
    credits = {"used": 1.5, "currency": "USD", "using": True}
    _, told = limited({}, usage(40, fable=100, credits=credits))
    assert [data for data, _ in told] == [
        {"event": "limit", "window": "model", "name": "Fable", "percent": 100},
        {"event": "credits", "window": "model", "name": "Fable", "percent": 100},
    ]


def test_a_limit_not_read_changes_nothing_of_what_was_told():
    assert limited({"limits": ["kept"]}, usage(90, error="unread: seven_day")) == (["kept"], [])
    assert limited({"limits": ["kept"]}, None) == (["kept"], [])


@pytest.fixture
def owner(settings, monkeypatch):
    """The workspace's owner with a browser subscribed, and the workspace answering what
    `owner.projects` holds."""
    found = person("ivo@example.com", "Ivo")
    subscribed(found)
    settings.WORKSPACE = found.email
    settings.WORKSPACE_TOKEN = "token"
    found.projects = listed(member(CHAT, "working"))
    found.usage = None

    def answered(request):
        if found.projects is None:
            raise httpx2.ConnectError("no route")
        return httpx2.Response(200, json={"projects": found.projects, "usage": found.usage})

    monkeypatch.setattr(
        "apps.workspace.views.httpx2.AsyncClient",
        partial(httpx2.AsyncClient, transport=httpx2.MockTransport(answered)),
    )
    return found


def changed():
    return Client().post("/api/workspace/changed", HTTP_AUTHORIZATION="Bearer token")


def test_the_owner_hears_what_changed_but_not_what_was_there_when_first_heard(owner):
    owner.projects = listed(member(CHAT, "waiting"))
    assert changed().status_code == 204
    assert not Notice.objects.exists()
    owner.projects = listed(member(CHAT, "idle"))
    changed()
    [notice] = Notice.objects.all()
    assert (notice.user, notice.kind) == (owner, Notice.Kind.CODE)
    assert notice.data == {"event": "ready", "project": "ponistra", "round": ROUND}
    assert notice.tag.startswith("code-")


def test_a_round_whose_chats_finished_asks_its_coordinator_to_consolidate(owner):
    owner.projects = listed(member(CHAT, "working"))
    changed()
    owner.projects = listed(member(CHAT, "idle"))
    changed()
    command = Command.objects.get()
    assert (command.kind, command.round, command.text, command.auto) == (
        Command.Kind.CONSOLIDATE,
        ROUND,
        AUTO,
        True,
    )
    changed()
    assert Command.objects.count() == 1


def test_the_owner_hears_a_weekly_limit_running_out(owner):
    changed()
    owner.usage = usage(82)
    changed()
    assert Notice.objects.get().data == {
        "event": "limit",
        "window": "week",
        "name": None,
        "percent": 82,
    }
    changed()
    assert Notice.objects.count() == 1


def test_a_workspace_that_does_not_answer_leaves_what_it_showed(owner):
    told()
    shown = Seen.objects.get().shown
    owner.projects = None
    assert changed().status_code == 204
    assert Seen.objects.get().shown == shown
    owner.projects = listed(member(CHAT, "waiting"))
    changed()
    assert Notice.objects.get().data["event"] == "waiting"


def test_nobody_hears_of_a_workspace_without_its_owner(owner, settings):
    settings.WORKSPACE = "someone@example.com"
    told()
    assert not Seen.objects.exists()


@pytest.mark.parametrize(
    "data, hr, en",
    [
        (
            {
                "event": "waiting",
                "project": "ponistra",
                "chat": "Obavijesti kruga",
                "session": CHAT,
            },
            ("Chat čeka vašu odluku", "ponistra: Obavijesti kruga"),
            ("A chat waits for your decision", "ponistra: Obavijesti kruga"),
        ),
        (
            {"event": "said", "project": "ponistra", "chat": "Koordinator", "text": "Zeleno."},
            ("Koordinator javlja", "ponistra: Zeleno."),
            ("The coordinator reports", "ponistra: Zeleno."),
        ),
        (
            {
                "event": "asks",
                "project": "ponistra",
                "chat": "Koordinator",
                "session": LEAD,
                "text": "",
            },
            ("Koordinator čeka vaš unos", "ponistra: Koordinator"),
            ("The coordinator waits for your input", "ponistra: Koordinator"),
        ),
        (
            {"event": "ready", "project": None, "round": ROUND},
            ("Krug je spreman za objedinjavanje", f"Općenito: {ROUND}"),
            ("A round is ready to consolidate", f"General: {ROUND}"),
        ),
        (
            {"event": "consolidated", "project": "ponistra", "round": ROUND},
            ("Krug je objedinjen i čeka push", f"ponistra: {ROUND}"),
            ("A round is consolidated and waits for its push", f"ponistra: {ROUND}"),
        ),
        (
            {"event": "night", "project": "ponistra", "failed": 3},
            ("Noćna provjera nije prošla", "ponistra · palih testova: 3"),
            ("The night check failed", "ponistra · failed tests: 3"),
        ),
        (
            {"event": "limit", "window": "week", "name": None, "percent": 82},
            ("Limit pretplate je pri kraju", "Tjedni limit: 82 %"),
            ("The plan's limit is running out", "Weekly limit: 82%"),
        ),
        (
            {"event": "credits", "window": "model", "name": "Fable", "percent": 100},
            ("Troše se krediti", "Fable"),
            ("Credits are being spent", "Fable"),
        ),
        (
            {"event": "browser", "project": "ponistra", "failed": None},
            ("Provjera u pregledniku nije prošla", "ponistra"),
            ("The browser check failed", "ponistra"),
        ),
    ],
)
def test_each_event_is_worded_in_the_browsers_language_and_opens_the_code_page(data, hr, en):
    notice = Notice(kind=Notice.Kind.CODE, data=data)
    for language, (title, body) in (("hr", hr), ("en", en)):
        worded = notices.worded(notice, language, 0)
        assert (worded["title"], worded["body"], worded["url"]) == (title, body, "/workspace")


@pytest.mark.parametrize(
    "data",
    [
        {"event": "waiting", "project": "ponistra", "chat": "Obavijesti kruga", "session": CHAT},
        {
            "event": "asks",
            "project": "ponistra",
            "chat": "Koordinator",
            "session": CHAT,
            "text": "",
        },
    ],
)
def test_a_chat_waiting_is_answered_from_the_notification(data):
    notice = Notice(kind=Notice.Kind.CODE, data=data)
    for language, (yes, no) in (("hr", ("Da", "Ne")), ("en", ("Yes", "No"))):
        worded = notices.worded(notice, language, 0)
        assert worded["session"] == CHAT
        assert worded["actions"] == [
            {"action": "yes", "title": yes},
            {"action": "no", "title": no},
        ]


def test_what_only_reports_carries_no_answers():
    data = {"event": "said", "project": "ponistra", "chat": "Koordinator", "session": LEAD}
    worded = notices.worded(
        Notice(kind=Notice.Kind.CODE, data={**data, "text": "Zeleno."}), "hr", 0
    )
    assert "actions" not in worded and "session" not in worded
