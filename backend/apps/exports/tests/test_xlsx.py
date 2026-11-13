import io
import zipfile

import pytest
from lxml import etree

from apps.blobs import store
from apps.blobs.tests.office import with_macros
from apps.blobs.tests.test_blobs import content
from apps.collab import server
from apps.content import grids
from apps.content.blocks import Block, Cell, Grid, Run, placed
from apps.content.grids import LOOK
from apps.documents.models import Node
from apps.exports import xlsx
from apps.exports.tests.test_docx import made
from apps.imports import excel
from apps.imports import xlsx as reader
from apps.imports.tests import test_xlsx, workbooks
from apps.imports.tests.test_docx import run
from apps.imports.tests.test_views import WORD, bring, priced
from apps.imports.tests.word_files import word_file
from apps.jobs.tests import handed
from apps.jobs.tests.handed import done, refused

pytestmark = pytest.mark.django_db

MEDIA_TYPES = {"xlsx": store.XLSX, "xlsm": store.XLSM}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(server, "announce", lambda room, news: None)


def saved(api, node: str, format: str = "xlsx") -> bytes:
    response = handed.saved(api, format, document=node)
    assert response["Content-Type"] == MEDIA_TYPES[format]
    return content(response)


def loaded(tmp_path, data: bytes):
    path = tmp_path / "saved.xlsx"
    path.write_bytes(data)
    model = workbooks.load(path)
    model.evaluate()
    return model


def shape(table: Block) -> tuple:
    """The table as it shows, by the places of its rows and columns rather than their ids."""
    grid = table.grid
    rows, cols = (
        {id: y for y, id in enumerate(grid.rows)},
        {id: x for x, id in enumerate(grid.cols)},
    )

    def placed_pieces(pieces: list) -> list:
        return [
            piece
            if isinstance(piece, str)
            else {end: (rows[at["row"]], cols[at["col"]]) for end, at in piece.items()}
            for piece in pieces
        ]

    return (
        [table.attrs["widths"][col] for col in grid.cols],
        {rows[row]: height for row, height in table.attrs.get("heights", {}).items()},
        rows.get(table.attrs.get("frozen")),
        {
            axis: [{**rows, **cols}[id] for id in ids]
            for axis, ids in table.attrs.get("hidden", {}).items()
        },
        [
            (
                each.y,
                each.x,
                each.rows,
                each.cols,
                [(r.text, r.marks) for r in each.cell.blocks[0].runs],
            )
            for each in placed(table)
        ],
        {
            (rows[key.split(":")[0]], cols[key.split(":")[1]]): placed_pieces(pieces)
            for key, pieces in grid.formulas.items()
        },
        {
            (rows[key.split(":")[0]], cols[key.split(":")[1]]): format
            for key, format in grid.formats.items()
        },
    )


def test_a_spreadsheet_goes_back_to_excel_a_sheet_a_tab_with_its_formulas_and_names(api, tmp_path):
    node = bring(api, priced(tmp_path), title="Cijene")["id"]
    model = loaded(tmp_path, saved(api, node))
    assert [sheet["name"] for sheet in model.get_worksheets_properties()] == ["Cijene", "Popust"]
    assert model.get_cell_formula(1, 1, 1) == "=Cijene!B1*0.9"
    assert [model.get_cell_formula(0, 1, col) for col in (1, 2, 3)] == [
        None,
        "=A1*Porez",
        "=FOOBAR(1)",
    ]
    assert model.get_formatted_cell_value(0, 1, 2) == "2.5"
    assert [(name["name"], name["formula"]) for name in model.get_defined_name_list()] == [
        ("Porez", "1.25")
    ]


def test_a_sheet_comes_back_as_it_went_out(api, tmp_path):
    def prepare(model):
        model.set_column_width(0, 1, 180.0)
        model.set_column_width(0, 2, 45.0)
        model.set_row_height(0, 2, 50.0)
        model.set_row_hidden(0, 3, True)
        model.set_column_hidden(0, 2, True)
        model.set_frozen_rows_count(0, 1)
        model.merge_cells(0, 3, 1, 4, 2)
        style = model.get_cell_style(0, 1, 1)
        style["font"] |= {"b": True, "color": "#C4321C"}
        style["alignment"] = {"horizontal": "center"}
        model.set_cell_style(0, 1, 1, style)
        model.set_cell_style(0, 2, 2, style | {"num_fmt": "0.00%"})

    path = test_xlsx.book(
        tmp_path,
        {"Plan": {"A1": "Ukupno", "B1": "1200", "B2": "=B1/4800", "A3": "Spojeno"}},
        prepare,
    )
    node = bring(api, path.read_bytes(), title="Plan")["id"]
    before = reader.read(path, "hr").tabs[0].blocks[0]
    assert before.attrs["frozen"] == before.grid.rows[0]
    assert before.attrs["hidden"] == {"rows": [before.grid.rows[2]], "cols": [before.grid.cols[1]]}
    assert before.attrs["widths"][before.grid.cols[1]] == 5.0
    again = tmp_path / "again.xlsx"
    again.write_bytes(saved(api, node))
    after = reader.read(again, "hr").tabs[0].blocks[0]
    assert shape(after) == shape(before)
    assert after.attrs["name"] == "Plan"


def test_a_column_and_a_row_styled_whole_come_in_as_their_looks_and_go_back_so(api, tmp_path):
    def prepare(model):
        style = model.get_cell_style(0, 1, 1)
        model.set_column_style(0, 2, style | {"font": style["font"] | {"b": True}})
        model.set_row_style(
            0, 3, style | {"alignment": {"horizontal": "center"}, "fill": {"color": "#D9E2F3"}}
        )
        model.set_cell_style(0, 1, 1, style | {"fill": {"color": "#FFFF00"}})

    path = test_xlsx.book(tmp_path, {"Plan": {"A1": "1", "B1": "2", "B2": "3", "A3": "4"}}, prepare)
    looks = (
        {1: {"marks": {"strong": {}}}},
        {2: {"attrs": {"align": "center"}, "fill": "#d9e2f3"}},
    )

    def placed_looks(table: Block) -> tuple[dict, dict]:
        grid = table.grid
        return (
            {grid.cols.index(id): look for id, look in grid.col_looks.items()},
            {grid.rows.index(id): look for id, look in grid.row_looks.items()},
        )

    assert placed_looks(reader.read(path, "hr").tabs[0].blocks[0]) == looks
    node = bring(api, path.read_bytes(), title="Plan")["id"]
    [laid] = grids.of_document(Node.objects.get(pk=node)).values()
    assert [cell[LOOK] for row in laid.rows for cell in row.cells.values() if LOOK in cell] == [
        {"fill": "#ffff00"}
    ]
    again = tmp_path / "again.xlsx"
    again.write_bytes(saved(api, node))
    model = loaded(tmp_path, again.read_bytes())
    assert model.get_column_style(0, 2)["font"]["b"]
    assert model.get_row_style(0, 3)["alignment"] == {"horizontal": "center"}
    assert model.get_row_style(0, 3)["fill"] == {"color": "#D9E2F3"}
    assert model.get_cell_style(0, 1, 1)["fill"] == {"color": "#FFFF00"}
    assert model.get_cell_style(0, 2, 2)["font"]["b"]
    assert placed_looks(reader.read(again, "hr").tabs[0].blocks[0]) == looks


def test_a_word_table_takes_its_share_of_the_text_width_and_the_documents_font(api, tmp_path):
    cell = "<w:tc><w:p>{}</w:p></w:tc>"
    body = (
        '<w:tbl><w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="9000"/></w:tblGrid><w:tr>'
        + cell.format(run("Stavka"))
        + cell.format(run("Iznos", '<w:highlight w:val="yellow"/>'))
        + "</w:tr></w:tbl>"
    )
    node = bring(api, word_file(body), title="Ponuda")["id"]
    model = loaded(tmp_path, saved(api, node))
    across = [(21.0 - 2 * 2.5) * share / 100 for share in (25, 75)]
    widths = [model.get_column_width(0, col) for col in (1, 2)]
    expected = [cm / xlsx.CHARACTER_CM * workbooks.PIXELS_PER_CHARACTER for cm in across]
    assert widths == pytest.approx(expected)
    style = model.get_cell_style(0, 1, 2)
    assert style["fill"] == {"color": "#FFFF00"}
    assert style["font"]["name"] == model.get_cell_style(0, 1, 1)["font"]["name"] == "Inter"


def test_a_table_s_designs_go_as_excel_tables_or_cell_by_cell_and_come_back(api, tmp_path):
    line = {"line": "single", "width": 0.75, "color": "#123456"}
    own = {"line": "double", "width": 2.25, "color": "#13579b"}
    ours = {
        "rules": "excel",
        "name": "Naš stil",
        "parts": {
            "table": {"edges": {"insideH": line, "bottom": line}},
            "header": {
                "marks": {"strong": {}, "color": {"color": "#fedcba"}},
                "fill": "#1f4e79",
                "edges": {"bottom": {"line": "single", "width": 1.5, "color": "#123456"}},
            },
            "rowBand1": {"fill": "#dde5ee"},
            "totals": {
                "marks": {"strong": False, "underline": {}},
                "fill": "none",
                "edges": {"top": {"line": "double", "width": 2.25}},
            },
        },
        "bands": {"rows": [2, 1], "columns": [1, 1]},
        "on": {"header": True, "totals": True, "rowBands": True},
    }
    scheme = excel.scheme(etree.fromstring(xlsx.THEME_XML))
    medium = excel.preset("TableStyleMedium2", scheme)[0] | {"on": {"header": True}}
    word = {
        "rules": "word",
        "parts": {"header": {"marks": {"strong": {}}, "fill": "#abcdef"}},
        "lines": {"top": line},
        "on": {"header": True},
    }

    def table(id: str, rows: int, design: dict, area: bool = False) -> Block:
        grid = Grid([f"r{y}" for y in range(rows)], ["c0", "c1", "c2"])
        cells = [
            Cell(row, col, [Block("paragraph", runs=[Run(f"{col}{row}" if y else col)])])
            for y, row in enumerate(grid.rows)
            for col in grid.cols
        ]
        if area:
            design = design | {"area": {"from": "r0:c0", "to": f"r{rows - 1}:c1"}}
            cells[6].fill, cells[6].edges = "#fafbfc", {"left": own}
        return Block("table", id, {"name": id, "designs": [design]}, grid=grid, cells=cells)

    content = [
        table("Prvi", 5, ours, area=True),
        table("Drugi", 3, medium),
        table("Treci", 2, word),
    ]
    document, _, _ = made(api, content)
    data = saved(api, str(document.pk))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        styles = etree.fromstring(archive.read("xl/styles.xml"))
        listed = [
            etree.fromstring(archive.read(name))
            for name in sorted(archive.namelist())
            if name.startswith("xl/tables/")
        ]
    assert [each.get("name") for each in styles.iter(f"{{{xlsx.MAIN}}}tableStyle")] == ["Naš stil"]
    assert [
        (each.get("ref"), each.find(f"{{{xlsx.MAIN}}}tableStyleInfo").get("name"))
        for each in listed
    ] == [
        ("A1:B5", "Naš stil"),
        ("A1:C3", "TableStyleMedium2"),
    ]
    model = loaded(tmp_path, data)
    style = model.get_cell_style(2, 1, 1)
    assert (style["fill"], style["font"]["b"], style["border"]["top"]) == (
        {"color": "#ABCDEF"},
        True,
        {"style": "thin", "color": "#123456"},
    )
    path = tmp_path / "again.xlsx"
    path.write_bytes(data)
    first, second, third = (tab.blocks[0] for tab in reader.read(path, "hr").tabs)

    def placed(design: dict, table: Block) -> dict:
        area = design.pop("area")
        rows, cols = table.grid.rows, table.grid.cols
        ends = [area[end].partition(":")[::2] for end in ("from", "to")]
        return design | {"area": [(rows.index(row), cols.index(col)) for row, col in ends]}

    sheet, *tables = first.attrs["designs"]
    assert sheet == {"rules": "excel"}
    assert [placed(each, first) for each in tables] == [ours | {"area": [(0, 0), (4, 1)]}]
    assert [placed(each, second) for each in second.attrs["designs"]] == [
        medium | {"area": [(0, 0), (2, 2)]}
    ]
    assert third.attrs["designs"] == [{"rules": "excel"}]
    owned = [(cell.fill, cell.edges) for cell in first.cells if cell.fill or cell.edges]
    assert owned == [("#fafbfc", {"left": own})]


@pytest.mark.django_db(transaction=True)
def test_a_table_brought_beside_one_of_its_name_takes_a_name_of_its_own(api, tmp_path):
    first = bring(api, priced(tmp_path), title="Cijene")["id"]
    (tmp_path / "other").mkdir()
    other = test_xlsx.book(
        tmp_path / "other",
        {"Cijene": {"A1": "2", "B1": "=A1*Porez"}},
        lambda model: model.new_defined_name("Porez", None, "2"),
    )
    sent = {"blob": store.put(io.BytesIO(other.read_bytes())).sha256, "title": "Druge"}
    done(api, "into", document=first, **sent)
    model = loaded(tmp_path, saved(api, first))
    assert [sheet["name"] for sheet in model.get_worksheets_properties()] == [
        "Cijene",
        "Popust",
        "Cijene (2)",
    ]
    assert {
        (name["name"], name["scope"], name["formula"]) for name in model.get_defined_name_list()
    } == {("Porez", None, "1.25"), ("Porez", 2, "2")}
    assert [model.get_formatted_cell_value(sheet, 1, 2) for sheet in (0, 2)] == ["2.5", "4"]


def test_a_document_without_tables_has_no_workbook(api):
    node = bring(api)["id"]
    assert refused(api, "xlsx", document=node) == (409, "no_tables")


def test_a_workbook_with_macros_goes_back_with_its_vba_project(api, tmp_path):
    original = with_macros(priced(tmp_path))
    response = bring(api, original, title="Cijene")
    assert response["macros"] == "xlsm"
    data = saved(api, response["id"], "xlsm")
    assert store.put(io.BytesIO(data)).media_type == store.XLSM
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(io.BytesIO(data)) as made:
        assert made.read("xl/vbaProject.bin") == source.read("xl/vbaProject.bin")
    path = tmp_path / "saved.xlsm"
    path.write_bytes(data)
    assert reader.read(path, "hr").report["macros"] == [
        {"name": "Module1", "code": 'Sub Zbroji()\n    Range("A1") = "Šećer"\nEnd Sub'}
    ]


def test_only_a_document_from_a_file_with_macros_saves_them(api, tmp_path):
    node = bring(api, priced(tmp_path), title="Cijene")
    assert node["macros"] is None
    assert refused(api, "xlsm", document=node["id"]) == (404, "no_macros")
    word = bring(api, with_macros(WORD))
    assert word["macros"] == "docm"
    assert refused(api, "xlsm", document=word["id"]) == (404, "no_macros")


def test_cells_carry_the_marks_all_their_text_shares():
    runs = [Run("Uk", {"strong": {}, "em": {}}), Run("upno", {"strong": {}})]
    paragraph = Block("paragraph", attrs={"align": "right"}, runs=runs)
    assert xlsx._look(Cell("r", "c", [paragraph])) == ({"strong": {}}, "right")
