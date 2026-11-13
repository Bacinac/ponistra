import pytest
from asgiref.sync import sync_to_async

from apps.content import blocks
from apps.content.blocks import Block, Cell, Grid, Run
from apps.content.operations import Refused

from .helpers import Room, fill, regrid
from .test_elements import first_tab

ROWS = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"]


def typed(text: str, bold: bool = False) -> list[Block]:
    return [Block("paragraph", runs=[Run(text, {"strong": {}} if bold else {})])]


def room_of(*values, bold: int = 0, cells: tuple[Cell, ...] = ()) -> Room:
    """A table of a column of cells holding the values, as the calculation left them, the first
    rows given in bold."""
    rows = ROWS[: len(values)]
    shown = [
        blocks.light_cell(f"r{y}:a", str(value), {"marks": {"strong": {}}} if y <= bold else None)
        for y, value in enumerate(values, 1)
        if value is not None
    ]
    room = Room(Block("table", "t", grid=Grid(rows, ["a", "b"]), cells=[*shown, *cells]))
    for y, value in enumerate(values, 1):
        if value is not None:
            room.calculated("t", f"r{y}", {"a": value})
    return room


def sorted_rows(room: Room, col: str = "a", descending: bool = False, **ends) -> list[str]:
    room.run({"op": "order", "table": "t", "col": col, "descending": descending, **ends})
    return room.grids["t"].row_ids()


def test_numbers_text_in_the_languages_order_logical_values_and_errors_with_empty_cells_last():
    values = ("čaj", 10, "cesta", None, True, 2, {"error": "#DIV/0!"}, "Ćup")
    ascending = ["r6", "r2", "r3", "r1", "r8", "r5", "r7", "r4"]
    assert sorted_rows(room_of(*values)) == ascending
    descending = ["r7", "r5", "r8", "r1", "r3", "r2", "r6", "r4"]
    assert sorted_rows(room_of(*values), descending=True) == descending


def test_equal_values_keep_their_order_and_case_does_not_count():
    assert sorted_rows(room_of("b", "A", "a", "B")) == ["r2", "r3", "r1", "r4"]
    assert sorted_rows(room_of("b", "A", "a", "B"), descending=True) == ["r1", "r4", "r2", "r3"]


@pytest.mark.parametrize(
    ("values", "bold", "sorted"),
    [
        (("Iznos", 3, 1, 2), 0, ["r1", "r3", "r4", "r2"]),
        (("Ime", "Marko", "Ana"), 1, ["r1", "r3", "r2"]),
        (("Marko", "Ana", "Iva"), 0, ["r2", "r3", "r1"]),
        (("Ime", "Marko", "Ana"), 3, ["r3", "r1", "r2"]),
    ],
)
def test_a_first_row_set_apart_by_bold_text_or_by_its_kind_of_value_stays_on_top(
    values, bold, sorted
):
    assert sorted_rows(room_of(*values, bold=bold)) == sorted


def test_only_the_rows_between_the_ends_are_sorted_and_a_merged_cell_moves_with_its_row():
    merged = (Cell("r3", "a", typed("2"), to="r3:b"),)
    assert sorted_rows(room_of("Iznos", 3, 2, 1, cells=merged), **{"from": "r4", "to": "r2"}) == [
        "r1",
        "r4",
        "r3",
        "r2",
    ]
    assert sorted_rows(room_of("Iznos", 3, 2, 1, cells=merged), col="b") == [
        "r3",
        "r1",
        "r2",
        "r4",
    ]
    assert sorted_rows(room_of("Iznos", 3, 2, 1, cells=merged)) == ["r1", "r4", "r3", "r2"]


def test_rows_that_a_merged_cell_spans_are_not_parted_and_unknown_lines_are_refused():
    merged = (Cell("r3", "a", typed("2"), to="r4:a"),)
    room = room_of(1, 3, 2, None, cells=merged)
    sort = {"op": "order", "table": "t", "col": "a"}
    for wrong, code in [
        ({}, "merged_rows"),
        ({"col": "c"}, "no_col"),
        ({"from": "gone", "to": "r1"}, "no_row"),
    ]:
        with pytest.raises(Refused) as found:
            room.run(sort | wrong)
        assert found.value.code == code
    assert sorted_rows(room, descending=True, **{"from": "r2", "to": "r1"}) == [
        "r2",
        "r1",
        "r3",
        "r4",
    ]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_table_is_sorted_by_the_values_its_book_calculated(api, live):
    def checked():
        tab = first_tab(api)
        elsewhere = {"table": "u", "from": {"row": "x", "col": "a"}}
        texts = [(1, "Iznos"), (2, "3"), (4, "2")]
        table = Block(
            "table",
            "t",
            grid=Grid(ROWS[:4], ["a"], formulas={"r3:a": [elsewhere]}),
            cells=[Cell(f"r{y}", "a", typed(text)) for y, text in texts],
        )
        other = Block(
            "table",
            "u",
            {"name": "Ulaz"},
            grid=Grid(["x"], ["a"]),
            cells=[Cell("x", "a", typed("1,5"))],
        )
        fill(tab, [table, other])
        regrid(tab, {"op": "order", "table": "t", "col": "a", "descending": True})
        assert Room.of(tab).grids["t"].row_ids() == ["r1", "r2", "r4", "r3"]
        regrid(tab, {"op": "order", "table": "t", "col": "a", "from": "r4", "to": "r2"})
        assert Room.of(tab).grids["t"].row_ids() == ["r1", "r4", "r2", "r3"]

    await sync_to_async(checked)()
