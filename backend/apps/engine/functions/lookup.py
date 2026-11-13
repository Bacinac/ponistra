import math
import re
from dataclasses import replace

from .. import collation, sql
from ..criteria import equal, wild
from ..grid import Area, Union, table
from ..parse import LAST_COL, LAST_ROW, Binary, Ref, Unreadable, column_name, parse, quote_sheet
from ..values import ERROR_TYPES, NA, REF, VALUE, Blank, Error, Matrix, compare, significant
from . import form, sql_form


def _line(context, given) -> tuple[list, bool] | Error:
    """The values of a row or column to search, and whether it is a column."""
    found = table(context, given)
    if isinstance(found, Error):
        return found
    if found.width == 1:
        return [row[0] for row in found.rows], True
    if found.height == 1:
        return list(found.rows[0]), False
    return VALUE


def _alike(each, sought) -> bool:
    return type(each) is type(sought) and not isinstance(each, Error | Blank)


def _approximate(line: list, sought, context) -> int | None:
    """Where Excel's halving of a line sorted up finds the value sought (MATCH 1, VLOOKUP and
    LOOKUP): from the middle of what is left it takes the first value of the sought's kind on
    its right, or the left half where none is there; an equal value gives the last of the equal
    ones after it, a smaller the right half and a larger the left, and where none is equal the
    last smaller one taken."""
    language = context.language
    low, high, best = 0, len(line) - 1, None
    while low <= high:
        middle = (low + high) // 2
        at = next((at for at in range(middle, high + 1) if _alike(line[at], sought)), None)
        if at is None:
            high = middle - 1
            continue
        order = compare(line[at], sought, language)
        if order == 0:
            while (
                at + 1 < len(line)
                and _alike(line[at + 1], sought)
                and compare(line[at + 1], sought, language) == 0
            ):
                at += 1
            return at
        if order < 0:
            best, low = at, at + 1
        else:
            high = at - 1
    return best


def _descending(line: list, sought, context) -> int | None:
    """Where MATCH -1 finds the value sought in a line sorted down, going along it among values
    of its kind: the first equal one, else the last larger before a smaller one."""
    best = None
    for at, each in enumerate(line):
        if not _alike(each, sought):
            continue
        order = compare(each, sought, context.language)
        if order == 0:
            return at
        if order < 0:
            break
        best = at
    return best


EMPTY = 4


def _ranked(given) -> int:
    match given:
        case float():
            return 0
        case str():
            return 1
        case bool():
            return 2
        case Error():
            return 3
    return EMPTY


def _side(each, sought, language) -> int:
    """Where a value stands to the one XMATCH and XLOOKUP seek the nearest of: by its kind
    (_ranked), then by compare, every error and every empty cell alike."""
    kinds = _ranked(each), _ranked(sought)
    if kinds[0] != kinds[1]:
        return (kinds[0] > kinds[1]) - (kinds[0] < kinds[1])
    if kinds[0] > 2:
        return 0
    order = compare(each, sought, language)
    return (order > 0) - (order < 0)


def _halved(line: list, sought, context, mode: int, down: bool) -> int | None:
    """Where XMATCH and XLOOKUP searching by halves (±2) find the value sought: every value
    ordered by _side, the first equal one of a line sorted up or the last of one sorted down,
    else by the mode the last smaller or larger one met."""
    low, high, met = 0, len(line) - 1, {}
    while low <= high:
        middle = (low + high) // 2
        order = _side(line[middle], sought, context.language)
        met[order] = middle
        if (order >= 0) if down else (order < 0):
            low = middle + 1
        else:
            high = middle - 1
    return met.get(0, met.get(mode) if mode else None)


def _exact(line: list, sought, context, wildcards: bool, backwards: bool = False) -> int | None:
    order = range(len(line) - 1, -1, -1) if backwards else range(len(line))
    return next((at for at in order if equal(sought, line[at], context.language, wildcards)), None)


def _part(given, at: int, column: bool, count: int = 1):
    """The row (or column) of an area or array that a position along the other way gives."""
    if isinstance(given, Area):
        if column:
            return Area(
                given.sheet, given.top + at, given.left, given.top + at + count - 1, given.right
            )
        return Area(
            given.sheet, given.top, given.left + at, given.bottom, given.left + at + count - 1
        )
    rows = (
        given.rows[at : at + count] if column else tuple(row[at : at + count] for row in given.rows)
    )
    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]
    return Matrix(rows)


def _vlookup(context, sought, given, index, approximate, vertical: bool):
    if isinstance(sought, Error):
        return sought
    if isinstance(sought, Blank):
        sought = 0.0
    found = table(context, given)
    if isinstance(found, Error):
        return found
    index = math.trunc(index)
    if index < 1:
        return VALUE
    if index > (found.width if vertical else found.height):
        return REF
    line = [row[0] for row in found.rows] if vertical else list(found.rows[0])
    if approximate:
        at = _approximate(line, sought, context)
    else:
        at = _exact(line, sought, context, True)
    if at is None:
        return NA
    return found.rows[at][index - 1] if vertical else found.rows[index - 1][at]


@form("VLOOKUP")
def vlookup(context, sought, given, index, approximate=True):
    return _vlookup(context, sought, given, index, approximate, True)


@form("HLOOKUP")
def hlookup(context, sought, given, index, approximate=True):
    return _vlookup(context, sought, given, index, approximate, False)


def _xfind(context, sought, line, mode, search):
    mode, search = math.trunc(mode), math.trunc(search)
    if mode not in (-1, 0, 1, 2) or search not in (-2, -1, 1, 2):
        return VALUE
    if search in (-2, 2):
        return VALUE if mode == 2 else _halved(line, sought, context, mode, search < 0)
    backwards = search in (-1, -2)
    at = _exact(line, sought, context, mode == 2, backwards)
    if at is not None or mode in (0, 2):
        return at
    language, best = context.language, None
    for each in range(len(line) - 1, -1, -1) if backwards else range(len(line)):
        value = line[each]
        if _side(value, sought, language) == mode and (
            best is None or _side(value, line[best], language) == -mode
        ):
            best = each
    return best


@form("XLOOKUP")
def xlookup(context, sought, lookup, returned, if_not_found=None, mode=0.0, search=1.0):
    if isinstance(sought, Error):
        return sought
    line = _line(context, lookup)
    if isinstance(line, Error):
        return line
    values, column = line
    if isinstance(returned, Error):
        return returned
    if not isinstance(returned, Area):
        returned = table(context, returned)
    if isinstance(lookup, Area):
        size = lookup.height if column else lookup.width
    else:
        size = len(values)
    if (returned.height if column else returned.width) != size:
        return VALUE
    at = _xfind(context, sought, values, mode, search)
    if isinstance(at, Error):
        return at
    if at is None:
        return NA if if_not_found is None or isinstance(if_not_found, Blank) else if_not_found
    return _part(returned, at, column)


@form("MATCH")
def match(context, sought, lookup, kind=1.0):
    if isinstance(sought, Error):
        return sought
    if isinstance(sought, Blank):
        sought = 0.0
    line = _line(context, lookup)
    if isinstance(line, Error):
        return line
    values = line[0]
    kind = math.trunc(kind)
    if kind == 0:
        at = _exact(values, sought, context, True)
    else:
        at = (_descending if kind < 0 else _approximate)(values, sought, context)
    return NA if at is None else at + 1


@form("XMATCH")
def xmatch(context, sought, lookup, mode=0.0, search=1.0):
    if isinstance(sought, Error):
        return sought
    line = _line(context, lookup)
    if isinstance(line, Error):
        return line
    at = _xfind(context, sought, line[0], mode, search)
    if isinstance(at, Error):
        return at
    return NA if at is None else at + 1


def sorting(a, b, order: int, language) -> int:
    """How SORT orders two values, up for an order of 1 and down for -1: by kind (_ranked),
    each kind as compare orders it and errors by their codes, empty cells last either way."""
    kinds = _ranked(a), _ranked(b)
    if EMPTY in kinds:
        return (kinds[0] > kinds[1]) - (kinds[0] < kinds[1])
    if kinds[0] != kinds[1]:
        return ((kinds[0] > kinds[1]) - (kinds[0] < kinds[1])) * order
    if isinstance(a, Error):
        a, b = ERROR_TYPES[a.value], ERROR_TYPES[b.value]
        return ((a > b) - (a < b)) * order
    return compare(a, b, language) * order


def _key(value) -> tuple:
    match value:
        case float():
            return 0, significant(value)
        case bool():
            return 2, value
        case Error():
            return 3, ERROR_TYPES[value.value]
    return 1, value


def sorted_by[T](items: list[T], value, descending: bool, language) -> list[T]:
    """The items in the order SORT gives their values: by Excel's merges (collation.sort) where
    text is among them, which Windows compares in no consistent order, else by the values'
    kinds and the values themselves, which merge as any stable sort would."""
    values = [value(item) for item in items]
    if any(isinstance(each, str) for each in values):
        order = -1 if descending else 1
        pairs = collation.sort(
            list(zip(values, items, strict=True)),
            lambda left, right: sorting(left[0], right[0], order, language),
        )
        return [item for _, item in pairs]
    filled = [
        (each, item)
        for each, item in zip(values, items, strict=True)
        if not isinstance(each, Blank)
    ]
    empty = [item for each, item in zip(values, items, strict=True) if isinstance(each, Blank)]
    ordered = sorted(filled, key=lambda pair: _key(pair[0]), reverse=descending)
    return [item for _, item in ordered] + empty


@form("SORT")
def sort_(context, given, index=1.0, order=1.0, by_col=False):
    """The rows (or with by_col the columns) of an array as SORT orders them by one column (or
    row): by Excel's merges (collation.sort), numbers before text, logicals and errors, each
    kind as compare orders it and errors by their codes, the other way round for a descending
    order, and empty cells last either way."""
    found = table(context, given)
    if isinstance(found, Error):
        return found
    index, order = math.floor(index), math.floor(order)
    lines = list(zip(*found.rows, strict=True)) if by_col else list(found.rows)
    if order not in (1, -1) or not 1 <= index <= len(lines[0]):
        return VALUE
    ordered = sorted_by(lines, lambda line: line[index - 1], order < 0, context.language)
    return Matrix(tuple(zip(*ordered, strict=True)) if by_col else tuple(ordered))


@form("LOOKUP")
def lookup_(context, sought, vector, result=None):
    if isinstance(sought, Error):
        return sought
    if isinstance(sought, Blank):
        sought = 0.0
    found = table(context, vector)
    if isinstance(found, Error):
        return found
    if result is None:
        column = found.height >= found.width
        line = [row[0] for row in found.rows] if column else list(found.rows[0])
        at = _approximate(line, sought, context)
        if at is None:
            return NA
        return found.rows[at][-1] if column else found.rows[-1][at]
    line = _line(context, vector)
    if isinstance(line, Error):
        return line
    at = _approximate(line[0], sought, context)
    if at is None:
        return NA
    returned = table(context, result)
    if isinstance(returned, Error):
        return returned
    flat = list(returned.values())
    return flat[at] if at < len(flat) else NA


@form("INDEX")
def index(context, given, row, col=None, area=None):
    if isinstance(given, Error):
        return given
    if isinstance(given, Union):
        number = math.trunc(area) if area is not None else 1
        if not 1 <= number <= len(given.areas):
            return REF
        given = given.areas[number - 1]
    if not isinstance(given, Area | Matrix):
        given = Matrix(((given,),))
    height, width = given.height, given.width
    row = math.trunc(row)
    if col is None:
        if height == 1 and width > 1:
            row, col = 1, row
        else:
            col = 0 if width > 1 else 1
    col = math.trunc(col)
    if row < 0 or col < 0:
        return VALUE
    if row > height or col > width:
        return REF
    if row and col:
        if isinstance(given, Area):
            top, left = given.top + row - 1, given.left + col - 1
            return Area(given.sheet, top, left, top, left)
        return given.rows[row - 1][col - 1]
    if row:
        return _part(given, row - 1, True)
    if col:
        return _part(given, col - 1, False)
    return given


@form("CHOOSE")
def choose(context, number, *options):
    at = math.trunc(number)
    if not 1 <= at <= len(options):
        return VALUE
    return options[at - 1]()


@form("ROW")
def row(context, reference=None):
    if reference is None:
        return context.row
    first = reference.areas[0] if isinstance(reference, Union) else reference
    return first.top


@form("COLUMN")
def column(context, reference=None):
    if reference is None:
        return context.col
    first = reference.areas[0] if isinstance(reference, Union) else reference
    return first.left


@form("ROWS")
def rows(context, given):
    if isinstance(given, Error):
        return given
    if isinstance(given, Area | Matrix):
        return given.height
    return VALUE if isinstance(given, Union) else 1


@form("COLUMNS")
def columns(context, given):
    if isinstance(given, Error):
        return given
    if isinstance(given, Area | Matrix):
        return given.width
    return VALUE if isinstance(given, Union) else 1


@form("OFFSET")
def offset(context, reference, rows_, cols, height=None, width=None):
    if isinstance(reference, Union):
        return VALUE
    tall = math.trunc(height) if height is not None else reference.height
    wide = math.trunc(width) if width is not None else reference.width
    if tall == 0 or wide == 0:
        return REF
    top, left = reference.top + math.trunc(rows_), reference.left + math.trunc(cols)
    if tall < 0:
        top, tall = top + tall + 1, -tall
    if wide < 0:
        left, wide = left + wide + 1, -wide
    bottom, right = top + tall - 1, left + wide - 1
    if top < 1 or left < 1 or bottom > LAST_ROW or right > LAST_COL:
        return REF
    return Area(reference.sheet, top, left, bottom, right)


_R1C1 = re.compile(r"R(\[-?\d+\]|\d+)?C(\[-?\d+\]|\d+)?", re.IGNORECASE)
_SHEET = re.compile(r"^(?:'((?:[^']|'')+)'|([^'!]+))!")


def _r1c1(text: str, here: int) -> int | None:
    if not text:
        return here
    if text.startswith("["):
        return here + int(text[1:-1])
    return int(text)


def _area(context, sheet: str | None, top, left, bottom, right):
    sheet = sheet or context.sheet
    if context.book.extent(sheet) is None:
        return REF
    if min(top, left) < 1 or bottom > LAST_ROW or right > LAST_COL:
        return REF
    return Area(sheet, min(top, bottom), min(left, right), max(top, bottom), max(left, right))


@form("INDIRECT")
def indirect(context, text, a1=True):
    if a1:
        try:
            tree = parse(text)
        except Unreadable:
            return REF
        ends = [tree] if isinstance(tree, Ref) else []
        if isinstance(tree, Binary) and tree.op == ":":
            ends = [tree.left, tree.right]
        if not ends or not all(isinstance(each, Ref) and each.book is None for each in ends):
            return REF
        first, last = ends[0], ends[-1]
        start, end = first.start, (last.end or last.start)
        return _area(
            context,
            first.sheet,
            start.row or 1,
            start.col or 1,
            end.row or LAST_ROW,
            end.col or LAST_COL,
        )
    sheet = None
    if found := _SHEET.match(text):
        sheet = (found[1] or "").replace("''", "'") or found[2]
        text = text[found.end() :]
    corners = text.split(":")
    if not 1 <= len(corners) <= 2:
        return REF
    points = []
    for corner in corners:
        found = _R1C1.fullmatch(corner)
        if not found:
            return REF
        points.append((_r1c1(found[1], context.row), _r1c1(found[2], context.col)))
    (top, left), (bottom, right) = points[0], points[-1]
    return _area(context, sheet, top, left, bottom, right)


@form("HYPERLINK")
def hyperlink(context, link, friendly=None):
    return link if friendly is None else friendly


@form("ADDRESS")
def address(context, row_, col, kind=1.0, a1=True, sheet=None):
    row_, col, kind = math.trunc(row_), math.trunc(col), math.trunc(kind)
    if not 1 <= row_ <= LAST_ROW or not 1 <= col <= LAST_COL or kind not in (1, 2, 3, 4):
        return VALUE
    fixed_row, fixed_col = kind in (1, 2), kind in (1, 3)
    if a1:
        text = (
            ("$" if fixed_col else "") + column_name(col) + ("$" if fixed_row else "") + str(row_)
        )
    else:
        text = f"R{row_ if fixed_row else f'[{row_}]'}C{col if fixed_col else f'[{col}]'}"
    return (quote_sheet(sheet) + "!" if sheet else "") + text


def _whole(given: sql.Typed | None, default: float) -> int:
    """A number known when compiling, truncated, as the lookups read their modes."""
    if given is None:
        return int(default)
    if given.known is sql.UNKNOWN or isinstance(given.known, bool):
        raise sql.Unsupported("a mode computed")
    return math.trunc(given.known)


def _line_sql(given: sql.Range) -> str:
    """Which way a line of cells runs (_line): y down a column, x along a row."""
    rows, cols = given.extent
    if cols == 1:
        return "y"
    if rows == 1:
        return "x"
    raise sql.Unsupported("#VALUE!")


NOT_FOUND = f"'{sql.NA}'::jsonb"


def _map(line: str, axis: str, beside: str, backwards: bool) -> sql.Typed:
    """What a lookup gives for each value of a line of cells e (`line`, the SQL after FROM),
    by its key: the place along the axis and `beside` of the first cell holding it, the last
    searching backwards; under sql.UNSURE the place of the first text whose key is unsure.
    Computed once, however many rows look a value up in it."""
    order = " DESC" if backwards else ""
    return sql.Typed(
        "(SELECT jsonb_object_agg(m.k, jsonb_build_array(m.p, m.v)) FROM (SELECT DISTINCT ON "
        f"(q.k) q.k, q.p, q.v FROM (SELECT {sql.key('e.v')} AS k, e.{axis} AS p, {beside} AS v "
        f"FROM {line}) AS q WHERE q.k IS NOT NULL ORDER BY q.k, q.p{order}) AS m)",
        sql.VALUE,
    )


def _found(
    scope, sought, mapping, otherwise: str, wildcards: bool, backwards: bool = False, blank=None
):
    """What the map gives for the value sought (_exact), or `otherwise`, `blank` sought for an
    empty cell where it is given. A text is NULL where the line holds a text it may match
    otherwise than by its lower case before the one found by it, or where the text sought is
    such, or a pattern where wildcards count."""

    def body(names: list[sql.Typed]) -> sql.Typed:
        m = names[0].sql
        known = blank if isinstance(sought.known, Blank) and blank is not None else sought.known
        if known is not sql.UNKNOWN:
            if wildcards and isinstance(known, str) and wild(known):
                raise sql.Unsupported("a pattern")
            found = f"{m} -> {sql.text_literal(sql.known_key(known))}"
            text = "true" if isinstance(known, str) else None
            odd = "false"
        else:
            s = sql.value(sought).sql
            if blank is not None:
                s = f"CASE WHEN {s} = 'null'::jsonb THEN {sql.jsonb_literal(blank)} ELSE {s} END"
            found = f"{m} -> ({sql.key(s)})"
            text = f"jsonb_typeof({s}) = 'string'"
            odd = f"({sql.key(s)}) = '{sql.UNSURE}'"
            if wildcards:
                odd += f" OR ({s} #>> '{{}}') ~ '[*?~]'"

        def result(f: list[sql.Typed]) -> sql.Typed:
            given = f"coalesce({f[0].sql} -> 1, {otherwise})"
            if text is None:
                return sql.Typed(given, sql.VALUE)
            earlier = ">" if backwards else "<"
            ahead = (
                f"{m} ? '{sql.UNSURE}' AND NOT coalesce(({f[0].sql} -> 0) {earlier} "
                f"({m} -> '{sql.UNSURE}' -> 0), false)"
            )
            return sql.Typed(
                f"CASE WHEN {text} AND ({odd} OR {ahead}) THEN NULL ELSE {given} END", sql.VALUE
            )

        return scope.bound([sql.Typed(found, sql.VALUE)], result)

    return scope.bound([mapping], body)


@sql_form("VLOOKUP")
def vlookup_sql(scope, sought, given, index, approximate=None):
    if approximate is None or approximate.known is not False:
        raise sql.Unsupported("an approximate lookup")
    column = _whole(index, 1)
    if column < 1:
        raise sql.Unsupported("#VALUE!")
    if column > given.extent[1]:
        raise sql.Unsupported("#REF!")
    mapping = _map(
        f"{given.source} AS e LEFT JOIN {given.source} AS r ON r.y = e.y AND r.x = {column} "
        "WHERE e.x = 1",
        "y",
        "coalesce(r.v, 'null'::jsonb)",
        False,
    )
    return _found(scope, sought, mapping, NOT_FOUND, True, blank=0.0)


@sql_form("XLOOKUP")
def xlookup_sql(scope, sought, lookup, returned, if_not_found=None, mode=None, search=None):
    mode, search = _whole(mode, 0), _whole(search, 1)
    if mode not in (0, 2) or search not in (-1, 1):
        raise sql.Unsupported("an approximate lookup")
    axis = _line_sql(lookup)
    column = axis == "y"
    if (returned.height != lookup.height) if column else (returned.width != lookup.width):
        raise sql.Unsupported("#VALUE!")
    if (returned.width if column else returned.height) != 1:
        raise sql.Unsupported("an area found")
    if if_not_found is None or if_not_found.kind == sql.BLANK:
        otherwise = NOT_FOUND
    elif if_not_found.kind == sql.VALUE and if_not_found.known is sql.UNKNOWN:
        otherwise = (
            f"CASE WHEN {if_not_found.sql} = 'null'::jsonb THEN {NOT_FOUND} "
            f"ELSE {if_not_found.sql} END"
        )
    else:
        otherwise = sql.value(if_not_found).sql
    mapping = _map(
        f"{lookup.source} AS e LEFT JOIN {returned.source} AS r ON r.{axis} = e.{axis}",
        axis,
        "coalesce(r.v, 'null'::jsonb)",
        search < 0,
    )
    return replace(_found(scope, sought, mapping, otherwise, mode == 2, search < 0), cell=None)


@sql_form("MATCH")
def match_sql(scope, sought, lookup, kind=None):
    if _whole(kind, 1) != 0:
        raise sql.Unsupported("an approximate lookup")
    axis = _line_sql(lookup)
    mapping = _map(f"{lookup.source} AS e", axis, f"to_jsonb(e.{axis}::float8)", False)
    return _found(scope, sought, mapping, NOT_FOUND, True, blank=0.0)


@sql_form("INDEX")
def index_sql(scope, given, row, col=None, area=None):
    if area is not None:
        raise sql.Unsupported("an area chosen")
    if col is None:
        if given.height == 1 and given.width > 1:
            row, col = 1, row
        elif given.width > 1:
            raise sql.Unsupported("a whole row")
        else:
            col = 1
    tests = []
    places = []
    for at, size in ((row, given.height), (col, given.width)):
        if isinstance(at, int):
            places.append(str(at))
            continue
        if at.known is not sql.UNKNOWN:
            known = math.trunc(at.known)
            if not 1 <= known <= size:
                raise sql.Unsupported("an error or a whole row or column")
            places.append(str(known))
            continue
        tests.append(f"trunc({at.sql}) BETWEEN 1 AND {size}")
        places.append(f"trunc({at.sql})")
    found = (
        f"coalesce((SELECT e.v FROM {given.source} AS e "
        f"WHERE e.y = {places[0]} AND e.x = {places[1]}), 'null'::jsonb)"
    )
    if tests:
        found = f"CASE WHEN {' AND '.join(tests)} THEN {found} END"
    return sql.Typed(found, sql.VALUE, cell=True)


@sql_form("HYPERLINK")
def hyperlink_sql(scope, link, friendly=None):
    if friendly is None:
        return link
    return replace(friendly, cell=False)
