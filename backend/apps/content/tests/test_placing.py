from apps.content import blocks, charts, placing
from apps.content.blocks import Block, Cell, Grid, Run

from .helpers import written


def chart(id: str, bottom: str) -> Block:
    range = {"table": "t", "from": {"row": "r1", "col": "a"}, "to": {"row": bottom, "col": "a"}}
    return Block("chart", id, {"range": range, "kind": "column"})


def test_a_live_tabs_text_is_followed_by_the_text_of_its_tables_cells_and_its_charts():
    typed = Cell("r1", "a", [Block("paragraph", runs=[Run("2"), Run("0", {"strong": {}})])])
    table = Block("table", "t", grid=Grid(["r1", "r2"], ["a"]), cells=[typed])
    doc, _ = written([table, chart("c", "r1")])
    told = []
    follower = placing.Follower(doc, lambda *given: told.append(given))
    assert follower.placing == placing.of(doc)
    assert (follower.placing.tables, follower.placing.nodes) == (["t"], {"t": {"r1:a": "20"}})
    assert follower.placing.charts == {
        "c": charts.Chart("t", "r1", "a", "r1", "a", "cols", False, None, None)
    }
    body = blocks.body_of(doc)
    body.children[0].children[0].children[0].children[0].insert(1, "5")
    [(now, texts, moved)] = told
    assert (now.nodes, texts, moved) == ({"t": {"r1:a": "250"}}, {"t": {"r1:a"}}, False)
    body.children[1].attributes["kind"] = "line"
    assert len(told) == 1
    body.children[1].attributes["range"] = chart("c", "r2").attrs["range"]
    assert told[-1][1:] == ({}, True)
    assert told[-1][0].charts["c"].bottom == "r2"
    del body.children[0]
    assert told[-1][1:] == ({}, True)
    assert (told[-1][0].tables, told[-1][0].nodes) == ([], {})
    follower.close()
    body.children[0].attributes["range"] = chart("c", "r1").attrs["range"]
    assert len(told) == 3
