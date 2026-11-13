from pycrdt import Doc, XmlElement, XmlText

from apps.content.blocks import (
    Block,
    Cell,
    Grid,
    Note,
    Run,
    body_of,
    in_order,
    light_cell,
    look_of,
    new_id,
    placed,
    read,
    visible,
)
from apps.content.grids import TEXT

from .helpers import written


def roundtrip(blocks: list[Block]) -> list[Block]:
    doc, held = written(blocks)
    received = Doc()
    received.apply_update(doc.get_update())
    return read(received, held)


def test_text_blocks_keep_their_ids_levels_and_marks():
    blocks = [
        Block("heading", attrs={"level": 2}, runs=[Run("Ponuda")]),
        Block("paragraph", runs=[Run("Ukupno", {"strong": {}}), Run(": 120 €")]),
        Block("paragraph"),
    ]
    assert roundtrip(blocks) == blocks
    assert [block.text for block in blocks] == ["Ponuda", "Ukupno: 120 €", ""]


def test_notes_stay_where_their_marks_are_and_out_of_the_text():
    note = Note("foot", runs=[Run("Vidi ", {}), Run("prilog", {"em": {}})])
    end = Note("end", runs=[Run("Izvor: HZN")])
    blocks = [
        Block("paragraph", runs=[Run("Cijena"), note, Run(" vrijedi"), end, Run(".")]),
        Block("heading", attrs={"level": 1}, runs=[Run("Rok"), Note("foot")]),
    ]
    assert roundtrip(blocks) == blocks
    assert [block.text for block in blocks] == ["Cijena vrijedi.", "Rok"]
    assert [[n.text for n in block.notes] for block in blocks] == [
        ["Vidi prilog", "Izvor: HZN"],
        [""],
    ]


def test_a_table_brings_its_grid_and_its_cells_with_their_blocks():
    cells = [
        Cell("r1", "c1", [Block("heading", attrs={"level": 2}, runs=[Run("Stavka")])], "r1:c2"),
        Cell(
            "r2",
            "c2",
            [Block("paragraph", runs=[Run("42", {"strong": {}})]), Block("paragraph")],
            fill="none",
            edges={"top": {"line": "double", "width": 1.5, "color": "#c00000"}, "left": "none"},
        ),
    ]
    grid = Grid(["r1", "r2"], ["c1", "c2"])
    design = {"rules": "word", "name": "lines", "parts": {"header": {"marks": {"strong": {}}}}}
    table = Block("table", attrs={"designs": [design]}, grid=grid, cells=cells)
    assert roundtrip([table]) == [table]
    assert [cell.text for cell in cells] == ["Stavka", "42"]


def test_a_table_is_read_row_by_row_whatever_order_its_cells_were_written_in():
    later = Block("paragraph", runs=[Run("B1")])
    first = Block("paragraph", runs=[Run("A1")])
    hidden = Block("paragraph", runs=[Run("pod spojenom")])
    gone = Block("paragraph", runs=[Run("obrisani redak")])
    cells = [
        Cell("r1", "c2", [later]),
        Cell("r2", "c1", [hidden]),
        Cell("r1", "c1", [first], "r2:c1"),
        Cell("r9", "c1", [gone]),
    ]
    table = Block("table", grid=Grid(["r1", "r2"], ["c1", "c2"]), cells=cells)
    after = Block("paragraph", runs=[Run("Nakon")])
    assert [(p.y, p.x, p.cell.text) for p in placed(table)] == [(0, 0, "A1"), (0, 1, "B1")]
    assert in_order([table, after]) == [table, first, later, after]


def test_a_table_prints_without_its_hidden_lines_and_a_merge_keeps_what_is_shown_of_it():
    cells = [
        light_cell("r1:c1", "Artikl"),
        light_cell("r1:c2", "skriveno"),
        Cell("r2", "c1", [Block("paragraph", runs=[Run("Spojeno")])], "r3:c3"),
        light_cell("r3:c1", "ispod"),
    ]
    attrs = {"hidden": {"rows": ["r3"], "cols": ["c2"]}, "frozen": "r3"}
    table = Block(
        "table", attrs=attrs, grid=Grid(["r1", "r2", "r3"], ["c1", "c2", "c3"]), cells=cells
    )
    shown = visible(table)
    assert (shown.grid.rows, shown.grid.cols) == (["r1", "r2"], ["c1", "c3"])
    assert shown.attrs == {"frozen": "r2"}
    assert [(p.y, p.x, p.rows, p.cols, p.cell.text) for p in placed(shown)] == [
        (0, 0, 1, 1, "Artikl"),
        (1, 0, 1, 2, "Spojeno"),
    ]
    assert visible(Block("table", grid=table.grid, cells=cells)).cells == cells


def test_a_light_cell_is_kept_as_its_text_and_read_as_a_paragraph():
    cells = [
        Cell("r1", "c1", [Block("heading", attrs={"level": 3}, runs=[Run("Artikl")])]),
        light_cell("r1:c2", "Kom"),
        light_cell("r2:c2", "12,5"),
    ]
    table = Block("table", grid=Grid(["r1", "r2"], ["c1", "c2"]), cells=cells)
    doc, held = written([table])
    assert held[table.id].entries(TEXT) == {"r1:c2": "Kom", "r2:c2": "12,5"}
    assert [element.tag for element in body_of(doc).children[0].children] == ["cell"]
    assert roundtrip([table]) == [table]
    assert [(p.y, p.x, p.cell.text) for p in placed(table)] == [
        (0, 0, "Artikl"),
        (0, 1, "Kom"),
        (1, 1, "12,5"),
    ]


def test_a_paragraph_is_light_whatever_attributes_at_their_defaults_an_editor_writes():
    defaults = {"list": None, "checked": False, "restart": False, "align": "center"}
    bold = Block("paragraph", attrs=defaults, runs=[Run("Zbroj", {"bold": {}})])
    assert look_of([bold]) == ("Zbroj", {"marks": {"bold": {}}, "attrs": {"align": "center"}})
    assert look_of([Block("paragraph", attrs={"checked": True}, runs=[Run("x")])]) is None


def test_a_cell_with_a_node_outweighs_its_text_left_behind():
    table = Block("table", "t1", grid=Grid(["r1"], ["c1"]), cells=[light_cell("r1:c1", "a")])
    doc, held = written([table])
    cell = body_of(doc).children[0].children.append(XmlElement("cell", {"row": "r1", "col": "c1"}))
    cell.children.append(XmlElement("paragraph", {"id": "p1"}, [XmlText("b")]))
    [table] = read(doc, held)
    assert [(each.text, each.light) for each in table.cells] == [("b", False)]


def test_a_table_without_its_grid_reads_as_empty():
    doc = Doc()
    body_of(doc).children.append(XmlElement("table", {"id": "t1"}))
    [table] = read(doc, {})
    assert (table.type, table.id, table.grid) == ("table", "t1", None)


def test_a_mark_that_may_overlap_itself_reads_by_its_name():
    doc = Doc()
    paragraph = body_of(doc).children.append(XmlElement("paragraph", {"id": "p1"}))
    text = paragraph.children.append(XmlText())
    text.insert(0, "PONISTRA", {"comment--a1b2": {"id": "k1"}})
    [block] = read(doc, {})
    assert block.runs == [Run("PONISTRA", {"comment": {"id": "k1"}})]


def test_ids_are_twelve_url_safe_characters():
    made = {new_id() for _ in range(1000)}
    assert len(made) == 1000
    assert all(len(id) == 12 and id.replace("-", "").replace("_", "").isalnum() for id in made)
