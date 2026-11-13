import pytest

from apps.content import blocks, calculation, finding
from apps.content.blocks import Block, Cell, Grid, Run, light_cell
from apps.content.operations import Refused
from apps.content.sheets import Sheets
from apps.content.table import tables_of

from .helpers import Room, fill
from .test_elements import first_tab


def paragraph(id: str, *runs: Run) -> Block:
    return Block("paragraph", id, runs=list(runs))


def room_of() -> Room:
    table = Block(
        "table",
        "t",
        {"hidden": {"rows": ["r4"]}},
        grid=Grid(["r1", "r2", "r3", "r4"], ["a", "b"]),
        cells=[
            light_cell("r1:a", "čaj"),
            light_cell("r1:b", "kava"),
            Cell("r2", "a", [paragraph("c1", Run("Zeleni ČAJ")), paragraph("c2", Run("x"))]),
            light_cell("r3:b", "'čaj"),
            light_cell("r4:a", "čaj"),
        ],
    )
    return Room(
        paragraph("p1", Run("Čaj", {"strong": {}}), Run(" i čajnik")),
        table,
        paragraph("p2", Run("Kraj čaja")),
    )


def hits(room: Room, text: str, **options) -> list[dict]:
    sought = finding.Sought(text, **options)
    if room.document is None:
        grids = room.grids
    else:
        held = Sheets(tables_of(room.document), document=room.document)
        grids = {table: held.peek(table) for table in held.base}
    found, more = finding.found_in(blocks.body_of(room.doc), grids, sought)
    assert not more
    return [hit.json() for hit in found]


def cell(table: str, row: str, col: str, **found) -> dict:
    return {"table": table, "row": row, "col": col, **found}


def text_of(room: Room, row: str, col: str) -> str:
    return room.grids["t"].cell(row, col).get("text")


def test_the_text_and_the_cells_shown_are_found_in_their_order_but_in_hidden_rows():
    room = room_of()
    rich = cell("t", "r2", "a", block="c1", **{"from": 7, "to": 10})
    assert hits(room, "čaj") == [
        {"block": "p1", "from": 0, "to": 3},
        {"block": "p1", "from": 6, "to": 9},
        cell("t", "r1", "a"),
        rich,
        cell("t", "r3", "b"),
        {"block": "p2", "from": 5, "to": 8},
    ]
    assert hits(room, "čaj", case=True) == [
        {"block": "p1", "from": 6, "to": 9},
        cell("t", "r1", "a"),
        cell("t", "r3", "b"),
        {"block": "p2", "from": 5, "to": 8},
    ]
    assert hits(room, "čaj", words=True) == [
        {"block": "p1", "from": 0, "to": 3},
        cell("t", "r1", "a"),
        rich,
        cell("t", "r3", "b"),
    ]
    assert hits(room, "'čaj") == []
    assert hits(room, "a.") == []


def test_a_replacement_everywhere_keeps_the_formatting_and_the_apostrophe_and_is_taken_back_whole():
    room = room_of()
    done = room.run({"op": "substitute", "find": "čaj", "by": "chai"})
    assert done.made == [{"replaced": 6}]
    p1 = next(block for block in room.read() if block.id == "p1")
    assert [(run.text, run.marks) for run in p1.runs] == [
        ("chai", {"strong": {}}),
        (" i chainik", {}),
    ]
    assert next(block for block in room.read() if block.id == "p2").text == "Kraj chaia"
    assert [text_of(room, *at) for at in [("r1", "a"), ("r3", "b"), ("r4", "a")]] == [
        "chai",
        "'chai",
        "čaj",
    ]
    assert hits(room, "chai") == [
        {"block": "p1", "from": 0, "to": 4},
        {"block": "p1", "from": 7, "to": 11},
        cell("t", "r1", "a"),
        cell("t", "r2", "a", block="c1", **{"from": 7, "to": 11}),
        cell("t", "r3", "b"),
        {"block": "p2", "from": 5, "to": 9},
    ]
    room.take_back(done.change)
    assert hits(room, "chai") == []
    assert len(hits(room, "čaj")) == 6
    assert [(run.text, run.marks) for run in room.read()[0].runs] == [
        ("Čaj", {"strong": {}}),
        (" i čajnik", {}),
    ]


def test_one_replacement_where_it_starts_or_in_one_cell():
    room = room_of()
    found = {"op": "substitute", "find": "čaj", "by": "čaj-"}
    assert room.run(found | {"block": "p1", "from": 6}).made == [{"replaced": 1}]
    assert next(block for block in room.read() if block.id == "p1").text == "Čaj i čaj-nik"
    room.run(found | {"table": "t", "row": "r1", "col": "a"})
    room.run(found | {"block": "c1", "from": 7})
    assert text_of(room, "r1", "a") == "čaj-"
    assert hits(room, "čaj-") == [
        {"block": "p1", "from": 6, "to": 10},
        cell("t", "r1", "a"),
        cell("t", "r2", "a", block="c1", **{"from": 7, "to": 11}),
    ]
    for wrong, code in [
        ({"block": "p1", "from": 1}, "no_words"),
        ({"block": "p1"}, "invalid"),
        ({"table": "t", "row": "r1"}, "invalid"),
        ({"block": "p1", "from": 0, "table": "t", "row": "r1", "col": "a"}, "invalid"),
        ({"table": "t", "row": "r1", "col": "b"}, "no_words"),
        ({"block": "gone", "from": 0}, "no_text"),
    ]:
        with pytest.raises(Refused) as refused:
            room.run(found | wrong)
        assert refused.value.code == code


@pytest.mark.django_db
def test_a_cell_a_formula_calculates_is_found_but_not_replaced(api):
    tab = first_tab(api)
    grid = Grid(["r1", "r2"], ["a"], formulas={"r2:a": ['UPPER("čaj")']})
    fill(tab, [Block("table", "t", grid=grid, cells=[light_cell("r1:a", "čaj")])])
    calculation.calculate(tab.document, {"t"}, {})
    response = api.get(f"/api/tabs/{tab.pk}/found", {"text": "ČAJ"})
    assert response.status_code == 200
    assert response.json() == {
        "hits": [cell("t", "r1", "a"), cell("t", "r2", "a", formula=True)],
        "more": False,
    }
    room = Room.of(tab)
    assert room.run({"op": "substitute", "find": "čaj", "by": "kava"}).made == [{"replaced": 1}]
    with pytest.raises(Refused) as refused:
        room.run(
            {"op": "substitute", "find": "čaj", "by": "kava", "table": "t", "row": "r2", "col": "a"}
        )
    assert refused.value.code == "formula"
    assert api.get(f"/api/tabs/{tab.pk}/found", {"text": ""}).status_code == 400
