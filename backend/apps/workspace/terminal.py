"""The owner's terminal on the page of projects (KR25): the browser's socket here, passed on as it
goes to one the workspace opens with its token, which runs a login shell for it in the project's
folder (workspace/terminal.mjs). It opens only under a recent confirmation of who the owner is
(D33), which the page has asked for just before (views.terminal):

    browser → {"folder": <project path>, "cols": …, "rows": …}
    then binary frames both ways: what the owner types and what the shell writes;
    browser → {"cols": …, "rows": …} resizes the terminal.

The socket closes with EXITED once the shell exits (its status the reason), REFUSED for anyone
but the owner freshly confirmed, and UNREACHABLE when the workspace could not be reached or
dropped it."""

import json
import logging
from contextlib import suppress
from importlib import import_module
from urllib.parse import urlencode

from anyio import CancelScope, create_task_group
from django.conf import settings
from websockets import ConnectionClosed, WebSocketException
from websockets.asyncio.client import ClientConnection, connect

from apps.collab.server import Signed, refuse, same_origin, signed_in
from apps.core.asyncdb import database
from apps.users.models import User
from apps.users.sessions import CONFIRMED, fresh

from .views import ASKED_WITHIN, CONFIRMED_FOR, kept_here, owns

logger = logging.getLogger(__name__)

PATH = "/api/workspace/terminal"
EXITED = 4000
REFUSED = 4403
UNREACHABLE = 4502
# What the workspace closes with that the page tells apart: the shell ended, a project it does
# not know, too many terminals open.
PASSED = {EXITED, 4404, 4429}
FRAME = 1 << 20
FOLDER = 4096
SIDE = range(2, 1001)


def far(folder: str, cols: int, rows: int) -> str:
    if kept_here():
        base = "ws://workspace:8081"
    else:
        base = "wss://" + settings.WORKSPACE_URL.removeprefix("https://").rstrip("/")
    return f"{base}/ponistra/terminal?{urlencode({'folder': folder, 'cols': cols, 'rows': rows})}"


def _size(given) -> tuple[int, int] | None:
    if not isinstance(given, dict):
        return None
    cols, rows = given.get("cols"), given.get("rows")
    if type(cols) is not int or type(rows) is not int or cols not in SIDE or rows not in SIDE:
        return None
    return cols, rows


def _opening(text: str | None) -> tuple[str, int, int] | None:
    try:
        given = json.loads(text or "")
    except ValueError:
        return None
    if (size := _size(given)) is None:
        return None
    folder = given.get("folder")
    if not isinstance(folder, str) or len(folder) > FOLDER:
        return None
    return folder, *size


@database
def _admitted(signed: Signed) -> bool:
    user = User.objects.filter(pk=signed.user).first()
    if user is None or not owns(user) or not settings.WORKSPACE_TOKEN:
        return False
    session = import_module(settings.SESSION_ENGINE).SessionStore(signed.session)
    return fresh(session.get(CONFIRMED), CONFIRMED_FOR)


async def _typed(receive, workspace: ClientConnection) -> None:
    with suppress(ConnectionClosed):
        while (message := await receive())["type"] == "websocket.receive":
            if (data := message.get("bytes")) is not None:
                await workspace.send(data)
                continue
            with suppress(ValueError):
                if size := _size(json.loads(message.get("text") or "")):
                    await workspace.send(json.dumps({"cols": size[0], "rows": size[1]}))
        await workspace.close()


async def _shown(workspace: ClientConnection, send, typing: CancelScope) -> None:
    # A browser gone fails the send; the shell ends as the workspace's socket closes behind it.
    with suppress(ConnectionClosed, OSError):
        async for message in workspace:
            if isinstance(message, bytes):
                await send({"type": "websocket.send", "bytes": message})
    typing.cancel()


async def _relayed(receive, send, folder: str, cols: int, rows: int) -> tuple[int, str]:
    try:
        async with connect(
            far(folder, cols, rows),
            additional_headers={"Authorization": f"Bearer {settings.WORKSPACE_TOKEN}"},
            proxy=None,
            open_timeout=ASKED_WITHIN,
            max_size=FRAME,
        ) as workspace:
            async with create_task_group() as group:
                group.start_soon(_shown, workspace, send, group.cancel_scope)
                await _typed(receive, workspace)
    except (OSError, TimeoutError, WebSocketException) as error:
        logger.warning("the code workspace did not open a terminal: %s", error)
        return UNREACHABLE, ""
    if workspace.close_code in PASSED:
        return workspace.close_code, workspace.close_reason or ""
    return UNREACHABLE, ""


async def socket(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    if not same_origin(scope) or (signed := await signed_in(scope)) is None:
        await refuse(send)
        return
    await send({"type": "websocket.accept"})
    first = await receive()
    opening = _opening(first.get("text")) if first["type"] == "websocket.receive" else None
    if opening is None or not await _admitted(signed):
        code, reason = REFUSED, ""
    else:
        code, reason = await _relayed(receive, send, *opening)
    with suppress(OSError):
        await send({"type": "websocket.close", "code": code, "reason": reason})
