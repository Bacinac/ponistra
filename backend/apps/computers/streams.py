"""A stream Ponistra asks a machine for on its link (ponistra-os `agent/API.md`, Ponistra): the
agent opens `api/computers/streams/{id}` and joins it to one of its API's WebSockets (a guest's
console, its SFTP session) or reads a request's body from it (an ISO), so the bytes never cross
the link."""

import asyncio
import json
import re
import secrets
from collections import deque
from contextlib import suppress

from . import link

PATTERN = re.compile(r"/api/computers/streams/([A-Za-z0-9_-]{1,128})")
OPENED = 30
# A refusal (a console another account's, a guest not running) closes the stream right after the
# agent connects it; a stream that has said nothing by then is the session itself.
REFUSAL = 0.5
# What waits to be sent before `drain` holds the writer.
HELD = 64
END = '{"type":"end"}'


class Refused(Exception):
    def __init__(self, status: int, error: str):
        super().__init__(error)
        self.status = status
        self.error = error


class Stream:
    """One stream's messages: `read` the bytes of the next (b"" once it ended, `ended` then holding
    the close code and the agent's error), `write` bytes, `close` it."""

    def __init__(self) -> None:
        self.ended: tuple[int, str] | None = None
        self._inbound: asyncio.Queue[bytes | str | None] = asyncio.Queue()
        self._outbound: deque[dict] = deque()
        self._wake = asyncio.Event()
        self._room = asyncio.Event()
        self._room.set()
        self._done = asyncio.Event()
        self._back: list[bytes | str] = []

    async def message(self) -> bytes | str | None:
        """The next message as it came, text or bytes; None once the stream ended."""
        if self._back:
            return self._back.pop()
        if self.ended is not None and self._inbound.empty():
            return None
        return await self._inbound.get()

    async def read(self) -> bytes:
        while True:
            given = await self.message()
            if given is None:
                return b""
            if isinstance(given, bytes):
                return given

    def write(self, data: bytes) -> None:
        self._queued({"type": "websocket.send", "bytes": bytes(data)})

    def write_text(self, text: str) -> None:
        self._queued({"type": "websocket.send", "text": text})

    async def drain(self) -> None:
        """Waits until what was written is nearly sent."""
        await self._room.wait()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.ended is None:
            self._queued({"type": "websocket.close", "code": code, "reason": reason[:120]})
        with suppress(TimeoutError):
            async with asyncio.timeout(OPENED):
                await self._done.wait()

    def _queued(self, message: dict) -> None:
        if self.ended is not None:
            return
        self._outbound.append(message)
        if len(self._outbound) >= HELD:
            self._room.clear()
        self._wake.set()

    def _end(self, code: int, reason: str) -> None:
        if self.ended is None:
            self.ended = (code, reason)
        self._inbound.put_nowait(None)
        self._room.set()
        self._wake.set()
        self._done.set()

    async def _sending(self, send) -> None:
        while self.ended is None:
            await self._wake.wait()
            self._wake.clear()
            while self._outbound:
                message = self._outbound.popleft()
                if len(self._outbound) < HELD // 2:
                    self._room.set()
                try:
                    await send(message)
                except OSError:
                    self._end(1006, "")
                    return
                if message["type"] == "websocket.close":
                    self._end(message["code"], message.get("reason", ""))
                    return


async def opened(computer, method: str, path: str, account: str) -> Stream:
    """A stream of the machine's API at `path`, run as `account`. Raises Refused: 503 while the
    machine is not connected, 504 when it did not open the stream, 502 with the agent's error
    when it refused it."""
    held = link.current(computer)
    if held is None:
        raise Refused(503, "computer_offline")
    key = secrets.token_urlsafe(16)
    waiting = asyncio.get_running_loop().create_future()
    held.streams[key] = waiting
    frame = {"type": "stream", "id": key, "method": method, "path": path, "account": account}
    try:
        await held.frame(frame)
        async with asyncio.timeout(OPENED):
            stream: Stream = await waiting
    except link.LinkDown:
        raise Refused(503, "computer_offline") from None
    except TimeoutError:
        raise Refused(504, "stream_not_opened") from None
    finally:
        held.streams.pop(key, None)
    with suppress(TimeoutError):
        async with asyncio.timeout(REFUSAL):
            first = await stream.message()
            if first is None:
                code, reason = stream.ended or (1006, "")
                raise Refused(502, reason or f"closed_{code}")
            stream._back.append(first)
    return stream


async def uploaded(
    computer, method: str, path: str, account: str, chunks
) -> tuple[int, str, bytes]:
    """A request whose body is too large for a frame, sent as the stream's binary messages from
    the async iterable `chunks`; the agent's one response frame, as `link.requested` gives it."""
    stream = await opened(computer, method, path, account)
    try:
        async for chunk in chunks:
            stream.write(chunk)
            await stream.drain()
        stream.write_text(END)
        while (given := await stream.message()) is not None:
            if isinstance(given, str):
                with suppress(ValueError):
                    frame = json.loads(given)
                    if isinstance(frame, dict) and frame.get("type") == "response":
                        return link.answer_of(frame)
        code, reason = stream.ended or (1006, "")
        raise Refused(502, reason or f"closed_{code}")
    finally:
        await stream.close()


async def socket(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    key = PATTERN.fullmatch(scope["path"]).group(1)
    found = await link.machine(link.scoped(scope))
    held = found and link.current(found.pk)
    waiting = held and held.streams.get(key)
    if waiting is None or waiting.done():
        await send({"type": "websocket.close", "code": link.GONE})
        return
    asked = scope.get("subprotocols", ())
    accepted = {"type": "websocket.accept"}
    if link.SUBPROTOCOL in asked:
        accepted["subprotocol"] = link.SUBPROTOCOL
    await send(accepted)
    stream = Stream()
    sending = asyncio.create_task(stream._sending(send))
    waiting.set_result(stream)
    try:
        while (message := await receive())["type"] == "websocket.receive":
            if (data := message.get("bytes")) is not None:
                stream._inbound.put_nowait(data)
            elif (text := message.get("text")) is not None:
                stream._inbound.put_nowait(text)
        stream._end(message.get("code", 1005), message.get("reason") or "")
    finally:
        stream._end(1006, "")
        sending.cancel()
        with suppress(asyncio.CancelledError):
            await sending
