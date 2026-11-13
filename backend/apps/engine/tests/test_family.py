"""Families of formulas (D22), each computed in one query over tables drawn at random, held to
what Python computes for every one of their cells: numbers, texts with Croatian and other
letters, blanks, logicals and errors, read by references relative and absolute, from the
table's own rows, the rows next to them and another table."""

import json
from collections import Counter
from datetime import datetime
from random import Random

import pytest
from django.db import connection

from apps.engine.book import Cells
from apps.engine.family import Family, Sheet
from apps.engine.parse import parse, relative
from apps.engine.sql import Unsupported, text_literal
from apps.engine.tests.saved import SAVED_ON, same, tolerance_of
from apps.engine.values import Error, loaded, stored

pytestmark = pytest.mark.django_db

OWN = "Podaci"
CODES = "Šifre"
ROWS = 300
CODED = 120
COL = 7

TEXTS = (
    "čelik", "Čelik", "ČELIK", "šaraf", "ŠARAF", "matica", "Matica", "đak", "Đak", "ćevap",
    "žica", "12", "1,5", "1.5", "", " razmak  dva ", "x*y", "a?b", "a~b", "ß", "ǅep", "ΣΙΓΜΑ",
    "TRUE", "abc", "ABC", ">5", "<=-0,5", "<>12", ">=1.5", "<1,5", "Ћевап", "ћевап", "ΌΣΟΣ",
    "όσος", "όσοσ", "ſ", "S", "\u212a", "k", "İ", "ı", "i",
)  # fmt: skip
ERRORS = ("#N/A", "#DIV/0!", "#VALUE!")

FAMILIES = (
    'IF(ISBLANK(A{r}),"",XLOOKUP(A{r},Šifre!$A$1:$A$120,Šifre!$B$1:$B$120))',
    'IFNA(XLOOKUP(A{r},Šifre!$A$1:$A$120,Šifre!$B$1:$B$120,"nema",0,-1),"x")',
    'XLOOKUP(A{r},Šifre!$A$1:$A$120,Šifre!$B$1:$B$120,"nema",2)',
    "VLOOKUP(A{r},Šifre!$A:$B,2,FALSE)",
    "MATCH(A{r},Šifre!$A:$A,0)",
    "INDEX(Šifre!$B:$B,MATCH(A{r},Šifre!$A:$A,0))",
    "ISNA(MATCH(D{r},Šifre!$A$1:$A$120,0))",
    "SUMIF($A$1:$A$301,A{r},$B$1:$B$301)",
    'SUMIFS($B:$B,$A:$A,A{r},$C:$C,">0")',
    "COUNTIF($A:$A,A{r})",
    'COUNTIFS($A:$A,">5",$B:$B,"<100")',
    'SUMIF($B$1:$B$301,">"&B{r},$C$1:$C$301)',
    'COUNTIF($B:$B,"<="&C{r})',
    'SUMIFS($C:$C,$A:$A,A{r},$B:$B,">="&B{r})',
    'SUMIFS($C:$C,$B:$B,">"&B{r},$C:$C,"<"&C{r})',
    'SUMIF($A:$A,"<>"&A{r},$B:$B)',
    'COUNTIFS($D:$D,"<"&B{r},$A:$A,"<>"&C{r})',
    'SUMIFS($B:$B,$D:$D,"="&D{r},$E:$E,"<>"&E{r})',
    'COUNTIFS($D:$D,">="&E{r},$E:$E,"<"&D{r})',
    'SUMIF($E:$E,">"&A{r},$B:$B)',
    "SUMIF($D:$D,D{r},$B:$B)+COUNTIF($E:$E,E{r})",
    "B{r}*C{r}",
    "ROUND(B{r}*C{r},2)",
    "ROUNDUP(B{r},1)+INT(C{r})",
    "ROUNDDOWN(C{r},-1)",
    "IFERROR(B{r}/C{r},0)",
    "ISERROR(B{r}/C{r})",
    "B{r}-B{p}",
    "SUM(B{p}:B{n})",
    "SUM(B{r}:D{r})",
    "AVERAGE(B{r}:C{r})",
    "COUNT(B{r}:E{r})+COUNTA(A{r}:E{r})",
    "MAX(B{r},C{r})-MIN($B$1:$B$301)",
    "$B$1*B{r}+Šifre!$B$1",
    "A{r}=Šifre!A{r}",
    "$B$100:$B$200*2",
    "AND(B{r}>0,C{r}<10)",
    "OR(B{r},C{r})",
    "NOT(B{r})",
    "IF(B{r}>C{r},D{r},E{r})",
    "D{r}<E{r}",
    "LEFT(D{r},3)&UPPER(E{r})",
    'TRIM(D{r})&"-"&LEN(E{r})',
    "MID(D{r},2,3)&RIGHT(E{r},2)&LOWER(D{r})",
    "EXACT(D{r},E{r})",
    "CONCATENATE(D{r},B{r})",
    "N(B{r})&T(D{r})",
    "ISNUMBER(B{r})+ISTEXT(D{r})*2+ISLOGICAL(C{r})*4+ISBLANK(E{r})*8",
    "ABS(B{r})",
    "HYPERLINK(D{r})",
)


def _number(draw: Random) -> float:
    return draw.choice(
        (
            float(draw.randint(-50, 50)),
            round(draw.uniform(-1000, 1000), 2),
            draw.uniform(-1, 1),
            0.1 + 0.2,
            1e15 + draw.randint(0, 9),
        )
    )


def _drawn(draw: Random, weights: tuple[int, int, int, int, int]):
    kind = draw.choices(("blank", "number", "text", "logical", "error"), weights)[0]
    if kind == "number":
        return _number(draw)
    if kind == "text":
        return draw.choice(TEXTS)
    if kind == "logical":
        return draw.random() < 0.5
    if kind == "error":
        return Error(draw.choice(ERRORS))
    return None


def _key(draw: Random):
    if draw.random() < 0.4:
        return float(draw.randint(1, 30))
    return _drawn(draw, (2, 0, 6, 1, 1))


def _tables(seed: int) -> dict[str, dict[tuple[int, int], object]]:
    draw = Random(seed)
    own = {}
    for row in range(1, ROWS + 2):
        own[row, 1] = _key(draw)
        own[row, 2] = _drawn(draw, (2, 12, 2, 1, 1))
        own[row, 3] = _drawn(draw, (2, 12, 2, 1, 1))
        own[row, 4] = _drawn(draw, (2, 2, 12, 1, 1))
        own[row, 5] = _drawn(draw, (2, 2, 12, 1, 1))
    codes = {}
    for row in range(1, CODED + 1):
        codes[row, 1] = _key(draw)
        codes[row, 2] = _drawn(draw, (1, 6, 6, 1, 1))
    return {
        name: {place: value for place, value in cells.items() if value is not None}
        for name, cells in ((OWN, own), (CODES, codes))
    }


def _loaded(tables) -> None:
    rows = [
        (name.casefold(), row, json.dumps({}))
        for name, cells in tables.items()
        for row in range(1, max(row for row, _ in cells) + 1)
    ]
    held = {(name.casefold(), row): {} for name, row, _ in rows}
    for name, cells in tables.items():
        for (row, col), found in cells.items():
            held[name.casefold(), row][str(col)] = stored(found)
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TEMP TABLE family_rows (sheet text, y int, vals jsonb, PRIMARY KEY (sheet, y))"
        )
        cursor.executemany(
            "INSERT INTO family_rows VALUES (%s, %s, %s::jsonb)",
            [(name, row, json.dumps(vals)) for (name, row), vals in held.items()],
        )


def _sheets(cells: Cells):
    def sheet(name: str) -> Sheet | None:
        extent = cells.extent(name)
        if extent is None:
            return None
        return Sheet(
            f"(SELECT y, vals FROM family_rows WHERE sheet = {text_literal(name.casefold())})",
            lambda col: text_literal(str(col)),
            lambda alias, key: f"{alias}.vals -> {key}",
            extent,
        )

    return sheet


def _written(text: str, row: int) -> str:
    return text.format(r=row, p=row - 1, n=row + 1)


def _book(tables, code: str) -> Cells:
    cells = Cells(code, datetime(2026, 10, 27, 12), Random(0), SAVED_ON)
    for name, held in tables.items():
        for (row, col), found in held.items():
            cells.put(name, row, col, found)
    return cells


@pytest.mark.parametrize("seed", (1, 2))
def test_a_family_computes_in_one_query_what_python_computes_for_each_cell(code, seed):
    tables = _tables(seed)
    _loaded(tables)
    wrong = []
    for text in FAMILIES:
        top = 2 if "{p}" in text else 1
        cells = _book(tables, code)
        trees = set()
        for row in range(top, ROWS + 1):
            cells.write(OWN, row, COL, _written(text, row))
            trees.add(relative(parse(_written(text, row)), row, COL))
        assert len(trees) == 1, text
        try:
            query = Family(_sheets(cells), OWN, COL, top, ROWS).query(trees.pop(), cells.language)
        except Unsupported as reason:
            print(f"{text}: python ({reason})")
            continue
        with connection.cursor() as cursor:
            cursor.execute(query)
            found = dict(cursor.fetchall())
        tally = Counter()
        for row in range(top, ROWS + 1):
            if found[row] is None:
                tally["null"] += 1
                continue
            tally["sql"] += 1
            given = found[row]
            value = loaded(json.loads(given) if isinstance(given, str) else given)
            computed = cells.value(OWN, row, COL)
            if not same(value, computed, tolerance_of(_written(text, row))):
                wrong.append(f"{_written(text, row)}: Python {computed!r}, SQL {value!r}")
        print(f"{text}: {dict(tally)}")
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:60])
