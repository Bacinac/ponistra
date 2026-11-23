import json
import uuid

import pytest
from anyio import create_memory_object_stream, create_task_group, fail_after
from asgiref.sync import sync_to_async
from django.db import connections
from django.test import AsyncClient, Client
from django.utils import timezone

from apps.access.tests.test_access import JSON, person
from apps.containers import reach, shell
from apps.containers.engine import Process
from apps.containers.models import Host
from apps.core.asyncdb import database
from apps.locations import sftp
from apps.locations.models import Location
from apps.locations.remote import Failed
from apps.meetings.tests.test_rings import ORIGIN
from apps.users.models import User
from apps.users.sessions import CONFIRMED

pytestmark = pytest.mark.django_db

SERVER = {"host": "dockerhost", "username": "dock", "password": "dockdock"}
STACK = """services:
  app:
    image: ponistra/test:1
    pull_policy: never
    command: ["sh", "-c", "echo zdravo; exec sleep 3600"]
    stop_grace_period: 1s
"""


def confirmed(client: Client) -> None:
    session = client.session
    session[CONFIRMED] = timezone.now().isoformat()
    session.save()


def _target(path: str = "") -> sftp.Target:
    return sftp.Target("dockerhost", 22, "dock", path, "dockdock", None, "", "")


async def _on_server(work, path: str = ""):
    link = sftp.Connection(_target(path))
    await link.open()
    try:
        return await work(sftp.Sftp(link))
    finally:
        link.end(Failed("location_closed"))


async def _text(text: str):
    yield text.encode()


async def _keys(server, text: str) -> None:
    if any(entry.name == "authorized_keys" for entry in await server.listed(".ssh")):
        await server.remove(".ssh/authorized_keys")
    await server.put(".ssh/authorized_keys", _text(text))


async def _stack_folder() -> str:
    name = f"s{uuid.uuid4().hex[:12]}"

    async def made(server):
        await server.mkdir(f"stacks/{name}")
        await server.put(f"stacks/{name}/compose.yaml", _text(STACK))

    await _on_server(made)
    return name


async def _trusted(line: str) -> None:
    await _on_server(lambda server: _keys(server, f"{line}\n"))


def _administrator(client) -> None:
    client.user.is_staff = True
    client.user.save()
    confirmed(client)


def _location(client, **changed) -> dict:
    given = {"kind": "sftp", "name": "Docker", "auth": "password", "path": "stacks"} | SERVER
    response = client.post("/api/locations", given | changed, content_type=JSON)
    assert response.status_code == 201, response.json()
    return response.json()


def test_only_an_administrator_owning_an_sftp_location_makes_it_a_docker_host(api):
    confirmed(api)
    location = Location.objects.create(
        owner=api.user,
        name="Docker",
        kind="sftp",
        host="dockerhost",
        port=22,
        username="dock",
        auth="password",
        secret=b"",
    )
    given = {"location": str(location.pk)}
    assert api.post("/api/containers/hosts", given, content_type=JSON).status_code == 403
    assert api.get("/api/containers/hosts").status_code == 403
    _administrator(api)
    listed = api.get("/api/containers/hosts").json()
    assert listed == {"hosts": [], "candidates": [{"id": str(location.pk), "name": "Docker"}]}
    made = api.post("/api/containers/hosts", given, content_type=JSON)
    assert made.status_code == 201
    shown = made.json()
    assert (
        shown["public_key"].startswith("ssh-ed25519 ")
        and " ponistra-docker@" in shown["public_key"]
    )
    assert shown["authorized"].startswith('restrict,command="c=$SSH_ORIGINAL_COMMAND; ')
    assert shown["authorized"].endswith(f'" {shown["public_key"]}')
    assert b"PRIVATE KEY" not in bytes(Host.objects.get().secret)
    again = api.post("/api/containers/hosts", given, content_type=JSON)
    assert (again.status_code, again.json()) == (409, {"error": "docker_host_exists"})
    assert api.get("/api/containers/hosts").json()["candidates"] == []

    theirs = person("ana@example.com")
    _administrator(theirs)
    assert theirs.get(f"/api/containers/hosts/{location.pk}").status_code == 404
    assert theirs.get("/api/containers/hosts").json()["hosts"] == []
    assert api.delete(f"/api/containers/hosts/{location.pk}").status_code == 204
    assert Location.objects.filter(pk=location.pk).exists() and not Host.objects.exists()


def test_a_smb_location_is_no_docker_host(api):
    _administrator(api)
    location = Location.objects.create(
        owner=api.user,
        name="Dijeljeno",
        kind="smb",
        host="nas",
        port=445,
        username="ivo",
        auth="password",
        secret=b"",
    )
    made = api.post("/api/containers/hosts", {"location": str(location.pk)}, content_type=JSON)
    assert made.json() == {"error": "docker_needs_sftp"}


def test_the_forced_command_takes_a_folder_as_it_is():
    line = reach.authorized("ssh-ed25519 AAAA ponistra")
    command = line.removeprefix('restrict,command="').removesuffix('" ssh-ed25519 AAAA ponistra')
    assert '\\"$d\\"' in command and '"' not in command.replace('\\"', "")
    assert command.replace('\\"', '"') == reach.COMMAND


@pytest.mark.xdist_group("docker")
@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_stack_is_brought_up_watched_stopped_and_taken_down_on_the_host():
    user = await sync_to_async(User.objects.create_user)(
        "ivo@example.com", "Kamen-Most-Rijeka-71", is_staff=True
    )
    browser = AsyncClient()
    await browser.aforce_login(user)
    session = await browser.asession()
    await session.aset(CONFIRMED, timezone.now().isoformat())
    await session.asave()
    name = await _stack_folder()
    given = {"kind": "sftp", "name": "Docker", "auth": "password", "path": "stacks"} | SERVER
    location = (await browser.post("/api/locations", given, content_type=JSON)).json()
    base = f"/api/containers/hosts/{location['id']}"
    try:
        made = await browser.post(
            "/api/containers/hosts", {"location": location["id"]}, content_type=JSON
        )
        unknown = await browser.get(base)
        assert (unknown.status_code, unknown.json()) == (409, {"error": "location_login"})
        await _trusted(made.json()["authorized"])
        host = (await browser.get(base)).json()
        assert host["version"] and host["api"]

        held = await database(lambda: reach.host(user, location["id"]))()
        refused = await Process(reach.target(held), "id").open()
        assert await refused.ended() == 126
        assert (await refused.failure()).error == "docker_command_refused"
        refused.close()

        empty = (await browser.get(f"{base}/stack", {"path": ""})).json()
        assert empty == {"file": None, "containers": [], "said": []}
        found = (await browser.get(f"{base}/stack", {"path": name})).json()
        assert (found["file"], found["containers"]) == ("compose.yaml", [])

        up = await browser.post(f"{base}/stack?path={name}", {"verb": "up"}, content_type=JSON)
        streamed = b"".join([each async for each in up.streaming_content])
        said = [json.loads(line) for line in streamed.splitlines()]
        assert said[-1] == {"status": 0}, said
        running = (await browser.get(f"{base}/stack", {"path": name})).json()["containers"]
        assert [(each["service"], each["state"]) for each in running] == [("app", "running")]
        container = running[0]["id"]

        everything = (await browser.get(f"{base}/containers")).json()["containers"]
        mine = next(each for each in everything if each["id"].startswith(container))
        assert (mine["project"], mine["service"]) == (name, "app")
        images = (await browser.get(f"{base}/images")).json()["images"]
        assert any("ponistra/test:1" in each["tags"] and each["used"] for each in images)
        networks = (await browser.get(f"{base}/networks")).json()["networks"]
        assert any(each["name"] == "bridge" and each["built_in"] for each in networks)
        assert any(each["project"] == name and each["used"] for each in networks)
        assert "volumes" in (await browser.get(f"{base}/volumes")).json()

        await _shelled(browser.cookies["sessionid"].value, location["id"], container)

        stopped = await browser.post(f"{base}/containers/{container}/stop")
        assert stopped.status_code == 204
        logs = await browser.get(f"{base}/containers/{container}/logs", {"tail": "50"})
        text = b"".join([each async for each in logs.streaming_content]).decode()
        assert "zdravo" in text
        exited = (await browser.get(f"{base}/stack", {"path": name})).json()["containers"]
        assert exited[0]["state"] == "exited"

        down = await browser.post(f"{base}/stack?path={name}", {"verb": "down"}, content_type=JSON)
        assert b'{"status": 0}' in b"".join([each async for each in down.streaming_content])
        gone = (await browser.get(f"{base}/stack", {"path": name})).json()["containers"]
        assert gone == []
        pruned = await browser.post(f"{base}/prune", {"kind": "networks"}, content_type=JSON)
        assert pruned.status_code == 200 and "reclaimed" in pruned.json()
        missing = await browser.post(f"{base}/containers/{container}/start")
        assert missing.status_code == 404 and missing.json()["error"] == "docker_not_found"
    finally:
        down = await browser.post(f"{base}/stack?path={name}", {"verb": "down"}, content_type=JSON)
        [each async for each in down.streaming_content]
        sftp.ended("")
        await sync_to_async(connections.close_all)()


class Browser:
    """The page's end of a shell's socket."""

    def __init__(self, cookie: str, opening: dict, task_group) -> None:
        self.to_server, received = create_memory_object_stream[dict](100)
        sent, self.from_server = create_memory_object_stream[dict](100)
        headers = [
            (b"host", b"ponistra.example"),
            (b"origin", ORIGIN.encode()),
            (b"cookie", cookie.encode()),
        ]
        scope = {"type": "websocket", "path": shell.PATH, "headers": headers}
        self.to_server.send_nowait({"type": "websocket.connect"})
        self.to_server.send_nowait({"type": "websocket.receive", "text": json.dumps(opening)})
        task_group.start_soon(shell.socket, scope, received.receive, sent.send)

    async def message(self) -> dict:
        with fail_after(20):
            message = await self.from_server.receive()
            while message["type"] == "websocket.accept":
                message = await self.from_server.receive()
        return message

    async def shown(self) -> bytes:
        message = await self.message()
        assert message["type"] == "websocket.send", message
        return message["bytes"]

    def type(self, data: bytes) -> None:
        self.to_server.send_nowait({"type": "websocket.receive", "bytes": data})


async def _shelled(session: str, location: str, container: str) -> None:
    cookie = f"sessionid={session}"
    opening = {"host": location, "container": container, "cols": 100, "rows": 30}
    async with create_task_group() as tg:
        browser = Browser(cookie, opening, tg)
        shown = b""
        browser.type(b"echo $((6*7))\r")
        while b"42" not in shown:
            shown += await browser.shown()
        browser.type(b"exit 3\r")
        while (message := await browser.message())["type"] == "websocket.send":
            pass
        assert message == {"type": "websocket.close", "code": shell.EXITED, "reason": "3"}


@pytest.mark.parametrize("verb", ["build", "up; id", ""])
def test_only_the_verbs_of_a_stack_are_run(api, verb):
    _administrator(api)
    location = _location(api)
    Host.objects.create(location_id=location["id"], secret=b"", public_key="")
    answer = api.post(
        f"/api/containers/hosts/{location['id']}/stack?path=x", {"verb": verb}, content_type=JSON
    )
    assert answer.json() == {"error": "invalid_verb"}
