import re
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from apps.blobs import store
from apps.content import formulas, palette
from apps.content.blocks import Block, key_of
from apps.content.models import GridRow
from apps.imports import create, reading, sheetml, xlsx
from apps.imports.tests import workbooks

COMMENTS = (
    '<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><commentList>'
    '<comment ref="A1" authorId="0"><text><t>Provjeriti</t></text></comment>'
    '<comment ref="A2" authorId="0"><text><t>Iznos</t></text></comment>'
    "</commentList></comments>"
)
RULES = (
    '<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1">'
    "<formula>TRUE</formula></cfRule></conditionalFormatting>"
    '<dataValidations count="1"><dataValidation type="whole" sqref="A2">'
    "<formula1>1</formula1></dataValidation></dataValidations>"
)


def book(
    tmp_path: Path,
    sheets: dict[str, dict[str, str]],
    prepare: Callable | None = None,
    parts: dict[str, str | Callable[[str], str]] | None = None,
    rules: str = "",
    saved: dict | None = None,
) -> Path:
    """A workbook written with each sheet's cells typed in, `prepare` given the
    model first; parts added, or a part written changed by a function of its text, and
    rules put into the first sheet as Excel would write them."""
    model = workbooks.create()
    for index, title in enumerate(sheets):
        if index:
            model.new_sheet()
        model.rename_sheet(index, title)
    model.saved = saved or {}
    if prepare:
        prepare(model)
    for index, cells in enumerate(sheets.values()):
        for address, text in cells.items():
            model.set_user_input(index, *formulas.place(address), text)
    model.evaluate()
    path = tmp_path / "book.xlsx"
    model.save_to_xlsx(str(path))
    if parts or rules:
        written = tmp_path / "written.xlsx"
        path.rename(written)
        with zipfile.ZipFile(written) as source, zipfile.ZipFile(path, "w") as target:
            changed = {name: each for name, each in (parts or {}).items() if callable(each)}
            for name in source.namelist():
                data = source.read(name)
                if name == "xl/worksheets/sheet1.xml":
                    data = data.replace(b"</worksheet>", f"{rules}</worksheet>".encode())
                if name in changed:
                    data = changed[name](data.decode()).encode()
                target.writestr(name, data)
            for name, data in (parts or {}).items():
                if not callable(data):
                    target.writestr(name, data)
    return path


def tables(imported: reading.Imported) -> list[Block]:
    return [block for tab in imported.tabs for block in tab.blocks if block.type == "table"]


def key(table: Block, address: str) -> str:
    row, col = formulas.place(address)
    return key_of(table.grid.rows[row - 1], table.grid.cols[col - 1])


def point(table: Block, address: str, fixed: bool = False) -> dict:
    row, col = formulas.place(address)
    found = {"row": table.grid.rows[row - 1], "col": table.grid.cols[col - 1]}
    return {**found, "absRow": True, "absCol": True} if fixed else found


def texts(table: Block) -> dict[str, str]:
    return table.grid.texts | {f"{cell.row}:{cell.col}": cell.text for cell in table.cells}


def shown(table: Block, *addresses: str) -> list[str]:
    return [table.grid.values[key(table, address)]["text"] for address in addresses]


def test_each_sheet_is_a_table_under_its_name_with_its_formulas_by_row_and_column(tmp_path):
    path = book(
        tmp_path,
        {
            "Data": {"A1": "1", "A2": "2", "A3": "3.25"},
            "Other sheet": {
                "B2": "=SUM(Data!A1:A3)",
                "B3": "='Other sheet'!$B$2*2+B2",
                "B4": "=SUM(Data!A:A)",
                "B5": '=Data!A3&"!"',
            },
        },
        saved={"Other sheet": {"B2": 6.25, "B3": 18.75, "B4": 6.25, "B5": "3.25!"}},
    )
    imported = xlsx.read(path, "hr")
    data, other = tables(imported)
    assert imported.page is None
    assert [(tab.title, [block.type for block in tab.blocks]) for tab in imported.tabs] == [
        ("Data", ["table", "paragraph"]),
        ("Other sheet", ["table", "paragraph"]),
    ]
    assert (data.attrs["name"], other.attrs["name"]) == ("Data", "Other sheet")
    assert (len(data.grid.rows), len(data.grid.cols)) == (3, 1)
    assert (len(other.grid.rows), len(other.grid.cols)) == (5, 2)
    assert (data.attrs["sized"], other.attrs["sized"]) == (True, True)
    assert list(data.attrs["widths"].values()) == [9.1]
    assert list(other.attrs["widths"].values()) == [9.1, 9.1]
    assert texts(data) == {key(data, "A1"): "1", key(data, "A2"): "2", key(data, "A3"): "3,25"}
    column = {"col": data.grid.cols[0]}
    assert other.grid.formulas == {
        key(other, "B2"): [
            "SUM(",
            {"table": data.id, "from": point(data, "A1"), "to": point(data, "A3")},
            ")",
        ],
        key(other, "B3"): [
            {"from": point(other, "B2", fixed=True)},
            "*2+",
            {"from": point(other, "B2")},
        ],
        key(other, "B4"): ["SUM(", {"table": data.id, "from": column, "to": column}, ")"],
        key(other, "B5"): [{"table": data.id, "from": point(data, "A3")}, '&"!"'],
    }
    assert shown(other, "B2", "B3", "B4", "B5") == ["6,25", "18,75", "6,25", "3.25!"]
    assert imported.report["cells"] == [] and imported.report["functions"] == []


def test_defined_names_are_the_documents_and_point_into_its_tables(tmp_path):
    def prepare(model):
        model.new_defined_name("Total", None, "SUM(Data!$A$1:$A$2)")
        model.new_defined_name("Rate", 1, "0.25")
        model.new_defined_name("_xlnm.Print_Area", 0, "Data!$A$1:$A$2")

    path = book(
        tmp_path,
        {"Data": {"A1": "4", "A2": "6"}, "Calc": {"A1": "=Total*Rate"}},
        prepare,
        saved={"Calc": {"A1": 2.5}},
    )
    imported = xlsx.read(path, "hr")
    data, calc = tables(imported)
    assert sorted(imported.names.values(), key=lambda name: name["name"]) == [
        {"name": "Rate", "pieces": ["0.25"], "table": calc.id},
        {
            "name": "Total",
            "pieces": [
                "SUM(",
                {
                    "table": data.id,
                    "from": point(data, "A1", fixed=True),
                    "to": point(data, "A2", fixed=True),
                },
                ")",
            ],
        },
    ]
    assert calc.grid.formulas == {key(calc, "A1"): ["Total*Rate"]}
    assert shown(calc, "A1") == ["2,5"]


def test_a_name_into_another_workbook_goes_with_its_link(tmp_path, caplog):
    def linked(text: str) -> str:
        return text.replace(
            "</definedNames>",
            '<definedName name="blagdani">[1]konstante!$B$23:$B$36</definedName>'
            "<definedName name=\"Ostali\">'[1]Druga knjiga'!$A$1</definedName></definedNames>",
        )

    path = book(
        tmp_path,
        {"Sheet1": {"A1": "=Rate*4"}},
        lambda model: model.new_defined_name("Rate", None, "0.25"),
        parts={"xl/workbook.xml": linked, "xl/externalLinks/externalLink1.xml": "<externalLink/>"},
    )
    imported = xlsx.read(path, "hr")
    assert [name["name"] for name in imported.names.values()] == ["Rate"]
    assert imported.report["lost"] == {"externalLinks": 1}
    assert "refused" not in caplog.text


def test_a_deleted_range_reads_as_ref_alone_without_the_sheet_it_was_in():
    reader = formulas.Formulas(["Data"], set())
    assert reader.parts("SUM(Data!#REF!,'Data'!#REF!)+Data!A1") == [
        "SUM(#REF!,#REF!)+",
        formulas.Ref(0, formulas.End(1, 1), None, "Data!A1"),
    ]


def test_a_function_we_do_not_know_keeps_its_formula_shows_name_and_is_reported(tmp_path):
    path = book(
        tmp_path,
        {"Sheet1": {"A1": "=FOOBAR(1)+1", "A2": "=SUM(1,2)"}},
        saved={"Sheet1": {"A1": "#NAME?", "A2": 3}},
    )
    imported = xlsx.read(path, "hr")
    (sheet,) = tables(imported)
    assert sheet.grid.formulas[key(sheet, "A1")] == ["FOOBAR(1)+1"]
    assert sheet.grid.values[key(sheet, "A1")] == {"text": "#NAME?", "kind": "error"}
    assert imported.report["functions"] == ["FOOBAR"]
    assert imported.report["cells"] == []


def test_a_formula_written_without_its_value_is_computed_on_import(tmp_path, capfd):
    path = book(
        tmp_path,
        {"Sheet1": {"A1": "2", "A2": "=A1*3"}},
        parts={"xl/worksheets/sheet1.xml": lambda text: re.sub(r"</f><v>[^<]*</v>", "</f>", text)},
    )
    imported = xlsx.read(path, "hr")
    (sheet,) = tables(imported)
    assert key(sheet, "A2") not in sheet.grid.values
    assert imported.saved == {}
    assert capfd.readouterr().out == ""


def test_a_value_is_written_as_the_locale_types_it_and_reads_back_the_same(tmp_path):
    cells = {"A1": "'007", "A2": "1e20", "A3": "0.1", "A4": "TRUE", "A5": "'1,5", "A6": "'=A1"}
    imported = xlsx.read(book(tmp_path, {"Sheet1": cells}), "hr")
    (sheet,) = tables(imported)
    assert [texts(sheet)[key(sheet, address)] for address in cells] == [
        "'007",
        "100000000000000000000",
        "0,1",
        "TRUE",
        "'1,5",
        "'=A1",
    ]
    (tmp_path / "en").mkdir()
    imported = xlsx.read(book(tmp_path / "en", {"Sheet1": cells}), "en")
    (sheet,) = tables(imported)
    assert [texts(sheet)[key(sheet, address)] for address in ("A3", "A5")] == ["0.1", "1,5"]


def test_a_cell_with_a_look_its_link_or_a_merge_has_a_node(tmp_path):
    def prepare(model):
        bold = model.get_cell_style(0, 1, 1)
        bold["font"] = {**bold["font"], "b": True}
        bold["alignment"] = {"horizontal": "center"}
        model.set_cell_style(0, 1, 1, bold)
        model.set_cell_style(0, 1, 2, bold)
        number = model.get_cell_style(0, 2, 1)
        model.set_cell_style(0, 2, 1, {**number, "num_fmt": "0.00"})
        model.set_cell_link(0, 3, 1, {"type": "External", "target": "https://example.com"})
        model.set_cell_link(0, 3, 2, {"type": "Internal", "location": "Sheet1!A1"})
        model.merge_cells(0, 4, 1, 5, 2)

    cells = {"A1": "Naslov", "B1": "=1+1", "A2": "2.5", "A3": "Stranica", "B3": "Gore"}
    imported = xlsx.read(book(tmp_path, {"Sheet1": cells}, prepare), "hr")
    (sheet,) = tables(imported)
    cells = {f"{cell.row}:{cell.col}": cell for cell in sheet.cells}
    title = cells[key(sheet, "A1")]
    assert (title.light, title.blocks[0].attrs, title.blocks[0].runs[0].marks) == (
        False,
        {"align": "center"},
        {"strong": {}},
    )
    assert cells[key(sheet, "B1")].blocks[0].attrs == {
        "align": "center",
        "endMarks": {"strong": {}},
    }
    assert sheet.grid.formats == {key(sheet, "A2"): "0.00"}
    assert sheet.grid.texts == {key(sheet, "A2"): "2,5", key(sheet, "B3"): "Gore"}
    assert key(sheet, "A2") not in cells and key(sheet, "B3") not in cells
    assert cells[key(sheet, "A3")].blocks[0].runs[0].marks == {
        "link": {"href": "https://example.com"}
    }
    merged = cells[key(sheet, "A4")]
    assert (merged.to, [block.runs for block in merged.blocks]) == (key(sheet, "B5"), [[]])
    assert imported.report["lost"] == {"internalLinks": 1}


@pytest.mark.parametrize(
    ("locale", "shown"),
    [
        (
            "hr",
            [
                '#,##0\\ "€";[Red]\\-#,##0\\ "€"',
                '"$"#,##0.00_);\\("$"#,##0.00\\)',
                '#,##0.00\\ "€";[Red]\\-#,##0.00\\ "€"',
            ],
        ),
        (
            "en",
            [
                '"€"#,##0_);[Red]\\("€"#,##0\\)',
                '"$"#,##0.00_);\\("$"#,##0.00\\)',
                '"$"#,##0.00_);[Red]\\("$"#,##0.00\\)',
            ],
        ),
    ],
)
def test_excels_built_in_currency_formats_show_as_the_language_writes_its_own(
    tmp_path, locale, shown
):
    """Ids 6 and 7 with the codes Excel writes for them in Croatian and in English, 8 without a
    code: Excel shows each in the currency of the regional format it runs in."""
    codes = ('"€"#,##0_);[Red]\\("€"#,##0\\)', '"$"#,##0.00_);\\("$"#,##0.00\\)', "0.000")

    def prepare(model):
        for row, code in enumerate(codes, 1):
            model.set_cell_style(0, row, 1, {**model.get_cell_style(0, row, 1), "num_fmt": code})

    def renumbered(text: str) -> str:
        text = re.sub(r'<numFmt numFmtId="166"[^>]*/>', "", text)
        for written, id in (("164", 6), ("165", 7), ("166", 8)):
            text = text.replace(f'numFmtId="{written}"', f'numFmtId="{id}"')
        return text

    cells = {"A1": "12", "A2": "12", "A3": "12"}
    path = book(tmp_path, {"Sheet1": cells}, prepare, {"xl/styles.xml": renumbered})
    (sheet,) = tables(xlsx.read(path, locale))
    assert [sheet.grid.formats[key(sheet, address)] for address in cells] == shown


def test_a_workbook_without_styles_reads_its_cells_in_the_general_format(tmp_path):
    written = book(tmp_path, {"Sheet1": {"A1": "2.5"}})
    path = tmp_path / "bare.xlsx"
    with zipfile.ZipFile(written) as source, zipfile.ZipFile(path, "w") as target:
        for name in source.namelist():
            text = re.sub(
                r"<(Relationship|Override) [^>]*styles[^>]*/>", "", source.read(name).decode()
            )
            if name != "xl/styles.xml":
                target.writestr(name, text)
    (sheet,) = tables(xlsx.read(path, "hr"))
    assert key(sheet, "A1") not in sheet.grid.formats
    assert texts(sheet)[key(sheet, "A1")] == "2,5"


def test_a_sheet_keeps_its_column_widths_and_the_row_heights_given_by_hand(tmp_path):
    def prepare(model):
        model.set_column_width(0, 2, 180.0)
        model.set_row_height(0, 2, 40.0)
        model.set_row_height(0, 9, 40.0)

    imported = xlsx.read(book(tmp_path, {"Sheet1": {"A1": "1", "B3": "2"}}, prepare), "hr")
    (sheet,) = tables(imported)
    assert list(sheet.attrs["widths"].values()) == [9.1, 20.0]
    assert sheet.attrs["heights"] == {sheet.grid.rows[1]: 25.6}


def test_what_a_table_cannot_hold_is_counted_and_a_hidden_row_is_kept(tmp_path):
    def prepare(model):
        model.set_user_array_formula(0, 1, 3, 1, 3, "=A1:A3*2")
        filled = model.get_cell_style(0, 1, 1)
        model.set_cell_style(0, 1, 1, {**filled, "fill": {"color": "#FFFF00"}})
        model.set_row_hidden(0, 2, True)
        model.set_sheet_state(1, "hidden")

    path = book(
        tmp_path,
        {"Sheet1": {"A1": "1", "A2": "2", "A3": "3"}, "Hidden": {"A1": "x"}},
        prepare,
        parts={
            "xl/charts/chartEx1.xml": "<chartSpace/>",
            "xl/media/image1.png": "png",
            "xl/comments1.xml": COMMENTS,
        },
        rules=RULES,
    )
    imported = xlsx.read(path, "hr")
    sheet, _ = tables(imported)
    assert sheet.attrs["hidden"] == {"rows": [sheet.grid.rows[1]]}
    assert sheet.grid.formulas == {
        key(sheet, "C1"): [{"from": point(sheet, "A1"), "to": point(sheet, "A3")}, "*2"]
    }
    assert imported.report["lost"] == {
        "cellComments": 2,
        "charts": 1,
        "conditionalFormats": 1,
        "hiddenSheets": 1,
        "sheetImages": 1,
        "spills": 2,
        "validations": 1,
    }


def test_a_cell_and_a_row_keep_their_fill_a_white_one_too(tmp_path):
    def prepare(model):
        plain = model.get_cell_style(0, 1, 1)
        model.set_cell_style(0, 1, 1, {**plain, "fill": {"color": "#FFFF00"}})
        model.set_cell_style(0, 1, 2, {**plain, "fill": {"color": "#FFFFFF"}})
        model.set_row_style(0, 3, {**plain, "fill": {"color": "#D9E2F3"}})

    cells = {"A1": "1", "B1": "2", "A2": "3", "A3": "4"}
    imported = xlsx.read(book(tmp_path, {"Sheet1": cells}, prepare), "hr")
    (sheet,) = tables(imported)
    fills = {key_of(cell.row, cell.col): cell.fill for cell in sheet.cells}
    assert fills == {
        key(sheet, "A1"): "#ffff00",
        key(sheet, "B1"): "#ffffff",
        key(sheet, "A3"): "#d9e2f3",
    }
    assert sheet.grid.row_looks == {sheet.grid.rows[2]: {"fill": "#d9e2f3"}}
    assert "lost" not in imported.report or "fills" not in imported.report["lost"]


@pytest.mark.django_db
def test_a_value_that_differs_from_the_workbooks_is_reported_and_a_volatile_one_is_not(
    tmp_path, django_user_model
):
    cells = {"A1": "1", "B1": "=A1+1", "B2": "=RAND()", "B3": "=A1*2", "B4": "=NEMA(1)"}

    def saved_otherwise(text: str) -> str:
        return re.sub(r"(<c r=\"B[14]\"[^>]*><f[^>]*>[^<]*</f><v>)[^<]*", r"\g<1>41", text).replace(
            't="e"', ""
        )

    path = book(tmp_path, {"Data": cells}, parts={"xl/worksheets/sheet1.xml": saved_otherwise})
    user = django_user_model.objects.create_user(email="a@b.test", password="x")
    with path.open("rb") as file:
        source = store.put(file)
    node = create.document(source, None, "Book", user)
    node.refresh_from_db()
    assert node.imported["cells"] == ["Data!B1", "Data!B4"]
    assert node.imported["lost"]["values"] == 2
    rows = list(GridRow.objects.filter(grid__document=node).order_by("position"))
    (b1, *_) = [col for col in rows[0].values if rows[0].values[col] == 41]
    assert rows[0].shown[b1] == "41"


def test_what_is_not_a_spreadsheet_or_too_large_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "file.xlsx"
    path.write_bytes(b"not a zip")
    with pytest.raises(reading.Unreadable):
        xlsx.read(path, "hr")
    path = book(tmp_path, {"Sheet1": {"A1": "1", "C3": "3"}})
    monkeypatch.setattr(xlsx, "LARGEST", 8)
    with pytest.raises(reading.TooManyCells):
        xlsx.embedded(path, "hr", "Sheet1")


def _with_huge_part(path: Path, target: Path, claimed: int | None = None) -> Path:
    with (
        zipfile.ZipFile(path) as source,
        zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as written,
    ):
        for name in source.namelist():
            written.writestr(name, source.read(name))
        written.writestr("xl/bomb.xml", b"x" * 2_000_000)
    if claimed is not None:
        data = bytearray(target.read_bytes())
        at = data.find(b"PK\x01\x02")
        while at != -1:
            named = int.from_bytes(data[at + 28 : at + 30], "little")
            if bytes(data[at + 46 : at + 46 + named]) == b"xl/bomb.xml":
                data[at + 24 : at + 28] = claimed.to_bytes(4, "little")
            at = data.find(b"PK\x01\x02", at + 4)
        target.write_bytes(data)
    return target


def test_a_file_that_unpacks_past_the_bound_never_reaches_the_reader(tmp_path, monkeypatch):
    path = _with_huge_part(book(tmp_path, {"Sheet1": {"A1": "1"}}), tmp_path / "huge.xlsx")
    monkeypatch.setattr(sheetml, "LARGEST_BOOK", 1_000_000)
    with pytest.raises(reading.TooLarge):
        xlsx.read(path, "hr")


def test_a_part_that_claims_a_small_size_is_measured_by_unpacking_it(tmp_path, monkeypatch):
    path = _with_huge_part(
        book(tmp_path, {"Sheet1": {"A1": "1"}}), tmp_path / "lying.xlsx", claimed=10
    )
    monkeypatch.setattr(sheetml, "LARGEST_BOOK", 1_000_000)
    with pytest.raises(reading.TooLarge):
        xlsx.read(path, "hr")


def test_an_excel_table_comes_as_a_design_over_its_range_and_a_bordered_cell_keeps_its_edges(
    tmp_path,
):
    def prepare(model):
        plain = model.get_cell_style(0, 1, 1)
        lines = {"left": {"style": "thin", "color": "#FF0000"}, "bottom": {"style": "medium"}}
        model.set_cell_style(0, 5, 4, {**plain, "border": lines})

    table = (
        '<table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="1" '
        'name="Popis" displayName="Popis" ref="A1:B3"><autoFilter ref="A1:B3"/>'
        '<tableColumns count="2"><tableColumn id="1" name="Ime"/><tableColumn id="2" name="Broj"/>'
        '</tableColumns><tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" '
        'showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>'
    )
    related = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdT" Target="../tables/table1.xml" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/table"/></Relationships>'
    )
    parts = {
        "xl/tables/table1.xml": table,
        "xl/worksheets/_rels/sheet1.xml.rels": related,
        "xl/worksheets/sheet1.xml": lambda text: text.replace(
            "</worksheet>",
            '<tableParts count="1"><tablePart r:id="rIdT"/></tableParts></worksheet>',
        ),
        "[Content_Types].xml": lambda text: text.replace(
            "</Types>",
            '<Override PartName="/xl/tables/table1.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/></Types>',
        ),
    }
    cells = {"A1": "Ime", "B1": "Broj", "A2": "a", "B2": "1", "A3": "b", "B3": "2"}
    imported = xlsx.read(book(tmp_path, {"Sheet1": cells}, prepare, parts), "hr")
    (sheet,) = tables(imported)
    base, design = sheet.attrs["designs"]
    assert base == {"rules": "excel"}
    assert (design["rules"], design["name"], design["on"], design["area"]) == (
        "excel",
        "TableStyleMedium2",
        {"header": True, "rowBands": True},
        {"from": key(sheet, "A1"), "to": key(sheet, "B3")},
    )
    assert {"header", "rowBand1", "table"} <= set(design["parts"])
    edges = {key_of(cell.row, cell.col): cell.edges for cell in sheet.cells if cell.edges}
    assert edges == {
        key(sheet, "D5"): {
            "left": {"line": "single", "width": 0.75, "color": palette.named("text", "#ff0000")},
            "bottom": {"line": "single", "width": 1.5},
        }
    }
