import io
import zipfile

import pytest
from asgiref.sync import sync_to_async
from pycrdt import Doc, Map, XmlElement

from apps.access.models import Grant, Role
from apps.access.tests.test_access import person, share
from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.collab import server
from apps.collab.models import Update
from apps.comments.models import Comment, Thread
from apps.content import blocks, grids, names, numbering, pages, people, styles, tallies
from apps.content.blocks import Block, Grid, Run, light_cell
from apps.content.models import DocumentBlob
from apps.content.sheets import Sheets
from apps.documents.models import Node, Tab
from apps.documents.tests.test_views import create
from apps.exports.tests.test_docx import made
from apps.jobs.tests.handed import done, saved
from apps.search.tests.test_search import pdf_bytes
from apps.users.models import User
from apps.versions import history
from apps.versions.models import Version

from .test_docx import PNG
from .test_views import bring, state, unbrought

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(server, "announce", lambda room, news: None)


def exported(api, document, versions: bool = False) -> bytes:
    return content(saved(api, "ponx", document=document.pk, versions=versions))


def proposed(user: User) -> dict:
    return {"id": "p1", "author": "Ana Anić", "user": user.pk, "date": "2026-10-19T10:00:00Z"}


def changed(document: Node, change) -> None:
    """The document's own state changed as given, with the grids of the tables it writes into
    its headers and footers."""
    own = state(document.room)
    before = own.get_state()
    sheets = Sheets({})
    change(own, sheets)
    Update.objects.create(document=document, room=document.room, data=own.get_update(before))
    for _, laid in sheets.tables():
        grids.put(document, None, laid)


CENTRED, BOLD = {"attrs": {"align": "center"}}, {"marks": {"strong": {}}}


def table(id: str, text: str, grid: Grid | None = None, **attrs) -> Block:
    grid = grid or Grid(["r1"], ["a"])
    return Block("table", id, attrs, grid=grid, cells=[light_cell("r1:a", text)])


def offer(api, ana: User) -> tuple[Node, Tab, Tab]:
    """A document of two tabs, the second one's pages its own, each with a table, with a
    proposed change, a comment, a picture, its original and a version."""
    content = [
        Block("heading", "h", attrs={"level": 1}, runs=[Run("Cijene")]),
        Block("paragraph", "a", runs=[Run("Ukupno "), Run("100 €", {"insertion": proposed(ana)})]),
        table(
            "t",
            "Najam",
            Grid(["r1", "r2"], ["a"], row_looks={"r1": CENTRED}, col_looks={"a": BOLD}),
            frozen="r1",
        ),
    ]
    document, tab, written = made(api, content)
    child = document.tabs.create(title="Prilog", position=1, parent=tab)
    header = [Block("paragraph", runs=[Run("Prilog A")]), table("z", "Zaglavlje")]

    def laid_out(own, sheets):
        page = {"width": 14.8, "height": 21}
        pages.write(own, sheets, page, {"header": header}, tab=str(child.pk))
        tallies.keep(own, str(tab.pk), content, styles.read(own)[1])

    changed(document, laid_out)
    for shown in (PNG, pdf_bytes("Prilog ponudi")):
        DocumentBlob.objects.create(document=document, blob=store.put(io.BytesIO(shown)))
    document.source = store.put(io.BytesIO(b"{\\rtf1 Ponuda}"))
    document.save()
    anchor = {"from": written.position("a", 0), "to": written.position("a", 6, -1)}
    thread = Thread.objects.create(tab=tab, anchor=anchor, quote="Ukupno", resolved_by=ana)
    Comment.objects.create(thread=thread, author=ana, body="Provjeriti.")
    Comment.objects.create(thread=thread, outside_author="Iva Ivić", body="Provjereno.")
    history.take(document, by=api.user, title="Prva verzija")
    return document, tab, child


def users_in(room) -> set[int]:
    return people.users(people.tab_roots(state(room)))


def test_a_file_of_our_own_comes_back_as_the_document_it_was(api):
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana")
    document, tab, child = offer(api, ana)
    data = exported(api, document, versions=True)
    response = bring(api, data, title="Ponuda natrag")
    again = Node.objects.get(pk=response["id"])
    assert (again.title, again.source_id, again.imported) == (
        "Ponuda natrag",
        document.source_id,
        None,
    )
    first, second = again.tabs_in_order()
    assert {first.pk, second.pk}.isdisjoint({tab.pk, child.pk})
    assert (second.parent_id, second.title, second.position) == (first.pk, "Prilog", 1)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        kept = archive.read(f"tabs/{tab.pk}/state.yjs")
    assert bytes(Update.objects.get(room=first.room).data) == kept
    assert blocks.read(state(first.room), grids.of_tab(first)) == blocks.read(
        state(tab.room), grids.of_tab(tab)
    )
    assert users_in(first.room) == {ana.pk}

    own, headed = state(again.room), grids.of_own(again)
    assert styles.read(own) == styles.read(state(document.room))
    assert pages.read(own, headed, str(second.pk))[0]["width"] == 14.8
    [line, held] = pages.read(own, headed, str(second.pk))[1]["header"]
    assert (line.text, held.cells[0].text) == ("Prilog A", "Zaglavlje")
    assert pages.read(own, headed, str(first.pk)) == pages.read(own, headed)
    for name in (pages.TABS, numbering.NUMBERS, tallies.HEADINGS):
        assert set(own.get(name, type=Map).keys()) <= {str(first.pk), str(second.pk)}
    assert str(first.pk) in own.get(tallies.HEADINGS, type=Map)

    [thread] = Thread.objects.filter(tab=first)
    before = Thread.objects.get(tab=tab)
    assert (thread.anchor, thread.resolved_by, thread.created_at) == (
        before.anchor,
        ana,
        before.created_at,
    )
    assert [
        (each.author, each.outside_author) for each in thread.comments.order_by("created_at")
    ] == [
        (ana, ""),
        (None, "Iva Ivić"),
    ]
    assert set(again.shown.values_list("blob", flat=True)) == set(
        document.shown.values_list("blob", flat=True)
    )
    [version] = Version.objects.filter(document=again)
    assert (version.number, version.title, list(version.editors.all())) == (
        1,
        "Prva verzija",
        [api.user],
    )
    assert {(part.tab, part.parent) for part in version.tabs.all()} == {
        (first.pk, None),
        (second.pk, first.pk),
    }
    assert str(second.pk) in state_of_version(version).get(pages.TABS, type=Map)
    assert sorted((part.tab is None, part.table) for part in version.grids.all()) == sorted(
        [(False, "t"), (True, *headed)]
    )
    [part] = version.grids.filter(table="t")
    assert (part.tab, part.frozen) == (first.pk, "r1")
    kept = history.grids_of(version)["t"]
    assert ([row.look for row in kept.rows], [col.look for col in kept.cols]) == (
        [CENTRED, None],
        [BOLD],
    )
    restored = grids.of_tab(first)["t"]
    assert restored.frozen == "r1"
    assert ([row.look for row in restored.rows], restored.look_at("r2", "a")) == (
        [CENTRED, None],
        BOLD,
    )


def state_of_version(version: Version) -> Doc:
    doc = Doc()
    doc.apply_update(bytes(version.state.data))
    return doc


def test_its_people_are_this_installations_by_their_email(api):
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana")
    document, _, _ = offer(api, ana)
    data = exported(api, document)
    ana.delete()
    response = bring(api, data, title="Bez Ane")
    first = Node.objects.get(pk=response["id"]).tabs_in_order()[0]
    assert users_in(first.room) == set()
    [_, total, _] = blocks.read(state(first.room), grids.of_tab(first))
    assert total.runs[1].marks["insertion"] == {
        key: value for key, value in proposed(ana).items() if key != "user"
    }
    thread = Thread.objects.get(tab=first)
    assert thread.resolved_by is None
    assert [each.outside_author for each in thread.comments.order_by("created_at")] == [
        "Ana",
        "Iva Ivić",
    ]

    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana")
    response = bring(api, data, title="Nova Ana")
    first = Node.objects.get(pk=response["id"]).tabs_in_order()[0]
    assert users_in(first.room) == {ana.pk}
    assert Thread.objects.get(tab=first).comments.order_by("created_at")[0].author == ana


def styled(document: Node, **looks) -> None:
    def put(own, sheets):
        stored = own.get(styles.STYLES, type=Map)
        for id, look in looks.items():
            stored[id] = Map({**styles.TEMPLATE[styles.STYLES]["text"], **look})

    changed(document, put)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_file_of_our_own_goes_after_a_documents_tabs(api, live):
    def checked():
        ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana")
        document, tab, child = offer(api, ana)
        styled(document, istaknuto={"size": 20}, napomena={"size": 9})
        data = exported(api, document, versions=True)
        target, before, _ = made(
            api, [Block("paragraph", runs=[Run("Uvod")])], istaknuto={"size": 14}
        )
        blob = store.put(io.BytesIO(data))
        sent = {"blob": blob.sha256, "title": "Ponuda"}
        found = done(api, "into", document=target.pk, **sent)
        assert found["report"] == {"fonts": [], "lost": {"versions": 1}, "accepted": 0}
        kept, first, second = target.tabs_in_order()
        assert (kept.pk, found["tab"]["id"]) == (before.pk, str(first.pk))
        assert (first.title, first.position, second.parent_id, second.title) == (
            "Ponuda",
            1,
            first.pk,
            "Prilog",
        )
        [moved] = grids.of_tab(first)
        assert moved not in grids.of_tab(tab) | grids.of_own(document) | grids.of_own(target)
        ours = blocks.read(state(first.room), grids.of_tab(first))
        theirs = blocks.read(state(tab.room), grids.of_tab(tab))
        assert ours[:2] == theirs[:2]
        assert (ours[2].id, ours[2].cells) == (moved, theirs[2].cells)
        assert users_in(first.room) == {ana.pk}
        assert Thread.objects.get(tab=first).comments.count() == 2
        assert not target.versions.exists()

        own, headed = state(target.room), grids.of_own(target)
        looks = styles.read(own)[1]
        assert (looks["istaknuto"]["size"], looks["napomena"]["size"]) == (14, 9)
        assert not pages.owns(own, str(first.pk))
        assert pages.read(own, headed, str(second.pk))[0]["width"] == 14.8
        [line, held] = pages.read(own, headed, str(second.pk))[1]["header"]
        assert (line.text, held.cells[0].text) == ("Prilog A", "Zaglavlje")
        [_, theirs] = pages.read(state(document.room), grids.of_own(document), str(child.pk))[1][
            "header"
        ]
        assert held.id not in grids.of_own(document)
        assert held.cells == theirs.cells
        [heading] = own.get(tallies.HEADINGS, type=Map)[str(first.pk)]
        assert heading["text"] == "Cijene"

    await sync_to_async(checked)()


def test_its_defined_names_come_back_with_it_and_go_beside_a_documents_own(api):
    pointed = {"table": "t", "from": {"row": "r1", "col": "a"}}
    document, _, _ = made(api, [table("t", "7,5", name="Cijene")])
    held = {"n1": names.entry("Tečaj", [pointed]), "n2": names.entry("Rok", ["30"], "t")}
    names.put(document, held)
    data = exported(api, document)
    response = bring(api, data, title="Ponuda natrag")
    assert names.of_document(Node.objects.get(pk=response["id"])) == held

    target, _, _ = made(api, [table("x", "1", name="Cijene")], title="Cjenik")
    names.put(target, {"m1": names.entry("Tečaj", ["7,6"])})
    sent = {"blob": store.put(io.BytesIO(data)).sha256, "title": "Ponuda"}
    done(api, "into", document=target.pk, **sent)
    _, first = target.tabs_in_order()
    [moved] = grids.of_tab(first)
    assert grids.of_tab(first)[moved].name == "Cijene (2)"
    found = [
        (each["name"], each["pieces"], each.get("table"))
        for each in names.of_document(target).values()
    ]
    assert sorted(found, key=lambda each: (each[0], each[2] or "")) == [
        ("Rok", ["30"], moved),
        ("Tečaj", ["7,6"], None),
        ("Tečaj", [{**pointed, "table": moved}], moved),
    ]


def test_a_copy_is_the_document_made_again_from_its_own_file(api):
    ana = person("ana@example.com", first_name="Ana")
    document, tab, _ = offer(api, ana.user)
    folder = create(api, "folder", "Ponude")
    Node.objects.filter(pk=document.pk).update(parent=folder)
    again = Node.objects.get(pk=done(api, "copy", document=document.pk, title="Kopija")["id"])
    assert (str(again.parent_id), again.title, again.source_id) == (
        folder,
        "Kopija",
        document.source_id,
    )
    first, second = again.tabs_in_order()
    assert blocks.read(state(first.room), grids.of_tab(first)) == blocks.read(
        state(tab.room), grids.of_tab(tab)
    )
    assert second.title == "Prilog"
    assert Thread.objects.get(tab=first).comments.count() == 2
    assert not again.versions.exists()

    assert share(api, folder, "read", id=ana.user.pk).status_code == 201
    mine = Node.objects.get(pk=done(ana, "copy", document=document.pk, title="Moja ponuda")["id"])
    assert mine.parent_id is None
    assert Grant.objects.filter(node=mine, user=ana.user, role=Role.OWN).exists()


def zipped(parts: dict[str, bytes]) -> bytes:
    found = io.BytesIO()
    with zipfile.ZipFile(found, "w") as archive:
        archive.writestr("mimetype", store.PONX, zipfile.ZIP_STORED)
        for name, data in parts.items():
            archive.writestr(name, data)
    return found.getvalue()


def parts_of(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist() if name != "mimetype"}


@pytest.mark.parametrize(
    "broken, error",
    [
        ({"manifest.json": b'{"format": "ponistra", "version": 5}'}, "newer_file"),
        ({"manifest.json": b'{"format": "ponistra", "version": 3}'}, "unreadable"),
        ({"manifest.json": b'{"format": "ponistra", "version": 1}'}, "unreadable"),
        ({"names.json": b'{"n": {"name": "Porez"}}'}, "unreadable"),
        ({"manifest.json": b'{"format": "other", "version": 1}'}, "unreadable"),
        ({"document.json": b"[]"}, "unreadable"),
        ({"own.yjs": b"garbage"}, "unreadable"),
    ],
)
def test_a_file_that_is_not_as_saved_is_refused_aloud(api, broken, error):
    document, _, _ = made(api, [Block("paragraph", runs=[Run("Tekst")])])
    data = zipped({**parts_of(exported(api, document)), **broken})
    assert unbrought(api, data) == (422, error)
    assert Node.objects.filter(title="Ugovor").count() == 0


def test_a_tab_the_editor_could_not_hold_is_refused(api):
    document, tab, _ = made(api, [Block("paragraph", runs=[Run("Tekst")])])

    def broken(doc):
        blocks.body_of(doc).children.append(XmlElement("script"))

    doc = state(tab.room)
    broken(doc)
    data = zipped(
        {**parts_of(exported(api, document)), f"tabs/{tab.pk}/state.yjs": doc.get_update()}
    )
    assert unbrought(api, data) == (422, "unreadable")
