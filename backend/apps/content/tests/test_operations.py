from uuid import uuid4

import pytest
from pycrdt import Doc, XmlFragment

from apps.actions.tables import _references
from apps.content import blocks, designs, grids
from apps.content.blocks import Block, Cell, Grid, Note, Run, key_of
from apps.content.grids import FORMAT, FORMULA, TEXT
from apps.content.operations import Refused, open_tab, perform, undo, write
from apps.content.sheets import Sheets
from apps.documents.models import Node

from .helpers import Room, written


def tab(*content: Block) -> Room:
    return Room(*content)


def test_what_is_written_into_a_column_put_in_with_it_stays_and_goes_with_its_undoing():
    room = tab(Block("table", "t", grid=Grid(["r"], ["a"]), cells=[blocks.light_cell("r:a", "1")]))
    done = run(
        room,
        {"op": "lines", "table": "t", "axis": "cols", "ids": ["b"]},
        {"op": "cells", "table": "t", "cells": [{"row": "r", "col": "b", "value": "EUR"}]},
    )
    assert room.grids["t"].cell("r", "b")[grids.TEXT] == "EUR"
    room.take_back(done.change)
    assert room.grids["t"].col_ids() == ["a"]


def test_what_refers_to_a_table_is_read_while_a_change_is_writing_it():
    room = tab(
        Block(
            "table",
            "t",
            grid=Grid(["r"], ["a", "b"]),
            cells=[blocks.light_cell("r:a", "1")],
        )
    )
    run(room, {"op": "cells", "table": "t", "cells": [{"row": "r", "col": "b", "formula": "=A1"}]})
    seen: list[dict] = []

    def read(doc, sheets):
        sheets.get("t")
        seen.extend(_references(doc, sheets, "t"))
        return [{"op": "cells", "table": "t", "cells": [{"row": "r", "col": "a", "value": "2"}]}]

    room.build(read)
    assert seen


def run(room: Room, *operations: dict, locale: str = "hr"):
    return room.run(*operations, locale=locale)


def held(room: Room) -> tuple[bytes, dict]:
    return room.doc.get_state(), {id: grids.whole(laid) for id, laid in room.grids.items()}


def refused(room: Room, *operations: dict) -> Refused:
    before = held(room)
    with pytest.raises(Refused) as found:
        run(room, *operations)
    assert held(room) == before
    return found.value


def paragraph(id: str, *runs: Run | Note, **attrs) -> Block:
    return Block("paragraph", id, attrs, list(runs))


def ids(room: Room) -> list[str]:
    return [block.id for block in room.read()]


def texts(room: Room) -> dict[str, str]:
    return {block.id: block.text for block in room.read()}


def table(room: Room, id: str) -> Block:
    return next(block for block in room.read() if block.id == id)


def grid_of(room: Room, id: str) -> dict:
    laid = room.grids[id]
    return {
        "rows": laid.row_ids(),
        "cols": laid.col_ids(),
        "texts": laid.entries(TEXT),
        "formats": laid.entries(FORMAT),
        "formulas": laid.entries(FORMULA),
    }


def node(type: str, text: str = "", **attrs) -> dict:
    content = [{"type": "text", "text": text}] if text else []
    return {"type": type, "attrs": attrs, **({"content": content} if content else {})}


def test_blocks_go_where_their_address_says_and_keep_or_get_their_ids():
    room = tab(paragraph("a", Run("Prvi")), paragraph("b", Run("Drugi")))
    done = run(
        room,
        {"op": "insert", "at": {"start": "body"}, "blocks": [node("title", "Ponuda", id="t")]},
        {"op": "insert", "at": {"after": "a"}, "blocks": [node("heading", "Uvod", level=2)]},
        {"op": "insert", "at": {"end": "body"}, "blocks": [node("pageBreak")]},
    )
    made = done.made[1]["blocks"][0]
    assert ids(room) == ["t", "a", made, "b", done.made[2]["blocks"][0]]
    assert table(room, made).attrs == {"level": 2}
    assert texts(room)[made] == "Uvod"
    assert done.written.position(made, 1) is not None


def test_a_block_put_in_a_cell_takes_the_cells_text_along():
    grid = Grid(["r1"], ["c1", "c2"])
    room = tab(Block("table", "t", grid=grid, cells=[blocks.light_cell("r1:c1", "Iznos")]))
    run(
        room,
        {
            "op": "insert",
            "at": {"end": {"table": "t", "row": "r1", "col": "c1"}},
            "blocks": [node("paragraph", "u eurima")],
        },
    )
    (cell,) = table(room, "t").cells
    assert (cell.row, cell.col, cell.light) == ("r1", "c1", False)
    assert [block.text for block in cell.blocks] == ["Iznos", "u eurima"]
    assert "r1:c1" not in grid_of(room, "t")["texts"]


@pytest.mark.parametrize(
    ("operation", "code"),
    [
        (
            {"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph", align="middle")]},
            "schema",
        ),
        ({"op": "insert", "at": {"end": "body"}, "blocks": [node("sidebar")]}, "schema"),
        (
            {"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph", colour="red")]},
            "schema",
        ),
        ({"op": "insert", "at": {"end": "body"}, "blocks": [node("cell")]}, "schema"),
        ({"op": "insert", "at": {"end": "body"}, "blocks": [node("table")]}, "table_as_block"),
        ({"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph", id="a")]}, "taken"),
        ({"op": "insert", "at": {"before": "x"}, "blocks": [node("paragraph")]}, "no_block"),
        ({"op": "insert", "at": {"middle": "body"}, "blocks": [node("paragraph")]}, "invalid"),
        ({"op": "insert", "at": {"end": "body"}, "blocks": []}, "invalid"),
        ({"op": "rename"}, "unknown_operation"),
    ],
)
def test_what_the_schema_or_the_tab_does_not_allow_changes_nothing(operation, code):
    room = tab(paragraph("a", Run("Tekst")))
    assert refused(room, operation).code == code


def test_a_run_that_fails_any_operation_changes_nothing_and_says_which():
    room = tab(paragraph("a", Run("Tekst")))
    found = refused(
        room,
        {"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph", "Novo")]},
        {"op": "delete", "from": "a"},
        {"op": "set", "block": "nema", "attrs": {"align": "center"}},
    )
    assert (found.code, found.operation) == ("no_block", 2)
    assert texts(room) == {"a": "Tekst"}


def test_the_text_needs_a_block_and_a_cell_its_own():
    room = tab(
        paragraph("a", Run("Tekst")),
        Block(
            "table",
            "t",
            grid=Grid(["r"], ["c"]),
            cells=[Cell("r", "c", [Block("heading", "p", {"level": 2}, [Run("x")])])],
        ),
    )
    assert refused(room, {"op": "delete", "from": "a", "to": "t"}).code == "schema"
    assert refused(room, {"op": "delete", "from": "p"}).code == "schema"
    run(room, {"op": "delete", "from": "a"})
    assert ids(room) == ["t"]


def test_a_run_reaches_the_doc_as_one_transaction_taken_back_whole():
    room = tab(paragraph("a", Run("Tekst")))
    done = run(
        room,
        {"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph", "Novo")]},
        {"op": "set", "block": "a", "type": "heading", "attrs": {"level": 3}},
    )
    room.take_back(done.change)
    assert [(block.type, block.text) for block in room.read()] == [("paragraph", "Tekst")]
    assert run(room, {"op": "move", "from": "a", "at": {"start": "body"}}).change is None


def test_a_run_taken_back_from_the_state_stored_since_leaves_what_others_wrote():
    room = tab(
        paragraph("a", Run("Prvi")),
        paragraph("b", Run("Drugi")),
        Block("table", "t", grid=Grid(["r"], ["c"]), cells=[blocks.light_cell("r:c", "2")]),
    )
    done = run(
        room,
        {"op": "delete", "from": "a"},
        {"op": "insert", "at": {"after": "b"}, "blocks": [node("paragraph", "Novo", id="n")]},
        {"op": "mark", "range": {"block": "b"}, "mark": "strong"},
        {"op": "cells", "table": "t", "cells": [{"row": "r", "col": "c", "formula": "1+1"}]},
    )
    others = [
        {
            "op": "text",
            "range": {"block": "b", "from": 5},
            "content": [{"type": "text", "text": "!"}],
        },
        {"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph", "Tuđi", id="x")]},
    ]
    room.run(*others, origin="other")
    stored = Doc(skip_gc=True)
    stored.apply_update(room.doc.get_update())
    room.doc = stored
    room.take_back(done.change)
    assert texts(room) == {"a": "Prvi", "b": "Drugi!", "t": "", "x": "Tuđi"}
    assert ids(room) == ["a", "b", "t", "x"]
    assert table(room, "b").runs == [Run("Drugi!")]
    assert grid_of(room, "t")["texts"] == {"r:c": "2"}
    assert "r:c" not in grid_of(room, "t")["formulas"]


def test_a_run_is_taken_back_once_and_its_undo_taken_back_does_it_again():
    room = tab(paragraph("a", Run("Prvi")))
    done = run(room, {"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph", "Novo")]})
    undone = room.take_back(done.change)
    assert texts(room) == {"a": "Prvi"}
    with pytest.raises(Refused) as found:
        room.take_back(done.change)
    assert found.value.code == "undone"
    room.take_back(undone)
    assert list(texts(room).values()) == ["Prvi", "Novo"]


def test_a_block_takes_another_type_with_its_text_marks_and_notes():
    note = Note("foot", "n1", [Run("izvor")])
    room = tab(
        paragraph(
            "a", Run("Važno", {"strong": {}}), note, Run(" je"), list="bullet", align="center"
        )
    )
    run(room, {"op": "set", "block": "a", "type": "heading", "attrs": {"level": 2, "align": None}})
    (block,) = room.read()
    assert (block.type, block.id, block.attrs) == ("heading", "a", {"level": 2})
    assert block.runs == [Run("Važno", {"strong": {}}), note, Run(" je")]


@pytest.mark.parametrize(
    ("operation", "code"),
    [
        ({"op": "set", "block": "a", "attrs": {"level": 2}}, "attribute"),
        ({"op": "set", "block": "a", "attrs": {"id": "b"}}, "attribute"),
        ({"op": "set", "block": "a", "attrs": {"indent": 11}}, "schema"),
        ({"op": "set", "block": "t", "type": "paragraph"}, "retype"),
        ({"op": "grid", "table": "t", "name": "Cijene"}, "name_taken"),
        ({"op": "grid", "table": "t", "name": "a:b"}, "invalid"),
        ({"op": "set", "block": "a", "type": "table"}, "invalid"),
    ],
)
def test_a_blocks_attributes_are_its_types_and_the_values_the_schema_allows(operation, code):
    room = tab(
        paragraph("a", Run("Tekst")),
        Block("table", "t", grid=Grid(["r"], ["c"])),
        Block("table", "u", {"name": "Cijene"}, grid=Grid(["r"], ["c"])),
    )
    assert refused(room, operation).code == code


def test_rows_are_hidden_and_shown_again_by_their_ends_and_columns_by_the_grid():
    room = tab(Block("table", "t", grid=Grid(["r1", "r2", "r3", "r4"], ["a", "b"])))
    hide = {"op": "lines", "table": "t", "axis": "rows", "hidden": True}
    run(room, hide | {"from": "r2", "to": "r3"})
    run(room, {"op": "grid", "table": "t", "hidden": {"cols": {"b": True}}})
    assert table(room, "t").attrs["hidden"] == {"rows": ["r2", "r3"], "cols": ["b"]}
    run(room, {"op": "grid", "table": "t", "hidden": {"cols": {"b": False}}})
    shown = run(room, hide | {"from": "r4", "to": "r1", "hidden": False})
    assert "hidden" not in table(room, "t").attrs
    for wrong, code in [
        ({"from": "r1", "to": "x"}, "no_row"),
        ({"from": "r1", "hidden": "da"}, "invalid"),
        ({"from": "r1", "to": "r2", "remove": True}, "invalid"),
    ]:
        assert refused(room, hide | wrong).code == code
    unknown = {"op": "grid", "table": "t", "hidden": {"cols": {"x": True}}}
    assert refused(room, unknown).code == "no_col"
    room.take_back(shown.change)
    assert table(room, "t").attrs["hidden"] == {"rows": ["r2", "r3"]}


def test_a_table_referred_to_keeps_its_name_and_one_no_longer_referred_to_gives_it_up():
    pointed = {"table": "t", "from": {"row": "r", "col": "c"}}
    room = tab(
        Block("table", "t", {"name": "Cijene"}, grid=Grid(["r"], ["c"])),
        Block("table", "s", grid=Grid(["r"], ["c"], formulas={"r:c": ["2*", pointed]})),
    )
    assert refused(room, {"op": "grid", "table": "t", "name": ""}).code == "name_needed"
    run(room, {"op": "cells", "table": "s", "cells": [{"row": "r", "col": "c", "value": "1"}]})
    room.names["n"] = {"name": "Iznos", "pieces": [pointed]}
    assert refused(room, {"op": "grid", "table": "t", "name": ""}).code == "name_needed"
    del room.names["n"]
    run(room, {"op": "grid", "table": "t", "name": ""})
    assert table(room, "t").attrs.get("name") is None


def test_rows_are_frozen_down_to_one_of_the_tables_and_freed():
    room = tab(Block("table", "t", {}, grid=Grid(["r1", "r2", "r3"], ["c"])))
    run(room, {"op": "grid", "table": "t", "frozen": "r2"})
    assert room.grids["t"].frozen == "r2" and table(room, "t").attrs["frozen"] == "r2"
    assert refused(room, {"op": "grid", "table": "t", "frozen": "r9"}).code == "no_row"
    run(room, {"op": "grid", "table": "t", "frozen": None})
    assert room.grids["t"].frozen is None and "frozen" not in table(room, "t").attrs


def test_a_mark_goes_on_a_range_across_a_note_and_comes_off():
    room = tab(
        paragraph("a", Run("Ugovor"), Note("foot", "n1", [Run("bilješka")]), Run(" o najmu"))
    )
    run(room, {"op": "mark", "range": {"block": "a", "from": 2, "to": 9}, "mark": "strong"})
    found = [(run.text, run.marks) for run in room.read()[0].runs if isinstance(run, Run)]
    assert found == [("Ug", {}), ("ovor", {"strong": {}}), (" o ", {"strong": {}}), ("najmu", {})]
    run(room, {"op": "mark", "range": {"block": "a"}, "mark": "strong", "remove": True})
    run(room, {"op": "mark", "range": {"block": "n1"}, "mark": "em"})
    (block,) = room.read()
    assert [(run.text, run.marks) for run in block.runs if isinstance(run, Run)] == [
        ("Ugovor", {}),
        (" o najmu", {}),
    ]
    assert block.notes[0].runs == [Run("bilješka", {"em": {}})]


def test_a_mark_takes_off_the_marks_it_excludes_and_its_attributes_are_checked():
    room = tab(paragraph("a", Run("H2O", {"sup": {}})))
    run(room, {"op": "mark", "range": {"block": "a", "from": 1, "to": 2}, "mark": "sub"})
    marks = [(run.text, run.marks) for run in room.read()[0].runs]
    assert marks == [("H", {"sup": {}}), ("2", {"sub": {}}), ("O", {"sup": {}})]
    run(room, {"op": "mark", "range": {"block": "a"}, "mark": "size", "attrs": {"pt": 14}})
    assert all(run.marks.get("size") == {"pt": 14} for run in room.read()[0].runs)
    assert refused(room, {"op": "mark", "range": {"block": "a"}, "mark": "link"}).code == "schema"
    for attrs in ({"pt": 0}, {"size": 13}):
        given = {"op": "mark", "range": {"block": "a"}, "mark": "size", "attrs": attrs}
        assert refused(room, given).code == "invalid"
    given = {"op": "mark", "range": {"block": "a"}, "mark": "strong", "attrs": {"pt": 3}}
    assert refused(room, given).code == "invalid"
    assert (
        refused(room, {"op": "mark", "range": {"block": "a", "to": 4}, "mark": "em"}).code
        == "range"
    )


def test_ranges_are_counted_in_the_text_as_the_run_found_it_in_characters_not_bytes():
    room = tab(paragraph("a", Run("Čišćenje "), Run("žutih", {"em": {}}), Run(" 🍋 limuna")))
    strong = [{"type": "strong"}]
    run(
        room,
        {
            "op": "text",
            "range": {"block": "a", "from": 9, "to": 14},
            "content": [{"type": "text", "text": "zelenih", "marks": strong}],
        },
        {"op": "text", "range": {"block": "a", "from": 15, "to": 17}, "content": []},
        {"op": "mark", "range": {"block": "a", "from": 0, "to": 8}, "mark": "em"},
    )
    found = [(run.text, run.marks) for run in room.read()[0].runs]
    assert found == [
        ("Čišćenje", {"em": {}}),
        (" ", {}),
        ("zelenih", {"strong": {}}),
        (" limuna", {}),
    ]
    again = {"op": "text", "range": {"block": "a", "from": 1, "to": 3}, "content": []}
    overlapping = {"op": "mark", "range": {"block": "a", "from": 2, "to": 5}, "mark": "em"}
    assert refused(room, again, overlapping).code == "overlap"


def test_a_range_is_given_by_its_words_at_their_first_occurrence_or_the_one_counted():
    room = tab(
        paragraph("a", Run("Rok je 30 dana, "), Note("foot", "n", [Run("x")]), Run("30 dana"))
    )
    run(
        room,
        {"op": "mark", "range": {"block": "a", "words": "30 dana", "occurrence": 2}, "mark": "em"},
        {
            "op": "text",
            "range": {"block": "a", "words": "30"},
            "content": [{"type": "text", "text": "45"}],
        },
    )
    found = [(run.text, run.marks) for run in room.read()[0].runs if isinstance(run, Run)]
    assert found == [("Rok je 45 dana, ", {}), ("30 dana", {"em": {}})]
    missing = {"op": "mark", "range": {"block": "a", "words": "60 dana"}, "mark": "em"}
    assert (refused(room, missing).code, refused(room, missing).detail) == ("no_words", "60 dana")
    third = {"op": "mark", "range": {"block": "a", "words": "dana", "occurrence": 3}, "mark": "em"}
    assert refused(room, third).code == "no_words"
    for given in ({"words": "Rok", "from": 0}, {"occurrence": 1}):
        both = {"op": "mark", "range": {"block": "a", **given}, "mark": "em"}
        assert refused(room, both).code == "invalid"


def test_a_proposal_is_carried_with_the_text_but_never_set_or_marked():
    room = tab(paragraph("a", Run("Uvod")))
    proposal = {"id": "p", "author": "Ana Horvat", "date": "2026-10-19T10:00:00Z"}
    marked = {"type": "text", "text": "Novo", "marks": [{"type": "insertion", "attrs": proposal}]}
    noted = {"type": "footnote", "attrs": {"id": "f", "insertion": proposal}, "content": [marked]}
    run(
        room,
        {
            "op": "insert",
            "at": {"after": "a"},
            "blocks": [{"type": "paragraph", "attrs": {"id": "b"}, "content": [marked, noted]}],
        },
    )
    carried = room.read()[1]
    assert carried.runs[0].marks == {"insertion": proposal}
    assert carried.runs[1].proposed == {"insertion": proposal}
    for operation in [
        {"op": "set", "block": "a", "attrs": {"deletion": proposal}},
        {"op": "set", "block": "a", "attrs": {"deletion": None}},
        {"op": "mark", "range": {"block": "a"}, "mark": "formatting", "attrs": proposal},
    ]:
        assert refused(room, operation).code == "invalid", operation


def test_text_goes_into_an_empty_block():
    room = tab(paragraph("a"))
    run(
        room, {"op": "text", "range": {"block": "a"}, "content": [{"type": "text", "text": "Prvo"}]}
    )
    assert texts(room) == {"a": "Prvo"}


def test_a_table_comes_from_rows_of_values_typed_as_the_documents_language_types_them():
    room = tab(paragraph("a", Run("Cijene")))
    done = run(
        room,
        {
            "op": "table",
            "at": {"after": "a"},
            "name": "Cijene",
            "widths": [3, None],
            "rows": [
                ["Artikl", "Cijena"],
                ["Kava", 1234.5],
                ["Čaj", {"value": 2, "format": "0.00"}],
                ["Ukupno", {"formula": "=SUM(B2:B3)"}],
            ],
        },
    )
    made = done.made[0]
    rows, cols = made["rows"], made["cols"]
    grid = grid_of(room, made["table"])
    assert grid["rows"] == rows and grid["cols"] == cols
    assert grid["texts"] == {
        key_of(rows[0], cols[0]): "Artikl",
        key_of(rows[0], cols[1]): "Cijena",
        key_of(rows[1], cols[0]): "Kava",
        key_of(rows[1], cols[1]): "1234,5",
        key_of(rows[2], cols[0]): "Čaj",
        key_of(rows[2], cols[1]): "2",
        key_of(rows[3], cols[0]): "Ukupno",
    }
    assert grid["formats"] == {key_of(rows[2], cols[1]): "0.00"}
    assert grid["formulas"] == {
        key_of(rows[3], cols[1]): [
            "SUM(",
            {"from": {"row": rows[1], "col": "@"}, "to": {"row": rows[2], "col": "@"}},
            ")",
        ]
    }
    placed = table(room, made["table"])
    assert placed.attrs == {
        "name": "Cijene",
        "widths": {cols[0]: 3},
        "designs": [designs.ours(designs.NEW)],
    }
    assert ids(room) == ["a", made["table"]]


def test_a_table_keeps_the_ids_given_for_its_lines_as_many_as_it_has():
    room = tab(paragraph("a"))
    done = run(
        room,
        {
            "op": "table",
            "at": {"after": "a"},
            "rowIds": ["r1", "r2"],
            "colIds": ["c1"],
            "rows": [["Kava"], ["Čaj"]],
        },
    )
    grid = grid_of(room, done.made[0]["table"])
    assert grid["rows"] == ["r1", "r2"] and grid["cols"] == ["c1"]
    assert grid["texts"] == {"r1:c1": "Kava", "r2:c1": "Čaj"}
    fewer = {"op": "table", "at": {"after": "a"}, "rowIds": ["r1"], "rows": [["1"], ["2"]]}
    assert refused(room, fewer).code == "lines"


def test_a_formula_refers_to_another_table_by_its_name_and_within_it_only():
    room = tab(Block("table", "t", {"name": "Tečaj"}, grid=Grid(["r1", "r2"], ["c"])))
    done = run(
        room,
        {"op": "table", "at": {"end": "body"}, "rows": [[{"formula": "'tečaj'!$A$2*2"}]]},
    )
    made = done.made[0]
    key = key_of(made["rows"][0], made["cols"][0])
    assert grid_of(room, made["table"])["formulas"][key] == [
        {"table": "t", "from": {"row": "r2", "absRow": True, "col": "c", "absCol": True}},
        "*2",
    ]
    for formula, code in (("Tečaj!A3", "outside"), ("B1+1", "outside"), ("Kamate!A1", "no_table")):
        operation = {"op": "table", "at": {"end": "body"}, "rows": [[{"formula": formula}]]}
        assert refused(room, operation).code == code


def test_a_moved_formula_moves_its_relative_references_and_outside_its_table_is_missing():
    room = tab(Block("table", "t", grid=Grid(["r1", "r2", "r3"], ["a", "b"])))
    moved = {"row": "r3", "col": "b", "formula": "A1+$A$1+A$2", "by": {"rows": 1, "cols": 1}}
    above = {"row": "r1", "col": "a", "formula": "SUM(A1:A2)*2", "by": {"rows": -1}}
    run(room, {"op": "cells", "table": "t", "cells": [moved, above]})
    formulas = grid_of(room, "t")["formulas"]
    assert formulas[key_of("r3", "b")] == [
        {"from": {"row": "r2", "col": "@"}},
        "+",
        {"from": {"row": "r1", "absRow": True, "col": "a", "absCol": True}},
        "+",
        {"from": {"row": "r2", "absRow": True, "col": "@"}},
    ]
    assert formulas[key_of("r1", "a")] == ["SUM(#REF!)*2"]
    value = {"row": "r1", "col": "a", "value": 1, "by": {"rows": 1}}
    assert refused(room, {"op": "cells", "table": "t", "cells": [value]}).code == "invalid"


def test_a_copy_of_a_table_stands_after_it_under_a_name_of_its_own_with_its_formulas_or_values():
    doubled = ["SUM(", {"from": {"row": "r1", "col": "a"}}, ")*2"]
    priced = Block(
        "table",
        "t",
        {"name": "Cijene"},
        grid=Grid(["r1", "r2"], ["a"], formulas={key_of("r2", "a"): doubled}),
        cells=[
            blocks.light_cell(key_of("r1", "a"), "3"),
            Cell("r2", "a", [paragraph("p", Run("Prvi")), paragraph("q", Run("Drugi"))]),
        ],
    )
    room = tab(priced, paragraph("kraj"))
    copied = run(room, {"op": "copy", "table": "t"}).made[0]
    assert copied["name"] == "Cijene (2)"
    assert ids(room) == ["t", copied["table"], "kraj"]
    copy = grid_of(room, copied["table"])
    assert (copy["rows"], copy["cols"]) == (["r1", "r2"], ["a"])
    assert copy["formulas"] == {key_of("r2", "a"): grids.formula_at(doubled, "r2", "a")}
    assert copy["texts"] == {key_of("r1", "a"): "3"}
    [cell] = [cell for cell in table(room, copied["table"]).cells if cell.row == "r2"]
    assert cell.text == "Prvi\nDrugi" and {block.id for block in cell.blocks}.isdisjoint("pq")
    room.calculated("t", "r1", {"a": 3.0})
    room.calculated("t", "r2", {"a": 6.0})
    valued = run(room, {"op": "copy", "table": "t", "values": True, "name": "Iznosi"}).made[0]
    assert grid_of(room, valued["table"])["formulas"] == {}
    assert grid_of(room, valued["table"])["texts"] == {
        key_of("r1", "a"): "3",
        key_of("r2", "a"): "6",
    }
    assert run(room, {"op": "copy", "table": "t"}).made[0]["name"] == "Cijene (3)"
    assert refused(room, {"op": "copy", "table": "t", "name": "iznosi"}).code == "name_taken"


def test_a_copy_taken_back_is_gone_and_done_again_stands_as_it_was():
    room = tab(
        Block(
            "table",
            "t",
            attrs={"name": "Cijene"},
            grid=Grid(["r1", "r2"], ["a"]),
            cells=[blocks.light_cell(key_of("r1", "a"), "3")],
        ),
        paragraph("kraj"),
    )
    done = run(room, {"op": "copy", "table": "t", "name": "Kopija"})
    new = done.made[0]["table"]
    assert grid_of(room, new)["texts"] == {key_of("r1", "a"): "3"}
    undone = room.take_back(done.change)
    assert new not in room.grids and ids(room) == ["t", "kraj"]
    room.take_back(undone)
    assert grid_of(room, new)["texts"] == {key_of("r1", "a"): "3"}
    assert ids(room) == ["t", new, "kraj"]


def test_a_table_changed_in_the_run_is_not_copied_from_what_is_not_stored_yet():
    room = tab(Block("table", "t", grid=Grid(["r"], ["a"])))
    if room.document is None:
        pytest.skip("a grid held whole copies as the change left it")
    wrote = {"op": "cells", "table": "t", "cells": [{"row": "r", "col": "a", "value": "1"}]}
    assert refused(room, wrote, {"op": "copy", "table": "t"}).code == "copy_of_changed"


def test_a_merged_cell_spans_the_slots_it_covers():
    room = tab(paragraph("a"))
    done = run(
        room,
        {
            "op": "table",
            "at": {"end": "body"},
            "rows": [[{"value": "Naslov", "span": {"cols": 2}}, None], ["a", "b"]],
        },
    )
    made = done.made[0]
    rows, cols = made["rows"], made["cols"]
    merged = next(cell for cell in table(room, made["table"]).cells if cell.to)
    assert (merged.row, merged.col, merged.to, merged.text) == (
        rows[0],
        cols[0],
        key_of(rows[0], cols[1]),
        "Naslov",
    )
    covered = {
        "op": "table",
        "at": {"end": "body"},
        "rows": [[{"value": 1, "span": {"rows": 2}}], ["x"]],
    }
    assert refused(room, covered).code == "covered"
    beyond = {"op": "table", "at": {"end": "body"}, "rows": [[{"value": 1, "span": {"cols": 2}}]]}
    assert refused(room, beyond).code == "span"
    assert (
        refused(room, {"op": "table", "at": {"end": "body"}, "rows": [["=1+1"]]}).code
        == "formula_as_value"
    )


def test_a_cell_merged_over_its_neighbours_takes_their_place_and_splits_back_to_its_own():
    heading = Cell("r2", "a", [Block("heading", "h", {"level": 2}, [Run("Ispod")])])
    cells = [blocks.light_cell("r1:b", "Desno"), heading]
    room = tab(Block("table", "t", grid=Grid(["r1", "r2", "r3"], ["a", "b"]), cells=cells))
    grid = room.grids["t"]
    grid.row("r1").cells["b"][FORMAT] = "0.00"
    merge = {"row": "r1", "col": "a", "value": "Zbroj", "span": {"rows": 2, "cols": 2}}
    run(room, {"op": "cells", "table": "t", "cells": [merge]})
    [merged] = table(room, "t").cells
    assert (merged.row, merged.col, merged.to, merged.text) == ("r1", "a", "r2:b", "Zbroj")
    assert room.grids["t"].row("r1").cells == {"a": {TEXT: "Zbroj", "to": "r2:b"}}
    assert room.grids["t"].row("r2").cells == {}
    under = {"op": "cells", "table": "t", "cells": [{"row": "r2", "col": "b", "value": 1}]}
    assert refused(room, under).code == "covered"
    over = {"row": "r3", "col": "a", "span": {"rows": 1, "cols": 2}}
    run(room, {"op": "cells", "table": "t", "cells": [over]})
    into = {"row": "r3", "col": "b", "span": {"rows": 1, "cols": 1}}
    assert refused(room, {"op": "cells", "table": "t", "cells": [into]}).code == "covered"
    across = {"row": "r1", "col": "a", "span": {"rows": 3}}
    assert refused(room, {"op": "cells", "table": "t", "cells": [across]}).code == "span"
    beyond = {"row": "r3", "col": "a", "span": {"rows": 2}}
    assert refused(room, {"op": "cells", "table": "t", "cells": [beyond]}).code == "span"

    split = {"row": "r1", "col": "a", "span": {"rows": 1, "cols": 1}}
    run(room, {"op": "cells", "table": "t", "cells": [split]})
    assert room.grids["t"].row("r1").cells == {"a": {TEXT: "Zbroj"}}
    run(room, {"op": "cells", "table": "t", "cells": [{"row": "r2", "col": "b", "value": 2}]})
    assert grid_of(room, "t")["texts"]["r2:b"] == "2"


def test_cells_take_values_formulas_formats_and_blocks_keeping_a_cells_look():
    bold = paragraph("p", Run("7", {"strong": {}}), align="right")
    grid = Grid(["r1", "r2"], ["c1", "c2"])
    room = tab(
        Block(
            "table",
            "t",
            grid=grid,
            cells=[
                Cell("r1", "c1", [bold]),
                blocks.light_cell("r2:c1", "staro"),
                Cell("r1", "c2", [paragraph("q")], to="r2:c2"),
            ],
        )
    )
    run(
        room,
        {
            "op": "cells",
            "table": "t",
            "cells": [
                {"row": "r1", "col": "c1", "value": 12.5, "format": "0.0"},
                {"row": "r2", "col": "c1", "formula": "A1*2"},
            ],
        },
    )
    found = {key_of(cell.row, cell.col): cell for cell in table(room, "t").cells}
    (kept,) = found["r1:c1"].blocks
    assert (found["r1:c1"].light, kept.attrs, kept.runs) == (
        True,
        {"align": "right"},
        [Run("12,5", {"strong": {}})],
    )
    stored = grid_of(room, "t")
    assert stored["formats"] == {"r1:c1": "0.0"}
    assert stored["formulas"] == {"r2:c1": [{"from": {"row": "r1", "col": "@"}}, "*2"]}
    assert "r2:c1" not in stored["texts"]
    run(
        room,
        {
            "op": "cells",
            "table": "t",
            "cells": [
                {"row": "r1", "col": "c1", "format": None, "blocks": [node("heading", "Zbroj")]}
            ],
        },
    )
    found = {key_of(cell.row, cell.col): cell for cell in table(room, "t").cells}
    assert [(block.type, block.text) for block in found["r1:c1"].blocks] == [("heading", "Zbroj")]
    assert grid_of(room, "t")["formats"] == {}
    covered = {"op": "cells", "table": "t", "cells": [{"row": "r2", "col": "c2", "value": 1}]}
    assert refused(room, covered).code == "covered"
    both = {
        "op": "cells",
        "table": "t",
        "cells": [{"row": "r1", "col": "c1", "value": 1, "formula": "2"}],
    }
    assert refused(room, both).code == "contents"
    gone = {"op": "cells", "table": "t", "cells": [{"row": "r9", "col": "c1", "value": 1}]}
    assert refused(room, gone).code == "no_cell"


def test_what_is_entered_in_a_cell_takes_the_format_excel_gives_it_unless_the_cells_stays():
    room = tab(Block("table", "t", grid=Grid(["r1", "r2", "r3", "r4"], ["c1", "c2"]), cells=[]))

    def entered(locale="hr", col="c1", **rows):
        cells = [{"row": row, "col": col, **content} for row, content in rows.items()]
        return run(room, {"op": "cells", "table": "t", "cells": cells}, locale=locale)

    done = entered(
        r1={"value": "1.250,5"}, r2={"value": "12 €"}, r3={"value": "'1.2.2026"}, r4={"value": 1.5}
    )
    croatian = {"r1:c1": "#,##0.00", "r2:c1": '#,##0\\ "€";[Red]\\-#,##0\\ "€"'}
    assert grid_of(room, "t")["formats"] == croatian
    room.take_back(done.change)
    assert grid_of(room, "t")["formats"] == {}
    entered(r1={"value": "1.2.2026"}, r2={"value": "12%", "format": "0.0"}, r3={"value": "Kava"})
    entered(
        "en",
        r1={"value": "12%"},
        r2={"value": "2/1/2026"},
        r3={"value": "9:05 PM"},
        r4={"value": "$12.50"},
    )
    dollars = '"$"#,##0.00_);[Red]\\("$"#,##0.00\\)'
    formats = {"r1:c1": "0%", "r2:c1": "0.0", "r3:c1": "h:mm AM/PM", "r4:c1": dollars}
    assert grid_of(room, "t")["formats"] == formats
    entered(
        "en",
        "c2",
        r1={"formula": "A4+A1"},
        r2={"formula": "SUM(A3)"},
        r3={"formula": "PMT(0.05/12,60,10000)"},
        r4={"formula": "A4*2"},
    )
    formats |= {"r1:c2": dollars, "r2:c2": "h:mm AM/PM", "r3:c2": dollars}
    assert grid_of(room, "t")["formats"] == formats
    entered(r1={"format": "@"})
    entered(r1={"value": "1250"}, r3={"value": "1250"})
    stored = grid_of(room, "t")
    assert stored["formats"] == formats | {"r1:c1": "@"}
    assert (stored["texts"]["r1:c1"], stored["texts"]["r3:c1"]) == ("'1250", "1250")
    entered(r1={"formula": "A3*2"})
    stored = grid_of(room, "t")
    assert "r1:c1" in stored["formulas"] and stored["formats"]["r1:c1"] == "@"


def test_whole_lines_are_formatted_and_so_are_the_cells_in_them_showing_another_look():
    grid = Grid(["r1", "r2", "r3"], ["c1", "c2"], row_looks={"r3": {"marks": {"em": {}}}})
    cells = [
        blocks.light_cell("r1:c1", "plain"),
        blocks.light_cell("r2:c1", "own", {"attrs": {"align": "right"}}),
        Cell("r1", "c2", [paragraph("p", Run("čvor"))]),
        Cell("r2", "c2", [paragraph("q", Run("a")), paragraph("e")]),
    ]
    room = tab(Block("table", "t", grid=grid, cells=cells))
    bold = {"op": "looks", "table": "t", "axis": "cols", "from": "c2", "to": "c1"}
    done = run(room, {**bold, "marks": {"strong": {}}})
    laid = room.grids["t"]
    assert [col.look for col in laid.cols] == [{"marks": {"strong": {}}}] * 2
    assert "look" not in laid.cell("r1", "c1")
    assert laid.cell("r2", "c1")["look"] == {"marks": {"strong": {}}, "attrs": {"align": "right"}}
    assert laid.look_at("r3", "c2") == {"marks": {"em": {}, "strong": {}}}
    found = {key_of(cell.row, cell.col): cell for cell in table(room, "t").cells}
    assert found["r1:c2"].blocks[0].runs == [Run("čvor", {"strong": {}})]
    assert found["r2:c2"].blocks[1].attrs == {"endMarks": {"strong": {}}}

    centred = {"op": "looks", "table": "t", "axis": "rows", "from": "r1", "to": "r1"}
    run(room, {**centred, "marks": {"strong": None}, "attrs": {"align": "center"}})
    laid = room.grids["t"]
    assert laid.row("r1").look == {"attrs": {"align": "center"}}
    assert "look" not in laid.cell("r1", "c1")
    found = {key_of(cell.row, cell.col): cell for cell in table(room, "t").cells}
    (kept,) = found["r1:c2"].blocks
    assert (kept.attrs, kept.runs) == ({"align": "center"}, [Run("čvor")])

    room.take_back(done.change)
    laid = room.grids["t"]
    assert [col.look for col in laid.cols] == [None, None]
    assert laid.cell("r2", "c1")["look"] == {"attrs": {"align": "right"}}
    assert "look" not in laid.cell("r3", "c2")
    assert refused(room, {**bold, "to": "c9"}).code == "no_col"
    assert refused(room, {**centred, "from": "r9"}).code == "no_row"


def test_a_cell_is_filled_in_its_look_or_on_its_node_and_keeps_it_while_written_in():
    grid = Grid(["r1", "r2"], ["c1", "c2"], row_looks={"r2": {"fill": "#d9e2f3"}})
    cells = [
        blocks.light_cell("r1:c1", "svijetla"),
        Cell("r1", "c2", [paragraph("p", Run("a")), paragraph("q")]),
    ]
    room = tab(Block("table", "t", grid=grid, cells=cells))
    filled = [
        {"row": "r1", "col": "c1", "fill": "yellow"},
        {"row": "r1", "col": "c2", "fill": "#ff0000"},
    ]
    run(room, {"op": "cells", "table": "t", "cells": filled})
    laid = room.grids["t"]
    assert laid.cell("r1", "c1") == {"text": "svijetla", "look": {"fill": "yellow"}}
    found = {key_of(cell.row, cell.col): cell for cell in table(room, "t").cells}
    assert (found["r1:c1"].fill, found["r1:c2"].fill) == ("yellow", "#ff0000")

    written = [
        {"row": "r1", "col": "c1", "value": "nova"},
        {"row": "r2", "col": "c1", "value": "x"},
    ]
    run(room, {"op": "cells", "table": "t", "cells": written})
    laid = room.grids["t"]
    assert laid.cell("r1", "c1")["look"] == {"fill": "yellow"}
    assert laid.look_at("r2", "c1") == {"fill": "#d9e2f3"}
    unfilled = [{"row": "r2", "col": "c1", "fill": None}]
    run(room, {"op": "cells", "table": "t", "cells": unfilled})
    assert room.grids["t"].cell("r2", "c1")["look"] == {}

    bold = {"op": "looks", "table": "t", "axis": "rows", "from": "r1", "to": "r1"}
    bold["marks"] = {"strong": {}}
    run(room, bold)
    assert room.grids["t"].cell("r1", "c1")["look"] == {"marks": {"strong": {}}, "fill": "yellow"}
    unfill = {"op": "looks", "table": "t", "axis": "cols", "from": "c2", "to": "c2"}
    done = run(room, {**unfill, "fill": None})
    assert room.grids["t"].col("c2").look is None
    found = {key_of(cell.row, cell.col): cell for cell in table(room, "t").cells}
    assert found["r1:c2"].fill is None
    assert refused(room, {"op": "cells", "table": "t", "cells": [{**filled[0], "fill": "Red"}]})

    room.take_back(done.change)
    found = {key_of(cell.row, cell.col): cell for cell in table(room, "t").cells}
    assert found["r1:c2"].fill == "#ff0000"


def test_a_cells_blocks_keep_their_ids_where_written_again_and_take_no_others():
    cells = [Cell("r", "c", [Block("heading", "p", {"level": 2}, [Run("1")])])]
    room = tab(Block("table", "t", grid=Grid(["r"], ["c"]), cells=cells), paragraph("a"))

    def written(id: str) -> dict:
        given = [{"row": "r", "col": "c", "blocks": [node("heading", "2", id=id, level=2)]}]
        return {"op": "cells", "table": "t", "cells": given}

    run(room, written("p"))
    (cell,) = table(room, "t").cells
    assert [(block.id, block.text) for block in cell.blocks] == [("p", "2")]
    assert refused(room, written("a")).code == "taken"
    assert refused(room, written("t")).code == "taken"


def test_content_is_written_checked_as_a_run_is_and_a_refused_write_changes_nothing():
    room = tab(paragraph("a", Run("Tekst")))
    heading = Block("heading", "a", {"level": 2})
    taken = Block("table", "t", grid=Grid(["r"], ["c"]), cells=[Cell("r", "c", [heading])])
    for content, code in [
        ([paragraph("n"), paragraph("n")], "taken"),
        ([paragraph("a")], "taken"),
        ([taken, paragraph("z")], "taken"),
        ([Block("sidebar", "s")], "schema"),
        ([paragraph("p", align="middle")], "schema"),
    ]:
        before = held(room)
        with pytest.raises(Refused) as found:
            room.doc.apply_update(write(room.doc, Sheets(room.grids), content).update)
        assert (found.value.code, held(room)) == (code, before)

    def header(own: Doc) -> XmlFragment:
        return own.get("header", type=XmlFragment)

    written([paragraph("h", Run("Zaglavlje"))], room.doc, into=header)
    found = blocks.read(room.doc, room.grids, header(room.doc))
    assert [block.text for block in found] == ["Zaglavlje"]
    assert ids(room) == ["a"]


def test_lines_go_in_before_a_line_or_at_the_end():
    room = tab(Block("table", "t", grid=Grid(["r1", "r2"], ["c1"])))
    run(
        room,
        {"op": "lines", "table": "t", "axis": "rows", "ids": ["n1", "n2"], "before": "r2"},
        {"op": "lines", "table": "t", "axis": "cols", "ids": ["c2"]},
        {"op": "cells", "table": "t", "cells": [{"row": "n2", "col": "c2", "value": "novo"}]},
    )
    stored = grid_of(room, "t")
    assert (stored["rows"], stored["cols"]) == (["r1", "n1", "n2", "r2"], ["c1", "c2"])
    assert stored["texts"] == {"n2:c2": "novo"}
    taken = {"op": "lines", "table": "t", "axis": "rows", "ids": ["r1"]}
    assert refused(room, taken).code == "taken"
    assert refused(room, {**taken, "ids": ["n9"], "from": "r1"}).code == "invalid"


def test_a_row_put_into_a_calculated_column_takes_the_formula_its_neighbours_share():
    room = tab(Block("table", "t", grid=Grid(["r1", "r2", "r3", "r4"], ["a", "b", "c"])))
    cells = [
        {"row": f"r{y}", "col": "c", "formula": f"A{y}*B{y}", "format": "0.00"} for y in (2, 3)
    ]
    run(
        room,
        {
            "op": "cells",
            "table": "t",
            "cells": [{"row": "r4", "col": "c", "formula": "SUM(C2:C3)"}],
        },
        {"op": "cells", "table": "t", "cells": cells},
        {"op": "lines", "table": "t", "axis": "rows", "ids": ["n1"], "before": "r3"},
        {"op": "lines", "table": "t", "axis": "rows", "ids": ["n0"], "before": "r2"},
        {"op": "lines", "table": "t", "axis": "rows", "ids": ["n2"], "before": "r4"},
        {"op": "lines", "table": "t", "axis": "rows", "ids": ["n3"]},
        {"op": "lines", "table": "t", "axis": "cols", "ids": ["d"]},
    )
    stored = grid_of(room, "t")
    assert stored["rows"] == ["r1", "n0", "r2", "n1", "r3", "n2", "r4", "n3"]
    shared = stored["formulas"]["r2:c"]
    assert {key: held for key, held in stored["formulas"].items() if held == shared} == {
        f"{row}:c": shared for row in ("n0", "r2", "n1", "r3", "n2")
    }
    assert "n3:c" not in stored["formulas"]
    assert stored["formats"] == {f"{row}:c": "0.00" for row in ("n0", "r2", "n1", "r3", "n2")}


def test_lines_taken_out_keep_merged_cells_ranges_names_and_charts_on_the_lines_left():
    over = {"from": {"row": "r1", "col": "b"}, "to": {"row": "r3", "col": "b"}}
    grid = Grid(
        ["r1", "r2", "r3", "r4"],
        ["a", "b"],
        formulas={"r4:b": ["SUM(", over, ")"]},
        formats={"r1:a": "0%", "r2:b": "0.00", "r3:b": "0.00"},
    )
    cells = [
        Cell("r1", "a", [paragraph("m", Run("Spojeno"))], to="r2:a"),
        Cell("r3", "b", [paragraph("e", Run("3"))]),
        blocks.light_cell("r2:b", "2"),
        blocks.light_cell("r3:a", "x"),
        blocks.light_cell("r4:a", "y"),
    ]
    other = {"s1:a": ["SUM(", {"table": "t", **over}, ")+", {"table": "t", "from": over["from"]}]}
    charted = {"table": "t", "from": {"row": "r1", "col": "a"}, "to": {"row": "r3", "col": "b"}}
    room = tab(
        Block("table", "t", {"heights": {"r1": 30, "r4": 40}}, grid=grid, cells=cells),
        Block("table", "s", grid=Grid(["s1"], ["a"], formulas=other)),
        Block("chart", "ch", {"range": charted}),
    )
    room.names["n"] = {"name": "Iznosi", "pieces": [{"table": "t", **over}]}
    taken = {"op": "lines", "table": "t", "axis": "rows", "remove": True}
    done = run(room, taken | {"from": "r1", "to": "r1"}, taken | {"from": "r3", "to": "r3"})
    stored = grid_of(room, "t")
    assert stored["rows"] == ["r2", "r4"]
    assert stored["texts"] == {"r2:a": "Spojeno", "r2:b": "2", "r4:a": "y"}
    assert stored["formats"] == {"r2:a": "0%", "r2:b": "0.00"}
    kept = {"from": {"row": "r2", "col": "b"}, "to": {"row": "r2", "col": "b"}}
    assert stored["formulas"] == {"r4:b": grids.formula_at(["SUM(", kept, ")"], "r4", "b")}
    assert grid_of(room, "s")["formulas"]["s1:a"] == [
        "SUM(",
        {"table": "t", **kept},
        ")+",
        {"table": "t", "from": {"row": "r1", "col": "b"}},
    ]
    assert room.names["n"]["pieces"] == [{"table": "t", **kept}]
    assert table(room, "ch").attrs["range"]["from"] == {"row": "r2", "col": "a"}
    found = table(room, "t")
    assert found.attrs["heights"] == {"r4": 40}
    merged = {(cell.row, cell.col): (cell.to, cell.text) for cell in found.cells}
    assert merged[("r2", "a")] == (None, "Spojeno")
    room.take_back(done.change)
    assert room.names["n"]["pieces"] == [{"table": "t", **over}]
    assert grid_of(room, "t")["formulas"] == {
        "r4:b": grids.formula_at(["SUM(", over, ")"], "r4", "b")
    }


def test_columns_taken_out_move_a_merged_cell_to_the_slots_it_keeps():
    cells = [
        Cell("r1", "a", [paragraph("h", Run("Naslov"))], to="r1:c"),
        Cell("r2", "b", [paragraph("x", Run("x"))], to="r2:c"),
    ]
    widths = {"b": 10, "c": 20}
    room = tab(
        Block("table", "t", {"widths": widths}, grid=Grid(["r1", "r2"], list("abc")), cells=cells)
    )
    remove = {"op": "lines", "table": "t", "axis": "cols", "remove": True}
    assert refused(room, remove | {"from": "z", "to": "a"}).code == "no_col"
    assert refused(room, remove | {"from": "c", "to": "a"}).code == "lines"
    assert refused(room, remove | {"from": "b", "to": "b", "before": "c"}).code == "invalid"
    assert refused(room, remove | {"ids": ["b"]}).code == "invalid"
    assert refused(room, remove | {"from": "b"}).code == "invalid"
    run(room, remove | {"from": "b", "to": "b"})
    found = table(room, "t")
    assert found.grid.cols == ["a", "c"] and found.attrs["widths"] == {"c": 20}
    assert [(cell.row, cell.col, cell.to) for cell in found.cells] == [
        ("r1", "a", "r1:c"),
        ("r2", "c", None),
    ]


def test_rows_sorted_keep_ranges_over_their_places_and_references_on_their_rows():
    over = {"table": "t", "from": {"row": "a", "col": "x"}, "to": {"row": "c", "col": "x"}}
    alone = {"table": "t", "from": {"row": "a", "col": "x"}}
    other = {"s1:a": ["SUM(", over, ")+", alone]}
    charted = {"table": "t", "from": {"row": "h", "col": "x"}, "to": {"row": "c", "col": "x"}}
    merged = Cell("m1", "x", [paragraph("mp", Run("spojeno"))], to="m2:x")
    room = tab(
        Block("table", "t", grid=Grid(["h", "a", "b", "c"], ["x"])),
        Block("table", "s", grid=Grid(["s1"], ["a"], formulas=other)),
        Block("chart", "ch", {"range": charted}),
        Block("table", "u", grid=Grid(["m1", "m2", "m3"], ["x"]), cells=[merged]),
    )
    for row, value in {"h": "Naslov", "a": 1, "b": 2, "c": 3}.items():
        room.calculated("t", row, {"x": value})
    run(room, {"op": "order", "table": "t", "col": "x", "descending": True})
    assert grid_of(room, "t")["rows"] == ["h", "c", "b", "a"]
    assert grid_of(room, "s")["formulas"]["s1:a"] == [
        "SUM(",
        {**over, "from": {"row": "c", "col": "x"}, "to": {"row": "a", "col": "x"}},
        ")+",
        alone,
    ]
    assert table(room, "ch").attrs["range"]["to"] == {"row": "a", "col": "x"}
    sort = {"op": "order", "table": "u", "col": "x"}
    assert refused(room, sort | {"from": "m2", "to": "m1"}).code == "merged_rows"
    assert refused(room, sort | {"table": "t", "from": "z", "to": "a"}).code == "no_row"
    assert refused(room, sort | {"col": "y"}).code == "no_col"
    run(room, sort | {"from": "m3", "to": "m3"})
    assert grid_of(room, "u")["rows"] == ["m1", "m2", "m3"]


def test_blocks_move_as_copies_of_themselves_and_a_table_keeps_its_grid():
    room = tab(
        paragraph("a", Run("A", {"em": {}})),
        paragraph("b", Run("B")),
        Block("table", "t", grid=Grid(["r"], ["c"]), cells=[blocks.light_cell("r:c", "x")]),
        paragraph("c", Run("C")),
    )
    run(room, {"op": "move", "from": "a", "to": "b", "at": {"after": "c"}})
    assert ids(room) == ["t", "c", "a", "b"]
    assert room.read()[2].runs == [Run("A", {"em": {}})]
    run(room, {"op": "move", "from": "t", "at": {"start": "body"}})
    assert ids(room) == ["t", "c", "a", "b"]
    run(room, {"op": "move", "from": "b", "at": {"before": "c"}})
    assert ids(room) == ["t", "b", "c", "a"]
    assert grid_of(room, "t")["texts"] == {"r:c": "x"}
    run(room, {"op": "move", "from": "c", "at": {"start": {"table": "t", "row": "r", "col": "c"}}})
    (cell,) = table(room, "t").cells
    assert [block.text for block in cell.blocks] == ["C", "x"]
    into = {"op": "move", "from": "t", "at": {"end": {"table": "t", "row": "r", "col": "c"}}}
    assert refused(room, into).code == "into_itself"
    assert (
        refused(room, {"op": "move", "from": "a", "to": "b", "at": {"end": "body"}}).code
        == "not_a_run"
    )


def test_a_table_cannot_stand_in_a_cell():
    room = tab(
        Block("table", "t", grid=Grid(["r"], ["c"])),
        Block("table", "u", grid=Grid(["r"], ["c"])),
    )
    move = {"op": "move", "from": "u", "at": {"end": {"table": "t", "row": "r", "col": "c"}}}
    assert refused(room, move).code == "schema"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "stranger",
    [
        {"type": "image", "attrs": {"blob": "ab" * 32}},
        {"type": "pdf", "attrs": {"blob": "ab" * 32}},
        {"type": "slideBreak", "attrs": {"background": {"image": "ab" * 32}}},
    ],
)
def test_a_run_shows_only_the_documents_own_images_and_pdfs(stranger):
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Ponuda")
    first = open_tab(document)
    second = open_tab(document, "Prilog")
    assert [(first.position, first.title), (second.position, second.title)] == [
        (0, ""),
        (1, "Prilog"),
    ]
    with pytest.raises(Refused) as found:
        perform(first, [{"op": "insert", "at": {"end": "body"}, "blocks": [stranger]}], "run")
    assert (found.value.code, found.value.detail) == ("blob", "ab" * 32)


@pytest.mark.django_db
def test_a_run_is_not_taken_back_from_a_tab_that_has_moved_to_another_room():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Ponuda")
    moved = open_tab(document)
    done = run(tab(), {"op": "insert", "at": {"end": "body"}, "blocks": [node("paragraph")]})
    with pytest.raises(Refused) as found:
        undo(moved, uuid4(), done.change)
    assert (found.value.code, found.value.detail) == ("moved", str(moved.pk))
