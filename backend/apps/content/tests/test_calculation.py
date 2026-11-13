from datetime import date

import pytest
from django.utils import timezone

from apps.content import calculation, grids
from apps.content.grids import Col, Laid, Row, apply
from apps.content.models import Grid, GridRow
from apps.content.models import Name as Defined
from apps.documents.models import Node, Tab


def formula(row: str, col: str, *pieces) -> dict:
    return {"formula": grids.formula_at(list(pieces), row, col)}


def at(row: str, col: str, **point) -> dict:
    return {"from": {"row": row, "col": col, **point}}


def stored(document: Node, tab: Tab, laid: Laid) -> None:
    laid.tab = tab.pk
    grids.store(document, apply(None, grids.made(laid)))


def kept(table: str) -> tuple[dict, dict]:
    rows = GridRow.objects.filter(grid__table=table).values_list("row", "values", "shown")
    return {row: values for row, values, _ in rows}, {row: shown for row, _, shown in rows}


def typed_in(table: str, row: str, col: str, text: str | None) -> None:
    line = GridRow.objects.get(grid__table=table, row=row)
    if text is None:
        del line.cells[col]
    else:
        line.cells[col] = {"text": text}
    line.save()


def settled(document: Node) -> None:
    """Holds what a calculation of what changed left to what calculating every table gives."""
    left = kept("t"), kept("u")
    Grid.objects.update(calculated="")
    calculation.calculate(document, {"t", "u"}, {})
    assert (kept("t"), kept("u")) == left


def held() -> dict[str, set[str]]:
    """Every row of every table, as a reader holding them all."""
    found: dict[str, set[str]] = {}
    for table, row in GridRow.objects.values_list("grid__table", "row"):
        found.setdefault(table, set()).add(row)
    return found


@pytest.fixture
def known() -> calculation.Known:
    return calculation.Known()


def today() -> float:
    return float((timezone.localdate() - date(1899, 12, 30)).days)


@pytest.fixture
def document():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik", locale="hr")
    tab = Tab.objects.create(document=document, position=0)
    prices = Laid(
        "t",
        name="Cijene",
        cols=[Col(id) for id in "abcdef"],
        rows=[
            Row(f"r{y}", cells={"a": {"text": text}})
            for y, text in enumerate(["1,5", "2", "x", "'7", "TRUE"])
        ],
    )
    for row in prices.rows:
        row.cells["b"] = formula(row.id, "b", "2*", at(row.id, "a"))
    prices.own("r1").cells["b"]["format"] = "0.00"
    prices.own("r0").cells["c"] = formula("r0", "c", at("r0", "b"))
    prices.own("r1").cells["c"] = formula("r1", "c", at("r0", "c"), "+", at("r1", "b"))
    for row in ("r0", "r1"):
        prices.own(row).cells["d"] = formula(
            row, "d", at("r0", "a", absRow=True, absCol=True), "*", at(row, "b")
        )
    prices.own("r4").cells["d"] = formula(
        "r4", "d", "SUM(", {**at("r0", "b", absRow=True), "to": {"row": "r1", "col": "b"}}, ")"
    )
    prices.own("r0").cells["e"] = formula(
        "r0", "e", at("r0", "a"), "*", {"table": "u", **at("q0", "k")}
    )
    prices.own("r0").cells["f"] = formula("r0", "f", "Stopa*2")
    prices.own("r2").cells["e"] = {"to": "r3:f"}
    prices.own("r3").cells["e"] = {"text": "skriveno"}
    prices.own("r3").cells["f"] = formula("r3", "f", "1+1")
    prices.own("r4").cells["f"] = formula("r4", "f", "ROW()")
    stored(document, tab, prices)
    rates = Laid(
        "u",
        name="Tečaj",
        cols=[Col("k")],
        rows=[
            Row("q0", cells={"k": {"text": "7,5345"}}),
            Row("q1", cells={"k": formula("q1", "k", "TODAY()")}),
        ],
    )
    stored(document, tab, rates)
    Defined.objects.create(
        document=document,
        key="n1",
        name="Stopa",
        pieces=[{"table": "u", **at("q0", "k", absRow=True, absCol=True)}],
    )
    return document


@pytest.mark.django_db
def test_a_table_calculated_whole_keeps_each_cells_value_and_what_it_shows(document):
    calculation.calculate(document, {"t", "u"}, {})

    values, shown = kept("t")
    assert {row: held.get("a") for row, held in values.items()} == {
        "r0": 1.5,
        "r1": 2.0,
        "r2": "x",
        "r3": "7",
        "r4": True,
    }
    assert {row: held["b"] for row, held in values.items()} == {
        "r0": 3.0,
        "r1": 4.0,
        "r2": {"error": "#VALUE!"},
        "r3": 14.0,
        "r4": 2.0,
    }
    assert [values[row]["c"] for row in ("r0", "r1")] == [3.0, 7.0]
    assert [values[row]["d"] for row in ("r0", "r1", "r4")] == [4.5, 6.0, 7.0]
    assert values["r0"]["e"] == pytest.approx(11.30175)
    assert values["r0"]["f"] == pytest.approx(15.069)
    assert "e" not in values["r3"] and "f" not in values["r3"]
    assert shown["r0"] == {"b": "3", "c": "3", "d": "4,5", "e": "11,30175", "f": "15,069"}
    assert shown["r1"]["b"] == "4,00"
    assert shown["r2"] == {"b": "#VALUE!"}
    assert shown["r3"] == {"a": "7", "b": "14"}
    assert kept("u") == (
        {"q0": {"k": 7.5345}, "q1": {"k": today()}},
        {"q0": {}, "q1": {"k": str(int(today()))}},
    )
    assert set(Grid.objects.values_list("calculated", flat=True)) == {"2:hr"}


@pytest.mark.django_db
def test_a_cell_with_a_node_of_its_own_holds_the_value_of_its_text(document):
    calculation.calculate(document, {"t", "u"}, {"t": {"r2:a": "4"}})

    values, shown = kept("t")
    assert values["r2"]["a"] == 4.0 and values["r2"]["b"] == 8.0
    assert shown["r2"] == {"b": "8"}


def test_typed_text_holds_what_excel_reads_it_as_in_the_format_excel_gives_it():
    language = calculation.Language("hr", 2026, "cp1250")
    texts = ("1.234,5", "15%", "'12", "false", "#N/A", "1.5.2026", "Rijeka")
    assert [calculation.typed(text, language) for text in texts] == [
        1234.5,
        0.15,
        "12",
        False,
        calculation.Error("#N/A"),
        46143.0,
        "Rijeka",
    ]
    assert [calculation.implied(text, language) for text in texts] == [
        "#,##0.00",
        "0%",
        "",
        "",
        "",
        "mm-dd-yy",
        "",
    ]


def test_a_cell_shows_the_built_in_dates_as_the_language_writes_its_short_date():
    moment = 46054 + 10.5 / 24
    shown = [
        (calculation.shown(moment, code, "hr"), calculation.shown(moment, code, "en"))
        for code in ("mm-dd-yy", "m/d/yy h:mm", "d/m/yy", "d\\/m")
    ]
    assert shown == [
        ("1.2.2026", "2/1/2026"),
        ("1.2.2026 10:30", "2/1/2026 10:30"),
        ("1.2.26", "1/2/26"),
        ("1/2", "1/2"),
    ]


@pytest.mark.django_db
def test_a_subtotal_leaving_out_hidden_rows_is_calculated_again_once_a_row_is_hidden():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Zbroj", locale="hr")
    tab = Tab.objects.create(document=document, position=0)
    laid = Laid(
        "t",
        cols=[Col("a")],
        rows=[Row(f"r{y}", cells={"a": {"text": text}}) for y, text in enumerate("124")],
    )
    span = {**at("r0", "a"), "to": {"row": "r2", "col": "a"}}
    laid.rows.append(Row("r3", cells={"a": formula("r3", "a", "SUBTOTAL(109,", span, ")")}))
    laid.rows.append(Row("r4", cells={"a": formula("r4", "a", "SUBTOTAL(9,", span, ")")}))
    stored(document, tab, laid)
    calculation.calculate(document, {"t"}, {})
    assert kept("t")[0]["r3"]["a"] == 7.0
    GridRow.objects.filter(row="r1").update(hidden=True)

    calculation.calculate(document, {"t"}, {}, {"t": {("r1", "a")}})

    values, _ = kept("t")
    assert (values["r3"]["a"], values["r4"]["a"]) == (5.0, 7.0)


@pytest.mark.django_db
def test_a_changed_cell_has_what_reads_it_calculated_and_nothing_else(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    typed_in("t", "r0", "a", "3")

    found = calculation.calculate(
        document, {"t", "u"}, {}, {"t": {("r0", "a")}}, told=held(), known=known
    )

    values, shown = kept("t")
    assert [values[row]["b"] for row in ("r0", "r1")] == [6.0, 4.0]
    assert [values[row]["c"] for row in ("r0", "r1")] == [6.0, 10.0]
    assert [values[row]["d"] for row in ("r0", "r1", "r4")] == [18.0, 12.0, 10.0]
    assert values["r0"]["e"] == pytest.approx(22.6035)
    assert shown["r0"]["d"] == "18"
    assert found == {"t": {row: (values[row], shown[row]) for row in ("r0", "r1", "r4")}}
    assert values["r0"]["a"] == 3.0 and "a" not in shown["r0"]
    settled(document)


@pytest.mark.django_db
def test_a_cell_of_another_table_has_the_cells_reading_it_calculated(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    typed_in("u", "q0", "k", "2")

    found = calculation.calculate(
        document, {"t", "u"}, {}, {"u": {("q0", "k")}}, told=held(), known=known
    )

    values, shown = kept("t")
    assert found == {"t": {"r0": (values["r0"], shown["r0"])}, "u": {"q0": ({"k": 2.0}, {})}}
    assert (values["r0"]["e"], shown["r0"]["e"]) == (3.0, "3")
    assert (values["r0"]["f"], shown["r0"]["f"]) == (4.0, "4")
    settled(document)


@pytest.mark.django_db
def test_a_cleared_cell_holds_nothing_and_what_reads_it_reads_it_empty(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    typed_in("t", "r1", "a", None)

    found = calculation.calculate(
        document, {"t", "u"}, {}, {"t": {("r1", "a")}}, told=held(), known=known
    )

    values, shown = kept("t")
    assert "a" not in values["r1"]
    assert values["r1"]["b"] == 0.0 and shown["r1"]["b"] == "0,00"
    assert found == {"t": {row: (values[row], shown[row]) for row in ("r1", "r4")}}
    assert (values["r4"]["d"], shown["r4"]["d"]) == (3.0, "3")
    settled(document)


@pytest.mark.django_db
def test_a_formula_giving_another_value_each_time_is_calculated_with_every_change(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    GridRow.objects.filter(grid__table="u", row="q1").update(values={"k": 1})

    found = calculation.calculate(
        document, {"t", "u"}, {}, {"t": {("r0", "a")}}, told=held(), known=known
    )

    assert found == {"u": {"q1": ({"k": today()}, {"k": str(int(today()))})}}
    assert kept("u")[0]["q1"] == {"k": today()}


@pytest.mark.django_db
def test_a_table_calculated_in_another_locale_is_calculated_whole(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    Grid.objects.filter(table="t").update(calculated=calculation.calculated("en"))
    GridRow.objects.filter(grid__table="t", row="r3").update(values={}, shown={})

    found = calculation.calculate(
        document, {"t", "u"}, {}, {"u": {("q0", "k")}}, told=held(), known=known
    )

    assert found == {"t": {"r3": ({"a": "7", "b": 14.0}, {"a": "7", "b": "14"})}}
    assert set(Grid.objects.values_list("calculated", flat=True)) == {"2:hr"}


@pytest.mark.django_db
def test_nothing_changed_calculates_nothing(document):
    calculation.calculate(document, {"t", "u"}, {})
    GridRow.objects.filter(grid__table="t", row="r0").update(values={})

    assert calculation.calculate(document, {"t", "u"}, {}, {}) == {}
    assert kept("t")[0]["r0"] == {}


@pytest.mark.django_db
def test_a_row_put_above_has_where_each_row_stands_calculated_again(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    grid = Grid.objects.get(table="t")
    top = GridRow.objects.filter(grid=grid).order_by("position").first().position
    GridRow.objects.create(grid=grid, row="r9", position=top - grids.STEP)

    found = calculation.calculate(
        document, {"t", "u"}, {}, {}, moved={"t"}, told=held(), known=known
    )

    values, shown = kept("t")
    assert found == {"t": {"r4": (values["r4"], shown["r4"])}}
    assert (values["r4"]["f"], shown["r4"]["f"]) == (6.0, "6")
    settled(document)


@pytest.mark.django_db
def test_a_table_gone_from_the_text_is_read_as_a_reference_to_nothing(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)

    found = calculation.calculate(document, {"t"}, {}, {"u": None}, told=held(), known=known)

    values, _ = kept("t")
    assert found == {"t": {"r0": (values["r0"], kept("t")[1]["r0"])}}
    assert values["r0"]["e"] == values["r0"]["f"] == {"error": "#REF!"}

    found = calculation.calculate(document, {"t", "u"}, {}, {"u": None}, told=held(), known=known)

    assert kept("t")[0]["r0"]["e"] == pytest.approx(11.30175)
    assert set(found["t"]) == {"r0"}
    settled(document)


@pytest.mark.django_db
def test_a_changed_name_has_the_formulas_reading_it_calculated(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    Defined.objects.filter(name="Stopa").update(pieces=[at("r0", "a", absRow=True, absCol=True)])

    found = calculation.calculate(
        document, {"t", "u"}, {}, {}, named={"STOPA"}, told=held(), known=known
    )

    values, shown = kept("t")
    assert found == {"t": {"r0": (values["r0"], shown["r0"])}}
    assert (values["r0"]["f"], shown["r0"]["f"]) == (3.0, "3")
    settled(document)


@pytest.mark.django_db
def test_a_calculation_gives_of_the_rows_changed_only_those_told(document):
    calculation.calculate(document, {"t", "u"}, {})
    typed_in("t", "r0", "a", "3")
    changed = {"t": {("r0", "a")}}

    told = calculation.calculate(document, {"t", "u"}, {}, changed, told={"t": {"r1", "r2"}})
    typed_in("t", "r0", "a", "4")
    none = calculation.calculate(document, {"t", "u"}, {}, changed, told={"u": {"q0"}})
    typed_in("t", "r0", "a", "5")
    untold = calculation.calculate(document, {"t", "u"}, {}, changed)

    assert set(told) == {"t"} and set(told["t"]) == {"r1"}
    assert told["t"]["r1"][0]["c"] == 10.0
    assert none == {"t": {}}
    assert untold == {}
    assert kept("t")[0]["r0"]["b"] == 10.0


@pytest.mark.django_db
def test_formulas_known_are_not_read_again_while_what_they_read_stands(
    document, known, monkeypatch
):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    read = []
    parse = calculation.parse
    monkeypatch.setattr(calculation, "parse", lambda pieces: read.append(pieces) or parse(pieces))
    typed_in("t", "r0", "a", "3")

    calculation.calculate(document, {"t", "u"}, {}, {"t": {("r0", "a")}}, known=known)

    assert read == []
    assert kept("t")[0]["r0"]["b"] == 6.0
    grid = Grid.objects.get(table="t")
    top = GridRow.objects.filter(grid=grid).order_by("position").first().position
    GridRow.objects.create(grid=grid, row="r9", position=top - grids.STEP)

    calculation.calculate(document, {"t", "u"}, {}, {}, moved={"t"}, known=known)

    assert len(read) == 2
    assert kept("t")[0]["r4"]["f"] == 6.0
    settled(document)


def test_a_value_is_written_as_the_text_that_typed_holds_it():
    language = calculation.Language("hr", 2026, "cp1250")
    assert [
        calculation.written(value, language)
        for value in (
            1234.5,
            3.0,
            1e-7,
            1e20,
            True,
            calculation.Error("#N/A"),
            "12",
            "1.5.2026",
            "Rijeka",
        )
    ] == [
        "1234,5",
        "3",
        "0,0000001",
        "100000000000000000000",
        "TRUE",
        "#N/A",
        "'12",
        "'1.5.2026",
        "Rijeka",
    ]


@pytest.mark.django_db
def test_a_row_taken_out_leaves_what_names_it_by_id_a_reference_to_nothing(document, known):
    calculation.calculate(document, {"t", "u"}, {}, known=known)
    GridRow.objects.filter(grid__table="t", row="r0").delete()

    found = calculation.calculate(
        document,
        {"t", "u"},
        {},
        {"t": {("r1", col) for col in "abcdef"}},
        moved={"t"},
        out={("t", "r0")},
        told=held(),
        known=known,
    )

    values, shown = kept("t")
    assert found == {"t": {row: (values[row], shown[row]) for row in ("r1", "r4")}}
    assert values["r1"]["d"] == values["r4"]["d"] == {"error": "#REF!"}
    assert values["r4"]["f"] == 4.0
    settled(document)


def squares(document: Node) -> None:
    """A table of forty rows: the number, its square by a formula of its own in each row, a
    running total of the squares, their sum and each square read through INDIRECT."""
    tab = Tab.objects.create(document=document, position=1)
    rows = [Row(f"v{y}", cells={"a": {"text": str(y)}}) for y in range(1, 41)]
    for y, row in enumerate(rows, 1):
        row.cells["b"] = formula(row.id, "b", at(row.id, "a"), f"*{y}")
        above = [at(rows[y - 2].id, "c"), "+"] if y > 1 else []
        row.cells["c"] = formula(row.id, "c", *above, at(row.id, "b"))
        row.cells["e"] = formula(row.id, "e", 'INDIRECT("B"&ROW())')
    every = {**at("v1", "b", absRow=True), "to": {"row": "v40", "col": "b", "absRow": True}}
    rows[0].cells["d"] = formula("v1", "d", "SUM(", every, ")")
    stored(document, tab, Laid("v", cols=[Col(id) for id in "abcde"], rows=rows))


@pytest.mark.django_db
def test_a_calculation_holding_little_at_a_time_gives_what_holding_everything_does(
    document, monkeypatch
):
    squares(document)
    calculation.calculate(document, {"t", "u", "v"}, {})
    values, shown = kept("v")
    assert [values[f"v{y}"]["b"] for y in (1, 2, 40)] == [1.0, 4.0, 1600.0]
    assert values["v40"]["c"] == values["v1"]["d"] == 22140.0
    assert all(values[f"v{y}"]["e"] == y * y for y in range(1, 41))
    assert shown["v40"]["c"] == "22140"
    whole = kept("t"), kept("u"), (values, shown)
    for name, small in (("CHUNK", 3), ("HELD", 2), ("PAGES", 1), ("SHORT", 1)):
        monkeypatch.setattr(calculation, name, small)
    monkeypatch.setattr(calculation, "PAGE", 4)
    Grid.objects.update(calculated="")
    GridRow.objects.update(values={}, shown={})

    calculation.calculate(document, {"t", "u", "v"}, {})

    assert (kept("t"), kept("u"), kept("v")) == whole


@pytest.mark.django_db
def test_a_change_read_by_every_run_of_a_column_reaches_each_of_them(document, monkeypatch):
    monkeypatch.setattr(calculation, "SHORT", 2)
    squares(document)
    calculation.calculate(document, {"t", "u", "v"}, {})
    typed_in("v", "v1", "a", "3")

    calculation.calculate(document, {"t", "u", "v"}, {}, {"v": {("v1", "a")}})

    values, _ = kept("v")
    assert (values["v1"]["b"], values["v1"]["e"]) == (3.0, 3.0)
    assert values["v40"]["c"] == values["v1"]["d"] == 22142.0
