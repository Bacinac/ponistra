"""A guest's console through Ponistra (ponistra-os `agent/API.md`, Console): the page opens a ticket
through the machine's API as on the machine's own page, then connects here, at the ticket's path
under the computer's; Ponistra asks the machine for a stream to it and carries every message both
ways unchanged. The machine opens a ticket only for the account that made it."""

import asyncio
import re
import uuid
from contextlib import suppress

from apps.collab.server import refuse, same_origin, signed_in
from apps.core.asyncdb import database
from apps.users.models import User

from . import link, streams
from .models import Computer

PATTERN = re.compile(
    r"/api/computers/(?P<computer>[0-9a-f-]{36})/agent(?P<path>/v1/consoles/[A-Za-z0-9_-]{1,128})"
)
SUBPROTOCOL = "binary"
# Codes a close frame cannot carry: they say only that none came.
UNSENDABLE = {1005, 1006, 1015}


@database
def _admitted(user: int, computer: str) -> tuple[Computer, str] | None:
    person = User.objects.filter(pk=user, is_active=True, visitor=False).first()
    try:
        found = Computer.objects.filter(pk=uuid.UUID(computer), left_at__isnull=True).first()
    except ValueError:
        return None
    if person is None or found is None:
        return None
    return found, link.account(person)


async def _carried(receive, send, stream: streams.Stream) -> tuple[int, str]:
    async def typed() -> tuple[int, str]:
        while (message := await receive())["type"] == "websocket.receive":
            if (data := message.get("bytes")) is not None:
                stream.write(data)
            elif (text := message.get("text")) is not None:
                stream.write_text(text)
            await stream.drain()
        return message.get("code", 1000), message.get("reason") or ""

    async def shown() -> tuple[int, str]:
        while (given := await stream.message()) is not None:
            key = "bytes" if isinstance(given, bytes) else "text"
            await send({"type": "websocket.send", key: given})
        return stream.ended or (1000, "")

    tasks = {asyncio.create_task(typed()), asyncio.create_task(shown())}
    done, waiting = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in waiting:
        task.cancel()
    for task in waiting:
        with suppress(asyncio.CancelledError, OSError):
            await task
    return next(iter(done)).result()


async def socket(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    matched = PATTERN.fullmatch(scope["path"])
    signed = same_origin(scope) and await signed_in(scope)
    admitted = signed and await _admitted(signed.user, matched["computer"])
    if not admitted:
        await refuse(send)
        return
    found, account = admitted
    accepted = {"type": "websocket.accept"}
    if SUBPROTOCOL in scope.get("subprotocols", ()):
        accepted["subprotocol"] = SUBPROTOCOL
    await send(accepted)
    try:
        stream = await streams.opened(found, "GET", matched["path"], account)
    except streams.Refused as refused:
        with suppress(OSError):
            await send({"type": "websocket.close", "code": 1011, "reason": refused.error[:120]})
        return
    try:
        code, reason = await _carried(receive, send, stream)
    finally:
        await stream.close()
    if code in UNSENDABLE:
        code, reason = 1001, ""
    with suppress(OSError, RuntimeError):
        await send({"type": "websocket.close", "code": code, "reason": reason[:120]})
