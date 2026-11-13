import math
from collections.abc import Callable

from .. import sql
from ..grid import Area, intersected
from ..values import ERROR_TYPES, NA, VALUE, Blank, Error, Matrix
from . import form, sql_form


@form("ISBLANK")
def isblank(context, value):
    return isinstance(value, Blank)


@form("ISERROR")
def iserror(context, value):
    return isinstance(value, Error)


@form("ISERR")
def iserr(context, value):
    return isinstance(value, Error) and value != NA


@form("ISNA")
def isna(context, value):
    return value == NA


@form("ISNUMBER")
def isnumber(context, value):
    return isinstance(value, float)


@form("ISTEXT")
def istext(context, value):
    return isinstance(value, str)


@form("ISNONTEXT")
def isnontext(context, value):
    return not isinstance(value, str)


@form("ISLOGICAL")
def islogical(context, value):
    return isinstance(value, bool)


@form("TYPE")
def type_(context, value):
    if isinstance(value, Area):
        if value.height > 1 or value.width > 1:
            return 64
        value = intersected(context, value)
    match value:
        case Matrix():
            return 64
        case bool():
            return 4
        case str():
            return 2
        case Error():
            return 16
        case float() | Blank():
            return 1
    return VALUE


@form("ERROR.TYPE")
def error_type(context, value):
    return ERROR_TYPES[value.value] if isinstance(value, Error) else NA


@form("ISEVEN")
def iseven(context, number):
    return math.trunc(number) % 2 == 0


@form("ISODD")
def isodd(context, number):
    return math.trunc(number) % 2 == 1


@form("NA")
def na(context):
    return NA


@form("N")
def n(context, value):
    match value:
        case bool():
            return float(value)
        case float():
            return value
    return 0.0


SAMPLES = {sql.NUMBER: 0.0, sql.TEXT: "", sql.LOGICAL: False, sql.BLANK: Blank()}


def _folded(given: sql.Typed, python) -> sql.Typed:
    """The Python form's value on what a part is known to hold, or on a value of its kind where
    only that is known; NULL wherever such a part is, as Python is to compute it there."""
    known = given.known if given.known is not sql.UNKNOWN else SAMPLES[given.kind]
    found = sql.constant(python(None, known))
    if given.known is not sql.UNKNOWN or given.sure:
        return found
    return sql.Typed(f"CASE WHEN {given.sql} IS NOT NULL THEN {found.sql} END", found.kind)


def _is(given: sql.Typed, test: Callable[[str], str], python) -> sql.Typed:
    """A test of a value's kind: the jsonb test on a value, else the Python form's on what it is
    known to be."""
    if given.known is sql.UNKNOWN and given.kind not in SAMPLES:
        return sql.Typed(f"({test(given.sql)})", sql.LOGICAL)
    return _folded(given, python)


@sql_form("ISBLANK")
def isblank_sql(scope, given):
    return _is(given, lambda v: f"{v} = 'null'::jsonb", isblank)


@sql_form("ISNUMBER")
def isnumber_sql(scope, given):
    return _is(given, lambda v: f"jsonb_typeof({v}) = 'number'", isnumber)


@sql_form("ISTEXT")
def istext_sql(scope, given):
    return _is(given, lambda v: f"jsonb_typeof({v}) = 'string'", istext)


@sql_form("ISLOGICAL")
def islogical_sql(scope, given):
    return _is(given, lambda v: f"jsonb_typeof({v}) = 'boolean'", islogical)


@sql_form("ISERROR")
def iserror_sql(scope, given):
    return _is(given, lambda v: f"jsonb_typeof({v}) = 'object'", iserror)


@sql_form("ISNA")
def isna_sql(scope, given):
    return _is(given, lambda v: f"{v} = '{sql.NA}'::jsonb", isna)


@sql_form("N")
def n_sql(scope, given):
    if given.kind in (sql.NUMBER, sql.LOGICAL) and given.known is sql.UNKNOWN:
        return sql.number(given, scope)
    if given.known is not sql.UNKNOWN or given.kind in SAMPLES:
        return _folded(given, n)
    v = given.sql
    return sql.Typed(
        f"CASE jsonb_typeof({v}) WHEN 'number' THEN ({v})::float8 "
        f"WHEN 'boolean' THEN ({v})::boolean::int::float8 ELSE 0::float8 END",
        sql.NUMBER,
    )
