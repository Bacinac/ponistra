from pathlib import Path

from lxml import etree

from apps.content import formulas
from apps.imports import charts, docx, xlsx
from apps.imports.charts import Area, Series
from apps.imports.tests import workbooks

from .test_xlsx import book, point, tables
from .word_files import word_file

SPACE = (
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)
RELATIONSHIPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
LISTED = "http://schemas.openxmlformats.org/package/2006/relationships"
AXES = '<c:catAx><c:axId val="1"/></c:catAx><c:valAx><c:axId val="2"/></c:valAx>'


def cache(tag: str, points: list, code: str | None = None) -> str:
    format = f"<c:formatCode>{code}</c:formatCode>" if code else ""
    shown = "".join(
        f'<c:pt idx="{index}"><c:v>{each}</c:v></c:pt>'
        for index, each in enumerate(points)
        if each is not None
    )
    return f'<c:{tag}>{format}<c:ptCount val="{len(points)}"/>{shown}</c:{tag}>'


def ser(
    order: int,
    name: str | None,
    labels: str | None,
    values: str,
    shown: tuple = ("", [], []),
    code: str | None = None,
    x: bool = False,
) -> str:
    title, categories, numbers = shown
    tx = (
        f"<c:tx><c:strRef><c:f>{name}</c:f>{cache('strCache', [title])}</c:strRef></c:tx>"
        if name
        else ""
    )
    cat = (
        f"<c:{'xVal' if x else 'cat'}><c:strRef><c:f>{labels}</c:f>"
        f"{cache('strCache', categories)}</c:strRef></c:{'xVal' if x else 'cat'}>"
        if labels
        else ""
    )
    val = (
        f"<c:{'yVal' if x else 'val'}><c:numRef><c:f>{values}</c:f>"
        f"{cache('numCache', numbers, code)}</c:numRef></c:{'yVal' if x else 'val'}>"
    )
    return f'<c:ser><c:idx val="{order}"/><c:order val="{order}"/>{tx}{cat}{val}</c:ser>'


def space(groups: str, title: str | None = None, legend: bool = True, axes: str = AXES) -> str:
    heading = (
        f"<c:title><c:tx><c:rich><a:p><a:r><a:t>{title}</a:t></a:r></a:p></c:rich></c:tx></c:title>"
        if title
        else ""
    )
    shown = '<c:legend><c:legendPos val="b"/></c:legend>' if legend else ""
    return (
        f"<c:chartSpace {SPACE}><c:chart>{heading}<c:plotArea>{groups}{axes}</c:plotArea>"
        f"{shown}</c:chart></c:chartSpace>"
    )


def bars(series: str, direction: str = "col", grouping: str = "clustered", tag="barChart") -> str:
    return f'<c:{tag}><c:barDir val="{direction}"/><c:grouping val="{grouping}"/>{series}</c:{tag}>'


def parsed(xml: str) -> charts.Found:
    return charts.parse(etree.fromstring(xml))


TWO = ser(
    0, "Sheet1!$B$1", "Sheet1!$A$2:$A$3", "Sheet1!$B$2:$B$3", ("Prihod", ["Sij", "Velj"], [1, 2])
) + ser(
    1, "Sheet1!$C$1", "Sheet1!$A$2:$A$3", "Sheet1!$C$2:$C$3", ("Rashod", ["Sij", "Velj"], [3, 4])
)


def test_a_chart_part_gives_its_kind_stacking_title_legend_and_series():
    found = parsed(space(bars(TWO, "bar", "stacked"), title="Prihodi i rashodi"))
    assert (found.kind, found.stacked, found.title, found.legend, found.details) == (
        "bar",
        True,
        "Prihodi i rashodi",
        True,
        False,
    )
    assert found.series[0] == Series(
        Area("Sheet1", 1, 2, 1, 2),
        Area("Sheet1", 2, 1, 3, 1),
        Area("Sheet1", 2, 2, 3, 2),
        "Prihod",
        ["Sij", "Velj"],
        [1.0, 2.0],
        ["General", "General"],
    )


def test_what_our_chart_cannot_keep_is_told_and_a_kind_we_lack_has_none():
    assert parsed(space(bars(TWO, grouping="percentStacked"))).details
    assert parsed(space(bars(TWO, tag="bar3DChart"))).details
    assert parsed(space(bars(TWO) + f"<c:lineChart>{TWO}</c:lineChart>")).details
    assert parsed(space(bars(TWO), axes=AXES * 2)).details
    assert parsed(space(f"<c:radarChart>{TWO}</c:radarChart>")).kind is None
    assert charts.parse(etree.fromstring(f"<c:chartSpace {SPACE}/>")) is None


def test_a_title_set_to_show_without_text_is_the_only_series_name():
    one = ser(0, "'Q1 ''24'!$B$1", None, "'Q1 ''24'!$B$2:$B$4", ("Kom", [], [1, None, 3]))
    xml = space(f"<c:lineChart>{one}</c:lineChart>", legend=False).replace(
        "<c:chart>", "<c:chart><c:title/>"
    )
    found = parsed(xml)
    assert (found.kind, found.title, found.legend) == ("line", "Kom", False)
    assert found.series[0].values == Area("Q1 '24", 2, 2, 4, 2)
    assert found.series[0].shown_values == [1.0, None, 3.0]


def test_series_side_by_side_read_as_our_range_does():
    layout = charts.layout(parsed(space(bars(TWO))).series)
    assert layout == charts.Layout(Area("Sheet1", 1, 1, 3, 3), "cols", True, True, True)
    along = ser(0, "S!$A$2", "S!$B$1:$D$1", "S!$B$2:$D$2") + ser(
        1, "S!$A$3", "S!$B$1:$D$1", "S!$B$3:$D$3"
    )
    layout = charts.layout(parsed(space(bars(along))).series)
    assert layout == charts.Layout(Area("S", 1, 1, 3, 4), "rows", True, True, True)


def test_series_apart_are_drawn_over_the_range_around_them_and_told():
    apart = ser(0, None, "S!$A$1:$A$3", "S!$B$1:$B$3") + ser(1, None, None, "S!$D$1:$D$3")
    layout = charts.layout(parsed(space(bars(apart))).series)
    assert layout == charts.Layout(Area("S", 1, 1, 3, 4), "cols", False, True, False)
    elsewhere = ser(0, None, None, "S!$B$1:$B$3") + ser(1, None, None, "T!$C$1:$C$3")
    assert charts.layout(parsed(space(bars(elsewhere))).series) is None
    assert charts.layout([Series(values=None)]) is None


def drawing(*places: tuple[int, int]) -> str:
    anchors = "".join(
        "<xdr:twoCellAnchor><xdr:from>"
        f"<xdr:col>{col}</xdr:col><xdr:colOff>0</xdr:colOff>"
        f"<xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
        '<xdr:graphicFrame><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/'
        f'drawingml/2006/chart"><c:chart r:id="rId{number}"/></a:graphicData></a:graphic>'
        "</xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>"
        for number, (row, col) in enumerate(places, 1)
    )
    return (
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/'
        f'spreadsheetDrawing" {SPACE}>{anchors}</xdr:wsDr>'
    )


def listed(kind: str, *targets: str) -> str:
    related = "".join(
        f'<Relationship Id="rId{number}" Type="{RELATIONSHIPS}/{kind}" Target="{target}"/>'
        for number, target in enumerate(targets, 1)
    )
    return f'<Relationships xmlns="{LISTED}">{related}</Relationships>'


DATA = {"A1": "", "B1": "Prihod", "C1": "Rashod", "A2": "Sij", "B2": "1", "C2": "3"}


def test_a_sheets_charts_follow_its_table_over_the_cells_they_refer_to(tmp_path):
    lower = ser(0, None, None, "Sheet1!$B$2:$B$5") + ser(1, None, None, "Sheet1!$C$2:$C$5")
    path = book(
        tmp_path,
        {"Sheet1": {**DATA, "A3": "Velj", "B3": "2", "C3": "4"}, "Pregled": {"A1": "x"}},
        parts={
            "xl/worksheets/_rels/sheet2.xml.rels": listed("drawing", "../drawings/drawing1.xml"),
            "xl/drawings/drawing1.xml": drawing((9, 0), (1, 4), (1, 0)),
            "xl/drawings/_rels/drawing1.xml.rels": listed(
                "chart", "../charts/chart1.xml", "../charts/chart2.xml", "/xl/charts/chart3.xml"
            ),
            "xl/charts/chart1.xml": space(f"<c:lineChart>{lower}</c:lineChart>"),
            "xl/charts/chart2.xml": space(bars(TWO), title="Prvi kvartal"),
            "xl/charts/chart3.xml": space(f"<c:radarChart>{TWO}</c:radarChart>"),
        },
    )
    imported = xlsx.read(path, "hr")
    data, sheet = tables(imported)
    own, shown = imported.tabs
    assert [block.type for block in own.blocks] == ["table", "paragraph"]
    blocks = shown.blocks
    assert [block.type for block in blocks] == ["table", "chart", "chart", "paragraph"]
    first, second = blocks[1:3]
    assert first.attrs == {
        "range": {"table": data.id, "from": point(data, "A1"), "to": point(data, "C3")},
        "kind": "column",
        "stacked": False,
        "by": "cols",
        "names": True,
        "labels": True,
        "title": "Prvi kvartal",
        "legend": True,
    }
    assert second.attrs["kind"] == "line"
    assert second.attrs["range"] == {
        "table": data.id,
        "from": point(data, "B2"),
        "to": point(data, "C3"),
    }
    assert sheet.id != data.id
    assert imported.report["lost"] == {"charts": 1}


def sheets_of_charts(tmp_path) -> Path:
    """A workbook of a sheet of data, a chart sheet over it, and a sheet of cells of its own
    and a chart over the data's."""
    related = (
        f'<Relationship Id="rId9" Type="{RELATIONSHIPS}/chartsheet" '
        'Target="chartsheets/sheet1.xml"/>'
    )
    return book(
        tmp_path,
        {"Sheet1": {**DATA, "A3": "Velj", "B3": "2", "C3": "4"}, "Pregled": {"A1": "x"}},
        parts={
            "xl/workbook.xml": lambda xml: xml.replace(
                '<sheet name="Pregled"',
                '<sheet name="Grafikon" sheetId="3" r:id="rId9"/><sheet name="Pregled"',
            ),
            "xl/_rels/workbook.xml.rels": lambda xml: xml.replace(
                "</Relationships>", f"{related}</Relationships>"
            ),
            "xl/chartsheets/sheet1.xml": (
                '<chartsheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                f'xmlns:r="{RELATIONSHIPS}"><drawing r:id="rId1"/></chartsheet>'
            ),
            "xl/chartsheets/_rels/sheet1.xml.rels": listed("drawing", "../drawings/drawing1.xml"),
            "xl/drawings/drawing1.xml": drawing((0, 0)),
            "xl/drawings/_rels/drawing1.xml.rels": listed("chart", "../charts/chart1.xml"),
            "xl/charts/chart1.xml": space(bars(TWO)),
            "xl/worksheets/_rels/sheet2.xml.rels": listed("drawing", "../drawings/drawing2.xml"),
            "xl/drawings/drawing2.xml": drawing((0, 3)),
            "xl/drawings/_rels/drawing2.xml.rels": listed("chart", "../charts/chart2.xml"),
            "xl/charts/chart2.xml": space(f"<c:lineChart>{TWO}</c:lineChart>"),
        },
    )


def test_a_chart_sheet_is_a_tab_of_its_charts_in_the_workbooks_order(tmp_path):
    imported = xlsx.read(sheets_of_charts(tmp_path), "hr")
    data, _ = tables(imported)
    assert [(tab.title, [block.type for block in tab.blocks]) for tab in imported.tabs] == [
        ("Sheet1", ["table", "paragraph"]),
        ("Grafikon", ["chart", "paragraph"]),
        ("Pregled", ["table", "chart", "paragraph"]),
    ]
    whole = {"table": data.id, "from": point(data, "A1"), "to": point(data, "C3")}
    assert imported.tabs[1].blocks[0].attrs["range"] == whole
    assert imported.tabs[2].blocks[1].attrs["range"] == whole


def embedded(sheets: dict[str, dict[str, str]], saved: dict | None = None) -> bytes:
    model = workbooks.create()
    model.saved = saved or {}
    for index, (title, cells) in enumerate(sheets.items()):
        if index:
            model.new_sheet()
        model.rename_sheet(index, title)
        for address, text in cells.items():
            model.set_user_input(index, *formulas.place(address), text)
    model.evaluate()
    return bytes(model.to_xlsx())


def chart_run(rid: str) -> str:
    return (
        '<w:r><w:drawing><wp:inline><wp:extent cx="5486400" cy="3200400"/>'
        '<wp:docPr id="1" name="Grafikon 1"/><a:graphic>'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        f'<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="{rid}"/>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
    )


def word(tmp_path, body: str, charts: dict) -> list:
    path = tmp_path / "file.docx"
    path.write_bytes(word_file(body, charts=charts))
    found = docx.read(path, "hr")
    return found.tabs[0].blocks, found.report["lost"]


def test_a_word_chart_brings_the_sheet_of_its_workbook_just_before_it(tmp_path):
    workbook = embedded(
        {"Sheet1": {**DATA, "A3": "Velj", "B3": "=Ostalo!A1", "C3": "4"}, "Ostalo": {"A1": "2.5"}},
        saved={"Sheet1": {"B3": 2.5}},
    )
    body = f"<w:p>{chart_run('rIdC1')}</w:p><w:p><w:r><w:t>Ispod</w:t></w:r></w:p>"
    blocks, lost = word(tmp_path, body, {"rIdC1": (space(bars(TWO)), workbook)})
    table, chart, paragraph = blocks
    assert (table.type, chart.type, paragraph.text) == ("table", "chart", "Ispod")
    assert "name" not in table.attrs
    assert table.grid.formulas == {}
    assert set(table.grid.texts.values()) >= {"Prihod", "Sij", "Velj", "2,5"}
    assert chart.attrs["range"] == {
        "table": table.id,
        "from": point(table, "A1"),
        "to": point(table, "C3"),
    }
    assert (chart.attrs["names"], chart.attrs["labels"]) == (True, True)
    assert lost == {}


def test_a_linked_word_chart_keeps_the_values_it_last_showed(tmp_path):
    shown = ser(
        0,
        "[1]List!$B$1",
        "[1]List!$A$2:$A$3",
        "[1]List!$B$2:$B$3",
        ("Kom", ["A", "B"], [1.5, 2]),
        "0.0",
    )
    inside = f"<w:tbl><w:tr><w:tc><w:p>{chart_run('rIdC2')}</w:p></w:tc></w:tr></w:tbl>"
    body = f"<w:p>{chart_run('rIdC1')}</w:p>{inside}"
    blocks, lost = word(
        tmp_path,
        body,
        {
            "rIdC1": (space(bars(shown, grouping="percentStacked")), None),
            "rIdC2": (space(bars(TWO)), None),
        },
    )
    table, chart, _ = blocks
    texts = set(table.grid.texts.values())
    assert texts == {"Kom", "A", "B", "1,5", "2"}
    assert len(table.grid.formats) == 2 and set(table.grid.formats.values()) == {"0.0"}
    assert chart.attrs["range"]["table"] == table.id
    assert (chart.attrs["stacked"], chart.attrs["names"], chart.attrs["labels"]) == (
        True,
        True,
        True,
    )
    assert lost == {"charts": 1, "chartDetails": 1}
