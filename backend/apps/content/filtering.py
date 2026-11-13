"""A user's filter of a table (D22, E3): which of its rows they see, as SQL over the text each
cell shows and the value it holds (GridRow). Each condition takes one column: the texts let
through, the case not counting, an empty one for an empty cell; or a comparison with a value,
of text or of a number as it would be typed in the document's language. A row is shown when
it is not hidden and meets every condition."""

from collections.abc import Sequence
from dataclasses import dataclass

from django.db import connection

from apps.engine.functions.lookup import sorted_by

from . import calculation

TEXTS = ("equals", "notEquals", "begins", "ends", "contains", "notContains")
NUMBERS = ("greater", "greaterEqual", "less", "lessEqual")
CONDITIONS = TEXTS + NUMBERS
# The most texts a condition lets through, and the most distinct texts a column offers.
MOST = 1000

COMPARED = {"greater": ">", "greaterEqual": ">=", "less": "<", "lessEqual": "<="}


class Invalid(ValueError):
    """The conditions are not ones a filter takes."""


def _text(col: str, r: str = "r") -> tuple[str, list]:
    """What the column's cell shows, empty where it shows nothing; the apostrophe that keeps a
    typed value a text is not shown."""
    typed = f"{r}.cells -> %s ->> 'text'"
    held = f"coalesce({r}.shown ->> %s, {typed})"
    sql = (
        f"coalesce(CASE WHEN {held} LIKE '''%%' AND NOT {r}.shown ? %s "
        f"THEN substr({typed}, 2) ELSE {held} END, '')"
    )
    return sql, [col, col, col, col, col, col]


def _escaped(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def checked(conditions, cols: Sequence[str], locale: str) -> list[dict]:
    """The conditions as a filter keeps them, refused where one is not a condition of a column
    the table has, or a column has two."""
    if not isinstance(conditions, list) or len(conditions) > len(cols):
        raise Invalid("conditions")
    found, taken = [], set()
    for condition in conditions:
        if not isinstance(condition, dict) or condition.get("col") not in cols:
            raise Invalid("col")
        col = condition["col"]
        if col in taken:
            raise Invalid("col")
        taken.add(col)
        values, op, value = (condition.get(key) for key in ("values", "op", "value"))
        if values is not None and op is None and value is None:
            if (
                not isinstance(values, list)
                or not 0 < len(values) <= MOST
                or not all(isinstance(each, str) for each in values)
            ):
                raise Invalid("values")
            found.append({"col": col, "values": sorted(set(values))})
        elif values is None and op in CONDITIONS and isinstance(value, str):
            if op in NUMBERS and not isinstance(
                calculation.typed(value, calculation.language(locale)), float
            ):
                raise Invalid("number")
            found.append({"col": col, "op": op, "value": value})
        else:
            raise Invalid("condition")
    return found


def _condition(condition: dict, locale: str, r: str = "r") -> tuple[str, list]:
    text, params = _text(condition["col"], r)
    if "values" in condition:
        return (
            f"lower({text}) IN (SELECT lower(v) FROM unnest(%s::text[]) v)",
            [*params, condition["values"]],
        )
    op, value = condition["op"], condition["value"]
    if op in NUMBERS:
        number = calculation.typed(value, calculation.language(locale))
        col = condition["col"]
        return (
            f"jsonb_typeof({r}.\"values\" -> %s) = 'number' "
            f'AND ({r}."values" ->> %s)::float8 {COMPARED[op]} %s',
            [col, col, number],
        )
    match op:
        case "equals":
            return f"lower({text}) = lower(%s)", [*params, value]
        case "notEquals":
            return f"lower({text}) <> lower(%s)", [*params, value]
        case "begins":
            return f"{text} ILIKE %s", [*params, f"{_escaped(value)}%"]
        case "ends":
            return f"{text} ILIKE %s", [*params, f"%{_escaped(value)}"]
        case "contains":
            return f"{text} ILIKE %s", [*params, f"%{_escaped(value)}%"]
        case _:
            return f"{text} NOT ILIKE %s", [*params, f"%{_escaped(value)}%"]


@dataclass(frozen=True)
class View:
    """The rows of a table a user sees: those not hidden that meet the user's conditions."""

    conditions: tuple = ()
    locale: str = "hr"

    def sql(self, r: str = "r", besides: str | None = None) -> tuple[str, list]:
        """The predicate over the row aliased `r`, leaving out the condition of the column
        given."""
        parts, params = [f"NOT {r}.hidden"], []
        for condition in self.conditions:
            if condition["col"] != besides:
                sql, each = _condition(condition, self.locale, r)
                parts.append(f"({sql})")
                params += each
        return " AND ".join(parts), params

    def passing(self, grid: int, ids: Sequence[str]) -> set[str]:
        """Those of the rows given that the view shows."""
        where, params = self.sql()
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT r.row FROM content_gridrow r WHERE r.grid_id = %s AND r.row = ANY(%s) "
                f"AND {where}",
                [grid, list(ids), *params],
            )
            return {id for (id,) in cursor.fetchall()}


def texts(grid: int, view: View, col: str) -> tuple[list[tuple[str, int]], bool]:
    """The texts the column's cells show in the rows the other conditions let through, each
    with how many show it, the case not counting, in the order a sort in the document's
    language gives them, the empty one last; at most `MOST`, and whether there are more."""
    where, params = view.sql(besides=col)
    text, own = _text(col)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT min({text}), count(*) FROM content_gridrow r "
            f"WHERE r.grid_id = %s AND {where} GROUP BY lower({text}) "
            f"ORDER BY lower({text}) LIMIT %s",
            [*own, grid, *params, *own, *own, MOST + 1],
        )
        found = cursor.fetchall()
    filled = [(text, count) for text, count in found[:MOST] if text]
    ordered = sorted_by(filled, lambda each: each[0], False, calculation.language(view.locale))
    return ordered + [(text, count) for text, count in found[:MOST] if not text], len(found) > MOST
