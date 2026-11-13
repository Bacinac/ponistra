"""A table's data as the engine left it in Postgres (D22, E3): the rows below its header and
above its totals, the kind of value each of their cells holds and the text it shows, and the
order of rows by a column's values as Excel sorts them. Nothing is computed here; the values
are those the calculation wrote (GridRow.values)."""

import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from pycrdt import XmlElement

from apps.engine.functions.lookup import sorted_by
from apps.engine.values import loaded

from . import blocks, calculation
from . import rows as stored
from .blocks import CELL
from .grids import FORMAT, FORMULA, TEXT, Laid, formula_in, kind_of
from .sheets import merged
from .table import Draft

# The codes of SUBTOTAL that leave out what other subtotals hold, 101 AVERAGE to 111 VARP, as
# Excel's total row writes them.
SUBTOTALS = re.compile(r"SUBTOTAL\((10[1-9]|11[01]),")
READ = 2000


class Unsortable(Exception):
    """A merged cell spans rows that the sort would part."""


@dataclass(frozen=True)
class Data:
    """The rows of a table that hold its data, below its header and above its totals, and the
    kind of value each column holds in each of them, None where empty, with the text the
    columns asked for show there, and every row of subtotals, the totals' last."""

    rows: list[str]
    totals: str | None
    kinds: dict[str, list[str | None]]
    shown: dict[str, list[str]] = field(default_factory=dict)
    subtotals: list[str] = field(default_factory=list)


def held_rows(
    laid: Laid | Draft, ids: list[str], cols: Iterable[str]
) -> Iterator[tuple[str, tuple | None]]:
    """Each of the rows given in their order with what `_cells` gives of it, read a few
    thousand at a time so that a table of any length is never held whole."""
    cols = list(cols)
    for first in range(0, len(ids), READ):
        part = ids[first : first + READ]
        found = _cells(laid, part, cols)
        for id in part:
            yield id, found.get(id)


def formats_of(laid: Laid | Draft, ids: list[str], cols: Iterable[str]) -> dict[str, str | None]:
    """The number format most of the rows given show each column in, none where none has one."""
    cols = list(cols)
    counted: dict[str, Counter] = {col: Counter() for col in cols}
    for _, held in held_rows(laid, ids, cols):
        for col in cols:
            if held is not None and (format := (held[2].get(col) or {}).get(FORMAT)):
                counted[col][format] += 1
    return {col: each.most_common(1)[0][0] if each else None for col, each in counted.items()}


def calculated(laid: Laid | Draft, ids: list[str], col: str) -> bool:
    """Whether every row given holds in the column one formula, as the cells keep it: relative
    to its own row, so a formula filled down is one."""
    first = None
    for _, held in held_rows(laid, ids, [col]):
        found = (held[2].get(col) or {}).get(FORMULA) if held is not None else None
        if found is None or (first is not None and found != first):
            return False
        first = found
    return first is not None


def _cells(laid: Laid | Draft, ids: list[str], cols: Iterable[str]) -> dict[str, tuple]:
    """Of each row given, the values, the texts shown and the cells of the columns given."""
    cols = list(cols)
    if not isinstance(laid, Draft):
        return {
            id: (row.values, row.shown, row.cells)
            for id in ids
            if (row := laid.row(id)) is not None
        }
    mine = {**laid.owned, **laid.made}
    found = stored.columns(laid.base.grid, [id for id in ids if id not in mine], cols)
    for id in ids:
        if (row := mine.get(id)) is not None:
            found[id] = (row.values, row.shown, row.cells)
    return found


def _value(held: tuple | None, col: str):
    return loaded(None if held is None else held[0].get(col))


def _kind(held: tuple | None, col: str) -> str | None:
    value = None if held is None else held[0].get(col)
    return None if value is None else kind_of(value)


def _shown(held: tuple | None, col: str, locale: str) -> str:
    if held is None:
        return ""
    values, shown, cells = held
    if col in shown:
        return shown[col]
    cell = cells.get(col) or {}
    if isinstance(cell.get(TEXT), str):
        return cell[TEXT]
    format = cell.get(FORMAT)
    return calculation.shown(loaded(values.get(col)), format, locale)


def _emphasized(content: list[blocks.Block]) -> bool | None:
    """Whether all of the cell's text is bold or in headings; None if it has no text."""
    texts = [
        (block.type == "heading" or "strong" in run.marks)
        for block in content
        for run in block.runs
        if isinstance(run, blocks.Run) and run.text.strip()
    ]
    return all(texts) if texts else None


def _emphases(laid: Laid | Draft, element: XmlElement | None, row: str) -> list[bool]:
    """Whether each cell of the row with text has all of it bold or in headings."""
    nodes = {}
    if element is not None:
        nodes = {
            child.attributes.get("col"): child
            for child in element.children
            if isinstance(child, XmlElement)
            and child.tag == CELL
            and child.attributes.get("row") == row
        }
    found = []
    for col in laid.col_ids():
        if col in nodes:
            emphasized = _emphasized(blocks.blocks_in(nodes[col]))
        else:
            text = laid.cell(row, col).get(TEXT) or ""
            marks = (laid.look_at(row, col) or {}).get("marks") or {}
            emphasized = ("strong" in marks) if text.strip() else None
        if emphasized is not None:
            found.append(emphasized)
    return found


def _header(
    laid: Laid | Draft, element: XmlElement | None, ids: list[str], kinds: list[str | None]
) -> bool:
    """Whether the first of the rows is a header, as Excel and Word tell one: its text is all
    bold where the next row's is not, or the column holds text there and only other kinds
    below."""
    if len(ids) > 1:
        first, second = _emphases(laid, element, ids[0]), _emphases(laid, element, ids[1])
        if first and all(first) and False in second:
            return True
    below = [kind for kind in kinds[1:] if kind is not None]
    return kinds[0] == "text" and bool(below) and "text" not in below


def _subtotals(pieces, col: str, place: Callable[[str], int | None], y: int) -> bool:
    match pieces:
        case [
            str(head),
            {"from": {"row": first, "col": start}, "to": {"row": last, "col": end}},
            ")",
        ]:
            if (
                SUBTOTALS.fullmatch(head.replace(" ", "").upper()) is None
                or not start == end == col
            ):
                return False
            top, bottom = place(first), place(last)
            return top is not None and bottom is not None and top <= bottom < y
    return False


def subtotal_rows(document, laid: Laid | Draft) -> list[str]:
    """The rows with a formula that subtotals its own column, ignoring other subtotals, from a
    row above it to another, as Totals and Group write them, in the table's order."""
    if isinstance(laid, Draft):
        candidates = {*stored.subtotalling(document, laid.base.grid), *laid.owned, *laid.made}
    else:
        candidates = {row.id for row in laid.rows}
    rows = {id: row for id in candidates if (row := laid.row(id)) is not None}
    reached = {
        piece[end]["row"]
        for row in rows.values()
        for cell in row.cells.values()
        if isinstance(cell.get(FORMULA), list)
        for piece in cell[FORMULA]
        if isinstance(piece, dict)
        for end in ("from", "to")
        if isinstance(piece.get(end), dict) and "row" in piece[end]
    }
    places = laid.places(rows.keys() | reached)
    found = []
    for id, row in rows.items():
        for col, cell in row.cells.items():
            formula = cell.get(FORMULA)
            if isinstance(formula, list) and _subtotals(
                formula_in(formula, id, col), col, places.get, places[id]
            ):
                found.append(id)
                break
    return sorted(found, key=places.__getitem__)


def totals_row(document, laid: Laid | Draft) -> str | None:
    """The row of the table's totals, as Excel's total row and the action Totals write it:
    the last of its subtotal rows."""
    found = subtotal_rows(document, laid)
    return found[-1] if found else None


def data_of(
    document,
    laid: Laid | Draft,
    element: XmlElement | None,
    locale: str,
    shown: tuple[str, ...] = (),
) -> Data:
    """The table's data, with the text the columns given show in each of its rows."""
    subtotals = subtotal_rows(document, laid)
    totals = subtotals[-1] if subtotals else None
    ids = laid.ids(0, laid.size - 1)
    rows = ids[: ids.index(totals)] if totals else ids
    cols = laid.col_ids()
    kinds: dict[str, list] = {col: [] for col in cols}
    texts: dict[str, list] = {col: [] for col in shown}
    for _, held in held_rows(laid, rows, cols):
        for col in cols:
            kinds[col].append(_kind(held, col))
        for col in shown:
            texts[col].append(_shown(held, col, locale))
    if len(rows) > 1 and any(_header(laid, element, rows, each) for each in kinds.values()):
        rows = rows[1:]
        kinds = {col: each[1:] for col, each in kinds.items()}
        texts = {col: each[1:] for col, each in texts.items()}
    return Data(rows, totals, kinds, texts, subtotals)


def order(
    document,
    laid: Laid | Draft,
    element: XmlElement | None,
    locale: str,
    col: str,
    rows: list[str] | None,
    descending: bool,
    shown: Callable[[list[str]], list[str]] | None = None,
) -> list[str]:
    """The rows given, or else every row of the table below its header but its totals, in
    the order Excel sorts them by their values in the column: numbers, text as Windows
    compares it in the language, logical values, then errors, all of it reversed when
    descending; empty cells go last either way, and rows with equal values keep their
    order; of them only those `shown` keeps, where it is given, the rest staying where they
    are."""
    cols = laid.col_ids()
    if col not in cols:
        raise LookupError("no such column")
    if rows is None:
        totals = totals_row(document, laid)
        ids = laid.ids(0, laid.size - 1)
        places = {id: place for place, id in enumerate(ids)}
        chosen = [id for id in ids if id != totals]
    else:
        places = laid.places(rows)
        if len(places) != len(set(rows)):
            raise LookupError("no such row")
        chosen = sorted(places, key=places.__getitem__)
    x = cols.index(col)
    merges = merged(laid)
    covering = {
        each.y: each.cell.col
        for each in merges
        if each.rows == 1 and each.x <= x < each.x + each.cols
    }
    held = _cells(laid, chosen, {col, *covering.values()})

    def value(id: str):
        return _value(held.get(id), covering.get(places[id], col))

    if rows is None and len(chosen) > 1:
        kinds = [_kind(held.get(id), covering.get(places[id], col)) for id in chosen]
        if _header(laid, element, chosen, kinds):
            chosen = chosen[1:]
    if shown is not None:
        chosen = shown(chosen)
    taken = {places[id] for id in chosen}
    if any(each.rows > 1 and taken & set(range(each.y, each.y + each.rows)) for each in merges):
        raise Unsortable
    return sorted_by(chosen, value, descending, calculation.language(locale))
