"""A document's grids and defined names while it is in use (D16): their outlines held in memory
while a room of the document is open or a browser watches it, each change written to Postgres
before it is applied there, then sent to every browser watching the table. While a book lives
it is its grids' and names' one writer.

A browser that watches a document is sent the document's defined names and the size of each
table a formula can name, then each table's columns and how many rows it has of the tabs it
watches; it asks for the rows it shows by where they stand, is told their ids and sent their
cells, and is sent, of every change, where its lines went and what concerns the rows it
holds. A formula reaches it as text in the canonical form, its references in A1 by the places
rows and columns have now; the ids it is kept by stay on the server.

The book keeps what its tables calculate current in Postgres (calculation.py): a change to a
grid, to the text of a table's cells or to which tables stand in the tabs' texts marks what it
touched, and what the marked cells reach is calculated off the event loop, the changes that
arrive meanwhile taken together in the next pass. The rows calculated are sent to the browsers
holding them, and what the charts show is written into the state of their tab: a live tab's
room, or an idle tab's store."""

import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from logging import getLogger
from math import inf
from threading import get_ident
from typing import IO

from anyio import Event, Lock, create_memory_object_stream
from django.db import transaction
from pycrdt import Doc

from apps.actions.models import RunChange
from apps.content import calculation, charts, compute, filtering, grids, names, placing
from apps.content import rows as stored
from apps.content.blocks import key_of
from apps.content.charts import Chart
from apps.content.elements import column
from apps.content.filtering import View
from apps.content.grids import COLS, FORMAT, FORMULA, LOOK, ROWS, TEXT, TO, Look, Row
from apps.content.models import TableFilter
from apps.content.patching import Done
from apps.content.placing import Follower, Placing
from apps.content.sheets import Places, Sheets, apply_stored, parted
from apps.content.table import Draft, Table, tables_of
from apps.core.asyncdb import database
from apps.documents.models import Node
from apps.versions.history import lock

# The edits of a document a browser can still take back, the oldest forgotten first.
KEPT = 1000
SHOWN = (TEXT, FORMAT, LOOK, TO)
Looks = dict[str, Look]
# What a patch changes of its table that has the table calculated whole again.
WHOLE = {COLS, "made"}
UNPLACED = Placing()

log = getLogger(__name__)


def shown(cell: dict, places: Places, table: str, row: str, col: str, looks: Looks) -> dict:
    """A cell as a browser holds it: its formula as text and its look by key, which `looks`
    gathers."""
    found = {part: cell[part] for part in SHOWN if part in cell}
    if isinstance(cell.get(FORMULA), list):
        found[FORMULA] = places.text(cell[FORMULA], table, row, col)
    if LOOK in found:
        found[LOOK] = grids.keyed(found[LOOK], looks)
    return found


def outline(
    table: Table,
    looks: Looks,
    view: View | None = None,
    at: Mapping[str, int] | None = None,
) -> dict:
    """A grid without its rows: its name, its columns with their widths, how many rows it has,
    the heights set, the looks of the rows and the columns that have one by key, the lines
    hidden, the slot each merged cell reaches, the last frozen row and where each row these name
    stands, the first and the last among them, which a browser lays the table out by before it
    holds the rows it shows: `at` where it is given, else read from Postgres. Where a view is
    given, the rows are those it shows, places counted among them, with each named row's own
    place as its number, the hidden ones left
    out, and the conditions of the user's filter of the table."""
    found = {
        "table": table.table,
        "name": table.name,
        "cols": [[col.id, col.width] for col in table.cols],
        "rows": table.size,
        "heights": dict(table.heights),
        "looks": {
            axis: found
            for axis, lines in (
                (ROWS, table.looks.items()),
                (COLS, ((col.id, col.look) for col in table.cols)),
            )
            if (found := {id: grids.keyed(look, looks) for id, look in lines if look is not None})
        },
        "hidden": {
            axis: ids
            for axis, ids in (
                (ROWS, sorted(table.hidden)),
                (COLS, [col.id for col in table.cols if col.hidden]),
            )
            if ids
        },
        "merges": dict(table.merges),
        "frozen": table.frozen,
    }
    if view is not None:
        found["hidden"].pop(ROWS, None)
        found["rows"] = stored.count(table.grid, view)
        if view.conditions:
            found["filter"] = list(view.conditions)
        found |= _placed(table, _named(found) | _ends(table, view, found["rows"]), view)
    elif at is not None:
        found["at"] = dict(at)
    else:
        found["at"] = _standing(table, _named(found) | _ends(table))
    return found


def _named(told: dict) -> set[str]:
    """The rows an outline or a patch names by id: by their heights, their looks, being
    hidden or shown, the merged cells they hold or reach and the frozen row."""
    found = set(told.get("heights", {})) | set(told.get("looks", {}).get(ROWS, {}))
    found |= set(told.get("hidden", {}).get(ROWS, {}))
    for key, to in told.get("merges", {}).items():
        found.add(key.split(":")[0])
        if to:
            found.add(to.split(":")[0])
    if told.get("frozen"):
        found.add(told["frozen"])
    return found


def _ends(table: Table, view: View | None = None, size: int | None = None) -> set[str]:
    size = table.size if size is None else size
    return set(stored.ids_at(table.grid, {0, size - 1}, view).values()) if size else set()


def _standing(table: Table, ids: Iterable[str]) -> dict[str, int]:
    return stored.places_of(table.grid, ids)


def _placed(table: Table, ids: Iterable[str], view: View | None) -> dict:
    """Where the rows given stand, of those the view shows, and where it shows only some, each
    one's own place as its number."""
    at = stored.places_of(table.grid, ids, view)
    if view is None:
        return {"at": at}
    return {"at": at, "numbers": stored.places_of(table.grid, at)}


def merged(table: Table) -> list[tuple[str, str, str]]:
    """The table's merged cells, each (row, col, the slot it reaches)."""
    return [(*key.split(":", 1), to) for key, to in table.merges.items()]


def _merges(patch: dict, table: Table | None = None, put: Iterable[str] = ()) -> dict:
    """The slots the patch's cells now reach where that changed, by "row:col", none where a
    cell no longer is merged: of the cells it wrote, of the columns it put back and, as the
    table now has them, of the rows it put in."""
    found: dict[str, str | None] = {}
    for row, cols in patch.get("cells", {}).items():
        for col, (was, now) in cols.items():
            if (was or {}).get(TO) != (now or {}).get(TO):
                found[f"{row}:{col}"] = (now or {}).get(TO)
    for id, _, _, line in patch.get(COLS, {}).get("put", []):
        for row, cell in line.get("cells", {}).items():
            if cell.get(TO):
                found[f"{row}:{id}"] = cell[TO]
    if table is not None and (put := set(put)):
        found |= {key: to for key, to in table.merges.items() if key.partition(":")[0] in put}
    return found


class Watcher:
    """A browser watching a document's grids: the tabs it watches, the rows it holds of each
    table and the text of each formula it was sent, its user's filters by table, and what is
    yet to be sent to it."""

    def __init__(self, signed, role):
        self.signed = signed
        self.user = signed.user
        self.role = role
        self.tabs: set[str | None] = set()
        self.held: dict[str, set[str]] = {}
        self.texts: dict[tuple[str, str, str], str] = {}
        self.looks: set[str] = set()
        self.filters: dict[str, list[dict]] | None = None
        self.outbox, self.inbox = create_memory_object_stream[dict](inf)
        self.loop = get_ident()
        self.queued: list[dict] = []
        self.closed = False

    def tell(self, message: dict, looks: Looks | None = None) -> None:
        """Sends the message, after the looks it names by key that the browser lacks; told
        off the event loop, as the book works on the database's thread, it waits there for
        `flush`, the stream being the loop's alone."""
        if looks and (
            lacked := {key: look for key, look in looks.items() if key not in self.looks}
        ):
            self.looks |= lacked.keys()
            self._send({"type": "looks", "looks": lacked})
        self._send(message)

    def _send(self, message: dict) -> None:
        if get_ident() != self.loop:
            self.queued.append(message)
            return
        self.flush()
        if not self.closed:
            self.outbox.send_nowait(message)

    def flush(self) -> None:
        queued, self.queued = self.queued, []
        if not self.closed:
            for message in queued:
                self.outbox.send_nowait(message)

    def close(self) -> None:
        self.closed = True
        self.outbox.close()


@dataclass
class Kept:
    """An edit a browser made, to take back: the room it was made in, what it changed and
    what of the room's state the change is kept in, none for a tab's text and names."""

    room: str
    change: object
    scopes: Callable | None = None


@dataclass
class Book:
    """A document's grids and names while it is in use, and what its tables calculate, with
    by table the keys of the formulas each column holds and its merged cells, which
    calculating reads, and the tables that stood in the text as it last did. `start` has
    `run` started, as the first change comes; `outside` writes what charts show into an idle
    tab's state, by the tab.

    It holds each grid's outline (`Table`); its rows stay in Postgres. What reads or writes
    them runs on the database's thread with the book's lock held, what it tells the browsers
    sent once it is back on the event loop."""

    document: object
    start: Callable[[], None] | None = None
    outside: Callable[[str, dict[str, dict]], Awaitable[None]] | None = None
    lock: Lock = field(default_factory=Lock)
    grids: dict[str, Table] = field(default_factory=dict)
    names: dict[str, dict] = field(default_factory=dict)
    locale: str = ""
    loaded: bool = False
    watchers: set[Watcher] = field(default_factory=set)
    kept: OrderedDict[str, Kept] = field(default_factory=OrderedDict)
    users: int = 0
    placings: dict[str, Placing] = field(default_factory=dict)
    followers: dict[str, Follower] = field(default_factory=dict)
    columns: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    merges: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    stood: set[str] = field(default_factory=set)
    marked: dict[str, set[str] | None] = field(default_factory=dict)
    moved: set[str] = field(default_factory=set)
    out: set[tuple[str, str]] = field(default_factory=set)
    named: set[str] = field(default_factory=set)
    redraw: set[str] = field(default_factory=set)
    cleared: set[str] = field(default_factory=set)
    replaced: bool = False
    wake: Event = field(default_factory=Event)
    passed: Event = field(default_factory=Event)
    running: bool = False
    computing: bool = False
    known: calculation.Known = field(default_factory=calculation.Known)

    async def off[R](self, work: Callable[..., R], *args, alone: bool = False) -> R:
        """Runs the work on the database's thread, or one of its own, then sends the browsers
        what it told them."""
        try:
            return await database(work, own_thread=alone)(*args)
        finally:
            for watcher in list(self.watchers):
                watcher.flush()

    async def load(self) -> None:
        """Reads the document's grids, names and tabs' texts the first time they are asked
        for."""
        if self.loaded:
            return
        found = await database(_read)(self.document, self._keeping(), self.known)
        if not self.loaded:
            self.loaded = True
            self._took_in(*found)

    async def reload(self) -> None:
        """Reads the document's grids, names and idle tabs' texts again, the book's lock held,
        as something wrote them outside the book, has its tables computed again and the
        browsers watching them start over."""
        if not self.loaded:
            return
        self._took_in(*await database(_read)(self.document, self._keeping(), self.known))
        self.marked = dict.fromkeys(self.grids)
        self._wake()
        await self.off(self._restart)

    async def grew(self) -> None:
        """Reads the document's grids again, the book's lock held, as an import has written
        rows into them, and has the browsers lay them out again; nothing is computed."""
        if self.loaded:
            self._took_in(*await database(_read)(self.document, self._keeping(), self.known))
            await self.off(self._restart)

    def _restart(self) -> None:
        for watcher in list(self.watchers):
            watcher.held.clear()
            watcher.texts.clear()
            watcher.tell(self.index())
            watcher.tell(self.defined())
            for tab in watcher.tabs:
                looks: Looks = {}
                found = self.outlines(tab, looks, watcher)
                watcher.tell({"type": "grids", "tab": tab, "grids": found}, looks)

    def _keeping(self) -> set[str]:
        """The keys of the rows that the edits the book keeps to take back keep in Postgres."""
        return stored.kept_in(
            patch for each in self.kept.values() for patch in getattr(each.change, "grids", [])
        )

    def _took_in(self, found, defined, placings, locale, columns) -> None:
        self.grids, self.names, self.locale, self.columns = found, defined, locale, columns
        self.merges = {table: merged(each) for table, each in found.items()}
        self.placings = self._followed(placings)
        self.stood = self._standing()
        # What the charts show was drawn over values the reading may have calculated again.
        self.redraw |= {id for each in self.placings.values() for id in each.charts}

    def _standing(self) -> set[str]:
        return {table for table in placing.nodes_of(self.placings) if table in self.grids}

    def of(self, tab: str | None) -> dict[str, Table]:
        return {table: each for table, each in self.grids.items() if each.tab == tab}

    def sheets(self, tab: str | None = None, order: Iterable[str] | None = None) -> Sheets:
        return Sheets(
            self.grids,
            order,
            tab,
            self.names,
            placing.nodes_of(self.placings),
            document=self.document,
        )

    def outlines(self, tab: str | None, looks: Looks, watcher: Watcher) -> list[dict]:
        return [
            outline(each, looks, view=self.view(watcher, each)) for each in self.of(tab).values()
        ]

    def view(self, watcher: Watcher, table: Table) -> View | None:
        """The rows of the table the browser is shown, by its user's filter of it, none where
        it is shown every row."""
        cols = set(table.col_ids())
        conditions = tuple(
            each for each in (watcher.filters or {}).get(table.table, ()) if each["col"] in cols
        )
        if not conditions and not table.hidden:
            return None
        return View(conditions, self.locale)

    def index(self) -> dict:
        """The tables a formula can name, each with its size and its tab."""
        sheets = self.sheets()
        found = [
            [table, each.name, each.size, len(each.cols), each.tab]
            for table, each in self.grids.items()
            if each.name and sheets.stands(table)
        ]
        return {"type": "tables", "tables": found}

    def defined(self) -> dict:
        """The defined names, each with the table it is in force in alone."""
        found = [[each["name"], each.get("table")] for each in self.names.values()]
        return {"type": "names", "names": found}

    def where(self, name: str, table: str | None) -> list | None:
        """The cells the defined name in force in the table stands for, by their table and
        address, where it stands for cells of a table that stands rather than for a formula."""
        entry = names.in_force(self.names, name, table)
        pieces = entry["pieces"] if entry else []
        piece = pieces[0] if len(pieces) == 1 and isinstance(pieces[0], dict) else {}
        found = self.grids.get(piece.get("table", ""))
        if found is None or not found.size or not self.sheets().stands(found.table):
            return None
        start, end = piece["from"], piece.get("to", piece["from"])
        rows = _standing(found, {point["row"] for point in (start, end) if "row" in point})
        cols = {id: at for at, id in enumerate(found.col_ids())}
        ends = []
        for point, edge in ((start, 0), (end, -1)):
            row = rows.get(point["row"]) if "row" in point else range(found.size)[edge]
            col = cols.get(point["col"]) if "col" in point else range(len(cols))[edge]
            if row is None or col is None:
                return None
            ends.append(f"{column(col)}{row + 1}")
        return [found.table, ends[0] if ends[0] == ends[1] else ":".join(ends)]

    def referred(self, table: str) -> bool:
        return compute.referred(self.sheets(), compute.names_in(self.names), table)

    def watch(self, watcher: Watcher, tab: str | None) -> None:
        if watcher.filters is None:
            watcher.filters = dict(
                TableFilter.objects.filter(
                    user_id=watcher.user, document_id=self.document
                ).values_list("table", "conditions")
            )
        if not watcher.tabs:
            watcher.tell(self.index())
            watcher.tell(self.defined())
        watcher.tabs.add(tab)
        looks: Looks = {}
        found = self.outlines(tab, looks, watcher)
        watcher.tell({"type": "grids", "tab": tab, "grids": found}, looks)

    def rows(self, watcher: Watcher, table: str, spans: list[tuple[int, int]]) -> None:
        """Tells the browser the ids of the rows it shows, the spans of places given with both
        ends, and sends it the cells and values of those it did not hold yet; it holds them
        and lets go of the rest."""
        found = self.grids.get(table)
        if found is None or found.tab not in watcher.tabs:
            return
        view = self.view(watcher, found)
        standing: dict[str, int] = {}
        for first, last in spans:
            first = max(first, 0)
            for offset, id in enumerate(stored.ids_in(found.grid, first, last, view)):
                standing[id] = first + offset
        held = watcher.held.setdefault(table, set())
        gone = held - standing.keys()
        for key in [key for key in watcher.texts if key[0] == table and key[1] in gone]:
            del watcher.texts[key]
        places = Places(self.sheets())
        nodes = placing.nodes_of(self.placings).get(table)
        sent = {}
        looks: Looks = {}
        read = stored.read(self.document, found.grid, standing.keys() - held)
        places.learn((table, cell) for _, row in read.values() for cell in row.cells.values())
        for id, (_, row) in read.items():
            cells = {}
            for col, cell in row.cells.items():
                cells[col] = shown(cell, places, table, id, col, looks)
                if FORMULA in cells[col]:
                    watcher.texts[(table, id, col)] = cells[col][FORMULA]
            sent[id] = {"cells": cells, "values": grids.told(row, nodes)}
        watcher.held[table] = set(standing)
        told = {"type": "rows", "table": table, "at": standing, "rows": sent}
        if view is not None:
            told["numbers"] = stored.places_of(found.grid, standing)
        watcher.tell(told, looks)

    def standing(
        self, watcher: Watcher, table: str, places: list[int], rows: list[str], numbers: list[int]
    ) -> dict:
        """Where the rows stand, of a table the browser watches: those at the places given,
        those of the ids given and those whose own places are the numbers given, which it
        names, a row gone or not shown left out; and where the browser is shown only some,
        each one's own place as its number."""
        found = self.grids.get(table)
        if found is None or found.tab not in watcher.tabs:
            return {"at": {}, "named": {}}
        view = self.view(watcher, found)
        named = stored.ids_at(found.grid, numbers) if numbers else {}
        at = {id: place for place, id in stored.ids_at(found.grid, places, view).items()}
        told = _placed(found, {*rows, *named.values()}, view)
        told["at"] |= at
        if view is not None:
            told["numbers"] |= stored.places_of(found.grid, at)
        return told | {"named": named}

    def filter(self, watcher: Watcher, table: str, conditions) -> None:
        """Keeps the user's filter of the table, none where no condition is given, and lays
        the table out again for each of the user's browsers watching it."""
        found = self.grids.get(table)
        if found is None or found.tab not in watcher.tabs:
            return
        kept = filtering.checked(conditions, found.col_ids(), self.locale)
        mine = {"user_id": watcher.user, "document_id": self.document, "table": table}
        if kept:
            TableFilter.objects.update_or_create(**mine, defaults={"conditions": kept})
        else:
            TableFilter.objects.filter(**mine).delete()
        for each in list(self.watchers):
            if each.user != watcher.user or each.filters is None:
                continue
            if kept:
                each.filters[table] = kept
            else:
                each.filters.pop(table, None)
            if found.tab in each.tabs:
                looks: Looks = {}
                laid = self._laid(each, found, looks)
                each.tell({"type": "patch", "by": None, "patches": [laid]}, looks)

    def values(self, watcher: Watcher, table: str, col: str) -> dict | None:
        """The texts the column shows in the rows the browser's other conditions let through,
        each with how many rows show it, and whether there are more."""
        found = self.grids.get(table)
        if found is None or found.tab not in watcher.tabs or col not in found.col_ids():
            return None
        view = self.view(watcher, found) or View(locale=self.locale)
        texts, more = filtering.texts(found.grid, view, col)
        return {"values": [list(each) for each in texts], "more": more}

    def _laid(self, watcher: Watcher, table: Table, looks: Looks) -> dict:
        """The table laid out anew for the browser, which keeps the cells of the rows it holds
        until it asks for those it shows."""
        return {"table": table.table, "laid": outline(table, looks, view=self.view(watcher, table))}

    def keep(self, token: str, room: str, change, scopes: Callable | None = None) -> None:
        self.kept[token] = Kept(room, change, scopes)
        self.kept.move_to_end(token)
        while len(self.kept) > KEPT:
            self.kept.popitem(last=False)

    async def edit[R](
        self,
        work: Callable[[Sheets], tuple[R, list[dict], bool]],
        tab: str | None = None,
        order: Iterable[str] | None = None,
        by: str | None = None,
        alone: bool = False,
    ) -> tuple[R, list[dict]]:
        """Works a change out over the sheets of the tab's tables and applies the patches it
        gives, with the guard it gives, the book's lock held: each to its grid in Postgres, or
        to the defined names, all of them in one transaction, then sent to the browsers
        watching them. Returns what the work gave and the patches as they went, with what they
        found."""
        value, done, renamed = await self.off(self._edited, work, tab, order, by, alone=alone)
        if renamed:
            self.named |= {
                each["name"]
                for patch in renamed
                for pair in patch[names.NAMES].values()
                for each in pair
                if each
            }
            self._wake()
        for each in done:
            held = self.columns.setdefault(each.patch["table"], {})
            for col, keys in each.keys.items():
                held.setdefault(col, set()).update(keys)
            self._mark(each)
        return value, [each.patch for each in done] + renamed

    async def commit(
        self, patches: list[dict], guard: bool = False, by: str | None = None
    ) -> list[dict]:
        """Applies the patches as `edit` does those its work gives."""
        if not patches:
            return []
        return (await self.edit(lambda sheets: (None, patches, guard), by=by))[1]

    def _edited(self, work, tab, order, by) -> tuple:
        value, patches, guard = work(self.sheets(tab, order))
        if not patches:
            return value, [], []
        now, defined, done, renamed = _stored(self.document, self.grids, self.names, patches, guard)
        if done or renamed:
            self.grids, self.names = now, defined
            self._tell(done, by)
            if renamed:
                for watcher in list(self.watchers):
                    watcher.tell(self.defined())
        return value, done, renamed

    def _holding(self) -> dict[str, set[str]]:
        """By table, the rows the browsers hold."""
        found: dict[str, set[str]] = {}
        for watcher in self.watchers:
            for table, rows in watcher.held.items():
                found.setdefault(table, set()).update(rows)
        return found

    def _took(self, found: calculation.Calculated, holding: Mapping[str, set[str]]) -> None:
        """Sends the rows calculated to the browsers holding them, those held as the pass
        started given, and those a browser came to hold since read again, as it may have read
        them before the pass wrote them."""
        watchers = list(self.watchers)
        nodes = placing.nodes_of(self.placings)
        told: dict[str, dict[str, dict]] = {}
        for table, rows in found.items():
            each = self.grids.get(table)
            if each is None:
                continue
            held = set().union(*(watcher.held.get(table, set()) for watcher in watchers))
            for id, cells in stored.cells_of(each.grid, held & rows.keys()).items():
                values, shown = rows[id]
                row = Row(id, cells=cells, values=values, shown=shown)
                told.setdefault(table, {})[id] = grids.told(row, nodes.get(table))
            if late := held - holding.get(table, set()):
                for id, (_, row) in stored.read(self.document, each.grid, late).items():
                    told.setdefault(table, {})[id] = grids.told(row, nodes.get(table))
        for watcher in watchers:
            patches = []
            looks: Looks = {}
            for table in found:
                each = self.grids.get(table)
                if each is None or each.tab not in watcher.tabs:
                    continue
                view = self.view(watcher, each)
                calculated = self.columns.get(table, {})
                if view is not None and any(
                    calculated.get(condition["col"]) for condition in view.conditions
                ):
                    patches.append(self._laid(watcher, each, looks))
            for table, rows in told.items():
                held = watcher.held.get(table, set())
                if mine := {row: values for row, values in rows.items() if row in held}:
                    patches.append({"table": table, "values": mine})
            if patches:
                watcher.tell({"type": "patch", "patches": patches}, looks)

    def follow(self, tab: str, doc: Doc) -> None:
        """Follows the text of a live tab, in the doc of its room, which charts are then drawn
        into."""
        follower = Follower(doc, lambda now, texts, moved: self._placed(tab, now, texts, moved))
        self.followers[tab] = follower
        self.placed(tab, follower.placing)

    def unfollow(self, tab: str) -> None:
        """Lets the tab's text go as its room closes: what it holds stays as it was left."""
        self.followers.pop(tab).close()

    def placed(self, tab: str, now: Placing) -> None:
        """Takes in what the text of the tab holds now."""
        self._placed(tab, now, *placing.compared(self.placings.get(tab, UNPLACED), now))

    def relocale(self, locale: str) -> None:
        self.locale = locale
        self.marked = dict.fromkeys(self.grids)
        self._wake()

    async def run(self) -> None:
        """Computes what changed, each pass taking together what changed meanwhile, until
        nobody uses the book and nothing is left to compute."""
        try:
            while self.users or self._pending():
                await self.wake.wait()
                self.wake = Event()
                self.computing = True
                try:
                    if self._pending():
                        await self._pass()
                except Exception:
                    log.exception("Computing the tables of document %s failed", self.document)
                finally:
                    self.computing = False
                    passed, self.passed = self.passed, Event()
                    passed.set()
        finally:
            self.running = False

    async def settled(self) -> None:
        """Returns once what has changed so far is computed."""
        while self.computing or self.wake.is_set():
            await self.passed.wait()

    def _pending(self) -> bool:
        return self.loaded and bool(
            self.marked
            or self.moved
            or self.out
            or self.named
            or self.redraw
            or self.cleared
            or self.replaced
        )

    def _wake(self) -> None:
        """Has what changed calculated, as the first change comes, not as the book is read,
        which a reader or a page count does without changing a table."""
        self.wake.set()
        if not self.running:
            self.running = True
            self.start()

    async def _pass(self) -> None:
        # The book's own work runs on threads of its own: the database's thread may be held by
        # whoever waits for this pass, and the thread of the request that woke the book first
        # is gone once it answers.
        if parted(self.sheets(), self.stood):
            async with self.lock:
                await self.edit(
                    lambda sheets: (None, _parted(sheets, self.stood), False), alone=True
                )
        if self.replaced:
            self.replaced = False
            async with self.lock:
                await self.off(self._restating, alone=True)
        marked, self.marked = self.marked, {}
        moved, self.moved = self.moved, set()
        out, self.out = self.out, set()
        named, self.named = self.named, set()
        redraw, self.redraw = self.redraw, set()
        cleared, self.cleared = self.cleared, set()
        nodes = placing.nodes_of(self.placings)
        standing = self._standing()
        changed: dict[str, set[tuple[str, str]] | None] = {
            table: None if keys is None else {_place(key) for key in keys}
            for table, keys in marked.items()
            if table in standing
        }
        changed |= dict.fromkeys(self.stood - standing)
        self.stood = standing
        drawn = {id: chart for each in self.placings.values() for id, chart in each.charts.items()}
        columns = {
            table: {col: set(keys) for col, keys in cols.items()}
            for table, cols in self.columns.items()
        }
        async with self.lock:
            holding = self._holding()
        found, shown = await database(_calculated, own_thread=True)(
            self.document,
            _Pass(standing, nodes, changed, columns, dict(self.merges), moved, named, out, holding),
            drawn,
            redraw,
            self.known,
        )
        async with self.lock:
            await self.off(self._took, found, holding, alone=True)
        by_tab: dict[str, dict[str, dict]] = {tab: {} for tab in cleared}
        for tab, each in self.placings.items():
            for id in each.charts.keys() & shown.keys():
                by_tab.setdefault(tab, {})[id] = shown[id]
        for tab, each in by_tab.items():
            if tab in self.followers:
                charts.store(self.followers[tab].doc, each)
            elif self.outside is not None:
                await self.outside(tab, each)

    def _mark(self, done: Done) -> None:
        """Marks what the grid's patch changed: its table whole, or the cells it wrote, with
        every cell of a row put in, of the rows beside one taken out, of a row hidden or shown,
        which a subtotal leaving out hidden rows reads, and of a row whose formulas now stand at
        other distances from the rows they name."""
        patch = done.patch
        table = patch["table"]
        if "gone" in patch:
            self.columns.pop(table, None)
            self.merges.pop(table, None)
            self.marked[table] = None
            self._wake()
            return
        found = self.grids[table]
        edits = patch.get(ROWS, {}).get("edits", [])
        if (
            WHOLE & patch.keys()
            or any(edit[0] == "order" for edit in edits)
            or _merges(patch, found, done.put)
        ):
            self.merges[table] = merged(found)
            self.marked[table] = None
            self._wake()
            return
        keys = {key_of(row, col) for row, cols in patch.get("cells", {}).items() for col in cols}
        whole = done.put | done.restated | patch.get("hidden", {}).get(ROWS, {}).keys()
        if done.out:
            whole |= done.beside
            self.out |= {(table, id) for id in done.out}
            self.merges[table] = merged(found)
        if edits:
            self.moved.add(table)
        cols = found.col_ids()
        keys |= {key_of(row, col) for row in whole - done.out for col in cols}
        if keys or edits or "name" in patch:
            self._marked(table, keys)
            self._wake()

    def _marked(self, table: str, keys: set[str]) -> None:
        if table not in self.marked:
            self.marked[table] = set(keys)
        elif (held := self.marked[table]) is not None:
            held |= keys

    def _placed(self, tab: str, now: Placing, texts: dict[str, set[str]], moved: bool) -> None:
        before = self.placings.get(tab, UNPLACED)
        self.placings[tab] = now
        for table, keys in texts.items():
            self._marked(table, keys)
        if moved:
            for table in set(before.tables) ^ set(now.tables):
                self.marked[table] = None
            self.redraw |= {
                id
                for id, chart in now.charts.items()
                if id not in before.charts or before.charts[id] != chart
            }
            if before.charts.keys() - now.charts.keys():
                self.cleared.add(tab)
            if set(before.tables) != set(now.tables):
                # The formulas whose text the tables' names write are told by the next pass,
                # which reads them from Postgres; a tab's text tells this in a Yjs callback.
                for watcher in self.watchers:
                    watcher.tell(self.index())
                self.replaced = True
        if texts or moved:
            self._wake()

    def _restating(self) -> None:
        places = Places(self.sheets())
        for watcher in list(self.watchers):
            looks: Looks = {}
            if told := self._restated(watcher, places, looks):
                watcher.tell({"type": "patch", "by": None, "patches": told}, looks)

    def _followed(self, placings: dict[str, Placing]) -> dict[str, Placing]:
        """The tabs' texts as read, those followed as they are live."""
        found = {
            tab: self.followers[tab].placing if tab in self.followers else each
            for tab, each in placings.items()
        }
        return found | {tab: each.placing for tab, each in self.followers.items()}

    def _tell(self, done: list[Done], by: str | None) -> None:
        if not done:
            return
        moved = any(_moves(each.patch) for each in done)
        resized = any(_resizes(each.patch) for each in done)
        places = Places(self.sheets())
        for watcher in list(self.watchers):
            if resized:
                watcher.tell(self.index())
            told = []
            looks: Looks = {}
            for each in done:
                if self._tab_of(each.patch) in watcher.tabs:
                    told.extend(self._shown(watcher, each, places, looks))
            if moved:
                told.extend(self._restated(watcher, places, looks))
            if told:
                watcher.tell({"type": "patch", "by": by, "patches": told}, looks)

    def _tab_of(self, patch: dict) -> str | None:
        if "made" in patch:
            return patch["made"].get("tab")
        if "gone" in patch:
            return patch["gone"].get("tab")
        return self.grids[patch["table"]].tab

    def _shown(self, watcher: Watcher, done: Done, places: Places, looks: Looks) -> list[dict]:
        """The patch as the browser is sent it: each edit of its rows apart, the lines taken
        out by where they stood, reordered from where the first of them stands and put in by
        where they stand after; then the rest, its columns as rows were, and where each other
        row it names stands now, the first and the last where its rows changed; of the cells,
        those of the rows it holds; and the looks by key, which `looks` gathers. A table made,
        or whose rows moved too many to tell, is sent whole again as its outline."""
        patch = done.patch
        table = patch["table"]
        if "gone" in patch:
            _forget(watcher, table)
            return [{"table": table, "gone": True}]
        found = self.grids[table]
        if "made" in patch or done.told is None:
            _forget(watcher, table)
            return [{"table": table, "made": outline(found, looks), "tab": found.tab}]
        view = self.view(watcher, found)
        relaid = ROWS in patch.get("hidden", {}) or (
            view is not None and (bool(done.told) or _filtered(view, patch))
        )
        held = watcher.held.setdefault(table, set())
        sent = [self._laid(watcher, found, looks)] if relaid else []
        for lines in [] if relaid else done.told:
            each: dict = {}
            hidden = {}
            if "out" in lines:
                each["out"] = lines["out"]
            if "put" in lines:
                each["put"] = [
                    [id, at, size, grids.keyed(look, looks)]
                    for id, at, size, look, _ in lines["put"]
                ]
                hidden = {id: True for id, *_, gone in lines["put"] if gone}
            if "order" in lines:
                each["order"] = lines["order"]
            sent.append(
                {"table": table, ROWS: each} | ({"hidden": {ROWS: hidden}} if hidden else {})
            )
        held -= done.out
        told: dict = {"table": table}
        for part in ("name", "frozen"):
            if part in patch:
                told[part] = patch[part][1]
        if COLS in patch:
            lines = patch[COLS]
            each = {}
            if "out" in lines:
                each["out"] = [at for _, _, at, _ in lines["out"]]
            if "put" in lines:
                each["put"] = [
                    [id, at, line.get("size"), grids.keyed(line.get("look"), looks)]
                    for id, _, at, line in lines["put"]
                ]
                for id, _, _, line in lines["put"]:
                    if line.get("hidden"):
                        told.setdefault("hidden", {}).setdefault(COLS, {})[id] = True
            if "order" in lines:
                each["order"] = [_between(found, lines), lines["order"][1]]
            told[COLS] = each
        if "widths" in patch:
            told["widths"] = {col: pair[1] for col, pair in patch["widths"].items()}
        if "heights" in patch:
            told["heights"] = {row: pair[1] for row, pair in patch["heights"].items()}
        if "looks" in patch:
            told["looks"] = {
                axis: {id: grids.keyed(pair[1], looks) for id, pair in lines.items()}
                for axis, lines in patch["looks"].items()
            }
        for axis, lines in patch.get("hidden", {}).items():
            if relaid and axis == ROWS:
                continue
            hidden = told.setdefault("hidden", {}).setdefault(axis, {})
            hidden |= {id: pair[1] for id, pair in lines.items()}
        if merges := _merges(patch, found, done.put):
            told["merges"] = merges
        rows = {row for row in patch.get("cells", {}) if row in held}
        for _, _, _, line in patch.get(COLS, {}).get("put", []):
            rows |= line.get("cells", {}).keys() & held
        if rows:
            cells: dict[str, dict] = {}
            cols = {id for id, _, _, _ in patch.get(COLS, {}).get("put", [])}
            stood = stored.read(self.document, found.grid, rows)
            places.learn(
                (table, cell) for _, read in stood.values() for cell in read.cells.values()
            )
            for row, (_, read) in stood.items():
                for col in set(patch.get("cells", {}).get(row, {})) | cols:
                    cell = read.cells.get(col)
                    each = shown(cell, places, table, row, col, looks) if cell else None
                    cells.setdefault(row, {})[col] = each
                    if each and FORMULA in each:
                        watcher.texts[(table, row, col)] = each[FORMULA]
                    else:
                        watcher.texts.pop((table, row, col), None)
            told["cells"] = cells
        named = set() if relaid else _named(told) | (_ends(found) if sent else set())
        if named and (placed := _placed(found, named, view))["at"]:
            told |= placed
        return sent + ([told] if len(told) > 1 else [])

    def _restated(self, watcher: Watcher, places: Places, looks: Looks) -> list[dict]:
        """The formulas the browser holds whose text lines moved, put in, taken out or
        renamed, have changed, as the cells they are in."""
        by_table: dict[str, set[str]] = {}
        for table, row, _ in watcher.texts:
            by_table.setdefault(table, set()).add(row)
        read = {
            table: stored.read(self.document, self.grids[table].grid, rows)
            for table, rows in by_table.items()
            if table in self.grids
        }
        places.learn(
            (table, cell)
            for table, rows in read.items()
            for _, row in rows.values()
            for cell in row.cells.values()
        )
        changed: dict[str, dict[str, dict]] = {}
        for (table, row, col), text in list(watcher.texts.items()):
            found = read.get(table, {}).get(row)
            cell = found[1].cells.get(col) if found is not None else None
            if cell is None or not isinstance(cell.get(FORMULA), list):
                watcher.texts.pop((table, row, col), None)
                continue
            now = shown(cell, places, table, row, col, looks)
            if now[FORMULA] != text:
                watcher.texts[(table, row, col)] = now[FORMULA]
                changed.setdefault(table, {}).setdefault(row, {})[col] = now
        return [{"table": table, "cells": cells} for table, cells in changed.items()]


def _filtered(view: View, patch: dict) -> bool:
    """Whether the patch wrote a cell of a column the view's conditions take, or put a column
    in."""
    cols = {condition["col"] for condition in view.conditions}
    return COLS in patch or any(cols & row.keys() for row in patch.get("cells", {}).values())


def _forget(watcher: Watcher, table: str) -> None:
    watcher.held.pop(table, None)
    for key in [key for key in watcher.texts if key[0] == table]:
        del watcher.texts[key]


def _parted(sheets: Sheets, kept: Iterable[str]) -> list[dict]:
    """The patches that name apart the tables standing that share a name, as `parted` does."""
    return sheets.patches() if parted(sheets, kept) else []


def wrote_whole(out: IO[bytes], kept: Mapping[str, Draft], sheets: Sheets) -> None:
    """Writes the grids given whole as a browser holds them, row by row, each with the ids of
    the rows it shows in order, their cells and what they show, by table and "row:col", their
    formulas' text by the document's grids, and where rows are hidden each one's own place as
    its number: what the pages print; and the looks they name, by key."""

    def text(value) -> bytes:
        return json.dumps(value, ensure_ascii=False).encode()

    places = Places(sheets)
    looks: Looks = {}
    nodes = sheets.placing or {}
    document = sheets.document
    out.write(b'{"grids":[')
    for at, (table, draft) in enumerate(kept.items()):
        told = outline(draft.base, looks)
        every = stored.ids_in(draft.base.grid, 0, draft.size - 1)
        hidden = draft.base.hidden
        ids = [id for id in every if id not in hidden] if hidden else every
        if told["hidden"].pop(ROWS, None):
            shown_at = {id: place for place, id in enumerate(ids)}
            told |= {
                "rows": len(ids),
                "at": {id: shown_at[id] for id in told["at"] if id in shown_at},
                "numbers": {id: y for y, id in enumerate(every) if id in shown_at},
            }
        out.write(b"," * bool(at) + text(told)[:-1] + b',"ids":' + text(ids) + b',"cells":{')
        columns = draft.col_ids()
        texts = nodes.get(table)
        written = False
        known = places.of(table)[0].found
        for part in stored.parts(document, draft.base.grid):
            known.update({row.id: place + 1 for place, row in part})
            places.learn((table, cell) for _, row in part for cell in row.cells.values())
            for _, row in part:
                if row.hidden:
                    continue
                computed = grids.told(row, texts)
                entry = {
                    "cells": {
                        col: shown(cell, places, table, row.id, col, looks)
                        for col, cell in row.cells.items()
                    },
                    "values": {col: computed[col] for col in columns if col in computed},
                }
                out.write(b"," * written + text(row.id) + b":" + text(entry))
                written = True
        out.write(b"}}")
    out.write(b'],"looks":' + text(looks) + b"}")


def _between(table: Table, lines: dict) -> int:
    """Where the first column a patch reorders stands once the columns it takes out are gone
    and before those it puts in are."""
    at = table.col_ids().index(lines["order"][1][0])
    return at - sum(1 for _, _, put, _ in lines.get("put", []) if put < at)


def _moves(patch: dict) -> bool:
    """Whether the patch moves what formulas refer to: lines put in, taken out or reordered,
    a grid made, dropped or renamed."""
    return bool({"made", "gone", "name", ROWS} & patch.keys()) or any(
        part in patch.get(COLS, {}) for part in ("put", "out", "order")
    )


def _resizes(patch: dict) -> bool:
    """Whether the patch changes a table a formula can name or its size."""
    return (
        bool({"made", "gone", "name"} & patch.keys())
        or any(edit[0] != "order" for edit in patch.get(ROWS, {}).get("edits", []))
        or any(part in patch.get(COLS, {}) for part in ("put", "out"))
    )


def _place(key: str) -> tuple[str, str]:
    row, _, col = key.partition(":")
    return row, col


@dataclass(frozen=True)
class _Pass:
    """What a pass calculates: the tables standing, by table the text of the cells that have
    a node, what changed, the keys of the formulas of each column, the merged cells, the
    tables whose rows moved, the defined names that changed, the rows taken out and by table
    the rows the browsers hold."""

    standing: set[str]
    texts: Mapping[str, Mapping[str, str]]
    changed: Mapping[str, set[tuple[str, str]] | None]
    columns: dict[str, dict[str, set[str]]]
    merges: dict[str, list[tuple[str, str, str]]]
    moved: set[str]
    named: set[str]
    out: set[tuple[str, str]]
    held: dict[str, set[str]]


@transaction.atomic(durable=True)
def _calculated(
    document,
    each: _Pass,
    drawn: Mapping[str, Chart | None],
    redraw: set[str],
    known: calculation.Known,
) -> tuple[calculation.Calculated, dict[str, dict]]:
    """Calculates the pass, the formulas `known` taken as they stand, then draws the charts
    given and those over a table it changed."""
    node = Node.objects.get(pk=document)
    found = calculation.calculate(
        node,
        each.standing,
        each.texts,
        each.changed,
        each.columns,
        each.merges,
        each.moved,
        each.named,
        each.out,
        told=each.held,
        known=known,
    )
    redraw = redraw | {
        id
        for id, chart in drawn.items()
        if chart is not None and (chart.table in found or chart.table in each.changed)
    }
    shown = {
        id: charts.read(node, drawn[id], each.standing, each.texts) for id in redraw if id in drawn
    }
    return found, shown


@transaction.atomic(durable=True)
def _read(document, kept: set[str], known: calculation.Known) -> tuple:
    """The document's grids, names, tabs' texts, locale and the keys of the formulas each
    column holds, once what is out of date is calculated and what no change can take back
    any more is forgotten: the rows kept for the edits not given by the keys they keep, nor
    a run's, and then what nothing shares."""
    node = lock(document)
    placings = placing.of_document(document)
    nodes = placing.nodes_of(placings)
    calculation.current(node, nodes.keys(), nodes, known)
    runs = RunChange.objects.filter(run__document=document).values_list("grids", flat=True)
    stored.unshare(document, kept | stored.kept_in(patch for each in runs for patch in each))
    found = tables_of(document)
    columns = calculation.columns_of(calculation.tables_of(node, found.keys()).values())
    return found, names.of_document(document), placings, node.locale, columns


# Durable: the book holds in memory what Postgres has, so its writes never ride on a caller's
# transaction that could still roll back.
@transaction.atomic(durable=True)
def _stored(
    document, tables: Mapping[str, Table], defined: Mapping[str, dict], patches: list, guard: bool
) -> tuple[dict[str, Table], dict[str, dict], list[Done], list[dict]]:
    """Applies the patches in Postgres, the defined names' stored with them."""
    # A version is taken, or restored, with the document locked, so never halfway through.
    lock(document)
    now, defined, done, renamed = apply_stored(document, tables, defined, patches, guard)
    for patch in renamed:
        names.store(document, patch)
    return now, defined, done, renamed
