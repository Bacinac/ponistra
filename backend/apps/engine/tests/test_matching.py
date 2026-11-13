"""How Excel matches and orders values (D22), held to the workbook Excel saved in Croatian and in
English (matching.py): each of its formulas computed as Excel computed it, the texts of Order
and the values of Sorting sorted as SORT sorted them, and each text put to the next as Excel put
it."""

from random import Random

import pytest
from openpyxl.utils.cell import range_boundaries
from openpyxl.worksheet.formula import ArrayFormula

from apps.engine.book import Cells
from apps.engine.parse import parse, relative
from apps.engine.tests.matching import LOCALE, PATHS, workbook
from apps.engine.tests.saved import SAVED_ON, read, same, saved_at, saved_by, told
from apps.engine.values import NA, Matrix

MATCHED = (
    "Criteria", "Match", "XMatch", "Wild", "Equal", "Less", "VLookup", "HLookup", "XLookup",
    "Halving", "Probes", "Nearest",
)  # fmt: skip
ORDER = "Order"
SORTING = "Sorting"
SORTED = 2


@pytest.fixture(scope="module")
def written() -> dict[str, dict]:
    """Each sheet as matching.py writes it: its constants and its formulas by place, the places
    each array formula fills by the place it stands in, and each formula read once for the books
    of every language, a formula repeated down its rows one tree."""
    found = {}
    for sheet in workbook():
        cells = found[sheet.title] = {"constants": {}, "formulas": {}, "arrays": {}}
        for row in sheet.iter_rows():
            for cell in row:
                given = cell.value
                if isinstance(given, ArrayFormula):
                    cells["formulas"][cell.row, cell.column] = given.text[1:]
                    left, top, right, bottom = range_boundaries(given.ref)
                    cells["arrays"][cell.row, cell.column] = [
                        [(row, col) for col in range(left, right + 1)]
                        for row in range(top, bottom + 1)
                    ]
                elif cell.data_type == "f":
                    cells["formulas"][cell.row, cell.column] = given[1:]
                elif given is not None:
                    place = cell.row, cell.column
                    cells["constants"][place] = float(given) if type(given) is int else given
    shared: dict = {}
    for cells in found.values():
        cells["trees"] = {
            (row, col): shared.setdefault(tree := relative(parse(text), row, col), tree)
            for (row, col), text in cells["formulas"].items()
        }
    return found


def _sorted(saved: dict, written: dict) -> list:
    """The texts of Order as Excel's SORT gave them."""
    order = written[ORDER]
    last = max(row for row, col in (*order["constants"], *order["formulas"]) if col == 1)
    spilled = saved["values"] | saved["constants"]
    return [spilled[row, SORTED] for row in range(1, last + 1)]


def _book(code: str, saved: dict, written: dict, order: bool) -> Cells:
    """The saved workbook as the engine computes it: with `order`, Order alone with the texts as
    Excel sorted them; without, every other sheet."""
    cells = Cells(code, saved_at(PATHS[code]), Random(0), SAVED_ON)
    for title, sheet in written.items():
        if (title == ORDER) != order:
            continue
        for (row, col), value in sheet["constants"].items():
            cells.put(title, row, col, value)
        for (row, col), tree in sheet["trees"].items():
            if title == ORDER and col == SORTED:
                continue
            cells.place(title, row, col, tree)
    if order:
        for row, value in enumerate(_sorted(saved[ORDER], written), 1):
            cells.put(ORDER, row, SORTED, value)
    return cells


def _wrong(saved: dict, written: dict, title: str, cells: Cells) -> list[str]:
    values = saved[title]["values"]
    return [
        f"{title}!{row},{col} {text}: Excel {values[row, col]!r}, engine {computed!r}"
        for (row, col), text in written[title]["formulas"].items()
        if not (title == ORDER and col == SORTED)
        and not same(computed := cells.value(title, row, col), values[row, col], 0)
    ]


@pytest.fixture(scope="module")
def saved(code) -> dict[str, dict]:
    return read(PATHS[code], shared=True)


def test_the_matching_was_saved_by_excel_in_its_language(code, saved):
    assert saved_by(PATHS[code]) == "Microsoft Excel"
    title, row, col = LOCALE
    language = told(saved[title]["values"][row, col])
    assert language == code, f"{PATHS[code].name} was saved by Excel in {language}"


def test_the_saved_matching_holds_what_was_written(code, saved, written):
    unsaved = []
    for title, sheet in written.items():
        held = saved[title]
        filled = {place for places in sheet["arrays"].values() for line in places for place in line}
        constants = {
            place: value for place, value in held["constants"].items() if place not in filled
        }
        unsaved += [
            f"{title}!{row},{col}: {constants.get((row, col))!r} for {value!r}"
            for (row, col) in constants.keys() | sheet["constants"].keys()
            if not same(constants.get((row, col)), value := sheet["constants"].get((row, col)), 0)
        ]
        unsaved += [
            f"{title}!{row},{col}: {text}"
            for (row, col), text in held["formulas"].items()
            if text != sheet["formulas"][row, col]
            and parse(text) != parse(sheet["formulas"][row, col])
        ]
        unsaved += [
            f"{title}!{row},{col}: no value"
            for place in sheet["formulas"]
            if place not in held["values"]
            for row, col in (place,)
        ]
    assert not unsaved, f"{PATHS[code].name} is to be saved again in Excel:\n" + "\n".join(
        unsaved[:20]
    )


@pytest.fixture(scope="module")
def matched(code, saved, written) -> dict[str, list[str]]:
    """What the engine computes otherwise than Excel did in each sheet but Order, the book let go
    once read, as Order's is (ordered): one at a time fits in the memory a check has."""
    cells = _book(code, saved, written, False)
    found = {title: _wrong(saved, written, title, cells) for title in MATCHED}
    sorting = saved[SORTING]["values"] | saved[SORTING]["constants"]
    found[SORTING] = []
    for (row, col), places in written[SORTING]["arrays"].items():
        computed = cells.array(SORTING, row, col)
        for down, line in enumerate(places):
            for along, place in enumerate(line):
                if not isinstance(computed, Matrix):
                    value = computed
                elif down < len(computed.rows) and along < len(computed.rows[0]):
                    value = computed.rows[down][along]
                else:
                    value = NA
                if not same(value, sorting.get(place), 0):
                    text = written[SORTING]["formulas"][row, col]
                    found[SORTING].append(
                        f"{text} {place}: Excel {sorting.get(place)!r}, engine {value!r}"
                    )
    return found


@pytest.fixture(scope="module")
def ordered(code, saved, written) -> tuple[list[str], list[str]]:
    """Where SORT orders the texts of Order otherwise than Excel did, and what the engine puts
    to the next text otherwise."""
    cells = _book(code, saved, written, True)
    found = written[ORDER]["formulas"][1, SORTED]
    beside = max(col for _, col in written[ORDER]["formulas"]) + 2
    cells.write(ORDER, 1, beside, found)
    computed = [row[0] for row in cells.array(ORDER, 1, beside).rows]
    sorted_by_excel = _sorted(saved[ORDER], written)
    misordered = [
        f"{at}: Excel {excel!r}, engine {engine!r}"
        for at, (excel, engine) in enumerate(zip(sorted_by_excel, computed, strict=True), 1)
        if excel != engine
    ]
    return misordered, _wrong(saved, written, ORDER, cells)


@pytest.mark.parametrize("title", MATCHED)
def test_the_engine_matches_as_excel_matched(title, matched):
    wrong = matched[title]
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:60])


def test_texts_are_sorted_as_excel_sorted_them(ordered):
    wrong = ordered[0]
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:60])


def test_each_text_is_put_to_the_next_as_excel_put_it(ordered):
    wrong = ordered[1]
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:60])


def test_values_are_sorted_as_excel_sorted_them(matched):
    wrong = matched[SORTING]
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:60])
