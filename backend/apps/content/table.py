"""A table's grid while a book holds it (D22, E3): its columns, its name and frozen row, how many
rows it has and, of its rows, only what lays the table out before its rows are read: heights,
looks, the rows hidden and the merged cells, each by its row's id. The rows themselves stay in
Postgres, read by place or by id as a change or a browser needs them.

A change works on a `Draft` of the table: the rows it reads are read once and copied before
they change, and the lines it puts in, takes out and reorders are noted in turn, so that where
a row stands is known within the change as it goes, and its patch is made from the notes and
the rows it changed, never from the table compared whole."""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db import connection

from . import grids
from . import rows as stored
from .grids import COLS, LOOK, ROWS, TO, Col, Laid, Look, Row, cleaned, shared_of
from .models import Grid, Shared


@dataclass
class Table:
    table: str
    grid: int
    tab: object = None
    name: str = ""
    cols: list[Col] = field(default_factory=list)
    frozen: str | None = None
    size: int = 0
    heights: dict[str, float] = field(default_factory=dict)
    looks: dict[str, Look] = field(default_factory=dict)
    hidden: set[str] = field(default_factory=set)
    merges: dict[str, str] = field(default_factory=dict)

    def col(self, id: str) -> Col | None:
        return next((col for col in self.cols if col.id == id), None)

    def col_ids(self) -> list[str]:
        return [col.id for col in self.cols]

    def named(self) -> set[str]:
        """The rows the table's layout names by id."""
        found = set(self.heights) | set(self.looks) | self.hidden
        for key, to in self.merges.items():
            found |= {key.partition(":")[0], to.partition(":")[0]}
        if self.frozen:
            found.add(self.frozen)
        return found


def _jsonb(given):
    return json.loads(given) if isinstance(given, str) else given


def tables_of(document, tables: Iterable[str] | None = None) -> dict[str, Table]:
    """The document's tables as a book holds them, those given or all of them, by table id."""
    grids = Grid.objects.filter(document=document)
    if tables is not None:
        grids = grids.filter(table__in=list(tables))
    grids = list(grids)
    if not grids:
        return {}
    keys = {col["look"] for grid in grids for col in grid.cols if "look" in col}
    by_pk: dict[int, Table] = {}
    for grid in grids:
        by_pk[grid.pk] = Table(
            grid.table,
            grid.pk,
            None if grid.tab_id is None else str(grid.tab_id),
            grid.name,
            frozen=grid.frozen or None,
        )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT grid_id, count(*) FROM content_gridrow WHERE grid_id = ANY(%s) "
            "GROUP BY grid_id",
            [list(by_pk)],
        )
        for grid, size in cursor.fetchall():
            by_pk[grid].size = size
        cursor.execute(
            "SELECT grid_id, row, height, look, hidden, (SELECT jsonb_object_agg(k, v->'to') "
            "FROM jsonb_each(cells) AS e(k, v) WHERE v ? 'to') FROM content_gridrow "
            "WHERE grid_id = ANY(%s) AND (height IS NOT NULL OR look <> '' OR hidden "
            "OR jsonb_path_exists(cells, '$.*.to'))",
            [list(by_pk)],
        )
        named = cursor.fetchall()
    keys |= {row_look for *_, row_look, _, _ in named if row_look}
    shared = (
        shared_of(
            dict(
                Shared.objects.filter(document=document, key__in=list(keys)).values_list(
                    "key", "value"
                )
            )
        )
        if keys
        else {}
    )
    for grid in grids:
        by_pk[grid.pk].cols = [
            Col(col["id"], col.get("width"), shared.get(col.get("look")), col.get("hidden", False))
            for col in grid.cols
        ]
    for grid, id, height, row_look, hidden, merges in named:
        table = by_pk[grid]
        if height is not None:
            table.heights[id] = height
        if row_look:
            table.looks[id] = shared[row_look]
        if hidden:
            table.hidden.add(id)
        for col, to in (_jsonb(merges) or {}).items():
            if to:
                table.merges[f"{id}:{col}"] = to
    return {table.table: table for table in by_pk.values()}


class Draft:
    """A change to a table as it goes: its rows read as asked for, each copied before it changes
    (`own`), and its lines put in, taken out and reordered noted in turn (`edits`), each by
    places as the table stood just before it: ("put", place, ids), ("out", places) and
    ("order", first place, ids in their new order)."""

    def __init__(self, document, table: Table):
        self.document = document
        self.base = table
        self.table = table.table
        self.tab = table.tab
        self.name = table.name
        self.cols = [Col(col.id, col.width, col.look, col.hidden) for col in table.cols]
        self.frozen = table.frozen
        self.read: dict[str, Row | None] = {}
        self.owned: dict[str, Row] = {}
        self.made: dict[str, Row] = {}
        self.edits: list[tuple] = []
        self.size = table.size
        self.stood: dict[str, int | None] = {}

    # Where rows stand

    def places(self, ids: Iterable[str]) -> dict[str, int]:
        """Where each row given stands now, of those the table has."""
        ids = set(ids)
        found: dict[str, int] = {}
        born: dict[str, tuple[int, int]] = {}
        for index, edit in enumerate(self.edits):
            if edit[0] == "put":
                for offset, id in enumerate(edit[2]):
                    if id in ids:
                        born[id] = (edit[1] + offset, index + 1)
        base = self._based(ids - born.keys())
        starts = {id: (place, 0) for id, place in base.items()} | born
        for id, (place, since) in starts.items():
            now = self._traced(id, place, since)
            if now is not None:
                found[id] = now
        return found

    def _based(self, ids: set[str]) -> dict[str, int]:
        """Where the rows given stood before the change, read once each."""
        if wanted := ids - self.stood.keys():
            found = stored.places_of(self.base.grid, wanted)
            self.stood |= {id: found.get(id) for id in wanted}
        return {id: self.stood[id] for id in ids if self.stood[id] is not None}

    def _traced(self, id: str, place: int, since: int) -> int | None:
        for edit in self.edits[since:]:
            match edit:
                case ("put", at, ids):
                    if place >= at:
                        place += len(ids)
                case ("out", places):
                    if place in places:
                        return None
                    place -= sum(1 for each in places if each < place)
                case ("order", first, ids):
                    if first <= place < first + len(ids):
                        place = first + ids.index(id)
        return place

    def place(self, id: str) -> int | None:
        return self.places([id]).get(id)

    def has(self, id: str) -> bool:
        return self.place(id) is not None

    def ids_at(self, places: Iterable[int]) -> dict[int, str]:
        """The id of the row standing at each place given, of those the table reaches."""
        found: dict[int, str] = {}
        pending: dict[int, list[int]] = {}
        for wanted in places:
            if not 0 <= wanted < self.size:
                continue
            place, known = wanted, None
            for edit in reversed(self.edits):
                match edit:
                    case ("put", at, ids):
                        if at <= place < at + len(ids):
                            known = ids[place - at]
                            break
                        if place >= at + len(ids):
                            place -= len(ids)
                    case ("out", gone):
                        for each in sorted(gone):
                            if each <= place:
                                place += 1
                    case ("order", first, ids):
                        if first <= place < first + len(ids):
                            known = ids[place - first]
                            break
            if known is not None:
                found[wanted] = known
            else:
                pending.setdefault(place, []).append(wanted)
        for base, id in stored.ids_at(self.base.grid, pending).items():
            for wanted in pending[base]:
                found[wanted] = id
        return found

    def ids(self, first: int, last: int) -> list[str]:
        """The ids of the rows from the first place to the last, both included."""
        found = self.ids_at(range(max(first, 0), min(last, self.size - 1) + 1))
        return [found[place] for place in sorted(found)]

    def row_ids(self) -> list[str]:
        """Every row's id in order: for a change that reads the table whole, as a version or a
        copy of the table does."""
        return self.ids(0, self.size - 1)

    # Rows

    def load(self, ids: Iterable[str]) -> None:
        """Reads the rows given that were not read yet."""
        wanted = [id for id in set(ids) if id not in self.read and id not in self.made]
        if not wanted:
            return
        found = stored.read(self.document, self.base.grid, wanted)
        for id in wanted:
            self.read[id] = found[id][1] if id in found else None

    def row(self, id: str) -> Row | None:
        row = self.made.get(id) or self.owned.get(id)
        if row is None:
            self.load([id])
            row = self.read.get(id)
        return row if row is not None and self.has(id) else None

    def own(self, id: str) -> Row:
        """The row, to change: copied first, its cells' parts to be replaced, not changed in
        place."""
        if id in self.made and self.has(id):
            return self.made[id]
        if id not in self.owned:
            row = self.row(id)
            if row is None:
                raise KeyError(id)
            self.owned[id] = Row(
                row.id,
                row.height,
                {col: dict(cell) for col, cell in row.cells.items()},
                row.values,
                row.position,
                row.pk,
                row.look,
                row.shown,
                row.hidden,
            )
        return self.owned[id]

    def col(self, id: str) -> Col | None:
        return next((col for col in self.cols if col.id == id), None)

    def col_ids(self) -> list[str]:
        return [col.id for col in self.cols]

    def cell(self, row: str, col: str) -> dict:
        found = self.row(row)
        return found.cells.get(col, {}) if found else {}

    def inherited(self, row: str, col: str) -> Look | None:
        """The look a cell of the row and column takes where it has none of its own."""
        if row in self.owned or row in self.made:
            found = self.row(row).look
        else:
            found = self.base.looks.get(row)
        if found is not None:
            return found
        line = self.col(col)
        return None if line is None else line.look

    def look_at(self, row: str, col: str) -> Look | None:
        cell = self.cell(row, col)
        return cell[LOOK] if LOOK in cell else self.inherited(row, col)

    def looked(self) -> list[str]:
        """The rows with a look of their own."""
        mine = {**self.owned, **self.made}
        found = {id for id in self.base.looks if id not in mine}
        found |= {id for id, row in mine.items() if row.look is not None}
        return list(self.places(found))

    def holding(self, cols: set[str]) -> list[str]:
        """The rows with a cell in any of the columns given."""
        mine = {**self.owned, **self.made}
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT row FROM content_gridrow WHERE grid_id = %s AND cells ?| %s",
                [self.base.grid, sorted(cols)],
            )
            found = {id for (id,) in cursor.fetchall() if id not in mine}
        found |= {id for id, row in mine.items() if cols & row.cells.keys()}
        return list(self.places(found))

    def merges(self) -> dict[str, str]:
        """The slot each merged cell reaches, by "row:col", as the change leaves them."""
        found = {
            key: to
            for key, to in self.base.merges.items()
            if key.partition(":")[0] not in self.owned
        }
        for row in [*self.owned.values(), *self.made.values()]:
            for col, cell in row.cells.items():
                if cell.get(TO):
                    found[f"{row.id}:{col}"] = cell[TO]
        present = self.places({key.partition(":")[0] for key in found})
        return {key: to for key, to in found.items() if key.partition(":")[0] in present}

    # Lines

    def put_rows(self, ids: list[str], before: str | None, sizes: list[float | None]) -> None:
        at = self.size if before is None else self.place(before)
        if at is None:
            raise KeyError(before)
        for offset, id in enumerate(ids):
            size = sizes[offset] if offset < len(sizes) else None
            self.made[id] = Row(id, size)
        self.edits.append(("put", at, list(ids)))
        self.size += len(ids)

    def take_rows(self, ids: Iterable[str]) -> None:
        places = set(self.places(ids).values())
        if places:
            self.edits.append(("out", frozenset(places)))
            self.size -= len(places)

    def order_rows(self, first: int, ids: list[str]) -> None:
        self.edits.append(("order", first, list(ids)))

    def take_cols(self, ids: Iterable[str]) -> None:
        gone = set(ids)
        self.cols = [col for col in self.cols if col.id not in gone]
        for row in [*self.owned.values(), *self.made.values()]:
            row.cells = {col: cell for col, cell in row.cells.items() if col not in gone}

    def first(self, count: int) -> Laid:
        """The table as Postgres keeps it, of its rows only so many from the top."""
        rows = sorted(
            stored.read(self.document, self.base.grid, span=(0, count - 1)).values(),
            key=lambda each: each[0],
        )
        return Laid(
            self.table,
            self.tab,
            self.name,
            [Col(col.id, col.width, col.look, col.hidden) for col in self.cols],
            [row for _, row in rows],
            self.frozen,
        )

    def laid(self) -> Laid:
        """The table whole as the change leaves it: for what has to read every cell, within
        the ceiling on how much of it may be held at once."""
        base = grids.of_document(self.document, [self.table]).get(self.table)
        ids = base.row_ids() if base else []
        for edit in self.edits:
            match edit:
                case ("put", at, made):
                    ids[at:at] = made
                case ("out", places):
                    ids = [id for at, id in enumerate(ids) if at not in places]
                case ("order", first, ordered):
                    ids[first : first + len(ordered)] = ordered
        rows = (base.by_id() if base else {}) | self.owned | self.made
        return Laid(
            self.table,
            self.tab,
            self.name,
            [Col(col.id, col.width, col.look, col.hidden) for col in self.cols],
            [rows[id] for id in ids],
            self.frozen,
        )

    # The patch

    def _line(self, row: Row) -> dict:
        return (
            {
                "size": row.height,
                "cells": {col: cell for col, cell in row.cells.items() if cleaned(cell)},
            }
            | ({"look": row.look} if row.look is not None else {})
            | ({"hidden": True} if row.hidden else {})
        )

    def patch(self) -> dict | None:
        """What the change does to the table, none where it does nothing: the lines it put in,
        took out and reordered in turn, each row's put in with what it holds, and what changed
        of the rows that were there, each part with its before as the change found it."""
        base = self.base
        patch: dict = {"table": self.table}
        if self.name != base.name:
            patch["name"] = [base.name, self.name]
        if self.frozen != base.frozen:
            patch["frozen"] = [base.frozen, self.frozen]
        if cols := _cols(base.cols, self.cols):
            patch[COLS] = cols
        edits = []
        for edit in self.edits:
            match edit:
                case ("put", at, ids):
                    edits.append(["put", at, [[id, self._line(self.made[id])] for id in ids]])
                case ("out", places):
                    edits.append(["out", sorted(places)])
                case ("order", first, ids):
                    edits.append(["order", first, list(ids)])
        if edits:
            patch[ROWS] = {"edits": edits}
        was = {col.id: col for col in base.cols}
        widths = {
            col.id: [was[col.id].width, col.width]
            for col in self.cols
            if col.id in was and was[col.id].width != col.width
        }
        if widths:
            patch["widths"] = widths
        heights: dict = {}
        looks: dict = {ROWS: {}, COLS: {}}
        hidden: dict = {ROWS: {}, COLS: {}}
        cells: dict = {}
        for col in self.cols:
            if col.id in was and was[col.id].look != col.look:
                looks[COLS][col.id] = [was[col.id].look, col.look]
            if col.id in was and was[col.id].hidden != col.hidden:
                hidden[COLS][col.id] = [was[col.id].hidden, col.hidden]
        standing = {col.id for col in self.cols}
        present = self.places(self.owned)
        for id, row in self.owned.items():
            old = self.read[id]
            if id not in present:
                continue
            if old.height != row.height:
                heights[id] = [old.height, row.height]
            if old.look != row.look:
                looks[ROWS][id] = [old.look, row.look]
            if old.hidden != row.hidden:
                hidden[ROWS][id] = [old.hidden, row.hidden]
            for col in standing & (old.cells.keys() | row.cells.keys()):
                before, after = cleaned(old.cells.get(col)), cleaned(row.cells.get(col))
                if before != after:
                    cells.setdefault(id, {})[col] = [before, after]
        if heights:
            patch["heights"] = heights
        if looks := {axis: lines for axis, lines in looks.items() if lines}:
            patch["looks"] = looks
        if hidden := {axis: lines for axis, lines in hidden.items() if lines}:
            patch["hidden"] = hidden
        if cells:
            patch["cells"] = cells
        return patch if len(patch) > 1 else None


def _cols(before: list[Col], after: list[Col]) -> dict:
    """The columns put in, taken out and reordered, as a grid's patch tells them; a column taken
    out with no cells, which applying it finds."""
    was, now = [col.id for col in before], [col.id for col in after]
    had, has = set(was), set(now)
    by_id = {col.id: col for col in after}
    found: dict = {}
    out = [[id, was[at - 1] if at else None, at, {}] for at, id in enumerate(was) if id not in has]
    put = [
        [
            id,
            now[at - 1] if at else None,
            at,
            {"size": by_id[id].width}
            | ({"look": by_id[id].look} if by_id[id].look is not None else {})
            | ({"hidden": True} if by_id[id].hidden else {}),
        ]
        for at, id in enumerate(now)
        if id not in had
    ]
    kept_before = [id for id in was if id in has]
    kept_after = [id for id in now if id in had]
    if kept_before != kept_after:
        found["order"] = [kept_before, kept_after]
    if out:
        found["out"] = out
    if put:
        found["put"] = put
    return found
