"""A document's tables as an Excel workbook, written row by row out of Postgres as they stand
calculated: a sheet each, in reading order through the tabs, a table past Excel's last row going
on over further sheets, with their typed values, formulas, number formats and defined names, the
widths, heights, merged cells, links and fonts they show, their designs (D30) as Excel tables where
Excel's own rules draw them and cell by cell where not, and each tab's charts on its sheet: beside
their table where their tab holds it, else beside the tab's first, and a tab of charts alone a
sheet of its own under its title. The text around the tables goes to the Word file."""

import io
import json
import logging
import math
import posixpath
import re
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from itertools import accumulate
from typing import IO
from xml.sax.saxutils import escape, quoteattr

from lxml import etree
from pycrdt import Doc, XmlElement

from apps.content import (
    blocks,
    compute,
    designs,
    fonts,
    grids,
    names,
    pages,
    palette,
    rows,
    styles,
)
from apps.content import charts as drawn
from apps.content.blocks import Block, Cell, Run
from apps.content.formulas import column_name
from apps.content.grids import FORMAT, FORMULA, LOOK, MOST_CELLS, TEXT
from apps.content.models import Grid, GridRow
from apps.documents.models import Node
from apps.engine.registry import FUNCTIONS
from apps.imports import excel
from apps.imports.xlsx import TABLE_SWITCHES
from apps.versions.history import state_of

from . import charts, office
from .package import CONTENT_TYPES, PACKAGE, TYPES, rels_of

log = logging.getLogger(__name__)

EXCEL_ROWS = 1_048_576
LONGEST_TEXT = 32_767
LONGEST_FORMULA = 8_192
DEFAULT_WIDTH = 9.140625
# Excel's character of the default font is 7 pixels wide at 96 dots per inch.
CHARACTER_CM = 7 / 96 * 2.54
# Excel fits a row of no height of its own to the font, never less than so many times its size.
ROW_EM = 1.25
EMU_PER_POINT = 12_700
TOGGLES = {"strong": "b", "em": "i", "underline": "u", "strike": "strike"}
ALIGNED = {"center", "right", "justify"}
VERTICAL = {"top", "center", "bottom", "justify", "distributed"}
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
WORKSHEET = f"{charts.R}/worksheet"
DRAWING = f"{charts.R}/drawing"
CHART = f"{charts.R}/chart"
LINK = f"{charts.R}/hyperlink"
STYLES = f"{charts.R}/styles"
THEME = f"{charts.R}/theme"
DOCUMENT = f"{charts.R}/officeDocument"
SPREADSHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml"
WORKBOOK_TYPE = f"{SPREADSHEET}.sheet.main+xml"
WORKSHEET_TYPE = f"{SPREADSHEET}.worksheet+xml"
STYLES_TYPE = f"{SPREADSHEET}.styles+xml"
THEME_TYPE = "application/vnd.openxmlformats-officedocument.theme+xml"
DRAWING_TYPE = "application/vnd.openxmlformats-officedocument.drawing+xml"
CHART_TYPE = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
TABLE = f"{charts.R}/table"
TABLE_TYPE = f"{SPREADSHEET}.table+xml"
ELEMENTS = {part: type for type, part in excel.PARTS.items()}
STRIPES = {place: type for type, place in excel.STRIPES.items()}
EXCEL = designs.TABLES["rules"]["excel"]
# CT_Border's sequence, by the sides of a design.
BORDER = {
    "left": "left",
    "right": "right",
    "top": "top",
    "bottom": "bottom",
    "insideV": "vertical",
    "insideH": "horizontal",
}
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
# Excel's escape for what XML cannot hold, and text that would read as one kept as it is.
UNWRITABLE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\ud800-\\udfff\\ufffe\\uffff]")
ESCAPE_LIKE = re.compile(r"_x[0-9A-Fa-f]{4}_")
QUOTED = re.compile(r"\"(?:[^\"]|\"\")*\"|'(?:[^']|'')*'")
FUTURE = sorted((name for name, each in FUNCTIONS.items() if each.stored != name), key=len)
STORED = re.compile(
    r"\"(?:[^\"]|\"\")*\"|'(?:[^']|'')*'|(?<![\w.])("
    + "|".join(re.escape(name) for name in reversed(FUTURE))
    + r")(?=\()"
)
BEYOND = re.compile(r"\$?[A-Z]{1,3}\$?(\d{7,})")
# The colours are Office's: a preset of Excel's is only itself in the scheme Excel draws it in.
OFFICE = (
    ("dk1", "000000"),
    ("lt1", "FFFFFF"),
    ("dk2", "44546A"),
    ("lt2", "E7E6E6"),
    ("accent1", "4472C4"),
    ("accent2", "ED7D31"),
    ("accent3", "A5A5A5"),
    ("accent4", "FFC000"),
    ("accent5", "5B9BD5"),
    ("accent6", "70AD47"),
    ("hlink", "0563C1"),
    ("folHlink", "954F72"),
)
THEME_XML = (
    XML + f'<a:theme xmlns:a="{charts.A}" name="Office Theme"><a:themeElements>'
    '<a:clrScheme name="Office">'
    + "".join(f'<a:{tag}><a:srgbClr val="{color}"/></a:{tag}>' for tag, color in OFFICE)
    + '</a:clrScheme><a:fontScheme name="Office">'
    '<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/>'
    '</a:majorFont><a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/>'
    '<a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
    + "</a:fillStyleLst><a:lnStyleLst>"
    + "".join(
        f'<a:ln w="{width}"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
        for width in (6350, 12700, 19050)
    )
    + "</a:lnStyleLst><a:effectStyleLst>"
    + "<a:effectStyle><a:effectLst/></a:effectStyle>" * 3
    + "</a:effectStyleLst><a:bgFillStyleLst>"
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
    + "</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>"
).encode()


class Empty(Exception):
    """The document has no table to make a sheet of."""


def doc_of(room) -> Doc:
    doc = Doc()
    doc.apply_update(state_of(room))
    return doc


@dataclass(frozen=True)
class Computed:
    """The document's tables as they stand calculated and laid out: each table's block by its
    id and its grid's key, the sheets in order, by table or, a tab of charts alone, by tab, their
    titles, the width of each one's tab's text and the charts it shows in the order of the text,
    the font of the document's text and the defined names."""

    document: Node
    tables: dict[str, Block]
    keys: dict[str, int]
    sheets: dict[str, compute.Sheet]
    titles: dict[str, str]
    across: dict[str, float]
    charted: dict[str, list[dict]]
    font: str
    size: float
    defined: list[compute.Name]

    def sheet(self, table: str) -> charts.Sheet | None:
        if table not in self.tables:
            return None
        found = self.sheets[table]
        texts = {
            blocks.key_of(cell.row, cell.col): cell.text
            for cell in self.tables[table].cells
            if not cell.light
        }
        return charts.Sheet(
            self.document,
            table,
            self.keys[table],
            self.titles[table],
            found.rows,
            found.cols,
            texts,
        )

    def written(self) -> bytes:
        found = io.BytesIO()
        _write(self, found)
        return found.getvalue()


def computed(document: Node) -> Computed:
    own = doc_of(document.room)
    tables: dict[str, Block] = {}
    read = []
    for tab in document.tabs_in_order():
        doc = doc_of(tab.room)
        held = grids.placing_of_tab(tab) | grids.small_of_tab(tab)
        found = compute.tables_in(doc, held)
        page = pages.setup(own, str(tab.pk))
        tables |= found
        read.append((tab, found, page["width"] - page["left"] - page["right"], _charts_in(doc)))
    if not tables:
        raise Empty
    sheets: dict[str, compute.Sheet] = {}
    across: dict[str, float] = {}
    charted: dict[str, list[dict]] = {}
    for tab, found, width, shown in read:
        for id, table in found.items():
            grid = table.grid or blocks.Grid([], [])
            sheets[id] = compute.Sheet(
                grid.rows, grid.cols, compute.name_of(table) or tab.title or None
            )
            across[id] = width
        for attrs in shown:
            chart = drawn.chart_of(attrs)
            if chart is None or chart.table not in tables:
                continue
            host = chart.table if chart.table in found else next(iter(found), str(tab.pk))
            if host not in sheets:
                sheets[host] = compute.Sheet([], [], tab.title or None)
                across[host] = width
            charted.setdefault(host, []).append(attrs)
    defined = [
        name
        for name in compute.names_in(names.of_document(document))
        if name.table is None or name.table in tables
    ]
    theme, looks = styles.read(own)
    text = looks["text"]
    keys = dict(Grid.objects.filter(document=document).values_list("table", "pk"))
    return Computed(
        document,
        tables,
        keys,
        sheets,
        compute.titles_of(sheets),
        across,
        charted,
        styles.family(theme, text["font"]),
        text["size"],
        defined,
    )


def workbook(document: Node) -> IO[bytes]:
    """The workbook, in a file of its own: a long table's does not fit in memory."""
    book = computed(document)
    found = tempfile.TemporaryFile()
    _write(book, found)
    found.seek(0)
    return found


def _charts_in(doc: Doc) -> list[dict]:
    return [
        dict(element.attributes)
        for element in blocks.body_of(doc).children
        if isinstance(element, XmlElement) and element.tag == drawn.TAG
    ]


def _draws(look: designs.Cell) -> bool:
    return bool(
        look.fill not in (None, designs.NONE)
        or look.marks
        or look.align
        or look.valign
        or any(look.edges.values())
    )


def _listed(book: Computed, id: str, table: Block) -> list[tuple[dict, tuple, list[str]]]:
    """The designs of Excel's rules the sheet keeps as Excel tables, with their ranges from 1
    and their columns' names: each on the sheet's first page that merges no cell, overlaps no
    other, has a row beside its header and totals and, with a header, its columns named by
    distinct text there."""
    grid = table.grid or blocks.Grid([], [])
    taken = [
        (each.y, each.x, each.y + each.rows - 1, each.x + each.cols - 1)
        for each in blocks.placed(table)
        if each.rows > 1 or each.cols > 1
    ]
    found = []
    for design in table.attrs.get("designs") or []:
        drawing = design["rules"] == "excel" and (design.get("name") or design.get("parts"))
        bounds = office.area(design, grid) if drawing else None
        if bounds is None or bounds[2] >= EXCEL_ROWS:
            continue
        top, left, bottom, right = bounds
        on = design.get("on") or {}
        if bottom - top < bool(on.get("header")) + bool(on.get("totals")) or any(
            _overlap(bounds, other) for other in taken
        ):
            continue
        titles = _titled(book, id, grid, bounds) if on.get("header") else None
        if titles is None and on.get("header"):
            continue
        titles = titles or [f"Column{x - left + 1}" for x in range(left, right + 1)]
        if len({title.casefold() for title in titles}) < len(titles):
            continue
        taken.append(bounds)
        found.append((design, tuple(at + 1 for at in bounds), titles))
    return found


def _titled(book: Computed, id: str, grid, bounds: tuple) -> list[str] | None:
    """The text of the columns of a design's first row, none where one of them holds no plain
    text."""
    top, left, _, right = bounds
    row = next(rows.parts(book.document, book.keys[id], {grid.rows[top]}))[0][1]
    titles = []
    for col in grid.cols[left : right + 1]:
        text = row.values.get(col)
        if FORMULA in (row.cells.get(col) or {}) or not isinstance(text, str):
            return None
        if not text.strip() or "\n" in text:
            return None
        titles.append(text)
    return titles


def _overlap(one: tuple, other: tuple) -> bool:
    top, left, bottom, right = one
    return top <= other[2] and other[0] <= bottom and left <= other[3] and other[1] <= right


def _styled(base: dict, marks: dict[str, dict], look: dict) -> dict:
    """The font of the base and the marks, the look's fill or else the one they highlight, the
    look's edges and the alignment of its attributes: what a cell, a row or a column shows."""
    fill = office.solid("highlight", look.get("fill")) or palette.highlight(
        (marks.get("highlight") or {}).get("color")
    )
    align = (look.get("attrs") or {}).get("align")
    alignment = {
        **({"horizontal": align} if align in ALIGNED else {}),
        **({"vertical": look["valign"]} if look.get("valign") in VERTICAL else {}),
        **({"wrap_text": True} if look.get("wrapped") else {}),
    }
    found: dict = {"font": {**base["font"], **_font(marks)}}
    if fill:
        found["fill"] = {"color": f"#{fill}"}
    if edges := look.get("edges"):
        found["border"] = {
            side: _border(line)
            for side, line in edges.items()
            if side in ("top", "bottom", "left", "right") and designs.drawn(line)
        }
    return found | ({"alignment": alignment} if alignment else {})


def _border(edge: dict) -> dict:
    """An edge as a cell's border: the kind of Excel's line nearest it, in its colour."""
    color = office.solid("text", edge.get("color"))
    kind = EXCEL["kinds"][designs.kind_of(EXCEL, edge)]["name"]
    return {"style": kind, **({"color": f"#{color}"} if color else {})}


def _look(cell: Cell) -> tuple[dict[str, dict], str | None]:
    """The marks all of the cell's text carries, or an empty cell keeps at its end, and the
    alignment of its first paragraph."""
    runs = [run for block in cell.blocks for run in block.runs if isinstance(run, Run) and run.text]
    first = cell.blocks[0].attrs if cell.blocks else {}
    if not runs:
        kept = first.get("endMarks")
        return (kept if isinstance(kept, dict) else {}), first.get("align")
    shared = dict(runs[0].marks)
    for run in runs[1:]:
        shared = {name: value for name, value in shared.items() if run.marks.get(name) == value}
    return shared, first.get("align")


def _font(marks: dict[str, dict]) -> dict:
    font: dict = {key: True for mark, key in TOGGLES.items() if mark in marks}
    if color := palette.text((marks.get("color") or {}).get("color")):
        font["color"] = f"#{color}"
    if family := (marks.get("font") or {}).get("family"):
        font["name"] = fonts.office(family)
    size = (marks.get("size") or {}).get("pt")
    if isinstance(size, int | float) and size >= 1:
        font["sz"] = size
    return font


def _xml(element) -> bytes:
    return etree.tostring(element, xml_declaration=True, encoding="UTF-8", standalone=True)


def _place(row: int, col: int) -> str:
    letters = ""
    while col:
        col, rest = divmod(col - 1, 26)
        letters = chr(65 + rest) + letters
    return f"{letters}{row}"


def _table_style(root, design: dict, scheme: list[str], styled: dict[str, str]) -> str:
    """The name of the table style a design is: Excel's own where it is one in the workbook's
    theme, else one written into the styles once for each design, a later one of the same name
    but drawn otherwise numbered after it."""
    drawn = {key: value for key, value in design.items() if key not in ("on", "area")}
    name = design.get("name")
    if name and excel.preset(name, scheme)[0] == drawn:
        return name
    key = json.dumps(drawn, sort_keys=True)
    if key in styled:
        return styled[key]
    base = name or "Table design"
    made, suffix = base, 1
    while made in styled.values() or excel.preset(made, scheme)[0] is not None:
        suffix += 1
        made = f"{base} {suffix}"
    dxfs = root.find(f"{{{MAIN}}}dxfs")
    if dxfs is None:
        dxfs = etree.SubElement(root, f"{{{MAIN}}}dxfs")
    listed = root.find(f"{{{MAIN}}}tableStyles")
    if listed is None:
        listed = etree.Element(
            f"{{{MAIN}}}tableStyles",
            defaultTableStyle="TableStyleMedium2",
            defaultPivotStyle="PivotStyleLight16",
        )
        dxfs.addnext(listed)
    style = etree.SubElement(listed, f"{{{MAIN}}}tableStyle", name=made, pivot="0")
    parts = design.get("parts") or {}
    bands = design.get("bands") or {}
    for part, type in ELEMENTS.items():
        size = next(
            (
                bands.get(axis, [1, 1])[at]
                for (axis, at), stripe in STRIPES.items()
                if stripe == type
            ),
            1,
        )
        if part not in parts and size == 1:
            continue
        element = etree.SubElement(style, f"{{{MAIN}}}tableStyleElement", type=type)
        if part in parts:
            element.set("dxfId", str(len(dxfs)))
            dxfs.append(_dxf(parts[part]))
        if size != 1:
            element.set("size", str(int(size)))
    style.set("count", str(len(style)))
    dxfs.set("count", str(len(dxfs)))
    listed.set("count", str(len(listed)))
    styled[key] = made
    return made


def _dxf(part: dict):
    """A part of a design as a differential format: its font, its fill and its borders."""

    def put(parent, tag: str, **attrs):
        return etree.SubElement(parent, f"{{{MAIN}}}{tag}", attrs)

    def colored(parent, tag: str, kind: str, tint) -> None:
        shown = office.solid(kind, tint)
        put(parent, tag, **({"rgb": f"FF{shown}"} if shown else {"auto": "1"}))

    found = etree.Element(f"{{{MAIN}}}dxf")
    marks = part.get("marks") or {}
    if marks:
        font = put(found, "font")
        for mark, tag in (("strong", "b"), ("em", "i"), ("strike", "strike")):
            if mark in marks:
                put(font, tag, **({"val": "0"} if marks[mark] is False else {}))
        if "underline" in marks:
            put(font, "u", **({"val": "none"} if marks["underline"] is False else {}))
        if isinstance(size := office.attr(marks, "size", "pt"), int | float):
            put(font, "sz", val=f"{size:g}")
        if "color" in marks:
            colored(font, "color", "text", office.attr(marks, "color", "color"))
        if isinstance(family := office.attr(marks, "font", "family"), str):
            put(font, "name", val=family)
    if "fill" in part:
        if part["fill"] == designs.NONE:
            put(put(found, "fill"), "patternFill", patternType="none")
        else:
            colored(put(put(found, "fill"), "patternFill"), "bgColor", "highlight", part["fill"])
    if edges := part.get("edges"):
        border = put(found, "border")
        for side, tag in BORDER.items():
            if side not in edges:
                continue
            line = designs.drawn(edges[side])
            if line is None:
                put(border, tag)
                continue
            shown = _border(line)
            drawn = put(border, tag, style=shown["style"])
            if "color" in shown:
                put(drawn, "color", rgb=f"FF{shown['color'][1:]}")
    return found


def _anchor(drawing, col: int, row: int, cx: int, cy: int, number: int, rid: str) -> None:
    def put(parent, tag: str, text: str | None = None, **attrs):
        element = etree.SubElement(parent, f"{{{XDR}}}{tag}", attrs)
        element.text = text
        return element

    anchor = put(drawing, "oneCellAnchor")
    start = put(anchor, "from")
    for tag, value in (("col", col), ("colOff", 0), ("row", row), ("rowOff", 0)):
        put(start, tag, str(value))
    put(anchor, "ext", cx=str(cx), cy=str(cy))
    frame = put(anchor, "graphicFrame", macro="")
    names = put(frame, "nvGraphicFramePr")
    put(names, "cNvPr", id=str(number + 1), name=f"Chart {number}")
    put(names, "cNvGraphicFramePr")
    form = put(frame, "xfrm")
    charts.sub(form, "a:off", {"x": 0, "y": 0})
    charts.sub(form, "a:ext", {"cx": 0, "cy": 0})
    data = charts.sub(charts.sub(frame, "a:graphic"), "a:graphicData", {"uri": charts.C})
    charts.sub(data, "c:chart", {"r:id": rid})
    put(anchor, "clientData")


def _text(value: str) -> str:
    """The text as a part of the file holds it, cut to what a cell of Excel's holds."""
    value = ESCAPE_LIKE.sub(lambda found: "_x005F" + found.group(0), value[:LONGEST_TEXT])
    return escape(UNWRITABLE.sub(lambda found: f"_x{ord(found.group(0)):04X}_", value))


def _number(value: float) -> str:
    found = repr(value)
    return found[:-2] if found.endswith(".0") else found


def _formula(text: str) -> str:
    """The formula as the file stores it, a function added to Excel since 2007 by its prefix."""

    def stored(found: re.Match) -> str:
        name = found.group(1)
        return FUNCTIONS[name].stored if name else found.group(0)

    return STORED.sub(stored, text) if FUTURE else text


def _beyond(text: str) -> bool:
    return any(int(row) > EXCEL_ROWS for row in BEYOND.findall(QUOTED.sub("", text)))


def _cell(place: str, value, formula: str | None, style: int) -> str:
    """A cell of the sheet's data: what `value` is as Postgres keeps it, under its formula."""
    head = f'<c r="{place}"' + (f' s="{style}"' if style else "")
    held = f"<f>{escape(formula)}</f>" if formula else ""
    match value:
        case None:
            return f"{head}>{held}</c>" if formula else (f"{head}/>" if style else "")
        case bool():
            return f'{head} t="b">{held}<v>{int(value)}</v></c>'
        case dict():
            return f'{head} t="e">{held}<v>{escape(value["error"])}</v></c>'
        case str() if formula:
            return f'{head} t="str">{held}<v>{_text(value)}</v></c>'
        case str():
            return f'{head} t="inlineStr"><is><t xml:space="preserve">{_text(value)}</t></is></c>'
    return f"{head}>{held}<v>{_number(float(value))}</v></c>"


def _attributes(given: dict) -> str:
    return "".join(f" {name}={quoteattr(str(value))}" for name, value in given.items())


class _Styles:
    """What the workbook's cells look like, each distinct font, fill, edge, number format and
    their combination written once."""

    def __init__(self, base: dict):
        self.root = etree.Element(f"{{{MAIN}}}styleSheet", nsmap={None: MAIN})
        self.fonts: dict[str, int] = {}
        self.fills: dict[str, int] = {"": 0, '"gray125"': 1}
        self.borders: dict[str, int] = {"{}": 0}
        self.formats: dict[str, int] = {"General": 0}
        self.formats_by_id: dict[int, str] = {}
        self.cells: dict[tuple, int] = {}
        self.base = base
        self.of(base, None)

    @staticmethod
    def _index(held: dict, given) -> int:
        return held.setdefault(json.dumps(given, sort_keys=True), len(held))

    def of(self, style: dict, format: str | None) -> int:
        font = self._index(self.fonts, style.get("font") or self.base["font"])
        fill = self.fills[""]
        if given := style.get("fill"):
            fill = self._index(self.fills, given["color"])
        border = self._index(self.borders, style.get("border") or {})
        code = self.formats.setdefault(format or "General", 163 + len(self.formats))
        alignment = style.get("alignment")
        key = (font, fill, border, code, json.dumps(alignment, sort_keys=True))
        return self.cells.setdefault(key, len(self.cells))

    def xml(self) -> bytes:
        put = etree.SubElement
        root = self.root
        dxfs = root.find(f"{{{MAIN}}}dxfs")
        if dxfs is None:
            dxfs = put(root, f"{{{MAIN}}}dxfs", count="0")
        parts = []
        if len(self.formats) > 1:
            numbers = etree.Element(f"{{{MAIN}}}numFmts", count=str(len(self.formats) - 1))
            for code, id in self.formats.items():
                if id:
                    put(numbers, f"{{{MAIN}}}numFmt", numFmtId=str(id), formatCode=code)
            parts.append(numbers)
        fonts_of = etree.Element(f"{{{MAIN}}}fonts", count=str(len(self.fonts)))
        for each in self.fonts:
            _font_of(fonts_of, json.loads(each))
        parts.append(fonts_of)
        fills = etree.Element(f"{{{MAIN}}}fills", count=str(len(self.fills)))
        put(put(fills, f"{{{MAIN}}}fill"), f"{{{MAIN}}}patternFill", patternType="none")
        put(put(fills, f"{{{MAIN}}}fill"), f"{{{MAIN}}}patternFill", patternType="gray125")
        for each in list(self.fills)[2:]:
            pattern = put(put(fills, f"{{{MAIN}}}fill"), f"{{{MAIN}}}patternFill")
            pattern.set("patternType", "solid")
            put(pattern, f"{{{MAIN}}}fgColor", rgb=f"FF{json.loads(each)[1:]}")
            put(pattern, f"{{{MAIN}}}bgColor", indexed="64")
        parts.append(fills)
        borders = etree.Element(f"{{{MAIN}}}borders", count=str(len(self.borders)))
        for each in self.borders:
            _border_of(borders, json.loads(each))
        parts.append(borders)
        linked = etree.Element(f"{{{MAIN}}}cellStyleXfs", count="1")
        put(linked, f"{{{MAIN}}}xf", numFmtId="0", fontId="0", fillId="0", borderId="0")
        parts.append(linked)
        cells = etree.Element(f"{{{MAIN}}}cellXfs", count=str(len(self.cells)))
        for font, fill, border, code, alignment in self.cells:
            xf = put(
                cells,
                f"{{{MAIN}}}xf",
                numFmtId=str(code),
                fontId=str(font),
                fillId=str(fill),
                borderId=str(border),
                xfId="0",
                **({"applyNumberFormat": "1"} if code else {}),
                **({"applyFont": "1"} if font else {}),
                **({"applyFill": "1"} if fill else {}),
                **({"applyBorder": "1"} if border else {}),
            )
            if given := json.loads(alignment):
                xf.set("applyAlignment", "1")
                aligned = {
                    "horizontal": given.get("horizontal"),
                    "vertical": given.get("vertical"),
                    "wrapText": "1" if given.get("wrap_text") else None,
                }
                put(
                    xf,
                    f"{{{MAIN}}}alignment",
                    {name: value for name, value in aligned.items() if value},
                )
        parts.append(cells)
        named = etree.Element(f"{{{MAIN}}}cellStyles", count="1")
        put(named, f"{{{MAIN}}}cellStyle", name="Normal", xfId="0", builtinId="0")
        parts.append(named)
        for part in parts:
            dxfs.addprevious(part)
        return _xml(root)


def _font_of(parent, font: dict) -> None:
    put = etree.SubElement
    element = put(parent, f"{{{MAIN}}}font")
    for tag in ("b", "i", "strike"):
        if font.get(tag):
            put(element, f"{{{MAIN}}}{tag}")
    if font.get("u"):
        put(element, f"{{{MAIN}}}u")
    put(element, f"{{{MAIN}}}sz", val=f"{font['sz']:g}")
    if color := font.get("color"):
        put(element, f"{{{MAIN}}}color", rgb=f"FF{color[1:]}")
    put(element, f"{{{MAIN}}}name", val=font["name"])
    put(element, f"{{{MAIN}}}family", val="2")


def _border_of(parent, border: dict) -> None:
    put = etree.SubElement
    element = put(parent, f"{{{MAIN}}}border")
    for side in ("left", "right", "top", "bottom"):
        given = border.get(side)
        line = put(element, f"{{{MAIN}}}{side}", **({"style": given["style"]} if given else {}))
        if given and "color" in given:
            put(line, f"{{{MAIN}}}color", rgb=f"FF{given['color'][1:]}")
    put(element, f"{{{MAIN}}}diagonal")


@dataclass
class _Table:
    """What writing a table's rows goes by: its block and grid's key, its cells placed and the
    slots its merged cells reach by where they stand, and how its designs draw each slot, where
    its size lets them be laid out."""

    id: str
    block: Block
    key: int
    cols: list[str]
    placed: dict[tuple[int, int], blocks.Placed]
    reach: dict[int, list[int]]
    cover: dict[tuple[int, int], blocks.Placed]
    listed: list[tuple[dict, tuple, list[str]]]
    designed: dict | None
    letters: list[str]
    links: list[tuple[str, str]] = field(default_factory=list)


def _table_of(book: Computed, id: str, listed: list[tuple[dict, tuple, list[str]]]) -> _Table:
    table = book.tables[id]
    grid = table.grid or blocks.Grid([], [])
    shown = blocks.placed(table)
    cover = {
        (y, x): each
        for each in shown
        if each.rows > 1 or each.cols > 1
        for y in range(each.y, each.y + each.rows)
        for x in range(each.x, each.x + each.cols)
    }
    reach: dict[int, list[int]] = {}
    for y, x in cover:
        reach.setdefault(y, []).append(x)
    kept = [each for each, _, _ in listed]
    others = [each for each in table.attrs.get("designs") or [] if not _among(each, kept)]
    small = len(grid.rows) * len(grid.cols) <= MOST_CELLS
    if others and not small:
        log.warning("Table %s is past the ceiling on cells: its designs are not drawn", id)
    designed = (
        office.designed(replace(table, attrs={**table.attrs, "designs": others})) if small else None
    )
    return _Table(
        id,
        table,
        book.keys[id],
        grid.cols,
        {(each.y, each.x): each for each in shown},
        reach,
        cover,
        listed,
        designed,
        [column_name(x) for x in range(1, len(grid.cols) + 1)],
    )


def _among(design: dict, kept: list[dict]) -> bool:
    return any(design is each for each in kept)


class _Writing:
    """A workbook on its way into the archive, its sheets one after another, each of its rows
    out of Postgres and into the file before the next is read."""

    def __init__(self, book: Computed, archive: zipfile.ZipFile):
        self.book = book
        self.archive = archive
        self.base = {
            "font": {"name": fonts.office(book.font), "sz": book.size},
        }
        self.styles = _Styles(self.base)
        self.scheme = excel.scheme(etree.fromstring(THEME_XML))
        self.designs: dict[str, str] = {}
        self.listed = {id: _listed(book, id, table) for id, table in book.tables.items()}
        self.places = compute.places_of(book.sheets)
        self.long = any(len(sheet.rows) > EXCEL_ROWS for sheet in book.sheets.values())
        self.taken = {title.casefold() for title in book.titles.values()}
        self.written: list[tuple[str, str, str]] = []
        self.firsts: dict[str, int] = {}
        self.numbers = dict(
            zip(
                book.sheets,
                accumulate((self._pages(host) for host in book.sheets), initial=1),
                strict=False,
            )
        )
        self.table_count = 0
        self.chart_count = 0

    def run(self) -> None:
        self._contents()
        for host in self.book.sheets:
            self._sheet(host)
        self._package()

    def _pages(self, host: str) -> int:
        return max(1, math.ceil(len(self.book.sheets[host].rows) / EXCEL_ROWS))

    def _contents(self) -> None:
        """The content types first in the archive, as tools that read a file's kind expect."""
        book = self.book
        sheets = sum(self._pages(host) for host in book.sheets)
        listed = sum(len(each) for each in self.listed.values())
        charts_in = sum(len(each) for each in book.charted.values())
        overrides = [
            ("/xl/workbook.xml", WORKBOOK_TYPE),
            ("/xl/styles.xml", STYLES_TYPE),
            ("/xl/theme/theme1.xml", THEME_TYPE),
            *((f"/xl/worksheets/sheet{n}.xml", WORKSHEET_TYPE) for n in range(1, sheets + 1)),
            *((f"/xl/tables/table{n}.xml", TABLE_TYPE) for n in range(1, listed + 1)),
            *(
                (f"/xl/drawings/drawing{self.numbers[host]}.xml", DRAWING_TYPE)
                for host in book.charted
            ),
            *((f"/xl/charts/chart{n}.xml", CHART_TYPE) for n in range(1, charts_in + 1)),
        ]
        rels = "application/vnd.openxmlformats-package.relationships+xml"
        self.archive.writestr(
            CONTENT_TYPES,
            XML
            + f'<Types xmlns="{TYPES}"><Default Extension="rels" ContentType="{rels}"/>'
            + '<Default Extension="xml" ContentType="application/xml"/>'
            + "".join(
                f'<Override PartName="{part}" ContentType="{type}"/>' for part, type in overrides
            )
            + "</Types>",
        )

    def _title(self, host: str, page: int) -> str:
        title = self.book.titles[host]
        if not page:
            return title
        number = page + 1
        while True:
            made = f"{title[: 31 - len(str(number)) - 3]} ({number})"
            if made.casefold() not in self.taken:
                self.taken.add(made.casefold())
                return made
            number += 1

    def _begin(self, host: str, table: _Table | None, page: int) -> tuple[str, IO[bytes]]:
        number = len(self.written) + 1
        name = f"xl/worksheets/sheet{number}.xml"
        self.written.append((self._title(host, page), name, host))
        if not page:
            self.firsts[host] = number - 1
        out = self.archive.open(name, "w", force_zip64=True)
        selected = ' tabSelected="1"' if number == 1 else ""
        out.write(
            (
                XML + f'<worksheet xmlns="{MAIN}" xmlns:r="{charts.R}">'
                f'<sheetViews><sheetView{selected} workbookViewId="0">'
                + (self._pane(table) if table is not None and not page else "")
                + "</sheetView></sheetViews>"
                + f'<sheetFormatPr defaultRowHeight="{self.book.size * ROW_EM:g}"/>'
                + (self._cols(host, table) if table is not None else "")
                + "<sheetData>"
            ).encode()
        )
        return name, out

    def _pane(self, table: _Table) -> str:
        grid = table.block.grid
        frozen = table.block.attrs.get("frozen")
        if frozen not in grid.rows:
            return ""
        count = min(grid.rows.index(frozen) + 1, EXCEL_ROWS - 1)
        return (
            f'<pane ySplit="{count}" topLeftCell="A{count + 1}" '
            'activePane="bottomLeft" state="frozen"/>'
        )

    def _cols(self, host: str, table: _Table) -> str:
        attrs = table.block.attrs
        grid = table.block.grid
        widths = attrs.get("widths") if isinstance(attrs.get("widths"), dict) else {}
        hidden = (attrs.get("hidden") or {}).get("cols", ())
        made = []
        for x, col in enumerate(grid.cols, 1):
            look = grid.col_looks.get(col)
            width = widths.get(col)
            sized = isinstance(width, int | float) and width > 0
            if not sized and not look and col not in hidden:
                continue
            characters = DEFAULT_WIDTH
            if sized:
                characters = (
                    width
                    if attrs.get("sized")
                    else self.book.across[host] * width / 100 / CHARACTER_CM
                )
            values = {"min": x, "max": x, "width": f"{characters:g}"}
            if sized:
                values["customWidth"] = 1
            if look:
                values["style"] = self.styles.of(
                    _styled(self.base, look.get("marks") or {}, look), None
                )
            if col in hidden:
                values["hidden"] = 1
            made.append(f"<col{_attributes(values)}/>")
        return f"<cols>{''.join(made)}</cols>" if made else ""

    def _sheet(self, host: str) -> None:
        book = self.book
        table = _table_of(book, host, self.listed[host]) if host in book.tables else None
        page = 0
        name, out = self._begin(host, table, page)
        if table is not None:
            for at, text in self._rows(table):
                if at // EXCEL_ROWS != page:
                    self._end(host, table, name, out, page)
                    page = at // EXCEL_ROWS
                    name, out = self._begin(host, table, page)
                if text:
                    out.write(text.encode())
        self._end(host, table, name, out, page)

    def _end(self, host: str, table: _Table | None, name: str, out: IO[bytes], page: int) -> None:
        text, relations, parts = self._after(host, table, name) if not page else ("", [], [])
        out.write(f"</sheetData>{text}</worksheet>".encode())
        out.close()
        for part, data in parts:
            self.archive.writestr(part, data)
        if relations:
            self.archive.writestr(rels_of(name), _relations(relations))

    def _rows(self, table: _Table) -> Iterator[tuple[int, str]]:
        index = {col: x for x, col in enumerate(table.cols)}
        everywhere = range(len(table.cols)) if table.designed is not None else None
        for part in rows.parts(self.book.document, table.key):
            memo: dict[tuple, tuple[int, str | None]] = {}
            for at, row in part:
                number = at % EXCEL_ROWS + 1
                across = everywhere
                if across is None:
                    across = sorted(
                        {index[col] for col in row.cells.keys() | row.values.keys() if col in index}
                        | set(table.reach.get(at, ()))
                    )
                cells = "".join(self._cell(table, row, at, x, number, memo) for x in across)
                values: dict = {"r": number}
                if isinstance(row.height, int | float) and row.height > 0:
                    values |= {"ht": f"{min(row.height, 409.5):g}", "customHeight": 1}
                if row.hidden:
                    values["hidden"] = 1
                if row.look:
                    look = _styled(self.base, row.look.get("marks") or {}, row.look)
                    values |= {"s": self.styles.of(look, None), "customFormat": 1}
                yield (
                    at,
                    f"<row{_attributes(values)}>{cells}</row>"
                    if (cells or len(values) > 1)
                    else "",
                )

    def _cell(self, table: _Table, row, at: int, x: int, number: int, memo: dict) -> str:
        col = table.cols[x]
        held = row.cells.get(col) or {}
        each = table.placed.get((at, x))
        parent = table.cover.get((at, x))
        place = f"{table.letters[x]}{number}"
        hidden_by_merge = each is None and parent is not None
        value = None if hidden_by_merge else row.values.get(col)
        format = held.get(FORMAT)
        formula = None
        pieces = held.get(FORMULA)
        if isinstance(pieces, list) and at < EXCEL_ROWS and not hidden_by_merge:
            key = blocks.key_of(row.id, col)
            text = compute.formula_text(pieces, table.id, self.places, self.book.titles, key)
            if len(text) <= LONGEST_FORMULA and not (self.long and _beyond(text)):
                formula = _formula(text)
        grid = table.block.grid
        look_given = held.get(LOOK) or row.look or grid.col_looks.get(col)
        wrapped = isinstance(value, str) and "\n" in value
        if each is None and parent is None and table.designed is None:
            if look_given is None and not format:
                return _cell(place, value, formula, 0)
            memoed = (id(look_given), format, wrapped)
            if memoed not in memo:
                memo[memoed] = self._looked(
                    table, row, at, x, None, parent, look_given, held, format, wrapped
                )
            style, href = memo[memoed]
        else:
            style, href = self._looked(
                table, row, at, x, each, parent, look_given, held, format, wrapped
            )
        if href and at < EXCEL_ROWS:
            table.links.append((place, href))
        return _cell(place, value, formula, style)

    def _looked(
        self, table, row, at, x, each, parent, look_given, held, format, wrapped
    ) -> tuple[int, str | None]:
        col = table.cols[x]
        given: Cell | None = each.cell if each is not None else None
        if given is None and look_given is not None:
            key = blocks.key_of(row.id, col)
            given = blocks.light_cell(key, held.get(TEXT, ""), look_given)
        if table.designed is not None:
            look = table.designed[(row.id, col)]
        else:
            fill = given.fill if given is not None else None
            edges = dict(given.edges or {}) if given is not None else {}
            if parent is not None and each is None:
                fill = parent.cell.fill
                outer = {
                    "top": at == parent.y,
                    "bottom": at == parent.y + parent.rows - 1,
                    "left": x == parent.x,
                    "right": x == parent.x + parent.cols - 1,
                }
                edges = {
                    side: line for side, line in (parent.cell.edges or {}).items() if outer[side]
                }
            look = designs.Cell([], fill=fill, edges=edges)
        if given is None and not _draws(look) and not format:
            return 0, None
        marks, align = _look(given) if given is not None else ({}, None)
        style = _styled(
            self.base,
            {**look.marks, **marks},
            {
                "attrs": {"align": align or look.align},
                "valign": look.valign,
                "wrapped": wrapped,
                "fill": look.fill,
                "edges": look.edges,
            },
        )
        return self.styles.of(style, format), (marks.get("link") or {}).get("href")

    def _after(self, host: str, table: _Table | None, name: str) -> tuple[str, list, list]:
        """What the sheet holds after its data, in the order Excel requires, the relationships
        that takes and the parts it leads to."""
        text = ""
        relations: list[tuple[str, str, bool]] = []
        parts: list[tuple[str, bytes]] = []
        if table is not None:
            merged = [
                f'<mergeCell ref="{_place(each.y + 1, each.x + 1)}:'
                f'{_place(each.y + each.rows, each.x + each.cols)}"/>'
                for each in table.placed.values()
                if (each.rows > 1 or each.cols > 1) and each.y + each.rows <= EXCEL_ROWS
            ]
            if merged:
                text += f'<mergeCells count="{len(merged)}">{"".join(merged)}</mergeCells>'
            if table.links:
                links = []
                for place, target in table.links:
                    relations.append((LINK, target, True))
                    links.append(f'<hyperlink ref="{place}" r:id="rId{len(relations)}"/>')
                text += f"<hyperlinks>{''.join(links)}</hyperlinks>"
        if host in self.book.charted:
            relations.append((DRAWING, self._drawing(host, parts), False))
            text += f'<drawing r:id="rId{len(relations)}"/>'
        if table is not None and table.listed:
            ids = []
            for design, bounds, titles in table.listed:
                relations.append((TABLE, self._table(design, bounds, titles, parts), False))
                ids.append(f'<tablePart r:id="rId{len(relations)}"/>')
            text += f'<tableParts count="{len(ids)}">{"".join(ids)}</tableParts>'
        return text, relations, parts

    def _table(self, design: dict, bounds: tuple, titles: list[str], parts: list) -> str:
        self.table_count += 1
        count = self.table_count
        name = f"xl/tables/table{count}.xml"
        top, left, bottom, right = bounds
        on = design.get("on") or {}
        table = etree.Element(
            f"{{{MAIN}}}table",
            {
                "id": str(count),
                "name": f"Table{count}",
                "displayName": f"Table{count}",
                "ref": f"{_place(top, left)}:{_place(bottom, right)}",
                **({} if on.get("header") else {"headerRowCount": "0"}),
                **({"totalsRowCount": "1"} if on.get("totals") else {}),
            },
            nsmap={None: MAIN},
        )
        columns = etree.SubElement(table, f"{{{MAIN}}}tableColumns", count=str(len(titles)))
        for number, column in enumerate(titles, 1):
            etree.SubElement(columns, f"{{{MAIN}}}tableColumn", id=str(number), name=column)
        info = {theirs: "1" if on.get(ours) else "0" for theirs, ours in TABLE_SWITCHES.items()}
        style = _table_style(self.styles.root, design, self.scheme, self.designs)
        etree.SubElement(table, f"{{{MAIN}}}tableStyleInfo", name=style, **info)
        parts.append((name, _xml(table)))
        return name

    def _drawing(self, host: str, parts: list) -> str:
        """The sheet's charts, right of its table, one below another, each as wide as its tab's
        text."""
        book = self.book
        beside = book.sheets[host].cols
        nsmap = {"xdr": XDR, "a": charts.A, "c": charts.C, "r": charts.R}
        drawing = etree.Element(f"{{{XDR}}}wsDr", nsmap=nsmap)
        relations: list[tuple[str, str, bool]] = []
        heights = self._heights(host)
        row = 0
        for number, attrs in enumerate(book.charted[host], 1):
            self.chart_count += 1
            name = f"xl/charts/chart{self.chart_count}.xml"
            parts.append(
                (
                    name,
                    _xml(charts.space(attrs, book.sheet(drawn.chart_of(attrs).table), book.font)),
                )
            )
            relations.append((CHART, name, False))
            cx, cy = charts.size(book.across[host])
            _anchor(drawing, len(beside) + 1 if beside else 0, row, cx, cy, number, f"rId{number}")
            row = _below(heights, row, cy, book.size)
        name = f"xl/drawings/drawing{self.numbers[host]}.xml"
        parts.append((name, _xml(drawing)))
        parts.append((rels_of(name), _relations(relations, name)))
        return name

    def _heights(self, host: str) -> Iterator[float | None]:
        if host not in self.book.keys:
            return iter(())
        return iter(
            GridRow.objects.filter(grid=self.book.keys[host])
            .order_by("position")
            .values_list("height", flat=True)
            .iterator()
        )

    def _package(self) -> None:
        book = self.book
        sheets = "".join(
            f'<sheet name={quoteattr(title)} sheetId="{number}" r:id="rId{number}"/>'
            for number, (title, _, _) in enumerate(self.written, 1)
        )
        names_text = ""
        for name in book.defined:
            formula = compute.formula_text(name.pieces, None, self.places, book.titles)
            if len(formula) > LONGEST_FORMULA or (self.long and _beyond(formula)):
                continue
            scope = f' localSheetId="{self.firsts[name.table]}"' if name.table is not None else ""
            names_text += (
                f"<definedName name={quoteattr(name.name)}{scope}>"
                f"{escape(_formula(formula))}</definedName>"
            )
        if names_text:
            names_text = f"<definedNames>{names_text}</definedNames>"
        self.archive.writestr(
            "xl/workbook.xml",
            XML + f'<workbook xmlns="{MAIN}" xmlns:r="{charts.R}">'
            "<bookViews><workbookView/></bookViews>"
            f"<sheets>{sheets}</sheets>{names_text}</workbook>",
        )
        relations = [(WORKSHEET, part, False) for _, part, _ in self.written]
        relations += [(STYLES, "xl/styles.xml", False), (THEME, "xl/theme/theme1.xml", False)]
        self.archive.writestr(
            "xl/_rels/workbook.xml.rels", _relations(relations, "xl/workbook.xml")
        )
        self.archive.writestr("xl/styles.xml", self.styles.xml())
        self.archive.writestr("xl/theme/theme1.xml", THEME_XML)
        self.archive.writestr("_rels/.rels", _relations([(DOCUMENT, "xl/workbook.xml", False)], ""))


def _write(book: Computed, target: IO[bytes]) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        _Writing(book, archive).run()


def _relations(relations: list[tuple[str, str, bool]], source: str | None = None) -> bytes:
    """The relationships of a part, each of them rId and its place from 1, a target within the
    package relative to the part, none given meaning every target is in `xl/worksheets`."""
    folder = posixpath.dirname(source) if source is not None else "xl/worksheets"
    made = []
    for number, (kind, target, external) in enumerate(relations, 1):
        written = target if external or not folder else posixpath.relpath(target, folder)
        mode = ' TargetMode="External"' if external else ""
        made.append(
            f'<Relationship Id="rId{number}" Type={quoteattr(kind)} '
            f"Target={quoteattr(written)}{mode}/>"
        )
    return (XML + f'<Relationships xmlns="{PACKAGE}">{"".join(made)}</Relationships>').encode()


def _below(heights: Iterator, row: int, height: int, size: float) -> int:
    """The row a chart under one that starts at the top of the row given starts at, a row
    clear of it however Excel fits the rows between."""
    covered = 0.0
    while covered < height:
        row += 1
        own = next(heights, None)
        covered += (own or size * ROW_EM) * EMU_PER_POINT
    next(heights, None)
    return row + 1
