from .. import sql
from ..grid import scalar
from ..values import NA, VALUE, Error, compare
from . import form, sql_form


@form("IF")
def if_(context, test, if_true, if_false=None):
    if test:
        return if_true()
    return False if if_false is None else if_false()


@form("IFS")
def ifs(context, *pairs):
    for at in range(0, len(pairs) - 1, 2):
        test = pairs[at]()
        if isinstance(test, Error):
            return test
        if test:
            return pairs[at + 1]()
    return NA


@form("IFERROR")
def iferror(context, value, if_error):
    return if_error() if isinstance(value, Error) else value


@form("IFNA")
def ifna(context, value, if_na):
    return if_na() if value == NA else value


@form("AND")
def and_(context, logicals):
    return all(logicals) if logicals else VALUE


@form("OR")
def or_(context, logicals):
    return any(logicals) if logicals else VALUE


@form("XOR")
def xor(context, logicals):
    return sum(logicals) % 2 == 1 if logicals else VALUE


@form("NOT")
def not_(context, logical):
    return not logical


@form("TRUE")
def true(context):
    return True


@form("FALSE")
def false(context):
    return False


@form("SWITCH")
def switch(context, expression, *rest):
    for at in range(0, len(rest) - 1, 2):
        candidate = scalar(context, rest[at]())
        if isinstance(candidate, Error):
            return candidate
        if (
            type(candidate) is type(expression)
            and compare(expression, candidate, context.language) == 0
        ):
            return rest[at + 1]()
    return rest[-1]() if len(rest) % 2 else NA


def _alike(first: sql.Typed, second: sql.Typed) -> tuple[sql.Typed, sql.Typed]:
    """Two parts as one kind, values where they differ."""
    if first.kind == second.kind and first.kind not in ("blank",):
        return first, second
    return sql.value(first), sql.value(second)


def _either(first: sql.Typed, second: sql.Typed) -> bool | None:
    return first.cell if first.cell == second.cell else None


@sql_form("IF")
def if_sql(scope, test, if_true, if_false=None):
    otherwise = (lambda: sql.constant(False)) if if_false is None else if_false
    if test.known is not sql.UNKNOWN:
        return if_true() if test.known else otherwise()
    first, second = _alike(if_true(), otherwise())
    return sql.Typed(
        f"CASE WHEN {test.sql} THEN {first.sql} ELSE {second.sql} END",
        first.kind,
        cell=_either(first, second),
    )


def _replaced(given: sql.Typed, test: str, instead: sql.Typed) -> sql.Typed:
    if given.kind != sql.VALUE:
        return sql.Typed(given.sql, given.kind, given.simple, given.sure, False, given.known)
    instead = sql.value(instead)
    return sql.Typed(
        f"CASE WHEN {test} THEN {instead.sql} ELSE {given.sql} END",
        sql.VALUE,
        cell=False if instead.cell is False else None,
    )


@sql_form("IFERROR")
def iferror_sql(scope, given, if_error):
    return _replaced(given, f"jsonb_typeof({given.sql}) = 'object'", if_error())


@sql_form("IFNA")
def ifna_sql(scope, given, if_na):
    return _replaced(given, f"{given.sql} = '{sql.NA}'::jsonb", if_na())


def _logicals(scope, found: list, combined: str) -> sql.Typed:
    source = sql.elements(
        found,
        lambda v: (
            f"CASE jsonb_typeof({v}) WHEN 'number' THEN ({v})::float8 <> 0 "
            f"WHEN 'boolean' THEN ({v})::boolean END AS l, jsonb_typeof({v}) = 'object' AS bad"
        ),
        lambda given: sql.logical(given, scope),
        lambda g: f"{g} AS l, {g} IS NULL AS bad",
    )
    return sql.Typed(
        f"(SELECT CASE WHEN bool_or(e.bad) OR count(e.l) = 0 THEN NULL "
        f"ELSE {combined}(e.l) END FROM {source} AS e)",
        sql.LOGICAL,
    )


@sql_form("AND")
def and_sql(scope, found):
    return _logicals(scope, found, "bool_and")


@sql_form("OR")
def or_sql(scope, found):
    return _logicals(scope, found, "bool_or")


@sql_form("NOT")
def not_sql(scope, given):
    return sql.Typed(f"(NOT {given.sql})", sql.LOGICAL)


@sql_form("TRUE")
def true_sql(scope):
    return sql.constant(True)


@sql_form("FALSE")
def false_sql(scope):
    return sql.constant(False)
