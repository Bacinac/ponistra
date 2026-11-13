"""The forms of each of Excel's functions (D22), under its name in the registry. The Python form,
which every function has, is a function of the cell it is computed for and its arguments, each
already read as its kind in the registry says, a lazy one as a function to call where it is
needed. The SQL form, where SQL gives Excel's result exactly, is a function of the compiling
scope and its arguments as SQL (sql.Typed, sql.Range, a list of either for a list), a lazy one
as a function giving it."""

from collections.abc import Callable

FORMS: dict[str, Callable] = {}
SQL_FORMS: dict[str, Callable] = {}


def _registering(
    forms: dict[str, Callable], names: tuple[str, ...]
) -> Callable[[Callable], Callable]:
    def register(function: Callable) -> Callable:
        for name in names:
            forms[name] = function
        return function

    return register


def form(*names: str) -> Callable[[Callable], Callable]:
    return _registering(FORMS, names)


def sql_form(*names: str) -> Callable[[Callable], Callable]:
    return _registering(SQL_FORMS, names)


from . import (  # noqa: E402
    date_time,
    financial,
    information,
    logical,
    lookup,
    math_trig,
    statistical,
    text,
)

__all__ = [
    "FORMS",
    "SQL_FORMS",
    "date_time",
    "financial",
    "form",
    "sql_form",
    "information",
    "logical",
    "lookup",
    "math_trig",
    "statistical",
    "text",
]
