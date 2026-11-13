"""What a signed-in browser hears as it happens, over one WebSocket a tab beside the documents'
(/api/live): the rings of meetings, then the messages of conversations (S2). A change tells the
users it concerns on a Postgres channel, so it reaches them from any process; each process listens
once and wakes its sockets of those users, and each reads its user's state again and sends it
whenever it changed:

    server → {"type": "state", <part>: …, …}

The parts are what the apps add with `part`, each read from the database for one user. A guest
waiting at a meeting's door (S2-2) listens the same way to a state of its own, through `held`.

Beside the state, a tab hears which of the user's data changed, however it changed: on the phone,
over DAV, in a sync, by an agent or by a colleague. A trigger on each table a tab shows from
(migration `0006_changes`) names on a channel of its own the area and whom it concerns, a user
(`u<id>`), everyone (`*`), or a kind an app resolves to its users with `audience`, such as a
document by the grants along its folders; the tab reads that area again:

    server → {"type": "changed", "areas": ["contacts", …]}

An area of `*` is every area, sent after the listener lost the database, as what changed
meanwhile was not heard."""

import json
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from functools import partial
from logging import getLogger

import psycopg
from anyio import (
    BrokenResourceError,
    CancelScope,
    WouldBlock,
    create_memory_object_stream,
    create_task_group,
    sleep,
)
from django.db import connection

from apps.core.asyncdb import conninfo, database

from .server import refuse, same_origin, signed_in

PATH = "/api/live"
CHANNEL = "live"
CHANGES = "changed"
EVERY = "*"
# How long the listener waits to listen again after it lost the database.
RETRY = 5

log = getLogger(__name__)

PARTS: dict[str, Callable[[int], object]] = {}
# For a kind of target, the users a change to the one of that id concerns; None for everyone.
AUDIENCES: dict[str, Callable[[str], Iterable[int] | None]] = {}


class _Held:
    """An open socket: what wakes it, and what it was told since it last sent."""

    def __init__(self) -> None:
        self.waking, self.wakes = create_memory_object_stream[None](1)
        self.stale = True
        self.areas: set[str] = set()

    def wake(self, area: str | None = None) -> None:
        if area is None:
            self.stale = True
        else:
            self.areas.add(area)
        # One wake waiting is as good as many: the socket sends all it was told.
        # A socket closing has shut its stream before it leaves the listeners.
        with suppress(WouldBlock, BrokenResourceError):
            self.waking.send_nowait(None)


# Keyed by who listens: a user by their id, a guest as `guest` names them.
_sockets: dict[str, set[_Held]] = defaultdict(set)


def part(name: str, read: Callable[[int], object]) -> None:
    """Adds what `read` gives for a user to the state each of their tabs holds."""
    PARTS[name] = read


def audience(kind: str, resolve: Callable[[str], Iterable[int] | None]) -> None:
    """How a change the triggers name `<kind><id>` finds its users."""
    AUDIENCES[kind] = resolve


def tell(*users: int) -> None:
    """Wakes the users' tabs once the current transaction commits."""
    _told(map(str, users))


def guest(pk: int) -> str:
    """Whom a guest's socket listens as, beside the users by their ids."""
    return f"guest{pk}"


def tell_guests(*pks: int) -> None:
    _told(map(guest, pks))


def _told(listeners) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify(%s, %s)", [CHANNEL, ",".join(listeners)])


def _wake(listeners, area: str | None = None) -> None:
    for listener in listeners:
        for each in _sockets.get(listener, ()):
            each.wake(area)


@database
def _concerned(kind: str, key: str) -> list[int] | None:
    found = AUDIENCES[kind](key)
    return None if found is None else list(found)


async def _changed(payload: str) -> None:
    area, target = payload.split(" ", 1)
    users = [each for each in _sockets if each.isdigit()]
    if not users:
        return
    if target == EVERY:
        concerned = None
    elif target[0] == "u":
        concerned = [int(target[1:])]
    else:
        concerned = await _concerned(target[0], target[1:])
    _wake(users if concerned is None else (str(each) for each in concerned), area)


async def listen() -> None:
    """Wakes this process's sockets of the users the channels name, and all of them whenever it
    listens again, with every area, for what was told while it did not."""
    again = False
    while True:
        try:
            listener = await psycopg.AsyncConnection.connect(conninfo(), autocommit=True)
            try:
                await listener.execute(f"LISTEN {CHANNEL}")
                await listener.execute(f"LISTEN {CHANGES}")
                _wake(list(_sockets))
                if again:
                    _wake(list(_sockets), EVERY)
                again = True
                async for notice in listener.notifies():
                    if notice.channel == CHANGES:
                        await _changed(notice.payload)
                    else:
                        _wake(each for each in notice.payload.split(",") if each)
            finally:
                # Closed rather than left as a context manager: that rolls back first, which a
                # connection still waiting for notifications refuses, with a warning.
                with CancelScope(shield=True):
                    await listener.close()
        except Exception:
            log.exception("live failed")
            await sleep(RETRY)


@database
def _state(user: int) -> dict:
    return {name: read(user) for name, read in PARTS.items()}


async def _deliver(send, read: Callable[[], Awaitable[dict]], held: _Held) -> None:
    async def sent(message: dict) -> None:
        with suppress(OSError):
            await send({"type": "websocket.send", "text": json.dumps(message)})

    last = None
    async with held.wakes:
        while True:
            if held.stale:
                held.stale = False
                state = await read()
                if state != last:
                    await sent({"type": "state", **state})
                    last = state
            if held.areas:
                areas, held.areas = sorted(held.areas), set()
                await sent({"type": "changed", "areas": areas})
            await held.wakes.receive()


def online() -> set[int]:
    """The users with a tab open in this process."""
    return {int(each) for each in _sockets if each.isdigit()}


def _everyone_hears(listener: str) -> None:
    """A user who came or went changes who is online in every other user's state."""
    if listener.isdigit():
        _wake(each for each in list(_sockets) if each.isdigit() and each != listener)


def listening(listener: str) -> bool:
    """Whether a socket of the listener's is open in this process."""
    return listener in _sockets


async def held(receive, send, listener: str, read: Callable[[], Awaitable[dict]]) -> None:
    """Sends an accepted socket what `read` gives whenever the listener is told, until it closes."""
    held = _Held()
    arriving = listener not in _sockets
    _sockets[listener].add(held)
    if arriving:
        _everyone_hears(listener)
    try:
        async with create_task_group() as group:
            group.start_soon(_deliver, send, read, held)
            while (await receive())["type"] == "websocket.receive":
                pass
            group.cancel_scope.cancel()
    finally:
        _sockets[listener].discard(held)
        if not _sockets[listener]:
            del _sockets[listener]
            _everyone_hears(listener)
        held.waking.close()
        with suppress(OSError):
            await send({"type": "websocket.close"})


async def socket(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    if not same_origin(scope) or (signed := await signed_in(scope)) is None:
        await refuse(send)
        return
    await send({"type": "websocket.accept"})
    await held(receive, send, str(signed.user), partial(_state, signed.user))
