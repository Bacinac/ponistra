import json
from math import inf
from urllib.parse import parse_qs, urlsplit

import pytest
from anyio import create_memory_object_stream, create_task_group, fail_after
from django.test import Client
from django.utils import timezone
from websockets.asyncio.server import serve

from apps.core.asyncdb import database
from apps.meetings.tests.test_rings import ORIGIN
from apps.users import sessions
from apps.users.models import User
from apps.users.sessions import CONFIRMED
from apps.workspace import terminal
from apps.workspace.views import CONFIRMED_FOR

FOLDER = "/home/owner/ponistra"
OWNER = "ivo@example.com"


@pytest.fixture
def linked(settings):
    settings.WORKSPACE = OWNER
    settings.WORKSPACE_TOKEN = "token"
    settings.WORKSPACE_URL = ""


def confirmed(client: Client, at=None) -> None:
    session = client.session
    session[CONFIRMED] = (at or timezone.now()).isoformat()
    session.save()


@database
def signed(email: str = OWNER, at=None) -> str:
    """The cookie of a browser signed in as the user, who confirmed who they are at the time."""
    user = User.objects.create_user(email, "Kamen-Most-Rijeka-71")
    client = Client()
    client.force_login(user)
    confirmed(client, at)
    return f"sessionid={client.cookies['sessionid'].value}"


class Workspace:
    """The workspace's end of the terminal: what it was asked with and typed, the shell echoing."""

    def __init__(self) -> None:
        self.asked = []
        self.typed = []
        self.sized = []
        self.left = False

    async def shell(self, connection) -> None:
        self.asked.append(connection.request)
        await connection.send(b"$ ")
        async for message in connection:
            if isinstance(message, str):
                self.sized.append(json.loads(message))
            elif message == b"exit\r":
                await connection.close(terminal.EXITED, "3")
                return
            else:
                self.typed.append(message)
                await connection.send(message)
        self.left = True


class Browser:
    def __init__(self, cookie: str, opening: dict, task_group) -> None:
        self.to_server, received = create_memory_object_stream[dict](inf)
        sent, self.from_server = create_memory_object_stream[dict](inf)
        headers = [
            (b"host", b"ponistra.example"),
            (b"origin", ORIGIN.encode()),
            (b"cookie", cookie.encode()),
        ]
        scope = {"type": "websocket", "path": terminal.PATH, "headers": headers}
        self.to_server.send_nowait({"type": "websocket.connect"})
        self.to_server.send_nowait({"type": "websocket.receive", "text": json.dumps(opening)})
        task_group.start_soon(terminal.socket, scope, received.receive, sent.send)

    async def message(self) -> dict:
        with fail_after(5):
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


@pytest.fixture
async def workspace(monkeypatch):
    shell = Workspace()
    async with serve(shell.shell, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        local = terminal.far

        def far(folder, cols, rows):
            return local(folder, cols, rows).replace("workspace:8081", f"127.0.0.1:{port}")

        monkeypatch.setattr(terminal, "far", far)
        yield shell


@pytest.mark.django_db
def test_the_owner_opens_a_terminal_only_under_a_recent_confirmation(api, settings):
    settings.WORKSPACE, settings.WORKSPACE_TOKEN = api.user.email, "token"
    confirmed(api, timezone.now() - CONFIRMED_FOR)
    answer = api.post("/api/workspace/terminal")
    assert (answer.status_code, answer.json()) == (403, {"error": "confirm_required"})
    confirmed(api, timezone.now() - sessions.CONFIRMED_FOR * 6)
    assert api.post("/api/workspace/terminal").json() == {"ok": True}


@pytest.mark.django_db
def test_nobody_but_the_owner_opens_a_terminal(api, settings):
    settings.WORKSPACE, settings.WORKSPACE_TOKEN = "owner@example.com", "token"
    confirmed(api)
    assert api.post("/api/workspace/terminal").status_code == 403


@pytest.mark.django_db
def test_a_workspace_without_a_token_opens_no_terminal(api, settings):
    settings.WORKSPACE, settings.WORKSPACE_TOKEN = api.user.email, ""
    confirmed(api)
    assert api.post("/api/workspace/terminal").json() == {"error": "workspace_not_linked"}


def test_a_workspace_elsewhere_opens_its_terminal_at_its_own_address(settings):
    settings.WORKSPACE_URL = "https://code.example/"
    assert terminal.far("/home/owner/a b", 80, 24) == (
        "wss://code.example/ponistra/terminal?folder=%2Fhome%2Fowner%2Fa+b&cols=80&rows=24"
    )


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_the_owners_terminal_passes_what_is_typed_and_shown_until_the_shell_ends(
    linked, workspace
):
    opening = {"folder": FOLDER, "cols": 120, "rows": 30}
    cookie = await signed()
    async with create_task_group() as tg:
        browser = Browser(cookie, opening, tg)
        assert await browser.shown() == b"$ "
        browser.type("ls č\r".encode())
        assert await browser.shown() == "ls č\r".encode()
        browser.to_server.send_nowait({"type": "websocket.receive", "text": "ping"})
        assert await browser.message() == {"type": "websocket.send", "text": "pong"}
        for size in ({"cols": 90, "rows": 20}, {"cols": 0, "rows": 20}):
            browser.to_server.send_nowait({"type": "websocket.receive", "text": json.dumps(size)})
        browser.type(b"exit\r")
        assert await browser.message() == {"type": "websocket.close", "code": 4000, "reason": "3"}
    request = workspace.asked[0]
    assert request.headers["Authorization"] == "Bearer token"
    address = urlsplit(request.path)
    assert address.path == "/ponistra/terminal"
    assert parse_qs(address.query) == {"folder": [FOLDER], "cols": ["120"], "rows": ["30"]}
    assert workspace.sized == [{"cols": 90, "rows": 20}]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_browser_that_leaves_ends_the_shell(linked, workspace):
    opening = {"folder": FOLDER, "cols": 80, "rows": 24}
    cookie = await signed()
    async with create_task_group() as tg:
        browser = Browser(cookie, opening, tg)
        assert await browser.shown() == b"$ "
        browser.to_server.send_nowait({"type": "websocket.disconnect", "code": 1001})
        assert (await browser.message())["type"] == "websocket.close"
    assert workspace.left


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_only_the_owner_freshly_confirmed_opens_a_terminal(linked, workspace):
    opening = {"folder": FOLDER, "cols": 80, "rows": 24}
    async with create_task_group() as tg:
        stale = Browser(await signed(at=timezone.now() - CONFIRMED_FOR), opening, tg)
        assert (await stale.message())["code"] == terminal.REFUSED
        other = Browser(await signed("someone@example.com"), opening, tg)
        assert (await other.message())["code"] == terminal.REFUSED
    assert workspace.asked == []


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_an_unreachable_workspace_closes_the_terminal(linked, monkeypatch):
    monkeypatch.setattr(terminal, "far", lambda *_: "ws://127.0.0.1:9/ponistra/terminal")
    opening = {"folder": FOLDER, "cols": 80, "rows": 24}
    cookie = await signed()
    async with create_task_group() as tg:
        browser = Browser(cookie, opening, tg)
        assert (await browser.message())["code"] == terminal.UNREACHABLE
