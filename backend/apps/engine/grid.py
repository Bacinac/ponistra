"""The cells a formula reaches (D22): an area of a sheet as a value, the book that gives each
cell's value, the cell a formula is computed for, and how an area is read as Excel reads it."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from random import Random
from typing import Protocol

from . import values
from .formats import Language
from .parse import LAST_COL, LAST_ROW, Held
from .values import VALUE, Error, Matrix, Scalar


@dataclass(frozen=True)
class Area:
    """A rectangle of cells on a sheet."""

    sheet: str
    top: int
    left: int
    bottom: int
    right: int

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def width(self) -> int:
        return self.right - self.left + 1


@dataclass(frozen=True)
class Union:
    """Areas taken together, as (A1,C3) gives them."""

    areas: tuple[Area, ...]


Value = Scalar | Matrix | Area | Union


class Book(Protocol):
    """The cells formulas reach."""

    def value(self, sheet: str, row: int, col: int) -> Scalar:
        """A cell's value, computed first where it holds a formula."""

    def extent(self, sheet: str) -> tuple[int, int] | None:
        """The last row and column holding anything; None for a sheet the book lacks."""

    def hidden(self, sheet: str, row: int) -> bool:
        """Whether the row is hidden."""

    def subtotal(self, sheet: str, row: int, col: int) -> bool:
        """Whether the cell's formula holds a SUBTOTAL, which another SUBTOTAL passes over."""

    def held(self, node: Held, here: Context) -> Area | Error:
        """The area a table's reference by the ids of its rows and columns stands for."""


@dataclass
class Context:
    """The cell a formula is computed for, and the computation it is part of: the moment and
    the random numbers every cell of one computation shares, as NOW gives one time throughout
    Excel's recalculation."""

    book: Book
    sheet: str
    row: int
    col: int
    language: Language
    now: datetime
    random: Random


def bounded(area: Area, book: Book) -> Area:
    """The area with a whole column or row cut to the cells the sheet holds, so that A:A is
    read as far as anything is written."""
    extent = book.extent(area.sheet) or (0, 0)
    bottom = min(area.bottom, extent[0]) if area.bottom == LAST_ROW else area.bottom
    right = min(area.right, extent[1]) if area.right == LAST_COL else area.right
    return Area(area.sheet, area.top, area.left, bottom, right)


def matrix(context: Context, area: Area) -> Matrix:
    """The values of an area, by rows."""
    area = bounded(area, context.book)
    value = context.book.value
    return Matrix(
        tuple(
            tuple(value(area.sheet, row, col) for col in range(area.left, area.right + 1))
            for row in range(area.top, area.bottom + 1)
        )
    )


def cells(context: Context, given: Area | Union | Matrix) -> Iterator[Scalar]:
    """Every value of an area, of areas taken together or of an array, by rows."""
    match given:
        case Matrix():
            yield from given.values()
        case Union(areas):
            for area in areas:
                yield from matrix(context, area).values()
        case Area():
            yield from matrix(context, given).values()


def intersected(context: Context, area: Area) -> Scalar:
    """The one cell of an area a formula reads where it takes one value: the area's only cell,
    or the one in the formula's own row of a column or own column of a row; #VALUE! where
    there is none (Excel's implicit intersection)."""
    value = context.book.value
    if area.height == 1 and area.width == 1:
        return value(area.sheet, area.top, area.left)
    if area.width == 1 and area.top <= context.row <= area.bottom:
        return value(area.sheet, context.row, area.left)
    if area.height == 1 and area.left <= context.col <= area.right:
        return value(area.sheet, area.top, context.col)
    return VALUE


def scalar(context: Context, given: Value) -> Scalar:
    """A value as one: an area by its intersection with the formula's cell, an array by its
    first value."""
    match given:
        case Area():
            return intersected(context, given)
        case Union():
            return VALUE
        case Matrix():
            return given.rows[0][0] if given.rows and given.rows[0] else VALUE
    return given


def table(context: Context, given: Value) -> Matrix | Error:
    """A value as an array: an area's values, a single value as an array of one."""
    match given:
        case Area():
            return matrix(context, given)
        case Matrix() | Error():
            return given
        case Union():
            return VALUE
    return Matrix(((given,),))


def numbers(context: Context, given: Value) -> list[float] | Error:
    """The numbers to aggregate in a value: those in an area or array, an error there ending
    it, and a value given itself read as one number."""
    if isinstance(given, Area | Union | Matrix):
        found = []
        for each in cells(context, given):
            if isinstance(each, float):
                found.append(each)
            elif isinstance(each, Error):
                return each
        return found
    number = values.number(given, context.language)
    return number if isinstance(number, Error) else [number]
