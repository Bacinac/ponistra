from apps.engine.functions import FORMS
from apps.engine.parse import parse, written
from apps.engine.registry import FUNCTIONS


def test_a_function_has_its_arguments_written_exactly_when_it_has_a_form():
    assert [name for name in FORMS if FUNCTIONS[name].args is None] == []
    assert [name for name, each in FUNCTIONS.items() if each.args and name not in FORMS] == []


def test_a_newer_function_is_written_under_the_prefix_xlsx_stores_it_with():
    assert written(parse("FILTER(A1:A3,B1:B3)")) == "_xlfn._xlws.FILTER(A1:A3,B1:B3)"
    assert written(parse("_xlfn.LET(_xlpm.x,1,_xlpm.x)")).startswith("_xlfn.LET(")
    assert written(parse("WORKDAY.INTL(A1,1)")) == "WORKDAY.INTL(A1,1)"
    assert len(FUNCTIONS) > 500
