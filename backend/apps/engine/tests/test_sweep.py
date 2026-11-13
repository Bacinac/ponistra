"""The sweep (D22) held to Excel: each family of the workbook Excel saved in Croatian and in
English (sweep.py), computed in one query over the data Excel saved beside it, every one of its
cells by the sweep, a total equal to the one Excel saved to the last bit and an error to the
one Excel met first."""

import json

import pytest
from django.db import connection

from apps.engine.family import Family
from apps.engine.parse import parse, relative
from apps.engine.tests.saved import read, same, saved_by, told
from apps.engine.tests.sweep import FAMILIES, FIRST, LOCALE, PATHS, ROWS, SHEET, formula, table
from apps.engine.tests.test_family import _book, _loaded, _sheets
from apps.engine.values import loaded

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def saved(code) -> dict:
    return read(PATHS[code], shared=True)[SHEET]


def test_the_sweep_was_saved_by_excel_in_its_language(code, saved):
    assert saved_by(PATHS[code]) == "Microsoft Excel"
    language = told(saved["values"][LOCALE])
    assert language == code, f"{PATHS[code].name} was saved by Excel in {language}"


def test_the_saved_sweep_holds_the_data_and_the_families(code, saved):
    drawn = {
        place: float(value) if type(value) is int else value
        for place, value in table().items()
        if not (isinstance(value, str) and value.startswith("="))
    }
    data = {place: value for place, value in saved["constants"].items() if place[1] < FIRST}
    unsaved = (
        [
            f"{row},{col}: {data.get((row, col))!r} for {drawn.get((row, col))!r}"
            for row, col in data.keys() | drawn.keys()
            if not same(data.get((row, col)), drawn.get((row, col)), 0)
        ]
        + [
            f"{row},{col}: {text}"
            for (row, col), text in saved["formulas"].items()
            if col >= FIRST and parse(text) != parse(formula(FAMILIES[col - FIRST], row))
        ]
        + [
            f"{row},{col}: no value"
            for col in range(FIRST, FIRST + len(FAMILIES))
            for row in range(1, ROWS + 1)
            if (row, col) not in saved["values"]
        ]
    )
    assert not unsaved, f"{PATHS[code].name} is to be saved again in Excel:\n" + "\n".join(
        unsaved[:20]
    )


def test_the_sweep_totals_what_excel_saved(code, saved):
    tables = {
        SHEET: {
            place: value
            for cells in (saved["constants"], saved["values"])
            for place, value in cells.items()
            if place[1] < FIRST
        }
    }
    _loaded(tables)
    cells = _book(tables, code)
    wrong = []
    for col, family in enumerate(FAMILIES, FIRST):
        tree = relative(parse(formula(family, 1)), 1, col)
        query = Family(_sheets(cells), SHEET, col, 1, ROWS).query(tree, cells.language)
        with connection.cursor() as cursor:
            cursor.execute(query)
            found = dict(cursor.fetchall())
        for row in range(1, ROWS + 1):
            excel = saved["values"][row, col]
            given = found[row]
            if given is None:
                wrong.append(f"{formula(family, row)}: Excel {excel!r}, left to Python")
                continue
            value = loaded(json.loads(given) if isinstance(given, str) else given)
            if type(value) is not type(excel) or value != excel:
                wrong.append(f"{formula(family, row)}: Excel {excel!r}, SQL {value!r}")
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:60])
