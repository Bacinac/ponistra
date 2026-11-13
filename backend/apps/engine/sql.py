"""Formulas computed in SQL (D22): each part of a formula a SQL expression of one kind, read as
another kind as Excel reads it, and NULL wherever SQL would not give Excel's value exactly, so
that the cell is computed by the Python forms instead. No part may raise: Postgres stops a whole
query at a float beyond its range, at one that underflows to 0 and at a division by zero, so
each operation is guarded before it runs. An expression used more than once is computed once,
bound in a subquery of its own, since SQL would compute it again wherever it is written."""

import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

from django.db import DatabaseError, connection, transaction

from . import criteria, formats, values
from .collation import collation
from .formats import CULTURES, Language
from .values import Blank, Error, stored

NUMBER = "number"
TEXT = "text"
LOGICAL = "logical"
VALUE = "value"
BLANK = "blank"

CANCELS = repr(2.0**-48)
NA = '{"error": "#N/A"}'
UNKNOWN = object()


class Unsupported(Exception):
    """A formula SQL does not compute; its cells are computed in Python."""


@dataclass(frozen=True)
class Typed:
    """A part of a formula as SQL: a float8 (NUMBER), text (TEXT), a boolean (LOGICAL), a jsonb
    value (VALUE: a number, a string, a boolean, null for an empty cell, {"error": code} for an
    error) or an argument left empty (BLANK). `simple` where it costs nothing to write it twice,
    `sure` where it is never NULL, `cell` where it is a reference to one cell, which a function
    taking a list reads as an area, None where it may be either; `known` the value of a
    constant."""

    sql: str
    kind: str
    simple: bool = False
    sure: bool = False
    cell: bool | None = False
    known: object = UNKNOWN


@dataclass(frozen=True)
class Range:
    """The cells of an area as a SQL source of rows (y, x, v): the row and column within it,
    each from 1, and the cell's value as VALUE gives it, an empty cell's among them. `height`
    and `width` are the area's, `extent` the rows and columns of it the source gives, a whole
    column or row cut to the cells its sheet holds (grid.bounded); `resized` the area of
    another size from the same first cell; `moves` where it is another for each cell
    compiled, its source reading where that cell is."""

    source: str
    height: int
    width: int
    extent: tuple[int, int]
    resized: Callable[[int, int], Range] = field(compare=False, repr=False)
    moves: bool = False


def _letters(first: int, last: int, excluded: str = "") -> str:
    return "".join(
        chr(code)
        for code in range(first, last + 1)
        if chr(code) not in excluded
        and len(chr(code).lower()) == 1
        and len(chr(code).upper()) == 1
        and chr(code).isprintable()
    )


# Letters whose case Python and a translation table change alike, one character to one, and that
# Python's regular expressions match regardless of case only as their lower case: the dotted and
# dotless i and the long s match others there.
CASED = _letters(0x20, 0x7E) + _letters(0xA0, 0x17E, "İıſ")


def _compared() -> tuple[str, list[str]]:
    """The letters of CASED whose texts compare as their lower cases do in every language
    (collation): each weighing as one steady letter, alike exactly where their lower cases are;
    and the case forms of a pair of them that a language weighs as one letter but does not
    take as that pair (Croatian lJ, which is no lj), which text holding them is left out by."""
    out = set(CASED)
    uneven = set()
    for code in CULTURES:
        weighed = collation(code)
        lowers: dict[bytes | None, set[str]] = {}
        keys: dict[str, set[bytes | None]] = {}
        for letter in CASED:
            key = weighed.key(tuple(map(ord, letter)))
            single = len(key.primary) == 2 and len(key.diacritics) == 1
            punctuation = not key.primary and not key.diacritics and len(key.rest[1]) == 1
            if not key.steady or not (single or punctuation):
                out.discard(letter)
            found = weighed.equality(letter)
            lowers.setdefault(found, set()).add(letter.lower())
            keys.setdefault(letter.lower(), set()).add(found)
        out -= {letter for letter in CASED if len(lowers[weighed.equality(letter)]) > 1}
        out -= {letter for letter in CASED if len(keys[letter.lower()]) > 1}
        pairs = {"".join(map(chr, units)) for units in weighed.compressions}
        for pair in pairs:
            forms = itertools.product(*({each.lower(), each.upper()} for each in pair))
            uneven.update(form for form in map("".join, forms) if form not in pairs)
    letters = "".join(sorted(out))
    return letters, sorted(form for form in uneven if all(each in letters for each in form))


COMPARED, UNEVEN = _compared()
LOWER = (
    "".join(c for c in CASED if c.lower() != c),
    "".join(c.lower() for c in CASED if c.lower() != c),
)
UPPER = (
    "".join(c for c in CASED if c.upper() != c),
    "".join(c.upper() for c in CASED if c.upper() != c),
)


def _class(letters: str) -> str:
    """A bracket expression of the letters, as ranges where they run on."""
    codes = sorted(map(ord, letters))
    runs: list[list[int]] = []
    for code in codes:
        if runs and code == runs[-1][1] + 1:
            runs[-1][1] = code
        else:
            runs.append([code, code])
    parts = []
    for first, last in runs:
        start, end = _escaped(chr(first)), _escaped(chr(last))
        parts.append(start if first == last else f"{start}-{end}")
    return "[" + "".join(parts) + "]"


def _escaped(letter: str) -> str:
    return "\\" + letter if letter in "\\]^-[" else letter


CASED_TEXT = "^" + _class(CASED) + "*$"
COMPARED_TEXT = "^" + _class(COMPARED) + "*$"


def compared_text(t: str) -> str:
    """Whether a text t compares as its lower case does (_compared)."""
    uneven = "".join(f" AND strpos({t}, {text_literal(form)}) = 0" for form in UNEVEN)
    return f"({t} ~ {text_literal(COMPARED_TEXT)}{uneven})"


def _even(given: str) -> bool:
    return all(each in COMPARED for each in given) and not any(form in given for form in UNEVEN)


def text_literal(text: str) -> str:
    if "\x00" in text:
        raise Unsupported("a text Postgres cannot hold")
    return "'" + text.replace("'", "''") + "'::text"


def number_literal(number: float) -> str:
    return f"'{number!r}'::float8"


def jsonb_literal(given) -> str:
    return "'" + json.dumps(stored(given)).replace("'", "''") + "'::jsonb"


def lowered(sql: str) -> str:
    """Text in lower case where CASED_TEXT holds for it."""
    return f"translate({sql}, {text_literal(LOWER[0])}, {text_literal(LOWER[1])})"


def uppered(sql: str) -> str:
    return f"translate({sql}, {text_literal(UPPER[0])}, {text_literal(UPPER[1])})"


def constant(given) -> Typed:
    """A value known when the formula is compiled."""
    match given:
        case bool():
            return Typed("true" if given else "false", LOGICAL, True, True, known=given)
        case float():
            return Typed(number_literal(given), NUMBER, True, True, known=given)
        case str():
            return Typed(text_literal(given), TEXT, True, True, known=given)
        case Blank():
            return Typed("'null'::jsonb", BLANK, True, True, known=given)
    raise Unsupported(given.value)


class Scope:
    """What compiling one formula shares: its language, the names of what it binds and `each`,
    a SELECT of the value of a part's SQL (v) in each cell compiled."""

    def __init__(self, language: Language, each: Callable[[str], str]):
        self.language = language
        self.each = each
        self._count = 0
        self._origins: dict[str, str] = {}

    def bound(self, given: list[Typed], body: Callable[[list[Typed]], Typed]) -> Typed:
        """The body over the parts given, each one not simple computed once before it."""
        columns = []
        names = []
        alias = None
        for each in given:
            if each.simple:
                names.append(each)
                continue
            if alias is None:
                self._count += 1
                alias = f"b{self._count}"
            name = f"{alias}.v{len(columns)}"
            columns.append(f"{each.sql} AS v{len(columns)}")
            self._origins[name] = self.origin(each.sql)
            names.append(replace(each, sql=name, simple=True))
        result = body(names)
        if not columns:
            return result
        return replace(
            result,
            sql=f"(SELECT {result.sql} FROM (SELECT {', '.join(columns)} OFFSET 0) AS {alias})",
            simple=False,
        )

    def origin(self, sql: str) -> str:
        """The SQL a name bound stands for, which reads nothing bound around it."""
        return self._origins.get(sql, sql)

    def read(self, query: str) -> list[tuple]:
        """The rows of a query, read off the database now."""
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchall()
        except DatabaseError as error:
            raise Unsupported(f"unread: {error}") from error


def value(given: Typed) -> Typed:
    """A part as a jsonb value."""
    if given.known is not UNKNOWN:
        return replace(given, sql=jsonb_literal(given.known), kind=VALUE)
    if given.kind in (NUMBER, TEXT, LOGICAL):
        return replace(given, sql=f"to_jsonb({given.sql})", kind=VALUE, simple=False)
    return given


def number(given: Typed, scope: Scope, logicals: bool = True) -> Typed:
    """A part read as one number (values.number): a logical as 1 or 0, an empty cell as 0, text
    as Excel reads it, which only a constant is read as here."""
    if given.known is not UNKNOWN:
        if isinstance(given.known, bool) and not logicals:
            raise Unsupported("#VALUE!")
        return constant(values.number(given.known, scope.language))
    if given.kind == NUMBER:
        return given
    if given.kind == LOGICAL:
        if not logicals:
            return Typed("NULL::float8", NUMBER, True)
        return replace(given, sql=f"({given.sql})::int::float8", kind=NUMBER, simple=False)
    if given.kind == TEXT:
        return Typed("NULL::float8", NUMBER, True)
    return scope.bound(
        [given],
        lambda v: Typed(
            f"CASE jsonb_typeof({v[0].sql}) WHEN 'number' THEN ({v[0].sql})::float8"
            + (f" WHEN 'boolean' THEN ({v[0].sql})::boolean::int::float8" if logicals else "")
            + " WHEN 'null' THEN 0::float8 END",
            NUMBER,
            cell=given.cell,
        ),
    )


def _numeral(x: str, mark: str) -> str:
    """A number as text in its fifteen significant digits (formats.numeral): plain from 1E-04
    up to 1E+15, where every such number fits plain; NULL beyond."""
    return (
        f"CASE WHEN {x} = 0 THEN '0' WHEN abs({x}) >= 1e-4 AND abs({x}) < 1e15 "
        f"THEN replace(trim_scale(({x})::numeric)::text, '.', {text_literal(mark)}) END"
    )


def text(given: Typed, scope: Scope) -> Typed:
    """A part read as text (values.text)."""
    if given.known is not UNKNOWN:
        return constant(values.text(given.known, scope.language))
    mark = formats.marks(scope.language.code)[0]
    if given.kind == TEXT:
        return given
    if given.kind == LOGICAL:
        return Typed(f"CASE {given.sql} WHEN true THEN 'TRUE' WHEN false THEN 'FALSE' END", TEXT)
    if given.kind == NUMBER:
        return scope.bound([given], lambda x: Typed(_numeral(x[0].sql, mark), TEXT))
    return scope.bound(
        [given],
        lambda v: Typed(
            f"CASE jsonb_typeof({v[0].sql}) WHEN 'string' THEN {v[0].sql} #>> '{{}}' "
            "WHEN 'null' THEN '' "
            f"WHEN 'boolean' THEN CASE ({v[0].sql})::boolean WHEN true THEN 'TRUE' "
            "ELSE 'FALSE' END "
            f"WHEN 'number' THEN {_numeral(f'({v[0].sql})::float8', mark)} END",
            TEXT,
            cell=given.cell,
        ),
    )


def _cell_text(c: str) -> str:
    return f"({c} #>> '{{}}')"


def _logical_of_text(t: str) -> str:
    return (
        f"CASE WHEN {t} ~ '^[A-Za-z]*$' "
        f"THEN CASE upper({t}) WHEN 'TRUE' THEN true WHEN 'FALSE' THEN false END END"
    )


def logical(given: Typed, scope: Scope) -> Typed:
    """A part read as a logical (values.logical): a number TRUE unless 0, text TRUE or FALSE."""
    if given.known is not UNKNOWN:
        return constant(values.logical(given.known, scope.language))
    if given.kind == LOGICAL:
        return given
    if given.kind == NUMBER:
        return Typed(f"({given.sql}) <> 0", LOGICAL)
    if given.kind == TEXT:
        return scope.bound([given], lambda t: Typed(_logical_of_text(t[0].sql), LOGICAL))
    return scope.bound(
        [given],
        lambda v: Typed(
            f"CASE jsonb_typeof({v[0].sql}) WHEN 'boolean' THEN ({v[0].sql})::boolean "
            f"WHEN 'number' THEN ({v[0].sql})::float8 <> 0 WHEN 'null' THEN false "
            f"WHEN 'string' THEN {_logical_of_text(_cell_text(v[0].sql))} END",
            LOGICAL,
            cell=given.cell,
        ),
    )


def _nullable(names: list[Typed]) -> str:
    tests = [f"{each.sql} IS NULL" for each in names if not each.sure]
    return f"WHEN {' OR '.join(tests)} THEN NULL " if tests else ""


def _sum(a: str, b: str, op: str) -> str:
    return f"CASE WHEN abs({a}) < 8e307 AND abs({b}) < 8e307 THEN {a} {op} {b} + 0 END"


def _settled(a: str, b: str, op: str) -> str:
    """A sum or difference that is 0 where its operands cancel (values.cancelled); NULL where
    they are too small to tell, as multiplying by 2^-48 would underflow."""
    other = f"{b} < 0" if op == "+" else f"{b} > 0"
    larger = f"greatest(abs({a}), abs({b}))"
    return (
        f"CASE WHEN abs({a}) < 8e307 AND abs({b}) < 8e307 THEN "
        f"CASE WHEN ({a} < 0) = ({other}) THEN {a} {op} {b} + 0 "
        f"WHEN {larger} >= 1e-300 THEN CASE WHEN abs({a} {op} {b}) < {larger} * {CANCELS} "
        f"THEN 0::float8 ELSE {a} {op} {b} + 0 END END END"
    )


def _product(a: Typed, b: Typed) -> str:
    x, y = a.sql, b.sql
    return (
        f"CASE {_nullable([a, b])}WHEN {x} = 0 OR {y} = 0 THEN 0::float8 "
        f"WHEN abs({x}) <= 1e308 / greatest(abs({y}), 1) "
        f"AND abs({x}) >= 1e-300 / least(abs({y}), 1) "
        f"THEN {x} * {y} + 0 END"
    )


def _quotient(a: Typed, b: Typed) -> str:
    x, y = a.sql, b.sql
    return (
        f"CASE {_nullable([a, b])}WHEN {y} = 0 THEN NULL WHEN {x} = 0 THEN 0::float8 "
        f"WHEN abs({x}) <= 1e308 * least(abs({y}), 1) "
        f"AND abs({x}) >= 1e-300 * greatest(abs({y}), 1) "
        f"THEN {x} / {y} + 0 END"
    )


def _power(a: Typed, b: Typed) -> str:
    """values.power where the result is well within a float: a positive base, or a negative one
    to a whole power."""
    x, y = a.sql, b.sql
    return (
        f"CASE {_nullable([a, b])}WHEN {x} = 0 THEN CASE WHEN {y} > 0 THEN 0::float8 END "
        f"WHEN {y} = 0 THEN 1::float8 "
        f"WHEN ({x} > 0 OR {y} = trunc({y})) AND abs({y}) BETWEEN 1e-100 AND 1e100 "
        f"AND abs({y} * ln(abs({x}))) < 700 THEN power({x}, {y}) + 0 END"
    )


def arithmetic(op: str, left: Typed, right: Typed, scope: Scope, settling: bool = False) -> Typed:
    """An operation on two numbers (evaluate.ARITHMETIC), NULL where Excel gives an error."""
    left, right = number(left, scope), number(right, scope)

    def body(names: list[Typed]) -> Typed:
        a, b = names
        match op:
            case "+" | "-":
                sql = (_settled if settling else _sum)(a.sql, b.sql, op)
            case "*":
                sql = _product(a, b)
            case "/":
                sql = _quotient(a, b)
            case "^":
                sql = _power(a, b)
            case _:
                raise Unsupported(op)
        return Typed(sql, NUMBER)

    return scope.bound([left, right], body)


def negated(given: Typed, scope: Scope) -> Typed:
    given = number(given, scope)
    if given.known is not UNKNOWN:
        return constant(values.finite(-given.known))
    return Typed(f"(0::float8 - {given.sql})", NUMBER)


def percent(given: Typed, scope: Scope) -> Typed:
    given = number(given, scope)
    if given.known is not UNKNOWN:
        return constant(values.finite(given.known / 100))
    return scope.bound(
        [given],
        lambda x: Typed(
            f"CASE WHEN abs({x[0].sql}) >= 1e-300 OR {x[0].sql} = 0 THEN {x[0].sql} / 100 + 0 END",
            NUMBER,
        ),
    )


def joined(left: Typed, right: Typed, scope: Scope) -> Typed:
    return Typed(f"({text(left, scope).sql} || {text(right, scope).sql})", TEXT)


def same_text(a: str, b: str) -> str:
    """Whether two texts are equal as Excel compares them (values.compare), NULL where the
    collation could tell otherwise than their lower case."""
    return (
        f"CASE WHEN {compared_text(a)} AND {compared_text(b)} THEN {lowered(a)} = {lowered(b)} END"
    )


RANKS = {NUMBER: 0, TEXT: 1, LOGICAL: 2}


def _rank(v: str) -> str:
    return f"CASE jsonb_typeof({v}) WHEN 'number' THEN 0 WHEN 'string' THEN 1 ELSE 2 END"


def _nothing(v: str) -> str:
    return (
        f"CASE jsonb_typeof({v}) WHEN 'string' THEN '\"\"'::jsonb "
        "WHEN 'boolean' THEN 'false'::jsonb ELSE '0'::jsonb END"
    )


def compared(op: str, left: Typed, right: Typed, scope: Scope) -> Typed:
    """A comparison (evaluate.COMPARISONS) as values.compare orders: numbers to fifteen
    significant digits, then text regardless of case, then logicals, an empty cell as the
    other side's nothing; text is only held equal or not here."""
    if left.known is not UNKNOWN and right.known is not UNKNOWN:
        return constant(_holds(op, values.compare(left.known, right.known, scope.language)))
    if left.kind == BLANK and right.kind in RANKS:
        left = constant(_nothing_of(right.kind))
    elif right.kind == BLANK and left.kind in RANKS:
        right = constant(_nothing_of(left.kind))
    if left.kind in RANKS and right.kind in RANKS:
        return scope.bound([left, right], lambda names: _static_comparison(op, *names))
    if left.known is not UNKNOWN or right.known is not UNKNOWN:
        flipped = left.known is not UNKNOWN
        known, given = (left, right) if flipped else (right, left)
        return scope.bound(
            [value(given)],
            lambda v: _against(op, v[0].sql, known.known, scope.language, flipped),
        )
    return scope.bound([value(left), value(right)], lambda names: _dynamic_comparison(op, *names))


def _nothing_of(kind: str):
    return {NUMBER: 0.0, TEXT: "", LOGICAL: False}[kind]


def _static_comparison(op: str, a: Typed, b: Typed) -> Typed:
    if a.kind != b.kind:
        result = "true" if _holds(op, RANKS[a.kind] - RANKS[b.kind]) else "false"
        nullable = _nullable([a, b])
        return Typed(f"CASE {nullable}ELSE {result} END" if nullable else result, LOGICAL)
    if a.kind == NUMBER:
        return Typed(f"(({a.sql})::numeric {op} ({b.sql})::numeric)", LOGICAL)
    if a.kind == LOGICAL:
        return Typed(f"({a.sql} {op} {b.sql})", LOGICAL)
    if op not in ("=", "<>"):
        raise Unsupported("text ordered as Excel's collation orders it")
    same = same_text(a.sql, b.sql)
    return Typed(same if op == "=" else f"NOT {same}", LOGICAL)


def _holds(op: str, order: int) -> bool:
    return {
        "=": order == 0,
        "<>": order != 0,
        "<": order < 0,
        ">": order > 0,
        "<=": order <= 0,
        ">=": order >= 0,
    }[op]


def _against(op: str, v: str, known, language: Language, flipped: bool) -> Typed:
    """A value v compared with one known when compiling, which never meets a cast in SQL:
    Postgres would fold the cast of a constant while planning and stop at one that fails."""

    def ordered(given: str, other: str) -> str:
        return f"{other} {op} {given}" if flipped else f"{given} {op} {other}"

    def static(sample) -> str:
        order = values.compare(sample, known, language)
        return "true" if _holds(op, -order if flipped else order) else "false"

    blank = isinstance(known, Blank)
    if blank or isinstance(known, float):
        other = number_literal(0.0 if blank else known)
        number = ordered(f"({v})::float8::numeric", f"{other}::numeric")
    else:
        number = static(0.0)
    if (blank or isinstance(known, str)) and op in ("=", "<>"):
        same = same_text(_cell_text(v), text_literal("" if blank else known))
        string = same if op == "=" else f"NOT {same}"
    elif blank or isinstance(known, str):
        string = "NULL::boolean"
    else:
        string = static("")
    if blank or isinstance(known, bool):
        logical_ = ordered(f"({v})::boolean", "true" if known is True else "false")
    else:
        logical_ = static(False)
    return Typed(
        f"CASE jsonb_typeof({v}) WHEN 'null' THEN {static(Blank())} WHEN 'number' THEN {number} "
        f"WHEN 'string' THEN {string} WHEN 'boolean' THEN {logical_} END",
        LOGICAL,
    )


def _dynamic_comparison(op: str, a: Typed, b: Typed) -> Typed:
    left = f"CASE WHEN {a.sql} = 'null'::jsonb THEN {_nothing(b.sql)} ELSE {a.sql} END"
    right = f"CASE WHEN {b.sql} = 'null'::jsonb THEN {_nothing(a.sql)} ELSE {b.sql} END"
    texts = (
        same_text(f"({left} #>> '{{}}')", f"({right} #>> '{{}}')")
        if op in ("=", "<>")
        else "NULL::boolean"
    )
    if op == "<>":
        texts = f"NOT {texts}"
    return Typed(
        f"CASE WHEN jsonb_typeof({a.sql}) = 'object' OR jsonb_typeof({b.sql}) = 'object' THEN NULL "
        f"WHEN jsonb_typeof({left}) <> jsonb_typeof({right}) "
        f"THEN {_rank(left)} {op} {_rank(right)} "
        f"WHEN jsonb_typeof({left}) = 'number' "
        f"THEN ({left})::float8::numeric {op} ({right})::float8::numeric "
        f"WHEN jsonb_typeof({left}) = 'boolean' THEN ({left})::boolean {op} ({right})::boolean "
        f"ELSE {texts} END",
        LOGICAL,
    )


def elements(
    items: list,
    in_area: Callable[[str], str],
    read: Callable[[Typed], Typed],
    given: Callable[[str], str],
) -> str:
    """A source of the elements of a list in order (k, y, x and the columns read): each cell
    of an area or of a reference to one cell as `in_area` reads its value, each value given
    itself first `read`, then as `given` reads it."""
    rows = []
    for at, item in enumerate(items):
        if isinstance(item, Range):
            rows.append(f"SELECT {at} AS k, e.y, e.x, {in_area('e.v')} FROM {item.source} AS e")
        elif item.cell:
            rows.append(
                f"SELECT {at} AS k, 1 AS y, 1 AS x, {in_area('e.v')} "
                f"FROM (SELECT {value(item).sql} AS v OFFSET 0) AS e"
            )
        else:
            rows.append(
                f"SELECT {at} AS k, 1 AS y, 1 AS x, {given('e.g')} "
                f"FROM (SELECT {read(item).sql} AS g OFFSET 0) AS e"
            )
    return "(" + " UNION ALL ".join(rows) + ")"


def _pattern(written: str) -> str:
    """A criterion's pattern (criteria.fits) as a regular expression over text in lower case."""
    out = []
    for at, part in enumerate(criteria.parts(written, criteria.ANY)):
        if at % 2:
            out.append(".*" if part == "*" else ".")
            continue
        if not _even(part):
            raise Unsupported("a letter whose case SQL may change otherwise")
        out += [each if each.isalnum() else "\\" + each for each in part.lower()]
    return "^(?:" + "".join(out) + ")$"


def _same_cased(c: str, written: str) -> str:
    """Whether a cell is text a criterion matches (criteria._equal_to); NULL for text SQL may
    compare otherwise (compared_text)."""
    found = criteria.literal(written)
    if found is None:
        test = f"{lowered(_cell_text(c))} ~ {text_literal(_pattern(written))}"
    else:
        if not _even(found):
            raise Unsupported("a letter whose case SQL may change otherwise")
        test = f"{lowered(_cell_text(c))} = {text_literal(found.lower())}"
    return (
        f"CASE WHEN jsonb_typeof({c}) = 'string' THEN CASE WHEN {compared_text(_cell_text(c))} "
        f"THEN {test} END ELSE false END"
    )


UNSURE = "x"


def key(v: str) -> str:
    """The key a lookup finds a value v by, two values having the same where criteria.equal
    holds them equal: a number by its fifteen significant digits, text by its lower case, a
    logical and an empty cell as themselves; UNSURE for text SQL may compare otherwise
    (compared_text), NULL for an error, which no lookup finds."""
    t = _cell_text(v)
    return (
        f"CASE jsonb_typeof({v}) "
        f"WHEN 'number' THEN 'n' || trim_scale(({v})::float8::numeric)::text "
        f"WHEN 'string' THEN CASE WHEN {compared_text(t)} "
        f"THEN 's' || {lowered(t)} ELSE '{UNSURE}' END "
        f"WHEN 'boolean' THEN 'b' || ({v})::text WHEN 'null' THEN 'e' END"
    )


def known_key(given) -> str:
    """key of a value known when compiling."""
    match given:
        case Blank():
            return "e"
        case bool():
            return "btrue" if given else "bfalse"
        case float():
            return "n" + format(Decimal(f"{given + 0.0:.15g}").normalize(), "f")
        case str() if _even(given):
            return "s" + given.lower()
    raise Unsupported("a value SQL keys otherwise")


def _equal_to(given) -> Callable[[str], str]:
    """criteria._equal_to: a number matches text that reads as it too, which only text holding
    a digit can."""
    match given:
        case bool() | Error():
            return lambda c: f"({c} = {jsonb_literal(given)})"
        case float():
            return lambda c: (
                f"CASE jsonb_typeof({c}) WHEN 'number' "
                f"THEN ({c})::float8::numeric = ({number_literal(given)})::numeric "
                f"WHEN 'string' THEN CASE WHEN {_cell_text(c)} ~ '[0-9]' THEN NULL ELSE false END "
                "ELSE false END"
            )
    return lambda c: _same_cased(c, given)


def matching(given: Typed, language: Language) -> Callable[[str], str]:
    """The test a criterion known when compiling puts to a cell's value c (criteria.criterion),
    NULL where SQL cannot tell."""
    if given.known is UNKNOWN:
        raise Unsupported("a criterion computed")
    found = given.known
    if isinstance(found, Blank):
        found = 0.0
    if not isinstance(found, str):
        return _equal_to(found)
    op, written = criteria.split(found)
    if written == "":
        match op:
            case "=":
                return lambda c: f"({c} = 'null'::jsonb)"
            case "<>":
                return lambda c: f"({c} <> 'null'::jsonb)"
            case "":
                return lambda c: f"({c} = 'null'::jsonb OR {c} = '\"\"'::jsonb)"
        return lambda c: "false"
    operand = criteria.operand(written, language)
    if op in ("", "="):
        return _equal_to(operand)
    if op == "<>":
        if isinstance(operand, float):
            return lambda c: (
                f"CASE WHEN jsonb_typeof({c}) = 'number' "
                f"THEN ({c})::float8::numeric <> ({number_literal(operand)})::numeric ELSE true END"
            )
        test = _equal_to(operand)
        return lambda c: f"(NOT {test(c)})"
    match operand:
        case bool():
            return lambda c: (
                f"CASE WHEN jsonb_typeof({c}) = 'boolean' THEN ({c})::boolean {op} {operand} "
                "ELSE false END"
            )
        case float():
            return lambda c: (
                f"CASE WHEN jsonb_typeof({c}) = 'number' "
                f"THEN ({c})::float8::numeric {op} ({number_literal(operand)})::numeric "
                "ELSE false END"
            )
        case str():
            return lambda c: (
                f"CASE WHEN jsonb_typeof({c}) = 'string' THEN NULL::boolean ELSE false END"
            )
    raise Unsupported("an error ordered")


def numbers(found: list, scope: Scope) -> str:
    """A source of the numbers of a list (grid.numbers) in order (k, y, x, n, bad): an area's
    numbers, bad at an error in it, and each value given itself read as a number, bad where it
    is NULL."""
    return elements(
        found,
        lambda v: (
            f"CASE WHEN jsonb_typeof({v}) = 'number' THEN ({v})::float8 END AS n, "
            f"jsonb_typeof({v}) = 'object' AS bad"
        ),
        lambda given: number(given, scope),
        lambda g: f"{g} AS n, {g} IS NULL AS bad",
    )
