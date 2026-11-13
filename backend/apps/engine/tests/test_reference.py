"""Every case of the workbooks Excel saved, in Croatian and in English, computed by the engine
from the formula Excel saved, as of the moment Excel saved it, and held to the value Excel saved
beside it: a number to the fifteen significant digits Excel keeps, or to the precision Excel
documents for a function it computes by iteration. TEXT over a code outside the grammar's domain
or one Excel misreads (grammar.py) is not held to Excel."""

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from random import Random

import pytest

from apps.engine import formats
from apps.engine.book import Cells
from apps.engine.parse import Call, Text, parse, written
from apps.engine.tests import grammar
from apps.engine.tests.cases import CASES, PATHS, READING
from apps.engine.tests.saved import MISSING, SAVED_ON, same, saved_at, saved_by, told, tolerance_of
from apps.engine.values import VALUE

OVERFLOW = 2**32
OVERFLOW_SHORT = 22
CASED = [
    (title, row, formula)
    for title, formulas in CASES.items()
    if title not in READING
    for row, formula in enumerate(formulas, 1)
]


def test_the_workbook_was_saved_by_excel_in_its_language(code, etalon):
    assert saved_by(PATHS[code]) == "Microsoft Excel"
    language = told(etalon["Locale"]["values"][1, 1])
    assert language == code, f"{PATHS[code].name} was saved by Excel in {language}"


def test_the_saved_workbook_holds_every_case(code, etalon):
    unsaved = [
        f"{title} {row}: {formula}"
        for title, formulas in CASES.items()
        for row, formula in enumerate(formulas, 1)
        if parse(etalon.get(title, {"formulas": {}})["formulas"].get((row, 1), "0"))
        != parse(formula)
    ]
    assert not unsaved, f"{PATHS[code].name} is to be saved again in Excel:\n" + "\n".join(unsaved)


def test_formulas_are_written_as_excel_wrote_them(etalon):
    rewritten = [
        f"{title}!{row},{col}: {text} as {written(parse(text))}"
        for title, sheet in etalon.items()
        for (row, col), text in sheet["formulas"].items()
        if written(parse(text)) != text
    ]
    assert not rewritten, "\n".join(rewritten)


@pytest.mark.parametrize(
    ("title", "row", "formula"),
    CASED,
    ids=[f"{title}-{row}-{formula}" for title, row, formula in CASED],
)
def test_the_engine_computes_what_excel_saved(code, title, row, formula, etalon, book):
    sheet = etalon.get(title, {"formulas": {}, "values": {}})
    text = sheet["formulas"].get((row, 1))
    assert text, f"{PATHS[code].name} is to be saved again in Excel: {title} {row}: {formula}"
    saved = sheet["values"][row, 1]
    if saved is MISSING:
        saved = ""
    computed = book.value(title, row, 1)
    held = same(computed, saved, tolerance_of(text)) or _outside(text, code)
    assert held, f"{text}: Excel {saved!r}, engine {computed!r}"


def _outside(text: str, code: str) -> bool:
    """Whether the formula is TEXT over a code the grammar does not hold in the language or
    Excel misreads."""
    tree = parse(text)
    if not (isinstance(tree, Call) and tree.name == "TEXT" and len(tree.args) == 2):
        return False
    given = tree.args[1]
    if isinstance(given, Text):
        given = given.value
    else:
        cells = Cells(code, saved_at(PATHS[code]), Random(0), SAVED_ON)
        cells.write("Code", 1, 1, written(given))
        given = cells.value("Code", 1, 1)
    return isinstance(given, str) and (
        not grammar.valid(given, code) or grammar.misread(given, code)
    )


def _overflowed(text: str, code: str, saved) -> bool:
    """Whether Excel overflowed reading the text, which the engine reads as no time: a word it
    reads a date or a time with taken as a part of the time, that part 2**32 less the word's
    number (a month's own, OVERFLOW_SHORT for AM, one less for PM), as Excel was seen to give
    it. The time is the word and up to two numbers beside it, as hours, minutes and seconds in
    their order, the number after them a fraction of a second, its digits counted by the number
    after it where Excel gives them that count; a date anywhere in the text adds whole days.
    6 A,5 in Croatian is 6 minutes and 2**32 - 22 seconds and a half, 6 PM:5 6 hours,
    2**32 - 21 minutes and 5 seconds, 1: Jul an hour and 2**32 - 7 minutes. NUMBERVALUE drops
    its spaces and its groups before the decimal mark first."""
    if not isinstance(saved, float):
        return False
    called = re.fullmatch(
        r'(?:_xlfn\.)?(VALUE|DATEVALUE|TIMEVALUE|NUMBERVALUE)\("([^"]*)"(?:,"([^"]*)")?(?:,"([^"]*)")?\)',
        text,
    )
    if called is None:
        return False
    name, written, decimal, group = called.groups()
    if name == "NUMBERVALUE":
        written = _numbervalue_text(written, decimal, group, code)
    tokens = re.findall(r"[0-9]+|[^\W\d_]+", written)
    for at, word in enumerate(tokens):
        if (number := _word_number(word, code)) is None:
            continue
        for start in range(max(at - 2, 0), at + 1):
            for end in range(at + 1, min(start + 3, len(tokens)) + 1):
                parts = [
                    OVERFLOW - number if place == at else tokens[place]
                    for place in range(start, end)
                ]
                if not all(isinstance(part, int) or part.isdigit() for part in parts):
                    continue
                for seconds in _clock(parts, tokens[end:]):
                    if _overflow_matches(name, seconds, saved):
                        return True
    return False


def _word_number(word: str, code: str) -> int | None:
    if re.fullmatch("[AaPp][Mm]?", word):
        return OVERFLOW_SHORT - (word[0] in "Pp")
    return formats._month(word, code)


def _numbervalue_text(text: str, decimal: str | None, group: str | None, code: str) -> str:
    marks = formats.marks(code)
    decimal = (decimal or marks[0])[:1]
    if group is None:
        group = marks[1] if marks[1] != decimal else marks[0]
    text = re.sub("[ \t\n\r]", "", text)
    whole, point, places = text.partition(decimal)
    return whole.replace(group[:1], "") + point + places


def _clock(parts: list, after: list[str]):
    """The seconds the parts make as hours, minutes and seconds in their order, with each
    fraction of a second the numbers after them may give."""
    numbers = [int(part) for part in parts]
    units = {1: ((3600,), (60,), (1,)), 2: ((3600, 60), (60, 1)), 3: ((3600, 60, 1),)}
    fractions = [Decimal(0)]
    if after[:1] and after[0].isdigit():
        fractions.append(Decimal(f"0.{after[0]}"))
        if after[1:2] and after[1].isdigit():
            fractions.append(Decimal(int(after[0])).scaleb(-len(after[1])))
    for unit in units[len(numbers)]:
        whole = sum(number * each for number, each in zip(numbers, unit, strict=True))
        for fraction in fractions:
            yield (whole + fraction).quantize(Decimal("0.001"), ROUND_HALF_UP)


def _overflow_matches(name: str, seconds: Decimal, saved: float) -> bool:
    serial = float(seconds / formats.SECONDS_A_DAY)
    tolerance = 1e-9 + 16 * math.ulp(serial)
    if name == "TIMEVALUE":
        apart = abs(serial % 1 - saved)
        return min(apart, 1 - apart) <= tolerance
    if name == "DATEVALUE":
        return saved.is_integer() and saved >= math.floor(serial)
    days = round(saved - serial)
    return days >= 0 and abs(serial + days - saved) <= tolerance + 16 * math.ulp(saved)


@pytest.mark.parametrize("title", READING)
def test_the_engine_reads_text_as_excel_did(code, title, etalon, book):
    sheet = etalon.get(title)
    if sheet is None:
        pytest.fail(f"{PATHS[code].name} is to be saved again in Excel")
    misread = []
    for (row, _), text in sorted(sheet["formulas"].items()):
        saved = sheet["values"][row, 1]
        computed = book.value(title, row, 1)
        if same(computed, "" if saved is MISSING else saved, tolerance_of(text)):
            continue
        if _outside(text, code):
            continue
        if not (computed == VALUE and _overflowed(text, code, saved)):
            misread.append(f"{text}: Excel {saved!r}, engine {computed!r}")
    assert not misread, f"{len(misread)} misread:\n" + "\n".join(misread)
