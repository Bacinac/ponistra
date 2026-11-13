import pytest
from asgiref.sync import sync_to_async
from pycrdt import Doc

from apps.access.models import Grant, Role
from apps.collab.books import Book, Watcher
from apps.collab.server import Signed
from apps.content import names
from apps.content.blocks import Block, Grid, light_cell
from apps.content.models import GridRow
from apps.content.placing import Placing
from apps.content.tests.helpers import afill
from apps.content.tests.test_compute import (
    cells,
    change,
    computing,
    live,
    number,
    shows,
    told,
    until,
)
from apps.documents.models import Node, Tab

pytestmark = [pytest.mark.anyio, pytest.mark.django_db(transaction=True)]

REF = {"text": "#REF!", "kind": "error"}


async def tabs(first: list[Block], second: list[Block]) -> tuple[Book, list[tuple[str, Doc]]]:
    """A document of two tabs holding the blocks, and its book; the second tab nobody has open."""
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Tablice")
    found = []
    for position, content in enumerate([first, second]):
        tab = await Tab.objects.acreate(document=document, position=position)
        doc, _ = await afill(tab, content)
        found.append((str(tab.pk), doc))
    book = Book(document.pk)
    await book.load()
    return book, found


def entry() -> Block:
    return Block(
        "table",
        "t2",
        {"name": "Ulaz"},
        grid=Grid(["r1", "r2"], ["a"]),
        cells=[light_cell("r1:a", "4")],
    )


async def test_a_table_computes_with_one_of_a_tab_nobody_has_open_and_draws_its_charts_there():
    sales = Block("table", "t1", {"name": "Prodaja"}, grid=Grid(["r1"], ["a", "b"]))
    range = {"table": "t2", "from": {"row": "r1", "col": "a"}, "to": {"row": "r2", "col": "a"}}
    drawn = Block("chart", "c", {"range": range, "kind": "column"})
    book, [(one, doc), (two, other)] = await tabs([sales], [entry(), drawn])
    shown: dict[str, dict] = {}

    async def outside(tab: str, charts: dict[str, dict]) -> None:
        shown.update(charts if tab == two else {})

    book.outside = outside

    def values() -> list:
        return shown.get("c", {}).get("series", [{}])[0].get("values")

    async with computing(book, one, doc):
        await change(doc, book, one, cells("t1", r1a={"formula": "Ulaz!A1*2"}))
        await until(lambda: shows(book, "t1", {"r1:a": number("8")}))
        await change(other, book, two, cells("t2", r1a={"value": 5}))
        await until(lambda: shows(book, "t1", {"r1:a": number("10")}))
        await change(other, book, two, cells("t2", r2a={"formula": "Prodaja!B1"}))
        await change(doc, book, one, cells("t1", r1b={"value": 3}))
        await until(lambda: values() == [5.0, 3.0])
        assert await told(book, "t2") == {"r1:a": number("5"), "r2:a": number("3")}


async def test_a_table_taken_out_of_its_text_frees_its_name_and_takes_another_coming_back():
    sales = Block("table", "t1", grid=Grid(["r1"], ["a"]))
    book, [(one, doc), (two, _)] = await tabs([sales], [entry()])
    watcher = Watcher(Signed(1, "key"), Role.OWN)
    book.watchers.add(watcher)
    await book.off(book.watch, watcher, one)
    for _ in range(3):
        watcher.inbox.receive_nowait()
    async with computing(book, one, doc):
        await change(doc, book, one, cells("t1", r1a={"formula": "Ulaz!A1*2"}))
        await until(lambda: shows(book, "t1", {"r1:a": number("8")}))
        kept = book.placings[two]
        book.placed(two, Placing())
        assert watcher.inbox.receive_nowait() == {"type": "tables", "tables": []}
        await until(lambda: shows(book, "t1", {"r1:a": REF}))
        await change(doc, book, one, {"op": "grid", "table": "t1", "name": "ULAZ"})
        assert book.grids["t1"].name == "ULAZ"
        book.placed(two, kept)
        await until(lambda: book.grids["t2"].name == "Ulaz (2)")
        await until(lambda: shows(book, "t1", {"r1:a": number("8")}))
        assert book.grids["t1"].name == "ULAZ"


async def test_a_defined_name_leads_to_the_cells_it_stands_for_in_force_in_the_table():
    sales = Block("table", "t1", {"name": "Prodaja"}, grid=Grid(["r1"], ["a", "b"]))
    book, _ = await tabs([sales], [entry()])
    ulaz = {"table": "t2", "from": {"row": "r1", "col": "a"}, "to": {"row": "r2", "col": "a"}}
    book.names = {
        "n1": names.entry("Ukupno", [ulaz]),
        "n2": names.entry("Stopa", [{"table": "t2", "from": {"row": "r2", "col": "a"}}], "t1"),
        "n3": names.entry("Stopa", ["0.25"]),
        "n4": names.entry("Zbroj", ["SUM(", ulaz, ")"]),
        "n5": names.entry("Stupac", [{"table": "t2", "from": {"col": "a"}, "to": {"col": "a"}}]),
    }
    assert await book.off(book.where, "ukupno", None) == ["t2", "A1:A2"]
    assert await book.off(book.where, "Stopa", "t1") == ["t2", "A2"]
    assert await book.off(book.where, "Stopa", "t2") is None
    assert await book.off(book.where, "Zbroj", "t1") is None
    assert await book.off(book.where, "Stupac", "t1") == ["t2", "A1:A2"]
    assert await book.off(book.where, "Nema", None) is None


async def test_a_tab_deleted_takes_its_tables_out_of_a_book_in_use(api, live):
    book, [_, (two, _)] = await tabs([Block("table", "t1", grid=Grid(["r1"], ["a"]))], [entry()])
    await Grant.objects.acreate(node_id=book.document, user=api.user, role=Role.OWN)
    held = live.book(book.document)
    await held.load()
    assert held.index()["tables"] == [["t2", "Ulaz", 2, 1, two]]
    response = await sync_to_async(api.delete)(f"/api/tabs/{two}")
    assert response.status_code == 204
    assert ("t2" in held.grids, held.index()["tables"]) == (False, [])
    live.release(book.document)


async def test_a_row_a_browser_came_to_hold_while_the_book_calculated_is_sent_as_written():
    doc, book, tab = await live(Block("table", "t", grid=Grid(["r1", "r2"], ["a"])))
    watcher = Watcher(Signed(1, "key"), Role.OWN)
    book.watchers.add(watcher)
    await book.off(book.watch, watcher, tab)
    await book.off(book.rows, watcher, "t", [(0, 1)])
    for _ in range(4):
        watcher.inbox.receive_nowait()
    await GridRow.objects.filter(row="r2").aupdate(cells={"a": {"text": "7"}}, values={"a": 7.0})

    await book.off(book._took, {"t": {}}, {"t": {"r1"}})

    assert watcher.inbox.receive_nowait() == {
        "type": "patch",
        "patches": [{"table": "t", "values": {"r2": {"a": number("7")}}}],
    }
