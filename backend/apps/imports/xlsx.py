"""Spreadsheets as tabs, a sheet each. Each sheet of an xlsx file, as its XML gives it, becomes a
tab under its name holding a table of the same name, from A1 to the last cell it uses or a formula
points at, so that addresses, ROW() and implicit intersection stay as the file has them. Formulas
are kept in pieces by row and column id (D4), a range that runs past a sheet's last row or column
cut at its edge; the workbook's defined names become the document's, but for those into another
workbook, which go with its link. Plain text is kept in light cells, a cell with a look of its own
as a node in the marks the Word import writes. ods and xls files arrive made xlsx by LibreOffice.

What our engine computes is held to the value the file saved with each formula; the cells that
differ, the functions the registry does not have and what a table cannot hold are reported. A
sheet's charts follow its table, drawn over the cells their series refer to; a chart sheet, or a
sheet of charts and no cells, is a tab of its charts."""

import math
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import replace
from functools import partial
from itertools import batched
from pathlib import Path

from lxml import etree

from apps.content import calculation, fonts, grids, schema, styles
from apps.content.blocks import Block, Cell, Grid, Run, key_of, look_of, new_id
from apps.content.formulas import (
    NAME,
    QUOTED,
    End,
    Formulas,
    Part,
    Ref,
    column_name,
    place,
    quote_name,
)
from apps.content.grids import FORMAT, FORMULA, LOOK, TEXT
from apps.content.models import Grid as StoredGrid
from apps.content.models import GridRow
from apps.engine.parse import Error
from apps.engine.values import loaded, stored

from . import charts, colors, laying, sheetml, vba
from .laying import Ids
from .reading import Imported, Tab, TooManyCells
from .sheetml import MAIN, RELATIONSHIPS, Formatted, Sheet, Source, related, whole, worksheets

LARGEST = 1_000_000
NAMED = 20
_BLANK = {"formula": None, "shared": None, "kind": None, "value": None, "style": {}}
VOLATILE = {"NOW", "TODAY", "RAND", "RANDBETWEEN", "RANDARRAY"}
# Excel writes a reference into another workbook as [1]Sheet!A1, '[1]Sheet'!A1 or [1]!Name.
ELSEWHERE = re.compile(r"(?:'\[\d+\][^']*'|\[\d+\][\w.:]*)!")
ALIGNED = {"center", "right", "justify"}
DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
TABLE_SWITCHES = {
    "showFirstColumn": "firstColumn",
    "showLastColumn": "lastColumn",
    "showRowStripes": "rowBands",
    "showColumnStripes": "columnBands",
}


def read(path: Path, locale: str) -> Imported:
    """The workbook as a tab for each sheet, its cells typed as the locale types them."""
    return Workbook(Source(path, locale), locale).read()


def embedded(path: Path, locale: str, title: str) -> Imported | None:
    """One sheet of a workbook another file holds, read as a workbook of its own: a formula
    that reaches past the sheet, or into a defined name, keeps the value it saved."""
    source = Source(path, locale)
    index = next(
        (
            at
            for at, (name, _, _) in enumerate(source.sheets)
            if name.casefold() == title.casefold()
        ),
        None,
    )
    return None if index is None else Workbook(source, locale).read(index)


def shown(found: charts.Found, locale: str) -> tuple[Block, Block] | None:
    """A table of the values a chart last showed, its series down the columns under their
    names and its categories in the first column, and the chart over the whole of it: for a
    chart whose cells are in no workbook at hand."""
    series = found.series
    if not any(each.shown_values for each in series):
        return None
    language = calculation.language(locale)
    names = any(each.shown_name is not None for each in series)
    labels = next((each.shown_labels for each in series if each.shown_labels), [])
    length = max(len(labels), *(len(each.shown_values) for each in series))
    rows = [new_id() for _ in range(length + names)]
    cols = [new_id() for _ in range(len(series) + bool(labels))]
    texts, formats = {}, {}

    def put(row: int, col: int, text: str | None, code: str = "General") -> None:
        if text:
            key = key_of(rows[row], cols[col])
            texts[key] = text
            if code.lower() != "general":
                formats[key] = code

    for index, text in enumerate(labels):
        put(index + names, 0, text)
    for col, each in enumerate(series, bool(labels)):
        if names:
            put(0, col, each.shown_name)
        for index, value in enumerate(each.shown_values):
            code = each.formats[index] if index < len(each.formats) else "General"
            if value is not None:
                put(index + names, col, calculation.written(float(value), language), code)
    table = Block("table", grid=Grid(rows, cols, formats=formats, texts=texts))
    whole = charts.Area("", 1, 1, len(rows), len(cols))
    over = {
        "table": table.id,
        "from": {"row": rows[0], "col": cols[0]},
        "to": {"row": rows[-1], "col": cols[-1]},
    }
    return table, charts.chart(found, charts.Layout(whole, "cols", names, bool(labels)), over)


def _reaches_out(parts: list[Part], own: int, names: set[str]) -> bool:
    return any(
        part.sheet not in (None, own)
        if isinstance(part, Ref)
        else any(found[0].casefold() in names for found in NAME.finditer(part))
        for part in parts
    )


class Workbook:
    def __init__(self, source: Source, locale: str):
        self.source = source
        self.locale = locale
        self.language = calculation.language(locale)
        self.base = source.base
        self.scheme = source.scheme
        self.formats = source.formats
        self.lost: dict[str, int] = {}
        self.macros: list[dict] | None = None
        self.fonts: set[str] = (
            {name} if (name := (self.base.get("font") or {}).get("name")) else set()
        )

    def read(self, only: int | None = None) -> Imported:
        """The workbook's tabs; of the sheet `only` alone, as a workbook of its own, where one
        is given."""
        source = self.source
        titles = [name for name, _, _ in source.sheets]
        named = [
            entry
            for entry in source.names
            if only is None
            and not entry["name"].lower().startswith("_xlnm.")
            and not ELSEWHERE.search(QUOTED.sub("", entry["formula"]))
        ]
        formulas = Formulas(
            titles,
            {entry["name"].casefold() for entry in (source.names if only is not None else named)},
        )
        indexes = range(len(titles)) if only is None else [only]
        walks: dict[int, Iterator[int]] = {}
        sheets = []
        for at, index in enumerate(indexes):
            if source.large(index):
                if only is not None:
                    raise TooManyCells
                sheet, walks[at] = source.opened(index, at)
            else:
                sheet = source.sheet(index, at)
                if only is None and sheet.last_row * sheet.last_col > grids.MOST_CELLS:
                    sheet, walks[at] = source.opened(index, at)
            sheets.append(sheet)
        for sheet in sheets:
            if not sheet.streamed:
                self._ruled(sheet)
        parsed = self._parsed(sheets, formulas, only)
        names = [(entry, formulas.parts(entry["formula"])) for entry in named]
        for (index, _), parts in parsed.items():
            self._reach(sheets, parts, index)
        for _, parts in names:
            self._reach(sheets, parts, None)
        drawn = self._charts(sheets) if only is None else []
        for sheet in sheets:
            sheet.reach(1, 1)
        if only is not None and sheets[0].last_row * sheets[0].last_col > LARGEST:
            raise TooManyCells
        for sheet in sheets:
            sheet.rows = Ids(0 if sheet.streamed else sheet.last_row)
            sheet.cols = Ids(sheet.last_col)
        ids = [new_id() for _ in sheets]
        tables = [self._table(sheet, sheets, ids, parsed) for sheet in sheets]
        filled = {sheet.index for sheet in sheets if sheet.cells or sheet.streamed}
        saved = self._saved(sheets, ids, parsed)
        # The tables hold the cells now.
        for sheet in sheets:
            if not sheet.streamed:
                sheet.cells.clear()
        defined = {
            new_id(): {
                "name": entry["name"],
                "pieces": _pieces(parts, None, sheets, ids),
                **({"table": ids[entry["scope"]]} if entry["scope"] is not None else {}),
            }
            for entry, parts in names
        }
        if only is None:
            self._beyond()
        after: dict[str, list[Block]] = {}
        for host, found, layout, sheet in drawn:
            box = layout.box
            over = {
                "table": ids[sheet.index],
                "from": _point(End(box.top, box.left), sheet),
                "to": _point(End(box.bottom, box.right), sheet),
            }
            after.setdefault(host, []).append(charts.chart(found, layout, over))
        with zipfile.ZipFile(source.path) as archive:
            listed = [
                (name, kind, part)
                for name, kind, part, _ in sheetml.listed(archive)
                if only is None or part == source.sheets[only][2]
            ]
        parts = [part for _, kind, part in listed if kind == "worksheet"]
        held = {
            part: table
            for part, sheet, table in zip(parts, sheets, tables, strict=False)
            if sheet.index in filled
            or (sheet.last_row, sheet.last_col) != (1, 1)
            or part not in after
        }
        tabs = []
        for name, _, part in listed:
            shown = [*([held[part]] if part in held else []), *after.get(part, [])]
            if shown:
                tabs.append(Tab(name, [*shown, Block("paragraph")]))
        report = {
            "fonts": fonts.substituted(self.fonts),
            "lost": {key: count for key, count in sorted(self.lost.items()) if count},
            "accepted": 0,
            "functions": sorted(formulas.unknown),
            "cells": [],
            **({"macros": self.macros} if self.macros is not None else {}),
        }
        return Imported(
            tabs,
            None,
            {},
            self._theme(),
            styles.TEMPLATE[styles.STYLES],
            {},
            [],
            report,
            {},
            names=defined,
            saved=saved,
            rest=(
                partial(
                    self._rest,
                    [(sheets[at], walk) for at, walk in walks.items()],
                    sheets,
                    ids,
                    formulas,
                    report,
                )
                if walks
                else None
            ),
        )

    def _ruled(self, sheet: Sheet) -> None:
        self._count("spills", sheet.spills)
        for rule, count in sheet.rules.items():
            self._count(rule, count)

    def _rest(
        self,
        walks: list[tuple[Sheet, Iterator[int]]],
        sheets: list[Sheet],
        ids: list[str],
        formulas: Formulas,
        report: dict,
        out,
    ) -> dict:
        """Sends the large sheets' rows, those Excel's formulas name past a table's end too; the
        import's report as it ends and the tables whose rows were sent."""
        layings = {}
        for sheet, walk in walks:
            layings[sheet.index] = self._flowed(out, sheet, walk, sheets, ids, formulas)
        for sheet in sheets:
            laid = layings.get(sheet.index)
            if laid is None and (
                sheet.last_row > len(sheet.rows) or sheet.last_col > len(sheet.cols)
            ):
                laid = layings[sheet.index] = laying.Laying(
                    out, ids[sheet.index], sheet.rows, len(sheet.cols)
                )
            if laid is None:
                continue
            laid.col(sheet.last_col, partial(self._col, sheet))
            frozen = sheet.frozen and sheet.rows[min(sheet.frozen, sheet.last_row) - 1]
            laid.finish(sheet.last_row, (frozen or "") if sheet.streamed else "")
            if sheet.streamed:
                laid.merge(_merges(sheet))
        report["lost"] = {key: count for key, count in sorted(self.lost.items()) if count}
        report["fonts"] = fonts.substituted(self.fonts)
        report["functions"] = sorted(formulas.unknown)
        return {"report": report, "written": [ids[sheet.index] for sheet, _ in walks]}

    def _flowed(
        self,
        out,
        sheet: Sheet,
        walk: Iterator[int],
        sheets: list[Sheet],
        ids: list[str],
        formulas: Formulas,
    ) -> laying.Laying:
        """Sends a sheet's rows as they are read, each with the value the file saved for it."""
        laid = laying.Laying(out, ids[sheet.index], sheet.rows, len(sheet.cols))
        index, shared = sheet.index, {}
        col_looks: dict[int, dict | None] = {}

        def lined(col: int) -> dict | None:
            if col not in col_looks:
                col_looks[col] = self._col_look(sheet, col)
            return col_looks[col]

        for number in walk:
            sheet.reach(number, None)
            line = laying.Line(number)
            line.look = self._row_look(sheet, number)
            line.height = sheet.heights.get(number)
            line.hidden = number in sheet.hidden_rows
            places = sorted({col for _, col in (*sheet.cells, *sheet.formatted.cells)})
            for col in places:
                sheet.reach(number, col)
                laid.col(col, partial(self._col, sheet))
                cell = sheet.cells.get((number, col)) or _BLANK
                id, given = sheet.cols[col - 1], {}
                parts = (
                    self._parts(sheet, number, col, cell, formulas, shared, None)
                    if cell["formula"] or cell["shared"] is not None
                    else None
                )
                if parts is not None:
                    self._reach(sheets, parts, index)
                    given[FORMULA] = _pieces(parts, index, sheets, ids)
                    if entry := self._kept(sheet, number, col, cell, parts):
                        laid.compare(number, id, stored(entry[0]), entry[1])
                code = cell["style"].get("num_fmt", "general")
                format = None if code.lower() == "general" else code
                if format:
                    given[FORMAT] = format
                text, placed = self._placed(
                    sheet, (number, col), cell, bool(line.look or lined(col))
                )
                if placed is not None:
                    light = look_of(placed.blocks, placed.fill, placed.edges)
                    if light is None:
                        self._count("largeLinks")
                    else:
                        text, look = light
                        given[LOOK] = look
                if text:
                    given[TEXT] = text
                if cell["kind"] is not None:
                    value = Error(cell["value"]) if cell["kind"] == "error" else cell["value"]
                    line.values[id] = stored(value)
                    written = calculation.shown(value, format, self.locale)
                    if written != (text if parts is None else None) or format:
                        line.shown[id] = written
                if given:
                    line.cells[id] = given
            sheet.cells.clear()
            sheet.formatted.cells.clear()
            sheet.formatted.rows.clear()
            sheet.row_styles.clear()
            sheet.heights.clear()
            sheet.hidden_rows.clear()
            laid.add(line)
        self._ruled(sheet)
        self._count("largeLinks", len(sheet.links))
        for merge in sheet.merges:
            sheet.reach(merge["row"] + merge["height"] - 1, merge["column"] + merge["width"] - 1)
        return laid

    def _col(self, sheet: Sheet, col: int, laid: laying.Laying) -> dict:
        """A column a large sheet's rows reached, as its table keeps it."""
        width = next(
            (width for low, high, width in sheet.widths if low <= col <= high), sheet.default_width
        )
        look = laid.key_of(self._col_look(sheet, col))
        return (
            {"id": sheet.cols[col - 1], "width": round(width, 1)}
            | ({"look": look} if look is not None else {})
            | (
                {"hidden": True}
                if any(low <= col <= high for low, high, _ in sheet.hidden_cols)
                else {}
            )
        )

    def _row_look(self, sheet: Sheet, row: int) -> dict | None:
        formatted = sheet.formatted or Formatted()
        if row not in sheet.row_styles and row not in formatted.rows:
            return None
        return self._line_look(
            self.source.style(str(sheet.row_styles[row])) if row in sheet.row_styles else {},
            formatted.rows.get(row),
        )

    def _col_look(self, sheet: Sheet, col: int) -> dict | None:
        formatted = sheet.formatted or Formatted()
        found = next((xf for low, high, xf in sheet.col_styles if low <= col <= high), None)
        return self._line_look(
            self.source.style(str(found)) if found is not None else {},
            self._col_format(formatted, col),
        )

    def _parsed(
        self, sheets: list[Sheet], formulas: Formulas, only: int | None
    ) -> dict[tuple[int, tuple[int, int]], list[Part]]:
        """Each cell's formula as parts, a shared one moved from the cell that holds it. A
        formula with no cell left to hold it, or read alone and reaching past its sheet, keeps
        its value and is a formula no more."""
        parsed = {}
        for sheet in sheets:
            if sheet.streamed:
                continue
            shared: dict[str, tuple[int, int, list[Part]]] = {}
            for (row, col), cell in sheet.cells.items():
                parts = self._parts(sheet, row, col, cell, formulas, shared, only)
                if parts is not None:
                    parsed[sheet.index, (row, col)] = parts
        return parsed

    def _parts(
        self,
        sheet: Sheet,
        row: int,
        col: int,
        cell: dict,
        formulas: Formulas,
        shared: dict[str, tuple[int, int, list[Part]]],
        only: int | None,
    ) -> list[Part] | None:
        """The cell's formula as parts, none where it holds none, a shared one moved from the
        cell that holds it."""
        if cell["formula"]:
            text = sheetml.resolved(cell["formula"], self.source.tables, row)
            parts = formulas.parts(text)
            if cell["shared"] is not None:
                shared[cell["shared"]] = (row, col, parts)
        elif cell["shared"] is not None and cell["shared"] in shared:
            top, left, master = shared[cell["shared"]]
            parts = _moved(master, row - top, col - left)
        else:
            cell["shared"] = None
            return None
        if only is not None:
            if _reaches_out(parts, only, formulas.names):
                cell["formula"], cell["shared"] = None, None
                return None
            parts = [replace(part, sheet=None) if isinstance(part, Ref) else part for part in parts]
        cell["formula"] = cell["formula"] or True
        return parts

    def _saved(
        self,
        sheets: list[Sheet],
        ids: list[str],
        parsed: dict[tuple[int, tuple[int, int]], list[Part]],
    ) -> dict[str, dict[str, tuple[object, str | None]]]:
        """By table and cell, the value each formula's file saved with it and the address to
        report it by, none for those that change by themselves or read another workbook, whose
        value is neither ours to compute nor to hold against us."""
        saved: dict[str, dict[str, tuple[object, str | None]]] = {}
        for (index, (row, col)), parts in parsed.items():
            sheet = sheets[index]
            entry = self._kept(sheet, row, col, sheet.cells[row, col], parts)
            if entry is not None:
                key = key_of(sheet.rows[row - 1], sheet.cols[col - 1])
                saved.setdefault(ids[index], {})[key] = entry
        return saved

    @staticmethod
    def _kept(
        sheet: Sheet, row: int, col: int, cell: dict, parts: list[Part]
    ) -> tuple[object, str | None] | None:
        """The value the file saved with the formula and the address to report it by."""
        if cell["kind"] is None or _volatile(parts):
            return None
        address = None
        if not any(isinstance(part, str) and ELSEWHERE.search(part) for part in parts):
            address = f"{quote_name(sheet.title)}!{column_name(col)}{row}"
        return Error(cell["value"]) if cell["kind"] == "error" else cell["value"], address

    def _theme(self) -> dict[str, str]:
        """Ours, its text in the workbook's font or the stand-in we have for it."""
        theme = dict(styles.TEMPLATE[styles.THEME])
        if (name := (self.base.get("font") or {}).get("name")) and (
            shown := fonts.substitute(name)
        ):
            theme["text"] = shown
        return theme

    def _count(self, key: str, count: int = 1) -> None:
        self.lost[key] = self.lost.get(key, 0) + count

    def _charts(self, sheets: list[Sheet]) -> list[tuple[str, charts.Found, charts.Layout, Sheet]]:
        """Each chart, by the part of the sheet showing it, with how it reads them and the sheet
        its cells are in, reached to its range."""
        titled = {sheet.title.casefold(): sheet for sheet in sheets}
        found = []
        with zipfile.ZipFile(self.source.path) as archive:
            parts = set(archive.namelist())
            self._count(
                "charts",
                sum(1 for part in parts if re.fullmatch(r"xl/charts/chartEx\d+\.xml", part)),
            )
            hosts = [*worksheets(archive)[: len(sheets)], *worksheets(archive, "chartsheet")]
            for part in hosts:
                for drawn in _drawn(archive, part, parts):
                    chart = charts.parse(self.source.held(whole(archive, drawn)))
                    if chart is None:
                        continue
                    layout = chart.kind and charts.layout(chart.series)
                    sheet = layout and titled.get(layout.box.sheet.casefold())
                    if not sheet:
                        self._count("charts")
                        continue
                    sheet.reach(layout.box.top, layout.box.left)
                    self._count("chartDetails", int(chart.details or not layout.neat))
                    found.append((part, chart, layout, sheet))
        return found

    @staticmethod
    def _reach(sheets: list[Sheet], parts: list[Part], own: int | None) -> None:
        for part in parts:
            if isinstance(part, Ref):
                sheet = part.sheet if part.sheet is not None else own
                if sheet is not None:
                    sheets[sheet].reach(part.start.row, part.start.col)

    # Cells

    def _table(
        self,
        sheet: Sheet,
        sheets: list[Sheet],
        ids: list[str],
        parsed: dict[tuple[int, tuple[int, int]], list[Part]],
    ) -> Block:
        index = sheet.index
        merged = {
            (merge["row"], merge["column"]): (
                merge["row"] + merge["height"] - 1,
                merge["column"] + merge["width"] - 1,
            )
            for merge in sheet.merges
        }
        formulas, formats, texts, values, cells = {}, {}, {}, {}, []
        formatted = sheet.formatted or Formatted()
        row_looks = {
            sheet.rows[row - 1]: look
            for row in sorted({*sheet.row_styles, *formatted.rows})
            if row <= len(sheet.rows)
            and (
                look := self._line_look(
                    self.source.style(str(sheet.row_styles[row]))
                    if row in sheet.row_styles
                    else {},
                    formatted.rows.get(row),
                )
            )
        }
        col_looks = {
            id: look for col, id in enumerate(sheet.cols, 1) if (look := self._col_look(sheet, col))
        }
        for (row, col), cell in () if sheet.streamed else sorted(sheet.cells.items()):
            key = key_of(sheet.rows[row - 1], sheet.cols[col - 1])
            if cell["formula"]:
                formulas[key] = _pieces(parsed[index, (row, col)], index, sheets, ids)
                if cell["kind"] is not None:
                    values[key] = self._showing(cell, cell["style"])
            if cell["style"].get("num_fmt", "general").lower() != "general":
                formats[key] = cell["style"]["num_fmt"]
            last = merged.pop((row, col), None)
            to = last and key_of(sheet.rows[last[0] - 1], sheet.cols[last[1] - 1])
            lines = row_looks.get(sheet.rows[row - 1]) or col_looks.get(sheet.cols[col - 1])
            text, placed = self._placed(sheet, (row, col), cell, bool(lines), to)
            if placed is not None:
                cells.append(placed)
            elif text is not None:
                texts[key] = text
        for (row, col), last in merged.items():
            to = key_of(sheet.rows[last[0] - 1], sheet.cols[last[1] - 1])
            fill, edges = self._own(formatted.cells.pop((row, col), None))
            cells.append(
                Cell(
                    sheet.rows[row - 1],
                    sheet.cols[col - 1],
                    [Block("paragraph")],
                    to,
                    fill=fill,
                    edges=edges,
                )
            )
        for (row, col), xf in () if sheet.streamed else sorted(formatted.cells.items()):
            if row <= len(sheet.rows) and col <= len(sheet.cols):
                fill, edges = self._own(xf)
                cells.append(
                    Cell(
                        sheet.rows[row - 1],
                        sheet.cols[col - 1],
                        [Block("paragraph")],
                        fill=fill,
                        edges=edges,
                    )
                )
        self._count("hiddenSheets", int(sheet.hidden))
        widths = [
            next(
                (width for low, high, width in sheet.widths if low <= col <= high),
                sheet.default_width,
            )
            for col in range(1, sheet.last_col + 1)
        ]
        attrs = {
            "widths": {col: round(width, 1) for col, width in zip(sheet.cols, widths, strict=True)},
            "sized": True,
        }
        heights = {
            sheet.rows[row - 1]: height
            for row, height in sheet.heights.items()
            if row <= sheet.last_row
        }
        if heights:
            attrs["heights"] = heights
        hidden = {
            "rows": [id for y, id in enumerate(sheet.rows, 1) if y in sheet.hidden_rows],
            "cols": [
                id
                for x, id in enumerate(sheet.cols, 1)
                if any(low <= x <= high for low, high, _ in sheet.hidden_cols)
            ],
        }
        if hidden := {axis: ids for axis, ids in hidden.items() if ids}:
            attrs["hidden"] = hidden
        if schema.holds("tableName", sheet.title):
            attrs["name"] = sheet.title
        if frozen := min(sheet.frozen, len(sheet.rows)):
            attrs["frozen"] = sheet.rows[frozen - 1]
        lined = (
            sheet.streamed
            or any(cell.edges for cell in cells)
            or any(look.get("edges") for look in (*row_looks.values(), *col_looks.values()))
        )
        if designs := self._designs(sheet, lined):
            attrs["designs"] = designs
        grid = Grid(
            list(sheet.rows),
            list(sheet.cols),
            formulas,
            formats,
            values,
            row_looks=row_looks,
            col_looks=col_looks,
            texts=texts,
        )
        return Block("table", ids[index], attrs, grid=grid, cells=cells)

    def _placed(
        self,
        sheet: Sheet,
        at: tuple[int, int],
        cell: dict,
        lined: bool,
        to: str | None = None,
    ) -> tuple[str | None, Cell | None]:
        """The text a cell holds and, where it has a look of its own, the cell that shows it."""
        row, col = at
        style = cell["style"]
        marks, attrs = self._look(style)
        fill, edges = self._own(sheet.formatted.cells.pop(at, None))
        link = sheet.links.get(at)
        if link and not cell["formula"]:
            if link.get("type") == "External" and link.get("target"):
                marks = {
                    name: value
                    for name, value in marks.items()
                    if name not in ("underline", "color")
                }
                marks["link"] = {"href": link["target"]}
            else:
                self._count("internalLinks")
        text = None if cell["formula"] or cell["value"] is None else self._typed(cell)
        if not marks and not attrs and not fill and not edges and not to and not lined:
            return text, None
        if text is None:
            block = Block("paragraph", attrs={**attrs, **({"endMarks": marks} if marks else {})})
        else:
            block = Block("paragraph", attrs=attrs, runs=[Run(text, marks)])
        return text, Cell(
            sheet.rows[row - 1], sheet.cols[col - 1], [block], to, fill=fill, edges=edges
        )

    def _look(self, style: dict) -> tuple[dict, dict]:
        """The marks of a cell's font where it is not the workbook's, as the Word import
        writes them, and its paragraph's alignment."""
        font, plain = style.get("font") or {}, self.base.get("font") or {}
        marks: dict[str, dict] = {}
        for mark, key in (("strong", "b"), ("em", "i"), ("underline", "u"), ("strike", "strike")):
            if font.get(key) and not plain.get(key):
                marks[mark] = {}
        color = font.get("color")
        if color != plain.get("color"):
            if exact := colors.text_color(color):
                marks["color"] = {"color": exact}
        name = font.get("name")
        if name and name != plain.get("name"):
            marks["font"] = {"family": name}
            self.fonts.add(name)
        size = font.get("sz")
        if size is not None and size != plain.get("sz") and 1 <= size <= 400:
            marks["size"] = {"pt": size}
        align = (style.get("alignment") or {}).get("horizontal")
        return marks, ({"align": align} if align in ALIGNED else {})

    def _line_look(self, style: dict, xf: int | None) -> dict | None:
        """The look the style gives the cells of a row or a column, none where it gives the
        workbook's."""
        marks, attrs = self._look(style)
        fill, edges = self._own(xf)
        return {
            **({"marks": marks} if marks else {}),
            **({"attrs": attrs} if attrs else {}),
            **({"fill": fill} if fill else {}),
            **({"edges": edges} if edges else {}),
        } or None

    @staticmethod
    def _col_format(formatted: Formatted, col: int) -> int | None:
        return next((xf for low, high, xf in formatted.cols if low <= col <= high), None)

    def _own(self, xf: int | None) -> tuple[str | None, dict | None]:
        """The fill and the edges a cell format gives a cell over its table's design."""
        fill, edges, lost = self.formats.look(xf)
        self._count("tableStyles", lost)
        return fill, edges

    def _designs(self, sheet: Sheet, lined: bool) -> list[dict]:
        """The designs of the sheet's Excel tables, each over the cells its range takes; where its
        cells keep lines of their own, first Excel's rules over the whole sheet, drawing nothing,
        for those lines to meet as Excel's do."""
        found = [{"rules": "excel"}] if lined else []
        with zipfile.ZipFile(self.source.path) as archive:
            parts = set(archive.namelist())
            for _, part in related(archive, sheet.part, "table", parts):
                table = whole(archive, part)
                info = table.find(f"{MAIN}tableStyleInfo")
                ends = [place(each) for each in (table.get("ref") or "").split(":")]
                if info is None or not info.get("name") or None in ends or len(ends) != 2:
                    continue
                design, lost = self.formats.design(info.get("name"))
                self._count("tableStyles", lost + (design is None))
                (top, left), (bottom, right) = ends
                if design is None or (
                    not sheet.streamed and (bottom > len(sheet.rows) or right > len(sheet.cols))
                ):
                    continue
                on = {
                    "header": table.get("headerRowCount", "1") != "0",
                    "totals": table.get("totalsRowCount", "0") != "0",
                    **{
                        ours: info.get(theirs) in ("1", "true")
                        for theirs, ours in TABLE_SWITCHES.items()
                    },
                }
                design["on"] = {name: True for name, value in on.items() if value}
                design["area"] = {
                    "from": key_of(sheet.rows[top - 1], sheet.cols[left - 1]),
                    "to": key_of(sheet.rows[bottom - 1], sheet.cols[right - 1]),
                }
                found.append(design)
        return found

    def _showing(self, cell: dict, style: dict) -> dict:
        """What a formula's cell shows of the value its file saved."""
        value = Error(cell["value"]) if cell["kind"] == "error" else cell["value"]
        code = style.get("num_fmt")
        shown = calculation.shown(value, None if code == "General" else code, self.locale)
        return {"text": shown, "kind": cell["kind"]}

    def _typed(self, cell: dict) -> str:
        """The text of a value as the locale types it, read back as the same value."""
        value = cell["value"]
        return calculation.written(
            Error(value) if cell["kind"] == "error" else value, self.language
        )

    def _beyond(self) -> None:
        """What the file holds beyond its cells, counted as lost."""
        with zipfile.ZipFile(self.source.path) as archive:
            parts = archive.namelist()
            counted = {
                "sheetImages": r"xl/media/.+",
                "pivots": r"xl/pivotTables/.+\.xml",
                "externalLinks": r"xl/externalLinks/externalLink\d+\.xml",
                "macros": r"xl/vbaProject\.bin",
            }
            for key, pattern in counted.items():
                self._count(key, sum(1 for part in parts if re.fullmatch(pattern, part)))
            if "xl/vbaProject.bin" in parts:
                self.macros = vba.source(self.source.blob(archive, "xl/vbaProject.bin"))
            comments = 0
            for part in parts:
                if re.fullmatch(r"xl/(?:comments/)?comments?\d*\.xml", part):
                    comments += _elements(archive, part, "comment")
            self._count("cellComments", comments)


def _merges(sheet: Sheet) -> list[tuple[str, str, str]]:
    return [
        (
            sheet.rows[merge["row"] - 1],
            sheet.cols[merge["column"] - 1],
            key_of(
                sheet.rows[merge["row"] + merge["height"] - 2],
                sheet.cols[merge["column"] + merge["width"] - 2],
            ),
        )
        for merge in sheet.merges
    ]


def _pieces(parts: list[Part], own: int | None, sheets: list[Sheet], ids: list[str]) -> list:
    """The parts as a table keeps a formula: each reference by the ids of its rows and
    columns, with the table it is in where that is not the formula's own; one in a name
    that names no sheet stays text, as it refers to wherever the name is used."""
    pieces: list = []
    for part in parts:
        piece: str | dict = part if isinstance(part, str) else part.text
        sheet = part.sheet if isinstance(part, Ref) and part.sheet is not None else own
        if isinstance(part, Ref) and sheet is not None:
            piece = {
                **({"table": ids[sheet]} if sheet != own else {}),
                "from": _point(part.start, sheets[sheet]),
                **({"to": _point(part.end, sheets[sheet])} if part.end else {}),
            }
        if isinstance(piece, str) and pieces and isinstance(pieces[-1], str):
            pieces[-1] += piece
        else:
            pieces.append(piece)
    return pieces


def _point(end: End, sheet: Sheet) -> dict:
    """An end by id, cut at the sheet's last row and column."""
    point: dict = {}
    if end.row is not None:
        point["row"] = sheet.rows[min(end.row, sheet.last_row) - 1]
        if end.abs_row:
            point["absRow"] = True
    if end.col is not None:
        point["col"] = sheet.cols[min(end.col, sheet.last_col) - 1]
        if end.abs_col:
            point["absCol"] = True
    return point


class _Tagged:
    """How many elements of a tag a part holds, counted as a parser passes, keeping none."""

    def __init__(self, tag: str):
        self.tag = tag
        self.count = 0

    def start(self, tag, attrib, nsmap=None) -> None:
        self.count += tag == self.tag

    def end(self, tag) -> None:
        pass

    def data(self, text) -> None:
        pass

    def close(self) -> None:
        pass


def _elements(archive: zipfile.ZipFile, part: str, tag: str) -> int:
    tagged = _Tagged(f"{MAIN}{tag}")
    parser = etree.XMLParser(target=tagged, resolve_entities=False, no_network=True)
    with archive.open(part) as source:
        while chunk := source.read(1 << 20):
            parser.feed(chunk)
    return tagged.count


def _drawn(archive: zipfile.ZipFile, part: str, parts: set[str]) -> list[str]:
    """The chart parts a sheet's drawing shows, top to bottom and left to right."""
    found = []
    for _, drawing in related(archive, part, "drawing", parts):
        targets = dict(related(archive, drawing, "chart", parts))
        for anchor in whole(archive, drawing):
            chart = anchor.find(f".//{charts.C}chart")
            target = chart is not None and targets.get(chart.get(f"{RELATIONSHIPS}id"))
            if target:
                start = anchor.find(f"{DRAWING}from")
                place = (
                    (
                        int(start.findtext(f"{DRAWING}row", "0")),
                        int(start.findtext(f"{DRAWING}col", "0")),
                    )
                    if start is not None
                    else (0, 0)
                )
                found.append((place, target))
    return [target for _, target in sorted(found, key=lambda each: each[0])]


def _volatile(parts: list[Part]) -> bool:
    return any(
        isinstance(part, str) and any(re.search(rf"(?<![\w.]){name}\(", part) for name in VOLATILE)
        for part in parts
    )


def _moved(parts: list[Part], rows: int, cols: int) -> list[Part]:
    """A shared formula's parts for a cell so many rows and columns from the one holding it."""
    return [
        (
            replace(
                part,
                start=_shifted(part.start, rows, cols),
                end=part.end and _shifted(part.end, rows, cols),
            )
            if isinstance(part, Ref)
            else part
        )
        for part in parts
    ]


def _shifted(end: End, rows: int, cols: int) -> End:
    return replace(
        end,
        row=end.row if end.row is None or end.abs_row else max(end.row + rows, 1),
        col=end.col if end.col is None or end.abs_col else max(end.col + cols, 1),
    )


def _same(ours, theirs) -> bool:
    """Whether what a cell holds is the file's value: a number at Excel's fifteen digits."""
    if ours is None:
        ours = ""
    if isinstance(ours, bool) or isinstance(theirs, bool):
        return ours is theirs
    if isinstance(ours, float | int) and isinstance(theirs, float | int):
        return math.isclose(ours, theirs, rel_tol=0, abs_tol=0) or (
            f"{float(ours):.15g}" == f"{float(theirs):.15g}"
        )
    return ours == theirs


def compared(document, imported: Imported) -> None:
    """Holds each formula's value, computed by now, to the one the file saved with it. A cell
    that differs, or reads another workbook, keeps the file's value until what it reads changes;
    the cells that differ are counted and the first of them named in the report."""
    report, locale = imported.report, document.locale
    differing = _Differing()
    for table, saved in imported.saved.items():
        grid = StoredGrid.objects.filter(document=document, table=table).first()
        if grid is None:
            continue
        by_row: dict[str, list] = defaultdict(list)
        for key, (value, address) in saved.items():
            row, _, col = key.partition(":")
            by_row[row].append((col, stored(value), address))
        for ids in batched(by_row, 2000, strict=False):
            _held_to(grid.pk, {id: by_row[id] for id in ids}, locale, differing)
    if imported.rest is not None:
        for grid, rows in laying.saved():
            _held_to(grid, rows, locale, differing)
        laying.end()
    if differing.count:
        report["lost"] = {**report["lost"], "values": differing.count}
        report["cells"] = sorted(differing.names)[:NAMED]
    document.imported = report
    document.save(update_fields=["imported"])


class _Differing:
    """How many cells differ from the file, and the addresses of the first of them."""

    def __init__(self):
        self.count = 0
        self.names: list[str] = []

    def add(self, address: str) -> None:
        self.count += 1
        self.names.append(address)
        if len(self.names) > 100 * NAMED:
            self.names = sorted(self.names)[:NAMED]


def _held_to(grid: int, rows: dict[str, list], locale: str, differing: _Differing) -> None:
    """Puts the file's value back in each of the rows' cells it differs from."""
    changed = []
    for held in GridRow.objects.filter(grid_id=grid, row__in=rows).only("row", "values"):
        touched = False
        for col, theirs, address in rows[held.row]:
            if _same(held.values.get(col), theirs):
                continue
            if address:
                differing.add(address)
            format = (held.cells.get(col) or {}).get("format")
            held.values[col] = theirs
            held.shown[col] = calculation.shown(loaded(theirs), format, locale)
            touched = True
        if touched:
            changed.append(held)
    if changed:
        GridRow.objects.bulk_update(changed, ["values", "shown"], batch_size=500)
