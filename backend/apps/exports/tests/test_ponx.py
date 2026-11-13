import io
import json
import zipfile

import pytest
from pycrdt import Doc

from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.collab import server
from apps.comments.models import Comment, Thread
from apps.content import blocks, grids
from apps.content.blocks import Block, Grid, Run, light_cell
from apps.content.models import DocumentBlob
from apps.exports.xlsx import doc_of
from apps.imports.tests.test_docx import PNG
from apps.jobs.tests import handed
from apps.users.models import User
from apps.versions import history

from .test_docx import made

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(server, "announce", lambda room, news: None)


def saved(api, document, versions: bool = False) -> zipfile.ZipFile:
    response = handed.saved(api, "ponx", document=document.pk, versions=versions)
    assert response["Content-Type"] == store.PONX
    assert response["Content-Disposition"] == 'attachment; filename="Ponuda.ponx"'
    data = content(response)
    assert store.put(io.BytesIO(data)).media_type == store.PONX
    return zipfile.ZipFile(io.BytesIO(data))


def same(data: bytes, room, held: dict | None = None) -> bool:
    """The state of the room, its items as they were made: an object in an attribute encodes
    its keys in no set order, so equal states need not be equal bytes."""
    ours, theirs = Doc(), doc_of(room)
    ours.apply_update(data)
    held = held or {}
    return blocks.clocks(ours) == blocks.clocks(theirs) and (
        blocks.read(ours, held) == blocks.read(theirs, held)
    )


def proposed(user: User) -> dict:
    return {"id": "p1", "author": "Ana Anić", "user": user.pk, "date": "2026-10-19T10:00:00Z"}


def test_a_document_goes_whole_into_its_own_file(api):
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana")
    content = [
        Block("heading", "h", attrs={"level": 1}, runs=[Run("Cijene")]),
        Block(
            "paragraph",
            "a",
            runs=[Run("Ukupno "), Run("100 €", {"insertion": proposed(ana)})],
        ),
        Block("table", "t", grid=Grid(["r1"], ["a"]), cells=[light_cell("r1:a", "Najam")]),
    ]
    document, tab, written = made(api, content)
    child = document.tabs.create(title="Prilog", position=1, parent=tab)
    picture = store.put(io.BytesIO(PNG))
    DocumentBlob.objects.create(document=document, blob=picture)
    document.source = store.put(io.BytesIO(b"{\\rtf1 Ponuda}"))
    document.save()
    anchor = {"from": written.position("a", 0), "to": written.position("a", 6, -1)}
    thread = Thread.objects.create(tab=tab, anchor=anchor, quote="Ukupno", resolved_by=api.user)
    Comment.objects.create(thread=thread, author=api.user, body="Provjeriti.")
    Comment.objects.create(thread=thread, outside_author="Iva Ivić", body="Provjereno.")

    archive = saved(api, document)
    first = archive.infolist()[0]
    assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED)
    assert archive.read("mimetype").decode() == store.PONX
    assert json.loads(archive.read("manifest.json"))["version"] == 4
    assert same(archive.read("own.yjs"), document.room)
    assert same(archive.read(f"tabs/{tab.pk}/state.yjs"), tab.room, grids.of_tab(tab))
    assert same(archive.read(f"tabs/{child.pk}/state.yjs"), child.room)
    heading, total, table = json.loads(archive.read(f"tabs/{tab.pk}/content.json"))
    assert (heading["type"], heading["runs"][0]["text"]) == ("heading", "Cijene")
    assert total["runs"][1] == {"text": "100 €", "marks": {"insertion": proposed(ana)}}
    [cell] = table["cells"]
    assert (cell["row"], cell["col"], cell["blocks"][0]["runs"][0]["text"]) == ("r1", "a", "Najam")
    assert json.loads(archive.read("grids.json")) == {}
    kept = json.loads(archive.read(f"tabs/{tab.pk}/grids.json"))
    assert kept == {
        "t": {k: v for k, v in grids.whole(grids.of_tab(tab)["t"]).items() if k != "tab"}
    }
    assert json.loads(archive.read(f"tabs/{child.pk}/grids.json")) == {}
    assert archive.read(f"files/{picture.sha256}") == PNG
    assert not archive.namelist()[-1].startswith("versions/")
    described = json.loads(archive.read("document.json"))
    assert described["tabs"] == [
        {"id": str(tab.pk), "parent": None, "position": 0, "title": tab.title},
        {"id": str(child.pk), "parent": str(tab.pk), "position": 1, "title": "Prilog"},
    ]
    assert described["files"] == {picture.sha256: "image/png", document.source_id: store.RTF}
    assert (described["shown"], described["original"]) == ([picture.sha256], document.source_id)
    assert described["styles"]["text"]["kind"] == "text"
    [kept] = described["threads"]
    assert (kept["tab"], kept["anchor"], kept["resolved_by"]) == (str(tab.pk), anchor, api.user.pk)
    remarks = [(each["author"], each["outside_author"], each["body"]) for each in kept["comments"]]
    assert remarks == [
        (api.user.pk, "", "Provjeriti."),
        (None, "Iva Ivić", "Provjereno."),
    ]
    assert described["people"] == {
        str(api.user.pk): {"name": "", "email": "ivo@example.com"},
        str(ana.pk): {"name": "Ana", "email": "ana@example.com"},
    }
    assert "versions" not in described


def test_its_versions_go_with_it_when_asked_for(api):
    table = Block("table", "t", grid=Grid(["r1"], ["a"]), cells=[light_cell("r1:a", "Najam")])
    document, tab, _ = made(api, [Block("paragraph", "a", runs=[Run("Prva")]), table])
    history.take(document, by=api.user, title="Prva verzija")
    archive = saved(api, document, versions=True)
    [version] = json.loads(archive.read("document.json"))["versions"]
    assert (version["number"], version["title"], version["editors"]) == (
        1,
        "Prva verzija",
        [api.user.pk],
    )
    assert same(archive.read(f"versions/{version['state']}.yjs"), document.room)
    [part] = version["tabs"]
    assert (part["tab"], part["parent"], part["position"]) == (str(tab.pk), None, 0)
    assert same(archive.read(f"versions/{part['state']}.yjs"), tab.room, grids.of_tab(tab))
    [grid] = version["grids"]
    assert (grid["tab"], grid["table"], grid["name"]) == (str(tab.pk), "t", "")
    rows = [
        row
        for piece in grid["pieces"]
        for row in json.loads(archive.read(f"versions/pieces/{piece}.json"))
    ]
    assert [row[0] for row in rows] == ["r1"]
