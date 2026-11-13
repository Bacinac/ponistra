"""What code finds in a table for a model to read in place of its cells (D19, A6-4): of each
column its header, the kinds of value it holds, how many cells are empty, its distinct values
and the commonest of them, the least and the greatest number, and the address a formula reads
its data by; and the rows of a stretch of the table, each cell as it shows. Both read every row
of the table however long, a few thousand at a time."""

from collections import Counter

from pycrdt import Doc

from apps.collab import server
from apps.content import calculation
from apps.content.data import data_of, held_rows
from apps.content.grids import FORMAT, FORMULA, TEXT, kind_of
from apps.content.operations import Refused
from apps.content.sheets import Sheets
from apps.documents.models import Tab
from apps.engine.parse import column_name, quote_sheet
from apps.engine.values import loaded

from .tables import table_in

# Past this many distinct values a column counts no more of them.
DISTINCT = 10_000
COMMON = 5
SAMPLE = 12
# The rows a model reads of a stretch at once.
STRETCH = 200


def _shown(held: tuple | None, col: str, locale: str) -> str:
    if held is None:
        return ""
    values, shown, cells = held
    if col in shown:
        return shown[col]
    cell = cells.get(col) or {}
    if isinstance(cell.get(TEXT), str):
        return cell[TEXT]
    return calculation.shown(loaded(values.get(col)), cell.get(FORMAT), locale)


class _Column:
    """What one column's data holds, counted as its rows go by."""

    def __init__(self) -> None:
        self.kinds: Counter = Counter()
        self.formulas = 0
        self.values: Counter = Counter()
        self.more = False
        self.least: float | None = None
        self.most: float | None = None
        self.formats: Counter = Counter()

    def add(self, held: tuple | None, col: str, locale: str) -> None:
        value = None if held is None else held[0].get(col)
        cell = {} if held is None else held[2].get(col) or {}
        if FORMULA in cell:
            self.formulas += 1
        if format := cell.get(FORMAT):
            self.formats[format] += 1
        if value is None or value == "":
            self.kinds["empty"] += 1
            return
        kind = kind_of(value)
        self.kinds[kind] += 1
        if kind == "number":
            self.least = value if self.least is None else min(self.least, value)
            self.most = value if self.most is None else max(self.most, value)
        shown = _shown(held, col, locale)
        if shown in self.values or len(self.values) < DISTINCT:
            self.values[shown] += 1
        else:
            self.more = True

    def said(self, locale: str) -> dict:
        format = self.formats.most_common(1)[0][0] if self.formats else None
        found: dict = {"kinds": dict(self.kinds), "distinct": len(self.values)}
        if self.more:
            found["distinct"] = f"more than {DISTINCT}"
        if self.formulas:
            found["formulas"] = self.formulas
        if format:
            found["format"] = format
        if self.least is not None:
            found["least"] = calculation.shown(self.least, format, locale)
            found["greatest"] = calculation.shown(self.most, format, locale)
        common = [(text, times) for text, times in self.values.most_common(COMMON) if times > 1]
        if common:
            found["commonest"] = [{"value": text, "rows": times} for text, times in common]
        return found


def _sample(rows: list[str]) -> list[str]:
    """The first rows and others spread evenly over the rest."""
    if len(rows) <= SAMPLE:
        return rows
    head = SAMPLE // 2
    step = (len(rows) - head) / (SAMPLE - head)
    return rows[:head] + [rows[head + int(step * at)] for at in range(SAMPLE - head)]


def profile_of(
    document, doc: Doc, held: Sheets, table: str, locale: str, name: str | None = None
) -> dict:
    """The table as its columns' profiles, its data's rows by number and a sample of them, its
    data addressed by its name or the one given it."""
    laid, element = table_in(doc, held, table)
    data = data_of(document, laid, element, locale)
    cols = laid.col_ids()
    counted = {col: _Column() for col in cols}
    for _, found in held_rows(laid, data.rows, cols):
        for col in cols:
            counted[col].add(found, col, locale)
    first = laid.ids(0, 0)[0] if laid.size else None
    header = None
    if data.rows and first is not None and data.rows[0] != first:
        header = dict(held_rows(laid, [first], cols))[first]
    name = name or laid.name
    sheet = quote_sheet(name) if name else None
    top = laid.place(data.rows[0]) + 1 if data.rows else None
    bottom = laid.place(data.rows[-1]) + 1 if data.rows else None
    columns = []
    for at, col in enumerate(cols, 1):
        letter = column_name(at)
        said = {"id": col, "letter": letter}
        if header is not None:
            said["header"] = _shown(header, col, locale)
        if sheet is not None and top is not None:
            said["data"] = f"{sheet}!{letter}{top}:{letter}{bottom}"
        columns.append({**said, **counted[col].said(locale)})
    sample = _sample(data.rows)
    shown = dict(held_rows(laid, sample, cols))
    return {
        "table": table,
        "name": name or None,
        "rows": laid.size,
        "data": {"first": top, "last": bottom, "rows": len(data.rows)},
        "totals": laid.place(data.totals) + 1 if data.totals else None,
        "columns": columns,
        "sample": [
            {
                "row": laid.place(id) + 1,
                "cells": [_shown(shown.get(id), col, locale) for col in cols],
            }
            for id in sample
        ],
    }


def stretch_of(held: Sheets, table: str, first: int, count: int, locale: str) -> dict:
    """The rows of any of the document's tables from the one numbered `first`, each cell as it
    shows."""
    laid = held.peek(table)
    if laid is None:
        raise Refused("no_table", table)
    count = min(count, STRETCH)
    if first < 1 or first > laid.size:
        raise Refused("no_row", str(first))
    ids = laid.ids(first - 1, min(first + count, laid.size + 1) - 2)
    cols = laid.col_ids()
    found = dict(held_rows(laid, ids, cols))
    return {
        "table": table,
        "rows": laid.size,
        "columns": cols,
        "stretch": [
            {
                "row": first + at,
                "id": id,
                "cells": [_shown(found.get(id), col, locale) for col in cols],
            }
            for at, id in enumerate(ids)
        ],
    }


def profile(tab: Tab, table: str, name: str | None = None) -> dict:
    """The table of the tab profiled as it now computes."""
    document, locale = tab.document, tab.document.locale
    return server.read_grids(
        tab.room,
        lambda doc, held: profile_of(document, doc, held, table, locale, name),
        settled=True,
    )


def stretch(tab: Tab, table: str, first: int, count: int) -> dict:
    locale = tab.document.locale
    return server.read_grids(
        tab.room,
        lambda doc, held: stretch_of(held, table, first, count, locale),
        settled=True,
    )
