"""Excel's formulas read into a tree (D22): from the canonical form xlsx stores them in, from the
form a language with a decimal comma types them in, and from the pieces a table keeps, where a
reference is held by the ids of its rows and columns (D4); and the tree written back in the
canonical form, each newer function after the prefix xlsx stores it under."""

import re
from dataclasses import dataclass
from functools import cache
from typing import NamedTuple

from .formats import entered, numeral
from .registry import FUNCTIONS

LAST_ROW = 1_048_576
LAST_COL = 16_384
ERRORS = (
    "#NULL!",
    "#DIV/0!",
    "#VALUE!",
    "#REF!",
    "#NAME?",
    "#NUM!",
    "#N/A",
    "#GETTING_DATA",
    "#SPILL!",
    "#CALC!",
)
PREFIXES = re.compile(r"^(?:_xlfn\.|_xlws\.)+", re.IGNORECASE)
CELL = r"(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})"
AREA = re.compile(rf"{CELL}(?::{CELL})?(?![\w.(\[])")
COLUMNS = re.compile(r"(\$?)([A-Za-z]{1,3}):(\$?)([A-Za-z]{1,3})(?![\w.(\[])")
ROWS = re.compile(r"(\$?)(\d{1,7}):(\$?)(\d{1,7})(?![\w.(])")
SHEET = re.compile(r"(?:'(?:\[(\d+)\])?((?:[^']|'')+)'|(?:\[(\d+)\])?([^\W\d][\w.]*))!")
NAME = re.compile(r"[^\W\d][\w.\\?]*")
SPACE = re.compile(r"[ \n\r]+")
ASCII_LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
OPERATORS = ("<>", "<=", ">=", "<", ">", "=", "+", "-", "*", "/", "^", "&", "%", ":", "@")
COMPARISONS = {"=", "<>", "<", ">", "<=", ">="}
BINARY = {
    **dict.fromkeys(COMPARISONS, 10),
    "&": 20,
    "+": 30,
    "-": 30,
    "*": 40,
    "/": 40,
    "^": 50,
    ",": 80,
    " ": 85,
    ":": 90,
}
PERCENT = 60
PREFIX_OPERATOR = 70


class Unreadable(ValueError):
    """A formula that is not one."""


@dataclass(frozen=True)
class Syntax:
    decimal: str
    list: str
    row: str


CANONICAL = Syntax(".", ",", ";")
SEMICOLONS = Syntax(",", ";", "/")


@dataclass(frozen=True)
class End:
    """One end of a reference, its row and column counted from 1; a whole column has no row, a
    whole row no column."""

    row: int | None
    col: int | None
    abs_row: bool = False
    abs_col: bool = False


@dataclass(frozen=True)
class Number:
    value: float


@dataclass(frozen=True)
class Text:
    value: str


@dataclass(frozen=True)
class Logical:
    value: bool


@dataclass(frozen=True)
class Error:
    value: str


@dataclass(frozen=True)
class Missing:
    """An argument left empty."""


@dataclass(frozen=True)
class Ref:
    """A reference in A1, in the sheet named before it or else in the formula's own; in another
    workbook when `book` gives its number."""

    sheet: str | None
    start: End
    end: End | None = None
    book: int | None = None


@dataclass(frozen=True)
class Point:
    """One end of a reference a table keeps: the ids of its row and column, OWN for the cell's
    own; a whole column has no row, a whole row no column."""

    row: str | None
    col: str | None
    abs_row: bool = False
    abs_col: bool = False


@dataclass(frozen=True)
class Held:
    """A reference as a table keeps it, by the ids of its rows and columns, in the table given
    or else in the formula's own."""

    table: str | None
    start: Point
    end: Point | None = None


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Structured:
    """A reference into an Excel table by its name and columns, as Table1[[#This Row],[Price]]."""

    table: str
    spec: str


@dataclass(frozen=True)
class Call:
    """A function by its name in upper case, without the prefix xlsx stores it under."""

    name: str
    args: tuple


@dataclass(frozen=True)
class Prefix:
    op: str
    operand: object


@dataclass(frozen=True)
class Postfix:
    op: str
    operand: object


@dataclass(frozen=True)
class Binary:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Group:
    """An expression in parentheses, kept so that the formula is written back as it was."""

    inner: object


@dataclass(frozen=True)
class Array:
    rows: tuple


Node = (
    Number
    | Text
    | Logical
    | Error
    | Missing
    | Ref
    | Held
    | Name
    | Structured
    | Call
    | Prefix
    | Postfix
    | Binary
    | Group
    | Array
)


def column_number(name: str) -> int:
    number = 0
    for letter in name.upper():
        number = number * 26 + ord(letter) - 64
    return number


def column_name(number: int) -> str:
    name = ""
    while number:
        number, rest = divmod(number - 1, 26)
        name = chr(65 + rest) + name
    return name


def quote_sheet(name: str, always: bool = False) -> str:
    """A sheet's name as a reference writes it, quoted where it could be read as anything else."""
    plain = re.fullmatch(r"[^\W\d][\w.]*", name) and not _end_of(name) and not _r1c1(name)
    return name if plain and not always else "'" + name.replace("'", "''") + "'"


def _r1c1(name: str) -> bool:
    return bool(re.fullmatch(r"[Rr]\d*(?:[Cc]\d*)?|[Cc]\d*", name))


def _end(col: str | None, row: str | None, abs_col: str, abs_row: str) -> End | None:
    number = column_number(col) if col is not None else None
    line = int(row) if row is not None else None
    if (number is not None and number > LAST_COL) or (
        line is not None and not 0 < line <= LAST_ROW
    ):
        return None
    return End(line, number, bool(abs_row), bool(abs_col))


def _end_of(text: str) -> End | None:
    found = re.fullmatch(CELL, text)
    return found and _end(found[2], found[4], found[1], found[3])


def _ordered(start: End, end: End) -> tuple[End, End]:
    """The ends of a range top left first, each keeping whether its row and column are
    absolute, as Excel turns B2:A1 into A1:B2."""
    if (start.row or 0) <= (end.row or 0) and (start.col or 0) <= (end.col or 0):
        return start, end
    rows = sorted([(start.row, start.abs_row), (end.row, end.abs_row)], key=lambda e: e[0] or 0)
    cols = sorted([(start.col, start.abs_col), (end.col, end.abs_col)], key=lambda e: e[0] or 0)
    return (
        End(rows[0][0], cols[0][0], rows[0][1], cols[0][1]),
        End(rows[1][0], cols[1][0], rows[1][1], cols[1][1]),
    )


def _address(text: str, at: int) -> tuple[int, End, End | None] | None:
    """The reference at `at` in A1, a cell, a range of cells, whole columns or whole rows: its
    length and its ends."""
    if found := COLUMNS.match(text, at):
        start, end = _end(found[2], None, found[1], ""), _end(found[4], None, found[3], "")
    elif found := ROWS.match(text, at):
        start, end = _end(None, found[2], "", found[1]), _end(None, found[4], "", found[3])
    elif found := AREA.match(text, at):
        start = _end(found[2], found[4], found[1], found[3])
        end = _end(found[6], found[8], found[5], found[7]) if found[6] else start
    else:
        return None
    if start is None or end is None:
        return None
    if found.re is AREA and not found[6]:
        return found.end() - at, start, None
    return (found.end() - at, *_ordered(start, end))


class Token(NamedTuple):
    kind: str
    value: object = None


def _tokens(pieces: list, syntax: Syntax) -> list[Token]:
    tokens: list[Token] = []
    for piece in pieces:
        if isinstance(piece, str):
            tokens.extend(_lexed(piece, syntax))
        else:
            tokens.append(_held(piece))
    tokens.append(Token("end"))
    return tokens


def _point_of(point) -> Point | None:
    if not isinstance(point, dict) or (point.get("row"), point.get("col")) == (None, None):
        return None
    return Point(
        point.get("row"), point.get("col"), bool(point.get("absRow")), bool(point.get("absCol"))
    )


def _held(piece) -> Token:
    """A piece a table keeps as a reference; one that holds none is #REF!."""
    start = _point_of(piece.get("from")) if isinstance(piece, dict) else None
    end = _point_of(piece["to"]) if start and "to" in piece else None
    if start is None or (end is None and "to" in piece):
        return Token("error", "#REF!")
    return Token("ref", Held(piece.get("table"), start, end))


@cache
def _number(syntax: Syntax) -> re.Pattern:
    mark = re.escape(syntax.decimal)
    return re.compile(rf"(?:\d+(?:{mark}\d*)?|{mark}\d+)(?:[eE][+-]?\d+)?")


def _lexed(text: str, syntax: Syntax) -> list[Token]:
    number = _number(syntax)
    tokens: list[Token] = []
    braces = 0
    at = 0
    while at < len(text):
        char = text[at]
        if char in " \n\r":
            tokens.append(Token("space"))
            found = SPACE.match(text, at)
            at = found.end()
            continue
        if char == '"':
            end = at + 1
            while True:
                end = text.find('"', end)
                if end < 0:
                    raise Unreadable(text)
                if text.startswith('"', end + 1):
                    end += 2
                    continue
                break
            tokens.append(Token("text", text[at + 1 : end].replace('""', '"')))
            at = end + 1
            continue
        if char == "#":
            error = next((e for e in ERRORS if text[at:].upper().startswith(e)), None)
            if error is None:
                raise Unreadable(text)
            tokens.append(Token("error", error))
            at += len(error)
            continue
        if char in "{}()":
            braces += {"{": 1, "}": -1}.get(char, 0)
            tokens.append(Token(char))
            at += 1
            continue
        if char == syntax.list:
            tokens.append(Token("list"))
            at += 1
            continue
        if braces and char == syntax.row:
            tokens.append(Token("row"))
            at += 1
            continue
        named = NAME.match(text, at)
        if (char in "'[" or named and text.startswith("!", named.end())) and (
            found := SHEET.match(text, at)
        ):
            sheet = found[2].replace("''", "'") if found[2] else found[4]
            book = found[1] or found[3]
            book = int(book) if book else None
            if text[found.end() :].upper().startswith("#REF!"):
                tokens.append(Token("error", "#REF!"))
                at = found.end() + 5
                continue
            address = _address(text, found.end())
            if address is None:
                raise Unreadable(text)
            length, start, end = address
            tokens.append(Token("ref", Ref(sheet, start, end, book)))
            at = found.end() + length
            continue
        if (char == "$" or char in ASCII_LETTERS or char.isdecimal()) and (
            address := _address(text, at)
        ):
            length, start, end = address
            tokens.append(Token("ref", Ref(None, start, end)))
            at += length
            continue
        if (char.isdecimal() or char == syntax.decimal) and (found := number.match(text, at)):
            value = entered(found[0].replace(syntax.decimal, "."))
            if value is None:
                raise Unreadable(text)
            tokens.append(Token("number", value))
            at = found.end()
            continue
        if named:
            name = named[0]
            at = named.end()
            if text.startswith("(", at):
                tokens.append(Token("call", PREFIXES.sub("", name).upper()))
            elif text.startswith("[", at):
                depth, end = 0, at
                while end < len(text):
                    depth += {"[": 1, "]": -1}.get(text[end], 0)
                    end += 1
                    if not depth:
                        break
                if depth:
                    raise Unreadable(text)
                tokens.append(Token("ref", Structured(name, text[at:end])))
                at = end
            elif name.upper() in ("TRUE", "FALSE"):
                tokens.append(Token("logical", name.upper() == "TRUE"))
            else:
                tokens.append(Token("name", name))
            continue
        operator = next((op for op in OPERATORS if text.startswith(op, at)), None)
        if operator is None:
            raise Unreadable(text)
        tokens.append(Token("operator", operator))
        at += len(operator)
    return tokens


OPERANDS = {"ref", "name", "call", "("}


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.at = 0

    def peek(self, spaces: bool = False) -> Token:
        at = self.at
        while not spaces and self.tokens[at].kind == "space":
            at += 1
        return self.tokens[at]

    def take(self) -> Token:
        while self.tokens[self.at].kind == "space":
            self.at += 1
        token = self.tokens[self.at]
        self.at += 1
        return token

    def expect(self, kind: str) -> None:
        if self.take().kind != kind:
            raise Unreadable(kind)

    def intersects(self) -> bool:
        if self.tokens[self.at].kind != "space":
            return False
        after = self.at
        while self.tokens[after].kind == "space":
            after += 1
        return self.tokens[after].kind in OPERANDS

    def expression(self, bound: int = 0, union: bool = False):
        left = self.operand(union)
        while True:
            if self.intersects():
                op = " "
            else:
                token = self.peek()
                if token.kind == "operator" and token.value == "%":
                    if PERCENT <= bound:
                        break
                    self.take()
                    left = Postfix("%", left)
                    continue
                if token.kind == "operator" and token.value in BINARY:
                    op = token.value
                elif token.kind == "list" and union:
                    op = ","
                else:
                    break
            power = BINARY[op]
            if power <= bound:
                break
            if op == " ":
                self.skip_spaces()
            else:
                self.take()
            left = Binary(op, left, self.expression(power, union))
        return left

    def skip_spaces(self) -> None:
        while self.tokens[self.at].kind == "space":
            self.at += 1

    def operand(self, union: bool):
        token = self.take()
        match token.kind:
            case "number":
                return Number(token.value)
            case "text":
                return Text(token.value)
            case "logical":
                return Logical(token.value)
            case "error":
                return Error(token.value)
            case "ref":
                return token.value
            case "name":
                return Name(token.value)
            case "operator" if token.value in ("-", "+", "@"):
                return Prefix(token.value, self.expression(PREFIX_OPERATOR, union))
            case "(":
                inner = self.expression(0, union=True)
                self.expect(")")
                return Group(inner)
            case "{":
                return self.array()
            case "call":
                return self.call(token.value)
        raise Unreadable(token.kind)

    def call(self, name: str) -> Call:
        self.expect("(")
        args = []
        if self.peek().kind == ")":
            self.take()
            return Call(name, ())
        while True:
            if self.peek().kind in ("list", ")"):
                args.append(Missing())
            else:
                args.append(self.expression())
            token = self.take()
            if token.kind == ")":
                return Call(name, tuple(args))
            if token.kind != "list":
                raise Unreadable(name)

    def array(self) -> Array:
        rows, row = [], []
        while True:
            token = self.take()
            sign = 1
            if token.kind == "operator" and token.value in "-+":
                sign = -1 if token.value == "-" else 1
                token = self.take()
            match token.kind:
                case "number":
                    row.append(Number(sign * token.value))
                case "text" | "logical" | "error" if sign == 1:
                    row.append(
                        {"text": Text, "logical": Logical, "error": Error}[token.kind](token.value)
                    )
                case _:
                    raise Unreadable("array")
            token = self.take()
            if token.kind == "list":
                continue
            rows.append(tuple(row))
            row = []
            if token.kind == "row":
                continue
            if token.kind == "}" and len({len(each) for each in rows}) == 1:
                return Array(tuple(rows))
            raise Unreadable("array")


def parse(formula: str | list, syntax: Syntax = CANONICAL):
    """The tree of a formula, without its "=": given as text, or as the pieces a table keeps."""
    pieces = [formula] if isinstance(formula, str) else formula
    parser = _Parser(_tokens(pieces, syntax))
    if parser.peek().kind == "end":
        raise Unreadable("empty")
    tree = parser.expression()
    if parser.take().kind != "end":
        raise Unreadable("trailing")
    return tree


def relative(node, row: int, col: int):
    """The tree with each relative row and column of its references counted from the cell at
    `row` and `col`, as R1C1 writes them, so that every cell holding the same formula relative
    to its own has the same tree; it is computed, never written."""
    match node:
        case Ref(sheet, start, end, book):
            return Ref(sheet, _offset(start, row, col), end and _offset(end, row, col), book)
        case Call(name, args):
            return Call(name, tuple(relative(arg, row, col) for arg in args))
        case Prefix(op, operand) | Postfix(op, operand):
            return type(node)(op, relative(operand, row, col))
        case Binary(op, left, right):
            return Binary(op, relative(left, row, col), relative(right, row, col))
        case Group(inner):
            return Group(relative(inner, row, col))
    return node


def _offset(end: End, row: int, col: int) -> End:
    return End(
        end.row if end.abs_row or end.row is None else end.row - row,
        end.col if end.abs_col or end.col is None else end.col - col,
        end.abs_row,
        end.abs_col,
    )


def _point(end: End) -> str:
    text = ""
    if end.col is not None:
        text += ("$" if end.abs_col else "") + column_name(end.col)
    if end.row is not None:
        text += ("$" if end.abs_row else "") + str(end.row)
    return text


def _reference(node: Ref, quoted: bool = False) -> str:
    """A reference as Excel writes it; its sheet quoted always where it ends a range."""
    prefix = ""
    if node.sheet is not None:
        sheet = quote_sheet(node.sheet, quoted)
        if node.book is not None:
            here = f"[{node.book}]"
            sheet = "'" + here + sheet[1:] if sheet.startswith("'") else here + sheet
        prefix = sheet + "!"
    return prefix + _point(node.start) + (":" + _point(node.end) if node.end else "")


def written(node) -> str:
    """The formula of a tree in the canonical form, without its "="."""
    match node:
        case Number(value):
            return numeral(value)
        case Text(value):
            return '"' + value.replace('"', '""') + '"'
        case Logical(value):
            return "TRUE" if value else "FALSE"
        case Error(value):
            return value
        case Missing():
            return ""
        case Ref():
            return _reference(node)
        case Structured(table, spec):
            return table + spec
        case Name(name):
            return name
        case Call(name, args):
            function = FUNCTIONS.get(name)
            stored = function.stored if function else name
            return stored + "(" + ",".join(written(arg) for arg in args) + ")"
        case Prefix(op, operand):
            return op + written(operand)
        case Postfix(op, operand):
            return written(operand) + op
        case Binary(":", left, Ref() as right):
            return written(left) + ":" + _reference(right, quoted=True)
        case Binary(op, left, right):
            return written(left) + op + written(right)
        case Group(inner):
            return "(" + written(inner) + ")"
        case Array(rows):
            return "{" + ";".join(",".join(written(each) for each in row) for row in rows) + "}"
    raise TypeError(node)
