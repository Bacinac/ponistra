"""Excel's conditions on cells (D22): a criterion as COUNTIF, SUMIF and their kin read it, and
the matching MATCH and the lookups do, text with wildcards among it."""

import operator
import re
from collections.abc import Callable
from functools import cache

from . import formats, values
from .collation import collation
from .formats import Language
from .parse import ERRORS
from .values import ERROR_TYPES, Blank, Error, Scalar

OPERATORS = {
    "<=": operator.le,
    ">=": operator.ge,
    "<>": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "=": operator.eq,
}


# What a tilde takes as it is: in SEARCH a wildcard or a tilde, in a criterion's pattern and a
# lookup whatever follows it, a tilde ending the pattern nothing.
SEARCHED, ANY = "*?~", None


def parts(pattern: str, taken: str | None) -> list[str]:
    """A pattern's runs of text with a wildcard, * or ?, between each two."""
    found = [""]
    at = 0
    while at < len(pattern):
        each = pattern[at]
        if each == "~" and (taken is None or pattern[at + 1 : at + 2] in tuple(taken)):
            found[-1] += pattern[at + 1 : at + 2]
            at += 2
            continue
        if each in "*?":
            found += [each, ""]
        else:
            found[-1] += each
        at += 1
    return found


@cache
def wildcard(pattern: str) -> re.Pattern:
    """SEARCH's pattern: * for any run of characters and ? for any one, regardless of case."""
    out = [
        re.escape(each) if at % 2 == 0 else ".*" if each == "*" else "."
        for at, each in enumerate(parts(pattern, SEARCHED))
    ]
    return re.compile("".join(out), re.IGNORECASE | re.DOTALL)


def literal(pattern: str) -> str | None:
    """The text a criterion holding no * or ? stands for, its tildes as they are: "~~" is two
    tildes, where "~~*" starts with one."""
    return None if "*" in pattern or "?" in pattern else pattern


def wild(text: str) -> bool:
    return any(each in text for each in "*?~")


def fits(pattern: str, text: str, language: Language, taken: str | None) -> bool:
    """Whether a text matches a pattern: each run of it as many UTF-16 units of the text that
    Collation.matches holds equal, ? one unit and * any run of them."""
    matches = collation(language.code).matches
    units = _units(text)
    reach = {0}
    for at, part in enumerate(parts(pattern, taken)):
        if at % 2 and part == "?":
            reach = {place + 1 for place in reach if place < len(units)}
        elif at % 2:
            reach = set(range(min(reach), len(units) + 1))
        elif part:
            size = len(_units(part))
            reach = {
                place + size
                for place in reach
                if place + size <= len(units)
                and matches(part, "".join(units[place : place + size]))
            }
        if not reach:
            return False
    return len(units) in reach


def _units(text: str) -> list[str]:
    data = text.encode("utf-16-le", "surrogatepass")
    return [data[at : at + 2].decode("utf-16-le", "surrogatepass") for at in range(0, len(data), 2)]


def equal(sought: Scalar, candidate: Scalar, language: Language, wildcards=False) -> bool:
    """Whether a lookup finds a cell: the same kind of value and equal to it, text as compare
    holds it equal or, where wildcards count (MATCH and VLOOKUP always count them), as a
    pattern, even one without them: "ß" finds no "ss" there."""
    if isinstance(sought, Blank) or isinstance(candidate, Blank):
        return isinstance(sought, Blank) and isinstance(candidate, Blank)
    if type(sought) is not type(candidate):
        return False
    if isinstance(sought, str):
        if wildcards:
            return fits(sought, candidate, language, ANY)
        return collation(language.code).compare(sought, candidate) == 0
    if isinstance(sought, Error):
        return sought == candidate
    return values.compare(sought, candidate, language) == 0


def criterion(given: Scalar, language: Language) -> Callable[[Scalar], bool]:
    """The test a criterion puts to each cell. A number, logical or error matches that value;
    text may start with a comparison, and what follows it is read as a number, a date, a
    logical or an error where it is one, else as text with wildcards. A number matches text
    that reads as it too, but "<>" leaves out only the numbers equal to it; errors compare by
    their codes (#DIV/0! before #N/A); "=" alone matches empty cells, "" empty cells and empty
    text, "<>" everything but empty cells, and a comparison with nothing nothing."""
    if isinstance(given, Blank):
        given = 0.0
    if not isinstance(given, str):
        return _equal_to(given, language)
    op, written = split(given)
    if written == "":
        if op == "=":
            return lambda cell: isinstance(cell, Blank)
        if op == "<>":
            return lambda cell: not isinstance(cell, Blank)
        if op == "":
            return lambda cell: isinstance(cell, Blank) or cell == ""
        return lambda cell: False
    value = operand(written, language)
    if op in ("", "="):
        return _equal_to(value, language)
    if op == "<>":
        if isinstance(value, float):
            return lambda cell: (
                not (isinstance(cell, float) and values.compare(cell, value, language) == 0)
            )
        test = _equal_to(value, language)
        return lambda cell: not test(cell)
    compare = OPERATORS[op]
    if isinstance(value, float):
        return lambda cell: (
            isinstance(cell, float) and compare(values.compare(cell, value, language), 0)
        )
    if isinstance(value, str):
        return lambda cell: (
            isinstance(cell, str) and compare(values.compare(cell, value, language), 0)
        )
    if isinstance(value, Error):
        code = ERROR_TYPES[value.value]
        return lambda cell: isinstance(cell, Error) and compare(ERROR_TYPES[cell.value], code)
    return lambda cell: (
        type(cell) is type(value) and compare(values.compare(cell, value, language), 0)
    )


def split(given: str) -> tuple[str, str]:
    """A criterion written as text: the comparison it starts with ("" for none) and the rest."""
    for mark in OPERATORS:
        if given.startswith(mark):
            return mark, given[len(mark) :]
    return "", given


def operand(text: str, language: Language) -> Scalar:
    """What a criterion compares with: a number, a date, a logical or an error where the text
    is one, else the text."""
    number = formats.read(text, language, criterion=True)
    if number is not None:
        return number
    if text.upper() in ("TRUE", "FALSE"):
        return text.upper() == "TRUE"
    if text.upper() in ERRORS:
        return Error(text.upper())
    return text


def _equal_to(value: Scalar, language: Language) -> Callable[[Scalar], bool]:
    if isinstance(value, float):

        def number(cell: Scalar) -> bool:
            if isinstance(cell, str):
                cell = formats.read(cell, language)
            return isinstance(cell, float) and values.compare(cell, value, language) == 0

        return number
    if isinstance(value, str):
        if (found := literal(value)) is not None:
            same = collation(language.code).compare
            return lambda cell: isinstance(cell, str) and same(cell, found) == 0
        return lambda cell: isinstance(cell, str) and fits(value, cell, language, ANY)
    return lambda cell: type(cell) is type(value) and cell == value
