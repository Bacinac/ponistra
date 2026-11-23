"""A shell in a container of a Docker host (D55), for an administrator freshly confirmed (D33):
an exec of the Engine API with a terminal, its stream hijacked over the same ssh, spoken to the
page as the workspace's terminal speaks (`apps.workspace.terminal`), which the page asks first
over POST for the confirmation:

    browser → {"host": <location id>, "container": <id>, "cols": …, "rows": …}
    then binary frames both ways; {"cols": …, "rows": …} resizes; {"close": true} ends it;
    "ping" is answered "pong".

The socket closes with EXITED once the shell exits (its status the reason), REFUSED for anyone
else, MISSING for a container that is gone or not running, UNREACHABLE when the host was not."""

import asyncio
import json
import logging
from contextlib import suppress
from importlib import import_module

from django.conf import settings
from django.http import HttpResponse

from apps.access.models import Role
from apps.collab.server import Signed, refuse, same_origin, signed_in
from apps.core.api import Refused, api
from apps.core.asyncdb import database
from apps.locations.remote import Failed
from apps.users.models import User
from apps.users.sessions import CONFIRMED, fresh

from . import reach
from .engine import Engine, Refusal, part, path_of

log = logging.getLogger(__name__)

PATH = "/api/containers/shell"
EXITED = 4000
REFUSED = 4403
MISSING = 4404
UNREACHABLE = 4502
CLOSE = {"close": True}
PING = "ping"
PONG = "pong"
SIDE = range(2, 1001)
ID = 128
# bash where the image has it, sh where it has not.
SHELL = ["sh", "-c", "command -v bash >/dev/null && exec bash -l || exec sh -l"]


@api("POST", confirmed=("POST",))
async def confirmed(request):
    """Answers once the administrator has shown who they are, which the socket then requires."""
    if not request.user.is_staff:
        raise Refused(403, "forbidden")
    return HttpResponse(status=204)


def _size(given) -> tuple[int, int] | None:
    if not isinstance(given, dict):
        return None
    cols, rows = given.get("cols"), given.get("rows")
    if type(cols) is not int or type(rows) is not int or cols not in SIDE or rows not in SIDE:
        return None
    return cols, rows


def _opening(text: str | None) -> tuple[str, str, int, int] | None:
    try:
        given = json.loads(text or "")
    except ValueError:
        return None
    if (size := _size(given)) is None:
        return None
    host, container = given.get("host"), given.get("container")
    if not all(isinstance(each, str) and 0 < len(each) <= ID for each in (host, container)):
        return None
    return host, container, *size


@database
def _admitted(signed: Signed, host: str) -> Engine | None:
    user = User.objects.filter(pk=signed.user).first()
    if user is None or not user.is_staff:
        return None
    session = import_module(settings.SESSION_ENGINE).SessionStore(signed.session)
    if not fresh(session.get(CONFIRMED)):
        return None
    try:
        return reach.engine(reach.host(user, host, Role.EDIT))
    except Refused:
        return None


async def _typed(receive, send, writer: asyncio.StreamWriter, resize) -> None:
    while (message := await receive())["type"] == "websocket.receive":
        if (data := message.get("bytes")) is not None:
            writer.write(data)
            await writer.drain()
            continue
        if message.get("text") == PING:
            await send({"type": "websocket.send", "text": PONG})
            continue
        with suppress(ValueError):
            given = json.loads(message.get("text") or "")
            if given == CLOSE:
                return
            if size := _size(given):
                await resize(*size)


async def _shown(reader: asyncio.StreamReader, send) -> None:
    with suppress(OSError):
        while data := await reader.read(32 * 1024):
            await send({"type": "websocket.send", "bytes": data})


async def _shell(receive, send, engine: Engine, container: str, cols: int, rows: int):
    made = await engine.post(
        f"/containers/{part(container)}/exec",
        {
            "AttachStdin": True,
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": True,
            "ConsoleSize": [rows, cols],
            "Env": ["TERM=xterm-256color"],
            "Cmd": SHELL,
        },
    )
    exec_id = made["Id"]

    # Each resize is an ssh of its own, so a window dragged sends only the size it ends at.
    wanted: list[tuple[int, int]] = []
    resizing: asyncio.Task | None = None

    async def resized() -> None:
        while wanted:
            cols, rows = wanted.pop()
            wanted.clear()
            with suppress(Failed):
                await engine.post(f"/exec/{part(exec_id)}/resize", h=rows, w=cols)

    async def resize(cols: int, rows: int) -> None:
        nonlocal resizing
        wanted.append((cols, rows))
        if resizing is None or resizing.done():
            resizing = asyncio.create_task(resized())

    start = path_of(f"/exec/{part(exec_id)}/start")
    body = {"Detach": False, "Tty": True, "ConsoleSize": [rows, cols]}
    async with engine.answer("POST", start, body, upgrade=True) as (answer, process):
        showing = asyncio.create_task(_shown(answer.reader, send))
        typing = asyncio.create_task(_typed(receive, send, process.writer, resize))
        await asyncio.wait({showing, typing}, return_when=asyncio.FIRST_COMPLETED)
        for task in (showing, typing):
            task.cancel()
        for task in (showing, typing):
            with suppress(asyncio.CancelledError, OSError, ConnectionError):
                await task
    with suppress(Failed):
        ended = await engine.get(f"/exec/{part(exec_id)}/json")
        if not ended.get("Running"):
            return EXITED, str(ended.get("ExitCode", ""))
    return EXITED, ""


async def socket(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    if not same_origin(scope) or (signed := await signed_in(scope)) is None:
        await refuse(send)
        return
    await send({"type": "websocket.accept"})
    first = await receive()
    opening = _opening(first.get("text")) if first["type"] == "websocket.receive" else None
    engine = opening and await _admitted(signed, opening[0])
    if not engine:
        code, reason = REFUSED, ""
    else:
        try:
            code, reason = await _shell(receive, send, engine, *opening[1:])
        except Refusal as refused:
            # A container gone or not running answers 404 or 409; trying again cannot help.
            log.info("no shell in a container: %s", refused.message)
            code, reason = MISSING, ""
        except Failed as failed:
            log.info("no shell in a container: %s", failed.error)
            code, reason = UNREACHABLE, failed.error
    with suppress(OSError):
        await send({"type": "websocket.close", "code": code, "reason": reason})
