import json

import pytest

from apps.blobs.tests.test_blobs import content
from apps.collab import server
from apps.content import blocks, grids
from apps.content.blocks import Block, Cell, Grid
from apps.content.models import GridRow
from apps.content.operations import Refused
from apps.jobs.tests.handed import refused as refused_export

from .helpers import fill
from .test_elements import first_tab
from .test_sort import typed

pytestmark = pytest.mark.django_db(transaction=True)

ROWS = ["r1", "r2", "r3", "r4"]


def table(**at) -> Block:
    return Block(
        "table",
        "t",
        grid=Grid(ROWS, ["a", "b"]),
        cells=[Cell("r1", "a", typed("1")), Cell("r3", "a", typed("3"), **at)],
    )


def test_the_grids_printed_come_as_a_stream_without_their_hidden_rows(api):
    tab = first_tab(api)
    fill(tab, [table()])
    GridRow.objects.filter(grid__table="t", row="r2").update(hidden=True)
    [grid] = json.loads(content(api.get(f"/api/tabs/{tab.pk}/grids")))["grids"]
    assert grid["ids"] == ["r1", "r3", "r4"] and grid["rows"] == 3
    assert grid["numbers"] == {"r1": 0, "r3": 2, "r4": 3}
    assert set(grid["cells"]) == {"r1", "r3", "r4"}


def test_word_and_powerpoint_refuse_a_table_over_the_ceiling(api, monkeypatch):
    tab = first_tab(api)
    fill(tab, [table()])
    monkeypatch.setattr(grids, "MOST_CELLS", 7)
    assert refused_export(api, "docx", document=tab.document_id) == (413, "table_too_large")
    assert grids.small_of_tab(tab) == {}


def test_a_reader_of_the_whole_table_is_refused_and_one_that_may_stop_reads_the_first_rows(
    api, monkeypatch
):
    tab = first_tab(api)
    fill(tab, [table()])
    monkeypatch.setattr(grids, "MOST_CELLS", 4)
    with pytest.raises(Refused) as found:
        server.read_grids(tab.room, lambda doc, held: blocks.read(doc, held.grids()))
    assert found.value.code == "cells_over_ceiling"

    def cut(doc, held):
        whole = held.grids(cut=True)
        return whole["t"].row_ids(), whole.parted

    assert server.read_grids(tab.room, cut)[0] == ["r1", "r2"]


def test_elements_read_only_the_rows_that_bear_on_placing_and_know_the_order_of_all(api):
    tab = first_tab(api)
    fill(tab, [table(to="r4:a")])
    laid = grids.placing_of_tab(tab)["t"]
    assert laid.row_ids() == ROWS and [row.id for row in laid.rows] == ["r3"]
