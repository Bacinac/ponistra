"""Excel's values and the rules every function shares (D22): a number is a float, text a str, a
logical a bool, an error the formula's Error, an empty cell BLANK and an array a Matrix. How one
kind is read as another, how two values compare, how Excel rounds and how it counts days."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from . import formats
from .collation import collation
from .formats import Language
from .parse import Error


class Blank:
    """An empty cell, which is neither 0 nor empty text until something reads it as one."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "BLANK"


BLANK = Blank()
NULL = Error("#NULL!")
DIV0 = Error("#DIV/0!")
VALUE = Error("#VALUE!")
REF = Error("#REF!")
NAME = Error("#NAME?")
NUM = Error("#NUM!")
NA = Error("#N/A")
SPILL = Error("#SPILL!")
CALC = Error("#CALC!")
ERROR_TYPES = {
    "#NULL!": 1,
    "#DIV/0!": 2,
    "#VALUE!": 3,
    "#REF!": 4,
    "#NAME?": 5,
    "#NUM!": 6,
    "#N/A": 7,
    "#GETTING_DATA": 8,
    "#SPILL!": 9,
    "#CALC!": 14,
}

Scalar = float | str | bool | Error | Blank
CANCELS = 2.0**-48


def stored(value: Scalar):
    """The value as Postgres keeps a cell's in jsonb (sql.VALUE): a number, text or logical as
    itself, an error as {"error": its code} and an empty cell as null."""
    if isinstance(value, Error):
        return {"error": value.value}
    return None if isinstance(value, Blank) else value


def loaded(given) -> Scalar:
    """The value of a cell Postgres keeps (stored)."""
    match given:
        case None:
            return BLANK
        case bool() | str():
            return given
        case int() | float():
            return float(given)
        case {"error": str(code)}:
            return Error(code)
    raise ValueError(f"not a value: {given!r}")


@dataclass(frozen=True)
class Matrix:
    """An array of values, by rows."""

    rows: tuple[tuple[Scalar, ...], ...]

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def values(self):
        for row in self.rows:
            yield from row


def number(value: Scalar, language: Language) -> float | Error:
    """A value read as one number."""
    match value:
        case bool():
            return float(value)
        case float():
            return value
        case Blank():
            return 0.0
        case str():
            read = formats.read(value, language)
            return VALUE if read is None else read
    return value


def text(value: Scalar, language: Language) -> str | Error:
    """A value read as text: a number in fifteen significant digits, within twenty."""
    match value:
        case bool():
            return "TRUE" if value else "FALSE"
        case float():
            return formats.numeral(value, formats.marks(language.code)[0], formats.SHOWN)
        case Blank():
            return ""
    return value


def logical(value: Scalar, language: Language) -> bool | Error:
    """A value read as a logical: a number is TRUE unless it is 0."""
    match value:
        case bool():
            return value
        case float():
            return value != 0
        case Blank():
            return False
        case str():
            word = value.upper()
            return VALUE if word not in ("TRUE", "FALSE") else word == "TRUE"
    return value


def significant(value: float) -> Decimal:
    """The number to the fifteen significant digits Excel keeps."""
    return Decimal(f"{value:.15g}")


def rounded(value: float, digits: int, rounding: str = ROUND_HALF_UP) -> float:
    """Rounded to `digits` after the point, half away from zero unless told otherwise
    (ROUND_UP away from zero, ROUND_DOWN toward it), as Excel rounds the number it shows, not
    the binary one: ROUND(2.675, 2) is 2.68."""
    if not math.isfinite(value) or value == 0:
        return value
    shown = significant(value)
    if digits > 14 - shown.adjusted():
        return float(shown)
    return float(shown.quantize(Decimal(1).scaleb(-digits), rounding=rounding)) + 0.0


_ORDER = {float: 0, str: 1, bool: 2}


def compare(left: Scalar, right: Scalar, language: Language) -> int:
    """-1, 0 or 1 as Excel orders two values that are no errors: numbers before text before
    logicals, text as Windows compares it in the language (collation), and an empty cell as the
    other side's kind would hold nothing."""
    if isinstance(left, Blank):
        left = _nothing(right)
    if isinstance(right, Blank):
        right = _nothing(left)
    kinds = _ORDER[type(left)], _ORDER[type(right)]
    if kinds[0] != kinds[1]:
        return -1 if kinds[0] < kinds[1] else 1
    if isinstance(left, str):
        return collation(language.code).compare(left, right)
    if isinstance(left, float) and significant(left) == significant(right):
        return 0
    return (left > right) - (left < right)


def _nothing(other: Scalar) -> Scalar:
    match other:
        case str():
            return ""
        case bool():
            return False
    return 0.0


def cancelled(left: float, right: float, total: float) -> float:
    """A sum of two numbers of opposite signs, 0 where they cancel to within 2^-48 of the
    larger."""
    if (left < 0) != (right < 0) and abs(total) < max(abs(left), abs(right)) * CANCELS:
        return 0.0
    return total


def total(numbers) -> float:
    """Numbers added in order, as SUM adds them: a sum whose terms cancel to within what their
    binary form holds is 0."""
    result = 0.0
    for each in numbers:
        result = cancelled(result, each, result + each)
    return result


def lifted(apply: Callable, *given):
    """A function of single values run over arrays: each array given is read at the same place,
    a single row or column or value repeats along the other arrays, and a place beyond an
    array that has more than one is #N/A."""
    arrays = [each for each in given if isinstance(each, Matrix)]
    if not arrays:
        return apply(*given)
    height = max(each.height for each in arrays)
    width = max(each.width for each in arrays)

    def at(each, row: int, col: int):
        if not isinstance(each, Matrix):
            return each
        if each.height == 1 and each.width == 1:
            return each.rows[0][0]
        if (row >= each.height and each.height != 1) or (col >= each.width and each.width != 1):
            return NA
        return each.rows[min(row, each.height - 1)][min(col, each.width - 1)]

    return Matrix(
        tuple(
            tuple(apply(*(at(each, row, col) for each in given)) for col in range(width))
            for row in range(height)
        )
    )


def finite(number: float) -> float | Error:
    """A number as a cell holds it: #NUM! for one beyond what a cell holds, 0 for -0."""
    if math.isinf(number) or math.isnan(number):
        return NUM
    return number + 0.0


def power(base: float, exponent: float) -> float | Error:
    """Excel's ^: 0^0 is #NUM!, 0 to a negative power #DIV/0!, and a negative number to a
    fraction whose inverse is an odd whole number its odd root."""
    if base == 0:
        if exponent == 0:
            return NUM
        return DIV0 if exponent < 0 else 0.0
    if base < 0 and exponent != int(exponent):
        inverse = 1 / exponent
        if abs(inverse - round(inverse)) < 1e-9 and round(inverse) % 2:
            return finite(-math.exp(exponent * math.log(-base)))
        return NUM
    try:
        return finite(base**exponent)
    except OverflowError:
        return NUM
