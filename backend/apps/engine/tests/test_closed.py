"""The engine held to Excel over the closed domains of fractions (closed.py): what TEXT writes of
each code of a table written in the language, held to what Excel computed in
closed-<table>-<language>.xlsx."""

from pathlib import Path

import pytest

from apps.engine import numformat
from apps.engine.tests import closed, grammar
from apps.engine.tests.saved import computed, same, texted

HERE = Path(__file__).with_name("closed")


@pytest.mark.parametrize(
    ("table", "code"),
    [(table, code) for table in closed.TABLES for code in closed.languages(table)],
)
def test_text_writes_each_code_as_excel_did(table, code):
    path = HERE / f"closed-{table}-{code}.xlsx"
    wrong = []
    for at, ((written, value), (formula, excel)) in enumerate(
        zip(closed.rows(table, code), computed(path), strict=True), start=1
    ):
        assert texted(formula, value, written), (at, formula, value, written)
        given = value[1:-1] if value.startswith('"') else float(value)
        if len(written) > closed.SURE or grammar.misread(written, code, given):
            continue
        ours = numformat.shown(given, written, code, code)
        if not same(ours, excel, 0):
            wrong.append((at, written, value, ours, excel))
    assert not wrong, f"{len(wrong)} of {path.name}: {wrong[:20]}"
