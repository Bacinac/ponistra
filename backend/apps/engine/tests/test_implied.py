"""The number format Excel gives a cell as a text is typed in it or a formula entered, and
which of them a cell keeps where it holds one, held to what Excel gave the cells of implied.py's
files under the Croatian and the English regional format (D22 E3), what a cell shows in its
format, held to what each cell of them showed in Excel where the grammar holds the format, and
the formulas Excel refused to enter."""

import csv
import re

import pytest

from apps.content import calculation
from apps.engine.carried import carried, entered
from apps.engine.evaluate import formula
from apps.engine.formats import Language
from apps.engine.parse import Unreadable, parse
from apps.engine.registry import FUNCTIONS
from apps.engine.tests import grammar, implied
from apps.engine.tests.saved import MISSING, SAVED_ON, hashed, read, same, saved_at

PATHS = {code: path.with_suffix(".xlsx") for code, path in implied.PATHS.items()}


@pytest.fixture(scope="module")
def saved(code) -> dict:
    return next(iter(read(PATHS[code], code=code).values()))


def _typed(code: str) -> list[tuple[int, str]]:
    """Each text typed in column A of the file's first rows, by its row."""
    rows = implied.rows(code)
    over = len(implied.KINDS[code]) + len(implied.typed(code)) + 1
    return [(y, rows[y - 1][0]) for y in range(2, over + 1)]


def test_a_typed_text_takes_the_value_and_the_format_excel_gave_it(code, saved):
    language = Language(code, saved_at(PATHS[code]).year, SAVED_ON)
    wrong = []
    for y, text in _typed(code):
        excel = saved["constants"].get((y, 1), "")
        value = calculation.typed(text, language) if text else ""
        format = calculation.implied(text, language)
        given = saved["formats"].get((y, 1), "")
        if not same(value, excel, 0) or format != given:
            wrong.append((y, text, value, excel, format, given))
    assert not wrong, f"{len(wrong)} of {PATHS[code].name}: {wrong[:20]}"


def _drawn_again(text: str | None) -> bool:
    """Whether a formula calls a volatile function, which Excel computed again between saving the
    workbook and the CSV of what its cells showed (A11+NOW())."""
    names = re.findall(r"([A-Z][A-Z0-9.]*)\(", text or "")
    return any(FUNCTIONS[name].volatile for name in names if name in FUNCTIONS)


def test_a_cell_shows_its_value_in_its_format_as_excel_showed_it(code, saved):
    with implied.SHOWN[code].open(encoding="utf-8-sig", newline="") as file:
        lines = list(csv.reader(file, delimiter=implied.SYNTAX[code].list))
    excel = {
        (y, x): text for y, line in enumerate(lines, 1) for x, text in enumerate(line, 1) if text
    }
    # Excel shows a cell in the format it was given and saves some formats in a form that reads
    # otherwise (# ?/?, as #,\ ?/?, ., as .), so a cell the saved form does not show as Excel
    # did is held to the format given.
    formats = {(y, x): format for y, x, format, _ in implied.entries(code) if format}
    wrong = []
    for place in sorted(saved["constants"].keys() | saved["values"].keys()):
        if _drawn_again(saved["formulas"].get(place)):
            continue
        value = saved["constants"].get(place, saved["values"].get(place))
        value = "" if value is MISSING else value
        format = saved["formats"].get(place, "")
        if format and (
            not grammar.valid(format, "en") or grammar.misread(format, "en", value, celled=True)
        ):
            continue
        shown = calculation.shown(value, format, code)
        given = excel.get(place, "")
        if shown != given and formats.get(place, format) != format:
            format = formats[place]
            shown = calculation.shown(value, format, code)
        if shown != given and not (hashed(shown) and hashed(given)):
            wrong.append((place, value, format, shown, given))
    assert not wrong, f"{len(wrong)} of {implied.SHOWN[code].name}: {wrong[:20]}"


def test_the_engine_refuses_each_formula_excel_refused_to_enter(code, saved):
    taken = saved["constants"].keys() | saved["formulas"].keys()
    wrong, refused = [], 0
    for y, x, _, text in implied.entries(code):
        if not text.startswith("="):
            continue
        try:
            formula(parse(text[1:], implied.SYNTAX[code]))
        except Unreadable:
            ours = True
        else:
            ours = False
        refused += ours
        if ours != ((y, x) not in taken):
            wrong.append(((y, x), text, ours))
    assert refused, "no formula refused, as Excel refuses some of them"
    assert not wrong, f"{len(wrong)} of {PATHS[code].name}: {wrong[:20]}"


def _carried(code: str, saved: dict, text: str) -> str:
    """The format the formula gives its cell, by the formats Excel gave the cells it reads."""
    of = saved["formats"]
    tree = parse(text[1:], implied.SYNTAX[code])
    return carried(tree, lambda ref: of.get((ref.start.row, ref.start.col), ""), code)


def test_a_formula_takes_the_format_of_what_it_reads_as_excel_gave_it(code, saved):
    wrong = []
    for y, x, held, text in implied.entries(code):
        if held or not text.startswith("=") or (y, x) not in saved["formulas"]:
            continue
        ours, given = _carried(code, saved, text), saved["formats"].get((y, x), "")
        if ours != given:
            wrong.append(((y, x), text, ours, given))
    assert not wrong, f"{len(wrong)} of {PATHS[code].name}: {wrong[:20]}"


def test_a_cell_holding_a_format_keeps_the_value_and_the_format_excel_kept(code, saved):
    language = Language(code, saved_at(PATHS[code]).year, SAVED_ON)
    taken = saved["constants"].keys() | saved["formulas"].keys()
    wrong = []
    for y, x, held, text in implied.formatted(code):
        if (y, x) not in taken:
            continue
        kept = implied.kept(held, code)
        if text.startswith("="):
            ours, value = entered(kept, _carried(code, saved, text)), None
        else:
            ours = entered(kept, calculation.implied(text, language, kept))
            value = calculation.typed(calculation.kept(text, language, ours), language)
        given, excel = saved["formats"].get((y, x), ""), saved["constants"].get((y, x), "")
        if ours != given or value is not None and not same(value, excel, 0):
            wrong.append(((y, x), held, text, ours, given, value, excel))
    assert not wrong, f"{len(wrong)} of {PATHS[code].name}: {wrong[:20]}"
