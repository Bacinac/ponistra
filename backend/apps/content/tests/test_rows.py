import random

import pytest

from apps.content import grids, rows
from apps.content.grids import Col, Laid, Row, apply
from apps.content.models import Grid
from apps.documents.models import Node, Tab


def stored(size: int, seed: int) -> tuple[Node, int, Laid]:
    """A table of the size given whose second column refers to other rows of its own, relative,
    absolute and to its own row, as a seed draws them, stored and read back whole."""
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Redovi")
    tab = Tab.objects.create(document=document, position=0)
    draw = random.Random(seed)
    ids = [f"r{y}" for y in range(size)]
    laid = Laid("t", tab.pk, "Redovi", [Col("c0"), Col("c1")])
    for y, id in enumerate(ids):
        cells = {"c0": {"text": str(y)}}
        target = ids[min(max(y + draw.randint(-5, 5), 0), size - 1)]
        point = {"row": target, "col": "c0", **({"absRow": True} if draw.random() < 0.2 else {})}
        formula = ["2*", {"from": point}, "+", {"from": {"row": id, "col": "c0"}}]
        cells["c1"] = {"formula": grids.formula_at(formula, id, "c1")}
        laid.rows.append(Row(id, cells=cells))
    grids.store(document, apply(None, grids.made(laid)))
    grid = Grid.objects.get(document=document, table="t").pk
    return document, grid, grids.of_tab(tab)["t"]


@pytest.mark.django_db
@pytest.mark.parametrize("seed", [1, 2])
def test_rows_read_by_place_or_id_are_the_rows_of_the_grid_read_whole(seed):
    document, grid, whole = stored(300, seed)
    order = whole.row_ids()
    assert rows.count(grid) == 300
    assert rows.ids_in(grid, 40, 49) == order[40:50]
    assert rows.ids_in(grid, 295, 400) == order[295:]
    assert rows.ids_at(grid, [0, 3, 150, 299, 300]) == {
        0: order[0],
        3: order[3],
        150: order[150],
        299: order[299],
    }
    picked = random.Random(seed).sample(order, 30)
    assert rows.places_of(grid, [*picked, "none"]) == {id: order.index(id) for id in picked}

    for found in (rows.read(document, grid, span=(100, 160)), rows.read(document, grid, picked)):
        for id, (place, row) in found.items():
            assert place == order.index(id)
            assert row.cells == whole.row(id).cells


@pytest.mark.django_db
def test_a_reference_to_a_row_taken_out_reads_as_the_grid_read_whole_does():
    document, grid, whole = stored(20, 3)
    laid = whole.copy()
    first = laid.row_ids()[0]
    laid.own("r5").cells["c1"] = {
        "formula": grids.formula_at(["2*", {"from": {"row": first, "col": "c0"}}], "r5", "c1")
    }
    grids.store(document, apply(whole, grids.diff(whole, laid)))
    laid = grids.of_document(document)["t"]
    gone = laid.copy()
    gone.rows = [row for row in gone.rows if row.id != first]
    grids.store(document, apply(laid, grids.diff(laid, gone)))
    ((place, row),) = rows.read(document, grid, ["r5"]).values()
    assert row.cells == grids.of_document(document)["t"].row("r5").cells
    assert row.cells["c1"]["formula"][1]["from"]["row"] == first
