import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from asgiref.sync import sync_to_async
from pycrdt import Doc, Map

from apps.access.tests.test_access import create
from apps.collab.models import Update
from apps.content import elements
from apps.content.blocks import Block, Cell, Grid, Note, Run
from apps.content.models import Element
from apps.content.numbering import NUMBERS, styles_of
from apps.content.styles import STYLES
from apps.documents.models import Node, Tab
from apps.versions.history import state_of

from .helpers import edit, fill, regrid
from .test_numbering import NUMBERED, heading, own_state, paragraph

NOW = datetime(2026, 10, 17, 12, tzinfo=ZoneInfo("Europe/Zagreb"))


def rows(tab: Tab) -> list[tuple]:
    return list(
        Element.objects.filter(tab=tab).order_by("position").values_list("type", "text", "address")
    )


def first_tab(api) -> Tab:
    document = Node.objects.get(pk=create(api, "document", "Ponuda"))
    Update.objects.filter(room=document.room).update(created_at=NOW - timedelta(days=1))
    return document.tabs.get()


def test_columns_are_lettered_as_in_a_spreadsheet():
    assert [elements.column(x) for x in (0, 25, 26, 27, 701, 702)] == [
        "A",
        "Z",
        "AA",
        "AB",
        "ZZ",
        "AAA",
    ]


def test_every_heading_table_image_chart_text_and_filled_cell_has_its_address():
    figure = Block("image", attrs={"blob": "cd" * 32, "alt": "Detalj"})
    cells = [
        Cell("r2", "c3", [Block("paragraph", runs=[Run("42", {"strong": {}})])]),
        Cell("r1", "c1", [Block("paragraph", runs=[Run("Stavka")]), Block("paragraph")]),
        Cell("r2", "c2", [figure, Block("paragraph", runs=[Run(" ")])]),
    ]
    grid = Grid(["r1", "r2"], ["c1", "c2", "c3"])
    content = [
        Block("title", runs=[Run("Ponuda")]),
        Block("paragraph", runs=[Run("Uvod")]),
        Block("heading", attrs={"level": 1}, runs=[Run("Troškovi")]),
        Block("paragraph"),
        Block("paragraph", runs=[Run("Rad")]),
        Block("heading", attrs={"level": 3}, runs=[Run("Materijal")]),
        Block("paragraph", runs=[Run("Cijevi")]),
        Block("table", grid=grid, cells=cells),
        Block("image", attrs={"blob": "ab" * 32, "alt": "Shema cjevovoda", "width": 50}),
        Block("chart", attrs={"kind": "line", "title": "Troškovi po mjesecu"}),
        Block("heading", attrs={"level": 2}, runs=[Run("Prijevoz")]),
        Block("heading", attrs={"level": "9"}, runs=[Run("Rok")]),
        Block(
            "paragraph",
            attrs={"style": "note"},
            runs=[Run("Trideset", {"strong": {}}), Run(" dana")],
        ),
    ]
    found = elements.elements_of(content)
    within = {"section": "1.0.1", "table": 1}
    assert [(element.type, element.text, element.address) for element in found] == [
        ("title", "Ponuda", {"paragraph": 1}),
        ("paragraph", "Uvod", {"paragraph": 2}),
        ("heading", "Troškovi", {"section": "1"}),
        ("paragraph", "Rad", {"section": "1", "paragraph": 1}),
        ("heading", "Materijal", {"section": "1.0.1"}),
        ("paragraph", "Cijevi", {"section": "1.0.1", "paragraph": 1}),
        ("table", "", within),
        ("image", "Detalj", {**within, "cell": "B2", "image": 1}),
        ("image", "Shema cjevovoda", {"section": "1.0.1", "image": 2}),
        ("chart", "Troškovi po mjesecu", {"section": "1.0.1", "chart": 1}),
        ("heading", "Prijevoz", {"section": "1.1"}),
        ("heading", "Rok", {"section": "2"}),
        ("paragraph", "Trideset dana", {"section": "2", "paragraph": 1}),
    ]
    table, last = found[6], found[-1]
    assert (table.block, table.content) == (content[7].id, {})
    assert last.content == {
        "attrs": {"style": "note"},
        "runs": [{"text": "Trideset", "marks": {"strong": {}}}, {"text": " dana"}],
    }
    assert [element.position for element in found] == list(range(len(found)))


def test_a_heading_in_a_cell_numbers_on_as_any_other():
    numbering = {"styles": styles_of(own_state(**NUMBERED)), "start": {}}
    cells = [
        Cell("r1", "c2", [heading(1, "Drugi")]),
        Cell("r1", "c1", [heading(1, "Prvi"), paragraph("Opis")]),
    ]
    table = Block("table", grid=Grid(["r1"], ["c1", "c2"]), cells=cells)
    found = elements.elements_of([table, heading(1, "Treći")], numbering)
    assert [(element.type, element.text, element.address) for element in found] == [
        ("table", "", {"table": 1}),
        ("heading", "3. Treći", {"section": "3", "heading": "3."}),
    ]


def test_a_note_is_its_own_element_where_its_mark_is():
    note = Note("foot", runs=[Run("Prema ", {}), Run("HRN EN 1090", {"strong": {}})])
    end = Note("end", runs=[Run("Izvor")])
    content = [
        Block("paragraph", runs=[Run("Uvod"), note]),
        Block("heading", attrs={"level": 1}, runs=[Run("Troškovi"), end]),
        Block("paragraph", runs=[Note("foot", runs=[Run("Samo bilješka")])]),
    ]
    found = elements.elements_of(content)
    assert [(element.type, element.text, element.address) for element in found] == [
        ("paragraph", "Uvod", {"paragraph": 1}),
        ("footnote", "Prema HRN EN 1090", {"paragraph": 1, "note": "foot"}),
        ("heading", "Troškovi", {"section": "1"}),
        ("endnote", "Izvor", {"section": "1", "note": "end"}),
        ("footnote", "Samo bilješka", {"section": "1", "note": "foot"}),
    ]
    assert (found[1].block, found[1].content) == (
        note.id,
        {"runs": [{"text": "Prema "}, {"text": "HRN EN 1090", "marks": {"strong": {}}}]},
    )
    assert found[0].content["runs"] == [{"text": "Uvod"}]


@pytest.mark.django_db
def test_a_tab_is_read_again_and_its_elements_replaced(api):
    tab = first_tab(api)
    assert elements.due(NOW + timedelta(days=1)) == []
    fill(tab, [Block("heading", "h1", {"level": 1}, [Run("Ponuda")])], at=NOW)
    elements.tend(NOW + timedelta(seconds=3))
    assert rows(tab) == [("heading", "Ponuda", {"section": "1"})]
    assert Tab.objects.get(pk=tab.pk).derived_at == NOW

    fill(tab, [Block("paragraph", "p1", runs=[Run("Rok isporuke")])], at=NOW + timedelta(seconds=5))
    elements.tend(NOW + timedelta(seconds=10))
    assert rows(tab) == [("paragraph", "Rok isporuke", {"paragraph": 1})]
    assert elements.due(NOW + timedelta(days=1)) == []


@pytest.mark.django_db
def test_a_tab_is_due_once_quiet_or_once_its_first_unread_edit_is_half_a_minute_old(api):
    tab = first_tab(api)
    fill(tab, [Block("paragraph", runs=[Run("Prvo")])], at=NOW)
    assert elements.due(NOW + timedelta(seconds=2)) == []
    assert elements.due(NOW + timedelta(seconds=3)) == [tab]
    elements.derive(tab.pk)

    edit(tab, at=NOW + timedelta(seconds=10))
    edit(tab, at=NOW + timedelta(seconds=39))
    assert elements.due(NOW + timedelta(seconds=39.5)) == []
    assert elements.due(NOW + timedelta(seconds=40)) == [tab]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_tab_whose_grids_alone_changed_is_read_again_counted_from_its_first_such_edit(
    api, live
):
    def checked():
        tab = first_tab(api)
        fill(tab, [Block("table", "t", grid=Grid(["r1"], ["a"]))], at=NOW)
        elements.tend(NOW + timedelta(seconds=3))
        assert Tab.objects.get(pk=tab.pk).derived_at == NOW
        kept = Update.objects.filter(room=tab.room).count()

        regrid(tab, {"op": "cells", "table": "t", "cells": [{"row": "r1", "col": "a", "value": 1}]})
        assert Update.objects.filter(room=tab.room).count() == kept
        edited = tab.grids.get().edited_at
        assert elements.due(edited) == [tab]
        elements.tend(edited)
        assert Tab.objects.get(pk=tab.pk).derived_at == edited
        assert elements.due(edited + timedelta(days=1)) == []

    await sync_to_async(checked)()


@pytest.mark.django_db
def test_an_unreadable_tab_is_logged_once_and_read_again_after_its_next_edit(api, caplog):
    tab = first_tab(api)
    edit(tab, b"not an update", at=NOW)
    with caplog.at_level(logging.ERROR, logger="apps.content.elements"):
        elements.tend(NOW + timedelta(seconds=3))
    assert "could not be read" in caplog.text
    assert elements.due(NOW + timedelta(days=1)) == []
    fill(tab, [Block("paragraph", runs=[Run("Opet")])], at=NOW + timedelta(minutes=1))
    elements.tend(NOW + timedelta(minutes=2))
    assert rows(tab) == [("paragraph", "Opet", {"paragraph": 1})]


def test_a_numbered_block_leads_with_its_number_and_its_address_holds_it():
    numbering = {"styles": styles_of(own_state(**NUMBERED)), "start": {"#1": 1}}
    content = [
        heading(1, "Cijene"),
        paragraph("Tekst"),
        paragraph("", style="article"),
        heading(2, "Popusti"),
        paragraph("Rok", style="article"),
    ]
    found = [
        (each.type, each.text, each.address) for each in elements.elements_of(content, numbering)
    ]
    assert found == [
        ("heading", "2. Cijene", {"section": "1", "heading": "2."}),
        ("paragraph", "Tekst", {"section": "1", "heading": "2.", "paragraph": 1}),
        (
            "paragraph",
            "Članak 1.",
            {"section": "1", "heading": "2.", "paragraph": 2, "number": "Članak 1."},
        ),
        ("heading", "2.1. Popusti", {"section": "1.1", "heading": "2.1."}),
        (
            "paragraph",
            "Članak 2. Rok",
            {"section": "1.1", "heading": "2.1.", "paragraph": 1, "number": "Članak 2."},
        ),
    ]


def restyle(document: Node, at: datetime, looks: dict | None = None, tallies: dict | None = None):
    """Changes the document's own state the way its editors would."""
    own = Doc()
    own.apply_update(state_of(document.room))
    before = own.get_state()
    for id, look in (looks or {}).items():
        for name, value in look.items():
            own.get(STYLES, type=Map)[id][name] = value
    for tab, tally in (tallies or {}).items():
        own.get(NUMBERS, type=Map)[str(tab.pk)] = tally
    update = Update.objects.create(
        document=document, room=document.room, data=own.get_update(before)
    )
    Update.objects.filter(pk=update.pk).update(created_at=at)


@pytest.mark.django_db
def test_a_tab_is_numbered_anew_once_the_styles_or_the_tabs_before_it_change(api):
    first = first_tab(api)
    document = first.document
    second = Tab.objects.create(document=document, position=1, title="Cijene")
    fill(first, [heading(1, "Uvod")], at=NOW)
    fill(second, [heading(1, "Cijene")], at=NOW)
    elements.tend(NOW + timedelta(seconds=3))
    assert rows(second) == [("heading", "Cijene", {"section": "1"})]
    kept = Element.objects.get(tab=second).pk

    once = {"#1": {"reset": False, "count": 1}}
    restyle(document, NOW + timedelta(seconds=10), tallies={first: once, second: once})
    elements.tend(NOW + timedelta(seconds=15))
    assert Element.objects.get(tab=second).pk == kept
    assert elements.due(NOW + timedelta(days=1)) == []

    restyle(document, NOW + timedelta(seconds=20), looks={"h1": NUMBERED["h1"]})
    elements.tend(NOW + timedelta(seconds=25))
    assert rows(first) == [("heading", "1. Uvod", {"section": "1", "heading": "1."})]
    assert rows(second) == [("heading", "2. Cijene", {"section": "1", "heading": "2."})]

    moved = api.patch(
        f"/api/tabs/{second.pk}", {"parent": None, "position": 0}, content_type="application/json"
    )
    assert moved.status_code == 200
    elements.tend(NOW + timedelta(days=1))
    assert rows(second) == [("heading", "1. Cijene", {"section": "1", "heading": "1."})]
    assert rows(first) == [("heading", "2. Uvod", {"section": "1", "heading": "2."})]
