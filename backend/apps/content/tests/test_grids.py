import importlib
from itertools import pairwise

import pytest
from django.apps import apps as django_apps
from django.contrib.postgres.search import SearchQuery

from apps.content import grids, sheets, words
from apps.content import rows as stored
from apps.content.grids import Col, Laid, Row, apply, diff, inverse
from apps.content.models import GridRow, GridRowWords, Shared, StaleGridRow
from apps.documents.models import Node, Tab
from apps.search.text import CONFIG


def grid(rows: int = 3, cols: int = 2) -> Laid:
    return Laid(
        "t",
        name="Cijene",
        cols=[Col(f"c{x}") for x in range(cols)],
        rows=[Row(f"r{y}", cells={"c0": {"text": f"{y}"}}) for y in range(rows)],
    )


def changed(laid: Laid) -> Laid:
    after = laid.copy()
    after.rows.insert(1, Row("new", 18.0, {"c1": {"text": "umetnut"}}))
    del after.rows[3]
    after.own("r0").cells["c1"] = {
        "formula": grids.formula_at(["SUM(", {"from": {"row": "r0", "col": "c0"}}, ")"], "r0", "c1")
    }
    after.cols[1].width = 12.0
    after.name = "Popis"
    after.frozen = "new"
    return after


def test_a_patch_turns_the_grid_into_the_one_it_was_made_from_and_back():
    before = grid()
    after = changed(before)
    patch = diff(before, after)
    forward = apply(before, patch)
    assert forward.laid.row_ids() == after.row_ids()
    assert forward.laid.rows[0].cells == after.rows[0].cells
    assert forward.laid.cols[1].width == 12.0
    assert forward.laid.name == "Popis" and forward.laid.frozen == "new"
    back = apply(forward.laid, inverse(forward.patch))
    assert back.laid.row_ids() == before.row_ids() and back.laid.frozen is None
    assert [row.cells for row in back.laid.rows] == [row.cells for row in before.rows]
    assert back.laid.cols[1].width is None
    assert back.laid.name == "Cijene"


def test_taken_back_with_a_guard_keeps_what_somebody_wrote_since():
    before = grid()
    after = before.copy()
    after.own("r0").cells["c0"] = {"text": "moje"}
    after.own("r1").cells["c0"] = {"text": "moje"}
    forward = apply(before, diff(before, after))
    since = forward.laid.copy()
    since.own("r1").cells["c0"] = {"text": "tuđe"}
    back = apply(since, inverse(forward.patch), guard=True)
    assert back.laid.rows[0].cells["c0"] == {"text": "0"}
    assert back.laid.rows[1].cells["c0"] == {"text": "tuđe"}
    assert back.patch["cells"] == {"r0": {"c0": [{"text": "moje"}, {"text": "0"}]}}


def test_a_line_taken_out_comes_back_where_it_stood_with_its_cells():
    before = grid(4)
    after = before.copy()
    del after.rows[2]
    del after.cols[0]
    forward = apply(before, diff(before, after))
    assert forward.laid.row_ids() == ["r0", "r1", "r3"]
    assert all("c0" not in row.cells for row in forward.laid.rows)
    back = apply(forward.laid, inverse(forward.patch), guard=True)
    assert back.laid.row_ids() == ["r0", "r1", "r2", "r3"]
    assert back.laid.col_ids() == ["c0", "c1"]
    assert [row.cells for row in back.laid.rows] == [row.cells for row in before.rows]


def test_lines_taken_out_side_by_side_come_back_in_their_order():
    before = grid(5)
    after = before.copy()
    after.rows = [row for row in after.rows if row.id not in {"r1", "r2", "r3"}]
    forward = apply(before, diff(before, after))
    back = apply(forward.laid, inverse(forward.patch), guard=True)
    assert back.laid.row_ids() == ["r0", "r1", "r2", "r3", "r4"]


def test_a_cell_written_in_a_long_grid_copies_only_its_row():
    before = grid(100_000)
    grids._space(before)
    after = before.copy()
    after.own("r500").cells["c1"] = {"text": "x"}
    forward = apply(before, diff(before, after))
    assert forward.dirty == {"r500"}
    pairs = enumerate(zip(before.rows, forward.laid.rows, strict=True))
    changed = [at for at, (a, b) in pairs if a is not b]
    assert changed == [500]
    assert before.cell("r500", "c1") == {}


def test_reordered_rows_patch_only_the_stretch_that_moved():
    before = grid(6)
    grids._space(before)
    after = before.copy()
    after.rows[1], after.rows[3] = after.rows[3], after.rows[1]
    patch = diff(before, after)
    assert patch["rows"] == {"order": [["r1", "r2", "r3"], ["r3", "r2", "r1"]]}
    forward = apply(before, patch)
    assert forward.laid.row_ids() == ["r0", "r3", "r2", "r1", "r4", "r5"]
    positions = [row.position for row in forward.laid.rows]
    assert positions == sorted(positions)


def test_rows_put_in_between_take_positions_between_their_neighbours():
    before = grid(2)
    grids._space(before)
    after = before.copy()
    after.rows.insert(1, Row("a"))
    after.rows.insert(2, Row("b"))
    forward = apply(before, diff(before, after))
    positions = [row.position for row in forward.laid.rows]
    assert positions == sorted(set(positions))
    assert forward.dirty == {"a", "b"}
    assert not forward.spaced


@pytest.mark.django_db
def test_stored_patches_read_back_as_the_grid_they_made():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik")
    tab = Tab.objects.create(document=document, position=0)
    laid = grid()
    laid.tab = tab.pk
    made = apply(None, grids.made(laid))
    grids.store(document, made)
    after = changed(made.laid)
    forward = apply(made.laid, diff(made.laid, after))
    grids.store(document, forward)
    read = grids.of_tab(tab)["t"]
    assert read.row_ids() == after.row_ids()
    assert [row.cells for row in read.rows] == [row.cells for row in after.rows]
    assert read.name == "Popis" and read.cols[1].width == 12.0 and read.frozen == "new"
    back = apply(read, inverse(forward.patch), guard=True)
    grids.store(document, back)
    again = grids.of_tab(tab)["t"]
    assert again.row_ids() == laid.row_ids() and again.frozen is None
    assert GridRow.objects.filter(grid__table="t").count() == 3


@pytest.mark.django_db
def test_a_formula_filled_down_is_kept_once_its_own_row_written_as_such():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik")
    tab = Tab.objects.create(document=document, position=0)
    laid = grid()
    laid.tab = tab.pk
    for row in laid.rows:
        pieces = ["2*", {"from": {"row": row.id, "col": "c0"}}]
        row.cells["c1"] = {"formula": grids.formula_at(pieces, row.id, "c1")}
    filled = [row.cells["c1"]["formula"] for row in laid.rows]
    assert filled[0] == ["2*", {"from": {"row": "@", "col": "c0"}}]
    assert all(formula is filled[0] for formula in filled)
    made = apply(None, grids.made(laid))
    grids.store(document, made)
    assert {row.cells["c1"]["formula"] for row in GridRow.objects.all()} == {filled[0].key}
    assert Shared.objects.get(document=document).value == filled[0]
    read = grids.of_tab(tab)["t"]
    assert len({id(row.cells["c1"]["formula"]) for row in read.rows}) == 1
    assert grids.formula_in(read.own("r2").cells["c1"]["formula"], "r2", "c1") == [
        "2*",
        {"from": {"row": "r2", "col": "c0"}},
    ]
    after = read.copy()
    for row in laid.row_ids():
        after.own(row).cells["c1"] = {"text": "ručno"}
    grids.store(document, apply(read, diff(read, after)))
    assert Shared.objects.filter(document=document).count() == 1
    stored.unshare(document, set())
    assert not Shared.objects.filter(document=document).exists()


def doubled(row: str, target: str, **point) -> grids.Formula:
    return grids.formula_at(["2*", {"from": {"row": target, "col": "c0", **point}}], row, "c1")


def targets(laid: Laid) -> dict[str, str | None]:
    return {
        row.id: grids.formula_in(row.cells["c1"]["formula"], row.id, "c1")[1]["from"]["row"]
        for row in laid.rows
        if "c1" in row.cells
    }


def kept(document: Node) -> list:
    return sorted(
        (
            value
            for value in Shared.objects.filter(document=document).values_list("value", flat=True)
        ),
        key=str,
    )


@pytest.mark.django_db
def test_a_reference_to_the_row_above_filled_down_is_kept_once_and_follows_its_row():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik")
    tab = Tab.objects.create(document=document, position=0)
    laid = grid(4)
    laid.tab = tab.pk
    for above, row in pairwise(laid.rows):
        row.cells["c1"] = {"formula": doubled(row.id, above.id)}
    grids.store(document, apply(None, grids.made(laid)))
    above = ["2*", {"from": {"row": -1, "col": "c0"}}]
    assert kept(document) == [above]
    read = grids.of_tab(tab)["t"]
    assert targets(read) == {"r1": "r0", "r2": "r1", "r3": "r2"}

    after = read.copy()
    after.rows.insert(2, Row("new"))
    del after.rows[0]
    put = apply(read, diff(read, after))
    grids.store(document, put)
    read = grids.of_tab(tab)["t"]
    assert targets(read) == {"r1": "r0", "r2": "r1", "r3": "r2"}
    stored.unshare(document, set())
    gone, between = (
        ["2*", {"from": {"row": "r0", "col": "c0"}}],
        ["2*", {"from": {"row": -2, "col": "c0"}}],
    )
    assert kept(document) == sorted([above, gone, between], key=str)

    after = read.copy()
    after.rows.insert(0, after.rows.pop())
    moved = apply(read, diff(read, after))
    grids.store(document, moved)
    read = grids.of_tab(tab)["t"]
    assert read.row_ids() == ["r3", "r1", "new", "r2"]
    assert targets(read) == {"r3": "r2", "r1": "r0", "r2": "r1"}

    for patch in (moved.patch, put.patch):
        back = apply(read, inverse(patch), guard=True)
        grids.store(document, back)
        read = grids.of_tab(tab)["t"]
    assert read.row_ids() == laid.row_ids()
    assert targets(read) == {"r1": "r0", "r2": "r1", "r3": "r2"}
    stored.unshare(document, set())
    assert kept(document) == [above]


def test_a_reference_absolute_to_its_own_row_another_table_or_a_row_gone_is_kept_by_its_id():
    ids = ["r0", "r1", "r2"]
    at = {row: index for index, row in enumerate(ids)}
    pieces = [
        {"from": {"row": "r1", "col": "c0", "absRow": True}},
        "+",
        {"table": "u", "from": {"row": "r2", "col": "c0"}},
        "+",
        {"from": {"row": "r9", "col": "c0"}},
        "+",
        {"from": {"row": "r0", "col": "c0", "absRow": True}, "to": {"row": "r2", "col": "c0"}},
    ]
    held = grids.formula_at(pieces, "r1", "c1")
    stored = grids.stored_formula(held, "r1", at)
    assert stored == [
        *pieces[:-1],
        {"from": {"row": "r0", "col": "c0", "absRow": True}, "to": {"row": 1, "col": "c0"}},
    ]
    assert grids.held_formula(stored, "r1", "c1", 1, ids) == held
    beyond = grids.formula_at(["2*", {"from": {"row": -2, "col": "c0"}}], "r1", "c1")
    assert grids.held_formula(beyond, "r1", "c1", 1, ids) == [
        "2*",
        {"from": {"row": None, "col": "c0"}},
    ]


@pytest.mark.django_db
def test_formulas_kept_by_row_ids_are_kept_by_distance_once_migrated():
    distances = importlib.import_module("apps.content.migrations.0010_distances")
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik")
    tab = Tab.objects.create(document=document, position=0)
    laid = grid()
    laid.tab = tab.pk
    grids.store(document, apply(None, grids.made(laid)))
    first = ["2*", {"from": {"row": "r0", "col": "c0"}}]
    own = ["2*", {"from": {"row": "@", "col": "c0", "absRow": True}}]
    for row, pieces in (("r1", first), ("r2", first), ("r0", own)):
        Shared.objects.get_or_create(document=document, key=grids.digest(pieces), value=pieces)
        GridRow.objects.filter(row=row).update(cells={"c1": {"formula": grids.digest(pieces)}})

    distances.distance(django_apps, None)

    assert kept(document) == sorted(
        [
            ["2*", {"from": {"row": -1, "col": "c0"}}],
            ["2*", {"from": {"row": -2, "col": "c0"}}],
            ["2*", {"from": {"row": "r0", "col": "c0", "absRow": True}}],
        ],
        key=str,
    )
    read = grids.of_tab(tab)["t"]
    assert targets(read) == {"r0": "r0", "r1": "r0", "r2": "r0"}


@pytest.mark.django_db
def test_search_finds_what_a_row_shows_once_its_words_are_read_again_after_a_write():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik")
    tab = Tab.objects.create(document=document, position=0)
    laid = grid()
    laid.tab = tab.pk
    grids.store(document, apply(None, grids.made(laid)))
    words.read()
    assert GridRowWords.objects.count() == 3 and not StaleGridRow.objects.exists()
    second = GridRow.objects.get(row="r1")
    GridRow.objects.filter(pk=second.pk).update(shown={"c1": "Rijeka"})
    found = GridRowWords.objects.filter(words=SearchQuery("Rijeka", config=CONFIG))
    assert not found.exists()
    assert list(StaleGridRow.objects.values_list("grid_row", flat=True)) == [second.pk]
    words.read()
    assert list(found.values_list("grid_row", flat=True)) == [second.pk]
    assert not StaleGridRow.objects.exists()


def test_frozen_rows_grow_with_rows_put_above_their_last_and_end_above_it_taken_out():
    before = grid(4)
    before.frozen = "r1"
    after = before.copy()
    after.rows.insert(1, Row("new"))
    grown = apply(before, diff(before, after))
    assert "frozen" not in grown.patch and grown.laid.frozen == "r1"
    taken = apply(grown.laid, {"table": "t", "rows": {"out": [["r1"], ["new"]]}})
    assert taken.laid.frozen == "r0" and taken.patch["frozen"] == ["r1", "r0"]
    back = apply(taken.laid, inverse(taken.patch), guard=True).laid
    assert back.frozen == "r1" and back.row_ids() == grown.laid.row_ids()
    assert (
        apply(back, {"table": "t", "rows": {"out": [["r0"], ["new"], ["r1"]]}}).laid.frozen is None
    )
    with pytest.raises(ValueError):
        apply(back, {"table": "t", "frozen": ["r1", "gone"]})
    assert apply(back, {"table": "t", "frozen": ["r0", "r2"]}, guard=True).patch is None


@pytest.mark.django_db
def test_a_row_and_a_column_keep_their_looks_which_a_patch_changes_and_takes_back():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik")
    tab = Tab.objects.create(document=document, position=0)
    laid = grid()
    laid.tab = tab.pk
    bold = grids.look({"marks": {"strong": {}}})
    centred = grids.look({"attrs": {"align": "center"}})
    laid.cols[1].look = bold
    grids.store(document, apply(None, grids.made(laid)))
    read = grids.of_tab(tab)["t"]
    assert read.cols[1].look == bold and read.look_at("r0", "c1") == bold
    after = read.copy()
    after.own("r1").look = centred
    after.rows.insert(1, Row("new", look=centred))
    forward = apply(read, diff(read, after))
    assert forward.patch["looks"] == {"rows": {"r1": [None, centred]}}
    grids.store(document, forward)
    again = grids.of_tab(tab)["t"]
    assert again.rows[1].look == centred and again.look_at("r1", "c1") == centred
    assert GridRow.objects.get(row="r1").look == centred.key
    back = apply(again, inverse(forward.patch), guard=True)
    assert back.laid.row_ids() == laid.row_ids() and back.laid.row("r1").look is None
    grids.store(document, back)
    stored.unshare(document, set())
    assert [shared.value for shared in Shared.objects.filter(document=document)] == [bold]


@pytest.mark.django_db
def test_a_hidden_row_keeps_its_height_through_a_patch_a_version_and_being_put_back():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cjenik")
    tab = Tab.objects.create(document=document, position=0)
    laid = grid(4)
    laid.tab = tab.pk
    laid.rows[1].height, laid.rows[1].hidden = 30.0, True
    grids.store(document, apply(None, grids.made(laid)))
    read = grids.of_tab(tab)["t"]
    assert read.hidden() == {"rows": ["r1"]} and read.row("r1").height == 30.0
    after = read.copy()
    after.own("r1").hidden = False
    after.cols[0].hidden = True
    forward = apply(read, diff(read, after))
    assert forward.patch["hidden"] == {"rows": {"r1": [True, False]}, "cols": {"c0": [False, True]}}
    grids.store(document, forward)
    again = grids.of_tab(tab)["t"]
    assert again.hidden() == {"cols": ["c0"]} and again.row("r1").height == 30.0
    back = apply(again, inverse(forward.patch), guard=True).laid
    assert back.hidden() == {"rows": ["r1"]}
    back.cols[1].look = grids.look({"marks": {"strong": {}}})
    found: dict = {}
    at = back.at()
    rows = [
        grids.kept_line(
            row.id,
            row.height,
            grids.encoded(row.cells, row.id, at, found),
            {},
            {},
            grids.keyed(row.look, found),
            row.hidden,
        )
        for row in back.rows
    ]
    cols = grids.kept_cols(back, found)
    kept = grids.from_whole(
        "t",
        {
            "rows": grids.unkept_rows(rows, found),
            "cols": [grids.unkept_col(col, found) for col in cols],
        },
    )
    assert kept.hidden() == {"rows": ["r1"]} and kept.cols[1].look == back.cols[1].look
    taken = back.copy()
    taken.rows = [row for row in taken.rows if row.id != "r1"]
    out = apply(back, diff(back, taken))
    returned = apply(out.laid, inverse(out.patch), guard=True).laid.row("r1")
    assert returned.hidden and returned.height == 30.0


def test_a_cell_keeps_a_look_only_where_its_line_gives_it_another():
    laid = grid()
    laid.cols[1].look = grids.look({"marks": {"strong": {}}})
    sheets.write(laid, "r0", "c1", {"text": "x", "look": {"marks": {"strong": {}}}})
    assert laid.row("r0").cells["c1"] == {"text": "x"}
    sheets.write(laid, "r0", "c1", {"look": {}})
    assert laid.row("r0").cells["c1"] == {"text": "x", "look": {}}
    assert laid.look_at("r0", "c1") == {}
    sheets.write(laid, "r1", "c0", {"look": {}})
    assert "c0" in laid.row("r1").cells and "look" not in laid.row("r1").cells["c0"]
