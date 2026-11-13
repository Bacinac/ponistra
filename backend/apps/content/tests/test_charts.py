import pytest

from apps.content import blocks, calculation, charts, grids
from apps.content.blocks import Block, Grid
from apps.content.grids import Col, Laid, Row, apply
from apps.documents.models import Node, Tab

from .test_compute import cells, change, computing, live, until

ROWS = ["r1", "r2", "r3"]
COLS = ["a", "b", "c"]


def chart(**given) -> charts.Chart:
    attrs = {
        "table": "t",
        "top": "r1",
        "left": "a",
        "bottom": ROWS[-1],
        "right": COLS[-1],
        "by": "cols",
        "scatter": False,
        "names": None,
        "labels": None,
    }
    return charts.Chart(**{**attrs, **given})


def drawn(texts: dict[str, str], shown: charts.Chart, formats=None, formulas=None) -> dict:
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Grafikon", locale="hr")
    tab = Tab.objects.create(document=document, position=0)
    laid = Laid("t", tab.pk, "Podaci", [Col(id) for id in COLS], [Row(id) for id in ROWS])
    for part, given in (("text", texts), ("format", formats or {}), ("formula", formulas or {})):
        for key, value in given.items():
            row, _, col = key.partition(":")
            if part == "formula":
                value = grids.formula_at(value, row, col)
            laid.own(row).cells.setdefault(col, {})[part] = value
    grids.store(document, apply(None, grids.made(laid)))
    calculation.calculate(document, {"t"}, {})
    return charts.read(document, shown, {"t"}, {})


def grid(*lines: list[str]) -> dict[str, str]:
    return {
        f"{ROWS[y]}:{COLS[x]}": text
        for y, line in enumerate(lines)
        for x, text in enumerate(line)
        if text
    }


def series(name, values, texts) -> dict:
    return {"name": name, "values": values, "texts": texts}


@pytest.mark.django_db
def test_the_first_row_names_the_series_and_the_first_column_gives_the_categories():
    texts = grid(["", "Prihod", "Rashod"], ["Sij", "1.200,5", "800"], ["Velj", "", "700"])
    formulas = {"r3:b": [{"from": {"row": "r2", "col": "b"}}, "*2"]}
    formats = {"r2:b": "#,##0.00", "r3:b": "#,##0.00"}
    assert drawn(texts, chart(), formats, formulas) == {
        "labels": ["Sij", "Velj"],
        "series": [
            series("Prihod", [1200.5, 2401.0], ["1.200,50", "2.401,00"]),
            series("Rashod", [800.0, 700.0], ["800", "700"]),
        ],
    }


@pytest.mark.django_db
def test_numbers_alone_are_series_without_names_or_categories():
    texts = grid(["1", "2", "3"], ["4", "x", ""], ["7", "8", "9"])
    found = drawn(texts, chart())
    assert found["labels"] is None
    assert [each["name"] for each in found["series"]] == [None, None, None]
    assert found["series"][1] == series(None, [2.0, None, 8.0], ["2", "x", "8"])
    assert found["series"][2]["values"] == [3.0, None, 9.0]


@pytest.mark.django_db
def test_dates_under_the_first_cell_are_categories_and_text_after_it_names():
    texts = grid(["Dan", "Kom", "Kg"], ["15.12.2025.", "3", "1,5"], ["16.12.2025.", "4", "2"])
    found = drawn(texts, chart())
    assert found["labels"] == ["15.12.2025.", "16.12.2025."]
    assert [each["name"] for each in found["series"]] == ["Kom", "Kg"]


@pytest.mark.django_db
def test_series_along_the_rows_read_the_range_turned():
    texts = grid(["", "Sij", "Velj"], ["Prihod", "1", "2"], ["Rashod", "3", "4"])
    assert drawn(texts, chart(by="rows")) == {
        "labels": ["Sij", "Velj"],
        "series": [
            series("Prihod", [1.0, 2.0], ["1", "2"]),
            series("Rashod", [3.0, 4.0], ["3", "4"]),
        ],
    }


@pytest.mark.django_db
def test_a_scatter_takes_its_first_column_as_x_values():
    texts = grid(["1", "10", "5"], ["2", "20", "6"], ["4", "40", "7"])
    found = drawn(texts, chart(scatter=True))
    assert found["x"] == [1.0, 2.0, 4.0]
    assert found["labels"] == ["1", "2", "4"]
    assert [each["values"] for each in found["series"]] == [[10.0, 20.0, 40.0], [5.0, 6.0, 7.0]]
    texts = grid(["a", "10", "5"], ["b", "20", "6"], ["c", "40", "7"])
    found = drawn(texts, chart(scatter=True))
    assert "x" not in found
    assert found["labels"] == ["a", "b", "c"]


@pytest.mark.django_db
def test_names_and_categories_set_on_the_chart_overrule_what_the_cells_hold():
    texts = grid(["2020", "5", "6"], ["2021", "7", "8"], ["2022", "9", "1"])
    found = drawn(texts, chart(labels=True))
    assert found["labels"] == ["2020", "2021", "2022"]
    assert len(found["series"]) == 2
    texts = grid(["", "A", "B"], ["x", "1", "2"], ["y", "3", "4"])
    found = drawn(texts, chart(names=False, labels=False))
    assert found["labels"] is None
    assert found["series"][0]["texts"] == ["", "x", "y"]


@pytest.mark.django_db
def test_a_range_whose_lines_are_gone_shows_nothing():
    assert drawn({}, chart(bottom="gone")) == charts.MISSING


def test_a_number_format_writes_a_date_when_it_has_a_date_part_outside_its_literals():
    assert charts.dated("dd.mm.yyyy.")
    assert charts.dated("[h]:mm")
    assert not charts.dated('#,##0.00 "kom/dan"')
    assert not charts.dated("[Red]0.0\\h")
    assert not charts.dated("General")


def test_a_charts_attributes_give_where_its_values_are():
    range = {"table": "t", "from": {"row": "r1", "col": "a"}, "to": {"row": "r3", "col": "c"}}
    found = charts.chart_of({"range": range, "kind": "scatter", "by": "rows", "names": True})
    assert found == chart(by="rows", scatter=True, names=True)
    assert charts.chart_of({"range": {"table": "t", "from": {"row": "r1"}}}) is None
    assert charts.chart_of({}) is None


def chart_block(id: str, table: str = "t", bottom: str = "r3") -> Block:
    range = {"table": table, "from": {"row": "r1", "col": "b"}, "to": {"row": bottom, "col": "b"}}
    return Block("chart", id, {"range": range, "kind": "column"})


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_live_tab_writes_what_its_charts_show_and_takes_it_away_with_them():
    table = Block("table", "t", grid=Grid(ROWS, ["a", "b"]))
    doc, book, tab = await live(table, chart_block("c1"), chart_block("c2", table="elsewhere"))
    shown = charts.charts_of(doc)
    body = blocks.body_of(doc)

    def values(id: str):
        found = shown.to_py() or {}
        return found.get(id, {}).get("series", [{}])[0].get("values")

    async with computing(book, tab, doc):
        await change(doc, book, tab, cells("t", r2b={"value": 5}))
        await until(lambda: values("c1") == [None, 5.0, None])
        assert shown["c2"] == charts.MISSING
        await change(doc, book, tab, cells("t", r3b={"value": 6}))
        await until(lambda: values("c1") == [None, 5.0, 6.0])
        body.children[1].attributes["kind"] = "line"
        range = {"table": "t", "from": {"row": "r2", "col": "b"}, "to": {"row": "r3", "col": "b"}}
        body.children[1].attributes["range"] = range
        await until(lambda: values("c1") == [5.0, 6.0])
        del body.children[2]
        await until(lambda: "c2" not in shown)
        await change(doc, book, tab, {"op": "delete", "from": "t"})
        await until(lambda: shown.get("c1") == charts.MISSING)
