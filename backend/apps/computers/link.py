"""The link each enrolled machine dials and keeps up (ponistra-os `agent/API.md`, Ponistra): text
frames of one JSON object each. The agent says `hello` and sends its `alerts`; Ponistra sends a
`request` of the machine's API as the account of the person acting and waits for its `response`,
or a `stream`, which the agent opens as a connection of its own (`streams`).

Every machine's link is held in this process, the one uvicorn runs, so a request finds it here."""

import asyncio
import hashlib
import json
import logging
import secrets
import uuid
from contextlib import suppress

from django.utils import timezone

from apps.core.asyncdb import database

from .models import Computer

log = logging.getLogger(__name__)

PATH = "/api/computers/link"
SUBPROTOCOL = "ponistra-link.v1"
# What the agent reads at most in one frame.
MOST = 16 << 20
ANSWER = 120
GONE = 4403
METHODS = ("GET", "POST", "PUT", "DELETE")

_links: dict[uuid.UUID, Link] = {}


class LinkDown(Exception):
    pass


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def bearer(headers) -> str:
    scheme, _, secret = headers.partition(" ")
    return secret.strip() if scheme.lower() == "bearer" else ""


@database
def machine(token: str) -> Computer | None:
    """The computer whose token this is, none for one unknown or gone."""
    if not token:
        return None
    return Computer.objects.filter(token=digest(token), left_at__isnull=True).first()


def scoped(scope) -> str:
    given = next((value for key, value in scope["headers"] if key == b"authorization"), b"")
    return bearer(given.decode("latin-1"))


class Link:
    def __init__(self, computer: uuid.UUID, send) -> None:
        self.computer = computer
        self._send = send
        self._sending = asyncio.Lock()
        self.answers: dict[str, asyncio.Future] = {}
        self.streams: dict[str, asyncio.Future] = {}

    async def sent(self, message: dict) -> None:
        async with self._sending:
            await self._send(message)

    async def frame(self, data: dict) -> None:
        text = json.dumps(data, separators=(",", ":"))
        if len(text.encode()) > MOST:
            raise ValueError("frame_too_large")
        try:
            await self.sent({"type": "websocket.send", "text": text})
        except OSError as error:
            raise LinkDown from error

    async def closed(self, code: int) -> None:
        with suppress(OSError, RuntimeError):
            await self.sent({"type": "websocket.close", "code": code})

    def ended(self) -> None:
        for waiting in (*self.answers.values(), *self.streams.values()):
            if not waiting.done():
                waiting.set_exception(LinkDown())


def account(user) -> str:
    """Whom the machine runs a request as: the person's address, which it takes in lower case."""
    return user.email.lower()


def current(computer) -> Link | None:
    return _links.get(getattr(computer, "pk", computer))


def connected(computer) -> bool:
    return current(computer) is not None


def _error(status: int, error: str) -> tuple[int, str, bytes]:
    return status, "application/json", json.dumps({"error": error}).encode()


def answer_of(frame: dict) -> tuple[int, str, bytes]:
    status = frame.get("status")
    if type(status) is not int:
        return _error(502, "computer_answer")
    content_type = frame.get("content_type") or ""
    if "body" not in frame or frame["body"] is None:
        return status, content_type, b""
    given = frame["body"]
    if content_type.split(";")[0].strip() == "application/json":
        return status, content_type, json.dumps(given).encode()
    if isinstance(given, str):
        return status, content_type, given.encode()
    return status, content_type or "application/json", json.dumps(given).encode()


async def requested(
    computer, method: str, path: str, account: str, body=None
) -> tuple[int, str, bytes]:
    """One request of the machine's API through its link, as `account`: the machine's status,
    content type and body; 503 while the machine is not connected, 504 when it did not answer."""
    held = current(computer)
    if held is None:
        return _error(503, "computer_offline")
    if method not in METHODS or not path.startswith("/v1/"):
        return _error(400, "invalid_request")
    key = secrets.token_urlsafe(12)
    frame = {"type": "request", "id": key, "method": method, "path": path, "account": account}
    if body is not None:
        frame["body"] = body
    waiting = asyncio.get_running_loop().create_future()
    held.answers[key] = waiting
    try:
        await held.frame(frame)
        async with asyncio.timeout(ANSWER):
            return answer_of(await waiting)
    except ValueError:
        return _error(413, "request_too_large")
    except LinkDown:
        return _error(503, "computer_offline")
    except TimeoutError:
        return _error(504, "computer_timeout")
    finally:
        held.answers.pop(key, None)


async def dropped(computer) -> None:
    """Ends the link of a computer Ponistra removed; the agent's next dial is refused."""
    if (held := current(computer)) is not None:
        await held.closed(GONE)


@database
def _hello(pk: uuid.UUID, frame: dict) -> None:
    agent = frame.get("agent")
    facts = frame.get("facts")
    Computer.objects.filter(pk=pk).update(
        agent=agent[:64] if isinstance(agent, str) else "",
        facts=facts if isinstance(facts, dict) else {},
    )


@database
def _up(pk: uuid.UUID) -> None:
    now = timezone.now()
    Computer.objects.filter(pk=pk).update(connected_at=now, seen_at=now)


@database
def _down(pk: uuid.UUID) -> None:
    Computer.objects.filter(pk=pk).update(connected_at=None, seen_at=timezone.now())


async def _heard(held: Link, text: str) -> None:
    try:
        frame = json.loads(text)
    except ValueError:
        log.warning("computer %s sent what is not a frame", held.computer)
        return
    if not isinstance(frame, dict):
        return
    match frame.get("type"):
        case "hello":
            await _hello(held.computer, frame)
        case "alerts":
            given = frame.get("alerts")
            if isinstance(given, list):
                # The alerts tell people through push, whose imports reach back to this module.
                from . import alerts

                await database(alerts.received)(held.computer, given)
        case "response":
            waiting = held.answers.get(frame.get("id"))
            if waiting is not None and not waiting.done():
                waiting.set_result(frame)


async def socket(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    found = await machine(scoped(scope))
    if found is None:
        # Closed before it is accepted, the handshake is answered 403: the agent then holds the
        # machine revoked until it enrolls again.
        await send({"type": "websocket.close", "code": GONE})
        return
    if SUBPROTOCOL not in scope.get("subprotocols", ()):
        await send({"type": "websocket.close", "code": 4400})
        return
    await send({"type": "websocket.accept", "subprotocol": SUBPROTOCOL})
    held = Link(found.pk, send)
    if (before := _links.get(found.pk)) is not None:
        await before.closed(1000)
    _links[found.pk] = held
    await _up(found.pk)
    log.info("computer %s linked", found.pk)
    try:
        while (message := await receive())["type"] == "websocket.receive":
            if (text := message.get("text")) is not None:
                await _heard(held, text)
    finally:
        held.ended()
        if _links.get(found.pk) is held:
            del _links[found.pk]
            with suppress(Exception):
                await _down(found.pk)
        log.info("computer %s unlinked", found.pk)
