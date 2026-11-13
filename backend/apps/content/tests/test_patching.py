import random

import pytest

from apps.content import grids, patching
from apps.content.grids import Col, Laid, Row
from apps.content.models import Grid, GridRow, KeptRow
from apps.content.table import tables_of
from apps.documents.models import Node, Tab


def _formula(draw: random.Random, ids: list[str], y: int, id: str) -> list:
    target = ids[min(max(y + draw.randint(-5, 5), 0), len(ids) - 1)]
    point = {"row": target, "col": "c0", **({"absRow": True} if draw.random() < 0.2 else {})}
    span = ids[min(max(y + draw.randint(-4, 0), 0), len(ids) - 1)]
    return [
        "2*",
        {"from": point},
        "+SUM(",
        {"from": {"row": span, "col": "c0"}, "to": {"row": id, "col": "c0"}},
        ")",
    ]


def built(size: int, seed: int) -> Node:
    """A table whose second column refers to rows near and far, relative and absolute, as the
    seed draws them, with a frozen row, a height, a look and a hidden row."""
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Redovi")
    tab = Tab.objects.create(document=document, position=0)
    draw = random.Random(seed)
    ids = [f"r{y}" for y in range(size)]
    laid = Laid("t", tab.pk, "Redovi", [Col("c0"), Col("c1"), Col("c2", 80)])
    laid.frozen = ids[3]
    for y, id in enumerate(ids):
        cells = {"c0": {"text": str(y)}}
        if draw.random() < 0.8:
            formula = _formula(draw, ids, y, id)
            cells["c1"] = {"formula": grids.formula_at(formula, id, "c1")}
        laid.rows.append(Row(id, cells=cells))
    laid.rows[7].height = 30.0
    laid.rows[9].look = grids.look({"bold": True})
    laid.rows[11].hidden = True
    grids.store(document, grids.apply(None, grids.made(laid)))
    return document


def kept(document) -> list[tuple]:
    grid = Grid.objects.get(document=document, table="t")
    rows = GridRow.objects.filter(grid=grid).order_by("position")
    return [grid.frozen, grid.cols] + [
        (row.row, row.height, row.look, row.hidden, row.cells) for row in rows
    ]


def edited(laid: Laid, draw: random.Random, serial: int) -> tuple[Laid, list]:
    """A row edit drawn at random, as a grid changed whole and as the edit a draft notes."""
    after = laid.copy()
    ids = after.row_ids()
    kind = draw.choice(["out", "put", "order"] if len(ids) > 40 else ["put", "order"])
    if kind == "out":
        places = set()
        for _ in range(draw.randint(1, 3)):
            first = draw.randrange(len(ids))
            places |= set(range(first, min(first + draw.choice([1, 2, 5, 14, 30]), len(ids))))
        places.discard(0)
        after.rows = [row for at, row in enumerate(after.rows) if at not in places]
        if after.frozen not in after.row_ids():
            above = [id for at, id in enumerate(ids) if at < ids.index(laid.frozen)]
            after.frozen = next((id for id in reversed(above) if id in after.row_ids()), None)
        return after, ["out", sorted(places)]
    if kind == "put":
        at = draw.randint(0, len(ids))
        made = [f"n{serial}_{offset}" for offset in range(draw.choice([1, 3, 12]))]
        order = ids[:at] + made + ids[at:]
        rows = []
        for offset, id in enumerate(made):
            y = at + offset
            cells = {"c0": {"text": id}}
            cells["c1"] = {"formula": grids.formula_at(_formula(draw, order, y, id), id, "c1")}
            rows.append(Row(id, cells=cells, height=12.0 if offset == 0 else None))
        after.rows[at:at] = rows
        lines = [[row.id, {"size": row.height, "cells": row.cells}] for row in rows]
        return after, ["put", at, lines]
    first = draw.randrange(len(ids) - 1)
    span = ids[first : first + draw.choice([2, 6, 20, 40])]
    turned = list(span)
    draw.shuffle(turned)
    rows = {row.id: row for row in after.rows}
    after.rows[first : first + len(span)] = [rows[id] for id in turned]
    return after, ["order", first, turned]


def _same(old, new):
    assert len(old) == len(new)
    assert old[:2] == new[:2]
    for a, b in zip(old[2:], new[2:], strict=True):
        assert a == b


@pytest.mark.django_db
@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_rows_put_taken_and_reordered_as_sql_store_what_the_grid_changed_whole_does(seed):
    old, new = built(90, seed), built(90, seed)
    draw = random.Random(seed * 7)
    done = []
    for serial in range(12):
        laid = grids.of_document(old)["t"]
        after, edit = edited(laid, draw, serial)
        table = tables_of(new)["t"]
        went = patching.apply(new, table, {"table": "t", "rows": {"edits": [edit]}})
        if (patch := grids.diff(laid, after)) is None:
            assert went.patch is None
            continue
        grids.store(old, grids.apply(laid, patch))
        done.append(went.patch)
        _same(kept(old), kept(new))
        assert went.table == tables_of(new)["t"]
    first = built(90, seed)
    for patch in reversed(done):
        went = patching.apply(new, tables_of(new)["t"], patching.inverse(patch), guard=True)
        assert went.patch is not None
    assert grids.of_document(new)["t"].row_ids() == grids.of_document(first)["t"].row_ids()
    _same(
        [row[:1] + row[1:] for row in kept(first)],
        [row[:1] + row[1:] for row in kept(new)],
    )
    assert KeptRow.objects.filter(document=new).exists()


@pytest.mark.django_db
def test_cells_heights_looks_and_columns_as_sql_store_what_the_grid_changed_whole_does():
    old, new = built(40, 9), built(40, 9)
    laid = grids.of_document(old)["t"]
    after = laid.copy()
    ids = after.row_ids()
    after.own(ids[5]).cells["c2"] = {
        "formula": grids.formula_at(["1+", {"from": {"row": ids[2], "col": "c0"}}], ids[5], "c2")
    }
    after.own(ids[6]).height = 44.0
    after.own(ids[7]).look = grids.look({"italic": True})
    after.own(ids[8]).hidden = True
    after.cols = [after.cols[1], after.cols[0], Col("c3", 50)]
    patch = grids.diff(laid, after)
    grids.store(old, grids.apply(laid, patch))
    went = patching.apply(new, tables_of(new)["t"], patch)
    _same(kept(old), kept(new))
    assert went.table == tables_of(new)["t"]
    back = patching.apply(new, went.table, patching.inverse(went.patch), guard=True)
    _same(kept(built(40, 9)), kept(new))
    assert back.table == tables_of(new)["t"]
