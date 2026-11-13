from contextlib import asynccontextmanager
from inspect import isawaitable

import pytest
from anyio import create_task_group, fail_after, sleep
from pycrdt import Doc

from apps.access.models import Role
from apps.collab.books import Book, Watcher
from apps.collab.server import Signed
from apps.content import blocks, compute, grids
from apps.content.blocks import Block, Grid, light_cell
from apps.content.models import GridRow
from apps.content.operations import carry_out
from apps.content.sheets import Sheets
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab

from .helpers import afill

ROWS = ["r1", "r2", "r3", "r4"]
COLS = ["a", "b"]


def at(row: str | None = None, col: str | None = None, **flags) -> dict:
    return {**({"row": row} if row else {}), **({"col": col} if col else {}), **flags}


def ref(start: dict, end: dict | None = None) -> dict:
    return {"from": start, **({"to": end} if end else {})}


def number(text: str) -> dict:
    return {"text": text, "kind": "number"}


async def live(*content: Block) -> tuple[Doc, Book, str]:
    """A tab holding the blocks, its state and its document's book as its room has them."""
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Tablice")
    tab = await Tab.objects.acreate(document=document, position=0)
    doc, _ = await afill(tab, list(content))
    book = Book(document.pk)
    await book.load()
    return doc, book, str(tab.pk)


@asynccontextmanager
async def computing(book: Book, tab: str, doc: Doc):
    """The book following the tab's live text and computing what changes, as while somebody
    has it open."""
    book.users += 1
    try:
        async with create_task_group() as tg:
            book.start = lambda: tg.start_soon(book.run)
            book.follow(tab, doc)
            yield
            tg.cancel_scope.cancel()
    finally:
        book.unfollow(tab)
        book.users -= 1


async def change(doc: Doc, book: Book, tab: str, *operations: dict) -> None:
    """Carries out the operations as the tab's room does: the grids' patches first."""
    order = blocks.table_ids(blocks.body_of(doc))

    def work(sheets: Sheets):
        prepared = carry_out(doc, sheets, list(operations), "hr", "run")
        return prepared, prepared.patches, False

    async with book.lock:
        prepared, applied = await book.edit(work, tab, order)
    prepared.commit(doc, applied)


def cells(table: str, **given: dict) -> dict:
    found = [{"row": key[:-1], "col": key[-1], **cell} for key, cell in given.items()]
    return {"op": "cells", "table": table, "cells": found}


async def told(book: Book, table: str) -> dict:
    """What a browser is told of the table's cells, as Postgres holds them."""
    return await database(lambda: grids.of_document(book.document, [table])[table].told())()


async def shows(book: Book, table: str, expected: dict) -> bool:
    return await told(book, table) == expected


async def until(condition) -> None:
    with fail_after(5):
        while True:
            result = condition()
            if isawaitable(result):
                result = await result
            if result:
                return
            await sleep(0.01)


def test_each_reference_is_written_in_a1_by_the_places_its_row_and_column_have():
    places = {"t": ({"r1": 1, "r9": 9}, {"a": 1, "b": 2}), "u": ({"x": 3}, {"y": 2})}
    titles = {"t": "Prodaja", "u": "Cijene 2026"}
    pieces = [
        ref(at("r1", "a", absRow=True, absCol=True)),
        "+SUM(",
        ref(at(col="b"), at(col="b")),
        ",",
        ref(at("r9"), at("r9")),
        ")+",
        ref(at("gone", "a")),
        "+",
        ref(at("r1", "a"), at("r1", "gone")),
        "+",
        7,
        "+",
        {"table": "u", **ref(at("x", "y"), at("x", "y", absRow=True))},
        "+",
        {"table": "t", **ref(at("r9", "b"))},
        "+",
        {"table": "gone", **ref(at("x", "y"))},
    ]
    assert compute.formula_text(pieces, "t", places, titles) == (
        "$A$1+SUM(B:B,9:9)+#REF!+#REF!+#REF!+'Cijene 2026'!B3:B$3+Prodaja!B9+#REF!"
    )


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_the_rows_calculated_go_to_the_browsers_holding_them_as_they_change():
    doc, book, tab = await live(Block("table", "t", grid=Grid(["r1", "r2"], ["a"])))
    watcher = Watcher(Signed(1, "key"), Role.OWN)
    book.watchers.add(watcher)
    await book.off(book.watch, watcher, tab)
    await book.off(book.rows, watcher, "t", [(0, 0)])
    told = [watcher.inbox.receive_nowait() for _ in range(4)]
    assert [message["type"] for message in told] == ["tables", "names", "grids", "rows"]
    async with computing(book, tab, doc):
        await change(doc, book, tab, cells("t", r1a={"value": 1}, r2a={"value": 2}))
        await book.settled()
        assert watcher.inbox.receive_nowait()["patches"][0]["cells"].keys() == {"r1"}
        assert watcher.inbox.receive_nowait() == {
            "type": "patch",
            "patches": [{"table": "t", "values": {"r1": {"a": number("1")}}}],
        }
        await change(doc, book, tab, cells("t", r2a={"value": 3}))
        await book.settled()
        assert watcher.inbox.statistics().current_buffer_used == 0
    assert (await GridRow.objects.aget(row="r2")).values == {"a": 3.0}


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_live_tab_computes_its_tables_as_their_cells_formulas_and_locale_change():
    table = Block("table", "t", grid=Grid(["r1", "r2"], ["a"]), cells=[light_cell("r1:a", "2")])
    doc, book, tab = await live(table)
    async with computing(book, tab, doc):
        await change(doc, book, tab, cells("t", r2a={"formula": "A1*1.5"}))
        await until(lambda: shows(book, "t", {"r1:a": number("2"), "r2:a": number("3")}))
        await change(doc, book, tab, cells("t", r1a={"value": 2.5}))
        computed = {"r1:a": number("2,5"), "r2:a": number("3,75")}
        await until(lambda: shows(book, "t", computed))
        await Node.objects.filter(pk=book.document).aupdate(locale="en")
        book.relocale("en")
        error = {"r2:a": {"text": "#VALUE!", "kind": "error"}}
        await until(lambda: shows(book, "t", error))
    assert (await GridRow.objects.aget(row="r2")).values == {"a": {"error": "#VALUE!"}}


def test_a_table_takes_its_name_as_its_sheets_where_it_can_and_one_made_up_otherwise():
    named = [None, "Prodaja", "prodaja", "Sheet1", "a/b", "x" * 32]
    sheets = {str(n): compute.Sheet([], [], name) for n, name in enumerate(named)}
    assert list(compute.titles_of(sheets).values()) == [
        "Sheet2",
        "Prodaja",
        "Sheet3",
        "Sheet1",
        "Sheet4",
        "Sheet5",
    ]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_live_tab_computes_a_table_again_as_one_it_refers_to_changes_or_goes():
    doc, book, tab = await live(
        Block("table", "t1", grid=Grid(["r1"], ["a"])),
        Block("table", "t2", {"name": "Ulaz"}, grid=Grid(["r1"], ["a"])),
    )
    async with computing(book, tab, doc):
        await change(doc, book, tab, cells("t1", r1a={"formula": "Ulaz!A1*2"}))
        await change(doc, book, tab, cells("t2", r1a={"value": 4}))
        await until(lambda: shows(book, "t1", {"r1:a": number("8")}))
        await change(doc, book, tab, cells("t2", r1a={"value": 5}))
        await until(lambda: shows(book, "t1", {"r1:a": number("10")}))
        await change(doc, book, tab, {"op": "delete", "from": "t2"})
        error = {"r1:a": {"text": "#REF!", "kind": "error"}}
        await until(lambda: shows(book, "t1", error))
        assert "t2" in book.grids
        await change(doc, book, tab, {"op": "grid", "table": "t1", "name": "ULAZ"})
        assert book.grids["t1"].name == "ULAZ"
