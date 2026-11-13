"""Every case of the workbooks Excel saved compiled into SQL and computed by Postgres over the
cells Excel saved, the formula's own inputs among them, each held to the value Excel saved for
it, or NULL where Python is to compute it. Every function with a SQL form computes some case."""

import json
from collections import Counter

import pytest
from django.db import DatabaseError, connection, transaction

from apps.engine.book import calls
from apps.engine.evaluate import _reference
from apps.engine.functions import SQL_FORMS
from apps.engine.grid import Area, Context, bounded
from apps.engine.parse import Ref, parse, relative
from apps.engine.query import compiled
from apps.engine.sql import VALUE, Range, Typed, Unsupported, text_literal
from apps.engine.tests.cases import CASES, READING
from apps.engine.tests.saved import MISSING, same, tolerance_of
from apps.engine.values import Error, loaded, stored

pytestmark = pytest.mark.django_db


class _Sheets:
    """The places of a formula in a case's cell, read off the cells loaded into engine_cells."""

    def __init__(self, book, sheet: str, row: int, col: int):
        self.context = Context(book, sheet, row, col, book.language, book.now, book.random)

    def _area(self, node) -> Area | None:
        if not isinstance(node, Ref):
            raise Unsupported("a reference a table keeps")
        found = _reference(node)(self.context)
        return None if isinstance(found, Error) else found

    def cell(self, node, scope) -> Typed | None:
        area = self._area(node)
        if area is None:
            return None
        here = self.context
        if area.height == 1 and area.width == 1:
            row, col = area.top, area.left
        elif area.width == 1 and area.top <= here.row <= area.bottom:
            row, col = here.row, area.left
        elif area.height == 1 and area.left <= here.col <= area.right:
            row, col = area.top, here.col
        else:
            return None
        return Typed(
            "coalesce((SELECT t.v FROM engine_cells AS t WHERE "
            f"t.sheet = {text_literal(area.sheet.casefold())} AND t.y = {row} AND t.x = {col}), "
            "'null'::jsonb)",
            VALUE,
            sure=True,
            cell=True if area.height == area.width == 1 else None,
        )

    def area(self, node, scope) -> Range | None:
        area = self._area(node)
        return None if area is None else self._range(area)

    def each(self, given: str) -> str:
        return f"SELECT {given} AS v"

    def _range(self, area: Area) -> Range:
        cut = bounded(area, self.context.book)
        return Range(
            f"(SELECT g.y - {cut.top} + 1 AS y, h.x - {cut.left} + 1 AS x, "
            "coalesce(t.v, 'null'::jsonb) AS v "
            f"FROM generate_series({cut.top}, {cut.bottom}) AS g(y) "
            f"CROSS JOIN generate_series({cut.left}, {cut.right}) AS h(x) "
            f"LEFT JOIN engine_cells AS t ON t.sheet = {text_literal(area.sheet.casefold())} "
            "AND t.y = g.y AND t.x = h.x)",
            area.height,
            area.width,
            (max(cut.height, 0), max(cut.width, 0)),
            lambda height, width: self._range(
                Area(area.sheet, area.top, area.left, area.top + height - 1, area.left + width - 1)
            ),
        )


def _loaded(sheets: dict[str, dict]) -> None:
    rows = [
        (title.casefold(), row, col, json.dumps(stored("" if value is MISSING else value)))
        for title, sheet in sheets.items()
        if title not in READING
        for cells in (sheet["constants"], sheet["values"])
        for (row, col), value in cells.items()
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TEMP TABLE engine_cells (sheet text, y int, x int, v jsonb, "
            "PRIMARY KEY (sheet, y, x))"
        )
        cursor.executemany("INSERT INTO engine_cells VALUES (%s, %s, %s, %s::jsonb)", rows)


def test_sql_computes_what_excel_saved(code, etalon, book):
    _loaded(etalon)
    cased = [
        (title, row, text)
        for title in CASES
        if title not in READING
        for (row, col), text in etalon[title]["formulas"].items()
        if col == 1
    ]
    wrong = []
    computed: Counter = Counter()
    tally: Counter = Counter()
    for title, row, text in cased:
        tree = relative(parse(text), row, 1)
        try:
            sql = compiled(tree, _Sheets(book, title, row, 1), book.language)
        except Unsupported:
            tally["python"] += 1
            continue
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(f"SELECT r IS NULL, r FROM (SELECT {sql} AS r OFFSET 0) AS q")
                empty, found = cursor.fetchone()
        except DatabaseError as error:
            wrong.append(f"{title} {row} {text}: {str(error).splitlines()[0]}")
            continue
        if empty:
            tally["null"] += 1
            continue
        tally["sql"] += 1
        computed.update(set(calls(tree)))
        saved = etalon[title]["values"][row, 1]
        value = loaded(json.loads(found))
        if not same(value, "" if saved is MISSING else saved, tolerance_of(text)):
            wrong.append(f"{title} {row} {text}: Excel {saved!r}, SQL {value!r}")
    print(f"{code}: {dict(tally)}")
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong)
    unused = sorted(name for name in SQL_FORMS if not computed[name])
    assert not unused, f"no case computes in SQL: {', '.join(unused)}"
