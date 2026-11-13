"""The workbook of totals Excel computes for the sweep (D22): one sheet of ROWS rows of data, a
key in A, amounts of both signs in B, positive ones in C, dates in D, bounds in E and amounts
with a few errors in F, and beside them FAMILIES, each filled down the rows it reads, SUMIF,
SUMIFS, COUNTIF and COUNTIFS whose criteria each row computes from its own cells. `python -m
apps.engine.tests.sweep <file>` writes it without values; saved by Excel, once in Croatian and
once in English, it comes here as sweep-hr.xlsx and sweep-en.xlsx. Each set of criteria takes
thousands of numbers in the order SUM adds them, small and large, cancelling and not, so a
total Excel saved tells its order and its rounding to the last of the seventeen digits it saves.
The keys are codes, numbers, texts that read as numbers, logicals and blanks, and words whose
case differs, in Croatian, Cyrillic and Greek letters and those whose case changes their length."""

import sys
from pathlib import Path
from random import Random

from openpyxl import Workbook

from apps.engine.parse import parse, written
from apps.engine.tests.saved import LANGUAGES, TOLD

PATHS = {code: Path(__file__).with_name(f"sweep-{code}.xlsx") for code in LANGUAGES}
SHEET = "Sweep"
ROWS = 20_000
LOCALE = (1, 7)
FIRST = 8
FAMILIES = (
    f"SUMIF($A$1:$A${ROWS},A{{r}},$B$1:$B${ROWS})",
    "SUMIF($A:$A,A{r},$F:$F)",
    "COUNTIF($A:$A,A{r})",
    'SUMIF($D:$D,"<="&D{r},$B:$B)',
    'SUMIF($B:$B,">"&B{r},$C:$C)',
    'COUNTIF($B:$B,"<"&E{r})',
    'SUMIFS($B:$B,$A:$A,A{r},$D:$D,"<="&D{r})',
    'SUMIFS($C:$C,$D:$D,">="&D{r},$B:$B,"<"&E{r})',
    'SUMIF($A:$A,"<>"&A{r},$B:$B)',
    'COUNTIFS($A:$A,"<>"&A{r},$D:$D,">"&D{r})',
    'SUMIFS($B:$B,$A:$A,"="&A{r},$E:$E,">="&B{r})',
)
CODES = tuple(f"ART-{n:05d}" for n in range(1, 151))
WORDS = (
    "čelik", "Čelik", "ČELIK", "šaraf", "Šaraf", "matica", "MATICA", "đak", "Đak", "ćevap",
    "žica", "Ћевап", "ћевап", "ЋЕВАП", "ΌΣΟΣ", "όσος", "όσοσ", "straße", "STRASSE", "ǅep",
    "ǆep", "Ǆep", "İstanbul", "istanbul", "ıstanbul", "Kelvin", "kelvin", "ſtil", "stil",
    "12", "1,5", "1.5", "TRUE", "false", " razmak ", "abc", "ABC", ">5", "<>12",
)  # fmt: skip
CANCELLING = (0.1, 0.2, -0.3, 0.7, -0.6, -0.1, 1.1, -2.2, 0.3, -0.7)
ERRORS = ("=NA()", "=1/0", '=VALUE("x")')


def _key(draw: Random):
    drawn = draw.random()
    if drawn < 0.7:
        return draw.choice(CODES)
    if drawn < 0.85:
        return draw.choice(WORDS)
    if drawn < 0.95:
        return draw.randint(0, 50)
    if drawn < 0.97:
        return draw.random() < 0.5
    return None


def _signed(draw: Random):
    drawn = draw.random()
    if drawn < 0.75:
        return round(draw.uniform(-1000, 1000), 2)
    if drawn < 0.87:
        return draw.choice(CANCELLING)
    if drawn < 0.92:
        return round(draw.uniform(-1e12, 1e12), 2)
    if drawn < 0.95:
        return None
    if drawn < 0.97:
        return draw.choice(("12,5", "12.5", "-7"))
    return draw.randint(-50, 50)


def _with_errors(draw: Random):
    drawn = draw.random()
    if drawn < 0.0003:
        return draw.choice(ERRORS)
    if drawn < 0.01:
        return draw.choice((True, "tekst", None))
    return round(draw.uniform(0, 100), 2)


def table() -> dict[tuple[int, int], object]:
    """The data of the sheet by place, the same each time it is drawn."""
    draw = Random(27)
    cells = {}
    for row in range(1, ROWS + 1):
        cells[row, 1] = _key(draw)
        cells[row, 2] = _signed(draw)
        cells[row, 3] = round(draw.uniform(0, 1000), 2) if draw.random() < 0.97 else None
        cells[row, 4] = draw.randint(46000, 46364)
        cells[row, 5] = round(draw.uniform(-1000, 1000), 2)
        cells[row, 6] = _with_errors(draw)
    return {place: value for place, value in cells.items() if value is not None}


def formula(family: str, row: int) -> str:
    return family.format(r=row)


def workbook() -> Workbook:
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    for (row, col), value in table().items():
        sheet.cell(row, col, value)
    sheet.cell(*LOCALE, "=" + TOLD)
    for col, family in enumerate(FAMILIES, FIRST):
        for row in range(1, ROWS + 1):
            sheet.cell(row, col, "=" + written(parse(formula(family, row))))
    return book


if __name__ == "__main__":
    workbook().save(sys.argv[1])
