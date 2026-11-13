import itertools
from datetime import date

import pytest

from apps.engine import dates, formats, sql, values
from apps.engine.collation import collation
from apps.engine.formats import CULTURES
from apps.engine.values import BLANK, VALUE

EN = formats.Language("en", 2026, "cp1252")
HR = formats.Language("hr", 2026, "cp1250")


@pytest.mark.parametrize(
    ("number", "digits", "expected"),
    [(2.5, 0, 3), (-2.5, 0, -3), (2.675, 2, 2.68), (1.005, 2, 1.01), (1234.5678, -2, 1200)],
)
def test_rounding_is_half_away_from_zero_on_the_number_shown(number, digits, expected):
    assert values.rounded(number, digits) == expected


def test_the_calendar_counts_the_29th_of_february_1900():
    assert dates.serial(date(1900, 2, 28)) == 59
    assert dates.serial(date(1900, 3, 1)) == 61
    assert dates.serial(date(2026, 10, 27)) == 46322
    assert dates.day_of(60) == (1900, 2, 29)
    assert dates.day_of(0) == (1900, 1, 0)
    assert dates.day_of(dates.LAST_SERIAL + 1) is None


def test_values_read_as_numbers_logicals_and_text():
    assert values.number(True, EN) == 1
    assert values.number(BLANK, EN) == 0
    assert values.number("50%", EN) == 0.5
    assert values.number("abc", EN) is VALUE
    assert values.logical(BLANK, EN) is False
    assert values.logical(-0.5, EN) is True
    assert values.text(BLANK, EN) == ""
    assert values.text(1 / 3, EN) == "0.333333333333333"
    assert values.text(True, HR) == "TRUE"
    assert values.logical("true", HR) is True
    assert values.logical("ISTINA", HR) is VALUE


def test_values_order_as_excel_orders_them():
    assert values.compare("a", "A", EN) == 0
    assert values.compare("1", 2.0, EN) == 1
    assert values.compare(True, "z", EN) == 1
    assert values.compare(BLANK, 0.0, EN) == 0
    assert values.compare(BLANK, "", EN) == 0
    assert values.compare(0.1 + 0.2, 0.3, EN) == 0
    assert values.compare("č", "d", HR) == -1


@pytest.mark.parametrize("code", CULTURES)
def test_texts_sql_compares_by_their_lower_case_compare_so(code):
    weighed = collation(code)
    digraphs = "cCdDjJlLnNsSzZžŽ"
    texts = [
        text
        for text in (
            *(a + b for a in sql.COMPARED for b in sql.COMPARED),
            *map("".join, itertools.product(digraphs, repeat=3)),
        )
        if all(each in sql.COMPARED for each in text)
        and not any(form in text for form in sql.UNEVEN)
    ]
    lowers, keys = {}, {}
    for text in texts:
        found = weighed.equality(text)
        assert found is not None, text
        lowers.setdefault(found, set()).add(text.lower())
        keys.setdefault(text.lower(), set()).add(found)
    assert [each for each in lowers.values() if len(each) > 1] == []
    assert [text for text, each in keys.items() if len(each) > 1] == []


@pytest.mark.parametrize(
    ("text", "locale", "expected"),
    [
        (" 12 ", EN, 12),
        ("1e3", EN, 1000),
        ("(12)", EN, -12),
        ("1,234.5", EN, 1234.5),
        ("1,2", EN, None),
        ("123456789012345678", EN, 1.23456789012345e17),
        ("10/27/2026", EN, 46322),
        ("10/27/26", EN, 46322),
        ("1:45 PM", EN, (13 * 60 + 45) / 1440),
        ("1,5", HR, 1.5),
        ("1.234,5", HR, 1234.5),
        ("1,234.5", HR, None),
        ("27.10.2026", HR, 46322),
        ("27. 10. 2026", HR, 46322),
        ("27.10.2026.", HR, None),
        ("27.10.", HR, None),
        ("10/27/2026", HR, None),
        ("2026-10-27", HR, 46322),
        ("abc", HR, None),
    ],
)
def test_text_read_in_the_language(text, locale, expected):
    assert formats.read(text, locale) == expected


def test_a_date_without_its_year_falls_in_this_one():
    assert formats.read("1.5", HR) == dates.serial(date(2026, 5, 1))
    assert formats.read("10/27", EN) == dates.serial(date(2026, 10, 27))


def test_two_numbers_that_are_no_day_and_month_are_a_month_and_year():
    assert formats.read("10/27", HR) == dates.serial(date(2027, 10, 1))
    assert formats.read("10/2027", EN) == dates.serial(date(2027, 10, 1))
    assert formats.read("13/2026", HR) is None


@pytest.mark.parametrize(
    ("value", "mark", "width", "expected"),
    [
        (0.0, ".", formats.SHOWN, "0"),
        (1 / 3, ",", formats.SHOWN, "0,333333333333333"),
        (0.1 + 0.2, ",", formats.SHOWN, "0,3"),
        (1.23456789012345e17, ".", formats.SHOWN, "123456789012345000"),
        (1e20, ".", formats.WRITTEN, "100000000000000000000"),
        (1e20, ".", formats.SHOWN, "1E+20"),
        (1e21, ".", formats.WRITTEN, "1E+21"),
        (-0.000001, ",", formats.SHOWN, "-0,000001"),
        (1.2345e-7, ".", formats.SHOWN, "0.00000012345"),
        (1.23456789012345e-8, ".", formats.SHOWN, "1.23456789012345E-08"),
        (-2.5e300, ".", formats.SHOWN, "-2.5E+300"),
        (1 / 3, ",", formats.GENERAL, "0,333333333"),
        (-1 / 3, ",", formats.GENERAL, "-0,333333333"),
        (1234567890.55, ".", formats.GENERAL, "1234567891"),
        (123456789012, ".", formats.GENERAL, "1.23457E+11"),
        (99999999999.9, ".", formats.GENERAL, "1E+11"),
        (0.000123456789, ".", formats.GENERAL, "0.000123457"),
        (0.0000123456789, ".", formats.GENERAL, "1.23457E-05"),
    ],
)
def test_numbers_are_written_in_fifteen_digits_within_a_width(value, mark, width, expected):
    assert formats.numeral(value, mark, width) == expected


def test_typed_digits_past_the_fifteenth_turn_to_zeros():
    assert formats.entered("123456789012345678") == 1.23456789012345e17
    assert formats.entered("0.1234567890123456789") == 0.123456789012345
    assert formats.entered("9.999999999999999999E+307") == 9.99999999999999e307
    assert formats.entered("1E+308") is None
    assert formats.entered("9E400449787042") is None
    assert formats.entered("1E-99999999999999999999999") is None
    assert formats.entered("4.99999E-321") is None
    assert formats.entered("0E400") is None
    assert formats.entered("4287E-312") == 0
