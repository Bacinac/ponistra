import pytest

from apps.content import blocks
from apps.content.blocks import Block, Cell, Grid, Run, key_of
from apps.content.grids import FORMAT, FORMULA, LOOK, TEXT
from apps.content.sheets import Refused

from .helpers import Room


def paragraph(id: str, *runs: Run) -> Block:
    return Block("paragraph", id, {}, list(runs))


def sheet(*rows: list, locale: str = "hr") -> Room:
    room = Room(paragraph("a"))
    width = max(len(line) for line in rows)
    room.run(
        {
            "op": "table",
            "at": {"after": "a"},
            "id": "t",
            "rowIds": [f"r{y}" for y in range(len(rows))],
            "colIds": [f"c{x}" for x in range(width)],
            "rows": [list(line) + [None] * (width - len(line)) for line in rows],
        },
        locale=locale,
    )
    return room


def fill(room: Room, start: str, end: str, until: str, locale: str = "hr", **more):
    def point(slot: str) -> dict:
        row, col = slot.split(":")
        return {"row": row, "col": col}

    return room.run(
        {
            "op": "fill",
            "table": "t",
            "from": point(start),
            "to": point(end),
            "until": point(until),
            **more,
        },
        locale=locale,
    )


def column(room: Room, col: str, part: str = TEXT) -> list:
    laid = room.grids["t"]
    return [laid.cell(row, col).get(part) for row in laid.row_ids()]


def test_numbers_go_on_by_their_trend_and_one_number_is_repeated():
    room = sheet([1, 7], [3], [None], [None], [None])
    fill(room, "r0:c0", "r1:c0", "r4:c0")
    assert column(room, "c0") == ["1", "3", "5", "7", "9"]
    fill(room, "r0:c1", "r0:c1", "r2:c1")
    assert column(room, "c1") == ["7", "7", "7", None, None]


def test_numbers_continue_in_the_documents_language_and_the_way_they_were_written():
    room = sheet(["1,5", "10%", "1.000,5"], ["2", "15%", "1.001,5"], [None, None, None])
    for col in ("c0", "c1", "c2"):
        fill(room, f"r0:{col}", f"r1:{col}", f"r2:{col}")
    assert [column(room, col)[2] for col in ("c0", "c1", "c2")] == ["2,5", "20%", "1.002,50"]
    english = sheet(["1.5"], ["2"], [None], locale="en")
    fill(english, "r0:c0", "r1:c0", "r2:c0", locale="en")
    assert column(english, "c0") == ["1.5", "2", "2.5"]


def test_dates_go_on_by_a_day_or_by_the_months_between_them():
    room = sheet(["20.10.2026", "15.01.2026"], [None, "15.02.2026"], [None], [None])
    fill(room, "r0:c0", "r0:c0", "r2:c0")
    assert column(room, "c0")[:3] == ["20.10.2026", "21.10.2026", "22.10.2026"]
    fill(room, "r0:c1", "r1:c1", "r3:c1")
    assert column(room, "c1") == ["15.01.2026", "15.02.2026", "15.3.2026", "15.4.2026"]


def test_text_ending_in_a_number_counts_on_and_other_cells_repeat():
    room = sheet(
        ["Stavka 1", "R08", "a"], [None, None, "1"], [None, None, None], [None, None, None]
    )
    fill(room, "r0:c0", "r0:c0", "r2:c0")
    assert column(room, "c0")[:3] == ["Stavka 1", "Stavka 2", "Stavka 3"]
    fill(room, "r0:c1", "r0:c1", "r3:c1")
    assert column(room, "c1") == ["R08", "R09", "R10", "R11"]
    fill(room, "r0:c2", "r1:c2", "r3:c2")
    assert column(room, "c2") == ["a", "1", "a", "1"]


def test_a_fill_that_copies_repeats_the_cells_as_they_are_and_still_moves_formulas():
    room = sheet(["Stavka 1", "20.10.2026.", 2, {"formula": "=C1*2"}], [None], [None])
    fill(room, "r0:c0", "r0:c3", "r2:c0", copies=True)
    assert [column(room, col) for col in ("c0", "c1", "c2")] == [
        ["Stavka 1"] * 3,
        ["20.10.2026."] * 3,
        ["2"] * 3,
    ]
    rows = [
        next(piece for piece in pieces if isinstance(piece, dict))["from"]["row"]
        for pieces in column(room, "c3", FORMULA)
    ]
    assert rows == ["@", "@", "@"]


def test_a_formula_moves_with_its_copies_and_each_takes_its_cells_look_and_format():
    room = sheet([2, {"formula": "=A1*2"}], [3], [4], [5])
    bold = {
        "type": "paragraph",
        "content": [{"type": "text", "text": "2", "marks": [{"type": "strong"}]}],
    }
    room.run(
        {"op": "cells", "table": "t", "cells": [{"row": "r0", "col": "c0", "blocks": [bold]}]},
        {"op": "cells", "table": "t", "cells": [{"row": "r0", "col": "c1", "format": "0.00"}]},
    )
    fill(room, "r0:c1", "r0:c1", "r3:c1")
    rows = [
        next(piece for piece in pieces if isinstance(piece, dict))["from"]["row"]
        for pieces in column(room, "c1", FORMULA)
    ]
    assert rows == ["@", "@", "@", "@"]
    assert column(room, "c1", FORMAT) == ["0.00"] * 4
    room.run({"op": "cells", "table": "t", "cells": [{"row": "r3", "col": "c0", "value": None}]})
    fill(room, "r0:c0", "r2:c0", "r3:c0")
    looks = column(room, "c0", LOOK)
    assert column(room, "c0")[3] == "5" and looks[3] == looks[0] is not None


def test_a_cell_filled_on_takes_the_fill_and_the_edges_of_the_one_it_repeats():
    line = {"line": "single", "width": 0.5}
    held = Cell(
        "r0",
        "c0",
        [paragraph("p", Run("Prvi")), paragraph("q", Run("Drugi"))],
        fill="yellow",
        edges={"top": line},
    )
    table = Block("table", "t", grid=Grid(["r0", "r1", "r2"], ["c0"]), cells=[held])
    room = Room(paragraph("a"), table)
    fill(room, "r0:c0", "r0:c0", "r2:c0")
    (found,) = [block for block in blocks.read(room.doc, room.grids) if block.type == "table"]
    assert [(cell.fill, cell.edges) for cell in found.cells] == [("yellow", {"top": line})] * 3


def test_a_range_fills_up_and_left_counting_back():
    room = sheet([None, None, None], [None, 5, 6], [None, 6, None])
    fill(room, "r1:c1", "r2:c1", "r0:c1")
    assert column(room, "c1") == ["4", "5", "6"]
    fill(room, "r1:c1", "r1:c2", "r1:c0")
    assert room.grids["t"].cell("r1", "c0")[TEXT] == "4"


@pytest.mark.parametrize(
    ("start", "end", "until", "code"),
    [
        ("r0:c0", "r0:c0", "r1:c1", "fill"),
        ("r0:c0", "r1:c0", "r1:c0", "fill"),
        ("r0:c0", "r0:c0", "r0:zz", "no_cell"),
    ],
)
def test_a_fill_goes_one_way_out_of_its_range(start, end, until, code):
    room = sheet([1, 2], [3, 4])
    with pytest.raises(Refused) as found:
        fill(room, start, end, until)
    assert found.value.code == code


def test_merged_cells_are_not_filled_over():
    room = sheet([1, 2], [3, 4], [None, None])
    room.run(
        {
            "op": "cells",
            "table": "t",
            "cells": [{"row": "r1", "col": "c0", "span": {"rows": 1, "cols": 2}}],
        }
    )
    with pytest.raises(Refused) as found:
        fill(room, "r0:c0", "r0:c1", "r2:c1")
    assert found.value.code == "covered"
    assert key_of("r1", "c0") in room.grids["t"].entries("to")
