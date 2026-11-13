from datetime import UTC, timedelta
from decimal import Decimal

import pytest
from anyio import create_memory_object_stream, create_task_group
from asgiref.sync import sync_to_async
from django.test import AsyncClient
from django.utils import timezone
from pycrdt import Awareness, Doc, YMessageType, read_message

from apps.actions.models import ActionRun, RunChange
from apps.actions.registry import ACTIONS, Action, invalid
from apps.actions.tables import GROUP, TOTAL, calculate, chart, clean, group, total, totals
from apps.collab import server
from apps.collab.tests.test_server import Endpoint, until
from apps.content import calculation, compute, designs, grids, placing
from apps.content.blocks import Block, Cell, Grid, Run, key_of, light_cell
from apps.content.data import data_of, order, totals_row
from apps.content.operations import Refused
from apps.content.tests.helpers import Room, fill
from apps.content.tests.test_elements import first_tab
from apps.documents.models import Node, Tab
from apps.users.models import User

JSON = "application/json"
PRICE = '#,##0.00 "€"'


def typed(text: str, bold: bool = False) -> list[Block]:
    return [Block("paragraph", runs=[Run(text, {"strong": {}} if bold else {})])]


def priced(*lines: tuple[str, str, str]) -> Block:
    given = [("Artikl", "Količina", "Cijena"), *lines]
    rows = [f"r{y}" for y in range(1, len(given) + 1)]
    cells = [
        Cell(row, col, typed(text, y == 0))
        for y, (row, line) in enumerate(zip(rows, given, strict=True))
        for col, text in zip("abc", line, strict=True)
        if text
    ]
    formats = {key_of(row, "c"): PRICE for row in rows[1:]}
    grid = Grid(rows, list("abc"), formats=formats)
    attrs = {"designs": [designs.ours(designs.NEW)]}
    return Block("table", "t", attrs=attrs, grid=grid, cells=cells)


def amounts(*lines: tuple[str, str, str]) -> Block:
    """A priced table with a fourth column, Iznos, empty in the data."""
    table = priced(*lines)
    table.grid.cols.append("d")
    table.cells.append(Cell("r1", "d", typed("Iznos", True)))
    return table


def copied(doc: Doc) -> Doc:
    copy = Doc()
    copy.apply_update(doc.get_update())
    return copy


def table_in(room: Room) -> Block:
    return compute.tables_in(room.doc, room.grids, {"t"})["t"]


def values_in(room: Room, table: str = "t") -> dict[str, dict]:
    tab = Tab.objects.get(pk=room.tab)
    room.keep(tab)
    nodes = placing.nodes_of(placing.of_document(tab.document))
    calculation.calculate(tab.document, nodes.keys(), nodes)
    return grids.of_tab(tab)[table].told(nodes.get(table))


@pytest.mark.django_db
def test_the_actions_are_listed_with_their_targets_and_parameters(api):
    response = api.get("/api/actions")
    assert response.status_code == 200
    assert {"id": "table.totals", "target": "table", "review": "apply", "model": None}.items() <= (
        response.json()["actions"][0].items()
    )


def test_the_totals_labels_are_written_in_every_language_a_document_can_have():
    assert set(TOTAL) == set(GROUP) == set(Node.Locale.values)


@pytest.mark.django_db
def test_totals_subtotal_each_column_of_numbers_in_its_format_below_the_data(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"))])
    room = Room.of(tab)
    room.build(totals(tab, {"table": "t"}, {}))
    table = table_in(room)
    grid = table.grid
    assert grid.rows[:3] == ["r1", "r2", "r3"] and len(grid.rows) == 4
    row = grid.rows[3]
    for col in "bc":
        assert grid.formulas[key_of(row, col)] == [
            "SUBTOTAL(109,",
            {"from": {"row": "r2", "col": "@"}, "to": {"row": "r3", "col": "@"}},
            ")",
        ]
    assert grid.formats[key_of(row, "c")] == PRICE and key_of(row, "b") not in grid.formats
    cells = {(cell.row, cell.col): cell for cell in table.cells}
    label = cells[(row, "a")].blocks[0].runs
    assert [(run.text, run.marks) for run in label] == [("Ukupno", {"strong": {}})]
    assert cells[(row, "b")].blocks[0].attrs["endMarks"] == {"strong": {}}
    found = values_in(room)
    assert found[key_of(row, "b")]["text"] == "5"
    assert found[key_of(row, "c")]["text"].startswith("1,75")
    assert totals_row(None, room.grids["t"]) == row
    assert order(None, room.grids["t"], None, "hr", "b", None, False) == ["r3", "r2"]
    assert table.attrs["designs"] == [{**designs.ours(designs.NEW), "on": {"totals": True}}]


@pytest.mark.django_db
def test_totals_run_again_cover_the_rows_the_data_has_by_then(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"))])
    room = Room.of(tab)
    room.build(totals(tab, {"table": "t"}, {}))
    row = table_in(room).grid.rows[3]
    added = [
        {"op": "lines", "table": "t", "axis": "rows", "ids": ["r4"], "before": row},
        {"op": "cells", "table": "t", "cells": [{"row": "r4", "col": "b", "value": 4}]},
    ]
    room.run(*added)
    room.keep(tab)
    again = Room.of(tab)
    again.build(totals(tab, {"table": "t"}, {}))
    grid = table_in(again).grid
    assert grid.rows == ["r1", "r2", "r3", "r4", row]
    assert grid.formulas[key_of(row, "b")][1]["to"] == {"row": "r4", "col": "@"}
    assert values_in(again)[key_of(row, "b")]["text"] == "9"
    labels = [cell for cell in table_in(again).cells if cell.row == row and cell.col == "a"]
    assert [cell.text for cell in labels] == ["Ukupno"]


@pytest.mark.django_db
def test_totals_need_a_column_of_numbers_and_the_data_they_were_planned_for(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "", ""), ("Matica", "", ""))])
    with pytest.raises(Refused) as found:
        totals(tab, {"table": "t"}, {})
    assert found.value.code == "no_numbers"
    with pytest.raises(Refused) as found:
        totals(tab, {"table": "x"}, {})
    assert found.value.code == "no_table"
    fill(tab, [priced(("Vijak", "3", "1,5")), Block("paragraph", "p")])
    build = totals(tab, {"table": "t"}, {})
    room = Room.of(tab)
    room.run(
        {"op": "lines", "table": "t", "axis": "rows", "from": "r2", "to": "r2", "remove": True}
    )
    with pytest.raises(Refused) as found:
        room.build(build)
    assert found.value.code == "changed"
    gone = Room.of(tab)
    gone.run({"op": "delete", "from": "t"})
    with pytest.raises(Refused) as found:
        gone.build(build)
    assert found.value.code == "no_table"


def grouped(tab: Tab, col: str) -> Room:
    room = Room.of(tab)
    room.build(group(tab, {"table": "t", "col": col}, {}))
    return room


def subtotal(start: str, end: str) -> tuple:
    return ("SUBTOTAL(109,", {"from": {"row": start, "col": "@"}, "to": {"row": end, "col": "@"}})


@pytest.mark.django_db
def test_total_writes_the_function_chosen_under_the_column_making_the_totals_row_once(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"))])
    room = Room.of(tab)
    room.build(total(tab, {"table": "t", "col": "b"}, {"function": "average"}))
    table = table_in(room)
    grid = table.grid
    assert grid.rows[:3] == ["r1", "r2", "r3"] and len(grid.rows) == 4
    row = grid.rows[3]
    assert grid.formulas[key_of(row, "b")] == [
        "SUBTOTAL(101,",
        {"from": {"row": "r2", "col": "@"}, "to": {"row": "r3", "col": "@"}},
        ")",
    ]
    assert key_of(row, "c") not in grid.formulas
    cells = {(cell.row, cell.col): cell for cell in table.cells}
    label = cells[(row, "a")].blocks[0].runs
    assert [(run.text, run.marks) for run in label] == [("Ukupno", {"strong": {}})]
    assert values_in(room)[key_of(row, "b")]["text"] == "2,5"
    assert totals_row(None, room.grids["t"]) == row
    room.keep(tab)
    again = Room.of(tab)
    again.build(total(tab, {"table": "t", "col": "c"}, {"function": "max"}))
    grid = table_in(again).grid
    assert grid.rows == ["r1", "r2", "r3", row]
    assert grid.formulas[key_of(row, "c")][0] == "SUBTOTAL(104,"
    assert grid.formats[key_of(row, "c")] == PRICE
    assert values_in(again)[key_of(row, "c")]["text"].startswith("1,50")
    again.keep(tab)
    off = Room.of(tab)
    off.build(total(tab, {"table": "t", "col": "b"}, {"function": "none"}))
    grid = table_in(off).grid
    assert grid.rows == ["r1", "r2", "r3", row] and key_of(row, "b") not in grid.formulas
    assert totals_row(None, off.grids["t"]) == row
    off.keep(tab)
    gone = Room.of(tab)
    gone.build(total(tab, {"table": "t", "col": "c"}, {"function": "none"}))
    assert table_in(gone).grid.rows == ["r1", "r2", "r3"]
    assert table_in(gone).attrs["designs"][0]["on"] == {"totals": False}


@pytest.mark.django_db
def test_total_offers_a_column_of_text_the_count_of_its_values_alone(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"))])
    with pytest.raises(Refused) as found:
        total(tab, {"table": "t", "col": "a"}, {"function": "sum"})
    assert found.value.code == "text_column"
    with pytest.raises(Refused) as found:
        total(tab, {"table": "t", "col": "x"}, {"function": "sum"})
    assert found.value.code == "no_line"
    room = Room.of(tab)
    with pytest.raises(Refused) as found:
        room.build(total(tab, {"table": "t", "col": "b"}, {"function": "none"}))
    assert found.value.code == "no_totals"
    room.build(total(tab, {"table": "t", "col": "a"}, {"function": "counta"}))
    table = table_in(room)
    row = table.grid.rows[3]
    assert table.grid.formulas[key_of(row, "a")][0] == "SUBTOTAL(103,"
    assert values_in(room)[key_of(row, "a")]["text"] == "2"
    assert not [cell for cell in table.cells if cell.row == row and cell.col != "a"]
    assert totals_row(None, room.grids["t"]) == row
    assert order(None, room.grids["t"], None, "hr", "b", None, False) == ["r3", "r2"]


@pytest.mark.django_db
def test_calculate_writes_the_operation_into_every_row_of_the_data_in_the_operands_format(api):
    tab = first_tab(api)
    fill(tab, [amounts(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"))])
    room = Room.of(tab)
    product = {"operation": "product", "columns": ["b", "c"]}
    room.build(calculate(tab, {"table": "t", "col": "d"}, product))
    grid = table_in(room).grid
    assert grid.formulas[key_of("r2", "d")] == grid.formulas[key_of("r3", "d")]
    assert grid.formulas[key_of("r2", "d")][1:2] == ["*"]
    assert grid.formats[key_of("r2", "d")] == PRICE
    assert key_of("r1", "d") not in grid.formulas
    values = values_in(room)
    assert values[key_of("r2", "d")]["text"].startswith("4,50")
    assert values[key_of("r3", "d")]["text"].startswith("0,50")
    again = room
    again.build(
        calculate(tab, {"table": "t", "col": "d"}, {"operation": "average", "columns": ["b", "c"]})
    )
    grid = table_in(again).grid
    assert grid.formulas[key_of("r2", "d")][0] == "AVERAGE("
    assert values_in(again)[key_of("r2", "d")]["text"].startswith("2,25")


@pytest.mark.django_db
def test_calculate_takes_columns_of_numbers_into_an_empty_or_calculated_column(api):
    tab = first_tab(api)
    fill(tab, [amounts(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"))])

    def refused(col: str, operation: str, columns: list[str]) -> str:
        with pytest.raises(Refused) as found:
            calculate(tab, {"table": "t", "col": col}, {"operation": operation, "columns": columns})
        return found.value.code

    assert refused("d", "sum", ["b", "x"]) == "no_line"
    assert refused("d", "sum", ["b", "d"]) == "same_column"
    assert refused("d", "difference", ["a", "b", "c"]) == "operands"
    assert refused("d", "sum", ["a", "b"]) == "text_operand"
    assert refused("c", "sum", ["b", "b"]) == "column_in_use"
    room = Room.of(tab)
    room.build(
        calculate(tab, {"table": "t", "col": "d"}, {"operation": "quotient", "columns": ["c", "b"]})
    )
    assert values_in(room)[key_of("r2", "d")]["text"].startswith("0,50")


@pytest.mark.django_db
def test_group_sorts_the_data_and_subtotals_each_run_of_a_value_above_the_totals(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"), ("Vijak", "1", "1,5"))])
    room = grouped(tab, "a")
    table = table_in(room)
    rows = table.grid.rows
    assert rows[:2] == ["r1", "r3"] and rows[3:5] == ["r2", "r4"] and len(rows) == 7
    first, second, total = rows[2], rows[5], rows[6]
    formulas = table.grid.formulas
    assert tuple(formulas[key_of(first, "b")][:2]) == subtotal("r3", "r3")
    assert tuple(formulas[key_of(second, "c")][:2]) == subtotal("r2", "r4")
    assert tuple(formulas[key_of(total, "b")][:2]) == subtotal("r3", second)
    assert table.grid.formats[key_of(second, "c")] == PRICE
    cells = {(cell.row, cell.col): cell for cell in table.cells}
    labels = [
        (cells[(row, "a")].text, cells[(row, "a")].blocks[0].runs[0].marks)
        for row in (first, second, total)
    ]
    assert labels == [
        ("Matica ukupno", {"strong": {}}),
        ("Vijak ukupno", {"strong": {}}),
        ("Ukupno", {"strong": {}}),
    ]
    found = values_in(room)
    assert [found[key_of(row, "b")]["text"] for row in (first, second, total)] == ["2", "4", "6"]
    assert totals_row(None, room.grids["t"]) == total
    assert table.attrs["designs"][0]["on"] == {"totals": True}

    room.keep(tab)
    again = grouped(tab, "c")
    table = table_in(again)
    rows = table.grid.rows
    assert rows[:2] == ["r1", "r3"] and rows[3:5] == ["r2", "r4"] and rows[6] == total
    assert first not in rows and second not in rows
    label = next(cell for cell in table.cells if cell.row == rows[2] and cell.col == "c")
    assert label.text == "0,25 € ukupno"
    assert tuple(table.grid.formulas[key_of(total, "b")][:2]) == subtotal("r3", rows[5])
    assert values_in(again)[key_of(total, "b")]["text"] == "6"


@pytest.mark.django_db
def test_group_needs_another_column_of_numbers_and_a_column_of_the_table(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", ""), ("Matica", "2", ""))])
    for col, code in [("b", "no_numbers"), ("z", "no_line")]:
        with pytest.raises(Refused) as found:
            group(tab, {"table": "t", "col": col}, {})
        assert found.value.code == code


def cleaned(tab: Tab) -> Room:
    room = Room.of(tab)
    room.build(clean(tab, {"table": "t"}, {}))
    return room


@pytest.mark.django_db
def test_clean_trims_text_makes_numbers_of_numbers_kept_as_text_and_takes_out_empty_lines(api):
    tab = first_tab(api)
    rows, cols = ["r1", "r2", "r3", "r4", "r5"], list("abc")
    cells = [
        Cell("r1", "a", typed("Artikl", True)),
        Cell("r1", "b", typed("Količina", True)),
        Cell("r2", "a", [Block("paragraph", "p2", runs=[Run("  Vijak   M8 ", {"em": {}})])]),
        light_cell("r2:b", "'12"),
        light_cell("r3:a", "   "),
        light_cell("r4:a", " Matica"),
        light_cell("r4:b", "1 234,50"),
        light_cell("r5:a", "Šifra"),
        light_cell("r5:b", "'007"),
    ]
    fill(tab, [Block("table", "t", grid=Grid(rows, cols), cells=cells)])
    room = cleaned(tab)
    table = table_in(room)
    assert (table.grid.rows, table.grid.cols) == (["r1", "r2", "r4", "r5"], ["a", "b"])
    found = {(cell.row, cell.col): cell for cell in table.cells}
    vijak = found[("r2", "a")]
    assert vijak.light and [(run.text, run.marks) for run in vijak.blocks[0].runs] == [
        ("Vijak M8", {"em": {}})
    ]
    assert {
        key: found[key].text for key in [("r4", "a"), ("r2", "b"), ("r4", "b"), ("r5", "b")]
    } == {
        ("r4", "a"): "Matica",
        ("r2", "b"): "12",
        ("r4", "b"): "1234,50",
        ("r5", "b"): "'007",
    }
    room.keep(tab)
    calculation.calculate(tab.document, {"t"}, {})
    assert data_of(None, Room.of(tab).grids["t"], None, "hr").kinds["b"] == [
        "number",
        "number",
        "text",
    ]


@pytest.mark.django_db
def test_clean_keeps_merged_lines_and_those_a_reference_points_at_alone(api):
    tab = first_tab(api)
    cells = [
        Cell("r1", "a", typed("Naslov"), to="r1:b"),
        Cell("r2", "a", typed(""), to="r3:a"),
        light_cell("r4:b", "1"),
    ]
    alone = {"s1:a": [{"table": "t", "from": {"row": "r5", "col": "c"}}, "+1"]}
    fill(
        tab,
        [
            Block(
                "table",
                "t",
                grid=Grid(["r1", "r2", "r3", "r4", "r5", "r6"], list("abc")),
                cells=cells,
            ),
            Block("table", "s", grid=Grid(["s1"], ["a"], formulas=alone)),
        ],
    )
    room = cleaned(tab)
    table = table_in(room)
    assert (table.grid.rows, table.grid.cols) == (["r1", "r2", "r3", "r4", "r5"], list("abc"))
    room.keep(tab)
    with pytest.raises(Refused) as found:
        cleaned(tab)
    assert found.value.code == "clean"


def charted(tab: Tab, target: dict) -> Room:
    room = Room.of(tab)
    room.build(chart(tab, {"table": "t", **target}, {}))
    return room


def point(row: str, col: str) -> dict:
    return {"row": row, "col": col}


@pytest.mark.django_db
def test_a_chart_comes_just_after_the_table_over_its_data_or_the_cells_given(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", "1,5"), ("Matica", "2", "0,25"))])
    room = Room.of(tab)
    room.build(totals(tab, {"table": "t"}, {}))
    room.keep(tab)
    room = charted(tab, {})
    assert [block.type for block in room.read()] == ["table", "chart", "paragraph"]
    drawn = room.read()[1].attrs
    assert drawn["range"] == {"table": "t", "from": point("r1", "a"), "to": point("r3", "c")}
    assert drawn["by"] == "cols" and drawn.get("kind", "column") == "column"

    room.keep(tab)
    again = charted(tab, {"from": point("r2", "c"), "to": point("r1", "a")})
    content = again.read()
    assert [block.type for block in content] == ["table", "chart", "chart", "paragraph"]
    assert content[1].attrs["range"]["from"] == point("r1", "a")
    assert content[1].attrs["range"]["to"] == point("r2", "c")
    assert content[1].attrs["by"] == "rows"


@pytest.mark.django_db
def test_a_chart_needs_both_ends_of_its_cells_and_the_lines_they_were_given_on(api):
    tab = first_tab(api)
    fill(tab, [priced(("Vijak", "3", "1,5"))])
    action = ACTIONS["table.chart"]
    assert invalid(action, {"table": "t", "from": point("r1", "a")}, {}) == "invalid_target"
    with pytest.raises(Refused) as found:
        charted(tab, {"from": point("r1", "a"), "to": point("r9", "c")})
    assert found.value.code == "changed"


def test_proposals_are_accepted_or_rejected_by_their_ids_or_all_of_the_tabs():
    for verb in ("accept", "reject"):
        named, every = ACTIONS[f"proposal.{verb}"], ACTIONS[f"document.{verb}"]
        assert named.plan(None, {"ids": ["p1"]}, {}) == [{"op": verb, "ids": ["p1"]}]
        assert every.plan(None, {}, {}) == [{"op": verb}]
        assert invalid(named, {"ids": []}, {}) == "invalid_target"
        assert invalid(named, {}, {}) == "invalid_target"


@pytest.mark.django_db
def test_a_run_is_refused_an_unknown_action_a_wrong_target_and_a_reader(api, client):
    tab = first_tab(api)
    url = f"/api/tabs/{tab.pk}/runs"
    asked = {"action": "table.totals", "target": {"table": "t"}}
    for wrong, status in [
        ({"action": "table.nothing"}, 404),
        ({"target": {"table": "t", "row": "r"}}, 400),
        ({"target": "t"}, 400),
        ({"parameters": {"how": 1}}, 400),
    ]:
        assert api.post(url, asked | wrong, content_type=JSON).status_code == status
    assert not ActionRun.objects.exists()
    reader = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    client.force_login(reader)
    assert client.post(url, asked, content_type=JSON).status_code in (403, 404)


async def signed_in() -> tuple[AsyncClient, Tab]:
    user = await sync_to_async(User.objects.create_user)("ivo@example.com", "Kamen-Most-Rijeka-71")
    browser = AsyncClient()
    await browser.aforce_login(user)
    response = await browser.post(
        "/api/nodes", {"kind": "document", "title": "Ponuda"}, content_type=JSON
    )
    tab = await Tab.objects.select_related("document").aget(document_id=response.json()["id"])
    return browser, tab


async def rows_of(tab: Tab) -> list[str]:
    return await sync_to_async(server.read_grids)(
        tab.room, lambda room, held: held.grids()["t"].row_ids()
    )


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_run_is_kept_with_its_change_and_taken_back_once(live):
    browser, tab = await signed_in()
    await sync_to_async(fill)(tab, [priced(("Vijak", "3", "1,5"))])
    url = f"/api/tabs/{tab.pk}/runs"
    response = await browser.post(
        url, {"action": "table.totals", "target": {"table": "t"}}, content_type=JSON
    )
    assert response.status_code == 201, response.json()
    described = response.json()["run"]
    assert (described["action"], described["state"], described["changed"]) == (
        "table.totals",
        "done",
        True,
    )
    run = await ActionRun.objects.aget(pk=described["id"])
    assert run.finished_at is not None and await run.changes.acount() == 1
    assert len(await rows_of(tab)) == 3
    undo = f"/api/runs/{run.pk}/undo"
    response = await browser.post(undo)
    assert response.status_code == 200 and response.json()["run"]["state"] == "undone"
    assert await rows_of(tab) == ["r1", "r2"]
    response = await browser.post(undo)
    assert (response.status_code, response.json()["error"]) == (422, "not_done")

    await sync_to_async(fill)(tab, [priced(("Vijak", "", ""))])
    response = await browser.post(
        url, {"action": "table.totals", "target": {"table": "t"}}, content_type=JSON
    )
    assert (response.status_code, response.json()["error"]) == (422, "no_numbers")
    failed = await ActionRun.objects.exclude(pk=run.pk).aget()
    assert (failed.state, failed.error) == ("failed", "no_numbers: t")
    response = await browser.post(f"/api/runs/{failed.pk}/undo")
    assert (response.status_code, response.json()["error"]) == (422, "not_done")


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_run_whose_change_cannot_be_kept_takes_it_back(live, monkeypatch):
    browser, tab = await signed_in()
    await sync_to_async(fill)(tab, [priced(("Vijak", "3", "1,5"))])

    def refused(change, *args, **kwargs):
        raise RuntimeError("database")

    monkeypatch.setattr(RunChange, "save", refused)
    with pytest.raises(RuntimeError):
        await browser.post(
            f"/api/tabs/{tab.pk}/runs",
            {"action": "table.totals", "target": {"table": "t"}},
            content_type=JSON,
        )
    assert await rows_of(tab) == ["r1", "r2"]
    run = await ActionRun.objects.aget(document=tab.document)
    assert run.state == ActionRun.State.FAILED


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_run_shows_in_its_room_while_it_runs(live):
    _, tab = await signed_in()
    room = str(tab.room)
    to_server = create_memory_object_stream[bytes](256)
    to_client = create_memory_object_stream[bytes](256)
    async with create_task_group() as tg:
        tg.start_soon(live.serve, Endpoint(room, to_client[0], to_server[1]))
        assert (await to_client[1].receive())[0] == YMessageType.SYNC
        await until(lambda: room in live.rooms)
        presence = {"action": "table.totals", "user": {"id": 1, "name": "Ivo"}}
        await live.attend(room, "run", presence)
        await live.attend(room, "run", None)
        heard = Awareness(Doc())
        told = []
        for _ in range(2):
            message = await to_client[1].receive()
            assert message[0] == YMessageType.AWARENESS
            heard.apply_awareness_update(read_message(message[1:]), "server")
            told += [
                state["runs"] for client, state in heard.states.items() if client != heard.client_id
            ]
        assert told == [{"run": presence}, {}]
        to_server[0].close()
        await until(lambda: not live.rooms)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_an_action_reviewed_as_proposals_writes_them_under_the_user_who_runs_it(
    live, monkeypatch
):
    def plan(tab: Tab, target: dict, parameters: dict) -> list:
        content = [{"type": "text", "text": "kuće"}]
        return [{"op": "text", "range": {"block": "a", "from": 6, "to": 11}, "content": content}]

    proposing = Action("test.propose", "document", plan, review="propose")
    monkeypatch.setitem(ACTIONS, proposing.id, proposing)
    browser, tab = await signed_in()
    await sync_to_async(fill)(tab, [Block("paragraph", "a", runs=[Run("Najam stana")])])
    response = await browser.post(
        f"/api/tabs/{tab.pk}/runs", {"action": "test.propose", "target": {}}, content_type=JSON
    )
    assert response.status_code == 201, response.json()
    run = await ActionRun.objects.select_related("user").aget(pk=response.json()["run"]["id"])
    (block,) = (await sync_to_async(Room.of)(tab)).read()
    assert [(each.text, set(each.marks)) for each in block.runs] == [
        ("Najam ", set()),
        ("stana", {"deletion"}),
        ("kuće", {"insertion"}),
    ]
    change = block.runs[2].marks["insertion"]
    assert block.runs[1].marks["deletion"] == change
    date = run.started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert {**change, "id": ""} == {
        "id": "",
        "author": "ivo@example.com",
        "user": run.user.pk,
        "date": date,
    }


@pytest.mark.django_db
def test_an_administrator_sees_what_the_models_took_and_the_free_requests_but_not_whose(api):
    tab = first_tab(api)

    def made(action: str, **fields) -> ActionRun:
        return ActionRun.objects.create(
            document=tab.document, user=api.user, action=action, target={}, **fields
        )

    tokens = {"input_tokens": 1000, "output_tokens": 100, "cache_read_tokens": 10}
    made("text.summarise", model="claude-sonnet-5-5", cost=Decimal("0.003"), **tokens)
    made("text.summarise", model="claude-opus-9", cost=None, **tokens)
    for request in ("Skrati  tekst.", " skrati tekst. ", "Prevedi."):
        made(
            "text.ask",
            model="claude-opus-5-5",
            cost=Decimal("0.01"),
            parameters={"request": request},
        )
    made("table.sort")
    old = made("text.ask", model="claude-opus-5-5", parameters={"request": "Staro."})
    ActionRun.objects.filter(pk=old.pk).update(started_at=timezone.now() - timedelta(days=400))
    assert api.get("/api/runs/usage").status_code == 403
    api.user.is_staff = True
    api.user.save()
    found = api.get("/api/runs/usage").json()
    month = timezone.localtime().strftime("%Y-%m")
    assert found["spent"] == [
        {
            "month": month,
            "action": "text.ask",
            "runs": 3,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost": 0.03,
            "unpriced": 0,
        },
        {
            "month": month,
            "action": "text.summarise",
            "runs": 2,
            "input_tokens": 2000,
            "output_tokens": 200,
            "cache_read_tokens": 20,
            "cache_write_tokens": 0,
            "cost": 0.003,
            "unpriced": 1,
        },
    ]
    first, second = found["requests"]
    assert first["text"] in {"Skrati  tekst.", " skrati tekst. "} and first["times"] == 2
    assert (second["text"], second["times"]) == ("Prevedi.", 1)
    assert set(first) == {"text", "times", "last"}
