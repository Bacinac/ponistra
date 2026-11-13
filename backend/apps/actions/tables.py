"""Actions on a table, carried out by code."""

import re
from collections.abc import Callable, Iterator, Mapping

from pycrdt import Doc, XmlElement

from apps.collab import server
from apps.content import blocks, calculation, compute
from apps.content import rows as stored
from apps.content.data import (
    Data,
    Unsortable,
    calculated,
    data_of,
    formats_of,
    held_rows,
    order,
    totals_row,
)
from apps.content.grids import FORMULA, TEXT, Laid, formula_in
from apps.content.operations import TEXTBLOCKS, Refused
from apps.content.sheets import Sheets, covered, merged
from apps.content.table import Draft
from apps.documents.models import Tab
from apps.engine.parse import column_name

Build = Callable[[Doc, Sheets], list]

# What a table's totals row is labelled in the document's language, as Excel labels it there.
TOTAL = {
    "hr": "Ukupno",
    "en": "Total",
    "en-GB": "Total",
    "de": "Ergebnis",
    "fr": "Total",
    "it": "Totale",
    "es": "Total",
}
# What a group's subtotals row is labelled, by the value it groups, as Excel labels it there.
GROUP = {
    "hr": "{} ukupno",
    "en": "{} Total",
    "en-GB": "{} Total",
    "de": "{} Ergebnis",
    "fr": "Total {}",
    "it": "Totale {}",
    "es": "Total {}",
}
# What a cell of the totals row holds, by the function SUBTOTAL computes over its column, as
# Excel's total row offers them; none takes the function off.
# How a calculated column is worked out of the columns it takes, written as Excel writes it:
# an operator between them, or a function over them.
OPERATIONS = {
    "sum": "+",
    "difference": "-",
    "product": "*",
    "quotient": "/",
    "average": "AVERAGE",
    "min": "MIN",
    "max": "MAX",
}
PAIRS = ("difference", "quotient")
FUNCTIONS = {
    "sum": 109,
    "average": 101,
    "count": 102,
    "counta": 103,
    "min": 105,
    "max": 104,
    "none": None,
}
BOLD = [{"type": "strong"}]
LOOK = [{"type": "paragraph", "attrs": {"endMarks": {"strong": {}}}}]
SPACE = re.compile(r"\s+")
GROUPED = re.compile(r"(?<=\d)[ \u00a0\u2009\u202f](?=\d{3}(?!\d))")
# Leading zeros and letters mark a code, as an article's number or a postal code is, kept as text.
CODE = re.compile(r"[-+]?0\d|.*[A-Za-z]")


def _placed(doc: Doc, sheets: Sheets, id: str) -> tuple[Laid | Draft, XmlElement] | None:
    laid = sheets.peek(id)
    return None if laid is None else compute.placed_in(doc, {id: laid}, {id}).get(id)


def _found(
    tab: Tab, id: str, shown: tuple[str, ...] = ()
) -> tuple[Laid | Draft, Data, list[blocks.Cell]]:
    """The table to read, its data as the engine last calculated it and the cells it keeps as
    nodes in the text."""
    locale = tab.document.locale

    def reading(doc: Doc, held: Sheets):
        placed = _placed(doc, held, id)
        if placed is None:
            return None
        grid, element = placed
        data = data_of(held.document, grid, element, locale, shown)
        return grid, data, blocks.table_of(element, {}).cells

    found = server.read_grids(tab.room, reading)
    if found is None:
        raise Refused("no_table", id)
    return found


def _taken_out(id: str, axis: str, at: Mapping[str, int]) -> list[dict]:
    """The operations that take out the lines, given with where each stands, one for each run
    of them standing together."""
    runs: list[list[str]] = []
    for line in sorted(at, key=at.__getitem__):
        if runs and at[line] == at[runs[-1][1]] + 1:
            runs[-1][1] = line
        else:
            runs.append([line, line])
    return [
        {"op": "lines", "table": id, "axis": axis, "from": first, "to": last, "remove": True}
        for first, last in runs
    ]


def _shape(sheets: Sheets, id: str) -> tuple[list[str], list[str]]:
    laid = sheets.peek(id)
    if laid is None:
        raise Refused("no_table", id)
    return laid.row_ids(), laid.col_ids()


def table_in(doc: Doc, sheets: Sheets, id: str) -> tuple[Laid | Draft, XmlElement]:
    placed = _placed(doc, sheets, id)
    if placed is None:
        raise Refused("no_table", id)
    return placed


def _totals_shown(doc: Doc, sheets: Sheets, id: str, on: bool) -> list[dict]:
    """The operation that turns the totals of the designs over the whole table on or off; none
    where they already are."""
    designs = blocks.table_of(table_in(doc, sheets, id)[1], {}).attrs.get("designs") or []
    if all("area" in each or each.get("on", {}).get("totals", False) == on for each in designs):
        return []
    turned = [
        each if "area" in each else {**each, "on": {**each.get("on", {}), "totals": on}}
        for each in designs
    ]
    return [{"op": "set", "block": id, "attrs": {"designs": turned}}]


def _sums(kinds: dict[str, list[str | None]], but: str | None = None) -> list[str]:
    """The columns that hold numbers alone, empty cells aside."""
    return [
        col
        for col, each in kinds.items()
        if col != but and "number" in each and set(each) <= {"number", None}
    ]


def _labelled(row: str, sums: list[str], col: str | None, label: str) -> list[dict]:
    """The look of a row of subtotals: bold, labelled in the column given."""
    cells: list[dict] = [{"row": row, "col": each, "blocks": LOOK} for each in sums]
    if col is not None:
        text = {"type": "text", "text": label, "marks": BOLD}
        cells.append({"row": row, "col": col, "blocks": [{"type": "paragraph", "content": [text]}]})
    return cells


def _subtotals(
    row: str,
    sums: list[str],
    cols: list[str],
    start: int,
    end: int,
    formats: dict,
    code: int = FUNCTIONS["sum"],
) -> list[dict]:
    """The cells of a row that subtotal each column of numbers from one row to another,
    counted from 1, in the column's number format, by SUBTOTAL's function of the code."""

    def subtotal(col: str) -> str:
        letter = column_name(cols.index(col) + 1)
        return f"SUBTOTAL({code},{letter}{start}:{letter}{end})"

    return [
        {"row": row, "col": col, "formula": subtotal(col), "format": formats[col]} for col in sums
    ]


def totals(tab: Tab, target: dict, parameters: dict) -> Build:
    """A row below the table's data that subtotals each of its columns of numbers in the
    number format most of the column shows in, labelled in bold in the first other column;
    run again, its subtotals cover the rows the data has by then."""
    id = target["table"]
    locale = tab.document.locale
    laid, data, _ = _found(tab, id)
    sums = _sums(data.kinds)
    if not sums:
        raise Refused("no_numbers", id)
    formats = formats_of(laid, data.rows, sums)
    label = next((col for col in laid.col_ids() if col not in sums), None)
    first = data.rows[0]

    def build(doc: Doc, sheets: Sheets) -> list[dict]:
        rows, cols = _shape(sheets, id)
        if first not in rows or any(col not in cols for col in sums):
            raise Refused("changed", id)
        new = data.totals not in rows
        row = blocks.new_id() if new else data.totals
        end = len(rows) if new else rows.index(row)
        start = rows.index(first) + 1
        if start > end:
            raise Refused("changed", id)
        built: list[dict] = []
        if new:
            built += [
                {"op": "lines", "table": id, "axis": "rows", "ids": [row]},
                {"op": "cells", "table": id, "cells": _labelled(row, sums, label, TOTAL[locale])},
                *_totals_shown(doc, sheets, id, True),
            ]
        written = _subtotals(row, sums, cols, start, end, formats)
        return [*built, {"op": "cells", "table": id, "cells": written}]

    return build


def total(tab: Tab, target: dict, parameters: dict) -> Build:
    """The cell of the totals row under the column holds the function chosen, a subtotal over
    the column's data in the number format most of it shows in, or nothing; a column holding
    other than numbers takes the count of its values alone. The row is made below the data,
    labelled as Totals labels it, when the table has none, and taken out with its last
    subtotal."""
    id, col = target["table"], target["col"]
    code = FUNCTIONS[parameters["function"]]
    locale = tab.document.locale
    laid, data, _ = _found(tab, id)
    every = laid.col_ids()
    if col not in every:
        raise Refused("no_line", col)
    if not data.rows:
        raise Refused("no_numbers", id)
    numbers = _sums(data.kinds)
    if code not in (None, FUNCTIONS["counta"]) and col not in numbers:
        raise Refused("text_column", col)
    formats = formats_of(laid, data.rows, [col]) if col in numbers else {col: None}
    label = next((each for each in every if each not in numbers and each != col), None)
    first = data.rows[0]
    alone = not any(
        other != col and FORMULA in cell
        for _, held in held_rows(laid, [data.totals] if data.totals else [], every)
        if held is not None
        for other, cell in held[2].items()
    )

    def build(doc: Doc, sheets: Sheets) -> list[dict]:
        rows, cols = _shape(sheets, id)
        if first not in rows or col not in cols:
            raise Refused("changed", id)
        new = data.totals not in rows
        if code is None:
            if new:
                raise Refused("no_totals", id)
            if alone:
                return [
                    *_taken_out(id, "rows", {data.totals: rows.index(data.totals)}),
                    *_totals_shown(doc, sheets, id, False),
                ]
            cleared = [{"row": data.totals, "col": col, "value": None}]
            return [{"op": "cells", "table": id, "cells": cleared}]
        row = blocks.new_id() if new else data.totals
        end = len(rows) if new else rows.index(row)
        start = rows.index(first) + 1
        if start > end:
            raise Refused("changed", id)
        built: list[dict] = []
        if new:
            built += [
                {"op": "lines", "table": id, "axis": "rows", "ids": [row]},
                {"op": "cells", "table": id, "cells": _labelled(row, [col], label, TOTAL[locale])},
                *_totals_shown(doc, sheets, id, True),
            ]
        written = _subtotals(row, [col], cols, start, end, formats, code)
        return [*built, {"op": "cells", "table": id, "cells": written}]

    return build


def calculate(tab: Tab, target: dict, parameters: dict) -> Build:
    """Every row of the data holds in the column the operation over the columns given, as
    Excel's calculated column holds a formula, in the number format the first of them shows in
    that has one; the column holds nothing in the data, or is calculated already. A row put
    into the data later takes the formula of its neighbours."""
    id, col = target["table"], target["col"]
    operation, columns = parameters["operation"], parameters["columns"]
    laid, data, _ = _found(tab, id)
    every = laid.col_ids()
    for each in (col, *columns):
        if each not in every:
            raise Refused("no_line", each)
    if col in columns:
        raise Refused("same_column", col)
    if operation in PAIRS and len(columns) != 2:
        raise Refused("operands", operation)
    if not data.rows:
        raise Refused("no_numbers", id)
    numbers = _sums(data.kinds)
    for each in columns:
        if each not in numbers:
            raise Refused("text_operand", each)
    if any(data.kinds[col]) and not calculated(laid, data.rows, col):
        raise Refused("column_in_use", col)
    formats = formats_of(laid, data.rows, columns)
    format = next((found for each in columns if (found := formats[each])), None)
    first = data.rows[0]

    def build(doc, sheets):
        rows, cols = _shape(sheets, id)
        if first not in rows or any(each not in cols for each in (col, *columns)):
            raise Refused("changed", id)
        letters = [column_name(cols.index(each) + 1) for each in columns]
        way = OPERATIONS[operation]

        def formula(row: str) -> str:
            points = [f"{letter}{rows.index(row) + 1}" for letter in letters]
            return way.join(points) if len(way) == 1 else f"{way}({','.join(points)})"

        written = [
            {"row": row, "col": col, "formula": formula(row), "format": format}
            for row in data.rows
            if row in rows
        ]
        return [{"op": "cells", "table": id, "cells": written}]

    return build


def group(tab: Tab, target: dict, parameters: dict) -> Build:
    """The table's data sorted by the column and, below each run of one value in it, a row
    that subtotals each other column of numbers, labelled in bold with the value, as Excel's
    Subtotal writes it; below them the totals row, which counts no subtotal twice. Run again,
    by any column, it first takes out the rows of the groups before."""
    id, by = target["table"], target["col"]
    locale = tab.document.locale
    laid, data, _ = _found(tab, id, (by,))
    every = laid.col_ids()
    if by not in every:
        raise Refused("no_line", by)
    grouped = set(data.subtotals) - {data.totals}
    kept = [y for y, row in enumerate(data.rows) if row not in grouped]
    rows = [data.rows[y] for y in kept]
    sums = _sums({col: [each[y] for y in kept] for col, each in data.kinds.items()}, by)
    if not rows or not sums:
        raise Refused("no_numbers", id)
    shown = dict(zip(data.rows, data.shown[by], strict=True))
    formats = formats_of(laid, rows, sums)
    label = next((col for col in every if col not in sums), None)

    def build(doc: Doc, sheets: Sheets) -> list[dict]:
        now, cols = _shape(sheets, id)
        old = [row for row in now if row in grouped]
        left = [row for row in now if row not in grouped]
        if rows[0] not in left or by not in cols or any(col not in cols for col in sums):
            raise Refused("changed", id)
        first = left.index(rows[0])
        if set(left[first : first + len(rows)]) != set(rows):
            raise Refused("changed", id)
        try:
            ordered = order(sheets.document, sheets.peek(id), None, locale, by, rows, False)
        except Unsortable:
            raise Refused("merged_rows", id) from None
        groups: list[list[str]] = []
        for row in ordered:
            if groups and shown[row].casefold() == shown[groups[-1][0]].casefold():
                groups[-1].append(row)
            else:
                groups.append([row])
        totals = data.totals if data.totals in left else None
        made = [blocks.new_id() for _ in groups]
        total = totals or blocks.new_id()
        laid = [row for each, sub in zip(groups, made, strict=True) for row in (*each, sub)]
        final = [*left[:first], *laid, *left[first + len(rows) :], *([] if totals else [total])]
        at = {row: y + 1 for y, row in enumerate(final)}
        built: list[dict] = []
        if old:
            built += _taken_out(id, "rows", {row: y for y, row in enumerate(now) if row in grouped})
        ends = {"from": left[first], "to": left[first + len(rows) - 1]}
        built.append({"op": "order", "table": id, "col": by, **ends})
        for sub, before in zip(made, [*(each[0] for each in groups[1:]), totals], strict=True):
            place = {"before": before} if before else {}
            built.append({"op": "lines", "table": id, "axis": "rows", "ids": [sub], **place})
        if not totals:
            built.append({"op": "lines", "table": id, "axis": "rows", "ids": [total]})
            built += _totals_shown(doc, sheets, id, True)
        looks = [
            cell
            for each, sub in zip(groups, made, strict=True)
            for cell in _labelled(sub, sums, by, GROUP[locale].format(shown[each[0]]).strip())
        ]
        if not totals:
            looks += _labelled(total, sums, label, TOTAL[locale])
        written = [
            cell
            for each, sub in zip(groups, made, strict=True)
            for cell in _subtotals(sub, sums, cols, at[each[0]], at[each[-1]], formats)
        ]
        written += _subtotals(total, sums, cols, at[final[first]], at[made[-1]], formats)
        return [
            *built,
            {"op": "cells", "table": id, "cells": looks},
            {"op": "cells", "table": id, "cells": written},
        ]

    return build


def _textual(cell: blocks.Cell) -> bool:
    return all(
        block.type in TEXTBLOCKS and all(isinstance(run, blocks.Run) for run in block.runs)
        for block in cell.blocks
    )


def _plain(cell: blocks.Cell) -> bool:
    """Whether the cell holds one paragraph of text alone, as a value typed into it does."""
    return cell.light or (
        len(cell.blocks) == 1 and cell.blocks[0].type == "paragraph" and _textual(cell)
    )


def _number(text: str) -> str | None:
    """The text of a number kept as text, without the apostrophe that keeps it so and the
    spaces between its digit groups."""
    bare = GROUPED.sub("", text.strip().removeprefix("'").strip())
    return bare if bare and not bare.startswith("=") and not CODE.match(bare) else None


def _trimmed(text: str) -> list[tuple[int, int]]:
    """The whitespace that goes: around the text, and within it all of each run but its first."""
    found = []
    for each in SPACE.finditer(text):
        if each.start() == 0 or each.end() == len(text):
            found.append((each.start(), each.end()))
        elif each.end() - each.start() > 1:
            found.append((each.start() + 1, each.end()))
    return found


def _references(doc: Doc, sheets: Sheets, id: str) -> Iterator[dict]:
    """Every reference to the table: in each table's formulas, the names and the charts."""
    for owner, found in sheets.tables():
        if isinstance(found, Draft):
            rows = stored.naming(sheets.document, found.base.grid, id, owner == id)
        else:
            rows = found.rows
        for row in rows:
            for col, cell in row.cells.items():
                for piece in formula_in(cell.get(FORMULA) or (), row.id, col):
                    if isinstance(piece, dict) and (piece.get("table") or owner) == id:
                        yield piece
    for entry in sheets.names().values():
        for piece in entry["pieces"]:
            if isinstance(piece, dict) and piece.get("table") == id:
                yield piece
    for child in blocks.body_of(doc).children:
        if isinstance(child, XmlElement) and child.tag == "chart":
            over = child.attributes.get("range")
            if isinstance(over, dict) and over.get("table") == id:
                yield over


def _shown_rows(
    laid: Laid | Draft, nodes: list[blocks.Cell]
) -> Iterator[tuple[str, dict, list[blocks.Cell]]]:
    """Each row in its order, with its cells as they are kept and those that hold text and no
    merged cell covers, the node of one that has it standing for it."""
    cols = laid.col_ids()
    hidden = covered(laid)
    noded: dict[str, dict[str, blocks.Cell]] = {}
    for cell in nodes:
        noded.setdefault(cell.row, {})[cell.col] = cell
    for row, held in held_rows(laid, laid.ids(0, laid.size - 1), cols):
        kept = held[2] if held is not None else {}
        own = noded.get(row, {})
        shown = []
        for col in cols:
            key = blocks.key_of(row, col)
            if key in hidden:
                continue
            if col in own:
                shown.append(own[col])
            elif TEXT in kept.get(col, ()):
                shown.append(blocks.light_cell(key, kept[col][TEXT]))
        yield row, kept, shown


def _empty(
    doc: Doc, sheets: Sheets, id: str, laid: Laid | Draft, nodes: list[blocks.Cell]
) -> dict[str, list[str]]:
    """The rows and columns that hold nothing, of each axis none where all do: no merged cell
    spans them, no formula is in them, and no reference points at them alone."""
    cols = laid.col_ids()
    held: set[str] = set()
    rows: list[str] = []
    for row, kept, shown in _shown_rows(laid, nodes):
        full = {cell.col for cell in shown if not _textual(cell) or cell.text.strip()}
        full |= {col for col, cell in kept.items() if FORMULA in cell}
        held |= full
        if not full:
            rows.append(row)
    merges = merged(laid)
    spanned = {line for each in merges for line in laid.ids(each.y, each.y + each.rows - 1)}
    held |= {col for each in merges for col in cols[each.x : each.x + each.cols]}
    gone = {
        "row": dict.fromkeys(row for row in rows if row not in spanned),
        "col": dict.fromkeys(col for col in cols if col not in held),
    }

    def between(part: str, first: str, last: str) -> list[str]:
        if part == "col":
            return cols[cols.index(first) : cols.index(last) + 1]
        at = laid.places([first, last])
        return laid.ids(at[first], at[last]) if at[first] <= at[last] else []

    if any(gone.values()):
        for piece in _references(doc, sheets, id):
            for part, lines in gone.items():
                if "to" not in piece and (line := piece.get("from", {}).get(part)) is not None:
                    lines.pop(line, None)
    if any(gone.values()):
        for piece in _references(doc, sheets, id):
            for part, lines in gone.items():
                first, last = piece.get("from", {}).get(part), piece.get("to", {}).get(part)
                if first in lines and last in lines:
                    span = between(part, first, last)
                    if span and all(line in lines for line in span):
                        for line in span:
                            del lines[line]
    return {
        axis: list(gone[part]) if len(gone[part]) < size else []
        for axis, part, size in (("rows", "row", laid.size), ("cols", "col", len(cols)))
    }


def clean(tab: Tab, target: dict, parameters: dict) -> Build:
    """The table's data cleaned: the whitespace around each cell's text and repeated within
    it gone, the numbers of its data kept as text made numbers, and the rows and columns that
    hold nothing taken out."""
    id = target["table"]
    locale = tab.document.locale
    laid, data, nodes = _found(tab, id)
    data_rows = {row: y for y, row in enumerate(data.rows)}
    candidates: dict[str, tuple[str, str]] = {}
    for row, kept, shown in _shown_rows(laid, nodes):
        y = data_rows.get(row)
        if y is None:
            continue
        for cell in shown:
            if data.kinds[cell.col][y] != "text" or FORMULA in kept.get(cell.col, ()):
                continue
            if _plain(cell) and (bare := _number(cell.text)) is not None:
                candidates[blocks.key_of(row, cell.col)] = (cell.text, bare)
    language = calculation.language(locale)
    numbers = {
        key: found
        for key, found in candidates.items()
        if isinstance(calculation.typed(found[1], language), float)
    }

    def build(doc: Doc, sheets: Sheets) -> list[dict]:
        now, element = table_in(doc, sheets, id)
        nodes = blocks.table_of(element, {}).cells
        empty = _empty(doc, sheets, id, now, nodes)
        gone = {"row": set(empty["rows"]), "col": set(empty["cols"])}
        texts: list[dict] = []
        values: list[dict] = []
        for row, _, shown in _shown_rows(now, nodes):
            if row in gone["row"]:
                continue
            for cell in shown:
                if cell.col in gone["col"] or not _textual(cell):
                    continue
                key = blocks.key_of(cell.row, cell.col)
                before, bare = numbers.get(key, (None, None))
                if bare is not None and cell.text == before and _plain(cell):
                    values.append({"row": cell.row, "col": cell.col, "value": bare})
                elif cell.light and (spans := _trimmed(cell.text)):
                    kept = cell.text
                    for start, end in reversed(spans):
                        kept = kept[:start] + kept[end:]
                    values.append({"row": cell.row, "col": cell.col, "value": kept})
                elif not cell.light:
                    texts += [
                        {
                            "op": "text",
                            "range": {"block": block.id, "from": start, "to": end},
                            "content": [],
                        }
                        for block in cell.blocks
                        for start, end in _trimmed(block.text)
                    ]
        built = [*texts, *([{"op": "cells", "table": id, "cells": values}] if values else [])]
        cols = now.col_ids()
        built += _taken_out(id, "rows", now.places(empty["rows"])) if empty["rows"] else []
        built += _taken_out(id, "cols", {col: cols.index(col) for col in empty["cols"]})
        if not built:
            raise Refused("clean", id)
        return built

    return build


def chart(tab: Tab, target: dict, parameters: dict) -> Build:
    """A column chart just after the table, over the cells given or else the whole table above
    its totals row, its series running down the columns unless the range is wider than tall,
    and its names and categories decided as Excel decides them on inserting a chart."""
    id = target["table"]

    def build(doc: Doc, sheets: Sheets) -> list[dict]:
        laid = table_in(doc, sheets, id)[0]
        cols = laid.col_ids()
        if "from" in target:
            ends = target["from"], target["to"]
            at = laid.places(end["row"] for end in ends)
            if any(end["row"] not in at or end["col"] not in cols for end in ends):
                raise Refused("changed", id)
            top, bottom = sorted(at[end["row"]] for end in ends)
            left, right = sorted(cols.index(end["col"]) for end in ends)
        else:
            totals = totals_row(sheets.document, laid)
            top, left, right = 0, 0, len(cols) - 1
            bottom = max(laid.place(totals) - 1, 0) if totals else laid.size - 1
        first, last = laid.ids(top, top)[0], laid.ids(bottom, bottom)[0]
        attrs = {
            "range": {
                "table": id,
                "from": {"row": first, "col": cols[left]},
                "to": {"row": last, "col": cols[right]},
            },
            "by": "rows" if right - left > bottom - top else "cols",
        }
        made: list[dict] = [{"type": "chart", "attrs": attrs}]
        children = blocks.body_of(doc).children
        last = children[len(children) - 1]
        if isinstance(last, XmlElement) and last.attributes.get("id") == id:
            made.append({"type": "paragraph"})
        return [{"op": "insert", "at": {"after": id}, "blocks": made}]

    return build
