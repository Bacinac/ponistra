import csv
import io
import zipfile
from pathlib import Path

import pytest

from apps.blobs import store
from apps.content.models import Grid, GridRow, Shared
from apps.documents.models import Node
from apps.exports import delimited as saved_as
from apps.exports import xlsx as exported
from apps.imports import create, delimited, laying, office, reading, sheetml
from apps.imports.tests.test_xlsx import book
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def ana():
    return User.objects.create_user(email="ana@example.com", password="x")


def imported(path: Path, user, opened=None):
    with path.open("rb") as file:
        return create.document(store.put(file), None, "Velika", user, opened)


def rows_of(document):
    grid = Grid.objects.get(document=document)
    cols = [col["id"] for col in grid.cols]
    return [
        [
            (
                (row.cells.get(col) or {}).get("text"),
                row.values.get(col),
                row.shown.get(col),
                (row.cells.get(col) or {}).get("to") is not None,
            )
            for col in cols
        ]
        for row in GridRow.objects.filter(grid=grid).order_by("position")
    ]


FILLED = {
    "Sheet1": {
        "A1": "1",
        "B1": "tekst",
        "C1": "=A1+1",
        "A2": "3",
        "C2": "=A2+1",
        "A4": "4",
        "C4": "=SUM(A1:A4)",
    }
}


def test_a_large_sheet_is_read_as_a_small_one_is(tmp_path, ana, monkeypatch):
    path = book(tmp_path, FILLED, saved={"Sheet1": {"C1": 2, "C2": 4, "C4": 8}})
    whole = rows_of(imported(path, ana))
    monkeypatch.setattr(sheetml, "LARGE_PART", 0)
    flowed = rows_of(imported(path, ana))
    assert flowed == whole


def test_the_first_rows_can_be_read_before_the_last_are_written(tmp_path, ana, monkeypatch):
    monkeypatch.setattr(sheetml, "LARGE_PART", 0)
    seen = []
    document = imported(
        book(tmp_path, FILLED, saved={"Sheet1": {"C1": 2, "C2": 4, "C4": 8}}),
        ana,
        lambda node: seen.append(Grid.objects.filter(document=node).get().calculated),
    )
    assert seen and seen[0]
    assert GridRow.objects.filter(grid__document=document).count() == 4


def test_a_formula_that_differs_from_the_file_keeps_its_value_and_is_reported(
    tmp_path, ana, monkeypatch
):
    monkeypatch.setattr(sheetml, "LARGE_PART", 0)
    path = book(tmp_path, FILLED, saved={"Sheet1": {"C1": 99, "C2": 4, "C4": 8}})
    document = imported(path, ana)
    assert document.imported["lost"]["values"] == 1
    assert document.imported["cells"] == ["Sheet1!C1"]
    assert rows_of(document)[0][2][1] == 99


def test_a_large_sheets_merges_and_styles_are_kept(tmp_path, ana, monkeypatch):
    monkeypatch.setattr(sheetml, "LARGE_PART", 0)

    def prepared(model):
        style = model.get_cell_style(0, 1, 1)
        style["font"]["b"] = True
        model.set_cell_style(0, 1, 1, style)

    path = book(
        tmp_path,
        FILLED,
        prepare=prepared,
        rules='<mergeCells count="1"><mergeCell ref="A1:B2"/></mergeCells>',
        saved={"Sheet1": {"C1": 2, "C2": 4, "C4": 8}},
    )
    document = imported(path, ana)
    first = GridRow.objects.filter(grid__document=document).order_by("position").first()
    held = next(iter(first.cells.values()))
    assert "to" in held
    assert Shared.objects.filter(document=document, key=held["look"]).exists()


def test_a_file_of_many_rows_takes_the_memory_of_one_batch(tmp_path, ana, monkeypatch):
    monkeypatch.setattr(sheetml, "LARGE_PART", 0)
    monkeypatch.setattr("apps.imports.laying.BATCH", 2)
    document = imported(book(tmp_path, {"Sheet1": {f"A{n}": str(n) for n in range(1, 8)}}), ana)
    assert GridRow.objects.filter(grid__document=document).count() == 7


def written(tmp_path: Path, text: bytes) -> Path:
    path = tmp_path / "rows.csv"
    path.write_bytes(text)
    return path


def test_a_csv_is_a_table_typed_as_the_locale_types(tmp_path, ana, monkeypatch):
    monkeypatch.setattr(store, "sniff", lambda sample: store.TEXT)
    document = imported(
        written(tmp_path, b"naziv;cijena;datum\nkruh;2,50;12.3.2024\n=1+1;;'x\n"), ana
    )
    (head, line, last) = rows_of(document)
    assert [cell[1] for cell in head] == ["naziv", "cijena", "datum"]
    assert line[1][1] == 2.5
    assert isinstance(line[2][1], float) and line[2][2]
    assert last[0][0] == "'=1+1" and last[0][1] == "=1+1"
    assert last[2][1] == "'x"


@pytest.mark.parametrize(
    ("text", "delimiter"),
    [(b"a,b,c\n1,2,3\n", ","), (b"a\tb\n1\t2\n", "\t"), (b"a;b\n1;2\n", ";")],
)
def test_a_csv_says_its_delimiter(tmp_path, text, delimiter):
    path = written(tmp_path, text)
    assert delimited._delimiter(path, delimited._encoding(path)) == delimiter


def test_a_csv_in_windows_1250_is_read(tmp_path):
    path = written(tmp_path, "šđčćž;x\n".encode("cp1250"))
    assert delimited._encoding(path) == "cp1250"


def test_a_table_is_saved_as_csv_as_it_shows(tmp_path, ana, monkeypatch):
    monkeypatch.setattr(store, "sniff", lambda sample: store.TEXT)
    document = imported(written(tmp_path, b"a;1,5\n'b;\n"), ana)
    with saved_as.table(document) as out:
        found = list(
            csv.reader(io.TextIOWrapper(out, encoding="utf-8-sig", newline=""), delimiter=";")
        )
    assert found == [["a", "1,5"], ["'b", ""]]


def test_rows_past_excels_last_go_on_a_sheet_of_their_own(tmp_path, ana, monkeypatch):
    monkeypatch.setattr(exported, "EXCEL_ROWS", 3)
    document = imported(book(tmp_path, {"Sheet1": {f"A{n}": str(n) for n in range(1, 8)}}), ana)
    with exported.workbook(document) as out:
        data = out.read()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        sheets = sorted(
            name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")
        )
        workbook = archive.read("xl/workbook.xml").decode()
    assert len(sheets) == 3
    assert "Sheet1 (2)" in workbook and "Sheet1 (3)" in workbook


def test_too_broken_a_csv_is_refused(tmp_path, ana, monkeypatch):
    monkeypatch.setattr(delimited, "LONGEST_FIELD", 3)
    monkeypatch.setattr(store, "sniff", lambda sample: store.TEXT)
    with pytest.raises(reading.Unreadable):
        imported(written(tmp_path, b"abcdefgh;1\n"), ana)


SHEET = (
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    '<row r="1"><c r="A1"><f t="array" ref="A1:B20">1</f><v>1</v></c><c r="B1"><v>2</v></c></row>'
    "</sheetData></worksheet>"
)


def _twice(workbook: str) -> str:
    start = workbook.index("<sheet ")
    end = workbook.index("/>", start) + 2
    sheet = workbook[start:end].replace('sheetId="1"', 'sheetId="2"').replace("Sheet1", "Drugi")
    return workbook[:end] + sheet + workbook[end:]


def test_a_part_denser_than_a_reader_takes_on_is_refused(tmp_path, monkeypatch):
    path = book(tmp_path, {"Sheet1": {"A1": "a"}})
    monkeypatch.setattr(office, "MOST_NODES", 5)
    with pytest.raises(reading.TooLarge):
        sheetml.Source(path, "hr")


def test_an_element_that_runs_on_is_refused_before_it_is_held(tmp_path, monkeypatch):
    source = sheetml.Source(book(tmp_path, {"Sheet1": {"A1": "a", "B1": "b"}}), "hr")
    monkeypatch.setattr(sheetml, "LONGEST_ELEMENT", 16)
    with pytest.raises(reading.TooLarge):
        source.sheet(0)


def test_sheets_too_much_together_are_read_in_rows(tmp_path, monkeypatch):
    path = book(tmp_path, {"Sheet1": {"A1": "a"}, "Drugi": {"A1": "b"}})
    first = sheetml.checked(path)["xl/worksheets/sheet1.xml"]
    monkeypatch.setattr(sheetml, "LARGEST_WHOLE_SHEETS", first)
    source = sheetml.Source(path, "hr")
    assert [source.large(0), source.large(1)] == [False, True]


def test_one_part_cannot_stand_for_two_sheets(tmp_path):
    path = book(tmp_path, {"Sheet1": {"A1": "a"}}, parts={"xl/workbook.xml": _twice})
    with pytest.raises(reading.Unreadable):
        sheetml.Source(path, "hr")


@pytest.mark.parametrize("most, kept", [(1_000, False), (10, True)])
def test_spilled_cells_are_remembered_only_up_to_a_limit(tmp_path, monkeypatch, most, kept):
    monkeypatch.setattr(sheetml, "MOST_SPILLED", most)
    path = book(
        tmp_path, {"Sheet1": {"A1": "a"}}, parts={"xl/worksheets/sheet1.xml": lambda _: SHEET}
    )
    assert ((1, 2) in sheetml.Source(path, "hr").sheet(0).cells) is kept


@pytest.mark.parametrize("flowed", [False, True])
def test_a_workbook_with_more_different_formulas_than_an_import_takes_is_refused(
    tmp_path, ana, monkeypatch, flowed
):
    if flowed:
        monkeypatch.setattr(sheetml, "LARGE_PART", 0)
    cells = {f"A{y}": str(y) for y in range(1, 5)}
    cells |= {f"B{y}": f"=A{y}*2" for y in range(1, 5)}
    path = book(tmp_path, {"Sheet1": {**cells, "C1": "=A1+1", "C2": "=A1+2"}})
    monkeypatch.setattr(laying, "MOST_FORMULAS", 3)
    imported(path, ana)
    cells["C3"] = "=A1+3"
    path = book(tmp_path, {"Sheet1": {**cells, "C1": "=A1+1", "C2": "=A1+2", "C3": "=A1+3"}})
    held = Node.objects.count()

    with pytest.raises(reading.TooManyFormulas):
        imported(path, ana)

    assert Node.objects.count() == held + flowed
