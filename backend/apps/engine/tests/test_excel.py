from pathlib import Path

import pytest

from apps.engine import formats
from apps.engine.formats import CULTURES
from apps.engine.tests import excel

# Application.International's settings by their index: xlCountrySetting, xlDecimalSeparator,
# xlThousandsSeparator, xlDateSeparator, xlYearCode to xlSecondCode and xlGeneralFormatName.
COUNTRY, DECIMAL, GROUP, DAY_MARK, GENERAL = 2, 3, 4, 17, 26
CODED = {"year": 19, "month": 20, "day": 21, "hour": 22, "minute": 23, "second": 24}


def test_the_script_knows_the_country_of_every_document_language():
    assert excel.COUNTRIES.keys() == CULTURES.keys()
    written = excel.script()
    assert all(f"'{code}' = '{name}'" in written for code, name in CULTURES.items())


@pytest.mark.parametrize("code", CULTURES)
def test_the_language_writes_as_excel_told_it_does(code):
    told = dict(
        line.split("\t", 1)
        for line in Path(__file__)
        .with_name(f"international-{code}.tsv")
        .read_text(encoding="utf-8-sig")
        .splitlines()
    )
    setting = {int(index): value for index, value in told.items()}
    codes = formats.CODES[code]
    assert int(setting[COUNTRY]) == excel.COUNTRIES[code]
    assert formats.marks(code) == (setting[DECIMAL], setting[GROUP])
    assert formats.day_mark(code) == setting[DAY_MARK]
    assert {part: getattr(codes, part) for part in CODED} == {
        part: setting[index] for part, index in CODED.items()
    }
    assert codes.general == setting[GENERAL]
