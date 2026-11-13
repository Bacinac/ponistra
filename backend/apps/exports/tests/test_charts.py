import io
import zipfile

import pytest
from lxml import etree

from apps.collab import server
from apps.content import palette
from apps.content.blocks import Block
from apps.exports import charts
from apps.imports import xlsx as reader
from apps.imports.tests import workbooks
from apps.imports.tests.test_charts import sheets_of_charts
from apps.imports.tests.test_views import bring
from apps.imports.tests.test_xlsx import book, point

from .test_docx import made, parts_of, read
from .test_docx import saved as word
from .test_xlsx import saved as excel

pytestmark = pytest.mark.django_db

C = f"{{{charts.C}}}"
A = f"{{{charts.A}}}"
DATA = {
    "A1": "",
    "B1": "Prihod",
    "C1": "Rashod",
    "A2": "Sij",
    "B2": "1200",
    "C2": "300",
    "A3": "Velj",
    "B3": "=B2*2",
    "C3": "450",
}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(server, "announce", lambda room, news: None)


def sales(tmp_path) -> Block:
    def prepare(model):
        style = model.get_cell_style(0, 2, 2)
        for row in (2, 3):
            model.set_cell_style(0, row, 2, style | {"num_fmt": "#,##0.00"})

    path = book(tmp_path, {"Prodaja": DATA}, prepare)
    table = reader.read(path, "hr").tabs[0].blocks[0]
    table.attrs["name"] = "Prodaja"
    return table


def over(table: Block, start: str, end: str, **attrs) -> Block:
    found = {
        "kind": "column",
        "stacked": False,
        "by": "cols",
        "names": True,
        "labels": True,
        "title": None,
        "legend": True,
        **attrs,
    }
    range = {"table": table.id, "from": point(table, start), "to": point(table, end)}
    return Block("chart", attrs={"range": range, **found})


def placed(chart: Block, table: Block) -> dict:
    """A chart's attributes with its range by the places of its ends in its table."""
    rows = {id: y for y, id in enumerate(table.grid.rows)}
    cols = {id: x for x, id in enumerate(table.grid.cols)}
    range = chart.attrs["range"]
    ends = {end: (rows[range[end]["row"]], cols[range[end]["col"]]) for end in ("from", "to")}
    return {**chart.attrs, "range": ends}


def charted(tmp_path) -> tuple[Block, list[Block]]:
    table = sales(tmp_path)
    drawn = [
        over(table, "A1", "C3", title="Prvi kvartal", stacked=True),
        over(table, "A1", "C3", kind="bar", by="rows", legend=False),
        over(table, "B1", "C3", kind="line", labels=False),
        over(table, "A2", "B3", kind="pie", names=False),
        over(table, "A1", "C3", kind="doughnut"),
        over(table, "B1", "C3", kind="scatter"),
        over(table, "A1", "C3", kind="area", stacked=True, title="Trend"),
    ]
    return table, drawn


def test_a_tables_charts_go_to_excel_beside_it_and_come_back_as_they_were(api, tmp_path):
    table, drawn = charted(tmp_path)
    gone = Block("chart", attrs={**drawn[0].attrs, "range": {**drawn[0].attrs["range"]}})
    gone.attrs["range"]["table"] = "nowhere"
    document, _, _ = made(api, [table, *drawn, gone])
    path = tmp_path / "again.xlsx"
    path.write_bytes(excel(api, str(document.pk)))
    found = reader.read(path, "hr").tabs[0].blocks
    assert [block.type for block in found] == ["table", *["chart"] * len(drawn), "paragraph"]
    back = found[0]
    assert [placed(chart, back) for chart in found[1:-1]] == [
        placed(chart, table) for chart in drawn
    ]
    with zipfile.ZipFile(path) as archive:
        sheet = etree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        anchors = etree.fromstring(archive.read("xl/drawings/drawing1.xml"))
        first = etree.fromstring(archive.read("xl/charts/chart1.xml"))
    assert etree.QName(sheet[-1]).localname == "drawing"
    places = [
        (int(anchor.findtext(".//{*}from/{*}col")), int(anchor.findtext(".//{*}from/{*}row")))
        for anchor in anchors
    ]
    assert [col for col, _ in places] == [4] * len(drawn)
    assert [row for _, row in places] == [20 * number for number in range(len(drawn))]
    colours = [fill.get("val") for fill in first.iter(f"{A}srgbClr")]
    assert colours == palette.chart()[:2]
    assert [ref.text for ref in first.iter(f"{C}f")] == [
        "'Prodaja'!$B$1",
        "'Prodaja'!$A$2:$A$3",
        "'Prodaja'!$B$2:$B$3",
        "'Prodaja'!$C$1",
        "'Prodaja'!$A$2:$A$3",
        "'Prodaja'!$C$2:$C$3",
    ]
    values = first.find(f".//{C}val/{C}numRef/{C}numCache")
    assert values.findtext(f"{C}formatCode") == "#,##0.00"
    assert [pt.findtext(f"{C}v") for pt in values.iter(f"{C}pt")] == ["1200.0", "2400.0"]
    assert first.find(f".//{A}latin").get("typeface")


def test_each_tab_goes_to_excel_as_a_sheet_with_its_charts_and_comes_back_as_it_was(api, tmp_path):
    path = sheets_of_charts(tmp_path)
    node = bring(api, path.read_bytes(), title="Pregled")["id"]
    again = tmp_path / "again.xlsx"
    again.write_bytes(excel(api, node))

    def shown(path):
        tabs = reader.read(path, "hr").tabs
        (data,) = (block for block in tabs[0].blocks if block.type == "table")
        return [
            (
                tab.title,
                [
                    placed(block, data) if block.type == "chart" else block.type
                    for block in tab.blocks
                ],
            )
            for tab in tabs
        ]

    assert shown(again) == shown(path)
    with zipfile.ZipFile(again) as archive:
        listed = [part for part in archive.namelist() if part.startswith("xl/drawings/drawing")]
        anchors = etree.fromstring(archive.read("xl/drawings/drawing2.xml"))
        alone = etree.fromstring(archive.read("xl/charts/chart1.xml"))
    assert sorted(listed) == ["xl/drawings/drawing2.xml", "xl/drawings/drawing3.xml"]
    assert anchors.findtext(".//{*}from/{*}col") == "0"
    assert alone.findtext(f".//{C}val//{C}f") == "'Sheet1'!$B$2:$B$3"


def test_a_chart_goes_to_word_with_its_workbook_and_comes_back_over_a_table_of_its_own(
    api, tmp_path
):
    table, drawn = charted(tmp_path)
    gone = Block("chart", attrs={**drawn[0].attrs, "range": {**drawn[0].attrs["range"]}})
    gone.attrs["range"]["table"] = "nowhere"
    document, _, _ = made(api, [table, *drawn, gone])
    data = word(api, str(document.pk))
    found = read(tmp_path, data)
    blocks = found.tabs[0].blocks
    kinds = ["table", *["table", "chart"] * len(drawn)]
    assert [block.type for block in blocks][: len(kinds)] == kinds
    pairs = list(zip(blocks[1::2], blocks[2::2], strict=False))[: len(drawn)]
    assert [placed(chart, own) for own, chart in pairs] == [placed(chart, table) for chart in drawn]
    assert found.report["lost"] == {"charts": 1}
    parts = parts_of(data)
    assert "2.400,00" in parts["word/document.xml"].decode()
    embedded = [name for name in parts if name.startswith("word/embeddings/")]
    assert len(embedded) == len(drawn)
    workbook = tmp_path / "embedded.xlsx"
    workbook.write_bytes(parts[embedded[0]])
    model = workbooks.load(workbook)
    assert model.get_cell_formula(0, 3, 2) == "=B2*2"
    space = etree.fromstring(parts["word/charts/chart1.xml"])
    assert space.find(f"{C}externalData") is not None
    missing = etree.fromstring(parts[f"word/charts/chart{len(drawn) + 1}.xml"])
    assert missing.find(f".//{C}ser") is None
    assert missing.find(f"{C}externalData") is None


def test_a_chart_without_tables_goes_to_word_empty(api, tmp_path):
    chart = Block(
        "chart",
        attrs={"range": {"table": "x", "from": {"row": "r", "col": "c"}}, "kind": "pie"},
    )
    document, _, _ = made(api, [chart])
    parts = parts_of(word(api, str(document.pk)))
    space = etree.fromstring(parts["word/charts/chart1.xml"])
    assert space.find(f".//{C}pieChart") is not None
    assert space.find(f".//{C}ser") is None
    with zipfile.ZipFile(io.BytesIO(word(api, str(document.pk)))) as archive:
        assert not [name for name in archive.namelist() if "embeddings" in name]
