"""The workbooks Excel saved, as the tests that hold the engine to them read them: each sheet's
formulas, constants and saved values by place, and a value computed held to the one saved."""

import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from apps.engine import formats
from apps.engine.book import calls
from apps.engine.parse import parse
from apps.engine.registry import FUNCTIONS
from apps.engine.values import ERROR_TYPES, Error

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RICH = "{http://schemas.microsoft.com/office/spreadsheetml/2017/richdata}"
RELATIONSHIP = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PROPERTIES = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
MODIFIED = "{http://purl.org/dc/terms/}modified"
SAVED_IN = ZoneInfo("Europe/Zagreb")
SAVED_ON = "cp1250"
LANGUAGES = tuple(formats.CULTURES)
# What each workbook tells the language Excel computed it in by: Windows' long date of a day,
# which names its month in the language and writes the day before it or after, else the month's
# name alone. TEXT reads a code after the tag in the language's own letters (German d is no day,
# fr and it y no year), so each way stands apart and the first naming February tells.
TOLD_BY = ("[$-F800]dddd, mmmm dd, yyyy", "[$-F800]", "[$-F800]0", "mmmm", "MMMM")
TOLD = '&"|"&'.join(f'IFERROR(TEXT(DATE(2001,2,3),"{code}"),"")' for code in TOLD_BY)
FEBRUARY = {
    "veljač": "hr",
    "february": "en",
    "februar": "de",
    "février": "fr",
    "febbraio": "it",
    "febrero": "es",
}
MISSING = object()
ESCAPED = re.compile("_x([0-9A-Fa-f]{4})_")
TEXT_CALL = re.compile(r'TEXT\(("(?:[^"]|"")*"|[^,"]*),"((?:[^"]|"")*)"\)')
# The codes of Excel's built-in number formats, which a file names by id alone (ECMA-376 Part 1,
# §18.8.30), 47 as Excel shows it, not the mmss.0 the standard writes.
BUILT_IN = {
    0: "",
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    12: "# ?/?",
    13: "# ??/??",
    14: "mm-dd-yy",
    15: "d-mmm-yy",
    16: "d-mmm",
    17: "mmm-yy",
    18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM",
    20: "h:mm",
    21: "h:mm:ss",
    22: "m/d/yy h:mm",
    37: "#,##0 ;(#,##0)",
    38: "#,##0 ;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)",
    40: "#,##0.00;[Red](#,##0.00)",
    45: "mm:ss",
    46: "[h]:mm:ss",
    47: "mm:ss.0",
    48: "##0.0E+0",
    49: "@",
}


def _place(reference: str) -> tuple[int, int]:
    letters = reference.rstrip("0123456789")
    col = 0
    for letter in letters:
        col = col * 26 + ord(letter) - 64
    return int(reference[len(letters) :]), col


def _unescaped(text: str) -> str:
    """Text as xlsx writes it, a character XML cannot hold as _xHHHH_ of its code."""
    return ESCAPED.sub(lambda found: chr(int(found.group(1), 16)), text)


def _rich_errors(archive: ZipFile) -> dict[int, Error]:
    """The error of each value metadata a cell names by its vm, from 1: Excel saves a #SPILL! or
    a #CALC! as #VALUE! and the error itself as a rich value, by an errorType one less than the
    number ERROR.TYPE gives it."""
    if "xl/metadata.xml" not in archive.namelist():
        return {}
    metadata = ET.fromstring(archive.read("xl/metadata.xml"))
    kinds = [each.get("name") for each in metadata.find(f"{MAIN}metadataTypes")]
    future = {
        each.get("name"): [block.find(f".//{RICH}rvb") for block in each]
        for each in metadata.iter(f"{MAIN}futureMetadata")
    }
    keys = [
        [key.get("n") for key in each]
        for each in ET.fromstring(archive.read("xl/richData/rdrichvaluestructure.xml"))
    ]
    rich = [
        dict(zip(keys[int(each.get("s"))], [v.text for v in each.iter(f"{RICH}v")], strict=True))
        for each in ET.fromstring(archive.read("xl/richData/rdrichvalue.xml"))
    ]
    named = {code - 1: name for name, code in ERROR_TYPES.items()}
    found = {}
    for at, block in enumerate(metadata.find(f"{MAIN}valueMetadata"), start=1):
        record = block.find(f"{MAIN}rc")
        if kinds[int(record.get("t")) - 1] != "XLRICHVALUE":
            continue
        value = rich[int(future["XLRICHVALUE"][int(record.get("v"))].get("i"))]
        found[at] = Error(named[int(value["errorType"])])
    return found


def _saved(cell: ET.Element, strings: list[str], rich: dict[int, Error]):
    kind = cell.get("t", "n")
    value = cell.find(f"{MAIN}v")
    if kind == "inlineStr":
        return _unescaped("".join(each.text or "" for each in cell.iter(f"{MAIN}t")))
    if value is None:
        return MISSING
    text = value.text or ""
    match kind:
        case "s":
            return strings[int(text)]
        case "str":
            return _unescaped(text)
        case "b":
            return text == "1"
        case "e":
            return rich.get(int(cell.get("vm", 0)), Error(text))
    return float(text)


def _formats(archive: ZipFile, code: str | None) -> list[str]:
    """The number format of each cell style, by its index, "" for General: Excel's built-in
    currency formats (ids 5 to 8) as the language of the Excel that saved them shows them, which
    writes them in US English's form with its own currency."""
    styles = ET.fromstring(archive.read("xl/styles.xml"))
    own = {
        int(each.get("numFmtId")): each.get("formatCode") for each in styles.iter(f"{MAIN}numFmt")
    }
    if code is not None:
        own |= {id: formats.money(code, *shape) for id, shape in formats.MONEY_IDS.items()}
    found = []
    for xf in styles.find(f"{MAIN}cellXfs"):
        id = int(xf.get("numFmtId", 0))
        found.append(own[id] if id in own else BUILT_IN[id])
    return ["" if code == "General" else code for code in found]


def read(path, shared: bool = False, code: str | None = None) -> dict[str, dict]:
    """Each sheet of an xlsx by its name: its formulas and constants by place, Excel's saved
    value of each formula, its hidden rows, and the number format of each cell that has one, a
    built-in currency's as the language of `code` shows it; with `shared`, a formula Excel saved
    as the one of the cell it was filled from only by its value."""
    with ZipFile(path) as archive:
        names = archive.namelist()
        styled = _formats(archive, code)
        rich = _rich_errors(archive)
        strings = []
        if "xl/sharedStrings.xml" in names:
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")):
                strings.append(
                    _unescaped("".join(each.text or "" for each in item.iter(f"{MAIN}t")))
                )
        targets = {
            each.get("Id"): each.get("Target")
            for each in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        sheets = {}
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).iter(f"{MAIN}sheet"):
            target = targets[sheet.get(RELATIONSHIP)]
            part = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            found = {
                "formulas": {},
                "constants": {},
                "values": {},
                "hidden": set(),
                "formats": {},
            }
            for row in ET.fromstring(archive.read(part)).iter(f"{MAIN}row"):
                if row.get("hidden") in ("1", "true"):
                    found["hidden"].add(int(row.get("r")))
                for cell in row.iter(f"{MAIN}c"):
                    place = _place(cell.get("r"))
                    if format := styled[int(cell.get("s", 0))]:
                        found["formats"][place] = format
                    written = cell.find(f"{MAIN}f")
                    value = _saved(cell, strings, rich)
                    if written is not None:
                        if written.text:
                            found["formulas"][place] = written.text
                        elif not shared:
                            raise ValueError(f"{sheet.get('name')}!{cell.get('r')}: shared formula")
                        found["values"][place] = value
                    elif value is not MISSING:
                        found["constants"][place] = value
            sheets[sheet.get("name")] = found
    return sheets


def computed(path):
    """Each formula of an xlsx and the value Excel saved of it, sheet after sheet, read as each
    sheet streams: a workbook of more rows than `read` can hold."""
    with ZipFile(path) as archive:
        rich = _rich_errors(archive)
        targets = {
            each.get("Id"): each.get("Target")
            for each in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).iter(f"{MAIN}sheet"):
            target = targets[sheet.get(RELATIONSHIP)]
            part = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            with archive.open(part) as stream:
                rows = None
                for event, element in ET.iterparse(stream, ("start", "end")):
                    if event == "start":
                        if element.tag == f"{MAIN}sheetData":
                            rows = element
                    elif element.tag == f"{MAIN}c":
                        written = element.find(f"{MAIN}f")
                        if written is not None:
                            yield written.text, _saved(element, [], rich)
                    elif element.tag == f"{MAIN}row":
                        rows.clear()


def texted(formula: str, value: str, code: str) -> bool:
    """Whether a formula Excel saved is TEXT of the value and the code written: the code as it
    was, the value a text as it was or a number of the same value, which Excel may spell in
    another way. Read without the engine's parser, which would take most of a test's time over
    millions of rows."""
    found = TEXT_CALL.fullmatch(formula)
    if found is None or found[2].replace('""', '"') != code:
        return False
    if value.startswith('"'):
        return found[1] == value
    return float(found[1]) == float(value)


def told(text) -> str | None:
    """The language the first of TOLD's ways to name February is written in."""
    for way in str(text).split("|"):
        for word in re.findall(r"[^\W\d_]+", way.lower()):
            if starts := [start for start in FEBRUARY if word.startswith(start)]:
                code = FEBRUARY[max(starts, key=len)]
                return "en-GB" if code == "en" and way.lstrip()[:1].isdigit() else code
    return None


def saved_at(path) -> datetime:
    with ZipFile(path) as archive:
        saved = ET.fromstring(archive.read("docProps/core.xml")).findtext(MODIFIED)
    return datetime.fromisoformat(saved).astimezone(SAVED_IN).replace(tzinfo=None)


def saved_by(path) -> str:
    with ZipFile(path) as archive:
        return ET.fromstring(archive.read("docProps/app.xml")).findtext(f"{PROPERTIES}Application")


def tolerance_of(text: str) -> float:
    return max(
        (FUNCTIONS[name].tolerance for name in calls(parse(text)) if name in FUNCTIONS), default=0
    )


def same(computed, saved, tolerance: float) -> bool:
    if isinstance(saved, float) and isinstance(computed, float) and not isinstance(computed, bool):
        if tolerance:
            return math.isclose(computed, saved, rel_tol=tolerance, abs_tol=tolerance)
        return f"{computed:.15g}" == f"{saved:.15g}"
    return type(computed) is type(saved) and computed == saved


def hashed(text: str) -> bool:
    """A value its format cannot show, which Excel fills the cell with # for, as wide as it is."""
    return bool(text) and set(text) == {"#"}
