import pytest

from apps.engine.parse import (
    SEMICOLONS,
    Array,
    Binary,
    Call,
    End,
    Error,
    Group,
    Held,
    Logical,
    Missing,
    Name,
    Number,
    Point,
    Postfix,
    Prefix,
    Ref,
    Structured,
    Text,
    Unreadable,
    column_name,
    column_number,
    parse,
    quote_sheet,
    written,
)
from apps.engine.tests.cases import CASES, READING


def cases():
    return [
        formula for title, formulas in CASES.items() if title not in READING for formula in formulas
    ]


@pytest.mark.parametrize("formula", cases())
def test_every_case_reads_and_writes_back_to_the_same_tree(formula):
    tree = parse(formula)
    assert parse(written(tree)) == tree


def test_precedence_follows_excel():
    assert parse("-2^2") == Binary("^", Prefix("-", Number(2)), Number(2))
    assert parse("2^3^2") == Binary("^", Binary("^", Number(2), Number(3)), Number(2))
    assert parse("1+2*3") == Binary("+", Number(1), Binary("*", Number(2), Number(3)))
    assert parse("50%*200") == Binary("*", Postfix("%", Number(50)), Number(200))
    assert parse('1&2="12"') == Binary("=", Binary("&", Number(1), Number(2)), Text("12"))
    assert parse("-A1:B2") == Prefix("-", Ref(None, End(1, 1), End(2, 2)))


def test_references():
    assert parse("Data!A1:A3") == Ref("Data", End(1, 1), End(3, 1))
    assert parse("'My Sheet'!$A$1") == Ref("My Sheet", End(1, 1, True, True))
    assert parse("'It''s'!B2") == Ref("It's", End(2, 2))
    assert parse("A:A") == Ref(None, End(None, 1), End(None, 1))
    assert parse("$1:3") == Ref(None, End(1, None, True), End(3, None))
    assert parse("B2:A1") == Ref(None, End(1, 1), End(2, 2))
    assert parse("$B2:A$1") == Ref(None, End(1, 1, True, False), End(2, 2, False, True))
    assert parse("[1]Sheet1!A1") == Ref("Sheet1", End(1, 1), None, 1)
    assert parse("'[2]My Sheet'!A1") == Ref("My Sheet", End(1, 1), None, 2)
    assert parse("Data!#REF!") == Error("#REF!")
    assert parse("XFD1048576") == Ref(None, End(1_048_576, 16_384))
    assert parse("XFE1") == Name("XFE1")
    assert parse("LOG10(100)") == Call("LOG10", (Number(100),))
    assert parse("Sales[Price]") == Structured("Sales", "[Price]")
    assert parse("Sales[[#This Row],[Price]]") == Structured("Sales", "[[#This Row],[Price]]")


def test_reference_operators():
    a1, a3 = Ref(None, End(1, 1)), Ref(None, End(3, 1))
    assert parse("SUM((A1,A3))") == Call("SUM", (Group(Binary(",", a1, a3)),))
    assert parse("SUM(A1 A3)") == Call("SUM", (Binary(" ", a1, a3),))
    assert parse("A1:INDEX(A:A,3)") == Binary(
        ":", a1, Call("INDEX", (Ref(None, End(None, 1), End(None, 1)), Number(3)))
    )
    assert parse(" A1 + 1 ") == Binary("+", a1, Number(1))


def test_calls_and_arguments():
    assert parse("IF(TRUE,,2)") == Call("IF", (Logical(True), Missing(), Number(2)))
    assert parse("NOW()") == Call("NOW", ())
    assert parse("_xlfn.XLOOKUP(1,A1:A2,B1:B2)").name == "XLOOKUP"
    assert parse("_xlfn._xlws.SORT(A1:A3)").name == "SORT"
    assert written(parse("xlookup(1,A1:A2,B1:B2)")) == "_xlfn.XLOOKUP(1,A1:A2,B1:B2)"
    assert parse("f(1,)") == Call("F", (Number(1), Missing()))


def test_constants():
    assert parse('"say ""hi"""') == Text('say "hi"')
    assert parse('{1,-2;"a",TRUE}') == Array(((Number(1), Number(-2)), (Text("a"), Logical(True))))
    assert parse("#N/A") == Error("#N/A")
    assert parse("9.99999999999999E+307") == Number(9.99999999999999e307)
    assert parse("123456789012345678") == Number(1.23456789012345e17)
    assert written(parse("-1E-06+1.2345E-05")) == "-0.000001+0.000012345"
    assert parse(".5") == Number(0.5)


def test_the_form_a_decimal_comma_types():
    assert parse('IF(A1>1,5;"a";"b")', SEMICOLONS) == Call(
        "IF", (Binary(">", Ref(None, End(1, 1)), Number(1.5)), Text("a"), Text("b"))
    )
    assert parse("{1,5;2/3;4}", SEMICOLONS) == Array(
        ((Number(1.5), Number(2)), (Number(3), Number(4)))
    )


def test_the_pieces_a_table_keeps():
    piece = {"from": {"row": "r1", "col": "@"}, "to": {"row": "r9", "col": "@", "absRow": True}}
    other = {"table": "t2", "from": {"col": "c1"}, "to": {"col": "c1"}}
    assert parse(["SUM(", piece, ")+", other]) == Binary(
        "+",
        Call("SUM", (Held(None, Point("r1", "@"), Point("r9", "@", True)),)),
        Held("t2", Point(None, "c1"), Point(None, "c1")),
    )
    assert parse(["1+", {"from": {}}]) == Binary("+", Number(1), Error("#REF!"))
    assert parse(["1+", "lost"]) == Binary("+", Number(1), Name("lost"))


@pytest.mark.parametrize(
    "formula", ["", "SUM(", '"abc', "1+", "{1,2;3}", "#WHAT", "1 )", "A1!", "1E+308"]
)
def test_what_is_not_a_formula(formula):
    with pytest.raises(Unreadable):
        parse(formula)


def test_names_of_columns_and_sheets():
    assert [column_name(n) for n in (1, 26, 27, 702, 703, 16_384)] == [
        "A",
        "Z",
        "AA",
        "ZZ",
        "AAA",
        "XFD",
    ]
    assert column_number("xfd") == 16_384
    assert [quote_sheet(n) for n in ("Data", "My Sheet", "A1", "R1C1", "2026", "It's")] == [
        "Data",
        "'My Sheet'",
        "'A1'",
        "'R1C1'",
        "'2026'",
        "'It''s'",
    ]
