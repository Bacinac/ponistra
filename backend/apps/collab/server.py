import gc
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import suppress
from contextvars import copy_context
from dataclasses import dataclass
from importlib import import_module
from logging import getLogger
from math import inf
from time import monotonic
from types import SimpleNamespace
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from anyio import CancelScope, Event, Lock, fail_after, sleep
from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user
from django.http.cookie import parse_cookie
from django.utils import timezone
from pycrdt import Channel, Doc, YMessageType, YSyncMessageType, read_message
from pycrdt.websocket import WebsocketServer, YRoom, exception_logger
from pycrdt.websocket.asgi_server import ASGIWebsocket

from apps.access import rights
from apps.access.models import Role
from apps.content import blocks, calculation, charts, names, placing
from apps.content.sheets import Refused, Sheets
from apps.content.table import tables_of
from apps.core.asyncdb import database, released
from apps.documents.models import Node, Tab
from apps.users import sessions
from apps.users.models import User
from apps.versions.history import contributed

from .books import Book
from .models import Update
from .store import PostgresYStore

ROOM_PATH = re.compile(
    r"/api/collab/(?P<room>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
NO_CONTENT = b"\x00\x00"
REFUSED = 4403
CONTRIBUTION_EVERY = 60
BEHIND = 10


def header(scope, name: bytes) -> str:
    return next((value.decode("latin-1") for key, value in scope["headers"] if key == name), "")


def same_origin(scope) -> bool:
    # Browsers send cookies on cross-site WebSocket handshakes, and nothing like
    # CSRF protection guards them.
    origin = header(scope, b"origin")
    return bool(origin) and urlsplit(origin).netloc == header(scope, b"host")


async def refuse(send) -> None:
    """Closes the socket of a browser signed out, without a right or whose room is gone once it is
    accepted: a refused handshake is an error the browser logs, and its client tries again as after
    any drop, while 4400-4499 tells it, as y-websocket reads them, that trying again cannot help."""
    await send({"type": "websocket.accept"})
    await send({"type": "websocket.close", "code": REFUSED})


@dataclass(frozen=True)
class Signed:
    """Who a browser is signed in as, and the session it is signed in with."""

    user: int
    session: str


@database
def signed_in(scope) -> Signed | None:
    session_key = parse_cookie(header(scope, b"cookie")).get(settings.SESSION_COOKIE_NAME)
    session = import_module(settings.SESSION_ENGINE).SessionStore(session_key)
    user = get_user(SimpleNamespace(session=session))
    if not user.is_authenticated or session.get(sessions.PASSKEY_DUE):
        return None
    return Signed(user.pk, session_key)


@dataclass(frozen=True)
class Holder:
    document: UUID
    tab: UUID | None

    @property
    def grids(self) -> str | None:
        """The tab whose grids the room's tables have, none for the document's own."""
        return None if self.tab is None else str(self.tab)


class Prepared(Protocol):
    """A change prepared for a room: its grids' patches, applied first, and what then commits
    the rest of it to the room's state, given the patches as they went."""

    patches: list[dict]
    guard: bool

    def commit(self, doc: Doc, applied: list[dict]) -> Any: ...


@database
def holder(room: str) -> Holder | None:
    """What the room holds, a tab's content, its document's own state or a file's notes, while
    the node is live."""
    tab = Tab.objects.select_related("document").filter(room=room).first()
    document = tab.document if tab else Node.objects.filter(room=room).first()
    if document is None or not document.is_live():
        return None
    return Holder(document.pk, tab and tab.pk)


@database
def live(document: UUID) -> bool:
    node = Node.objects.filter(pk=document).first()
    return node is not None and node.is_live()


@database
def role_in(signed: Signed | None, document) -> Role | None:
    """The role the browser holds on the document, none once its session has ended."""
    if signed is None:
        return None
    found = User.everyone.filter(
        pk=signed.user,
        sessions__session_key=signed.session,
        sessions__expire_date__gt=timezone.now(),
    ).first()
    node = Node.objects.filter(pk=document).first()
    if found is None or node is None:
        return None
    return rights.reach(found, node.ancestry()).role


def writes(message: bytes) -> bool:
    """Whether a client's message would write: an update, or a sync reply."""
    return (
        len(message) > 2
        and message[0] == YMessageType.SYNC
        and message[1] in (YSyncMessageType.SYNC_STEP2, YSyncMessageType.SYNC_UPDATE)
    )


def changes(message: bytes) -> bool:
    """Whether a client's message carries edits: an update, or a sync reply with
    content the server had not seen."""
    return writes(message) and read_message(message[2:]) != NO_CONTENT


async def collect_garbage() -> None:
    while True:
        await sleep(1)
        gc.collect()


class Connection(ASGIWebsocket):
    _closing = False
    _contributed = -inf

    def __init__(
        self,
        receive,
        send,
        path: str,
        document=None,
        signed: Signed | None = None,
        role: Role | None = None,
    ):
        super().__init__(receive, send, path)
        self.document = document
        self.signed = signed
        self.user = signed and signed.user
        self.role = role

    async def recv(self) -> bytes:
        message = await super().recv()
        while self.role == Role.READ and writes(message):
            message = await super().recv()
        if (
            self.user is not None
            and monotonic() - self._contributed > CONTRIBUTION_EVERY
            and changes(message)
        ):
            self._contributed = monotonic()
            await database(contributed)(self.document, self.user)
        return message

    async def send(self, message: bytes) -> None:
        if self._closing:
            return
        # The room finishes broadcasts to a client that has just gone; ASGI servers
        # refuse a send on a closed connection with OSError, and nobody is there to read it.
        with suppress(OSError):
            await super().send(message)

    async def close(self) -> None:
        if not self._closing:
            self._closing = True
            await self._send({"type": "websocket.close"})


class CollabServer(WebsocketServer):
    """Yjs rooms over WebSocket, one per document tab and one for each document's own
    state, persisted in Postgres, and each document's grids in a book while it is in use.

    A room lives while at least one client is connected.
    It is loaded from the store before its first client syncs, and on the last
    client's departure its whole state replaces the stored updates, so the store
    holds one row per idle room instead of one per keystroke.
    """

    def __init__(self) -> None:
        log = getLogger(__name__)
        super().__init__(auto_clean_rooms=False, exception_handler=exception_logger, log=log)
        self._rooms_lock = Lock()
        self._members: Counter[str] = Counter()
        self._held: dict[str, Holder] = {}
        self.books: dict[UUID, Book] = {}

    async def __aenter__(self) -> CollabServer:
        await super().__aenter__()
        # pycrdt objects belong to the thread that made them (PyO3 unsendable). Freed
        # by a collection that allocation pressure starts on a database or view thread,
        # their Rust state, a whole document, is leaked instead; so cyclic garbage is
        # collected on the event loop only. Freezing what startup made keeps that cheap.
        gc.freeze()
        gc.disable()
        self._task_group.start_soon(collect_garbage)
        self._context = copy_context()
        return self

    async def __aexit__(self, *exc_info):
        try:
            return await super().__aexit__(*exc_info)
        finally:
            gc.collect()
            gc.unfreeze()
            gc.enable()

    async def __call__(self, scope, receive, send) -> None:
        if (await receive())["type"] != "websocket.connect":
            return
        match = ROOM_PATH.fullmatch(scope["path"])
        if match is None or not same_origin(scope):
            await send({"type": "websocket.close"})
            return
        if (
            (signed := await signed_in(scope)) is None
            or (held := await holder(match["room"])) is None
            or (role := await role_in(signed, held.document)) is None
        ):
            await refuse(send)
            return
        await send({"type": "websocket.accept"})
        await self.serve(Connection(receive, send, match["room"], held.document, signed, role))

    def book(self, document: UUID) -> Book:
        """The document's book, kept while somebody uses it and then until what changed is
        computed; `release` lets it go."""
        found = self.books.get(document)
        if found is None:
            found = self.books[document] = Book(document, outside=self._drawn)
            # Started in the server's own context, not in that of the request that wakes it:
            # what the book sends to the database's thread would go to that request's thread,
            # gone once it answers.
            found.start = lambda: self._context.copy().run(
                self._task_group.start_soon, self._computing, document, found
            )
        found.users += 1
        return found

    def release(self, document: UUID) -> None:
        found = self.books[document]
        found.users -= 1
        if found.users:
            return
        if found.running:
            found.wake.set()
        else:
            del self.books[document]

    async def _computing(self, document: UUID, book: Book) -> None:
        try:
            await book.run()
        finally:
            if not book.users and self.books.get(document) is book:
                del self.books[document]

    async def _drawn(self, tab: str, shown: dict[str, dict]) -> None:
        """Writes what charts show into the state of a tab nobody has open."""
        room = await _room_of(tab)
        if room is not None:
            await self.change(room, lambda doc, _: charts.store(doc, shown))

    async def revoke(self) -> None:
        """Closes the clients of every room whose tab or document is gone or has moved
        to another room, or whose document is trashed, and every client whose role on
        the document has changed, so it comes back with its new rights; and so the browsers
        watching a document's grids."""
        for name, room in list(self.rooms.items()):
            held = await holder(name)
            for client in list(room.clients):
                if held is None or await role_in(client.signed, held.document) != client.role:
                    await client.close()
        for document, book in list(self.books.items()):
            kept = await live(document)
            for watcher in list(book.watchers):
                if not kept or await role_in(watcher.signed, document) != watcher.role:
                    watcher.close()

    async def rewrite[T](self, document: UUID, write: Callable[[], T]) -> T:
        """Writes the document's grids outside its book, as restoring a version does: with
        the lock of a live book held, which then reads them again."""
        book = self.books.get(document)
        if book is None:
            done = await database(write)()
            await database(_refreshed)(document)
            return done
        async with book.lock:
            done = await database(write)()
            await book.reload()
            return done

    async def grew(self, document: UUID) -> None:
        """Tells the browsers of a live book that an import has written rows into its tables."""
        book = self.books.get(document)
        if book is not None:
            async with book.lock:
                await book.grew()

    async def announce(self, room: str, news: str) -> None:
        """Tells the clients of a document's own room that something kept outside the
        room, such as its comments or its tabs, has changed. The server's presence there
        carries the news: presence is neither stored nor versioned, unlike anything
        written into the room's state."""
        live = self.rooms.get(room)
        if live is not None:
            told = live.awareness.get_local_state() or {}
            live.awareness.set_local_state({**told, news: told.get(news, 0) + 1})

    async def attend(self, room: str, run: str, presence: dict | None) -> None:
        """Shows an action's run in a live room as a participant while it runs, in the
        server's presence there by the run's id; None takes it off."""
        live = self.rooms.get(room)
        if live is not None:
            told = live.awareness.get_local_state() or {}
            runs = {key: value for key, value in told.get("runs", {}).items() if key != run}
            live.awareness.set_local_state(
                {**told, "runs": runs if presence is None else {**runs, run: presence}}
            )

    async def launch(self, work: Callable[[], None]) -> None:
        """Starts work that outlives its request, on a thread of its own, from which it reaches
        the rooms as a request does."""
        self._task_group.start_soon(database(work, own_thread=True))

    async def recompute(self, document: UUID, locale: str) -> None:
        """Computes the document's tables again in its new locale, in the background."""
        self._task_group.start_soon(self._relocaled, self.book(document), locale)

    async def _relocaled(self, book: Book, locale: str) -> None:
        try:
            await book.load()
            book.relocale(locale)
        finally:
            self.release(book.document)

    async def change(self, name: str, edit: Callable[[Doc, Sheets], None]) -> None:
        """Changes a room's state and its grids as a client would: the edit writes a copy of
        the state and the sheets of the room's grids, the grids' patches are applied and
        then the copy's change. A live room's clients receive it and its store keeps it, an
        idle room's is stored beside its updates, unless the edit changed nothing. The rooms
        lock keeps a room from opening or compacting halfway through."""
        async with self._rooms_lock:
            room = self.rooms.get(name)
            held = self._held[name] if room is not None else await holder(name)
            if held is None:
                raise LookupError(f"nothing live holds room {name}")
            book = self.book(held.document)
            try:
                await book.load()
                state = room.ydoc if room is not None else await _stored(name)
                copy = Doc()
                copy.apply_update(state.get_update())
                before = copy.get_state()
                # An update always carries the whole delete set, so an unchanged state is told
                # from the update it gives before the edit, not from an empty one.
                unchanged = copy.get_update(before)

                def work(sheets: Sheets) -> tuple[None, list[dict], bool]:
                    edit(copy, sheets)
                    return None, sheets.patches(), False

                async with book.lock:
                    await book.edit(work, held.grids)
                update = copy.get_update(before)
                if update == unchanged:
                    return
                if room is not None:
                    room.ydoc.apply_update(update)
                else:
                    await database(Update.objects.create)(
                        document_id=held.document, tab_id=held.tab, room=name, data=update
                    )
                    if held.grids is not None:
                        book.placed(held.grids, placing.of(copy))
            finally:
                self.release(held.document)

    async def perform[T](
        self,
        name: str,
        edit: Callable[[Doc, Sheets], Prepared],
        settle: bool = True,
        by: str | None = None,
        after: tuple[int, int] | None = None,
    ) -> T:
        """Changes a tab's state in its room, opened for the change where nobody has it
        open: the change prepared, its grids' patches applied, then the rest committed to the
        room's state; returns what that gave once the tables are computed again, unless the
        change is not to wait for them. Leaving the room, the last one there stores it.

        A browser's change comes `after` its own edits to the room's state up to a clock of
        its client, which reach the room over another socket: it waits for them."""
        room = await self._join(name)
        try:
            if after is not None:
                await _reached(room.ydoc, *after)
            held = self._held[name]
            book = self.books[held.document]
            async with self._rooms_lock, book.lock:
                order = blocks.table_ids(blocks.body_of(room.ydoc)) if held.tab else None
                state = _copied(room.ydoc)

                def work(sheets: Sheets) -> tuple[Prepared, list[dict], bool]:
                    prepared = edit(state, sheets)
                    return prepared, prepared.patches, prepared.guard

                prepared, applied = await book.edit(work, held.grids, order, by)
                updates = []
                subscription = room.ydoc.observe(lambda event: updates.append(event.update))
                try:
                    done = prepared.commit(room.ydoc, applied)
                finally:
                    room.ydoc.unobserve(subscription)
            # The room stores an update once its broadcast takes it up, which leaving the room
            # may cancel first; its whole state is then stored as it closes.
            if updates:
                room.ystore.changed = True
            if settle:
                await book.settled()
            return done
        finally:
            with CancelScope(shield=True):
                await self._leave(name, room)

    async def read_live[T](self, name: str, reading: Callable[[Doc], T]) -> tuple[bool, T | None]:
        """Reads a live room's state as its clients have it, on the event loop its document
        is bound to; whether the room is live, and what was read."""
        async with self._rooms_lock:
            room = self.rooms.get(name)
            return (True, reading(room.ydoc)) if room is not None else (False, None)

    async def read_grids[T](
        self, name: str, reading: Callable[[Doc, Sheets], T], settled: bool = False
    ) -> tuple[bool, T | None]:
        """Reads a live room's state with its document's grids and names as the book has them,
        once what has changed is computed where they are to show what their cells compute."""
        if settled and (held := self._held.get(name)) and (book := self.books.get(held.document)):
            await book.settled()
        async with self._rooms_lock:
            room = self.rooms.get(name)
            if room is None:
                return False, None
            held = self._held[name]
            book = self.books[held.document]
            state = _copied(room.ydoc)
            async with book.lock:
                sheets = book.sheets(held.grids)
                return True, await book.off(reading, state, sheets)

    async def serve(self, websocket: Channel) -> None:
        try:
            room = await self._join(websocket.path)
            try:
                await room.serve(websocket)
            finally:
                with CancelScope(shield=True):
                    await self._leave(websocket.path, room)
        except Exception as exception:
            self._handle_exception(exception)

    async def _join(self, name: str) -> YRoom:
        async with self._rooms_lock:
            room = self.rooms.get(name)
            if room is None:
                held = await holder(name)
                if held is None:
                    raise LookupError(f"nothing live holds room {name}")
                book = self.book(held.document)
                try:
                    await book.load()
                    ystore = PostgresYStore(name, held.document, held.tab, log=self.log)
                    room = YRoom(
                        ready=False,
                        ystore=ystore,
                        exception_handler=exception_logger,
                        log=self.log,
                        # Deleted content stays in the state, so a run taken back brings it back.
                        ydoc=Doc(skip_gc=True),
                    )
                    await ystore.apply_updates(room.ydoc)
                    room.ready = True
                    await self.start_room(room)
                    # The room stores and sends only what changes once it observes the doc.
                    await room.ydoc_observed.wait()
                    if held.grids is not None:
                        book.follow(held.grids, room.ydoc)
                except BaseException:
                    self.release(held.document)
                    raise
                self.rooms[name] = room
                self._held[name] = held
            self._members[name] += 1
            return room

    async def _leave(self, name: str, room: YRoom) -> None:
        async with self._rooms_lock:
            self._members[name] -= 1
            if self._members[name]:
                return
            del self._members[name], self.rooms[name]
            held = self._held.pop(name)
            if held.grids is not None:
                self.books[held.document].unfollow(held.grids)
            try:
                await room.stop()
                await room.ystore.compact(room.ydoc.get_update())
            finally:
                self.release(held.document)


async def _reached(doc: Doc, client: int, clock: int) -> None:
    # The state is read once the change is through: within its observer it is still borrowed.
    changed = [Event()]
    subscription = doc.observe(lambda _: changed[0].set())
    try:
        with fail_after(BEHIND):
            while blocks.clocks(doc).get(client, 0) < clock:
                await changed[0].wait()
                changed[0] = Event()
    except TimeoutError:
        raise Refused("behind", f"{client}:{clock}") from None
    finally:
        doc.unobserve(subscription)


@database
def _room_of(tab: str) -> str | None:
    found = Tab.objects.filter(pk=tab).values_list("room", flat=True).first()
    return None if found is None else str(found)


def _updates(room: str) -> list[bytes]:
    found = Update.objects.filter(room=room).order_by("id").values_list("data", flat=True)
    return [bytes(data) for data in found]


def _copied(doc: Doc) -> Doc:
    """A copy of a room's state, which a change is worked out over on the database's thread
    while the room takes in its clients' updates."""
    found = Doc(skip_gc=True)
    found.apply_update(doc.get_update())
    return found


async def _stored(room: str) -> Doc:
    state = Doc()
    for data in await database(_updates)(room):
        state.apply_update(data)
    return state


collab = CollabServer()


def _on_loop[**P, T](work: Callable[P, Awaitable[T]]) -> Callable[P, T]:
    released()
    return async_to_sync(work)


def revoke() -> None:
    # Rooms live in this process's event loop; a sync view reaches it through async_to_sync.
    _on_loop(collab.revoke)()


def announce(room: UUID, news: str) -> None:
    _on_loop(collab.announce)(str(room), news)


def attend(room: UUID, run: str, presence: dict | None) -> None:
    _on_loop(collab.attend)(str(room), run, presence)


def launch(work: Callable[[], None]) -> None:
    _on_loop(collab.launch)(work)


def recompute(document: UUID, locale: str) -> None:
    _on_loop(collab.recompute)(document, locale)


def _refreshed(document: UUID) -> None:
    calculation.refresh(Node.objects.get(pk=document))


def rewrite[T](document: UUID, write: Callable[[], T]) -> T:
    return _on_loop(collab.rewrite)(document, write)


def grew(document: UUID) -> None:
    _on_loop(collab.grew)(document)


def change(room: UUID, edit: Callable[[Doc, Sheets], None]) -> None:
    _on_loop(collab.change)(str(room), edit)


def perform[T](room: UUID, edit: Callable[[Doc, Sheets], Prepared]) -> T:
    return _on_loop(collab.perform)(str(room), edit)


def read[T](room: UUID, reading: Callable[[Doc], T]) -> T:
    """Reads a room's state: a live room's as its clients have it, an idle room's from its
    store, within the request's own transaction."""
    live, found = _on_loop(collab.read_live)(str(room), reading)
    if live:
        return found
    state = Doc()
    for data in _updates(str(room)):
        state.apply_update(data)
    return reading(state)


def read_grids[T](room: UUID, reading: Callable[[Doc, Sheets], T], settled: bool = False) -> T:
    """Reads a room's state with its document's grids and names: a live room's as its clients
    and its book have them, an idle room's from the store and Postgres."""
    live, found = _on_loop(collab.read_grids)(str(room), reading, settled)
    if live:
        return found
    state = Doc()
    for data in _updates(str(room)):
        state.apply_update(data)
    tab = Tab.objects.filter(room=room).first()
    document = tab.document if tab is not None else Node.objects.get(room=room)
    nodes = placing.nodes_of(placing.of_document(document))
    calculation.current(document, nodes.keys(), nodes)
    held = Sheets(
        tables_of(document),
        tab=None if tab is None else str(tab.pk),
        defined=names.of_document(document),
        placing=nodes,
        document=document,
    )
    return reading(state, held)
