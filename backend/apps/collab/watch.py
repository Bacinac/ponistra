"""A browser watching a document's grids, over a WebSocket of its own beside the Yjs rooms of
the document's tabs (D16). It says which tab it watches and the spans of the rows it shows by
where they stand, and sends its edits as the operations a run carries out (D14), each
with a token: the edit is carried out in the tab's room, or the document's own for a header's
or a footer's table, and can be taken back by its token while the book keeps it.

Messages are JSON, one per frame:

    browser → {"type": "watch", "tab": id | null}
              {"type": "rows", "table": id, "spans": [[first, last], …]}
              {"type": "do", "token": t, "tab": id | null, "operations": […], "after": [c, n]}
              {"type": "undo", "token": t, "as": t2, "after": [c, n]}
              {"type": "standing", "table": id, "places": [place, …], "rows": [id, …],
               "numbered": [number, …]}
              {"type": "referred", "table": id}
              {"type": "where", "name": n, "table": id | null}
              {"type": "filter", "table": id, "conditions": [condition, …]}
              {"type": "values", "table": id, "col": id}
    server  → {"type": "tables", "tables": [[table, name, rows, cols, tab | null], …]}
              {"type": "names", "names": [[name, table | null], …]}
              {"type": "grids", "tab": id | null, "grids": [outline, …]}
              {"type": "rows", "table": id, "at": {id: place, …}, "numbers": {id: number, …},
               "rows": {id: {"cells": …, "values": …}}}
              {"type": "patch", "by": t | null, "patches": […]}
              {"type": "done", "token": t} | {"type": "refused", "token": t, "code": …}
              {"type": "standing", "table": id, "places": […], "rows": […], "numbered": […],
               "at": {id: place, …}, "named": {number: id, …}, "numbers": {id: number, …}}
              {"type": "referred", "table": id, "referred": bool}
              {"type": "where", "name": n, "table": id | null, "at": [table, address] | null}
              {"type": "values", "table": id, "col": id, "values": [[text, count], …],
               "more": bool}
              {"type": "filtered", "table": id} | {"type": "unfiltered", "table": id, "code": …}

An edit comes after the browser's own edits to the room's state, up to clock n of its Yjs
client c (`after`, optional), and is carried out once the room has them. A browser that lost
the socket before an answer sends the edit again: one the book still keeps is answered done.
The tables a formula can name, with their sizes, and the defined names are sent as the browser
first watches and again as they change. Whether a formula or a defined name refers to a table,
which must then keep its name, is asked of the whole document, as the browser holds only the
rows it shows; so is where a defined name in force in a table leads, the table and the address
of the cells it stands for, as the name box goes there; and so are the ids of rows by where
they stand, as a range typed by its address names its ends, and where rows stand by their ids,
as a chart's range names its ends.

Each user sees a table through their own filter of it (filtering.py), kept for them alone and
in force in each of their browsers: the rows hidden or not meeting its conditions are left out
of what a browser is sent, the places of the rest counted among them and each row's own place
sent beside as its number, "numbers", which its header and its address show. The rows a
browser is not shown are named only by the numbers a typed address gives. An edit over a range
of rows reaches only the rows the filter shows; a browser shown only some rows has the table
laid out anew ("laid", its cells kept) as rows go in, out or hidden, or as a cell a condition
reads changes. "values" asks for the texts a column shows in the rows the other conditions let
through, each with how many rows show it."""

import json
import re
from contextlib import suppress
from functools import partial
from logging import getLogger
from time import monotonic
from uuid import UUID

from anyio import CancelScope, create_task_group
from django.core.exceptions import ValidationError

from apps.access.models import Role
from apps.content import filtering, operations, pages
from apps.content.sheets import Refused
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab
from apps.versions.history import contributed

from . import server
from .books import Book, Watcher
from .server import CONTRIBUTION_EVERY, live, refuse, role_in, same_origin, signed_in

GRID_PATH = re.compile(
    r"/api/grids/(?P<document>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}")

log = getLogger(__name__)


@database
def _place(document: UUID, tab: str | None) -> tuple[str, str] | None:
    """The room of the tab, or of the document's own state, and its locale."""
    node = Node.objects.filter(pk=document).first()
    if node is None or node.room is None:
        return None
    if tab is None:
        return str(node.room), node.locale
    try:
        found = Tab.objects.filter(pk=tab, document=node).first()
    except ValidationError:
        return None
    return (str(found.room), node.locale) if found else None


def _after(message: dict) -> tuple[int, int] | None:
    after = message.get("after")
    if after is None:
        return None
    if (
        isinstance(after, list)
        and len(after) == 2
        and all(type(each) is int and each >= 0 for each in after)
    ):
        return after[0], after[1]
    raise Refused("invalid", "after")


def _places(value) -> bool:
    return isinstance(value, list) and all(
        isinstance(each, int) and not isinstance(each, bool) for each in value
    )


def _ids(value) -> bool:
    return isinstance(value, list) and all(isinstance(each, str) for each in value)


def _spans(value) -> list[tuple[int, int]] | None:
    if isinstance(value, list) and all(
        isinstance(span, list) and len(span) == 2 and _places(span) for span in value
    ):
        return [(first, last) for first, last in value]
    return None


class Watching:
    def __init__(self, send, document: UUID, book: Book, watcher: Watcher):
        self.send = send
        self.document = document
        self.book = book
        self.watcher = watcher
        self.contributed = -CONTRIBUTION_EVERY

    async def deliver(self, scope: CancelScope) -> None:
        """Sends what the book has for the browser until it lets the browser go."""
        async with self.watcher.inbox:
            async for message in self.watcher.inbox:
                with suppress(OSError):
                    await self.send({"type": "websocket.send", "text": json.dumps(message)})
        scope.cancel()

    async def take(self, message: dict) -> None:
        match message.get("type"):
            case "watch":
                tab = message.get("tab")
                if tab is not None and not isinstance(tab, str):
                    return
                if await _place(self.document, tab) is None:
                    return
                await self.book.load()
                await self.held(self.book.watch, self.watcher, tab)
            case "rows":
                table, spans = message.get("table"), _spans(message.get("spans"))
                if isinstance(table, str) and spans is not None:
                    await self.held(self.book.rows, self.watcher, table, spans)
            case "do":
                await self.answer(message.get("token"), partial(self.do, message))
            case "undo":
                await self.answer(message.get("token"), partial(self.undo, message))
            case "standing":
                table, places, rows = (message.get(key) for key in ("table", "places", "rows"))
                numbers = message.get("numbered", [])
                if (
                    not isinstance(table, str)
                    or not _places(places)
                    or not _ids(rows)
                    or not _places(numbers)
                ):
                    return
                told = await self.held(
                    self.book.standing, self.watcher, table, places, rows, numbers
                )
                asked = {"places": places, "rows": rows, "numbered": numbers}
                self.watcher.tell({"type": "standing", "table": table, **asked, **told})
            case "filter":
                table, conditions = message.get("table"), message.get("conditions")
                if not isinstance(table, str):
                    return
                try:
                    await self.held(self.book.filter, self.watcher, table, conditions)
                except filtering.Invalid as invalid:
                    self.watcher.tell({"type": "unfiltered", "table": table, "code": str(invalid)})
                else:
                    self.watcher.tell({"type": "filtered", "table": table})
            case "values":
                table, col = message.get("table"), message.get("col")
                if not isinstance(table, str) or not isinstance(col, str):
                    return
                found = await self.held(self.book.values, self.watcher, table, col)
                if found is not None:
                    self.watcher.tell({"type": "values", "table": table, "col": col, **found})
            case "referred":
                table = message.get("table")
                if not isinstance(table, str):
                    return
                await self.book.load()
                found = await self.held(self.book.referred, table)
                self.watcher.tell({"type": "referred", "table": table, "referred": found})
            case "where":
                name, table = message.get("name"), message.get("table")
                if not isinstance(name, str) or not isinstance(table, str | None):
                    return
                await self.book.load()
                at = await self.held(self.book.where, name, table)
                self.watcher.tell({"type": "where", "name": name, "table": table, "at": at})

    async def held(self, work, *args):
        """What the work gives, done over the book's rows with its lock held."""
        async with self.book.lock:
            return await self.book.off(work, *args)

    async def answer(self, token, act) -> None:
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            return
        try:
            if self.watcher.role == Role.READ:
                raise Refused("read_only")
            await act(token)
        except Refused as refused:
            self.watcher.tell(
                {
                    "type": "refused",
                    "token": token,
                    "code": refused.code,
                    "detail": refused.detail,
                    "operation": refused.operation,
                }
            )
            return
        self.watcher.tell({"type": "done", "token": token})
        if monotonic() - self.contributed > CONTRIBUTION_EVERY:
            self.contributed = monotonic()
            await database(contributed)(self.document, self.watcher.user)

    async def do(self, message: dict, token: str) -> None:
        if token in self.book.kept:
            return
        tab, given = message.get("tab"), message.get("operations")
        if tab is not None and not isinstance(tab, str) or not isinstance(given, list):
            raise Refused("invalid")
        place = await _place(self.document, tab)
        if place is None:
            raise Refused("no_tab", str(tab))
        room, locale = place
        own = tab is None
        seen = {
            table: filtering.View(tuple(conditions), locale)
            for table, conditions in (self.watcher.filters or {}).items()
        }
        table = next((each.get("table") for each in given if isinstance(each, dict)), None)

        def edit(doc, sheets):
            into = scopes = None
            if own:
                if pages.holding(doc, table) is None:
                    raise Refused("no_table", str(table))
                into = partial(pages.holding, table=table)
                scopes = pages.fragments
            return operations.carry_out(
                doc, sheets, given, locale, token, into=into, scopes=scopes, seen=seen
            )

        performed = await server.collab.perform(
            room, edit, settle=False, by=token, after=_after(message)
        )
        if performed.change:
            self.book.keep(token, room, performed.change, pages.fragments if own else None)

    async def undo(self, message: dict, token: str) -> None:
        then = message.get("as")
        if not isinstance(then, str) or not TOKEN.fullmatch(then):
            raise Refused("invalid")
        kept = self.book.kept.get(token)
        if kept is None:
            if then in self.book.kept:
                return
            raise Refused("forgotten", token)
        change = await server.collab.perform(
            kept.room,
            lambda doc, sheets: operations.take_back(kept.change, kept.scopes),
            settle=False,
            by=then,
            after=_after(message),
        )
        del self.book.kept[token]
        self.book.keep(then, kept.room, change, kept.scopes)


async def watch(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    match = GRID_PATH.fullmatch(scope["path"])
    if match is None or not same_origin(scope):
        await send({"type": "websocket.close"})
        return
    if (
        (signed := await signed_in(scope)) is None
        or not await live(match["document"])
        or (role := await role_in(signed, match["document"])) is None
    ):
        await refuse(send)
        return
    document = UUID(match["document"])
    await send({"type": "websocket.accept"})
    book = server.collab.book(document)
    watcher = Watcher(signed, role)
    watching = Watching(send, document, book, watcher)
    book.watchers.add(watcher)
    try:
        async with create_task_group() as group:
            group.start_soon(watching.deliver, group.cancel_scope)
            while True:
                message = await receive()
                if message["type"] != "websocket.receive":
                    break
                try:
                    data = json.loads(message.get("text") or "")
                except ValueError:
                    break
                if isinstance(data, dict):
                    await watching.take(data)
            group.cancel_scope.cancel()
    finally:
        book.watchers.discard(watcher)
        watcher.close()
        server.collab.release(document)
        with suppress(OSError):
            await send({"type": "websocket.close"})
