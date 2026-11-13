from pycrdt import Doc, Map

from apps.content import styles
from apps.content.blocks import Block, Run
from apps.content.numbering import (
    NUMBERS,
    numbered,
    numbering_of,
    numeral,
    start_of,
    styles_of,
)


def own_state(**looks) -> Doc:
    own = Doc()
    own.apply_update(styles.template())
    for id, look in looks.items():
        stored = own.get(styles.STYLES, type=Map)
        if id in stored:
            for name, value in look.items():
                stored[id][name] = value
        else:
            stored[id] = Map({**styles.TEMPLATE[styles.STYLES]["text"], **look})
    return own


NUMBERED = {
    "h1": {"numbering": "1", "suffix": "."},
    "h2": {"numbering": "1", "suffix": ".", "nested": True},
    "h3": {"numbering": "a", "suffix": ")"},
    "article": {"name": "Članak", "numbering": "1", "prefix": "Članak ", "suffix": "."},
}


def heading(level: int, text: str, **attrs) -> Block:
    return Block("heading", attrs={"level": level, **attrs}, runs=[Run(text)])


def paragraph(text: str, **attrs) -> Block:
    return Block("paragraph", attrs=attrs, runs=[Run(text)])


def labels(content: list[Block], start: dict | None = None, **looks) -> list[str]:
    numbering = {"styles": styles_of(own_state(**(looks or NUMBERED))), "start": start or {}}
    return list(numbered(content, numbering)[0].values())


def test_numerals_are_written_as_the_editor_writes_them():
    assert [numeral(count, "1") for count in (1, 2, 3)] == ["1", "2", "3"]
    assert numeral(28, "a") == "ab"
    assert numeral(3, "A") == "C"
    assert numeral(4, "i") == "iv"
    assert numeral(9, "I") == "IX"
    assert numeral(0, "a") == "0"


def test_headings_number_on_at_their_level_and_start_the_levels_below_again():
    content = [
        heading(1, "Uvod"),
        heading(2, "Cilj"),
        heading(2, "Opseg"),
        heading(3, "Iznimke"),
        heading(1, "Cijene"),
        heading(2, "Popusti"),
        heading(1, "Prilozi", restart=True),
    ]
    assert labels(content) == ["1.", "1.1.", "1.2.", "a)", "2.", "2.1.", "1."]


def test_a_numbered_style_counts_on_through_the_tab_but_never_numbers_a_list_item():
    content = [
        paragraph("Predmet", style="article"),
        paragraph("Obični tekst"),
        paragraph("Stavka", style="article", list="number"),
        heading(1, "Cijene"),
        paragraph("Plaćanje", style="article"),
    ]
    assert labels(content) == ["Članak 1.", "1.", "Članak 2."]


def test_numbers_count_on_from_the_tabs_before():
    content = [heading(2, "Cilj"), heading(1, "Cijene"), paragraph("Rok", style="article")]
    assert labels(content, {"#1": 2, "#2": 1, "article": 6}) == ["2.2.", "3.", "Članak 7."]


def test_a_style_with_nothing_valid_numbers_nothing():
    looks = {"h1": {"numbering": "x", "prefix": 7}, "h2": {"numbering": "1", "kind": None}}
    own = own_state(**looks)
    assert styles_of(own)["h1"] == {
        "kind": "h1",
        "numbering": "",
        "prefix": "",
        "suffix": "",
        "nested": False,
    }
    assert "h2" not in styles_of(own)
    assert labels([heading(1, "Uvod"), heading(2, "Cilj")], **looks) == []


def test_each_tab_starts_where_the_tabs_before_it_in_reading_order_leave_off():
    own = Doc()
    tallies = own.get(NUMBERS, type=Map)
    tallies["a"] = {"#1": {"reset": False, "count": 2}, "#2": {"reset": False, "count": 3.0}}
    tallies["b"] = {"#1": {"reset": True, "count": 1}, "#2": {"reset": True, "count": 0}}
    tallies["c"] = {"#2": {"reset": False, "count": 1}, "text": {"reset": False, "count": -1}}
    tallies["d"] = "broken"
    assert start_of(own, ["a", "b", "c", "d"], "a") == {}
    assert start_of(own, ["a", "b", "c", "d"], "b") == {"#1": 2, "#2": 3}
    assert start_of(own, ["a", "b", "c", "d", "e"], "e") == {"#1": 1, "#2": 1}
    assert start_of(own, ["c", "a", "e"], "e") == {"#1": 2, "#2": 4}


def test_a_tab_follows_only_the_counters_a_style_numbers_by():
    own = own_state(article=NUMBERED["article"])
    own.get(NUMBERS, type=Map)["a"] = {
        "#1": {"reset": False, "count": 2},
        "text": {"reset": False, "count": 9},
        "article": {"reset": False, "count": 4},
    }
    assert numbering_of(own, ["a", "b"], "b")["start"] == {"article": 4}
    own.get(styles.STYLES, type=Map)["h3"]["numbering"] = "1"
    assert numbering_of(own, ["a", "b"], "b")["start"] == {"#1": 2, "article": 4}
