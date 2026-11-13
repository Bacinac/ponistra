import json

import pytest

from apps.blobs.tests.test_blobs import content
from apps.content.blocks import Block, Cell, Grid

from .helpers import fill
from .test_elements import first_tab
from .test_sort import typed

ROWS = ["r1", "r2", "r3", "r4"]
SUMMED = ["SUM(", {"from": {"row": "r1", "col": "a"}, "to": {"row": "r2", "col": "a"}}, ")"]


def table(formulas: dict, formats: dict | None = None) -> Block:
    return Block(
        "table",
        "t",
        grid=Grid(ROWS, ["a", "b"], formulas=formulas, formats=formats or {}),
        cells=[Cell("r1", "a", typed("1,5")), Cell("r2", "a", typed("2"))],
    )


@pytest.mark.django_db
def test_a_tabs_grids_come_whole_with_what_their_cells_show_to_whoever_may_read_it(api, client):
    tab = first_tab(api)
    summed = Block(
        "table",
        "t",
        grid=Grid(ROWS, ["a", "b"], formulas={"r3:a": SUMMED}),
        cells=[Cell("r1", "a", typed("1,5")), Cell("r2", "a", typed("2"))],
    )
    fill(tab, [summed])
    tab.grids.create(document=tab.document, table="gone")
    response = api.get(f"/api/tabs/{tab.pk}/grids")
    assert response.status_code == 200
    [grid] = json.loads(content(response))["grids"]
    assert (grid["table"], grid["rows"], grid["ids"]) == ("t", len(ROWS), ROWS)
    assert grid["cells"]["r1"] == {
        "cells": {"a": {"text": "1,5"}},
        "values": {"a": {"text": "1,5", "kind": "number"}},
    }
    assert grid["cells"]["r3"] == {
        "cells": {"a": {"formula": "=SUM(A1:A2)"}},
        "values": {"a": {"text": "3,5", "kind": "number"}},
    }
    own = content(api.get(f"/api/nodes/{tab.document_id}/grids"))
    assert json.loads(own) == {"grids": [], "looks": {}}
    client.logout()
    assert api.get(f"/api/tabs/{tab.pk}/grids").status_code in (401, 403, 404)
