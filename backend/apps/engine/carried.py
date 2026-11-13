"""The number format Excel gives a cell as a formula or a text is entered in it (D22 E3), held to
what Excel gave the cells of implied.py's files: a formula carries the formats of the cells and
the functions it reads, and a format the cell holds gives way to what is entered only where
Excel lets it."""

from collections.abc import Callable, Iterator
from typing import NamedTuple

from . import formats
from .formats import CLOCK_SECONDS, DURATION
from .numformat import category
from .parse import Binary, Call, Group, Held, Prefix, Ref
from .registry import FUNCTIONS, Carried

KEPT = frozenset({"number", "currency", "text"})
GIVING_WAY = frozenset({"general", "number"})


class _Carried(NamedTuple):
    format: str = ""
    money: bool = False
    cancelled: bool = False


NOTHING = _Carried()
CANCELLED = _Carried(cancelled=True)


def carried(tree, format_of: Callable[[Ref | Held], str], locale: str) -> str:
    """The format a formula gives its cell: the first format it reads, from left to right, a
    reference by its first cell's (`format_of`), a function by its own or by its arguments'
    (registry's `format`); none where a second date follows a date, or a function's currency
    follows a format other than a date's, nor after it."""
    found = NOTHING
    for each in _read(tree, format_of, locale):
        found = _then(found, each)
    return found.format


def _then(found: _Carried, read: _Carried) -> _Carried:
    if found.cancelled or read.cancelled:
        return CANCELLED
    if not found.format:
        return read
    dated = category(found.format) == "date"
    if read.format and dated and category(read.format) == "date":
        return CANCELLED
    if read.money and not dated:
        return CANCELLED
    return found


def _read(node, format_of, locale: str) -> Iterator[_Carried]:
    """The formats a formula reads, in order: within a sum or a difference, a sign or brackets
    each as its own; a function's as one, SUM's seconds of a day summed into hours past it."""
    match node:
        case Group(inner) | Prefix(_, inner):
            yield from _read(inner, format_of, locale)
        case Binary(op, left, right) if op in "+-":
            yield from _read(left, format_of, locale)
            yield from _read(right, format_of, locale)
        case Ref() | Held():
            yield _Carried(format_of(node))
        case Call(name, args) if name in FUNCTIONS:
            given = FUNCTIONS[name].format
            if given is Carried.MONEY:
                yield _Carried(formats.money(locale, places=True), money=True)
            elif given is Carried.ARGUMENTS:
                found = NOTHING
                for arg in args:
                    for each in _read(arg, format_of, locale):
                        found = _then(found, each)
                if name == "SUM" and found.format == CLOCK_SECONDS:
                    found = found._replace(format=DURATION)
                yield found
            elif given:
                yield _Carried(given)


def entered(held: str, given: str) -> str:
    """The format of a cell holding one as a text or a formula giving another is entered in it:
    a number's, a currency's and text's stay, as does any where the one given is a number's or
    of its kind; a percent, a scientific number, a fraction, a date or a time give way."""
    if not held:
        return given
    kind = category(held)
    if kind in KEPT or category(given) in GIVING_WAY or category(given) == kind:
        return held
    return given
