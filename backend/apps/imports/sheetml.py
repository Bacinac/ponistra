"""What the parts of an xlsx file say, read from their XML as the program that saved it wrote
them: the workbook's sheets, defined names, Excel tables and cell formats, and each worksheet cell
by cell, every cell with the value it last computed."""

import posixpath
import re
import zipfile
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path, PurePosixPath

from lxml import etree

from apps.content.formulas import column_name, place
from apps.engine import formats
from apps.engine.formats import MONEY_IDS, built_in_money

from . import excel, office
from .laying import DEFAULT_WIDTH
from .reading import TooLarge, Unreadable

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIPS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
# Excel's width of a column none is given for, in the characters a file counts widths in.
# Past this a sheet's part is read a row at a time, its table placed only as far as grids do.
LARGE_PART = 8 * 1024 * 1024
# Unpacked only as a stream, so a limit on the time and disk a sender can take, not on memory.
LARGEST_BOOK = 4 * 1024 * 1024 * 1024
# What the file may make us hold at once. A part of a few kilobytes can unpack to gigabytes, so
# each is bounded by what it really unpacks to and by the XML nodes that makes, never its header.
LARGEST_WHOLE_SHEETS = 64 * 1024 * 1024
LONGEST_ELEMENT = 32 * 1024 * 1024
MOST_SPILLED = 1_000_000
MOST_HELD = 5_000_000
BUILT_IN = {
    0: "General",
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    12: "# ?/?",
    13: "# ??/??",
    14: formats.SHORT_DATE,
    15: formats.DAY_MONTH_YEAR,
    16: formats.DAY_MONTH,
    17: formats.MONTH_YEAR,
    18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM",
    20: formats.CLOCK,
    21: formats.CLOCK_SECONDS,
    22: formats.MOMENT,
    37: "#,##0 ;(#,##0)",
    38: "#,##0 ;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)",
    40: "#,##0.00;[Red](#,##0.00)",
    41: '_(* #,##0_);_(* (#,##0);_(* "-"_);_(@_)',
    42: '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)',
    43: '_(* #,##0.00_);_(* (#,##0.00);_(* "-"??_);_(@_)',
    44: '_($* #,##0.00_);_($* (#,##0.00);_($* "-"??_);_(@_)',
    45: "mm:ss",
    46: "[h]:mm:ss",
    # The standard prints mmss.0; this is the code Excel shows and keeps.
    47: "mm:ss.0",
    48: "##0.0E+0",
    49: "@",
}
TAGS = tuple(
    f"{MAIN}{name}"
    for name in (
        "c",
        "row",
        "col",
        "pane",
        "sheetFormatPr",
        "mergeCell",
        "hyperlink",
        "conditionalFormatting",
        "dataValidation",
    )
)
TRUE = ("1", "true")


@dataclass
class Formatted:
    """The cell formats a worksheet gives that fill or draw lines: its cells', by place, its
    rows', and its spans of columns'."""

    cells: dict[tuple[int, int], int] = field(default_factory=dict)
    rows: dict[int, int] = field(default_factory=dict)
    cols: list[tuple[int, int, int]] = field(default_factory=list)


@dataclass
class Sheet:
    """A worksheet as read: its cells by place, its arrays, merges, the heights in points of the
    rows Excel was told, the rows it hides and the spans of columns it hides, the widths of its
    spans of columns, the formats of its rows and columns, its links and the rows it freezes, its
    last row and column, and the ids its table's rows and columns are given."""

    index: int
    title: str
    hidden: bool
    part: str
    cells: dict[tuple[int, int], dict] = field(default_factory=dict)
    merges: list[dict] = field(default_factory=list)
    arrays: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)
    heights: dict[int, float] = field(default_factory=dict)
    hidden_rows: set[int] = field(default_factory=set)
    hidden_cols: list[tuple[int, int, float]] = field(default_factory=list)
    widths: list[tuple[int, int, float]] = field(default_factory=list)
    default_width: float = DEFAULT_WIDTH
    formatted: Formatted = field(default_factory=Formatted)
    row_styles: dict[int, int] = field(default_factory=dict)
    col_styles: list[tuple[int, int, int]] = field(default_factory=list)
    links: dict[tuple[int, int], dict] = field(default_factory=dict)
    frozen: int = 0
    spills: int = 0
    rules: dict[str, int] = field(default_factory=dict)
    last_row: int = 0
    last_col: int = 0
    streamed: bool = False
    rows: Sequence[str] | None = None
    cols: Sequence[str] | None = None

    def reach(self, row: int | None, col: int | None) -> None:
        if row is not None:
            self.last_row = max(self.last_row, row)
        if col is not None:
            self.last_col = max(self.last_col, col)


@dataclass(frozen=True)
class ExcelTable:
    """An Excel table: the sheet it is on, its range and its header and totals rows, and its
    columns' names in their order."""

    sheet: str
    top: int
    left: int
    bottom: int
    right: int
    headers: int
    totals: int
    columns: tuple[str, ...]


ESCAPED = re.compile("_x([0-9A-Fa-f]{4})_")


def checked(path: Path) -> dict[str, int]:
    """What each part of a file really unpacks to, within what a reader takes on."""
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > office.MOST_PARTS:
                raise TooLarge
            left = LARGEST_BOOK
            sizes = {}
            for part in archive.infolist():
                # The size a part's header gives is the sender's word; only unpacking it tells.
                part.file_size = 1 << 62
                unpacked = 0
                with archive.open(part) as stream:
                    while chunk := stream.read(1 << 20):
                        unpacked += len(chunk)
                        left -= len(chunk)
                        if left < 0:
                            raise TooLarge
                sizes[part.filename] = unpacked
            return sizes
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as error:
        raise Unreadable from error


class _Metered:
    """A part as the parser reads it, refused where an element runs on past `longest` bytes,
    which the parser holds until the element closes, or the part past `most`."""

    def __init__(self, source, longest: int, most: int = LARGEST_BOOK):
        self.source = source
        self.longest = longest
        self.most = most
        self.since = 0
        self.total = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self.source.read(size)
        self.since += len(chunk)
        self.total += len(chunk)
        if self.since > self.longest or self.total > self.most:
            raise TooLarge
        return chunk

    def mark(self) -> None:
        self.since = 0


def whole(archive: zipfile.ZipFile, part: str) -> etree._Element:
    """A part read into memory, one that is neither larger nor denser than a reader takes on."""
    nodes = etree.XMLParser(target=office._Nodes(), resolve_entities=False, no_network=True)
    data = bytearray()
    with archive.open(part) as stream:
        while chunk := stream.read(1 << 20):
            data += chunk
            if len(data) > office.LARGEST:
                raise TooLarge
            nodes.feed(chunk)
    return etree.fromstring(bytes(data), etree.XMLParser(resolve_entities=False, no_network=True))


def listed(archive: zipfile.ZipFile) -> list[tuple[str, str, str, str]]:
    """The workbook's sheets in its order, each by its name, its kind, "worksheet" or
    "chartsheet", its part and its state."""
    workbook = whole(archive, "xl/workbook.xml")
    relations = whole(archive, "xl/_rels/workbook.xml.rels")
    targets = {
        relation.get("Id"): (kind, relation.get("Target") or "")
        for relation in relations.iter(f"{PACKAGE}Relationship")
        if (kind := (relation.get("Type") or "").rpartition("/")[2]) in ("worksheet", "chartsheet")
    }
    found = []
    for sheet in workbook.iter(f"{MAIN}sheet"):
        if (target := targets.get(sheet.get(f"{RELATIONSHIPS}id"))) and target[1]:
            kind, path = target
            part = path.lstrip("/") if path.startswith("/") else str(PurePosixPath("xl", path))
            found.append((sheet.get("name") or "", kind, part, sheet.get("state") or "visible"))
    return found


def worksheets(archive: zipfile.ZipFile, kind: str = "worksheet") -> list[str]:
    """The workbook's worksheet parts in its order, chart sheets left out; or its chart sheets."""
    return [part for _, each, part, _ in listed(archive) if each == kind]


def related(
    archive: zipfile.ZipFile, part: str, kind: str, parts: set[str]
) -> list[tuple[str, str]]:
    """The parts in the file a part relates to by relationships of a kind, by id."""
    folder, name = posixpath.split(part)
    rels = f"{folder}/_rels/{name}.rels"
    if rels not in parts:
        return []
    found = []
    for relation in whole(archive, rels).iter(f"{PACKAGE}Relationship"):
        target = relation.get("Target") or ""
        if not (relation.get("Type") or "").endswith(f"/{kind}"):
            continue
        path = target[1:] if target.startswith("/") else posixpath.normpath(f"{folder}/{target}")
        if path in parts:
            found.append((relation.get("Id"), path))
    return found


def _outside(archive: zipfile.ZipFile, part: str, parts: set[str]) -> dict[str, str]:
    """Where a part's relationships to something outside the file lead, by id."""
    folder, name = posixpath.split(part)
    rels = f"{folder}/_rels/{name}.rels"
    if rels not in parts:
        return {}
    return {
        relation.get("Id"): relation.get("Target") or ""
        for relation in whole(archive, rels).iter(f"{PACKAGE}Relationship")
        if relation.get("TargetMode") == "External"
    }


def _text_of(element) -> str:
    """The text of a shared or inline string: its own and its runs', without phonetic hints,
    what XML cannot hold as Excel escapes it put back."""
    return ESCAPED.sub(
        lambda found: chr(int(found[1], 16)),
        "".join(
            child.text or ""
            for child in element.iter(f"{MAIN}t")
            if child.getparent().tag != f"{MAIN}rPh"
        ),
    )


class Source:
    """A workbook's file: its sheets and names, the look of each cell format, and its worksheets
    read one at a time."""

    def __init__(self, path: Path, locale: str):
        self.sizes = checked(path)
        self.path = path
        self.elements = 0
        try:
            with zipfile.ZipFile(path) as archive:
                self.parts = set(archive.namelist())
                every = listed(archive)
                self.sheets = [
                    (name, state, part) for name, kind, part, state in every if kind == "worksheet"
                ]
                if len({part for _, _, part in self.sheets}) < len(self.sheets):
                    raise Unreadable
                self.read_in_rows = self._in_rows()
                self.names = self._defined(
                    archive, [kind == "worksheet" for _, kind, _, _ in every]
                )
                themes = related(archive, "xl/workbook.xml", "theme", self.parts)
                styles = related(archive, "xl/workbook.xml", "styles", self.parts)
                self.scheme = excel.scheme(whole(archive, themes[0][1]) if themes else None)
                root = whole(archive, styles[0][1]) if styles else None
                self.formats = excel.Styles(
                    root if root is not None else etree.Element(f"{MAIN}styleSheet"), self.scheme
                )
                self.styles = self._cell_styles(root, locale)
                self.strings = self._strings(archive)
                self.tables = self._tables(archive)
        except (KeyError, etree.LxmlError, ValueError, IndexError) as error:
            raise Unreadable from error
        self.base = self.styles[0] if self.styles else {}

    @staticmethod
    def _defined(archive: zipfile.ZipFile, worksheet: list[bool]) -> list[dict]:
        """The defined names, each scoped by the place of its sheet among the worksheets."""
        numbers: dict[int, int] = {}
        for at, kept in enumerate(worksheet):
            if kept:
                numbers[at] = len(numbers)
        found = []
        for name in whole(archive, "xl/workbook.xml").iter(f"{MAIN}definedName"):
            local = name.get("localSheetId")
            if local is not None and int(local) not in numbers:
                continue
            found.append(
                {
                    "name": name.get("name") or "",
                    "formula": name.text or "",
                    "scope": None if local is None else numbers[int(local)],
                }
            )
        return found

    def _cell_styles(self, root, locale: str) -> list[dict]:
        """Each cell format as its font, its alignment and the code of its number format, a
        built-in currency as the language writes its own."""
        if root is None:
            return []
        given = {
            int(each.get("numFmtId")): each.get("formatCode") for each in root.iter(f"{MAIN}numFmt")
        }
        fonts = [self._font(each) for each in root.iterfind(f"{MAIN}fonts/{MAIN}font")]
        found = []
        for xf in root.iterfind(f"{MAIN}cellXfs/{MAIN}xf"):
            at = int(xf.get("fontId") or 0)
            number = int(xf.get("numFmtId") or 0)
            alignment = xf.find(f"{MAIN}alignment")
            found.append(
                {
                    "font": fonts[at] if at < len(fonts) else {},
                    "num_fmt": (
                        built_in_money(number, given.get(number), locale)
                        if number in MONEY_IDS
                        else given.get(number, BUILT_IN.get(number, "General"))
                    ),
                    "alignment": dict(alignment.attrib) if alignment is not None else {},
                }
            )
        return found

    def _font(self, element) -> dict:
        found: dict = {}
        for child in element:
            value = child.get("val")
            match etree.QName(child).localname:
                case "b" | "i" | "strike" as name:
                    found[name] = value not in ("0", "false")
                case "u":
                    found["u"] = value != "none"
                case "sz" if value and NUMBER.fullmatch(value):
                    found["sz"] = float(value)
                case "name":
                    found["name"] = value
                case "color":
                    found["color"] = excel.color(child, self.scheme)
        return found

    def _strings(self, archive: zipfile.ZipFile) -> list[str]:
        found = related(archive, "xl/workbook.xml", "sharedStrings", self.parts)
        if not found:
            return []
        strings = []
        with archive.open(found[0][1]) as stream:
            source = _Metered(stream, LONGEST_ELEMENT, office.LARGEST)
            for _, element in etree.iterparse(source, tag=f"{MAIN}si", resolve_entities=False):
                strings.append(_text_of(element))
                source.mark()
                element.clear()
                while element.getprevious() is not None:
                    del element.getparent()[0]
        return strings

    def held(self, root: etree._Element) -> etree._Element:
        """A part's tree, counted among those whose content stays until the workbook is read."""
        self.elements += sum(1 for _ in root.iter())
        if self.elements > MOST_HELD:
            raise TooLarge
        return root

    def blob(self, archive: zipfile.ZipFile, part: str) -> bytes:
        if self.sizes[part] > office.LARGEST:
            raise TooLarge
        return archive.read(part)

    def _in_rows(self) -> set[str]:
        """The worksheets read a row at a time, as each one or all of them together would be
        too much to hold."""
        left, found = LARGEST_WHOLE_SHEETS, set()
        for _, _, part in self.sheets:
            size = self.sizes.get(part, 0)
            if size > LARGE_PART or size > left:
                found.add(part)
            else:
                left -= size
        return found

    def _tables(self, archive: zipfile.ZipFile) -> dict[str, ExcelTable]:
        found = {}
        for name, _, part in self.sheets:
            for _, each in related(archive, part, "table", self.parts):
                table = self.held(whole(archive, each))
                ends = [place(end) for end in (table.get("ref") or "").split(":")]
                if len(ends) != 2 or None in ends:
                    continue
                (top, left), (bottom, right) = ends
                columns = tuple(
                    column.get("name") or "" for column in table.iter(f"{MAIN}tableColumn")
                )
                found[(table.get("displayName") or table.get("name") or "").casefold()] = (
                    ExcelTable(
                        name,
                        top,
                        left,
                        bottom,
                        right,
                        int(table.get("headerRowCount") or 1),
                        int(table.get("totalsRowCount") or 0),
                        columns,
                    )
                )
        return found

    def style(self, xf: str | None) -> dict:
        at = int(xf) if xf and xf.isdigit() else 0
        return self.styles[at] if at < len(self.styles) else self.base

    def _value(self, element) -> tuple[str | None, object]:
        """A cell's kind and the value it holds."""
        kind = element.get("t") or "n"
        text = None
        for child in element:
            if child.tag == f"{MAIN}v":
                text = child.text or ""
            elif child.tag == f"{MAIN}is":
                return "text", _text_of(child)
        if text is None:
            return None, None
        match kind:
            case "s":
                at = int(text) if text.isdigit() else -1
                return "text", self.strings[at] if 0 <= at < len(self.strings) else ""
            case "str":
                return "text", text
            case "b":
                return "bool", text in TRUE
            case "e":
                return "error", text
            case "d":
                return None, None
        return ("number", float(text)) if NUMBER.fullmatch(text.lstrip("-+")) else (None, None)

    def sheet(self, index: int, at: int | None = None) -> Sheet:
        """The worksheet at its place among the workbook's, numbered `at` where that is given."""
        sheet = self._empty(index, at)
        for _ in self.walked(sheet):
            pass
        for row, col in [*sheet.cells, *sheet.formatted.cells]:
            sheet.reach(row, col)
        for merge in sheet.merges:
            sheet.reach(merge["row"] + merge["height"] - 1, merge["column"] + merge["width"] - 1)
        return sheet

    def opened(self, index: int, at: int | None = None) -> tuple[Sheet, Iterator[int]]:
        """The worksheet read up to its first row, and the rest of it a row at a time: what
        stands before the rows is on the sheet by then, each row's cells and looks when its
        number is given, for the taker to clear, and what follows the rows at the end."""
        sheet = self._empty(index, at)
        sheet.streamed = True
        walk = self.walked(sheet)
        first = next(walk, None)
        return sheet, chain(() if first is None else (first,), walk)

    def large(self, index: int) -> bool:
        return self.sheets[index][2] in self.read_in_rows

    def _empty(self, index: int, at: int | None) -> Sheet:
        title, state, part = self.sheets[index]
        return Sheet(index if at is None else at, title, state != "visible", part)

    def walked(self, sheet: Sheet) -> Iterator[int]:
        """Reads the worksheet onto the sheet, giving the number of each row as it ends."""
        try:
            with zipfile.ZipFile(self.path) as archive:
                outside = _outside(archive, sheet.part, self.parts)
                with archive.open(sheet.part) as stream:
                    yield from self._walked(_Metered(stream, LONGEST_ELEMENT), sheet, outside)
        except (KeyError, etree.LxmlError, ValueError) as error:
            raise Unreadable from error

    def _walked(self, source: _Metered, sheet: Sheet, outside: dict[str, str]) -> Iterator[int]:
        spilled: set[tuple[int, int]] = set()
        row, col = 0, 0
        for _, element in etree.iterparse(source, tag=TAGS, resolve_entities=False):
            match etree.QName(element).localname:
                case "c":
                    col += 1
                    at = place(element.get("r") or "") or (row + 1, col)
                    col = at[1]
                    self._cell(element, at, sheet, spilled)
                case "row":
                    row = (
                        int(element.get("r") or row + 1)
                        if (element.get("r") or "").isdigit()
                        else row + 1
                    )
                    col = 0
                    self._row(element, row, sheet)
                    source.mark()
                    element.clear(keep_tail=True)
                    while element.getprevious() is not None:
                        del element.getparent()[0]
                    yield row
                    continue
                case "col":
                    self._col(element, sheet)
                case "pane":
                    if (element.get("state") or "").startswith("frozen"):
                        split = element.get("ySplit") or "0"
                        sheet.frozen = int(float(split)) if NUMBER.fullmatch(split) else 0
                case "sheetFormatPr":
                    width = element.get("defaultColWidth") or ""
                    if NUMBER.fullmatch(width) and float(width) > 0:
                        sheet.default_width = float(width)
                case "mergeCell":
                    ends = [place(end) for end in (element.get("ref") or "").split(":")]
                    if len(ends) == 2 and None not in ends:
                        (top, left), (bottom, right) = ends
                        sheet.merges.append(
                            {
                                "row": top,
                                "column": left,
                                "height": bottom - top + 1,
                                "width": right - left + 1,
                            }
                        )
                case "hyperlink":
                    start = place((element.get("ref") or "").split(":")[0])
                    if start:
                        target = outside.get(element.get(f"{RELATIONSHIPS}id") or "")
                        sheet.links[start] = (
                            {"type": "External", "target": target}
                            if target
                            else {"type": "Internal", "target": element.get("location")}
                        )
                case "conditionalFormatting":
                    sheet.rules["conditionalFormats"] = sheet.rules.get("conditionalFormats", 0) + 1
                case "dataValidation":
                    sheet.rules["validations"] = sheet.rules.get("validations", 0) + 1
            element.clear()

    def _cell(
        self, element, at: tuple[int, int], sheet: Sheet, spilled: set[tuple[int, int]]
    ) -> None:
        xf = element.get("s")
        if xf and xf.isdigit():
            shown, edges, _ = self.formats.look(int(xf))
            if shown or edges:
                sheet.formatted.cells[at] = int(xf)
        formula = element.find(f"{MAIN}f")
        kind, value = self._value(element)
        if formula is not None and formula.get("t") == "array" and formula.get("ref"):
            ends = [place(end) for end in formula.get("ref").split(":")]
            if None not in ends:
                sheet.arrays[ends[0]] = ends[-1]
                top, left, bottom, right = (*ends[0], *ends[-1])
                bottom, right = min(bottom, top + 4096), min(right, left + 4096)
                if len(spilled) + (bottom - top + 1) * (right - left + 1) <= MOST_SPILLED:
                    spilled |= {
                        (y, x)
                        for y in range(top, bottom + 1)
                        for x in range(left, right + 1)
                        if (y, x) != ends[0]
                    }
        if at in spilled:
            sheet.spills += int(value not in (None, ""))
            return
        text, shared = None, None
        if formula is not None and formula.get("t") != "dataTable":
            text = formula.text or None
            shared = formula.get("si") if formula.get("t") == "shared" else None
        if text or shared is not None or value not in (None, ""):
            sheet.cells[at] = {
                "formula": text,
                "shared": shared,
                "kind": kind,
                "value": value,
                "style": self.style(xf),
            }

    def _row(self, element, row: int, sheet: Sheet) -> None:
        xf = element.get("s") or ""
        if element.get("customFormat") in TRUE and xf.isdigit():
            sheet.row_styles[row] = int(xf)
            shown, edges, _ = self.formats.look(int(xf))
            if shown or edges:
                sheet.formatted.rows[row] = int(xf)
        if element.get("hidden") in TRUE:
            sheet.hidden_rows.add(row)
        height = element.get("ht") or ""
        if element.get("customHeight") in TRUE and NUMBER.fullmatch(height) and float(height) > 0:
            sheet.heights[row] = float(height)

    def _col(self, element, sheet: Sheet) -> None:
        low, high = element.get("min") or "", element.get("max") or ""
        if not (low.isdigit() and high.isdigit()):
            return
        span = int(low), int(high)
        width = element.get("width") or ""
        given = float(width) if NUMBER.fullmatch(width) else 0.0
        if given > 0:
            sheet.widths.append((*span, given))
        xf = element.get("style") or ""
        if xf.isdigit():
            sheet.col_styles.append((*span, int(xf)))
            shown, edges, _ = self.formats.look(int(xf))
            if shown or edges:
                sheet.formatted.cols.append((*span, int(xf)))
        if element.get("hidden") in TRUE:
            sheet.hidden_cols.append((*span, given))


STRUCTURED = re.compile(r'"(?:[^"]|"")*"|(?<![\w.$\]])([^\W\d][\w.]*)\[')
SPECIFIER = re.compile(r"\[((?:[^\]']|'.)*)\]")


def resolved(text: str, tables: dict[str, ExcelTable], row: int) -> str:
    """The formula with each reference into an Excel table as the cells it stands for, the
    row of a [#This Row] the row given; one naming no table or column stays as it was."""
    written: list[str] = []
    at = 0
    while found := STRUCTURED.search(text, at):
        table = tables.get(found[1].casefold()) if found[1] else None
        end = _closing(text, found.end() - 1) if table else None
        area = table and end and _area(table, text[found.end() : end], row)
        if not area:
            written.append(text[at : found.end()])
            at = found.end()
            continue
        written.append(text[at : found.start()] + area)
        at = end + 1
    return "".join(written) + text[at:]


def _closing(text: str, start: int) -> int | None:
    """Where the bracket opening at `start` closes, a quote mark escaping the next character."""
    depth, at = 0, start
    while at < len(text):
        match text[at]:
            case "'":
                at += 1
            case "[":
                depth += 1
            case "]":
                depth -= 1
                if depth == 0:
                    return at
        at += 1
    return None


def _column(name: str, table: ExcelTable) -> int | None:
    plain = re.sub(r"'(.)", r"\1", name).strip().casefold()
    for at, column in enumerate(table.columns):
        if column.casefold() == plain:
            return table.left + at
    return None


def _area(table: ExcelTable, spec: str, row: int) -> str | None:
    """The cells a table's specifiers stand for, as a reference with its sheet."""
    items = SPECIFIER.findall(spec) or ([spec] if spec else [])
    kinds = {item.casefold() for item in items if item.startswith("#")}
    names = [item for item in items if not item.startswith("#")]
    top, bottom = table.top + table.headers, table.bottom - table.totals
    relative = False
    if "#all" in kinds:
        top, bottom = table.top, table.bottom
    elif "#headers" in kinds:
        top, bottom = table.top, table.top
    elif "#totals" in kinds:
        top, bottom = table.bottom, table.bottom
    elif "#this row" in kinds or any(name.startswith("@") for name in names):
        top, bottom, relative = row, row, True
        names = [name.removeprefix("@") for name in names]
    left, right = table.left, table.right
    if names:
        first = _column(names[0], table)
        last = _column(names[-1], table)
        if first is None or last is None:
            return None
        left, right = first, last
    start = _cell_of(top, left, relative)
    end = _cell_of(bottom, right, relative)
    quoted = "'" + table.sheet.replace("'", "''") + "'!"
    return quoted + start if start == end else f"{quoted}{start}:{end}"


def _cell_of(row: int, col: int, relative: bool) -> str:
    return f"${column_name(col)}{'' if relative else '$'}{row}"
