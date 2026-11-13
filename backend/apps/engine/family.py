"""A family of cells computed in one query (D22): the cells of a run of rows of one column that
hold the same formula relative to their own (parse.relative gives them one tree), each a row of
one SELECT over the rows of their table, r. A reference relative to its cell reads the row r is
at, moved as far as it is written; one written absolutely reads the same cells for every row,
which Postgres computes once for the whole query. Which cells form a family, and in what order
families are computed, is the caller's: a family reading cells of its own column that another
of its cells computes is a chain, which Python computes."""

from collections.abc import Callable
from dataclasses import dataclass

from .formats import Language
from .parse import LAST_COL, LAST_ROW, End, Ref
from .query import compiled
from .sql import VALUE, Range, Scope, Typed, Unsupported

OWN = "r"


@dataclass(frozen=True)
class Sheet:
    """A table as a query reads it: `rows` a relation of its rows, each with its place y from
    1; `key` the SQL of a column's key by its number, `value` that of the value of the cell of
    a row alias in the column of a key, as sql.VALUE gives it, NULL for an empty one; `extent`
    its last row and column holding anything (grid.bounded)."""

    rows: str
    key: Callable[[int], str]
    value: Callable[[str, str], str]
    extent: tuple[int, int]


@dataclass(frozen=True)
class _Line:
    """A row or column of a reference: `at` itself, or, where it `moves`, its distance from
    the row r is at."""

    at: int
    moves: bool = False

    def sql(self) -> str:
        return f"({OWN}.y + {self.at})" if self.moves else str(self.at)


def _line(end: End, row: bool, whole: int, col: int) -> _Line:
    at, fixed = (end.row, end.abs_row) if row else (end.col, end.abs_col)
    if at is None:
        return _Line(whole)
    if fixed:
        return _Line(at)
    return _Line(at, moves=True) if row else _Line(col + at)


class Family:
    """The places of the formula of a family in column `col` of the table `own` names, from
    row `top` to `bottom`, each table read as `sheets` gives it, None for one there is not."""

    def __init__(
        self, sheets: Callable[[str], Sheet | None], own: str, col: int, top: int, bottom: int
    ):
        self.sheets = sheets
        self.own = own
        self.col = col
        self.top = top
        self.bottom = bottom

    def query(self, tree, language: Language) -> str:
        """The SELECT of each row y of the family and the jsonb value of its cell, NULL where
        Python is to compute it; Unsupported where Python computes them all."""
        return self.each(compiled(tree, self, language), f"{OWN}.y, ")

    def each(self, given: str, before: str = "") -> str:
        return (
            f"SELECT {before}{given} AS v FROM {self.sheets(self.own).rows} AS {OWN} "
            f"WHERE {OWN}.y BETWEEN {self.top} AND {self.bottom}"
        )

    def _lines(self, node) -> tuple[str, Sheet, tuple[_Line, _Line], tuple[_Line, _Line]] | None:
        if not isinstance(node, Ref):
            raise Unsupported("a reference a table keeps")
        if node.book is not None:
            return None
        name = node.sheet or self.own
        sheet = self.sheets(name)
        if sheet is None:
            return None
        start, end = node.start, node.end or node.start
        rows = _line(start, True, 1, self.col), _line(end, True, LAST_ROW, self.col)
        cols = _line(start, False, 1, self.col), _line(end, False, LAST_COL, self.col)
        if rows[0].moves != rows[1].moves:
            raise Unsupported("an area of another height in each row")
        if rows[0].at > rows[1].at:
            rows = rows[::-1]
        if cols[0].at > cols[1].at:
            cols = cols[::-1]
        if cols[0].at < 1 or cols[1].at > LAST_COL:
            return None
        return name, sheet, rows, cols

    def cell(self, node, scope: Scope) -> Typed | None:
        found = self._lines(node)
        if found is None:
            return None
        name, sheet, (top, bottom), (left, right) = found
        if top == bottom and left == right:
            return self._read(name, sheet, top, left.at, cell=True)
        if left == right:
            if top.moves:
                return (
                    self._read(name, sheet, _Line(0, True), left.at)
                    if top.at <= 0 <= bottom.at
                    else None
                )
            own = self._read(name, sheet, _Line(0, True), left.at)
            return Typed(
                f"CASE WHEN {OWN}.y BETWEEN {top.at} AND {bottom.at} THEN {own.sql} END",
                VALUE,
                cell=None,
            )
        if top == bottom and left.at <= self.col <= right.at:
            return self._read(name, sheet, top, self.col)
        return None

    def _read(
        self, name: str, sheet: Sheet, row: _Line, col: int, cell: bool | None = None
    ) -> Typed:
        key = sheet.key(col)
        if name.casefold() == self.own.casefold() and row == _Line(0, True):
            found = sheet.value(OWN, key)
        else:
            found = (
                f"(SELECT {sheet.value('t', key)} FROM {sheet.rows} AS t WHERE t.y = {row.sql()})"
            )
        return Typed(f"coalesce({found}, 'null'::jsonb)", VALUE, sure=True, cell=cell)

    def area(self, node, scope: Scope) -> Range | None:
        found = self._lines(node)
        if found is None:
            return None
        _, sheet, rows, cols = found
        return _range(sheet, rows, cols)


def _range(sheet: Sheet, rows: tuple[_Line, _Line], cols: tuple[_Line, _Line]) -> Range:
    top, bottom = rows
    left, right = cols
    cut = bottom
    if bottom == _Line(LAST_ROW):
        cut = _Line(min(LAST_ROW, sheet.extent[0]))
    last = min(LAST_COL, sheet.extent[1]) if right.at == LAST_COL else right.at
    keys = ", ".join(f"({x - left.at + 1}, {sheet.key(x)})" for x in range(left.at, last + 1))
    source = (
        f"(SELECT g.y - {top.sql()} + 1 AS y, c.x, "
        f"coalesce({sheet.value('t', 'c.k')}, 'null'::jsonb) AS v "
        f"FROM generate_series({top.sql()}, {cut.sql()}) AS g(y) "
        f"CROSS JOIN (VALUES {keys}) AS c(x, k) LEFT JOIN {sheet.rows} AS t ON t.y = g.y)"
        if keys
        else "(SELECT 1 AS y, 1 AS x, 'null'::jsonb AS v WHERE false)"
    )

    def resized(height: int, width: int) -> Range:
        return _range(
            sheet,
            (top, _Line(top.at + height - 1, top.moves)),
            (left, _Line(left.at + width - 1)),
        )

    return Range(
        source,
        bottom.at - top.at + 1,
        right.at - left.at + 1,
        (max(cut.at - top.at + 1, 0), max(last - left.at + 1, 0)),
        resized,
        top.moves,
    )
