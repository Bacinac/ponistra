"""What a document's tables calculate (D22 E3): the value of each of their cells by the engine,
read off Postgres and written back there with the text each shows (GridRow.values and shown).

A calculation starts from the cells that changed, or from whole tables, and follows what reads
them as far as it reaches: the formulas each column holds by their keys (`Columns`), each read
as the rows and columns it reaches from its cell. It numbers only the stretches of rows that
takes and those they read, in a table of its own for the transaction, `calc_rows`, so that a
reference kept by how far its row stands from its cell's own (grids.stored_formula) reads a
place. The cells to calculate fall into runs, cells of one column one below the other holding
the same formula; a run is computed in one query (engine.family) once the runs it reads are,
and what that query leaves by Python reading the same rows (`Rows`). Runs that read each
other, one reading its own column within its own rows and one reading whatever its cell gives
at the moment (INDIRECT, OFFSET) are Python's whole, each cell computed as it is first read. A
formula that gives another value each time (NOW, RAND) or reads what only computing tells is
calculated with every change.

A typed cell holds the value its text reads as in the document's language: text after an
apostrophe, TRUE or FALSE, an error's code, a number, a date or a time, else the text. A cell
a merged cell covers holds nothing."""

import json
from bisect import bisect_left, bisect_right
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from decimal import Decimal
from random import Random

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from apps.engine import formats, numformat
from apps.engine.book import SUBTOTALS, calls
from apps.engine.evaluate import formula
from apps.engine.family import Family, Sheet
from apps.engine.formats import Language
from apps.engine.grid import Area, Context
from apps.engine.parse import (
    Binary,
    Call,
    End,
    Group,
    Held,
    Name,
    Point,
    Ref,
    Unreadable,
    parse,
)
from apps.engine.sql import Unsupported, text_literal
from apps.engine.values import BLANK, ERROR_TYPES, NAME, REF, Blank, Error, Scalar, loaded, stored

from . import names, placing, schema
from .grids import FORMAT, FORMULA, OWN, TEXT
from .models import Grid, Shared

# Changed whenever the engine computes a value otherwise, so that every table is calculated
# again as it is next used (Grid.calculated).
CALCULATION = "2"
PAGE = 1024
# The rows one query reads or writes of a table at a time.
CHUNK = 8192
# How many values computed a calculation holds before writing them into the rows it reads.
HELD = 65536
# How many pages of rows a calculation keeps of each kind it reads, and formulas compiled.
PAGES = 64
# What a formula reads that only the moment of computing tells.
DYNAMIC = frozenset(("INDIRECT", "OFFSET"))
VOLATILE = DYNAMIC | {"NOW", "TODAY", "RAND", "RANDBETWEEN", "RANDARRAY", "CELL", "INFO"}
# What gives where a row stands, which rows put in, taken out or moved change.
POSITIONAL = frozenset(("ROW",))
UNSHOWN = "#######"
# Counting the rows above each of a few rows is quicker than numbering the table; for more,
# numbering it once is.
FEW = 16
# A table of which a calculation reads more than this share of rows is numbered whole.
MOST = 0.5
# Python computes a run of fewer cells quicker than a query does, and a graph needs so few
# runs one by one rather than through a node standing for them.
SHORT = 16

# By table, its columns' ids and the keys of the formulas each holds.
Columns = Mapping[str, Mapping[str, Collection[str]]]
# By table, its merged cells: the row and column of each and the cell it reaches, "row:col".
Merges = Mapping[str, Iterable[tuple[str, str, str]]]
# By table, the cells whose text, formula or format changed, (row, col), with all of those of
# a row put in and of the rows beside one taken out; None for a table to calculate whole, as
# one whose columns or merged cells changed, and for one that went.
Changed = Mapping[str, Collection[tuple[str, str]] | None]
# By table that changed, of each row told whose values or what its cells show changed, both as
# they now are.
Calculated = dict[str, dict[str, tuple[dict, dict]]]


def calculated(locale: str) -> str:
    return f"{CALCULATION}:{locale}"


def titles(named: Mapping[str, str]) -> dict[str, str]:
    """A sheet name for each table by its id, in the order given, as a workbook takes one: its
    own name where that is a valid one no table before it has, else a made-up one no table
    has."""
    found: dict[str, str] = {}
    taken: set[str] = set()
    for id, name in named.items():
        if name and schema.holds("tableName", name) and name.casefold() not in taken:
            found[id] = name
            taken.add(name.casefold())
    made = (f"Sheet{number}" for number in range(1, 2 * len(named) + 1))
    for id in named:
        if id not in found:
            found[id] = next(title for title in made if title.casefold() not in taken)
            taken.add(found[id].casefold())
    return {id: found[id] for id in named}


@dataclass(frozen=True)
class Table:
    """A table as a calculation reads it: its id, its grid's key, its sheet name, its columns
    in order and how many rows it has."""

    id: str
    grid: int
    title: str
    cols: tuple[str, ...]
    size: int

    def x(self, col: str) -> int | None:
        return self.cols.index(col) + 1 if col in self.cols else None


def typed(text: str, language: Language) -> Scalar:
    """The value of a cell its text is typed in."""
    if text.startswith("'"):
        return text[1:]
    if text.upper() in ("TRUE", "FALSE"):
        return text.upper() == "TRUE"
    if text.upper() in ERROR_TYPES:
        return Error(text.upper())
    number = formats.read(text, language)
    return text if number is None else number


# The kinds of format in whose cell a fraction typed alone reads as one.
NUMERIC = frozenset({"number", "currency", "percent", "scientific", "fraction"})


def implied(text: str, language: Language, held: str = "") -> str:
    """The number format Excel gives a cell holding the format `held` as the text is typed in
    it (formats.typed), none after an apostrophe."""
    found = _typed_in(text, language, held)
    return "" if found is None else found.format


def kept(text: str, language: Language, held: str) -> str:
    """What a cell holding the format `held` keeps of the text typed in it: text's format the
    text as written (an apostrophe before what would read as something else), a number's the
    number written where it reads the text otherwise than General does (1/2 in a cell of 0.00
    keeps 0.5), any other the text."""
    kind = numformat.category(held)
    if kind == "text":
        return text if text.startswith("'") else written(text, language)
    found = _typed_in(text, language, held)
    if found is None or kind not in NUMERIC or formats.typed(text, language) == found:
        return text
    return written(found.value, language)


def read_in(text: str, language: Language, held: str) -> Scalar:
    """The value of the text typed in a cell holding the format `held`."""
    found = _typed_in(text, language, held)
    return typed(text, language) if found is None else found.value


def _typed_in(text: str, language: Language, held: str) -> formats.Typed | None:
    if text.startswith("'"):
        return None
    return formats.typed(text, language, numeric=numformat.category(held) in NUMERIC)


def shown(value: Scalar, format: str | None, locale: str) -> str:
    """The text a cell holding the value shows in its number format."""
    match value:
        case Error():
            return value.value
        case bool():
            return "TRUE" if value else "FALSE"
        case Blank():
            return ""
    found = numformat.shown(value, numformat.celled(format or "General", locale), locale)
    return UNSHOWN if isinstance(found, Error) else found


def written(value: Scalar, language: Language) -> str:
    """The text that, typed in the language, holds the value: a number with the language's
    decimal mark and no exponent, a logical and an error as Excel writes them, and text that
    would read as something else after an apostrophe, as Excel keeps it."""
    match value:
        case bool():
            return "TRUE" if value else "FALSE"
        case Error():
            return value.value
        case Blank():
            return ""
        case int() | float():
            text = format(Decimal(repr(float(value))), "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text.replace(".", formats.marks(language.code)[0])
    return value if typed(value, language) == value and value[:1] != "=" else "'" + value


def language(locale: str) -> Language:
    return Language(locale, timezone.localtime().year, settings.CODE_PAGE)


@dataclass(frozen=True, slots=True)
class _End:
    """A row a reference reaches: `at` itself, or, where it `moves`, as far from its cell."""

    at: int
    moves: bool

    def of(self, y: int) -> int:
        return y + self.at if self.moves else self.at


@dataclass(frozen=True, slots=True)
class _Read:
    """An area a formula reads: its table, its columns and the rows its two ends reach."""

    table: Table
    left: int
    right: int
    ends: tuple[_End, _End]

    def rows(self, top: int, bottom: int) -> tuple[int, int]:
        """The rows the cells from `top` to `bottom` holding the formula read."""
        return min(end.of(top) for end in self.ends), max(end.of(bottom) for end in self.ends)

    def readers(self, top: int, bottom: int, size: int) -> tuple[int, int] | None:
        """The rows of a table of `size` rows whose cells holding the formula read any of the
        rows from `top` to `bottom`; None for none."""
        moving = [end for end in self.ends if end.moves]
        low, high = 1, size
        if not any(not end.moves and end.at >= top for end in self.ends):
            if not moving:
                return None
            low = max(low, min(top - end.at for end in moving))
        if not any(not end.moves and end.at <= bottom for end in self.ends):
            if not moving:
                return None
            high = min(high, max(bottom - end.at for end in moving))
        return (low, high) if low <= high else None


@dataclass(frozen=True, slots=True)
class _Formula:
    """A formula as the cells of one column hold it: its tree as `relative` gives one, the
    areas it reads, whether what it reads only computing tells and whether it is calculated
    with every change."""

    tree: object
    reads: tuple[_Read, ...]
    dynamic: bool
    volatile: bool
    positional: bool
    tables: frozenset[str]
    names: frozenset[str]
    rows: frozenset[tuple[str, str]]
    refs: tuple[tuple[Ref, str], ...] = ()


@dataclass
class _Named:
    """The tables a formula names by id, the rows it names by id, (table, row), and the
    defined names it reads, those in them too."""

    tables: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    rows: set[tuple[str, str]] = field(default_factory=set)


@dataclass(eq=False, slots=True)
class _Run:
    """Cells of one column one below the other holding the same formula, from `top` to
    `bottom`, those computed marked in `done`."""

    table: Table
    x: int
    key: str
    top: int
    bottom: int
    formula: _Formula | None = None
    done: bytearray = field(default_factory=bytearray)

    def needs(self) -> list[tuple[Table, int, int, int, int]]:
        """What it reads: each area by its table, its columns and its rows."""
        return [
            (read.table, read.left, read.right, *read.rows(self.top, self.bottom))
            for read in self.formula.reads
        ]

    def chained(self) -> bool:
        """Whether it reads cells of its own column within its own rows."""
        return any(
            table is self.table
            and left <= self.x <= right
            and top <= self.bottom
            and self.top <= bottom
            for table, left, right, top, bottom in self.needs()
        )

    def upward(self) -> bool:
        """Whether its cells read their own column below them, so are computed bottom up."""
        return any(
            read.table is self.table
            and read.left <= self.x <= read.right
            and any(end.moves and end.at > 0 for end in read.ends)
            for read in self.formula.reads
        )


def _mapped(node, change):
    """The tree with each node `change` gives another for, the rest as they were."""
    found = change(node)
    if found is not None:
        return found
    updated = {}
    for name in _fields(node):
        child = getattr(node, name)
        if isinstance(child, tuple):
            now = tuple(
                tuple(_mapped(item, change) for item in part)
                if isinstance(part, tuple)
                else _mapped(part, change)
                for part in child
            )
        else:
            now = _mapped(child, change)
        if now is not child:
            updated[name] = now
    return replace(node, **updated) if updated else node


def _nodes(node):
    """The node and every node under it."""
    yield node
    for name in _fields(node):
        child = getattr(node, name)
        for item in child if isinstance(child, tuple) else (child,):
            for part in item if isinstance(item, tuple) else (item,):
                yield from _nodes(part)


def _fields(node) -> tuple[str, ...]:
    """The names of the fields of a node of the tree, none for what is no dataclass."""
    kind = type(node)
    found = _FIELDS.get(kind)
    if found is None:
        found = _FIELDS[kind] = (
            tuple(each.name for each in fields(kind)) if is_dataclass(kind) else ()
        )
    return found


_FIELDS: dict[type, tuple[str, ...]] = {}


def _stretches(ys: Iterable[int]) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for y in sorted(set(ys)):
        if found and found[-1][1] == y - 1:
            found[-1] = (found[-1][0], y)
        else:
            found.append((y, y))
    return found


def _merged(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for top, bottom in sorted(spans):
        if found and top <= found[-1][1] + 1:
            found[-1] = (found[-1][0], max(found[-1][1], bottom))
        else:
            found.append((top, bottom))
    return found


def _missing(held: list[tuple[int, int]], top: int, bottom: int) -> list[tuple[int, int]]:
    """The stretches from `top` to `bottom` the merged stretches held leave out."""
    found, at = [], top
    for low, high in held:
        if high < at:
            continue
        if low > bottom:
            break
        if low > at:
            found.append((at, low - 1))
        at = max(at, high + 1)
    if at <= bottom:
        found.append((at, bottom))
    return found


def _ys(cursor, table: Table, rows: Collection[str]) -> dict[str, int]:
    """Where the rows of the table stand, counted from 1."""
    if not rows:
        return {}
    if len(rows) <= FEW:
        cursor.execute(
            "SELECT g.row, (SELECT count(*) FROM content_gridrow h WHERE h.grid_id = g.grid_id "
            "AND h.position <= g.position) FROM content_gridrow g "
            "WHERE g.grid_id = %s AND g.row = ANY(%s)",
            [table.grid, list(rows)],
        )
    else:
        cursor.execute(
            "SELECT n.row, n.y FROM (SELECT g.row, row_number() OVER (ORDER BY g.position) AS y "
            "FROM content_gridrow g WHERE g.grid_id = %s) AS n WHERE n.row = ANY(%s)",
            [table.grid, list(rows)],
        )
    return dict(cursor.fetchall())


def _holding(cursor, table: Table, col: str, keys: Collection[str]) -> list[int]:
    """Where the cells of the column holding any of the formulas stand."""
    cursor.execute(
        "SELECT n.y FROM (SELECT row_number() OVER (ORDER BY g.position) AS y, g.cells "
        "FROM content_gridrow g WHERE g.grid_id = %s) AS n "
        "WHERE n.cells -> %s ->> 'formula' = ANY(%s)",
        [table.grid, col, list(keys)],
    )
    return [y for (y,) in cursor.fetchall()]


class Known:
    """The formulas of a document's tables read as places, which a book keeps from one
    calculation to the next, each by its key, table and column while what it was read against
    stands: the tables, their titles, the defined names it reads and where the rows it names by
    id stand. A calculation holding the document's lock alone uses it."""

    def __init__(self) -> None:
        self.read: dict[tuple[str, str, int], _Formula] = {}
        self.tables: dict[str, Table] = {}
        self.defined: Mapping[str, dict] = {}
        self.ys: dict[tuple[str, str], int] = {}

    def standing(
        self, tables: Mapping[str, Table], defined: Mapping[str, dict]
    ) -> dict[str, Table]:
        """The tables, each that has not changed the very one the formulas known read; lets go
        of the formulas read against a table or a defined name that changed, and reads again
        the areas of those reading a table that only grew or shrank."""
        before = self.tables
        if {id: table.title for id, table in before.items()} != {
            id: table.title for id, table in tables.items()
        }:
            self.read.clear()
            before = {}
        now: dict[str, Table] = {}
        changed: set[str] = set()
        sized: set[str] = set()
        for id, table in tables.items():
            was = before.get(id)
            if was == table:
                now[id] = was
            else:
                now[id] = table
                if was is not None and replace(was, size=table.size) == table:
                    sized.add(id)
                else:
                    changed.add(id)
        renamed = {
            each["name"].casefold()
            for key in self.defined.keys() | defined.keys()
            if self.defined.get(key) != defined.get(key)
            for each in (self.defined.get(key), defined.get(key))
            if each is not None
        }
        if changed or renamed or sized:
            for at, each in list(self.read.items()):
                if (
                    at[1] in changed
                    or each.tables & changed
                    or each.names & renamed
                    or any(read.table.id in changed for read in each.reads)
                ):
                    del self.read[at]
                elif any(read.table.id in sized for read in each.reads):
                    self.read[at] = replace(each, reads=_reads(each.refs, now, at[2]))
        self.tables, self.defined = now, defined
        return now

    def located(self, ys: Mapping[tuple[str, str], int]) -> None:
        """Lets go of the formulas naming by id a row that now stands elsewhere."""
        before = self.ys
        for at, each in list(self.read.items()):
            if any(before.get(row) != ys.get(row) for row in each.rows):
                del self.read[at]
        self.ys = dict(ys)

    def rows(self) -> set[str]:
        return {row for each in self.read.values() for _, row in each.rows}


class _Places:
    """The formulas of a document's tables as the cells of each column hold them, their
    references read as places, those `known` taken as they are."""

    def __init__(self, tables: Mapping[str, Table], defined, known: Known):
        self.tables = tables
        self.titled = {table.title.casefold(): table for table in tables.values()}
        self.shared: dict[str, list] = {}
        self.defined = defined
        self.known = known
        self.ys: dict[tuple[str, str], int] = {}

    def take(self, cursor, document, columns: Columns) -> None:
        """Takes in the formulas the columns hold: lets go of those known whose rows moved and
        of those no column holds any more, and reads the pieces of those not known and where
        the rows stand that they and the defined names name by id."""
        wanted = self.known.rows() | self._rows([])
        self.ys = self._located(cursor, wanted)
        self.known.located(self.ys)
        held = {
            (key, table.id, x)
            for id, cols in columns.items()
            if (table := self.tables.get(id)) is not None
            for col, keys in cols.items()
            if (x := table.x(col)) is not None
            for key in keys
        }
        known = self.known.read
        for at in known.keys() - held:
            del known[at]
        missing = {key for key, *at in held if (key, *at) not in known}
        self.shared = dict(
            Shared.objects.filter(document=document, key__in=missing).values_list("key", "value")
        )
        self.ys |= self._located(cursor, self._rows(self.shared.values()) - wanted)
        self.known.ys = dict(self.ys)

    def _rows(self, shared: Iterable[list]) -> set[str]:
        wanted: set[str] = set()
        for pieces in [*shared, *(each["pieces"] for each in self.defined.values())]:
            for piece in pieces:
                if not isinstance(piece, dict):
                    continue
                for end in ("from", "to"):
                    point = piece.get(end)
                    row = point.get("row") if isinstance(point, dict) else None
                    if isinstance(row, str) and row != OWN:
                        wanted.add(row)
        return wanted

    def _located(self, cursor, wanted: set[str]) -> dict[tuple[str, str], int]:
        found = {}
        if wanted:
            for table in self.tables.values():
                for row, y in _ys(cursor, table, wanted).items():
                    found[table.id, row] = y
        return found

    def formula(self, key: str, table: Table, x: int) -> _Formula:
        """The formula of the key as the cells of the column x of the table hold it."""
        at = (key, table.id, x)
        found = self.known.read.get(at)
        if found is None:
            named = _Named()
            try:
                tree = self._placed(parse(self.shared[key]), table, x, frozenset(), named)
            except KeyError:
                # Unknown, so that a calculation that reads its pieces reads it.
                return self._read(NAME, table, x, named)
            except Unreadable:
                tree = NAME
            found = self.known.read[at] = self._read(tree, table, x, named)
        return found

    def _read(self, tree, own: Table, x: int, named: _Named) -> _Formula:
        refs, dynamic, volatile, positional = [], False, False, False
        for node in _nodes(tree):
            if isinstance(node, Call) and node.name.upper() in POSITIONAL:
                positional = True
            elif isinstance(node, Call) and node.name.upper() in VOLATILE:
                volatile = True
                dynamic = dynamic or node.name.upper() in DYNAMIC
            elif isinstance(node, Binary) and node.op in (":", " ", ","):
                if not (isinstance(node.left, Ref) and isinstance(node.right, Ref)):
                    dynamic = True
            elif isinstance(node, Ref) and node.book is None:
                table = self.titled.get(node.sheet.casefold()) if node.sheet else own
                if table is not None:
                    refs.append((node, table.id))
        refs = tuple(refs)
        # What a range built at the moment reaches its reads do not tell.
        return _Formula(
            tree,
            _reads(refs, self.tables, x),
            dynamic,
            volatile or dynamic,
            positional,
            _frozen(named.tables),
            _frozen(named.names),
            _frozen(named.rows),
            refs,
        )

    def _placed(self, tree, table: Table, x: int, naming: frozenset[str], named: _Named):
        def change(node):
            if isinstance(node, Held):
                return self._ref(node, table, x, named)
            if isinstance(node, Name):
                return self._named(node.name, table, x, naming, named)
            return None

        return _mapped(tree, change)

    def _named(self, name: str, table: Table, x: int, naming: frozenset[str], named: _Named):
        named.names.add(name.casefold())
        entry = names.in_force(self.defined, name, table.id)
        if entry is None or name.casefold() in naming:
            return NAME
        try:
            found = parse(entry["pieces"])
        except Unreadable:
            return NAME
        return Group(self._placed(found, table, x, naming | {name.casefold()}, named))

    def _ref(self, node: Held, own: Table, x: int, named: _Named):
        if node.table:
            named.tables.add(node.table)
        table = self.tables.get(node.table) if node.table else own
        if table is None:
            return REF
        start = self._end(node.start, table, x, named)
        end = node.end and self._end(node.end, table, x, named)
        if start is None or (node.end and end is None):
            return REF
        return Ref(None if table is own else table.title, start, end)

    def _end(self, point: Point, table: Table, x: int, named: _Named) -> End | None:
        row, abs_row = point.row, point.abs_row
        if row == OWN:
            row, abs_row = 0, False
        elif isinstance(row, str):
            named.rows.add((table.id, row))
            row, abs_row = self.ys.get((table.id, row)), True
            if row is None:
                return None
        col, abs_col = point.col, point.abs_col
        if col == OWN:
            col = x if abs_col else 0
        elif col is not None:
            place = table.x(col)
            if place is None:
                return None
            col = place if abs_col else place - x
        return End(row, col, abs_row, abs_col)


def _frozen(found: set) -> frozenset:
    # Every formula holds three of these, most of them empty, and frozenset(set()) is a new one.
    return frozenset(found) if found else _NONE


_NONE: frozenset = frozenset()


def _reads(refs: Iterable[tuple[Ref, str]], tables: Mapping[str, Table], x: int):
    return tuple(_area(node, tables[id], x) for node, id in refs)


def _area(node: Ref, table: Table, x: int) -> _Read:
    ends = (node.start, node.end or node.start)
    rows = tuple(
        _End(whole, False) if end.row is None else _End(end.row, not end.abs_row)
        for end, whole in zip(ends, (1, table.size), strict=True)
    )
    cols = [
        whole if end.col is None else end.col if end.abs_col else x + end.col
        for end, whole in zip(ends, (1, len(table.cols)), strict=True)
    ]
    return _Read(table, min(cols), max(cols), rows)


class _Dirty:
    """The stretches of rows to calculate of each column, by its table and place."""

    def __init__(self) -> None:
        self.spans: dict[tuple[str, int], list[tuple[int, int]]] = {}

    def add(self, table: Table, x: int, top: int, bottom: int) -> list[tuple[int, int]]:
        """Takes the stretch, within the table, and gives what of it was not taken yet."""
        top, bottom = max(top, 1), min(bottom, table.size)
        if top > bottom:
            return []
        held = self.spans.setdefault((table.id, x), [])
        new = _missing(held, top, bottom)
        if new:
            self.spans[table.id, x] = _merged([*held, *new])
        return new

    def of(self, table: Table) -> dict[int, list[tuple[int, int]]]:
        return {x: spans for (id, x), spans in self.spans.items() if id == table.id}


class Rows:
    """The cells of the tables a calculation reads, as the engine's book (grid.Book): a cell
    being calculated as its value is first read, any other as Postgres keeps it. What it
    computes it holds until there is HELD of it, then writes it into the rows it reads."""

    def __init__(self, cursor, places: _Places, language, now):
        self.cursor = cursor
        self.tables = places.titled
        self.places = places
        self.language = language
        self.now = now
        self.random = Random()
        self.numbered: dict[str, list[tuple[int, int]]] = {}
        self.computed: dict[tuple[str, int, int], Scalar] = {}
        self._runs: dict[tuple[str, int], tuple[list[int], list[_Run]]] = {}
        self._computing: set[tuple[str, int, int]] = set()
        self._pages: dict[tuple[int, int], dict[int, dict]] = {}
        self._cells: dict[tuple[int, int], dict[int, dict]] = {}
        self._hidden: dict[tuple[int, int], set[int]] = {}
        self._compiled: dict[object, object] = {}

    def ran(self, runs: Iterable[_Run]) -> None:
        """Takes the runs to calculate, none of their cells computed yet."""
        by_column: dict[tuple[str, int], list[_Run]] = {}
        for run in runs:
            run.done = bytearray(run.bottom - run.top + 1)
            by_column.setdefault((run.table.id, run.x), []).append(run)
        for at, each in by_column.items():
            each.sort(key=lambda run: run.top)
            self._runs[at] = ([run.top for run in each], each)

    def run(self, table: Table, row: int, col: int) -> _Run | None:
        """The run whose cell the place is, if any."""
        found = self._runs.get((table.id, col))
        if found is None:
            return None
        tops, runs = found
        at = bisect_right(tops, row) - 1
        return runs[at] if at >= 0 and row <= runs[at].bottom else None

    def put(self, run: _Run, row: int, value: Scalar) -> None:
        self.computed[run.table.id, row, run.x] = value
        run.done[row - run.top] = 1

    def spill(self) -> None:
        if len(self.computed) >= HELD:
            self.flush()

    def flush(self) -> None:
        """Writes what it computed into the rows it reads and the pages it read of them, for
        the queries after, and lets go of it."""
        tables = self.places.tables
        values = {(tables[id], y, x): value for (id, y, x), value in self.computed.items()}
        _kept(self.cursor, values)
        for (table, y, x), value in values.items():
            page = self._pages.get((table.grid, (y - 1) // PAGE))
            if page is None:
                continue
            held = page.get(y)
            if not isinstance(held, dict):
                held = page[y] = {}
            if isinstance(value, Blank):
                held.pop(table.cols[x - 1], None)
            else:
                held[table.cols[x - 1]] = stored(value)
        self.computed.clear()

    def number(self, table: Table, spans: Iterable[tuple[int, int]]) -> int:
        """Numbers the stretches of the table's rows not numbered yet, and gives how many."""
        held = self.numbered.setdefault(table.id, [])
        wanted = [
            each
            for top, bottom in _merged(spans)
            for each in _missing(held, max(top, 1), min(bottom, table.size))
        ]
        for top, bottom in wanted:
            self.cursor.execute(
                "INSERT INTO calc_rows SELECT grid_id, %s + row_number() OVER (ORDER BY position), "
                'id, "values" FROM (SELECT grid_id, position, id, "values" FROM content_gridrow '
                "WHERE grid_id = %s ORDER BY position OFFSET %s LIMIT %s) AS found",
                [top - 1, table.grid, top - 1, bottom - top + 1],
            )
        if wanted:
            self.numbered[table.id] = _merged([*held, *wanted])
        return sum(bottom - top + 1 for top, bottom in wanted)

    def _page(self, cache: dict, table: Table, row: int, column: str) -> dict:
        at = (table.grid, (row - 1) // PAGE)
        if at not in cache:
            _room(cache)
            top = at[1] * PAGE + 1
            self.number(table, [(top, top + PAGE - 1)])
            self.cursor.execute(
                f"SELECT c.y, {column} FROM calc_rows c JOIN content_gridrow g ON g.id = c.id "
                "WHERE c.grid = %s AND c.y BETWEEN %s AND %s",
                [table.grid, top, top + PAGE - 1],
            )
            cache[at] = {y: _jsonb(found) for y, found in self.cursor.fetchall()}
        return cache[at].get(row) or {}

    def value(self, sheet: str, row: int, col: int) -> Scalar:
        table = self.tables.get(sheet.casefold())
        if table is None:
            return REF
        at = (table.id, row, col)
        if at in self.computed:
            return self.computed[at]
        run = self.run(table, row, col)
        if run is not None and not run.done[row - run.top]:
            return self.calculate(run, row)
        if not (1 <= row <= table.size and 1 <= col <= len(table.cols)):
            return BLANK
        return loaded(self._page(self._pages, table, row, "c.vals").get(table.cols[col - 1]))

    def calculate(self, run: _Run, row: int) -> Scalar:
        at = (run.table.id, row, run.x)
        if at in self._computing:
            return 0.0
        tree = run.formula.tree
        compiled = self._compiled.get(tree)
        if compiled is None:
            _room(self._compiled)
            compiled = self._compiled[tree] = formula(tree)
        self._computing.add(at)
        try:
            context = Context(
                self, run.table.title, row, run.x, self.language, self.now, self.random
            )
            result = compiled(context)
        finally:
            self._computing.discard(at)
        self.put(run, row, result)
        return result

    def extent(self, sheet: str) -> tuple[int, int] | None:
        table = self.tables.get(sheet.casefold())
        return None if table is None else (table.size, len(table.cols))

    def hidden(self, sheet: str, row: int) -> bool:
        table = self.tables.get(sheet.casefold())
        if table is None or not 1 <= row <= table.size:
            return False
        at = (table.grid, (row - 1) // PAGE)
        if at not in self._hidden:
            _room(self._hidden)
            top = at[1] * PAGE + 1
            self.number(table, [(top, top + PAGE - 1)])
            self.cursor.execute(
                "SELECT c.y FROM calc_rows c JOIN content_gridrow g ON g.id = c.id "
                "WHERE c.grid = %s AND c.y BETWEEN %s AND %s AND g.hidden",
                [table.grid, top, top + PAGE - 1],
            )
            self._hidden[at] = {y for (y,) in self.cursor.fetchall()}
        return row in self._hidden[at]

    def subtotal(self, sheet: str, row: int, col: int) -> bool:
        table = self.tables.get(sheet.casefold())
        if table is None or not (1 <= row <= table.size and 1 <= col <= len(table.cols)):
            return False
        run = self.run(table, row, col)
        key = None if run is None else run.key
        if key is None:
            cell = self._page(self._cells, table, row, "g.cells").get(table.cols[col - 1])
            key = cell.get(FORMULA) if isinstance(cell, dict) else None
        if not isinstance(key, str):
            return False
        return not SUBTOTALS.isdisjoint(calls(self.places.formula(key, table, col).tree))

    def held(self, node: Held, here: Context) -> Area | Error:
        return REF


def _room(cache: dict) -> None:
    """Lets go of what a cache took first once it holds PAGES."""
    if len(cache) >= PAGES:
        del cache[next(iter(cache))]


def tables_of(document, standing: Collection[str]) -> dict[str, Table]:
    """The tables of the document standing in its text, in the order of their grids."""
    found = list(
        Grid.objects.filter(document=document, table__in=standing)
        .order_by("pk")
        .annotate(size=Count("rows"))
        .values_list("pk", "table", "name", "cols", "size")
    )
    named = titles({table: name for _, table, name, _, _ in found})
    return {
        table: Table(table, pk, named[table], tuple(col["id"] for col in cols), size)
        for pk, table, _, cols, size in found
    }


def columns_of(tables: Iterable[Table]) -> dict[str, dict[str, set[str]]]:
    """The keys of the formulas each column of the tables holds."""
    by_grid = {table.grid: table.id for table in tables}
    found: dict[str, dict[str, set[str]]] = {table: {} for table in by_grid.values()}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT g.grid_id, e.key, e.value ->> 'formula' FROM content_gridrow g, "
            "jsonb_each(g.cells) AS e WHERE g.grid_id = ANY(%s) "
            "AND e.value ->> 'formula' IS NOT NULL",
            [list(by_grid)],
        )
        for grid, col, key in cursor.fetchall():
            found[by_grid[grid]].setdefault(col, set()).add(key)
    return found


def merges_of(tables: Iterable[Table]) -> dict[str, list[tuple[str, str, str]]]:
    """The merged cells of the tables."""
    by_grid = {table.grid: table.id for table in tables}
    found: dict[str, list[tuple[str, str, str]]] = {table: [] for table in by_grid.values()}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT g.grid_id, g.row, e.key, e.value ->> 'to' FROM content_gridrow g, "
            "jsonb_each(g.cells) AS e WHERE g.grid_id = ANY(%s) AND e.value ->> 'to' IS NOT NULL",
            [list(by_grid)],
        )
        for grid, row, col, to in cursor.fetchall():
            found[by_grid[grid]].append((row, col, to))
    return found


def _covered(cursor, table: Table, merges: Iterable[tuple[str, str, str]]) -> set[tuple[int, int]]:
    """The places merged cells cover, the first of two that meet keeping its own."""
    merges = list(merges)
    if not merges:
        return set()
    ys = _ys(
        cursor, table, {row for row, _, _ in merges} | {to.partition(":")[0] for *_, to in merges}
    )
    placed = []
    for row, col, to in merges:
        y, x = ys.get(row), table.x(col)
        if y is not None and x is not None:
            end_row, _, end_col = to.partition(":")
            placed.append((y, x, ys.get(end_row, y), table.x(end_col) or x))
    taken: set[tuple[int, int]] = set()
    covered: set[tuple[int, int]] = set()
    for y, x, bottom, right in sorted(placed):
        slots = {(each, other) for each in range(y, bottom + 1) for other in range(x, right + 1)}
        if bottom < y or right < x or slots & taken:
            continue
        taken |= slots
        covered |= slots - {(y, x)}
    return covered


class _Found:
    """What a calculation finds to calculate: the runs of the cells holding a formula, each
    column's found one row after the other, and the cells typed in or emptied, the value of
    each written into the rows the calculation reads, with what it shows into calc_out, as
    soon as there is a CHUNK of them."""

    def __init__(self, cursor, locale: str):
        self.cursor = cursor
        self.locale = locale
        self.language = language(locale)
        self.runs: list[_Run] = []
        self.whole: set[int] = set()
        self._open: dict[tuple[str, int], _Run] = {}
        self._typed: list[tuple[Table, int, int, int, str | None, str | None]] = []

    def formula(self, table: Table, y: int, x: int, key: str) -> None:
        last = self._open.get((table.id, x))
        if last is not None and last.key == key and last.bottom == y - 1:
            last.bottom = y
            return
        run = _Run(table, x, key, y, y)
        self.runs.append(run)
        self._open[table.id, x] = run

    def typed(self, table: Table, y: int, x: int, id: int, text: str | None, format) -> None:
        """A cell typed in, by its text; with none, one that holds nothing now."""
        self._typed.append((table, y, x, id, text, format))
        if len(self._typed) >= CHUNK:
            self.flush()

    def flush(self) -> None:
        values: dict[tuple[Table, int, int], Scalar] = {}
        out = []
        for table, y, x, id, text, format in self._typed:
            col = table.cols[x - 1]
            if text is None:
                values[table, y, x] = BLANK
                out.append({"id": id, "col": col, "v": None, "s": None})
                continue
            value = values[table, y, x] = typed(text, self.language)
            shows = shown(value, format, self.locale)
            # What a number format writes stands in the cell's place, a text of its own too.
            plain = shows == text and format is None
            out.append({"id": id, "col": col, "v": stored(value), "s": None if plain else shows})
        _kept(self.cursor, values)
        _out(self.cursor, out)
        self._typed.clear()


def _scan(
    cursor,
    found: _Found,
    table: Table,
    spans: Mapping[int, list[tuple[int, int]]],
    taken: set[tuple[int, int]] | None,
    texts: Mapping[str, str],
    covered: set[tuple[int, int]],
    formulas_only: bool = False,
) -> None:
    """Finds the cells of the table to calculate: those holding a formula in the stretches of
    each column, and those that changed, by place (`taken`, every one where None, its rows
    then written whole unless only its formulas are read)."""

    def take(y: int, x: int, id: int, row: str, cell, changed: bool) -> None:
        col = table.cols[x - 1]
        cell = cell if isinstance(cell, dict) else {}
        key = cell.get(FORMULA)
        text = texts.get(f"{row}:{col}", cell.get(TEXT))
        if (y, x) in covered or not (isinstance(key, str) or (isinstance(text, str) and text)):
            if changed and taken is not None:
                found.typed(table, y, x, id, None, None)
        elif isinstance(key, str):
            found.formula(table, y, x, key)
        elif changed and not formulas_only:
            found.typed(table, y, x, id, text, cell.get(FORMAT))

    if taken is None:
        if not formulas_only:
            found.whole.add(table.grid)
        for top in range(1, table.size + 1, CHUNK):
            cursor.execute(
                "SELECT c.y, g.id, g.row, g.cells FROM calc_rows c JOIN content_gridrow g "
                "ON g.id = c.id WHERE c.grid = %s AND c.y BETWEEN %s AND %s ORDER BY c.y",
                [table.grid, top, top + CHUNK - 1],
            )
            for y, id, row, cells in cursor.fetchall():
                cells = _jsonb(cells)
                for x, col in enumerate(table.cols, 1):
                    take(y, x, id, row, cells.get(col), True)
        return
    # Here only the cells holding a formula, which every one that changed is among; the rest
    # of those that changed below, by their rows.
    for x, each in spans.items():
        col = table.cols[x - 1]
        for top, bottom in each:
            for low in range(top, bottom + 1, CHUNK):
                cursor.execute(
                    "SELECT c.y, g.cells -> %s FROM calc_rows c "
                    "JOIN content_gridrow g ON g.id = c.id WHERE c.grid = %s "
                    "AND c.y BETWEEN %s AND %s AND g.cells -> %s ->> 'formula' IS NOT NULL "
                    "ORDER BY c.y",
                    [col, table.grid, low, min(low + CHUNK - 1, bottom), col],
                )
                for y, cell in cursor.fetchall():
                    key = _jsonb(cell).get(FORMULA)
                    if isinstance(key, str) and (y, x) not in covered:
                        found.formula(table, y, x, key)
    by_y: dict[int, list[int]] = {}
    for y, x in taken:
        by_y.setdefault(y, []).append(x)
    ys = sorted(by_y)
    for at in range(0, len(ys), CHUNK):
        cursor.execute(
            "SELECT c.y, g.id, g.row, g.cells FROM calc_rows c JOIN content_gridrow g "
            "ON g.id = c.id WHERE c.grid = %s AND c.y = ANY(%s)",
            [table.grid, ys[at : at + CHUNK]],
        )
        for y, id, row, cells in cursor.fetchall():
            cells = _jsonb(cells)
            for x in by_y[y]:
                cell = cells.get(table.cols[x - 1])
                if isinstance(cell, dict) and isinstance(cell.get(FORMULA), str):
                    if (y, x) not in covered:
                        continue
                take(y, x, id, row, cell, True)


def _ordered(runs: list[_Run]) -> list[list[_Run]]:
    """The runs in groups each to be computed after the groups before, a group of several
    being runs that read each other. The runs an area reaches in a column are needed through
    nodes each standing for a stretch of them (_Spans), a run reading what its cell gives at
    the moment through one standing for every run."""
    by_column: dict[tuple[str, int], list[int]] = {}
    for index, run in enumerate(runs):
        by_column.setdefault((run.table.id, run.x), []).append(index)
    needs: list[set[int]] = [set() for _ in runs]
    columns = {
        at: _Spans(needs, sorted(each, key=lambda index: runs[index].top), runs)
        for at, each in by_column.items()
    }
    every = None
    for index, run in enumerate(runs):
        found = needs[index]
        if run.formula.dynamic:
            if every is None:
                every = len(needs)
                needs.append(set(range(len(runs))))
            found.add(every)
        for table, left, right, top, bottom in run.needs():
            for x in range(max(left, 1), min(right, len(table.cols)) + 1):
                column = columns.get((table.id, x))
                if column is not None:
                    found.update(column.reaching(top, bottom))
    return [
        group
        for group in (
            [runs[index] for index in each if index < len(runs)] for each in _components(needs)
        )
        if group
    ]


class _Spans:
    """The runs of one column, in order, and nodes of the graph each standing for a stretch of
    them, made as an area first reaches it: one needing two halves, down to the runs."""

    def __init__(self, needs: list[set[int]], indexes: list[int], runs: list[_Run]):
        self.needs = needs
        self.indexes = indexes
        self.tops = [runs[index].top for index in indexes]
        self.bottoms = [runs[index].bottom for index in indexes]
        self.made: dict[tuple[int, int], int] = {}

    def reaching(self, top: int, bottom: int) -> list[int]:
        """The nodes standing for the runs the rows from `top` to `bottom` reach."""
        low = bisect_left(self.bottoms, top)
        high = bisect_right(self.tops, bottom)
        if high - low <= SHORT:
            return self.indexes[low:high]
        return self._cover(low, high, 0, len(self.indexes))

    def _cover(self, low: int, high: int, start: int, end: int) -> list[int]:
        if high <= start or end <= low:
            return []
        if low <= start and end <= high:
            return [self._node(start, end)]
        middle = (start + end) // 2
        return self._cover(low, high, start, middle) + self._cover(low, high, middle, end)

    def _node(self, start: int, end: int) -> int:
        if end - start == 1:
            return self.indexes[start]
        if (start, end) not in self.made:
            middle = (start + end) // 2
            self.needs.append({self._node(start, middle), self._node(middle, end)})
            self.made[start, end] = len(self.needs) - 1
        return self.made[start, end]


def _components(needs: list[set[int]]) -> list[list[int]]:
    """Tarjan's strongly connected components of the graph, each after those it needs."""
    index: dict[int, int] = {}
    low: dict[int, int] = {}
    stack: list[int] = []
    on: set[int] = set()
    found: list[list[int]] = []
    for start in range(len(needs)):
        if start in index:
            continue
        index[start] = low[start] = len(index)
        stack.append(start)
        on.add(start)
        work = [(start, iter(sorted(needs[start])))]
        while work:
            node, rest = work[-1]
            step = next(rest, None)
            if step is None:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        each = stack.pop()
                        on.discard(each)
                        group.append(each)
                        if each == node:
                            break
                    found.append(group)
            elif step not in index:
                index[step] = low[step] = len(index)
                stack.append(step)
                on.add(step)
                work.append((step, iter(sorted(needs[step]))))
            elif step in on:
                low[node] = min(low[node], index[step])
    return found


def _sheet(table: Table) -> Sheet:
    return Sheet(
        f"(SELECT y, vals FROM calc_rows WHERE grid = {table.grid})",
        lambda col: text_literal(table.cols[col - 1]) if 1 <= col <= len(table.cols) else "NULL",
        lambda alias, key: f"{alias}.vals -> {key}",
        (table.size, len(table.cols)),
    )


def _kept(cursor, values: Mapping[tuple[Table, int, int], Scalar]) -> None:
    """Writes the values into the rows the calculation reads, for the queries after."""
    by_row: dict[tuple[int, int], tuple[dict, list]] = {}
    for (table, y, x), value in values.items():
        held, gone = by_row.setdefault((table.grid, y), ({}, []))
        if isinstance(value, Blank):
            gone.append(table.cols[x - 1])
        else:
            held[table.cols[x - 1]] = stored(value)
    if not by_row:
        return
    cursor.execute(
        "UPDATE calc_rows c SET vals = (c.vals - u.gone) || u.v FROM jsonb_to_recordset(%s::jsonb) "
        "AS u(grid int, y int, v jsonb, gone text[]) WHERE c.grid = u.grid AND c.y = u.y",
        [
            _json(
                [
                    {"grid": grid, "y": y, "v": held, "gone": gone}
                    for (grid, y), (held, gone) in by_row.items()
                ]
            )
        ],
    )


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _jsonb(given):
    # Django's cursor reads jsonb as its text, leaving JSONField to decode it.
    return json.loads(given) if isinstance(given, str) else given


def calculate(
    document,
    standing: Collection[str],
    texts: Mapping[str, Mapping[str, str]],
    changed: Changed | None = None,
    columns: Columns | None = None,
    merges: Merges | None = None,
    moved: Collection[str] = (),
    named: Collection[str] = (),
    out: Collection[tuple[str, str]] = (),
    constants_written: Collection[str] = (),
    told: Mapping[str, Collection[str]] | None = None,
    known: Known | None = None,
) -> Calculated:
    """Calculates what changed of the tables of the document standing in its text, every one
    whole where `changed` gives none and one calculated otherwise or in another locale, and
    what reads it: `texts` gives by table the text of the cells that have a node of their own,
    by "row:col", `moved` the tables whose rows moved, `named` the defined names that changed
    and `out` the rows taken out, (table, row). `columns` and `merges` give what of them the
    caller holds, the rest read. `constants_written` names tables whose cells that hold no
    formula an import has written with their values, so that only the formulas are read of
    them. Writes the value of each cell and what it shows; where `told` gives by table the rows
    a reader holds, gives each table that changed with those of them that changed. `known`
    keeps the formulas read for the next calculation of the document."""
    locale = document.locale
    now = timezone.localtime()
    with transaction.atomic(), connection.cursor() as cursor:
        # One calculation of a document at a time, each reading what the one before wrote;
        # an advisory lock, so that the edits it calculates are written meanwhile.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"calculation:{document.pk}"]
        )
        known = Known() if known is None else known
        defined = names.of_document(document)
        tables = known.standing(tables_of(document, standing), defined)
        stale = Grid.objects.filter(pk__in=[table.grid for table in tables.values()]).exclude(
            calculated=calculated(locale)
        )
        changed = dict.fromkeys(tables) if changed is None else changed
        went = {id for id in changed if id not in tables}
        changed = {
            **{id: each for id, each in changed.items() if id in tables},
            **dict.fromkeys(stale.values_list("table", flat=True)),
        }
        if not changed and not went and not moved and not named and not out:
            return {}
        columns = _completed(columns, tables, columns_of)
        merges = _completed(merges, tables, merges_of)
        places = _Places(tables, defined, known)
        places.take(cursor, document, columns)
        touched = _Touched(went, set(moved), {name.casefold() for name in named}, set(out))
        dirty, taken = _spread(cursor, tables, changed, columns, places, touched)
        cursor.execute(
            "CREATE TEMP TABLE IF NOT EXISTS calc_rows "
            "(grid int, y int, id bigint, vals jsonb, PRIMARY KEY (grid, y)) ON COMMIT DROP"
        )
        cursor.execute(
            "CREATE TEMP TABLE IF NOT EXISTS calc_out (id bigint, col text, v jsonb, s text) "
            "ON COMMIT DROP"
        )
        cursor.execute("TRUNCATE calc_rows, calc_out")
        rows = Rows(cursor, places, language(locale), now.replace(tzinfo=None))
        _numbered(cursor, rows, tables, dirty, columns, places, taken)
        found = _Found(cursor, locale)
        for table in tables.values():
            spans = dirty.of(table)
            if not spans and not taken.get(table.id):
                continue
            _scan(
                cursor,
                found,
                table,
                spans,
                taken.get(table.id, set()),
                texts.get(table.id, {}),
                _covered(cursor, table, merges.get(table.id, ())),
                table.id in constants_written,
            )
        found.flush()
        _computed(cursor, rows, places, found.runs, language(locale))
        _shown(cursor, found.runs, locale)
        whole = {id for id, each in changed.items() if each is None} - set(constants_written)
        return _written(cursor, tables, whole, found.whole, locale, told)


def current(
    document,
    standing: Collection[str],
    texts: Mapping[str, Mapping[str, str]],
    known: Known | None = None,
) -> None:
    """Calculates what a reading of the document finds out of date: the tables never
    calculated or in another locale, whole, and the formulas giving another value each time."""
    calculate(document, standing, texts, dict.fromkeys(standing, ()), known=known)


def refresh(document) -> None:
    """Calculates what is out of date for a reader or a writer outside the document's book."""
    nodes = placing.nodes_of(placing.of_document(document))
    current(document, nodes.keys(), nodes)


def _completed(held, tables: Mapping[str, Table], read):
    """What the caller holds of each table, read for those it holds nothing of."""
    if held is None:
        return read(tables.values())
    missing = [table for id, table in tables.items() if id not in held]
    return {**held, **read(missing)} if missing else held


@dataclass(frozen=True)
class _Touched:
    """What changed beyond cells: the tables that went, those whose rows moved, the defined
    names that changed and the rows taken out."""

    went: set[str]
    moved: set[str]
    named: set[str]
    out: set[tuple[str, str]]

    def reaches(self, formula: _Formula, table: str) -> bool:
        return bool(
            formula.tables & self.went
            or formula.names & self.named
            or formula.rows & self.out
            or (formula.positional and (table in self.moved or formula.tables & self.moved))
        )


def _spread(
    cursor,
    tables: Mapping[str, Table],
    changed: Changed,
    columns: Columns,
    places: _Places,
    touched: _Touched,
) -> tuple[_Dirty, dict[str, set[tuple[int, int]] | None]]:
    """The stretches of rows of each column to calculate: what changed, the formulas
    calculated with every change or that what changed beyond cells reaches, and what reads
    any of them, as far as it reaches; and by table the places of the cells that changed,
    None where every one did."""
    dirty = _Dirty()
    work: list[tuple[Table, int, int, int]] = []

    def mark(table: Table, x: int, spans: Iterable[tuple[int, int]]) -> None:
        for top, bottom in spans:
            work.extend((table, x, *each) for each in dirty.add(table, x, top, bottom))

    taken: dict[str, set[tuple[int, int]] | None] = {}
    for id, cells in changed.items():
        table = tables[id]
        if cells is None:
            taken[id] = None
            for x in range(1, len(table.cols) + 1):
                mark(table, x, [(1, table.size)])
            continue
        ys = _ys(cursor, table, {row for row, _ in cells})
        taken[id] = {
            (ys[row], table.x(col)) for row, col in cells if row in ys and table.x(col) is not None
        }
        by_x: dict[int, list[int]] = {}
        for y, x in taken[id]:
            by_x.setdefault(x, []).append(y)
        for x, ys_of in by_x.items():
            mark(table, x, _stretches(ys_of))
    readers: dict[tuple[str, int], list[tuple[Table, int, _Read]]] = {}
    for id, cols in columns.items():
        table = tables.get(id)
        if table is None:
            continue
        for col, keys in cols.items():
            x = table.x(col)
            if x is None:
                continue
            each = {key: places.formula(key, table, x) for key in keys}
            if taken.get(id, ()) is not None:
                if any(touched.reaches(found, id) for found in each.values()):
                    mark(table, x, [(1, table.size)])
                elif volatile := [key for key, found in each.items() if found.volatile]:
                    mark(table, x, _stretches(_holding(cursor, table, col, volatile)))
            for read in {read for found in each.values() for read in found.reads}:
                for other in range(max(read.left, 1), min(read.right, len(read.table.cols)) + 1):
                    readers.setdefault((read.table.id, other), []).append((table, x, read))
    while work:
        table, x, top, bottom = work.pop()
        for reader, at, read in readers.get((table.id, x), ()):
            found = read.readers(top, bottom, reader.size)
            if found is not None:
                mark(reader, at, [found])
    return dirty, taken


def _numbered(cursor, rows: Rows, tables, dirty: _Dirty, columns: Columns, places, taken) -> None:
    """Numbers the rows the calculation reads: those to calculate and those their formulas
    read, a table whole where that is most of it."""
    wanted: dict[str, list[tuple[int, int]]] = {}
    for (id, x), spans in dirty.spans.items():
        table = tables[id]
        wanted.setdefault(id, []).extend(spans)
        for key in columns.get(id, {}).get(table.cols[x - 1], ()):
            for read in places.formula(key, table, x).reads:
                wanted.setdefault(read.table.id, []).extend(read.rows(*span) for span in spans)
    for id, each in taken.items():
        wanted.setdefault(id, []).extend((y, y) for y, _ in each or ())
    count = 0
    for id, spans in wanted.items():
        table = tables[id]
        spans = _merged(
            (max(top, 1), min(bottom, table.size)) for top, bottom in spans if top <= bottom
        )
        if sum(bottom - top + 1 for top, bottom in spans) > MOST * table.size:
            spans = [(1, table.size)]
        count += rows.number(table, spans)
    if count > PAGE:
        cursor.execute("ANALYZE calc_rows")


def _computed(cursor, rows: Rows, places: _Places, runs: list[_Run], language) -> None:
    """Computes the cells of the runs in the order they read each other, writing what is
    computed into the rows the calculation reads before a query reads them."""
    for run in runs:
        run.formula = places.formula(run.key, run.table, run.x)
    rows.ran(runs)
    for group in _ordered(runs):
        for run in group:
            alone = len(group) == 1 and not run.formula.dynamic and not run.chained()
            if alone and run.bottom - run.top >= SHORT and not isinstance(run.formula.tree, Error):
                rows.flush()
                _queried(rows, run, places, language)
            ys = range(run.top, run.bottom + 1)
            for y in reversed(ys) if run.upward() else ys:
                if not run.done[y - run.top]:
                    rows.calculate(run, y)
                    rows.spill()
    rows.flush()


def _queried(rows: Rows, run: _Run, places: _Places, language) -> None:
    """Puts the values of the run's cells one query computes, leaving the rest to Python."""

    def sheets(name: str) -> Sheet | None:
        table = places.titled.get(name.casefold())
        return None if table is None else _sheet(table)

    family = Family(sheets, run.table.title, run.x, run.top, run.bottom)
    try:
        query = family.query(run.formula.tree, language)
    except Unsupported:
        return
    # A cursor of the server's, so that the rows come a CHUNK at a time; what the values put
    # meanwhile write into calc_rows it does not see, nor needs, as the run reads none of them.
    with connection.chunked_cursor() as stream:
        stream.execute(query)
        while chunk := stream.fetchmany(CHUNK):
            for y, value in chunk:
                if value is not None:
                    rows.put(run, y, loaded(_jsonb(value)))
            rows.spill()


def _shown(cursor, runs: list[_Run], locale: str) -> None:
    """Writes into calc_out the value of each cell of the runs and the text it shows, a CHUNK
    of each table's rows at a time."""
    by_chunk: dict[tuple[Table, int], list[tuple[int, int, int]]] = {}
    for run in runs:
        for top in range(run.top - (run.top - 1) % CHUNK, run.bottom + 1, CHUNK):
            low, high = max(top, run.top), min(top + CHUNK - 1, run.bottom)
            by_chunk.setdefault((run.table, top), []).append((run.x, low, high))
    for (table, top), each in by_chunk.items():
        cursor.execute(
            "SELECT c.y, c.id, c.vals, g.cells FROM calc_rows c JOIN content_gridrow g "
            "ON g.id = c.id WHERE c.grid = %s AND c.y BETWEEN %s AND %s",
            [table.grid, top, top + CHUNK - 1],
        )
        found = {y: (id, _jsonb(vals), _jsonb(cells)) for y, id, vals, cells in cursor.fetchall()}
        out = []
        for x, low, high in each:
            col = table.cols[x - 1]
            for y in range(low, high + 1):
                id, vals, cells = found[y]
                value = loaded(vals.get(col))
                cell = cells.get(col)
                format = cell.get(FORMAT) if isinstance(cell, dict) else None
                out.append(
                    {"id": id, "col": col, "v": stored(value), "s": shown(value, format, locale)}
                )
        _out(cursor, out)


def _out(cursor, out: list[dict]) -> None:
    if out:
        cursor.execute(
            "INSERT INTO calc_out SELECT * FROM jsonb_to_recordset(%s::jsonb) "
            "AS u(id bigint, col text, v jsonb, s text)",
            [_json(out)],
        )


def _written(
    cursor,
    tables,
    whole: set[str],
    rewritten: set[int],
    locale: str,
    told: Mapping[str, Collection[str]] | None,
) -> Calculated:
    """Writes into the rows what calc_out holds: the value of each cell, the text it shows
    where that is not its typed text or a number format writes it, none for one that holds
    nothing now, a row of a grid `rewritten` keeping no other; and, where `told`, gives each
    table that changed with those of the rows told that changed."""
    written = (
        "u AS (SELECT id, "
        "coalesce(jsonb_object_agg(col, v) FILTER (WHERE v IS NOT NULL), '{}') AS v, "
        "coalesce(array_agg(col) FILTER (WHERE v IS NULL), '{}') AS gone, "
        "coalesce(jsonb_object_agg(col, s) FILTER (WHERE s IS NOT NULL), '{}') AS s, "
        "coalesce(array_agg(col) FILTER (WHERE s IS NULL), '{}') AS plain "
        "FROM calc_out GROUP BY id), "
        "w AS (SELECT id FROM calc_rows WHERE grid = ANY(%s)), "
        "n AS (SELECT h.id, "
        'CASE WHEN w.id IS NULL THEN (h."values" - u.gone) || u.v '
        "ELSE coalesce(u.v, '{}') END AS v, "
        "CASE WHEN w.id IS NULL THEN (h.shown - u.plain) || u.s "
        "ELSE coalesce(u.s, '{}') END AS s "
        "FROM (SELECT id FROM u UNION SELECT id FROM w) AS i "
        "JOIN content_gridrow h ON h.id = i.id "
        "LEFT JOIN u ON u.id = i.id LEFT JOIN w ON w.id = i.id)"
    )
    update = (
        'UPDATE content_gridrow g SET "values" = n.v, shown = n.s FROM n '
        'WHERE g.id = n.id AND (g."values" <> n.v OR g.shown <> n.s)'
    )
    found: Calculated = {}
    if told is None:
        cursor.execute(f"WITH {written} {update}", [list(rewritten)])
    else:
        held = [(tables[id].grid, row) for id, rows in told.items() if id in tables for row in rows]
        # What changed stays with Postgres, which spills it to disk; only the rows a reader
        # holds come back, and a row naming each grid that changed.
        cursor.execute(
            f'WITH {written}, up AS ({update} RETURNING g.grid_id, g.row, g."values", g.shown) '
            'SELECT up.grid_id, up.row, up."values", up.shown FROM up '
            "JOIN unnest(%s::bigint[], %s::text[]) AS h(grid, row) "
            "ON h.grid = up.grid_id AND h.row = up.row "
            "UNION ALL SELECT DISTINCT grid_id, NULL, NULL::jsonb, NULL::jsonb FROM up",
            [list(rewritten), [grid for grid, _ in held], [row for _, row in held]],
        )
        by_grid = {table.grid: table.id for table in tables.values()}
        for grid, row, now, shows in cursor.fetchall():
            rows = found.setdefault(by_grid[grid], {})
            if row is not None:
                rows[row] = (_jsonb(now), _jsonb(shows))
    if whole:
        Grid.objects.filter(pk__in=[tables[id].grid for id in whole]).update(
            calculated=calculated(locale)
        )
    return found
