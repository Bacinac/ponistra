import io
import zipfile
from collections import Counter

import pytest
from lxml import etree

from apps.blobs import store
from apps.blobs.tests.office import with_macros
from apps.blobs.tests.test_blobs import content as read
from apps.collab import server
from apps.content import designs
from apps.content.blocks import Block, Cell, Field, Grid, Run
from apps.content.tests.helpers import fill
from apps.documents import printing
from apps.documents.models import Node, Tab
from apps.documents.views import describe
from apps.exports import pptx
from apps.imports import pptx as reader
from apps.imports.powerpoint import CLR_MAP, built_in_id
from apps.imports.tests.powerpoint_files import powerpoint_file
from apps.jobs.tests import handed
from apps.jobs.tests.handed import refused
from apps.search.tests.test_search import pdf_bytes

from .test_charts import over, sales
from .test_docx import made, parts_of, picture

pytestmark = pytest.mark.django_db

P = f"{{{pptx.P}}}"
A = f"{{{pptx.A}}}"
PROPOSAL = {"id": "p1", "author": "Ana", "user": 1, "date": "2026-10-19T10:00:00Z"}
TITLE = {"font": "headings", "size": 40, "color": "#262626", "anchor": "middle"}
BODY = {"font": "text", "size": 24, "levels": [24, 20, 18], "color": "#262626"}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(server, "announce", lambda room, news: None)


@pytest.fixture
def measuring(monkeypatch):
    """What the printer measures, by each tab's id, as the test sets it."""
    found = {}

    def measured(document_id, session):
        return found

    monkeypatch.setattr(printing, "measured", measured)
    return found


def box(key: str, blocks: list, fit: float = 1, look=None, role=None, **frame) -> dict:
    place = {"x": 1.746, "y": 5.071, "w": 30.374, "h": 12.087, **frame}
    return {
        "key": key,
        "role": role or key,
        "own": True,
        "fit": fit,
        **place,
        "look": look if look is not None else (TITLE if key == "title" else BODY),
        "blocks": blocks,
    }


def at(index: int, y: float = 5.2, h: float = 1, x: float = 2, w: float = 29.866) -> list:
    return [index, x, y, w, h]


def slide(layout, *boxes, hidden=False, notes=()) -> dict:
    return {"layout": layout, "hidden": hidden, "notes": list(notes), "boxes": list(boxes)}


def saved(api, document: Node) -> dict[str, bytes]:
    response = handed.saved(api, "pptx", document=document.pk)
    assert response["Content-Type"] == store.PPTX
    return parts_of(read(response))


def xml(parts: dict[str, bytes], name: str):
    return etree.fromstring(parts[name])


def texts(shape) -> list[str]:
    return ["".join(t.text for t in p.iter(f"{A}t")) for p in shape.iter(f"{A}p")]


def shapes(parts, number: int) -> list:
    tree = xml(parts, f"ppt/slides/slide{number}.xml").find(f"{P}cSld/{P}spTree")
    return [each for each in tree if each.tag in (f"{P}sp", f"{P}pic", f"{P}graphicFrame")]


def placeholder(shape) -> dict | None:
    found = shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
    return None if found is None else dict(found.attrib)


def tab_of(api, document: Node, title: str, content: list[Block]):
    made = api.post(f"/api/nodes/{document.pk}/tabs", {"title": title}, "application/json")
    tab = Tab.objects.get(pk=made.json()["id"])
    fill(tab, content)
    return tab


def test_slides_go_to_powerpoint_in_their_layouts_with_their_notes_and_tabs(api, measuring):
    content = [
        Block("title", runs=[Run("Ponuda")]),
        Block("subtitle", runs=[Run("Listopad")]),
        Block("heading", attrs={"level": 1}, runs=[Run("Cijene")]),
        Block("paragraph", attrs={"list": "bullet"}, runs=[Run("Najam")]),
        Block("paragraph", attrs={"list": "number"}, runs=[Run("Prvo")]),
        Block("paragraph", attrs={"list": "number"}, runs=[Run("Drugo")]),
        Block("paragraph", attrs={"list": "number", "restart": True}, runs=[Run("Opet")]),
        Block("paragraph", attrs={"speaker": True}, runs=[Run("Spomenuti popust")]),
        Block("heading", attrs={"level": 1, "layout": "two", "hidden": True}, runs=[Run("Dva")]),
        Block("paragraph", runs=[Run("Lijevo")]),
        Block("columnBreak"),
        Block("paragraph", runs=[Run("Desno "), Field("page"), Run(" od "), Field("pages")]),
    ]
    document, tab, _ = made(api, content)
    other = tab_of(
        api, document, "Prilog", [Block("heading", attrs={"level": 1}, runs=[Run("Kraj")])]
    )
    measuring[str(tab.pk)] = [
        slide(0, box("title", [at(0)]), box("subtitle", [at(1)])),
        slide(
            "content",
            box("title", [at(2)]),
            box("body", [at(3), at(4, 6.4), at(5, 7.6), at(6, 8.8)], fit=0.8),
            notes=[7],
        ),
        slide(
            2,
            box("title", [at(8)]),
            box("body", [at(9)]),
            box("second", [at(10, h=0), at(11)], x=17),
            hidden=True,
        ),
    ]
    measuring[str(other.pk)] = [slide(1, box("title", [at(0)]))]
    parts = saved(api, document)

    presentation = xml(parts, "ppt/presentation.xml")
    size = presentation.find(f"{P}sldSz")
    assert (int(size.get("cx")), int(size.get("cy"))) == (12192120, 6858000)
    ids = [int(each.get("id")) for each in presentation.iter(f"{P}sldId")]
    assert ids == [256, 257, 258, 259]
    sections = [
        (each.get("name"), [int(slide.get("id")) for slide in each.iter(f"{{{pptx.P14}}}sldId")])
        for each in presentation.iter(f"{{{pptx.P14}}}section")
    ]
    assert sections == [("Ponuda", [256, 257, 258]), ("Prilog", [259])]

    layouts = [xml(parts, f"ppt/slideLayouts/slideLayout{at}.xml") for at in range(1, 7)]
    assert [each.get("type") for each in layouts] == [
        "title",
        "obj",
        "twoObj",
        "secHead",
        "titleOnly",
        "blank",
    ]
    assert layouts[0].find(f"{P}cSld").get("name") == "Naslovni slajd"
    assert "ppt/slideLayouts/slideLayout7.xml" not in parts

    first = shapes(parts, 1)
    assert [placeholder(each) for each in first] == [
        {"type": "ctrTitle"},
        {"type": "subTitle", "idx": "1"},
    ]
    assert [texts(each) for each in first] == [["Ponuda"], ["Listopad"]]
    assert all(each.find(f"{P}spPr/{A}xfrm") is None for each in first)

    title, body, number = shapes(parts, 2)
    assert placeholder(body) == {"idx": "1"}
    assert placeholder(number) == {"type": "sldNum", "sz": "quarter", "idx": "11"}
    assert texts(number) == ["2"]
    assert body.find(f"{P}txBody/{A}bodyPr/{A}normAutofit").get("fontScale") == "80000"
    assert texts(body) == ["Najam", "Prvo", "Drugo", "1.\tOpet"]
    marks = [p.find(f"{A}pPr") for p in body.iter(f"{A}p")]
    assert marks[0].find(f"{A}buChar").get("char") == "•"
    assert [(each.get("type"), each.get("startAt")) for each in body.iter(f"{A}buAutoNum")] == [
        ("arabicPeriod", "1"),
        ("arabicPeriod", "1"),
    ]
    assert marks[3].find(f"{A}buNone") is not None
    assert [each.find(f"{A}spcBef/{A}spcPts").get("val") for each in marks] == [
        "0",
        "672",
        "672",
        "672",
    ]
    assert marks[0].get("indent") == str(-round(1.75 * 24 * 0.8 * pptx.EMU_PER_POINT))
    notes = xml(parts, "ppt/notesSlides/notesSlide1.xml")
    assert texts(notes.find(f".//{P}txBody")) == ["Spomenuti popust"]
    assert "ppt/notesSlides/notesSlide2.xml" not in parts

    third = xml(parts, "ppt/slides/slide3.xml")
    assert third.get("show") == "0"
    assert [(placeholder(each), texts(each)) for each in shapes(parts, 3)] == [
        ({"type": "title"}, ["Dva"]),
        ({"idx": "1"}, ["Lijevo"]),
        ({"idx": "2"}, ["Desno 3 od 4"]),
        ({"type": "sldNum", "sz": "quarter", "idx": "11"}, ["3"]),
    ]
    assert third.find(f".//{A}fld").get("type") == "slidenum"
    relations = parts["ppt/slides/_rels/slide3.xml.rels"].decode()
    assert "slideLayout3.xml" in relations


def test_pictures_tables_and_charts_go_where_the_slides_view_shows_them(api, measuring, tmp_path):
    blob = store.put(io.BytesIO(picture())).sha256
    table = sales(tmp_path)
    table.grid.col_looks[table.grid.cols[0]] = {"fill": "#c00000"}
    chart = over(table, "A1", "C3", title="Prihod")
    content = [
        Block("heading", attrs={"level": 1}, runs=[Run("Brojke")]),
        Block("paragraph", runs=[Run("Uvod")]),
        Block("image", attrs={"blob": blob, "alt": "Logotip"}),
        Block("paragraph", runs=[Run("Između")]),
        table,
        chart,
    ]
    document, tab, _ = made(api, content)
    measuring[str(tab.pk)] = [
        slide(
            1,
            box("title", [at(0)]),
            box(
                "body",
                [at(1, 5.2, 1), at(2, 6.4, 4, 3, 8), at(3, 10.6), at(4, 11.8, 2), at(5, 14, 3)],
                fit=0.5,
            ),
        )
    ]
    parts = saved(api, document)
    title, before, image, after, grid, drawn, _ = shapes(parts, 1)
    assert placeholder(before) == {"idx": "1"}
    frame = before.find(f"{P}spPr/{A}xfrm")
    assert frame.find(f"{A}off").attrib == {
        "x": str(pptx.emu(2 - 0.254)),
        "y": str(pptx.emu(5.2 - 0.127)),
    }
    assert texts(before) == ["Uvod"]
    assert placeholder(after) is None
    assert texts(after) == ["Između"]
    for text in (before, after):
        props = text.find(f"{P}txBody/{A}bodyPr")
        assert props.get("anchor") == "t"
        assert props.find(f"{A}noAutofit") is not None
        assert {run.get("sz") for run in text.iter(f"{A}rPr")} == {"1200"}

    assert image.find(f"{P}nvPicPr/{P}cNvPr").get("descr") == "Logotip"
    place = image.find(f"{P}spPr/{A}xfrm")
    assert place.find(f"{A}off").attrib == {"x": str(pptx.emu(3)), "y": str(pptx.emu(6.4))}
    assert place.find(f"{A}ext").attrib == {"cx": str(pptx.emu(8)), "cy": str(pptx.emu(4))}
    assert "ppt/media/picture1.png" in parts

    rows = list(grid.iter(f"{A}tr"))
    assert len(rows) == 3
    widths = [int(each.get("w")) for each in grid.iter(f"{A}gridCol")]
    assert abs(sum(widths) - pptx.emu(29.866)) <= len(widths)
    cells = [[texts(cell)[0] for cell in row.iter(f"{A}tc")] for row in rows[1:]]
    assert cells == [["Sij", "1.200,00", "300"], ["Velj", "2.400,00", "450"]]
    sizes = {run.get("sz") for run in grid.iter(f"{A}rPr")}
    assert sizes == {"1200"}
    first, second = list(rows[0].iter(f"{A}tc"))[:2]
    assert first.find(f"{A}tcPr/{A}solidFill/{A}srgbClr").get("val") == "C00000"
    assert second.find(f"{A}tcPr/{A}solidFill") is None

    assert drawn.find(f".//{{{pptx.charts.C}}}chart") is not None
    assert "ppt/charts/chart1.xml" in parts
    assert "ppt/embeddings/Microsoft_Excel_Worksheet1.xlsx" in parts


def table_of(designs: list[dict], own: dict | None = None) -> Block:
    grid = Grid(["r1", "r2", "r3"], ["c1", "c2"])
    cells = [
        Cell(row, col, [Block("paragraph", runs=[Run(row + col)])])
        for row in grid.rows
        for col in grid.cols
    ]
    if own:
        cells[3].fill, cells[3].edges = "#abcdef", own
    return Block("table", "t", {"designs": designs} if designs else {}, grid=grid, cells=cells)


def exported_table(api, measuring, tmp_path, table: Block, lost: int = 0) -> tuple[dict, Block]:
    document, tab, _ = made(api, [table])
    measuring[str(tab.pk)] = [slide(2, box("body", [at(0, 5.2, 6)]))]
    parts = saved(api, document)
    path = tmp_path / "saved.pptx"
    path.write_bytes(read(handed.saved(api, "pptx", document=document.pk)))
    imported = reader.read(path, "hr")
    (again,) = [block for block in imported.tabs[0].blocks if block.type == "table"]
    assert imported.report["lost"].get("tableStyles", 0) == lost
    return parts, again


def test_one_of_powerpoints_own_styles_goes_as_its_id_and_comes_back_as_it_went(
    api, measuring, tmp_path
):
    document, tab, _ = made(api, [table_of([])])
    measuring[str(tab.pk)] = [slide(2, box("body", [at(0, 5.2, 6)]))]
    scheme, faces, formats = reader.themed(xml(saved(api, document), "ppt/theme/theme1.xml"))
    master = reader.Master(None, None, scheme, dict(CLR_MAP), faces, {}, formats=formats)
    id = built_in_id("Medium Style 2 - Accent 3")
    props = etree.fromstring(
        f'<a:tblPr xmlns:a="{pptx.A}" firstRow="1" bandRow="1">'
        f"<a:tableStyleId>{id}</a:tableStyleId></a:tblPr>"
    )
    design = reader.Looks(Counter()).design(props, master)
    own = {"left": {"line": "single", "width": 2, "color": "#13579b"}, "right": "none"}
    parts, again = exported_table(api, measuring, tmp_path, table_of([design], own))
    tbl = next(xml(parts, "ppt/slides/slide1.xml").iter(f"{A}tbl"))
    props = tbl.find(f"{A}tblPr")
    switches = [props.get(each) for each in ("firstRow", "bandRow", "lastRow")]
    assert (props.findtext(f"{A}tableStyleId"), switches) == (id, ["1", "1", "0"])
    assert [len(each) for each in tbl.iter(f"{A}tcPr")] == [0, 0, 0, 3, 0, 0]
    assert len(xml(parts, "ppt/tableStyles.xml")) == 0
    assert again.attrs["designs"] == [design]
    drawn = {(cell.row, cell.col): (cell.fill, cell.edges) for cell in again.cells}
    assert [drawn[slot] for slot in drawn if drawn[slot] != (None, None)] == [("#abcdef", own)]


def test_any_other_design_goes_into_its_cells_under_no_style(api, measuring, tmp_path):
    line = {"line": "single", "width": 1, "color": "#fedcba"}
    design = {
        "rules": "powerpoint",
        "name": "Naš stil",
        "parts": {
            "table": {"fill": "#dde5ee", "edges": {"insideH": line, "insideV": line}},
            "header": {
                "marks": {"strong": {}, "color": {"color": "#fedcba"}},
                "fill": "#1f4e79",
                "edges": {"bottom": {"line": "double", "width": 3, "color": "#123456"}},
            },
            "rowBand1": {"fill": "#4472c480"},
            "totals": {
                "marks": {"em": {}, "strong": False},
                "edges": {"top": {"line": "dashed", "width": 1.5, "color": "#123456"}},
            },
            "topLeft": {"fill": "none"},
        },
        "on": {"header": True, "totals": True, "rowBands": True},
        "background": {
            "angle": 90,
            "stops": [{"at": 0, "color": "#fafbfc"}, {"at": 100, "color": "#dde5ee"}],
        },
        "shadow": {"color": "#00000066", "blur": 4, "distance": 3, "angle": 45},
    }
    own = {"left": {"line": "single", "width": 2, "color": "#13579b"}, "right": "none"}
    parts, again = exported_table(api, measuring, tmp_path, table_of([design], own))
    props = next(xml(parts, "ppt/slides/slide1.xml").iter(f"{A}tblPr"))
    assert props.findtext(f"{A}tableStyleId") == pptx.NO_STYLE
    assert len(xml(parts, "ppt/tableStyles.xml")) == 0
    (back,) = again.attrs["designs"]
    assert (back["name"], back["background"], back["shadow"]) == (
        "No Style, No Grid",
        design["background"],
        design["shadow"],
    )
    rows, cols = again.grid.rows, again.grid.cols
    resolved = designs.resolved(design, 3, 2, {(1, 1): own})

    def lines(edges: dict | None) -> dict:
        return {side: edge for side, edge in (edges or {}).items() if edge not in (None, "none")}

    drawn = {
        (rows.index(cell.row), cols.index(cell.col)): (cell.fill, lines(cell.edges))
        for cell in again.cells
    }
    want = {slot: (cell.fill, lines(cell.edges)) for slot, cell in resolved.items()}
    want[(1, 1)] = ("#abcdef", want[(1, 1)][1])
    assert drawn == want
    header = [run for cell in again.cells[:2] for each in cell.blocks for run in each.runs]
    looks = [(run.marks.get("strong"), run.marks.get("color")) for run in header]
    assert looks == [({}, {"color": "#fedcba"})] * 2


def test_powerpoint_casts_a_table_s_shadow_only_from_what_it_fills(api, measuring, tmp_path):
    shadow = {"color": "#00000066", "blur": 4, "distance": 3, "angle": 45}
    bare = {"rules": "powerpoint", "name": "Sjena", "shadow": shadow}
    filled = {**bare, "parts": {"table": {"fill": "#dde5ee"}}}
    for design, own, lost, kept in (
        (bare, None, 0, False),
        (bare, {"right": "none"}, 1, False),
        (filled, None, 0, True),
    ):
        table = table_of([design], own)
        _, again = exported_table(api, measuring, tmp_path, table, lost)
        assert ("shadow" in again.attrs["designs"][0]) is kept


def test_a_horizontal_line_goes_as_a_line_across_its_place(api, measuring):
    content = [
        Block("heading", attrs={"level": 1}, runs=[Run("Crta")]),
        Block("paragraph", runs=[Run("Iznad")]),
        Block("horizontalRule"),
        Block("paragraph", runs=[Run("Ispod")]),
    ]
    document, tab, _ = made(api, content)
    measuring[str(tab.pk)] = [
        slide(1, box("title", [at(0)]), box("body", [at(1, 5.2), at(2, 6.4, 0.5), at(3, 7.2)]))
    ]
    parts = saved(api, document)
    tree = xml(parts, "ppt/slides/slide1.xml").find(f"{P}cSld/{P}spTree")
    (line,) = tree.findall(f"{P}cxnSp")
    place = line.find(f"{P}spPr/{A}xfrm")
    assert place.find(f"{A}off").attrib == {"x": str(pptx.emu(2)), "y": str(pptx.emu(6.65))}
    assert place.find(f"{A}ext").attrib == {"cx": str(pptx.emu(29.866)), "cy": "0"}
    assert line.find(f"{P}spPr/{A}prstGeom").get("prst") == "line"
    (color,) = line.find(f"{P}spPr/{A}ln/{A}solidFill")
    assert color.tag in (f"{A}srgbClr", f"{A}schemeClr")
    _, above, below, _ = shapes(parts, 1)
    assert (texts(above), texts(below)) == (["Iznad"], ["Ispod"])


def test_the_pages_a_pdf_shows_go_below_one_another_in_its_frame(api, measuring):
    blob = store.put(io.BytesIO(pdf_bytes("Ugovor", "Potpisi", "Prilog"))).sha256
    content = [
        Block("heading", attrs={"level": 1}, runs=[Run("Najam")]),
        Block("pdf", attrs={"blob": blob, "title": "Najam", "first": 2}),
        Block("pdf", attrs={"blob": blob, "last": 1}),
    ]
    document, tab, _ = made(api, content)
    measuring[str(tab.pk)] = [
        slide(1, box("title", [at(0)]), box("body", [at(1, 5, 10, 2, 20), at(2, 2, 40, 4, 10)]))
    ]
    parts = saved(api, document)
    _, first, second, alone, _ = shapes(parts, 1)

    def place(shape) -> tuple:
        frame = shape.find(f"{P}spPr/{A}xfrm")
        sides = {**frame.find(f"{A}off").attrib, **frame.find(f"{A}ext").attrib}
        return shape.find(f"{P}nvPicPr/{P}cNvPr").get("descr"), *map(int, sides.values())

    across = 10 * 595 / (2 * 842)
    left = 2 + (20 - across) / 2
    assert [place(each) for each in (first, second, alone)] == [
        ("Najam · 2", *map(pptx.emu, (left, 5, across, 5))),
        ("Najam · 3", *map(pptx.emu, (left, 10, across, 5))),
        ("1", *map(pptx.emu, (4, 2, 10, 10 * 842 / 595))),
    ]
    assert sorted(name for name in parts if name.startswith("ppt/media/")) == [
        "ppt/media/page1.png",
        "ppt/media/page2.png",
        "ppt/media/page3.png",
    ]


def test_proposals_go_as_the_text_before_them(api, measuring):
    proposed = {"insertion": PROPOSAL}
    content = [
        Block("heading", attrs={"level": 1}, runs=[Run("Uvjeti")]),
        Block(
            "paragraph",
            runs=[
                Run("Plaćanje "),
                Run("odmah ", {"insertion": PROPOSAL}),
                Run("u roku ", {"deletion": PROPOSAL}),
                Run("30 dana", {"strong": {}, "formatting": {**PROPOSAL, "before": {}}}),
            ],
        ),
        Block("paragraph", attrs=proposed, runs=[Run(" i bez kamata", {"insertion": PROPOSAL})]),
        Block(
            "paragraph",
            attrs={"formatting": {**PROPOSAL, "before": {"type": "paragraph", "attrs": {}}}},
            runs=[Run("Dostava")],
        ),
    ]
    content[3].attrs["list"] = "bullet"
    document, tab, _ = made(api, content)
    measuring[str(tab.pk)] = [
        slide(1, box("title", [at(0)]), box("body", [at(1), at(2, 6.4), at(3, 7.6)]))
    ]
    title, body, _ = shapes(saved(api, document), 1)
    assert texts(body) == ["Plaćanje u roku 30 dana", "Dostava"]
    assert {run.get("b") for run in body.iter(f"{A}rPr")} == {None}
    assert body.find(f".//{A}buChar") is None


def test_slides_measured_other_than_they_are_are_refused(api, measuring):
    content = [Block("heading", attrs={"level": 1}, runs=[Run("Jedan")])]
    document, tab, _ = made(api, content)
    measuring[str(tab.pk)] = []
    assert refused(api, "pptx", document=document.pk) == (409, "slides_changed")


def test_without_the_printer_slides_are_refused_aloud(api, monkeypatch):
    def measured(document_id, session):
        raise printing.Unavailable

    monkeypatch.setattr(printing, "measured", measured)
    document, _, _ = made(api, [Block("paragraph", runs=[Run("Tekst")])])
    assert refused(api, "pptx", document=document.pk) == (503, "printer_unavailable")


def test_slides_from_a_file_with_macros_go_back_with_its_vba_project(api, measuring, tmp_path):
    original = with_macros(powerpoint_file())
    content = [Block("heading", attrs={"level": 1}, runs=[Run("Jedan")])]
    document, tab, _ = made(api, content)
    document.source = store.put(io.BytesIO(original))
    document.save()
    measuring[str(tab.pk)] = [slide(1, box("title", [at(0)]))]
    assert describe(document)["macros"] == "pptm"
    data = read(handed.saved(api, "pptm", document=document.pk))
    assert store.put(io.BytesIO(data)).media_type == store.PPTM
    parts = parts_of(data)
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        assert parts["ppt/vbaProject.bin"] == source.read("ppt/vbaProject.bin")
    path = tmp_path / "saved.pptm"
    path.write_bytes(data)
    assert [each["name"] for each in reader.read(path, "hr").report["macros"]] == ["Module1"]
