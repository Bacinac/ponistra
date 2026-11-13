import json
from functools import partial
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from apps.agents import tools
from apps.memory import ledger, night
from apps.memory.models import Advice, Analysed, Nightly, Proposal
from apps.push.models import Notice, Subscription
from apps.push.notices import worded
from apps.workspace.models import Command

pytestmark = pytest.mark.django_db

JSON = "application/json"
STORE = "-mnt-docker-ponistra"
FOLDER = "/mnt/docker/ponistra"
OLD = "---\nname: project-a\n---\n\nS1 11.11.2026 na devu necommitano (`apps/a.py`).\n"
NEW = "---\nname: project-a\n---\n\nS1 11.11.2026 commitano `abc1234` (`apps/a.py`).\n"
INDEX = "- [project-a](project_a.md) — S1\n"


class Workspace:
    """The workspace's memory as its service answers: files by store, the mechanical proposals it
    reads from them, what it was asked to write and the chats it was asked to start."""

    def __init__(self):
        self.files = {(STORE, "project_a.md"): OLD, (STORE, "MEMORY.md"): INDEX}
        self.proposed = True
        self.commands = []

    def listed(self) -> dict:
        hashes = {file: ledger.hash_of(text) for (_store, file), text in self.files.items()}
        proposals = []
        if self.proposed and self.files.get((STORE, "project_a.md")) == OLD:
            proposals.append(
                {
                    "store": STORE,
                    "file": "project_a.md",
                    "hash": ledger.hash_of(OLD),
                    "before": OLD,
                    "after": NEW,
                    "kind": "state",
                    "detail": "abc1234",
                }
            )
        return {
            "root": "/mnt/docker",
            "stores": [
                {
                    "store": STORE,
                    "folder": FOLDER,
                    "files": 1,
                    "bytes": 100,
                    "index": {"lines": 1, "bytes": 40, "tokens": 10, "cut": 0},
                    "findings": [{"file": "project_a.md", "kind": "stale", "detail": "b.py"}],
                    "hashes": hashes,
                }
            ],
            "proposals": proposals,
            "global": {"hash": ""},
        }

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = urlsplit(str(request.url)).path.removeprefix("/ponistra/")
        if path == "memory":
            return httpx2.Response(200, json=self.listed())
        if path == "memory/file":
            asked = {key: values[0] for key, values in parse_qs(request.url.query.decode()).items()}
            text = self.files.get((asked["store"], asked["file"]))
            return httpx2.Response(200, json={"text": text, "hash": ledger.hash_of(text)})
        if path == "memory/write":
            asked = json.loads(request.content)
            where = (asked["store"], asked["file"])
            if ledger.hash_of(self.files.get(where)) != asked["hash"]:
                return httpx2.Response(409, json={"error": "changed"})
            if asked["text"] is None:
                self.files.pop(where)
            else:
                self.files[where] = asked["text"]
            return httpx2.Response(200, json={"hash": ledger.hash_of(asked["text"])})
        if path == "commands":
            self.commands.append(json.loads(request.content))
            return httpx2.Response(200, json={"state": "taken", "session": None})
        return httpx2.Response(404, json={"error": "not_found"})


@pytest.fixture
def workspace(settings, monkeypatch):
    settings.WORKSPACE_TOKEN = "token"
    held = Workspace()
    monkeypatch.setattr(
        "apps.workspace.views.httpx2.AsyncClient",
        partial(httpx2.AsyncClient, transport=httpx2.MockTransport(held)),
    )
    return held


@pytest.fixture
def owner(api, settings):
    settings.WORKSPACE = api.user.email
    return api


def test_the_owner_reads_each_store_and_its_mechanical_proposals_once(owner, workspace):
    read = owner.get("/api/memory").json()
    [store] = read["stores"]
    assert (store["store"], store["files"], store["proposals"], store["unanalysed"]) == (
        STORE,
        1,
        1,
        2,
    )
    assert store["findings"] == [{"file": "project_a.md", "kind": "stale", "detail": "b.py"}]
    [proposal] = read["proposals"]
    assert (proposal["file"], proposal["kind"], proposal["source"]) == (
        "project_a.md",
        "state",
        "mechanical",
    )
    changed = [line for line in proposal["diff"] if line["op"] in "+-"]
    assert [line["op"] for line in changed] == ["-", "+"]
    owner.get("/api/memory")
    assert Proposal.objects.count() == 1
    assert owner.get("/api/memory/waiting").json() == {"count": 1}


def test_nobody_but_the_owner_reads_the_memory(api, settings, workspace):
    settings.WORKSPACE = "owner@example.com"
    refused = api.get("/api/memory")
    assert (refused.status_code, refused.json()) == (403, {"error": "not_the_owner"})


def test_an_accepted_proposal_is_written_and_taken_back_from_the_history(owner, workspace):
    [proposal] = owner.get("/api/memory").json()["proposals"]
    accepted = owner.post(f"/api/memory/proposals/{proposal['id']}", {"text": "yes"}, JSON)
    assert accepted.json()["state"] == "applied"
    assert workspace.files[(STORE, "project_a.md")] == NEW
    read = owner.get("/api/memory").json()
    assert read["proposals"] == []
    assert [each["state"] for each in read["history"]] == ["applied"]
    reverted = owner.post(f"/api/memory/proposals/{proposal['id']}/revert", {}, JSON)
    assert reverted.json()["state"] == "reverted"
    assert workspace.files[(STORE, "project_a.md")] == OLD


def test_a_rejected_proposal_is_not_proposed_again(owner, workspace):
    [proposal] = owner.get("/api/memory").json()["proposals"]
    owner.post(f"/api/memory/proposals/{proposal['id']}", {"text": "no"}, JSON)
    assert owner.get("/api/memory").json()["proposals"] == []
    again = owner.post(f"/api/memory/proposals/{proposal['id']}", {"text": "yes"}, JSON)
    assert (again.status_code, again.json()) == (409, {"error": "memory_decided"})


def test_a_file_changed_since_it_was_read_on_the_same_line_is_not_written(owner, workspace):
    [proposal] = owner.get("/api/memory").json()["proposals"]
    changed = OLD.replace("S1 11.11.2026", "S1 12.11.2026")
    workspace.files[(STORE, "project_a.md")] = changed
    workspace.proposed = False
    refused = owner.post(f"/api/memory/proposals/{proposal['id']}", {"text": "yes"}, JSON)
    assert (refused.status_code, refused.json()) == (409, {"error": "memory_changed"})
    assert workspace.files[(STORE, "project_a.md")] == changed
    assert Proposal.objects.get().state == Proposal.State.STALE


def test_a_file_changed_since_on_other_lines_takes_the_proposal_over_that_change(owner, workspace):
    [proposal] = owner.get("/api/memory").json()["proposals"]
    workspace.files[(STORE, "project_a.md")] = OLD + "\nIvo je dopisao redak.\n"
    accepted = owner.post(f"/api/memory/proposals/{proposal['id']}", {"text": "yes"}, JSON)
    assert accepted.json()["state"] == "applied"
    assert workspace.files[(STORE, "project_a.md")] == NEW + "\nIvo je dopisao redak.\n"
    owner.post(f"/api/memory/proposals/{proposal['id']}/revert", {}, JSON)
    assert workspace.files[(STORE, "project_a.md")] == OLD + "\nIvo je dopisao redak.\n"


def test_changes_merge_only_where_they_touch_different_lines():
    base = "a\nb\nc\nd\n"
    assert ledger.merged(base, "A\nb\nc\nd\n", "a\nb\nc\nD\n") == "A\nb\nc\nD\n"
    assert ledger.merged(base, "a\nb\nC\nd\n", "a\nB\nc\nd\n") == "a\nB\nC\nd\n"
    assert ledger.merged(base, "a\nB\nc\nd\n", "a\nb2\nc\nd\n") is None
    assert ledger.merged(base, "a\nx\nb\nc\nd\n", "a\ny\nb\nc\nd\n") is None


def test_a_proposal_the_workspace_no_longer_reads_goes_stale(owner, workspace):
    owner.get("/api/memory")
    workspace.proposed = False
    assert owner.get("/api/memory").json()["proposals"] == []
    assert Proposal.objects.get().state == Proposal.State.STALE


def test_a_reverted_change_is_refused_once_the_file_moved_on(owner, workspace):
    [proposal] = owner.get("/api/memory").json()["proposals"]
    owner.post(f"/api/memory/proposals/{proposal['id']}", {"text": "yes"}, JSON)
    workspace.files[(STORE, "project_a.md")] = NEW + "više\n"
    refused = owner.post(f"/api/memory/proposals/{proposal['id']}/revert", {}, JSON)
    assert (refused.status_code, refused.json()) == (409, {"error": "memory_changed"})
    assert Proposal.objects.get().state == Proposal.State.APPLIED


def test_an_agent_proposes_edits_to_the_file_as_it_is_now(owner, workspace):
    said = tools._memory_proposed(
        owner.user,
        STORE,
        "MEMORY.md",
        "Kraći redak.",
        [{"old_text": "— S1", "new_text": "— S1 gotov"}],
        None,
        False,
    )
    proposal = Proposal.objects.get(pk=said["proposal"])
    assert (proposal.source, proposal.before, proposal.after) == (
        "session",
        INDEX,
        "- [project-a](project_a.md) — S1 gotov\n",
    )
    with pytest.raises(ledger.Refused) as missing:
        ledger.proposed(STORE, "MEMORY.md", "x", edits=[{"old_text": "nema", "new_text": "y"}])
    assert missing.value.error == "old_text_not_found"
    removed = ledger.proposed(STORE, "project_a.md", "Duplikat.", remove=True)
    owner.post(f"/api/memory/proposals/{removed.pk}", {"text": "yes"}, JSON)
    assert (STORE, "project_a.md") not in workspace.files


def test_only_the_workspaces_owner_proposes_to_its_memory(api, settings, workspace):
    settings.WORKSPACE = "owner@example.com"
    with pytest.raises(ledger.Refused) as refused:
        tools._memory_proposed(api.user, STORE, "MEMORY.md", "x", None, "y", False)
    assert refused.value.error == "not_the_workspace_owner"


def test_an_analysis_starts_a_chat_over_the_files_changed_since_the_last(owner, workspace):
    asked = owner.post("/api/memory/analyse", {"store": STORE}, JSON)
    assert asked.json()["state"] == "taken"
    [command] = workspace.commands
    assert (command["kind"], command["folder"]) == ("chat", FOLDER)
    assert f"- {STORE}/project_a.md" in command["text"]
    assert "propose_memory" in command["text"]
    assert Analysed.objects.count() == 2
    refused = owner.post("/api/memory/analyse", {}, JSON)
    assert (refused.status_code, refused.json()) == (409, {"error": "memory_analysed"})
    workspace.files[(STORE, "MEMORY.md")] = INDEX + "- novo\n"
    owner.post("/api/memory/analyse", {}, JSON)
    assert workspace.commands[1]["folder"] == "/mnt/docker"
    assert f"- {STORE}/MEMORY.md" in workspace.commands[1]["text"]
    assert "project_a.md" not in workspace.commands[1]["text"]
    assert Command.objects.count() == 2


def _two_in_one_file(workspace) -> tuple[Proposal, Proposal]:
    text = OLD + "\nVidi [[project-old]].\n"
    workspace.files[(STORE, "project_a.md")] = text
    workspace.proposed = False
    first = ledger.proposed(
        STORE, "project_a.md", "Stanje.", text=NEW + "\nVidi [[project-old]].\n"
    )
    second = ledger.proposed(
        STORE, "project_a.md", "Poveznica.", text=OLD + "\nVidi [[project-b]].\n"
    )
    return first, second


def test_a_review_starts_a_chat_that_reads_the_open_proposals_and_groups_them(owner, workspace):
    first, second = _two_in_one_file(workspace)
    asked = owner.post("/api/memory/review", {}, JSON)
    assert asked.json()["state"] == "taken"
    [command] = workspace.commands
    assert (command["kind"], command["folder"]) == ("chat", "/mnt/docker")
    assert "memory_proposals" in command["text"] and "advise_memory" in command["text"]
    read = tools._memory_waiting(owner.user)["proposals"]
    assert [each["id"] for each in read] == [first.pk, second.pk]
    assert read[1]["changes"] == [{"old": "Vidi [[project-old]].", "new": "Vidi [[project-b]]."}]
    said = tools._memory_advised(
        owner.user,
        [
            {
                "title": "Stanje",
                "reason": "Git to potvrđuje.",
                "action": "accept",
                "proposals": [first.pk],
            },
            {
                "title": "Poveznice",
                "reason": "Vode na postojeće.",
                "action": "accept",
                "proposals": [second.pk],
            },
        ],
    )
    assert said == {"groups": 2}
    advice = owner.get("/api/memory").json()["advice"]
    assert [(each["title"], each["proposals"]) for each in advice] == [
        ("Stanje", [first.pk]),
        ("Poveznice", [second.pk]),
    ]


def test_a_group_accepted_at_once_writes_two_proposals_of_one_file_over_each_other(
    owner, workspace
):
    first, second = _two_in_one_file(workspace)
    [group] = ledger.advised(
        [
            {
                "title": "Sve",
                "reason": "Ispravno.",
                "action": "accept",
                "proposals": [first.pk, second.pk],
            }
        ]
    )
    followed = owner.post(f"/api/memory/advice/{group.pk}", {"text": "yes"}, JSON)
    assert followed.json() == {"applied": 2, "rejected": 0, "stale": 0}
    assert workspace.files[(STORE, "project_a.md")] == NEW + "\nVidi [[project-b]].\n"
    assert owner.get("/api/memory").json()["advice"] == []


def test_a_group_rejected_at_once_writes_nothing(owner, workspace):
    first, second = _two_in_one_file(workspace)
    [group] = ledger.advised(
        [
            {
                "title": "Sve",
                "reason": "Krivo.",
                "action": "reject",
                "proposals": [first.pk, second.pk],
            }
        ]
    )
    followed = owner.post(f"/api/memory/advice/{group.pk}", {"text": "no"}, JSON)
    assert followed.json() == {"applied": 0, "rejected": 2, "stale": 0}
    assert workspace.files[(STORE, "project_a.md")] == OLD + "\nVidi [[project-old]].\n"


def test_advice_names_each_open_proposal_once_and_replaces_the_advice_before(owner, workspace):
    first, second = _two_in_one_file(workspace)
    group = {"title": "A", "reason": "B.", "action": "look", "proposals": [first.pk]}
    for groups, error in [
        ([], "invalid_groups"),
        ([{**group, "action": "maybe"}], "invalid_action"),
        ([group, group], "proposal_in_two_groups"),
        ([{**group, "proposals": [first.pk + 999]}], "unknown_proposal"),
    ]:
        with pytest.raises(ledger.Refused) as refused:
            ledger.advised(groups)
        assert refused.value.error == error
    ledger.advised([group])
    owner.post(f"/api/memory/proposals/{second.pk}", {"text": "no"}, JSON)
    ledger.advised([group, {**group, "title": "C", "proposals": [second.pk]}])
    assert list(Advice.objects.values_list("title", flat=True)) == ["A"]
    with pytest.raises(ledger.Refused) as refused:
        tools._memory_advised(owner.user.__class__(email="x@example.com"), [group])
    assert refused.value.error == "not_the_workspace_owner"


def test_a_review_needs_open_proposals(owner, workspace):
    workspace.proposed = False
    refused = owner.post("/api/memory/review", {}, JSON)
    assert (refused.status_code, refused.json()) == (409, {"error": "memory_nothing_waiting"})


def test_the_owner_hears_of_a_new_proposal_and_answers_it_from_the_notification(owner, workspace):
    Subscription.objects.create(
        user=owner.user, endpoint="https://push.example.com/1", p256dh=b"k", auth=b"a"
    )
    ledger.heard()
    [notice] = Notice.objects.all()
    shown = worded(notice, "hr", 0)
    proposal = Proposal.objects.get()
    assert shown["title"] == "Prijedlog za memoriju"
    assert shown["answer"] == f"/api/memory/proposals/{proposal.pk}"
    assert [action["action"] for action in shown["actions"]] == ["yes", "no"]
    assert shown["url"] == "/workspace?view=memory"
    ledger.heard()
    assert Notice.objects.count() == 1
    owner.post(shown["answer"], {"text": "yes"}, JSON)
    assert workspace.files[(STORE, "project_a.md")] == NEW


def test_the_workspace_tells_of_a_change_only_with_its_token(client, workspace):
    refused = client.post("/api/memory/changed", {}, JSON, headers={"Authorization": "Bearer x"})
    assert refused.status_code == 403
    told = client.post("/api/memory/changed", {}, JSON, headers={"Authorization": "Bearer token"})
    assert told.status_code == 204


def test_the_nightly_pass_runs_once_a_night_only_when_turned_on(owner, workspace, monkeypatch):
    class Four:
        hour = night.HOUR

        @staticmethod
        def date():
            return __import__("datetime").date(2026, 11, 13)

    monkeypatch.setattr(night.timezone, "localtime", lambda: Four)
    night.passed()
    assert workspace.commands == [] and Proposal.objects.count() == 0
    assert owner.post("/api/memory/nightly", {"on": True}, JSON).json() == {"nightly": True}
    night.passed()
    night.passed()
    assert len(workspace.commands) == 1
    assert Proposal.objects.count() == 1
    assert Nightly.objects.get().last.isoformat() == "2026-11-13"


def test_the_owner_hears_that_the_advice_is_ready(owner, workspace):
    Subscription.objects.create(
        user=owner.user, endpoint="https://push.example.com/1", p256dh=b"k", auth=b"a"
    )
    first, _second = _two_in_one_file(workspace)
    ledger.advised([{"title": "A", "reason": "B.", "action": "accept", "proposals": [first.pk]}])
    [notice] = Notice.objects.all()
    shown = worded(notice, "hr", 0)
    assert (shown["title"], shown["url"]) == (
        "Preporuke za prijedloge memorije: 1",
        "/workspace?view=memory",
    )
