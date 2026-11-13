"""The engine held to Excel over the grammar's domain (grammar.py): what TEXT writes of each code
written in the language, held to what Excel computed in grammar-<language>.xlsx, and what a cell
of a file shows in each canonical code, held to what Excel showed of it on opening the file
(grammar-opened-<nn>-<language>-shown.csv)."""

import csv
from io import BytesIO
from pathlib import Path

from apps.content import calculation
from apps.engine import numformat
from apps.engine.tests import grammar, implied
from apps.engine.tests.saved import hashed, read, same, texted

HERE = Path(__file__).with_name("grammar")


def test_each_built_in_code_is_in_the_domain(code):
    outside = [each for each in grammar.built_in(code) if not grammar.valid(each, "en")]
    assert not outside, outside


def test_text_writes_each_code_as_excel_did(code):
    path = HERE / f"grammar-{code}.xlsx"
    saved = read(path)["TEXT"]
    wrong = []
    for y, (written, value) in enumerate(grammar.rows(code), start=1):
        formula = saved["formulas"][(y, 1)]
        given = f'"{grammar.TEXT}"' if value is None else str(value)
        assert texted(formula, given, written), (y, formula, value, written)
        given = grammar.TEXT if value is None else float(value)
        if grammar.misread(written, code, given):
            continue
        ours = numformat.shown(given, written, code, code)
        excel = saved["values"][(y, 1)]
        if not same(ours, excel, 0):
            wrong.append((y, written, value, ours, excel))
    assert not wrong, f"{len(wrong)} of {path.name}: {wrong[:20]}"


def test_a_cell_shows_each_code_as_excel_showed_it(code):
    wrong = []
    for name, rows in grammar.books(code).items():
        file = BytesIO()
        grammar.book(rows).save(file)
        cells = next(iter(read(file, code=code).values()))
        path = HERE / f"{name}-{code}-shown.csv"
        with path.open(encoding="utf-8-sig", newline="") as shown:
            lines = list(csv.reader(shown, delimiter=implied.SYNTAX[code].list))
        excel = {(y, x): text for y, line in enumerate(lines, 1) for x, text in enumerate(line, 1)}
        for y, (given, values) in enumerate(rows, start=1):
            for x in range(1, len(values) + 1):
                value = cells["constants"][(y, x)]
                if grammar.misread(given, "en", value, celled=True):
                    continue
                format = cells["formats"].get((y, x), "")
                ours = calculation.shown(value, format, code)
                text = excel.get((y, x), "")
                if ours != text and not (hashed(ours) and hashed(text)):
                    wrong.append((name, (y, x), given, format, value, ours, text))
    assert not wrong, f"{len(wrong)} of grammar-opened-{code}: {wrong[:20]}"
