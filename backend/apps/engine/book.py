"""A book held in memory (D22): constants and formulas by sheet, row and column, each formula
computed when first read and kept for the rest of the computation, one compiled function serving
every cell that holds the same formula relative to its own."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from random import Random

from .evaluate import formula, spilled
from .formats import Language
from .grid import Area, Context, Value
from .parse import Call, Held, parse, relative
from .values import BLANK, REF, Error, Scalar

SUBTOTALS = frozenset(("SUBTOTAL", "AGGREGATE"))


@dataclass(frozen=True)
class _Formula:
    tree: object


def calls(node) -> Iterator[str]:
    if isinstance(node, Call):
        yield node.name
    if is_dataclass(node):
        for each in fields(node):
            child = getattr(node, each.name)
            for item in child if isinstance(child, tuple) else (child,):
                yield from calls(item)


class Cells:
    """The cells of a book, computed in one computation: one moment and one run of random
    numbers for all of them. A cell its own formula reaches again reads as 0, as Excel gives a
    circular reference."""

    def __init__(self, locale: str, now: datetime, random: Random, code_page: str):
        self.language = Language(locale, now.year, code_page)
        self.now = now
        self.random = random
        self._names: dict[str, str] = {}
        self._cells: dict[str, dict[tuple[int, int], Scalar | _Formula]] = {}
        self._hidden: dict[str, set[int]] = {}
        self._extents: dict[str, tuple[int, int]] = {}
        self._computed: dict[tuple[str, int, int], Scalar] = {}
        self._computing: set[tuple[str, int, int]] = set()
        self._compiled: dict[object, Callable[[Context], Scalar]] = {}

    def _sheet(self, name: str) -> str:
        found = self._names.setdefault(name.casefold(), name)
        self._cells.setdefault(found, {})
        self._hidden.setdefault(found, set())
        self._extents.pop(found, None)
        return found

    def put(self, sheet: str, row: int, col: int, value: Scalar) -> None:
        """A constant in a cell."""
        self._cells[self._sheet(sheet)][row, col] = value

    def write(self, sheet: str, row: int, col: int, text: str) -> None:
        """A formula in a cell as xlsx keeps it: in Excel's English, without its "="."""
        self.place(sheet, row, col, relative(parse(text), row, col))

    def place(self, sheet: str, row: int, col: int, tree: object) -> None:
        """A formula already read and made relative to its cell, which books of every language
        can share."""
        self._cells[self._sheet(sheet)][row, col] = _Formula(tree)

    def hide(self, sheet: str, row: int) -> None:
        self._hidden[self._sheet(sheet)].add(row)

    def value(self, sheet: str, row: int, col: int) -> Scalar:
        name = self._names.get(sheet.casefold())
        if name is None:
            return REF
        held = self._cells[name].get((row, col), BLANK)
        if not isinstance(held, _Formula):
            return held
        key = (name, row, col)
        if key in self._computed:
            return self._computed[key]
        if key in self._computing:
            return 0.0
        compiled = self._compiled.get(held.tree)
        if compiled is None:
            compiled = self._compiled[held.tree] = formula(held.tree)
        self._computing.add(key)
        try:
            result = compiled(Context(self, name, row, col, self.language, self.now, self.random))
        finally:
            self._computing.discard(key)
        self._computed[key] = result
        return result

    def array(self, sheet: str, row: int, col: int) -> Value:
        """The whole value of the formula in a cell (evaluate.spilled), computed again."""
        name = self._names[sheet.casefold()]
        held = self._cells[name][row, col]
        context = Context(self, name, row, col, self.language, self.now, self.random)
        return spilled(held.tree)(context)

    def extent(self, sheet: str) -> tuple[int, int] | None:
        name = self._names.get(sheet.casefold())
        if name is None:
            return None
        if name not in self._extents:
            places = self._cells[name]
            self._extents[name] = (
                max((row for row, _ in places), default=0),
                max((col for _, col in places), default=0),
            )
        return self._extents[name]

    def hidden(self, sheet: str, row: int) -> bool:
        name = self._names.get(sheet.casefold())
        return name is not None and row in self._hidden[name]

    def subtotal(self, sheet: str, row: int, col: int) -> bool:
        name = self._names.get(sheet.casefold())
        held = name and self._cells[name].get((row, col))
        return isinstance(held, _Formula) and not SUBTOTALS.isdisjoint(calls(held.tree))

    def held(self, node: Held, here: Context) -> Area | Error:
        return REF
