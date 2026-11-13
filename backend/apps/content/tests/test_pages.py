from pycrdt import Doc, Map

from apps.content import pages, tallies
from apps.content.blocks import Block, Field, Grid, Note, Run, light_cell
from apps.content.numbering import NUMBERS, styles_of
from apps.content.sheets import Sheets

from .test_numbering import NUMBERED, heading, own_state, paragraph

PAGED = [Block("paragraph", runs=[Run("Stranica "), Field("page")])]


def test_a_tab_without_pages_of_its_own_has_the_documents():
    own, sheets = Doc(), Sheets({})
    pages.write(own, sheets, {"width": 29.7, "height": 21.0, "start": None}, {"footer": PAGED})
    setup, parts = pages.read(own, dict(sheets.tables()), "tab")
    assert setup == {**pages.DEFAULT, "width": 29.7, "height": 21.0}
    assert [block.runs for block in parts["footer"]] == [PAGED[0].runs]
    assert set(parts) == {"footer"}


def test_a_tab_with_pages_of_its_own_keeps_them_apart():
    own, sheets = Doc(), Sheets({})
    pages.write(own, sheets, {"top": 3.0}, {"header": PAGED})
    first = [Block("paragraph", runs=[Run("Prilog")])]
    pages.write(own, sheets, {"firstPage": True, "start": 1}, {"headerFirst": first}, tab="tab")
    copy = Doc()
    copy.apply_update(own.get_update())
    setup, parts = pages.read(copy, {}, "tab")
    assert setup == {**pages.DEFAULT, "firstPage": True, "start": 1}
    assert [block.text for block in parts["headerFirst"]] == ["Prilog"]
    assert set(parts) == {"headerFirst"}
    assert pages.read(copy, {})[0]["top"] == 3.0


def test_a_table_in_the_headers_of_several_tabs_is_a_table_of_its_own_in_each():
    own, sheets = Doc(), Sheets({})
    cells = [light_cell("r:c", "Ponuda br. 7")]
    table = Block("table", "t", grid=Grid(["r"], ["c"]), cells=cells)
    for tab in ("first", "second"):
        pages.write(own, sheets, {"top": 2.0}, {"header": [table]}, tab=tab)
    held = dict(sheets.tables())
    found = [pages.read(own, held, tab)[1]["header"][0] for tab in ("first", "second")]
    assert [block.cells[0].text for block in found] == ["Ponuda br. 7"] * 2
    assert len({block.id for block in found} | {"t"}) == 3 and set(held) == {
        block.id for block in found
    }


def test_a_section_keeps_what_it_sets_itself_beside_the_tabs_pages():
    own, sheets = Doc(), Sheets({})
    pages.write(own, sheets, {"top": 3.0}, {"header": PAGED})
    wide = {**pages.DEFAULT, "width": 29.7, "height": 21.0, "start": 4}
    footer = [Block("paragraph", runs=[Run("Prilog")])]
    pages.write_section(own, sheets, "tab", "b1", wide, {"footer": footer, "header": []})
    pages.write_section(own, sheets, "tab", "b2", None, {})
    copy = Doc()
    copy.apply_update(own.get_update())
    held = dict(sheets.tables())
    page, parts = pages.section(copy, held, "tab", "b1")
    assert page == wide
    assert {name: [block.text for block in part] for name, part in parts.items()} == {
        "header": [],
        "footer": ["Prilog"],
    }
    assert pages.sections(copy, held, "tab") == {"b1": (page, parts), "b2": (None, {})}
    assert (pages.section(copy, held, "tab", "elsewhere"), pages.owns(copy, "tab")) == (
        (None, {}),
        False,
    )
    assert len(pages.fragments(copy)) == len(pages.PARTS) + 2


def test_a_tab_keeps_its_tallies_as_its_editors_would():
    own = own_state(**NUMBERED)
    content = [
        heading(1, " Uvod "),
        paragraph("Tekst"),
        Block("paragraph", runs=[Run("Vidi"), Note("foot", runs=[Run("Bilješka")])]),
        heading(2, "Predmet", restart=True),
    ]
    tallies.keep(own, "tab", content, styles_of(own))
    assert own.get(tallies.HEADINGS, type=Map)["tab"] == [
        {"id": content[0].id, "level": 1, "text": "Uvod", "style": None, "restart": False},
        {"id": content[3].id, "level": 2, "text": "Predmet", "style": None, "restart": True},
    ]
    assert own.get(tallies.NOTES, type=Map)["tab"] == {"foot": 1, "end": 0}
    assert own.get(tallies.SLIDES, type=Map)["tab"] == 1
    tally = own.get(NUMBERS, type=Map)["tab"]
    assert (tally["#1"], tally["#2"]) == ({"reset": False, "count": 1}, {"reset": True, "count": 1})
