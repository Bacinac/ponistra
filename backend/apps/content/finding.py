"""Find and replace over a tab (D22, E3): its text and its notes as the document's state holds
them, its tables' cells by SQL over the text each shows (GridRow), in the order they stand."""

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from pycrdt import XmlElement, XmlFragment

from . import rows as stored
from .blocks import CELL, NOTE, TEXTBLOCKS, chunks_of
from .grids import FORMULA, TEXT, Laid
from .table import Draft

TABLE = "table"
# The most hits a search gives; past them it only says there are more.
LIMIT = 1000


@dataclass(frozen=True)
class Sought:
    """What is looked for: the text, whether its case counts and whether it stands as a word
    of its own."""

    text: str
    case: bool = False
    words: bool = False

    def pattern(self) -> re.Pattern:
        body = re.escape(self.text)
        if self.words:
            body = rf"(?<!\w){body}(?!\w)"
        return re.compile(body, 0 if self.case else re.IGNORECASE)

    def sql(self) -> str:
        """The regular expression Postgres finds the cells by, its case left to `matching`."""
        body = re.sub(r"([^\w\s])", r"\\\1", self.text)
        if self.words:
            body = f"(^|[^[:alnum:]_]){body}($|[^[:alnum:]_])"
        return body

    def spans(self, text: str) -> list[tuple[int, int]]:
        return [found.span() for found in self.pattern().finditer(text)]


@dataclass(frozen=True)
class Hit:
    """Where the text was found: in a block or a note, from a character to another, or in a
    table's cell, holding blocks or a text, the latter wholly and maybe by a formula."""

    block: str | None = None
    start: int = 0
    end: int = 0
    table: str | None = None
    row: str | None = None
    col: str | None = None
    formula: bool = False

    def json(self) -> dict:
        found: dict = {}
        if self.table is not None:
            found |= {"table": self.table, "row": self.row, "col": self.col}
        if self.block is not None:
            found |= {"block": self.block, "from": self.start, "to": self.end}
        if self.formula:
            found["formula"] = True
        return found


def unquoted(text: str) -> tuple[str, str]:
    """The apostrophe that keeps a cell's text a text, and the text it shows."""
    return ("'", text[1:]) if text.startswith("'") else ("", text)


def in_block(
    element: XmlElement, sought: Sought, cell: tuple[str, str, str] | None = None
) -> Iterator[Hit]:
    """The hits in the block's text, each text apart, then in its notes'."""
    id = element.attributes.get("id")
    if isinstance(id, str):
        table, row, col = cell or (None, None, None)
        for _, at, plain in chunks_of(element)[0]:
            for start, end in sought.spans(plain):
                yield Hit(id, at + start, at + end, table, row, col)
    for child in element.children:
        if isinstance(child, XmlElement) and child.tag == NOTE:
            yield from in_block(child, sought, cell)


def blocked_cells(element: XmlElement) -> dict[tuple[str, str], XmlElement]:
    """The table's cells holding blocks, by row and column."""
    return {
        (child.attributes.get("row"), child.attributes.get("col")): child
        for child in element.children
        if isinstance(child, XmlElement) and child.tag == CELL
    }


def text_cells(
    element: XmlElement, laid: Laid | Draft, sought: Sought, limit: int | None
) -> Iterator[tuple[str, str, str, bool]]:
    """The table's cells holding a text, typed or calculated, not blocks, that has the text
    sought, but in hidden rows: each one's row, column, typed text and whether a formula
    calculates it; in the table's order where it is read from Postgres whole."""
    pattern = sought.pattern()
    blocked = blocked_cells(element).keys()

    def held(row, col: str) -> tuple[str, str, bool] | None:
        if (row.id, col) in blocked:
            return None
        cell = row.cells.get(col) or {}
        if col in row.shown:
            text = row.shown[col]
        elif isinstance(cell.get(TEXT), str):
            text = unquoted(cell[TEXT])[1]
        else:
            return None
        return (text, cell.get(TEXT) or "", FORMULA in cell) if pattern.search(text) else None

    cols = laid.col_ids()
    if isinstance(laid, Draft):
        mine = {**laid.owned, **laid.made}
        found = stored.matching(laid.base.grid, sought.sql(), sought.case, limit, mine)
        laid.load(id for id, *_ in found)
        for id, _, col, text in found:
            if col in cols and pattern.search(text):
                row = laid.row(id)
                if row is not None and (each := held(row, col)) is not None:
                    yield id, col, each[1], each[2]
        rows = [row for row in mine.values() if not row.hidden]
    else:
        rows = [row for row in laid.rows if not row.hidden]
    for row in rows:
        for col in cols:
            if (each := held(row, col)) is not None:
                yield row.id, col, each[1], each[2]


def in_table(element: XmlElement, laid: Laid | Draft, sought: Sought, limit: int) -> list[Hit]:
    """The hits in the table's cells, by rows and in each by columns."""
    table = element.attributes.get("id")
    cols = {col: x for x, col in enumerate(laid.col_ids())}
    hits = [
        (row, col, Hit(None, 0, 0, table, row, col, formula))
        for row, col, _, formula in text_cells(element, laid, sought, limit)
    ]
    for (row, col), cell in blocked_cells(element).items():
        if col in cols:
            for child in cell.children:
                if isinstance(child, XmlElement) and child.tag in TEXTBLOCKS:
                    hits.extend(
                        (row, col, hit) for hit in in_block(child, sought, (table, row, col))
                    )
    ids = {row for row, _, _ in hits}
    if isinstance(laid, Draft):
        places = stored.positions(laid.base.grid, ids)
    else:
        places = {id: at for id, at in laid.at().items() if id in ids}
    hits = [each for each in hits if each[0] in places]
    hits.sort(key=lambda each: (places[each[0]], cols[each[1]]))
    return [hit for _, _, hit in hits]


def found_in(
    body: XmlFragment, grids: Mapping[str, Laid | Draft], sought: Sought, limit: int = LIMIT
) -> tuple[list[Hit], bool]:
    """The hits in the tab, at most `limit` of them, and whether there are more."""
    hits: list[Hit] = []
    for element in body.children:
        if not isinstance(element, XmlElement):
            continue
        if element.tag == TABLE:
            laid = grids.get(element.attributes.get("id"))
            if laid is not None:
                hits.extend(in_table(element, laid, sought, limit + 1 - len(hits)))
        elif element.tag in TEXTBLOCKS:
            hits.extend(in_block(element, sought))
        if len(hits) > limit:
            return hits[:limit], True
    return hits, False
