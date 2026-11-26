import json
import uuid

import pytest
from django.utils import timezone

from apps.access.models import Role
from apps.access.tests.test_access import JSON, person
from apps.blobs.tests.uploads import uploaded
from apps.computers import link, streams
from apps.computers.models import Computer, Manager
from apps.core.api import Refused
from apps.files.sources import source

from .test_locations import on_server, target
from .test_streamed import Piped

pytestmark = pytest.mark.django_db

GUESTS = [
    {"name": "web", "kind": "lxc", "status": "Running"},
    {"name": "baza", "kind": "vm", "status": "Stopped"},
    {"name": "novi", "kind": "lxc", "status": "Creating"},
    {"name": "ivin", "kind": "lxc", "status": "Running", "owner": "ivo@example.com"},
    {"name": "anin", "kind": "lxc", "status": "Running", "owner": "ana@example.com"},
]


@pytest.fixture
def place():
    """A folder of the test server for one test alone, as the guest's root sees it."""
    name = uuid.uuid4().hex
    on_server(lambda server: server.mkdir(name))
    yield f"home/sftp/files/{name}"
    on_server(lambda server: server.remove(name))


@pytest.fixture
def machine(api):
    found = Computer.objects.create(name="ured", token="t" * 64)
    Manager.objects.create(computer=found, user=api.user)
    return found


@pytest.fixture
def agent(monkeypatch):
    """The machine's agent behind its link: its guests, and each stream it opens the test
    server's SFTP, or the refusal set for it."""
    asked: list[tuple] = []
    refusal: list[streams.Refused] = []

    async def requested(computer, method, path, account, body=None):
        asked.append((method, path, account))
        return 200, "application/json", json.dumps(GUESTS).encode()

    async def opened(computer, method, path, account):
        asked.append((method, path, account))
        if refusal:
            raise refusal[0]
        return await Piped(target("")).opened()

    monkeypatch.setattr(link, "requested", requested)
    monkeypatch.setattr(streams, "opened", opened)
    return asked, refusal


def at(machine, guest: str = "web") -> str:
    return f"/api/guests/{machine.pk}/{guest}"


def test_the_guests_offered_are_the_managed_machines_but_those_being_made_or_anothers(
    api, machine, agent
):
    person("ana@example.com")
    listed = api.get("/api/guests").json()["computers"]
    assert listed == [
        {
            "id": str(machine.pk),
            "name": "ured",
            "guests": [
                {"name": "baza", "kind": "vm", "status": "Stopped"},
                {"name": "ivin", "kind": "lxc", "status": "Running"},
                {"name": "web", "kind": "lxc", "status": "Running"},
            ],
        }
    ]
    assert agent[0] == [("GET", "/v1/guests", "ivo@example.com")]


def test_a_machine_off_its_link_is_listed_with_why(api, machine, monkeypatch):
    async def requested(computer, method, path, account, body=None):
        return 503, "application/json", b'{"error":"computer_offline"}'

    monkeypatch.setattr(link, "requested", requested)
    listed = api.get("/api/guests").json()["computers"]
    assert listed == [
        {"id": str(machine.pk), "name": "ured", "guests": [], "error": "guest_offline"}
    ]


def test_a_guests_files_are_listed_written_renamed_and_read_over_its_link(
    api, machine, agent, place
):
    folder = place
    sent = {"path": folder, "name": "a.txt", "blob": uploaded(api, b"Ponistra")["sha256"]}
    assert api.post(f"{at(machine)}/put", sent, content_type=JSON).status_code == 201
    renamed = {"path": f"{folder}/a.txt", "to": f"{folder}/b.txt"}
    assert api.post(f"{at(machine)}/rename", renamed, content_type=JSON).status_code == 200
    listed = api.get(f"{at(machine)}/files", {"path": folder}).json()["entries"]
    assert [(each["name"], each["size"]) for each in listed] == [("b.txt", 8)]
    read = api.get(f"{at(machine)}/text", {"path": f"{folder}/b.txt"}).json()
    assert (read["kind"], read["text"]) == ("text", "Ponistra")
    top = api.get(f"{at(machine)}/files").json()
    assert top["path"] == "" and "home" in [each["name"] for each in top["entries"]]
    assert ("GET", "/v1/guests/web/sftp", "ivo@example.com") in agent[0]


@pytest.mark.parametrize(
    ("status", "error", "answer"),
    [
        (502, "not for this account: the files of anin are its owner's", (403, "guest_owned")),
        (502, "no such guest or snapshot", (404, "guest_missing")),
        (
            502,
            "not possible in the guest's current state: a VM's files open while it runs",
            (409, "guest_not_running"),
        ),
        (502, "guests are unavailable: Incus is not running", (503, "guest_unavailable")),
        (503, "computer_offline", (503, "guest_offline")),
    ],
)
def test_a_refusal_before_the_session_says_why(api, machine, agent, status, error, answer):
    agent[1].append(streams.Refused(status, error))
    refused = api.get(f"{at(machine, 'anin')}/files")
    assert (refused.status_code, refused.json()["error"]) == answer


def test_a_machine_that_left_offers_no_guests(api, machine, agent):
    Computer.objects.filter(pk=machine.pk).update(left_at=timezone.now())
    assert api.get("/api/guests").json() == {"computers": []}
    assert api.get(f"{at(machine)}/files").status_code == 404


def test_who_does_not_manage_the_machine_reaches_none_of_its_guests(machine, agent):
    ana = person("ana@example.com")
    assert ana.get("/api/guests").json() == {"computers": []}
    assert ana.get(f"{at(machine)}/files").status_code == 404
    assert agent[0] == []
    with pytest.raises(Refused):
        source(ana.user, f"computer:{machine.pk}/web")


def test_a_guest_is_a_source_of_files_by_its_key(api, machine):
    found = source(api.user, f"computer:{machine.pk}/web", Role.EDIT)
    assert (found.key, found.kind, found.name) == (f"computer:{machine.pk}/web", "computer", "web")
    with pytest.raises(Refused):
        source(api.user, f"computer:{machine.pk}/../etc")
