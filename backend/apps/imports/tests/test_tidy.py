from apps.content import styles
from apps.content.blocks import Block, Cell, Grid, Run, light_cell
from apps.imports.reading import Imported, Tab
from apps.imports.tidy import tidy

ARIAL = {"font": {"family": "Arial"}, "size": {"pt": 11}}
BODY = "Ovo je tekst koji je autor oblikovao rukom, redak za retkom, bez stilova."


def line(text: str, marks: dict, id: str) -> Block:
    return Block("paragraph", id, runs=[Run(text, marks)])


def imported(*content: Block, template: dict | None = None) -> Imported:
    theme = dict(styles.TEMPLATE[styles.THEME])
    return Imported([Tab("", list(content))], None, {}, theme, {}, {}, [], {}, {}, template)


def tidied(found: Imported) -> list[tuple[str, int | None, dict]]:
    tidy(found)
    return [
        (each.type, each.attrs.get("level"), each.runs[0].marks) for each in found.tabs[0].blocks
    ]


def look(found: Imported, id: str) -> tuple:
    style = found.styles[id]
    return style["font"], style["size"], style["bold"], style["color"]


def test_the_text_style_takes_what_the_text_shows_by_hand_and_larger_lines_become_headings():
    found = imported(
        line("Uvod", {**ARIAL, "size": {"pt": 16}, "strong": {}}, "a"),
        line(BODY, ARIAL, "b"),
        line("Pojmovi", {**ARIAL, "size": {"pt": 14}, "strong": {}}, "c"),
        line(BODY, ARIAL, "d"),
        line("Napomena", {**ARIAL, "strong": {}}, "e"),
        line("Ovo je naglašena rečenica.", {**ARIAL, "size": {"pt": 16}, "strong": {}}, "f"),
        line("Kratko", {}, "g"),
    )
    assert tidied(found) == [
        ("heading", 1, {}),
        ("paragraph", None, {}),
        ("heading", 2, {}),
        ("paragraph", None, {}),
        ("paragraph", None, {"strong": {}}),
        ("paragraph", None, {"size": {"pt": 16}, "strong": {}}),
        ("paragraph", None, {}),
    ]
    assert [look(found, id) for id in ("text", "h1", "h2")] == [
        ("Liberation Sans", 11, False, None),
        ("Liberation Sans", 16, True, None),
        ("Liberation Sans", 14, True, None),
    ]


def test_lines_of_one_look_at_the_text_s_size_are_headings_and_a_single_one_is_not():
    marked = {**ARIAL, "strong": {}, "color": {"color": "teal"}}
    found = imported(
        line("Ponuda", {**ARIAL, "size": {"pt": 14}, "strong": {}}, "a"),
        line("1. Predmet", marked, "b"),
        line(BODY, ARIAL, "c"),
        line("2. Cijena", marked, "d"),
        line(BODY, ARIAL, "e"),
        line("Napomena", {**ARIAL, "strong": {}}, "f"),
    )
    assert tidied(found) == [
        ("heading", 1, {}),
        ("heading", 2, {}),
        ("paragraph", None, {}),
        ("heading", 2, {}),
        ("paragraph", None, {}),
        ("paragraph", None, {"strong": {}}),
    ]
    assert look(found, "h2") == ("Liberation Sans", 11, True, "teal")


def test_a_heading_style_the_file_shows_already_keeps_its_look_and_the_line_its_own():
    found = imported(
        Block("heading", "h", {"level": 1}, [Run("Sadržaj", {})]),
        line("Uvod", {**ARIAL, "size": {"pt": 15}, "strong": {}}, "a"),
        line(BODY, ARIAL, "b"),
    )
    assert tidied(found)[1] == ("heading", 1, {"font": {"family": "Arial"}, "size": {"pt": 15}})
    assert "h1" not in found.styles


def test_a_line_that_shows_as_a_heading_style_takes_it():
    h3 = styles.TEMPLATE[styles.STYLES]["h3"]
    found = imported(
        line("Cijene", {"size": {"pt": h3["size"]}, "strong": {}}, "a"),
        line("Tekst ostaje kakav jest.", {}, "b"),
    )
    assert tidied(found) == [("heading", 3, {}), ("paragraph", None, {})]
    assert found.styles == {}


def test_cells_lose_the_marks_their_style_shows_a_formula_s_too():
    grid = Grid(["r1"], ["a", "b", "c"], formulas={"r1:c": ["1+1"]})
    cells = [
        light_cell("r1:a", "Iznos", {"marks": {**ARIAL, "strong": {}}}),
        light_cell("r1:b", "", {"marks": ARIAL}),
        light_cell("r1:c", "2", {"marks": ARIAL}),
    ]
    nested = Cell("r1", "a", [line("Stavka", ARIAL, "n")])
    found = imported(
        line(BODY, ARIAL, "p"),
        Block("table", "t", grid=grid, cells=cells),
        Block("table", "u", grid=Grid(["r1"], ["a"]), cells=[nested]),
    )
    tidy(found)
    shown, inner = found.tabs[0].blocks[1].cells, found.tabs[0].blocks[2].cells
    assert [cell.blocks[0].runs[0].marks for cell in (shown[0], shown[2])] == [{"strong": {}}, {}]
    assert "endMarks" not in shown[1].blocks[0].attrs
    assert inner[0].blocks[0].runs[0].marks == {}


def test_into_a_document_its_styles_keep_their_looks_and_a_heading_its_line_s():
    document = styles.own(dict(styles.TEMPLATE[styles.THEME]), {})
    found = imported(
        line("Uvod", {**ARIAL, "size": {"pt": 16}, "strong": {}}, "a"),
        line(BODY, ARIAL, "b"),
    )
    tidy(found, document)
    assert found.styles == {}
    assert [(each.type, each.runs[0].marks) for each in found.tabs[0].blocks] == [
        ("heading", {"font": {"family": "Arial"}, "size": {"pt": 16}}),
        ("paragraph", ARIAL),
    ]


def test_a_file_of_slides_keeps_its_formatting():
    found = imported(
        line("Uvod", {**ARIAL, "size": {"pt": 16}, "strong": {}}, "a"),
        line(BODY, ARIAL, "b"),
        template={},
    )
    assert tidied(found) == [
        ("paragraph", None, {**ARIAL, "size": {"pt": 16}, "strong": {}}),
        ("paragraph", None, ARIAL),
    ]
