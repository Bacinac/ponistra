"""Formulas in the canonical form xlsx stores them in, read into text and references to
cells, columns or rows: as a workbook's sheets and defined names give them, in the extent a
sheet has."""

import re
from dataclasses import dataclass

from apps.engine.registry import FUNCTIONS

LAST_ROW = 1_048_576
LAST_COL = 16_384
CELL = r"(\$?)([A-Za-z]{1,3})(\$?)(\d+)"
CELLS = re.compile(rf"{CELL}(?::{CELL})?(?![\w.(])")
COLUMNS = re.compile(r"(\$?)([A-Za-z]{1,3}):(\$?)([A-Za-z]{1,3})(?![\w.(])")
LINES = re.compile(r"(\$?)(\d+):(\$?)(\d+)(?![\w.(])")
SHEET = re.compile(r"(?:'((?:[^']|'')+)'|([^\W\d][\w.]*))!")
QUOTED = re.compile(r'"(?:[^"]|"")*"?')
ERROR = re.compile(r"#[A-Za-z0-9/]+[!?]?")
NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
NAME = re.compile(r"[^\W\d][\w.]*")
PREFIX = re.compile(r"^(?:_xl(?:fn|ws|udf)\.)+", re.IGNORECASE)
PARAMETER = re.compile(r"^_xlpm\.", re.IGNORECASE)
BARE_NAME = re.compile(r"[^\W\d][\w.]*")


@dataclass(frozen=True)
class End:
    """One end of a reference, its row and column counted from 1; a whole column has no
    row, a whole row no column."""

    row: int | None
    col: int | None
    abs_row: bool = False
    abs_col: bool = False


@dataclass(frozen=True)
class Ref:
    """A reference in a formula, in the sheet named before it or else in the formula's own,
    its ends ordered top left first, as written."""

    sheet: int | None
    start: End
    end: End | None
    text: str


Part = str | Ref


class Formulas:
    """Reads formulas in the canonical form into text and references, given the workbook's
    sheets and defined names; a function is written in upper case without the prefix xlsx
    stores it under, and those Excel does not have are gathered."""

    def __init__(self, sheets: list[str], names: set[str]):
        self.sheets = {name.casefold(): index for index, name in enumerate(sheets)}
        self.names = names
        self.unknown: set[str] = set()

    def parts(self, text: str) -> list[Part]:
        parts: list[Part] = []

        def add(piece: str) -> None:
            if parts and isinstance(parts[-1], str):
                parts[-1] += piece
            else:
                parts.append(piece)

        at = 0
        while at < len(text):
            named = SHEET.match(text, at)
            lost = named and ERROR.match(text, named.end())
            # Excel keeps the sheet of a deleted range before its #REF!; only the error stays.
            if lost and lost[0].upper() == "#REF!":
                add(lost[0])
                at = lost.end()
                continue
            found = named and address(text, named.end())
            if named and found:
                length, start, end = found
                written = text[at : named.end() + length]
                sheet = self.sheets.get((named[2] or named[1].replace("''", "'")).casefold())
                # After "]" the sheet is another workbook's, after ":" the end of a 3-D range.
                if sheet is None or (at and text[at - 1] in "]:"):
                    add(written)
                else:
                    parts.append(Ref(sheet, start, end, written))
                at += len(written)
                continue
            if text[at] == '"':
                found = QUOTED.match(text, at)
                add(found[0])
                at = found.end()
                continue
            if found := ERROR.match(text, at):
                add(found[0])
                at = found.end()
                continue
            if found := address(text, at):
                length, start, end = found
                parts.append(Ref(None, start, end, text[at : at + length]))
                at += length
                continue
            if found := NUMBER.match(text, at):
                add(found[0])
                at = found.end()
                continue
            if found := NAME.match(text, at):
                name = found[0]
                if text.startswith("(", found.end()) and name.casefold() not in self.names:
                    bare = PREFIX.sub("", name)
                    if bare.upper() in FUNCTIONS:
                        name = bare.upper()
                    else:
                        name = bare
                        self.unknown.add(bare.upper())
                add(PARAMETER.sub("", name))
                at = found.end()
                continue
            add(text[at])
            at += 1
        return parts


def column_number(name: str) -> int:
    number = 0
    for letter in name.upper():
        number = number * 26 + ord(letter) - 64
    return number


def column_name(number: int) -> str:
    letters = ""
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def quote_name(name: str) -> str:
    """A sheet's name as a formula writes it before a reference: bare where it can stand so."""
    if BARE_NAME.fullmatch(name) and not CELLS.fullmatch(name) and not COLUMNS.fullmatch(name):
        return name
    quoted = name.replace("'", "''")
    return f"'{quoted}'"


def _end(col: str | None, row: str | None, abs_col: str, abs_row: str) -> End | None:
    number = int(row) if row is not None else None
    index = column_number(col) if col is not None else None
    if (number is not None and not 1 <= number <= LAST_ROW) or (
        index is not None and not 1 <= index <= LAST_COL
    ):
        return None
    return End(number, index, abs_row == "$", abs_col == "$")


def _ordered(start: End, end: End) -> tuple[End, End]:
    """The top left end first, as Excel turns B3:A1 into A1:B3."""
    if start.row is not None and end.row is not None and start.row > end.row:
        start, end = (
            End(end.row, start.col, end.abs_row, start.abs_col),
            End(start.row, end.col, start.abs_row, end.abs_col),
        )
    if start.col is not None and end.col is not None and start.col > end.col:
        start, end = (
            End(start.row, end.col, start.abs_row, end.abs_col),
            End(end.row, start.col, end.abs_row, start.abs_col),
        )
    return start, end


def address(text: str, at: int) -> tuple[int, End, End | None] | None:
    if found := CELLS.match(text, at):
        abs_col, col, abs_row, row, *rest = found.groups()
        start = _end(col, row, abs_col, abs_row)
        end = _end(rest[1], rest[3], rest[0], rest[2]) if rest[1] else None
        if start is None or (rest[1] and end is None):
            return None
        return (found.end() - at, *_ordered(start, end)) if end else (found.end() - at, start, None)
    if found := COLUMNS.match(text, at):
        start, end = _end(found[2], None, found[1], ""), _end(found[4], None, found[3], "")
    elif found := LINES.match(text, at):
        start, end = _end(None, found[2], "", found[1]), _end(None, found[4], "", found[3])
    else:
        return None
    return (found.end() - at, *_ordered(start, end)) if start and end else None


def place(text: str) -> tuple[int, int] | None:
    """A cell's row and column, counted from 1, from its address, as "B3"."""
    found = CELLS.fullmatch(text)
    end = found and not found[6] and _end(found[2], found[4], found[1], found[3])
    return (end.row, end.col) if end else None
