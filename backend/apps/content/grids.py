"""Tables' grids as Postgres rows (D16). A table block stays in its tab's text; its columns,
its rows and what each cell holds beside the text are a `Grid` and its `GridRow`s.

A cell holds what was typed into it (`text`, where it has no node in the text), its formula
in pieces by row and column id (`formula`), its number format (`format`), the look of its
text where it has no node (`look`: the marks over all of it and its paragraph's attributes)
and, merged, the slot it reaches down and right to (`to`, "row:col"). The value of each cell
and the text it shows are the row's `values` and `shown`, which calculation.py alone writes. A
row and a column can
have a look too, which a light cell without one of its own shows: its row's, else its column's,
as Excel styles a whole row or column; a cell plain in such a line holds a look with nothing in
it.

A change to a grid is a patch: the lines it put in and took out, each with where it stood
and what it held, the lines it moved, and each cell, height, width, line's look, name and
frozen row it changed, before and after. A patch applied keeps what it found as its before,
so its inverse takes it back; taken back with a guard, each part goes back only where nobody
changed it since.

A formula refers to the row and the column of its own cell as such (`OWN`) and, as Postgres and
versions keep it, to another row of its own table written relative by how far that row stands
from its own (`stored_formula`), so a formula filled down a column is the same pieces in every
row. A reference written absolute, one to another table, whose rows do not move with this
one's, and one to a row no longer there keep the row's id. Cells and lines holding the same
formula or look hold one object, which nothing changes in place, and Postgres keeps it once
per document (`Shared`), each row and column naming it by key."""

import base64
import builtins
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal
from weakref import WeakValueDictionary

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.content.models import Grid, GridRow, Shared
from apps.documents.models import Node

TEXT = "text"
FORMULA = "formula"
FORMAT = "format"
LOOK = "look"
TO = "to"
INPUTS = (TEXT, FORMULA, FORMAT, LOOK, TO)

ROWS = "rows"
COLS = "cols"
Axis = Literal["rows", "cols"]

# Rows stand this far apart, so thousands can be put in between before they are spaced again.
STEP = 1 << 20
# What may be held of one table as a tree of Python objects (D22): about 140 MB.
MOST_CELLS = 200_000

OWN = "@"


class Formula(list):
    """A formula's pieces as the cells holding it share them, never changed in place."""

    __slots__ = ("__weakref__", "key")

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


class Look(dict):
    """A look as the cells in it share it, never changed in place."""

    __slots__ = ("__weakref__", "key")

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


_held: WeakValueDictionary[str, Formula | Look] = WeakValueDictionary()


def digest(value) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(hashlib.sha256(text.encode()).digest()[:9]).decode()


def _one(value, kind: type[Formula] | type[Look], key: str | None = None) -> Formula | Look:
    """The one object holding the value, its key a digest of it."""
    key = key or digest(value)
    found = _held.get(key)
    if found is None:
        found = kind(value)
        found.key = key
        _held[key] = found
    return found


def look(value: dict) -> Look:
    return value if type(value) is Look else _one(value, Look)


def _moved(piece, rows: tuple[str, str], cols: tuple[str, str]):
    """The piece with its references to the row `rows[0]` made to `rows[1]`, and the same of
    the columns."""
    if not isinstance(piece, dict) or "table" in piece:
        return piece
    ends = {}
    for end in ("from", "to"):
        point = piece.get(end)
        if isinstance(point, dict) and (point.get("row"), point.get("col")) != (None, None):
            moved = dict(point)
            for part, (was, now) in (("row", rows), ("col", cols)):
                if moved.get(part) == was:
                    moved[part] = now
            if moved != point:
                ends[end] = moved
    return {**piece, **ends} if ends else piece


def formula_at(pieces: list, row: str, col: str) -> Formula:
    """The formula of the cell at the row and column given, its pieces by ids: as the cell keeps
    it, the references to that row and column written OWN."""
    if type(pieces) is Formula:
        return pieces
    return _one([_moved(piece, (row, OWN), (col, OWN)) for piece in pieces], Formula)


def formula_in(pieces: list, row: str, col: str) -> list:
    """The formula a cell at the row and column given keeps, its pieces by ids."""
    return [_moved(piece, (OWN, row), (OWN, col)) for piece in pieces]


def moved_formula(pieces: list, before: tuple[str, str], after: tuple[str, str]) -> Formula:
    """The formula of a cell moved, as the cell keeps it where it is now: referring to what it
    referred to before."""
    return formula_at(formula_in(pieces, *before), *after)


def _rows_turned(formula: list, turn) -> list:
    """The pieces with the row of each point of a reference within its own table as `turn`
    gives it, the pieces themselves where none turns."""
    pieces, turned = [], False
    for piece in formula:
        if isinstance(piece, dict) and "table" not in piece:
            ends = {}
            for end in ("from", "to"):
                point = piece.get(end)
                if isinstance(point, dict) and "row" in point:
                    if (row := turn(point)) != point["row"]:
                        ends[end] = {**point, "row": row}
            if ends:
                piece, turned = {**piece, **ends}, True
        pieces.append(piece)
    return pieces if turned else formula


def stored_formula(formula: Formula, row: str, at: Mapping[str, int]) -> Formula:
    """The formula of the cell in the row as Postgres and versions keep it, given where each
    row of the table stands: a reference written relative to another row there by the distance
    to it, one written absolute to the cell's own row by the row's id."""
    own = at[row]

    def turn(point: dict):
        target = point["row"]
        if point.get("absRow"):
            return row if target == OWN else target
        if target != OWN and target in at:
            return at[target] - own or OWN
        return target

    turned = _rows_turned(formula, turn)
    return turned if type(turned) is Formula else _one(turned, Formula)


def _distance_changed(formula: list, row: str, was: Mapping[str, int], now: Mapping[str, int]):
    """Whether the formula of a cell in the row refers relatively to another row of its table
    as another distance, or another row by its id, once the rows stand as `now` says."""
    for piece in formula:
        if not isinstance(piece, dict) or "table" in piece:
            continue
        for end in ("from", "to"):
            point = piece.get(end)
            if not isinstance(point, dict) or point.get("absRow"):
                continue
            target = point.get("row")
            if target is None or target in (OWN, row):
                continue
            if (target in was) != (target in now):
                return True
            if target in now and was[target] - was[row] != now[target] - now[row]:
                return True
    return False


def held_formula(formula: Formula, row: str, col: str, own: int, ids: Sequence[str]) -> Formula:
    """The formula Postgres or a version keeps for the cell at the row and column given, the
    own-th of the rows given, as the cell holds it: each distance the id of the row there, none
    where no row is."""

    def turn(point: dict):
        target = point["row"]
        if isinstance(target, int):
            return ids[own + target] if 0 <= own + target < len(ids) else None
        return OWN if target == row else target

    return formula_at(_rows_turned(formula, turn), row, col)


@dataclass
class Col:
    id: str
    width: float | None = None
    look: Look | None = None
    hidden: bool = False


@dataclass
class Row:
    id: str
    height: float | None = None
    cells: dict[str, dict] = field(default_factory=dict)
    values: dict[str, object] = field(default_factory=dict)
    position: int | None = None
    pk: int | None = None
    look: Look | None = None
    shown: dict[str, str] = field(default_factory=dict)
    hidden: bool = False


@dataclass
class Laid:
    """A table's grid: its columns and rows in order, each row's cells by column id, and the
    last of the rows that stay at the top of the view as the others scroll past, none where none
    do: rows put in above it stay with it, as a sheet's frozen pane grows.

    A copy shares its rows with the grid it was copied from until it asks for one to change
    (`own`), so a change to a few cells of a long table copies only those rows: a row is
    changed only through `own`, apart from its values and what it shows, which calculating
    writes."""

    table: str
    tab: object = None
    name: str = ""
    cols: list[Col] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    frozen: str | None = None
    order: list[str] | None = None
    _index: dict[str, int] | None = field(default=None, init=False, repr=False, compare=False)
    _indexed: list[Row] | None = field(default=None, init=False, repr=False, compare=False)
    _owned: set[int] | None = field(default=None, init=False, repr=False, compare=False)
    _cols: dict[str, Col] | None = field(default=None, init=False, repr=False, compare=False)
    _colled: list[Col] | None = field(default=None, init=False, repr=False, compare=False)

    def row_ids(self) -> list[str]:
        if self.order is not None:
            return self.order
        return [row.id for row in self.rows]

    def col_ids(self) -> list[str]:
        return [col.id for col in self.cols]

    def at(self) -> dict[str, int]:
        """Where each row stands, kept while the rows stay the ones it was made of: a list
        put in their place or grown or shrunk makes it again, a row moved within it takes
        `touch`."""
        if (
            self._index is None
            or self._indexed is not self.rows
            or len(self._index) != len(self.rows)
        ):
            self._index = {row.id: at for at, row in enumerate(self.rows)}
            self._indexed = self.rows
        return self._index

    def by_id(self) -> dict[str, Row]:
        return {row.id: row for row in self.rows}

    @property
    def size(self) -> int:
        return len(self.rows)

    def places(self, ids: Iterable[str]) -> dict[str, int]:
        at = self.at()
        return {id: at[id] for id in ids if id in at}

    def place(self, id: str) -> int | None:
        return self.at().get(id)

    def has(self, id: str) -> bool:
        return id in self.at()

    def ids_at(self, places: Iterable[int]) -> dict[int, str]:
        return {place: self.rows[place].id for place in places if 0 <= place < len(self.rows)}

    def ids(self, first: int, last: int) -> list[str]:
        return [row.id for row in self.rows[max(first, 0) : max(last + 1, 0)]]

    def put_rows(self, ids: list[str], before: str | None, sizes: list[float | None]) -> None:
        at = len(self.rows) if before is None else self.at()[before]
        self.rows[at:at] = [
            Row(id, sizes[offset] if offset < len(sizes) else None) for offset, id in enumerate(ids)
        ]

    def take_rows(self, ids: Iterable[str]) -> None:
        gone = set(ids)
        self.rows = [row for row in self.rows if row.id not in gone]

    def order_rows(self, first: int, ids: list[str]) -> None:
        rows = self.by_id()
        self.rows = [*self.rows[:first], *(rows[id] for id in ids), *self.rows[first + len(ids) :]]

    def take_cols(self, ids: Iterable[str]) -> None:
        gone = set(ids)
        self.cols = [col for col in self.cols if col.id not in gone]
        for row in list(self.rows):
            if gone & row.cells.keys():
                cells = self.own(row.id).cells
                for col in gone & cells.keys():
                    del cells[col]

    def looked(self) -> list[str]:
        """The rows with a look of their own."""
        return [row.id for row in self.rows if row.look is not None]

    def holding(self, cols: set[str]) -> list[str]:
        """The rows with a cell in any of the columns given."""
        return [row.id for row in self.rows if cols & row.cells.keys()]

    def merges(self) -> dict[str, str]:
        """The slot each merged cell reaches, by "row:col"."""
        return {
            f"{row.id}:{col}": cell[TO]
            for row in self.rows
            for col, cell in row.cells.items()
            if cell.get(TO)
        }

    def row(self, id: str) -> Row | None:
        at = self.at().get(id)
        return None if at is None else self.rows[at]

    def col(self, id: str) -> Col | None:
        if self._cols is None or self._colled is not self.cols or len(self._cols) != len(self.cols):
            self._cols = {col.id: col for col in self.cols}
            self._colled = self.cols
        return self._cols.get(id)

    def own(self, id: str) -> Row:
        """The row, to change: copied first where it is still shared with another grid, its
        cells' parts to be replaced, not changed in place."""
        at = self.at()[id]
        row = self.rows[at]
        if self._owned is None or builtins.id(row) in self._owned:
            return row
        cells = {col: dict(cell) for col, cell in row.cells.items()}
        mine = Row(
            row.id,
            row.height,
            cells,
            row.values,
            row.position,
            row.pk,
            row.look,
            row.shown,
            row.hidden,
        )
        self.rows[at] = mine
        self._owned.add(builtins.id(mine))
        return mine

    def touch(self) -> None:
        self._index = None

    def cell(self, row: str, col: str) -> dict:
        found = self.row(row)
        return found.cells.get(col, {}) if found else {}

    def inherited(self, row: str, col: str) -> Look | None:
        """The look a cell of the row and column takes where it has none of its own."""
        found = self.row(row)
        if found is not None and found.look is not None:
            return found.look
        line = self.col(col)
        return None if line is None else line.look

    def look_at(self, row: str, col: str) -> Look | None:
        """The look the cell's text shows where it has no node: its own, else its line's."""
        cell = self.cell(row, col)
        return cell[LOOK] if LOOK in cell else self.inherited(row, col)

    def entries(self, part: str) -> dict[str, object]:
        """One part of every cell that has it, by "row:col"."""
        return {
            f"{row.id}:{col}": cell[part]
            for row in self.rows
            for col, cell in row.cells.items()
            if part in cell
        }

    def told(self, texts: Mapping[str, str] | None = None) -> dict[str, dict]:
        return {
            f"{row.id}:{col}": each for row in self.rows for col, each in told(row, texts).items()
        }

    def widths(self) -> dict[str, float] | None:
        found = {col.id: col.width for col in self.cols if col.width is not None}
        return found or None

    def heights(self) -> dict[str, float] | None:
        found = {row.id: row.height for row in self.rows if row.height is not None}
        return found or None

    def hidden(self) -> dict[str, list[str]] | None:
        """The ids of the rows and the columns hidden, by axis, of those that have any."""
        found = {
            axis: ids
            for axis, lines in ((ROWS, self.rows), (COLS, self.cols))
            if (ids := [line.id for line in lines if line.hidden])
        }
        return found or None

    def copy(self) -> Laid:
        laid = Laid(
            self.table,
            self.tab,
            self.name,
            [Col(col.id, col.width, col.look, col.hidden) for col in self.cols],
            list(self.rows),
            self.frozen,
        )
        laid._owned = set()
        return laid


def kind_of(value) -> str:
    """The kind of a value calculated, as a browser tells a number from text."""
    match value:
        case bool():
            return "bool"
        case int() | float():
            return "number"
        case dict():
            return "error"
    return "text"


def told(row: Row, texts: Mapping[str, str] | None = None) -> dict[str, dict]:
    """What a browser holds of the row's cells: of each holding a formula calculated or a number
    format the text it shows, and of a typed one calculated as other than text its value, which
    tells a number from text as it was read; `texts` gives the text of the cells that have a
    node, by "row:col"."""
    found = {}
    for col in row.cells.keys() | row.values.keys():
        cell = row.cells.get(col) or {}
        value = row.values.get(col)
        kind = kind_of(value)
        if (
            (FORMULA in cell and col in row.shown)
            or (FORMAT in cell and col in row.values)
            or kind != "text"
        ):
            typed = (texts or {}).get(f"{row.id}:{col}", cell.get(TEXT, ""))
            found[col] = {"text": row.shown.get(col, typed), "kind": kind}
    return found


def cleaned(cell: dict | None) -> dict | None:
    """The cell's inputs that hold something, none where nothing does: a look with nothing in it
    holds the cell plain in a line that has one."""
    if not cell:
        return None
    kept = {
        part: value
        for part in INPUTS
        if (value := cell.get(part)) is not None and (part == LOOK or value not in ("", {}, []))
    }
    return kept or None


def shared_of(entries: Mapping[str, object]) -> dict[str, Formula | Look]:
    """What cells share, by key, from what Postgres or a version keeps."""
    return {
        key: _one(value, Formula if isinstance(value, list) else Look, key)
        for key, value in entries.items()
    }


def keyed(value: dict | None, found: dict[str, Formula | Look]) -> str | None:
    """A line's look as Postgres and versions keep it, by its key, which `found` gathers."""
    if value is None:
        return None
    shown = look(value)
    found[shown.key] = shown
    return shown.key


def encoded(
    cells: Mapping[str, dict], row: str, at: Mapping[str, int], found: dict[str, Formula | Look]
) -> dict:
    """A row's cells as Postgres and versions keep them, given where each row of the table
    stands, each formula (as `stored_formula` gives it) and look by its key, which `found`
    gathers."""
    kept = {}
    for col, cell in cells.items():
        formula, shown = cell.get(FORMULA), cell.get(LOOK)
        if isinstance(formula, list) or isinstance(shown, dict):
            cell = dict(cell)
            if isinstance(formula, list):
                formula = stored_formula(formula_at(formula, row, col), row, at)
                found[formula.key] = formula
                cell[FORMULA] = formula.key
            if isinstance(shown, dict):
                cell[LOOK] = keyed(shown, found)
        kept[col] = cell
    return kept


def decoded(
    cells: Mapping[str, dict],
    shared: Mapping[str, Formula | Look],
    row: str,
    own: int,
    ids: Sequence[str],
) -> dict:
    """A row's cells as Postgres or a version keeps them, each formula and look by its key,
    holding what is shared in place of the key, each formula as the cell holds it (`held_formula`):
    the row's, the own-th of the rows given."""
    found = {}
    for col, cell in cells.items():
        if isinstance(cell.get(FORMULA), str) or isinstance(cell.get(LOOK), str):
            cell = dict(cell)
            if isinstance(key := cell.get(FORMULA), str):
                cell[FORMULA] = held_formula(shared[key], row, col, own, ids)
            if isinstance(key := cell.get(LOOK), str):
                cell[LOOK] = shared[key]
        found[col] = cell
    return found


def kept_line(
    id: str,
    height: float | None,
    cells: Mapping[str, dict],
    values: Mapping[str, object],
    shown: Mapping[str, str],
    look: str | None,
    hidden: bool,
) -> list:
    """A row as a version keeps it, its cells as Postgres does: [id, height, cells] and, as
    `_entry` puts them, its look's key and whether it is hidden, and where a value was
    calculated, after both, what it was and what it showed."""
    figures = {part: found for part, found in (("values", values), ("shown", shown)) if found}
    if figures:
        return [id, height, cells, look or None, hidden, figures]
    return _entry(id, height, cells, look=look or None, hidden=hidden)


def line_parts(line: list) -> tuple[str, float | None, dict, str | None, bool, dict]:
    """A row as a version keeps it, in its parts: id, height, cells, look's key, whether it is
    hidden and what was calculated."""
    id, height, cells, *rest = line
    look, hidden = _ending(rest)
    return id, height, cells, look, hidden, rest[2] if len(rest) > 2 else {}


def kept_cols(laid: Laid, found: dict[str, Formula | Look]) -> list:
    """The columns as a version keeps them, each [id, width] and, as `_entry` puts them, its
    look's key, which `found` gathers, and whether it is hidden."""
    return [
        _entry(col.id, col.width, look=keyed(col.look, found), hidden=col.hidden)
        for col in laid.cols
    ]


def unkept_rows(lines: list[list], shared: Mapping[str, Formula | Look]) -> list[list]:
    """The rows a version keeps, in order, holding what they share in place of the keys."""
    ids = [line[0] for line in lines]
    found = []
    for own, (id, height, cells, *rest) in enumerate(lines):
        key, hidden = _ending(rest)
        cells = decoded(cells, shared, id, own, ids)
        found.append(_entry(id, height, cells, look=key and shared[key], hidden=hidden))
    return found


def unkept_col(line: list, shared: Mapping[str, Formula | Look]) -> list:
    """A column a version keeps, holding its look in place of the key."""
    id, width, *rest = line
    key, hidden = _ending(rest)
    return _entry(id, width, look=key and shared[key], hidden=hidden)


def kept_col(col: Mapping) -> list:
    """A column of Postgres as a version keeps it."""
    return _entry(
        col["id"], col.get("width"), look=col.get("look"), hidden=col.get("hidden", False)
    )


def stored_col(line: list) -> dict:
    """A column a version keeps as Postgres does."""
    id, width, *rest = line
    look, hidden = _ending(rest)
    return (
        {"id": id}
        | ({"width": width} if width is not None else {})
        | ({"look": look} if look is not None else {})
        | ({"hidden": True} if hidden else {})
    )


def _placing_rows(rows, shared: Mapping[str, Formula | Look], cols: Iterable[dict]):
    """Of the rows, those a merged cell or a style can bear on; every row where a column has a
    style, as each of its cells then does."""
    styled = [
        key
        for key, value in shared.items()
        if not isinstance(value, Formula) and "style" in (value.get("attrs") or {})
    ]
    if any(col.get("look") in styled for col in cols):
        return rows
    return rows.extra(
        where=[
            "(content_gridrow.look = ANY(%s) OR EXISTS (SELECT 1 FROM "
            "jsonb_each(content_gridrow.cells) e WHERE e.value ? 'to' "
            "OR e.value->>'look' = ANY(%s)))"
        ],
        params=[styled, styled],
    )


def _read(grids, placing: bool = False) -> dict[str, Laid]:
    found = {
        grid.pk: Laid(
            grid.table,
            _tab(grid.tab_id),
            grid.name,
            frozen=grid.frozen or None,
        )
        for grid in grids
    }
    documents = {grid.document_id for grid in grids}
    shared = shared_of(
        dict(Shared.objects.filter(document__in=documents).values_list("key", "value"))
    )
    for grid in grids:
        found[grid.pk].cols = [
            Col(
                col["id"],
                col.get("width"),
                shared[col["look"]] if "look" in col else None,
                col.get("hidden", False),
            )
            for col in grid.cols
        ]
    kept = GridRow.objects.filter(grid__in=list(found)).order_by("grid", "position")
    every: dict[int, list[str]] = {}
    if placing:
        for grid in grids:
            every[grid.pk] = list(
                GridRow.objects.filter(grid=grid).order_by("position").values_list("row", flat=True)
            )
        kept = _placing_rows(kept, shared, [col for grid in grids for col in grid.cols])
    for grid, id, height, cells, values, position, pk, look, shown, hidden in kept.values_list(
        "grid", "row", "height", "cells", "values", "position", "pk", "look", "shown", "hidden"
    ):
        found[grid].rows.append(
            Row(id, height, cells, values, position, pk, shared.get(look), shown, hidden)
        )
    for pk, laid in found.items():
        ids = every.get(pk) or laid.row_ids()
        at = {id: own for own, id in enumerate(ids)}
        for row in laid.rows:
            row.cells = decoded(row.cells, shared, row.id, at[row.id], ids)
        if placing:
            laid.order = ids
    return {laid.table: laid for laid in found.values()}


def within(grids) -> list[Grid]:
    """Those of the grids within the ceiling on cells."""
    return [
        grid
        for grid in grids.annotate(lines=Count("rows"))
        if grid.lines * len(grid.cols) <= MOST_CELLS
    ]


def oversized(document) -> list[str]:
    """The names of the document's tables over the ceiling on cells."""
    found = Grid.objects.filter(document=document).annotate(lines=Count("rows"))
    return [grid.name for grid in found if grid.lines * len(grid.cols) > MOST_CELLS]


def of_tab(tab) -> dict[str, Laid]:
    """The grids of the tables a tab's text holds or held, by table id."""
    return _read(Grid.objects.filter(tab=tab))


def small_of_tab(tab) -> dict[str, Laid]:
    """The grids of the tab's tables within the ceiling on cells, by table id."""
    return _read(within(Grid.objects.filter(tab=tab)))


def placing_of_tab(tab) -> dict[str, Laid]:
    """The grids of the tab's tables as far as they bear on how cells are placed and numbered:
    every row's id, and of the rows only those with a merged cell or a cell of a style."""
    return _read(Grid.objects.filter(tab=tab), placing=True)


def of_document(document, tables: Iterable[str] | None = None) -> dict[str, Laid]:
    """The grids of the document's tables, those given or all of them, by table id."""
    found = Grid.objects.filter(document=document)
    return _read(found if tables is None else found.filter(table__in=list(tables)))


def of_own(document) -> dict[str, Laid]:
    """The grids of the tables in the document's headers and footers."""
    return _read(Grid.objects.filter(document=document, tab=None))


# Patches


def _line_of(laid: Laid, axis: Axis, id: str) -> dict:
    """What a line holds, to put it back: its size, its look and its cells, by the other
    axis."""
    if axis == ROWS:
        line = laid.row(id)
        cells = deepcopy(line.cells)
    else:
        line = laid.col(id)
        cells = {row.id: deepcopy(row.cells[id]) for row in laid.rows if id in row.cells}
    size = line.height if axis == ROWS else line.width
    return (
        {"size": size, "cells": cells}
        | ({"look": line.look} if line.look is not None else {})
        | ({"hidden": True} if line.hidden else {})
    )


def _looked(value: dict | None) -> Look | None:
    return None if value is None else look(value)


def _ids(laid: Laid | None, axis: Axis) -> list[str]:
    if laid is None:
        return []
    return laid.row_ids() if axis == ROWS else laid.col_ids()


def _lines(before: Laid | None, after: Laid, axis: Axis) -> dict:
    was, now = _ids(before, axis), _ids(after, axis)
    had, has = set(was), set(now)
    found: dict = {}
    out = [
        [id, was[at - 1] if at else None, at, _line_of(before, axis, id)]
        for at, id in enumerate(was)
        if id not in has
    ]
    put = [
        [id, now[at - 1] if at else None, at, _line_of(after, axis, id)]
        for at, id in enumerate(now)
        if id not in had
    ]
    kept_before = [id for id in was if id in has]
    kept_after = [id for id in now if id in had]
    if kept_before != kept_after:
        pairs = list(zip(kept_before, kept_after, strict=True))
        first = next(at for at, (a, b) in enumerate(pairs) if a != b)
        last = len(pairs) - next(at for at, (a, b) in enumerate(reversed(pairs)) if a != b)
        found["order"] = [kept_before[first:last], kept_after[first:last]]
    if out:
        found["out"] = out
    if put:
        found["put"] = put
    return found


def diff(before: Laid | None, after: Laid | None) -> dict | None:
    """The patch that turns the grid before into the one after, none where they are alike."""
    if after is None:
        if before is None:
            return None
        return {"table": before.table, "gone": whole(before)}
    patch: dict = {"table": after.table}
    if before is None:
        patch["made"] = {"tab": _tab(after.tab), "name": after.name}
    elif before.name != after.name:
        patch["name"] = [before.name, after.name]
    for axis in (ROWS, COLS):
        if lines := _lines(before, after, axis):
            patch[axis] = lines
    if before is not None:
        kept_cols = set(before.col_ids()) & set(after.col_ids())
        widths = {col.id: col.width for col in before.cols}
        changed_widths = {
            col.id: [widths[col.id], col.width]
            for col in after.cols
            if col.id in kept_cols and widths[col.id] != col.width
        }
        if changed_widths:
            patch["widths"] = changed_widths
        was_cols = {col.id: col for col in before.cols}
        looks: dict[str, dict] = {ROWS: {}, COLS: {}}
        hidden: dict[str, dict] = {ROWS: {}, COLS: {}}
        for col in after.cols:
            if col.id not in kept_cols:
                continue
            if (was := was_cols[col.id]).look != col.look:
                looks[COLS][col.id] = [was.look, col.look]
            if was.hidden != col.hidden:
                hidden[COLS][col.id] = [was.hidden, col.hidden]
        rows = before.by_id()
        cells: dict[str, dict] = {}
        heights: dict[str, list] = {}
        for row in after.rows:
            old = rows.get(row.id)
            if old is None or old is row:
                continue
            if old.height != row.height:
                heights[row.id] = [old.height, row.height]
            if old.look != row.look:
                looks[ROWS][row.id] = [old.look, row.look]
            if old.hidden != row.hidden:
                hidden[ROWS][row.id] = [old.hidden, row.hidden]
            for col in kept_cols & (old.cells.keys() | row.cells.keys()):
                was, now = cleaned(old.cells.get(col)), cleaned(row.cells.get(col))
                if was != now:
                    cells.setdefault(row.id, {})[col] = [was, now]
        if heights:
            patch["heights"] = heights
        if looks := {axis: lines for axis, lines in looks.items() if lines}:
            patch["looks"] = looks
        if hidden := {axis: lines for axis, lines in hidden.items() if lines}:
            patch["hidden"] = hidden
        if cells:
            patch["cells"] = cells
    if (was := before.frozen if before else None) != after.frozen:
        patch["frozen"] = [was, after.frozen]
    return patch if len(patch) > 1 else None


def _tab(tab) -> str | None:
    return None if tab is None else str(tab)


def _entry(*parts, look, hidden: bool = False) -> list:
    """A line as a grid whole holds it, its look after its parts where it has one, and a hidden
    line's look, none or not, followed by true."""
    if hidden:
        return [*parts, look, True]
    return [*parts] if look is None else [*parts, look]


def _ending(rest: list) -> tuple:
    """A line's look, none where it has none, and whether it is hidden, as `_entry` ends it."""
    return (rest[0] if rest else None), len(rest) > 1 and rest[1] is True


def col_line(col: Col) -> list:
    return _entry(col.id, col.width, look=col.look, hidden=col.hidden)


def row_line(row: Row) -> list:
    return _entry(row.id, row.height, deepcopy(row.cells), look=row.look, hidden=row.hidden)


def whole(laid: Laid) -> dict:
    return {
        "tab": _tab(laid.tab),
        "name": laid.name,
        "cols": [col_line(col) for col in laid.cols],
        "rows": [row_line(row) for row in laid.rows],
        "frozen": laid.frozen,
    }


def from_whole(table: str, whole: dict) -> Laid:
    cols, rows = [], []
    for id, width, *rest in whole.get("cols", []):
        look, hidden = _ending(rest)
        cols.append(Col(id, width, _looked(look), hidden))
    for id, height, cells, *rest in whole.get("rows", []):
        look, hidden = _ending(rest)
        rows.append(Row(id, height, cells, look=_looked(look), hidden=hidden))
    return Laid(table, whole.get("tab"), whole.get("name", ""), cols, rows, whole.get("frozen"))


def _swapped(pair: list) -> list:
    return [pair[1], pair[0]]


def inverse(patch: dict) -> dict:
    """The patch that takes the one given back."""
    back: dict = {"table": patch["table"]}
    if "made" in patch:
        back["gone"] = patch["made"]
    if "gone" in patch:
        back["made"] = patch["gone"]
    for part in ("name", "frozen"):
        if part in patch:
            back[part] = _swapped(patch[part])
    for axis in (ROWS, COLS):
        if axis not in patch:
            continue
        lines = patch[axis]
        turned: dict = {}
        if "put" in lines:
            turned["out"] = lines["put"]
        if "out" in lines:
            turned["put"] = lines["out"]
        if "order" in lines:
            turned["order"] = _swapped(lines["order"])
        back[axis] = turned
    for part in ("widths", "heights"):
        if part in patch:
            back[part] = {id: _swapped(pair) for id, pair in patch[part].items()}
    for part in ("looks", "hidden"):
        if part in patch:
            back[part] = {
                axis: {id: _swapped(pair) for id, pair in lines.items()}
                for axis, lines in patch[part].items()
            }
    if "cells" in patch:
        back["cells"] = {
            row: {col: _swapped(pair) for col, pair in cols.items()}
            for row, cols in patch["cells"].items()
        }
    return back


@dataclass
class Applied:
    """A patch as it went: what it changed, its before as found, the rows to store and of
    those the rows whose formulas now stand at other distances from the rows they name."""

    laid: Laid | None
    patch: dict | None
    dirty: set[str] = field(default_factory=set)
    restated: set[str] = field(default_factory=set)
    spaced: bool = False
    made: bool = False
    gone: bool = False
    meta: bool = False


def _space(laid: Laid) -> None:
    for at, row in enumerate(laid.rows):
        if row.position != (at + 1) * STEP:
            laid.own(row.id).position = (at + 1) * STEP


def _positioned(laid: Laid, new: set[str]) -> bool:
    """Gives the rows put in positions between their neighbours'; False where there is no
    room left between two of them."""
    rows = laid.rows
    at = 0
    while at < len(rows):
        if rows[at].id not in new:
            at += 1
            continue
        end = at
        while end < len(rows) and rows[end].id in new:
            end += 1
        low = rows[at - 1].position if at else 0
        high = rows[end].position if end < len(rows) else None
        count = end - at
        if low is None or (high is not None and high - low <= count):
            return False
        for offset in range(count):
            step = (offset + 1) * (STEP if high is None else (high - low) // (count + 1))
            rows[at + offset].position = low + step
        at = end
    return True


def _chain(after: dict[str | None, list[str]], start: str | None) -> list[str]:
    """The lines put in right after the one given, each followed by those after it: the one
    put last first, as one put in after another would stand."""
    found, stack = [], list(after.pop(start, []))
    while stack:
        id = stack.pop()
        found.append(id)
        stack.extend(after.pop(id, []))
    return found


def _with_put(ids: list[str], brought: dict[str, list]) -> list[str]:
    """The order of the lines with those brought put in, each right after the line it names,
    one there was or one put in too, and where that is gone at its index."""
    present = set(ids)
    after: dict[str | None, list[str]] = {}
    for id, (_, named, _, _) in brought.items():
        if named is None or named in brought or named in present:
            after.setdefault(named, []).append(id)
    order = _chain(after, None)
    for id in ids:
        order.append(id)
        if after:
            order.extend(_chain(after, id))
    placed = set(order)
    for id, (_, _, index, _) in brought.items():
        if id not in placed:
            run = [id, *_chain(after, id)]
            at = min(index, len(order))
            order[at:at] = run
            placed.update(run)
    return order


def apply(laid: Laid | None, patch: dict, guard: bool = False) -> Applied:
    """Applies the patch to a copy of the grid and returns what it did. With a guard, as a
    patch is taken back, each part applies only where the grid still has what the patch
    takes for its before: a cell somebody wrote since stays as they left it.

    A line taken out is told by the line before it in the grid as it was, and one put in by
    the line before it as it will be, so a patch's lines go back as its inverse puts them."""
    table = patch["table"]
    done: dict = {"table": table}
    if "gone" in patch:
        if laid is None:
            return Applied(None, None)
        return Applied(None, {"table": table, "gone": whole(laid)}, gone=True)
    applied = Applied(None, None)
    was = None
    if "made" in patch:
        if laid is not None:
            if guard:
                return Applied(laid, None)
            raise ValueError(f"grid {table} exists")
        laid = _made(table, patch["made"], done)
        applied.made = True
    elif laid is None:
        if guard:
            return Applied(None, None)
        raise ValueError(f"no grid {table}")
    else:
        was = laid
        laid = laid.copy()
    _renamed(laid, patch, guard, done, applied)
    frozen = laid.frozen
    new: set[str] = set()
    for axis in (ROWS, COLS):
        if lines := patch.get(axis):
            new |= _relined(laid, axis, lines, guard, done, applied)
    _frozen(laid, patch, guard, frozen, done, applied)
    if was is not None and ROWS in done:
        applied.restated = _restated(was, laid)
        applied.dirty |= applied.restated
    if new and not applied.made and not _positioned(laid, new):
        applied.spaced = True
    if applied.made or applied.spaced:
        _space(laid)
        applied.dirty |= set(laid.row_ids())
    cols = {col.id: col for col in laid.cols}
    _widened(cols, patch, guard, done, applied)
    _heightened(laid, patch, guard, done, applied)
    _marked(laid, cols, patch, "looks", "look", guard, done, applied)
    _marked(laid, cols, patch, "hidden", "hidden", guard, done, applied)
    _written(laid, cols, patch, guard, done, applied)
    applied.laid = laid
    applied.patch = done if len(done) > 1 else None
    return applied


def _made(table: str, made: dict, done: dict) -> Laid:
    laid = Laid(table, made.get("tab"), made.get("name", ""))
    if "cols" in made and "rows" in made:
        laid = from_whole(table, made)
    done["made"] = {"tab": made.get("tab"), "name": made.get("name", "")}
    return laid


def _renamed(laid: Laid, patch: dict, guard: bool, done: dict, applied: Applied) -> None:
    if "name" not in patch:
        return
    before, after = patch["name"]
    if (not guard or laid.name == before) and laid.name != after:
        done["name"] = [laid.name, after]
        laid.name = after
        applied.meta = True


def _relined(
    laid: Laid, axis: Axis, lines: dict, guard: bool, done: dict, applied: Applied
) -> set[str]:
    """Takes the lines of an axis out, orders and puts them as the patch says; gives the ids of
    the rows put in."""
    found: dict = {}
    ids = _ids(laid, axis)
    if gone := {id for id, *_ in lines.get("out", [])} & set(ids):
        found["out"] = _taken_out(laid, axis, ids, gone, applied)
        ids = [id for id in ids if id not in gone]
    if "order" in lines and (order := _reordered(laid, axis, ids, lines["order"], guard, applied)):
        found["order"] = order
        ids = _ids(laid, axis)
    brought: dict[str, list] = {}
    for entry in lines.get("put", []):
        if entry[0] in brought or entry[0] in set(ids):
            if guard:
                continue
            raise ValueError(f"{axis} {entry[0]} exists")
        brought[entry[0]] = entry
    if brought:
        found["put"] = _brought(laid, axis, ids, brought, applied)
    if found:
        done[axis] = found
        if axis == COLS:
            applied.meta = True
    return set(brought) if axis == ROWS else set()


def _taken_out(laid: Laid, axis: Axis, ids: list[str], gone: set[str], applied: Applied) -> list:
    out = [
        [id, ids[at - 1] if at else None, at, _line_of(laid, axis, id)]
        for at, id in enumerate(ids)
        if id in gone
    ]
    if axis == ROWS:
        if laid.frozen in gone:
            above = ids[: ids.index(laid.frozen)]
            laid.frozen = next((id for id in reversed(above) if id not in gone), None)
        laid.rows = [row for row in laid.rows if row.id not in gone]
        return out
    laid.cols = [col for col in laid.cols if col.id not in gone]
    for row in list(laid.rows):
        if gone & row.cells.keys():
            mine = laid.own(row.id)
            mine.cells = {col: c for col, c in mine.cells.items() if col not in gone}
            applied.dirty.add(row.id)
    return out


def _reordered(
    laid: Laid, axis: Axis, ids: list[str], order: list, guard: bool, applied: Applied
) -> list | None:
    before, after = order
    moving = set(before)
    if set(after) != moving or not moving <= set(ids):
        return None
    slots = [at for at, id in enumerate(ids) if id in moving]
    current = [ids[at] for at in slots]
    if (guard and current != before) or current == after:
        return None
    if axis == ROWS:
        rows = {laid.rows[at].id: laid.rows[at] for at in slots}
        positions = [laid.rows[at].position for at in slots]
        reordered = list(laid.rows)
        for at, id in zip(slots, after, strict=True):
            reordered[at] = rows[id]
        laid.rows = reordered
        for id, position in zip(after, positions, strict=True):
            laid.own(id).position = position
            applied.dirty.add(id)
    else:
        cols = {col.id: col for col in laid.cols}
        for at, id in zip(slots, after, strict=True):
            laid.cols[at] = cols[id]
    return [current, list(after)]


def _brought(
    laid: Laid, axis: Axis, ids: list[str], brought: dict[str, list], applied: Applied
) -> list:
    order = _with_put(ids, brought)
    at_of = {id: at for at, id in enumerate(order)}
    put = [
        [id, order[at_of[id] - 1] if at_of[id] else None, at_of[id], line]
        for id, (_, _, _, line) in sorted(brought.items(), key=lambda kv: at_of[kv[0]])
    ]
    if axis == ROWS:
        rows = {row.id: row for row in laid.rows}
        for id, (_, _, _, line) in brought.items():
            rows[id] = Row(
                id,
                line.get("size"),
                deepcopy(line.get("cells", {})),
                look=_looked(line.get("look")),
                hidden=line.get("hidden", False),
            )
        laid.rows = [rows[id] for id in order]
        applied.dirty |= brought.keys()
        return put
    cols = {col.id: col for col in laid.cols}
    for id, (_, _, _, line) in brought.items():
        cols[id] = Col(id, line.get("size"), _looked(line.get("look")), line.get("hidden", False))
        for row_id, cell in line.get("cells", {}).items():
            if laid.row(row_id) is not None and (cell := cleaned(cell)):
                laid.own(row_id).cells[id] = deepcopy(cell)
                applied.dirty.add(row_id)
    laid.cols = [cols[id] for id in order]
    return put


def _frozen(
    laid: Laid, patch: dict, guard: bool, frozen: str | None, done: dict, applied: Applied
) -> None:
    if "frozen" in patch:
        before, after = patch["frozen"]
        if after is not None and laid.row(after) is None:
            if not guard:
                raise ValueError(f"no row {after}")
        elif not guard or frozen == before:
            laid.frozen = after
    if laid.frozen != frozen:
        done["frozen"] = [frozen, laid.frozen]
        applied.meta = True


def _restated(was: Laid, laid: Laid) -> set[str]:
    """The rows whose formulas stand at other distances from the rows they name once the
    lines moved."""
    before, after = was.at(), laid.at()
    return {
        row.id
        for row in laid.rows
        if row.id in before
        and any(
            isinstance(formula := cell.get(FORMULA), list)
            and _distance_changed(formula, row.id, before, after)
            for cell in row.cells.values()
        )
    }


def _widened(cols: dict[str, Col], patch: dict, guard: bool, done: dict, applied: Applied) -> None:
    widths = {}
    for id, (before, after) in patch.get("widths", {}).items():
        if (col := cols.get(id)) is None or (guard and col.width != before) or col.width == after:
            continue
        widths[id] = [col.width, after]
        col.width = after
        applied.meta = True
    if widths:
        done["widths"] = widths


def _heightened(laid: Laid, patch: dict, guard: bool, done: dict, applied: Applied) -> None:
    heights = {}
    for id, (before, after) in patch.get("heights", {}).items():
        row = laid.row(id)
        if row is None or (guard and row.height != before) or row.height == after:
            continue
        heights[id] = [row.height, after]
        laid.own(id).height = after
        applied.dirty.add(id)
    if heights:
        done["heights"] = heights


def _marked(
    laid: Laid,
    cols: dict[str, Col],
    patch: dict,
    part: str,
    name: str,
    guard: bool,
    done: dict,
    applied: Applied,
) -> None:
    """Sets the look of rows and columns or whether they are hidden, by the attribute's name."""
    changed: dict[str, dict] = {}
    for axis, lines in patch.get(part, {}).items():
        for id, (before, after) in lines.items():
            line = laid.row(id) if axis == ROWS else cols.get(id)
            if line is None:
                continue
            now = getattr(line, name)
            if (guard and now != before) or now == after:
                continue
            changed.setdefault(axis, {})[id] = [now, after]
            value = _looked(after) if name == "look" else after
            if axis == ROWS:
                setattr(laid.own(id), name, value)
                applied.dirty.add(id)
            else:
                setattr(line, name, value)
                applied.meta = True
    if changed:
        done[part] = changed


def _written(
    laid: Laid, cols: dict[str, Col], patch: dict, guard: bool, done: dict, applied: Applied
) -> None:
    changed: dict[str, dict] = {}
    for row_id, by_col in patch.get("cells", {}).items():
        row = laid.row(row_id)
        if row is None:
            continue
        for col, (before, after) in by_col.items():
            if col not in cols:
                continue
            now = cleaned(row.cells.get(col))
            after = cleaned(after)
            if (guard and now != cleaned(before)) or now == after:
                continue
            changed.setdefault(row_id, {})[col] = [now, after]
            row = laid.own(row_id)
            if after is None:
                row.cells.pop(col, None)
            else:
                row.cells[col] = deepcopy(after)
            applied.dirty.add(row_id)
    if changed:
        done["cells"] = changed


# Storing


def _cols(laid: Laid, found: dict[str, Formula | Look]) -> list[dict]:
    return [
        {"id": col.id}
        | ({"width": col.width} if col.width is not None else {})
        | ({"look": keyed(col.look, found)} if col.look is not None else {})
        | ({"hidden": True} if col.hidden else {})
        for col in laid.cols
    ]


@transaction.atomic
def store(document, applied: Applied) -> dict[str, set[str]]:
    """Writes what an applied patch changed: the grid's own fields and the rows it touched, of
    the document given or by its id. Gives by column the keys of the formulas it wrote."""
    patch = applied.patch
    if patch is None:
        return {}
    document = getattr(document, "pk", document)
    # `unshare` forgets what no row names under the same lock, so never a key named here.
    Node.objects.select_for_update().only("pk").get(pk=document)
    table = patch["table"]
    if applied.gone:
        Grid.objects.filter(document=document, table=table).delete()
        return {}
    laid = applied.laid
    shared: dict[str, Formula | Look] = {}
    if applied.made:
        grid = Grid.objects.create(
            document_id=document,
            tab_id=laid.tab,
            table=table,
            name=laid.name,
            cols=_cols(laid, shared),
            frozen=laid.frozen or "",
        )
    else:
        grid = Grid.objects.get(document=document, table=table)
        grid.edited_at = timezone.now()
        fields = ["edited_at"]
        if applied.meta or "name" in patch:
            grid.name, grid.frozen = laid.name, laid.frozen or ""
            grid.cols = _cols(laid, shared)
            fields += ["name", "cols", "frozen"]
        grid.save(update_fields=fields)
    if not applied.made and (out := patch.get(ROWS, {}).get("out")):
        GridRow.objects.filter(grid=grid, row__in=[id for id, *_ in out]).delete()
    dirty = [row for id in applied.dirty if (row := laid.row(id)) is not None]
    at = laid.at()
    cells = {row.id: encoded(row.cells, row.id, at, shared) for row in dirty}
    keys: dict[str, set[str]] = {}
    for each in cells.values():
        for col, cell in each.items():
            if isinstance(key := cell.get(FORMULA), str):
                keys.setdefault(col, set()).add(key)
    looks = {row.id: keyed(row.look, shared) or "" for row in dirty}
    Shared.objects.bulk_create(
        [Shared(document_id=document, key=key, value=value) for key, value in shared.items()],
        batch_size=2000,
        ignore_conflicts=True,
    )
    new = [row for row in dirty if row.pk is None]
    if new:
        created = GridRow.objects.bulk_create(
            [
                GridRow(
                    grid=grid,
                    row=row.id,
                    position=row.position,
                    height=row.height,
                    cells=cells[row.id],
                    look=looks[row.id],
                    hidden=row.hidden,
                )
                for row in new
            ],
            batch_size=2000,
        )
        for row, stored in zip(new, created, strict=True):
            row.pk = stored.pk
    fresh = {row.id for row in new}
    kept = [row for row in dirty if row.id not in fresh]
    if kept:
        GridRow.objects.bulk_update(
            [
                GridRow(
                    pk=row.pk,
                    position=row.position,
                    height=row.height,
                    cells=cells[row.id],
                    look=looks[row.id],
                    hidden=row.hidden,
                )
                for row in kept
            ],
            ["position", "height", "cells", "look", "hidden"],
            batch_size=2000,
        )
    return keys


def put(document, tab: str | None, laid: Laid) -> None:
    """Writes a table's grid whole, of the tab given or, with none, of the document's headers
    and footers: what an importer or a restored version brings where nobody has it open."""
    fresh = Laid(
        laid.table,
        tab,
        laid.name,
        [Col(col.id, col.width, col.look, col.hidden) for col in laid.cols],
        [Row(row.id, row.height, row.cells, look=row.look, hidden=row.hidden) for row in laid.rows],
        laid.frozen,
    )
    _space(fresh)
    store(document, Applied(fresh, made(fresh), {row.id for row in fresh.rows}, made=True))


def pieces_rekeyed(pieces: list, by: Mapping[str, str]) -> list:
    """A formula's pieces referring to the tables by the new ids given."""
    return [
        {**piece, "table": by[piece["table"]]}
        if isinstance(piece, dict) and piece.get("table") in by
        else piece
        for piece in pieces
    ]


def rekeyed(laid: Laid, by: Mapping[str, str]) -> Laid:
    """The grid under its table's new id, its formulas referring to tables by theirs."""
    rows = [
        Row(
            row.id,
            row.height,
            {
                col: {**cell, FORMULA: pieces_rekeyed(cell[FORMULA], by)}
                if FORMULA in cell
                else cell
                for col, cell in row.cells.items()
            },
            look=row.look,
            hidden=row.hidden,
        )
        for row in laid.rows
    ]
    cols = [Col(col.id, col.width, col.look, col.hidden) for col in laid.cols]
    return Laid(by.get(laid.table, laid.table), laid.tab, laid.name, cols, rows, laid.frozen)


def made(laid: Laid) -> dict:
    """The patch that makes the grid given."""
    return {"table": laid.table, "made": whole(laid)}
