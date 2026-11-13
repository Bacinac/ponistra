from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from asgiref.sync import sync_to_async
from django.db import connection
from pycrdt import Doc, Map, Text

from apps.collab import server
from apps.collab.models import Update
from apps.content import blocks, grids, names
from apps.content.blocks import Block, Cell, Grid, Run
from apps.content.models import Element, GridRow, Name, Shared
from apps.content.tests.helpers import fill, regrid
from apps.documents.models import Node, Tab
from apps.users.models import User
from apps.versions import history
from apps.versions.models import (
    Contribution,
    Piece,
    State,
    Version,
    VersionEditor,
    VersionTab,
)

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 10, 16, 12, tzinfo=ZoneInfo("Europe/Zagreb"))


def document(api, title="Ponuda") -> Node:
    response = api.post(
        "/api/nodes", {"kind": "document", "title": title}, content_type="application/json"
    )
    return Node.objects.get(pk=response.json()["id"])


def write(tab: Tab, text: str, at: datetime | None = None) -> None:
    """Replaces the tab's content the way a room would leave it."""
    doc = Doc()
    doc.get("text", type=Text).insert(0, text)
    Update.objects.filter(tab=tab).delete()
    update = Update.objects.create(
        document_id=tab.document_id, tab=tab, room=tab.room, data=doc.get_update()
    )
    if at is not None:
        Update.objects.filter(pk=update.pk).update(created_at=at)


def text_of(data: bytes) -> str:
    doc = Doc()
    doc.apply_update(data)
    return str(doc.get("text", type=Text))


def read(tab: Tab) -> str:
    return text_of(history.state_of(tab.room))


def restyle(document: Node, font: str) -> None:
    """Changes the document's theme as a client of its own room would."""
    doc = Doc()
    doc.apply_update(history.state_of(document.room))
    before = doc.get_state()
    doc.get("theme", type=Map)["text"] = font
    Update.objects.create(document=document, room=document.room, data=doc.get_update(before))


def font_of(data: bytes) -> str:
    doc = Doc()
    doc.apply_update(data)
    return doc.get("theme", type=Map)["text"]


def test_a_version_holds_every_tab_with_its_place_and_content(api):
    offer = document(api)
    intro = offer.tabs.get()
    prices = Tab.objects.create(document=offer, parent=intro, position=0, title="Cijene")
    write(intro, "Uvod")
    write(prices, "1200 EUR")

    version = history.take(offer)

    assert version.number == 1 and version.title == ""
    detail = api.get(f"/api/versions/{version.pk}").json()
    assert [(tab["title"], tab["parent"]) for tab in detail["tabs"]] == [
        ("", None),
        ("Cijene", str(intro.pk)),
    ]
    assert [node["title"] for node in detail["path"]] == ["Ponuda"]
    state = api.get(f"/api/versions/{version.pk}/tabs/{prices.pk}/state")
    assert state["Content-Type"] == "application/octet-stream"
    assert text_of(state.content) == "1200 EUR"


def test_a_version_shows_a_tab_s_grids_with_their_values_and_reads_back_its_blocks(api):
    offer = document(api)
    intro = offer.tabs.get()
    double = {"r1:b": ["2*", {"from": {"row": "r1", "col": "a"}}]}
    table = Block(
        "table",
        "t",
        grid=Grid(["r1"], ["a", "b"], double),
        cells=[Cell("r1", "a", [Block("paragraph", runs=[Run("21")])])],
    )
    fill(intro, [Block("paragraph", "p", runs=[Run("Uvod")]), table])
    saved = history.take(offer)
    held = server.read_grids(intro.room, lambda doc, laid: blocks.read(doc, laid.grids()))
    fill(intro, [])

    outline = api.get(f"/api/versions/{saved.pk}/tabs/{intro.pk}/grids").json()
    assert [grid["rows"] for grid in outline["grids"]] == [1]
    shown = api.get(f"/api/versions/{saved.pk}/rows?table=t&spans=0-9").json()

    assert shown["at"] == {"r1": 0}
    assert shown["rows"]["r1"]["values"]["b"] == {"text": "42", "kind": "number"}
    uncalculated = [
        replace(block, grid=replace(block.grid, values={})) if block.grid else block
        for block in held
    ]
    assert history.blocks_of(saved, intro) == uncalculated
    assert history.blocks_of(saved, Tab.objects.create(document=offer, position=1)) == []


def test_an_automatic_version_of_unchanged_content_is_skipped_and_counts_as_checked(api):
    offer = document(api)
    first = history.take(offer)
    assert history.take(offer) is None
    assert Version.objects.get().checked_at > first.checked_at
    named = api.post(
        f"/api/nodes/{offer.pk}/versions",
        {"title": " Poslano kupcu "},
        content_type="application/json",
    )
    assert named.status_code == 201
    assert (named.json()["number"], named.json()["title"]) == (2, "Poslano kupcu")


def own_written(document: Node, edit) -> None:
    own = Doc()
    own.apply_update(history.state_of(document.room))
    before = own.get_state()
    edit(own)
    Update.objects.create(document=document, room=document.room, data=own.get_update(before))


def test_an_editor_rewriting_its_tallies_takes_no_version_but_a_changed_style_does(api):
    offer = document(api)
    history.take(offer)
    own_written(offer, lambda own: own.get("pages", type=Map).__setitem__("t", 3))
    own_written(offer, lambda own: own.get("styles", type=Map).__setitem__("x", {"size": 12}))
    own_written(offer, lambda own: own.get("styles", type=Map).__setitem__("x", {"size": 12}))
    assert history.take(offer) is not None
    own_written(offer, lambda own: own.get("styles", type=Map).__setitem__("x", {"size": 12}))
    own_written(offer, lambda own: own.get("pages", type=Map).__setitem__("t", 4))
    assert history.take(offer) is None
    assert Version.objects.count() == 2


def test_a_version_needs_a_title_to_be_saved_by_hand(api):
    offer = document(api)
    response = api.post(
        f"/api/nodes/{offer.pk}/versions", {"title": " "}, content_type="application/json"
    )
    assert response.json() == {"error": "invalid_title"}


def test_unchanged_tabs_are_stored_once_per_document(api):
    offer = document(api)
    intro = offer.tabs.get()
    prices = Tab.objects.create(document=offer, position=1, title="Cijene")
    write(intro, "Uvod")
    write(prices, "1200 EUR")
    history.take(offer)
    write(prices, "1100 EUR")
    history.take(offer)
    assert State.objects.count() == 4
    assert VersionTab.objects.count() == 4


def test_editors_are_who_changed_the_document_since_the_version_before(api):
    offer = document(api)
    ivo = User.objects.get()
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    history.contributed(offer.pk, ana.pk)
    first = history.take(offer)
    assert [user.email for user in first.editors.all()] == ["ana@example.com"]
    api.post(f"/api/nodes/{offer.pk}/tabs", {}, content_type="application/json")
    second = history.take(offer)
    assert [user.email for user in second.editors.all()] == [ivo.email]


def test_restore_brings_back_tabs_titles_and_content_in_fresh_rooms(api):
    offer = document(api)
    intro = offer.tabs.get()
    terms = Tab.objects.create(document=offer, position=1, title="Uvjeti")
    write(intro, "prvo")
    write(terms, "plaćanje 30 dana")
    saved = history.take(offer)
    rooms = {intro.room, terms.room}
    expected = [(intro.pk, ""), (terms.pk, "Uvjeti")]

    intro.title = "Sažetak"
    intro.save()
    write(intro, "drugo")
    terms.delete()
    added = Tab.objects.create(document=offer, position=2, title="Dodatak")
    response = api.post(f"/api/versions/{saved.pk}/restore")

    assert response.status_code == 200
    assert (response.json()["number"], response.json()["restored_from"]) == (3, 1)
    tabs = offer.tabs_in_order()
    assert [(tab.pk, tab.title) for tab in tabs] == expected
    assert [read(tab) for tab in tabs] == ["prvo", "plaćanje 30 dana"]
    assert not rooms & {tab.room for tab in tabs}
    assert not Tab.objects.filter(pk=added.pk).exists()
    replaced = Version.objects.get(number=2)
    assert {(part.title, text_of(part.state.data)) for part in replaced.tabs.all()} == {
        ("Sažetak", "drugo"),
        ("Dodatak", ""),
    }


def test_a_version_holds_the_theme_and_styles_and_restoring_brings_them_back(api):
    offer = document(api)
    restyle(offer, "Source Serif 4")
    saved = history.take(offer)
    room = offer.room
    restyle(offer, "IBM Plex Sans")
    assert history.take(offer).number == 2

    api.post(f"/api/versions/{saved.pk}/restore")

    offer.refresh_from_db()
    assert offer.room != room
    assert font_of(history.state_of(offer.room)) == "Source Serif 4"
    state = api.get(f"/api/versions/{saved.pk}/state")
    assert font_of(state.content) == "Source Serif 4"


def test_a_version_holds_the_defined_names_and_restoring_brings_them_back(api):
    offer = document(api)
    rate = names.entry("Tečaj", ["7,5"])
    names.put(offer, {"n1": rate})
    saved = history.take(offer)
    assert saved.names == {"n1": rate}
    Name.objects.filter(document=offer).delete()
    names.put(offer, {"n2": names.entry("Rok", ["30"])})
    assert history.take(offer).number == 2

    api.post(f"/api/versions/{saved.pk}/restore")

    assert names.of_document(offer) == {"n1": rate}


def test_a_version_keeps_what_its_cells_and_lines_share_and_restoring_brings_it_back(api):
    offer = document(api)
    intro = offer.tabs.get()
    double = {f"r{y}:b": ["2*", {"from": {"row": f"r{y}", "col": "a"}}] for y in (1, 2)}
    bold, centred = {"marks": {"strong": {}}}, {"attrs": {"align": "center"}}
    grid = Grid(["r1", "r2"], ["a", "b"], double, row_looks={"r2": centred}, col_looks={"a": bold})
    fill(intro, [Block("table", "t", grid=grid)])
    saved = history.take(offer)
    assert sorted(saved.shared.values(), key=str) == sorted(
        [["2*", {"from": {"row": "@", "col": "a"}}], bold, centred], key=str
    )
    intro.grids.all().delete()
    Shared.objects.filter(document=offer).delete()

    history.restore(saved, User.objects.get())

    laid = grids.of_document(offer)["t"]
    formulas = laid.entries("formula")
    assert {key: grids.formula_in(pieces, *key.split(":")) for key, pieces in formulas.items()} == (
        double
    )
    assert [row.look for row in laid.rows] == [None, centred]
    assert [col.look for col in laid.cols] == [bold, None]
    assert Shared.objects.filter(document=offer).count() == 3


def test_thinning_keeps_a_state_that_a_kept_version_still_holds(api):
    offer = document(api)
    older = history.take(offer)
    write(offer.tabs.get(), "izmjena")
    newer = history.take(offer)
    Version.objects.filter(pk=older.pk).update(created_at=NOW - timedelta(days=60, hours=1))
    Version.objects.filter(pk=newer.pk).update(created_at=NOW - timedelta(days=60))
    history.thin(NOW)
    assert Version.objects.get().pk == newer.pk
    assert Version.objects.get().state.sha256 == older.state.sha256


def test_restoring_unchanged_content_adds_only_the_restore(api):
    offer = document(api)
    saved = history.take(offer)
    api.post(f"/api/versions/{saved.pk}/restore")
    assert list(Version.objects.order_by("number").values_list("number", "restored_from")) == [
        (1, None),
        (2, 1),
    ]


def test_a_deleted_tab_is_in_the_version_taken_just_before(api):
    offer = document(api)
    terms = Tab.objects.create(document=offer, position=1, title="Uvjeti")
    write(terms, "plaćanje 30 dana")
    api.delete(f"/api/tabs/{terms.pk}")
    history.restore(Version.objects.get(), User.objects.get())
    assert read(offer.tabs.get(pk=terms.pk)) == "plaćanje 30 dana"


def test_a_document_is_due_once_quiet_or_once_its_first_unrecorded_edit_is_an_hour_old(api):
    offer = document(api)
    Node.objects.filter(pk=offer.pk).update(
        created_at=NOW - timedelta(days=1), updated_at=NOW - timedelta(minutes=5)
    )
    Update.objects.filter(document=offer).update(created_at=NOW - timedelta(minutes=5))
    assert history.due(NOW) == []
    assert history.due(NOW + timedelta(minutes=5)) == [offer]
    state = State.objects.create(document=offer, sha256="0" * 64, data=b"")
    Version.objects.create(document=offer, number=1, created_at=NOW, checked_at=NOW, state=state)
    assert history.due(NOW + timedelta(hours=2)) == []

    intro = offer.tabs.get()
    write(intro, "prvo", at=NOW + timedelta(minutes=1))
    Update.objects.create(document=offer, tab=intro, room=intro.room, data=b"\x00\x00")
    Update.objects.filter(created_at__gt=NOW + timedelta(minutes=1)).update(
        created_at=NOW + timedelta(minutes=58)
    )
    assert history.due(NOW + timedelta(minutes=60)) == []
    assert history.due(NOW + timedelta(minutes=62)) == [offer]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_document_whose_grids_alone_changed_is_due_counted_from_its_first_such_edit(
    api, live
):
    def checked():
        offer = document(api)
        intro = offer.tabs.get()
        fill(intro, [Block("table", "t", grid=Grid(["r1"], ["a"]))], at=NOW)
        Node.objects.filter(pk=offer.pk).update(created_at=NOW, updated_at=NOW)
        Update.objects.filter(document=offer).update(created_at=NOW)
        state = State.objects.create(document=offer, sha256="0" * 64, data=b"")
        Version.objects.create(
            document=offer, number=1, created_at=NOW, checked_at=NOW, state=state
        )
        assert history.due(NOW + timedelta(days=1)) == []
        kept = Update.objects.filter(document=offer).count()

        regrid(
            intro, {"op": "cells", "table": "t", "cells": [{"row": "r1", "col": "a", "value": 1}]}
        )
        assert Update.objects.filter(document=offer).count() == kept
        edited = intro.grids.get().edited_at
        assert history.due(edited) == [offer]

    await sync_to_async(checked)()


def test_thinning_keeps_titled_versions_the_last_day_then_one_a_day_then_one_a_week(api):
    offer = document(api)
    intro = offer.tabs.get()
    ages = {
        1: timedelta(weeks=8),
        2: timedelta(days=41),
        3: timedelta(days=40),
        4: timedelta(days=10),
        5: timedelta(days=2, hours=1),
        6: timedelta(days=2),
        7: timedelta(hours=3),
        8: timedelta(hours=2),
    }
    for number, age in ages.items():
        state = State.objects.create(document=offer, sha256=str(number) * 64, data=b"")
        version = Version.objects.create(
            document=offer,
            number=number,
            title="Ugovor" if number == 1 else "",
            created_at=NOW - age,
            checked_at=NOW - age,
            state=state,
        )
        VersionTab.objects.create(version=version, tab=intro.pk, position=0, state=state)

    history.thin(NOW)

    kept = [1, 3, 4, 6, 7, 8]
    assert list(Version.objects.order_by("number").values_list("number", flat=True)) == kept
    assert sorted(int(sha[0]) for sha in State.objects.values_list("sha256", flat=True)) == kept


def test_the_version_list_is_newest_first_and_a_version_can_be_titled(api):
    offer = document(api)
    first = history.take(offer)
    history.contributed(offer.pk, User.objects.get().pk)
    write(offer.tabs.get(), "izmjena")
    history.take(offer)
    listed = api.get(f"/api/nodes/{offer.pk}/versions").json()["versions"]
    assert [version["number"] for version in listed] == [2, 1]
    ivo = User.objects.get()
    assert listed[0]["editors"] == [{"id": ivo.pk, "email": ivo.email, "name": ivo.email}]
    renamed = api.patch(
        f"/api/versions/{first.pk}", {"title": "Prva"}, content_type="application/json"
    )
    assert renamed.json()["version"]["title"] == "Prva"


def test_the_versions_of_a_trashed_document_are_out_of_reach(api):
    offer = document(api)
    version = history.take(offer)
    tab = offer.tabs.get().pk
    assert api.get(f"/api/versions/{version.pk}/tabs/{version.pk}/state").status_code == 404
    api.post("/api/nodes/trash", {"nodes": [str(offer.pk)]}, content_type="application/json")
    assert api.get(f"/api/nodes/{offer.pk}/versions").status_code == 404
    assert api.get(f"/api/versions/{version.pk}").status_code == 404
    assert api.post(f"/api/versions/{version.pk}/restore").status_code == 404
    assert api.get(f"/api/versions/{version.pk}/tabs/{tab}/state").status_code == 404


def test_purging_a_document_takes_its_versions_states_and_contributions(api):
    offer = document(api)
    history.contributed(offer.pk, User.objects.get().pk)
    history.take(offer)
    api.post("/api/nodes/trash", {"nodes": [str(offer.pk)]}, content_type="application/json")
    api.post("/api/trash/purge", {"nodes": [str(offer.pk)]}, content_type="application/json")
    assert not Version.objects.exists()
    assert not State.objects.exists()
    assert not Contribution.objects.exists()


def test_the_database_takes_what_belongs_to_a_document_deleted_by_any_path(api):
    offer = document(api)
    intro = offer.tabs.get()
    write(intro, "Uvod")
    Element.objects.create(tab=intro, position=0, type="paragraph", text="Uvod")
    history.contributed(offer.pk, api.user.pk)
    history.take(offer, by=api.user)
    held = (Tab, Update, Element, Contribution, Version, VersionEditor, VersionTab, State)
    assert all(model.objects.exists() for model in held)
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM documents_node WHERE id = %s", [offer.pk])
    assert not any(model.objects.exists() for model in held)
    assert User.objects.filter(pk=api.user.pk).exists()


def _column(api, rows: int) -> tuple[Node, Tab]:
    """A document with a table of `rows` rows: a number in `a` and in `b` twice the row's own,
    and in `c` the row's number added to the first row's, by an absolute reference."""
    offer = document(api)
    tab = offer.tabs.get()
    ids = [f"r{at}" for at in range(rows)]
    formulas = {}
    for id in ids:
        formulas[f"{id}:b"] = ["2*", {"from": {"row": id, "col": "a"}}]
        formulas[f"{id}:c"] = [
            {"from": {"row": id, "col": "a"}},
            "+",
            {"from": {"row": "r0", "col": "a", "absRow": True}},
        ]
    table = Block(
        "table",
        "t",
        grid=Grid(ids, ["a", "b", "c"], formulas),
        cells=[
            Cell(id, "a", [Block("paragraph", runs=[Run(str(at + 1))])])
            for at, id in enumerate(ids)
        ],
    )
    fill(tab, [table])
    return offer, tab


def _window(api, version: Version, spans: str) -> dict:
    return api.get(f"/api/versions/{version.pk}/rows?table=t&spans={spans}").json()


def test_a_version_is_read_by_windows_of_its_rows_values_and_formulas_included(api):
    offer, tab = _column(api, 600)
    version = history.take(offer)

    (outline,) = api.get(f"/api/versions/{version.pk}/tabs/{tab.pk}/grids").json()["grids"]
    assert outline["rows"] == 600 and "cells" not in outline
    assert outline["at"]["r0"] == 0 and outline["at"]["r599"] == 599

    found = _window(api, version, "500-502")
    assert found["at"] == {"r500": 500, "r501": 501, "r502": 502}
    row = found["rows"]["r501"]
    assert row["values"]["b"] == {"text": "1004", "kind": "number"}
    assert row["cells"]["b"]["formula"] == "=2*A502"
    assert row["cells"]["c"]["formula"] == "=A502+A$1"
    assert row["values"]["c"] == {"text": "503", "kind": "number"}


def test_a_version_s_hidden_rows_are_left_out_of_its_windows_keeping_their_numbers(api):
    offer, tab = _column(api, 5)
    GridRow.objects.filter(grid__document=offer, row="r1").update(hidden=True)
    version = history.take(offer)

    (outline,) = api.get(f"/api/versions/{version.pk}/tabs/{tab.pk}/grids").json()["grids"]
    assert outline["rows"] == 4 and outline["numbers"]["r0"] == 0
    found = _window(api, version, "0-3")
    assert found["at"] == {"r0": 0, "r2": 1, "r3": 2, "r4": 3}
    assert found["numbers"] == {"r0": 0, "r2": 2, "r3": 3, "r4": 4}
    standing = api.get(f"/api/versions/{version.pk}/standing?table=t&numbered=1,2&rows=r4").json()
    assert standing["numbered"] == {"1": -1, "2": 1}
    assert standing["rows"] == {"r4": 3}


def test_restoring_a_version_brings_its_rows_back_with_their_values(api):
    offer, tab = _column(api, 3)
    version = history.take(offer)
    GridRow.objects.filter(grid__document=offer, row="r2").delete()
    GridRow.objects.filter(grid__document=offer, row="r0").update(values={})

    history.restore(version, offer.created_by)

    kept = GridRow.objects.filter(grid__document=offer).order_by("position")
    assert [row.row for row in kept] == ["r0", "r1", "r2"]
    assert kept[1].values["b"] == 4
    assert kept[1].cells["b"]["formula"] in Shared.objects.values_list("key", flat=True)


def test_an_automatic_version_of_an_unchanged_table_is_skipped(api):
    offer, _ = _column(api, 2)
    history.take(offer)
    assert history.take(offer) is None


def test_a_version_kept_without_values_is_calculated_as_it_stood_and_the_document_stays(api):
    offer, tab = _column(api, 3)
    version = history.take(offer)
    part = version.grids.get()
    renamed = {}
    for piece in Piece.objects.filter(document=offer):
        renamed[piece.sha256] = history.digest([line[:3] for line in piece.rows])
        piece.rows = [line[:3] for line in piece.rows]
        piece.sha256 = renamed[piece.sha256]
        piece.save(update_fields=["rows", "sha256"])
    part.pieces = [renamed[sha256] for sha256 in part.pieces]
    part.save(update_fields=["pieces"])
    GridRow.objects.filter(grid__document=offer, row="r2").delete()
    before = list(GridRow.objects.filter(grid__document=offer).values_list("row", flat=True))

    history.settle(version)
    history.collect_pieces(offer.pk)

    assert (
        list(GridRow.objects.filter(grid__document=offer).values_list("row", flat=True)) == before
    )
    found = _window(api, Version.objects.get(pk=version.pk), "0-2")
    assert found["rows"]["r2"]["values"]["b"] == {"text": "6", "kind": "number"}
