import io
import threading
import zipfile
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from uuid import UUID

import pytest
from pycrdt import Doc, Map

from apps.access.tests.test_access import create, person, share
from apps.blobs import store
from apps.blobs.tests.office import FILLER, odf, ole, with_macros
from apps.blobs.tests.test_blobs import PDF, content
from apps.collab import server
from apps.collab.models import Update
from apps.comments.models import Comment, Thread
from apps.content import grids, lists, pages, slides, tallies
from apps.content.models import DocumentBlob
from apps.content.styles import STYLES, THEME
from apps.content.tests.helpers import Room
from apps.content.tests.test_proposals import joined
from apps.documents.models import Node, Tab
from apps.jobs.tests.handed import done, refused

from . import test_docx, test_xlsx
from .powerpoint_files import powerpoint_file
from .test_docx import PNG, named, run, section
from .word_files import numbered, p, theme, word_file

pytestmark = pytest.mark.django_db

COMMENTS = (
    '<w:comment w:id="0" w:author="Marko Marić" w:date="2026-03-02T10:15:00Z">'
    "<w:p><w:r><w:t>Provjeriti iznos.</w:t></w:r></w:p></w:comment>"
)
DRAWING = (
    '<w:r><w:drawing><wp:inline><wp:extent cx="2880000" cy="100"/><wp:docPr id="1" name="S"/>'
    '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic><pic:blipFill><a:blip r:embed="rId10"/></pic:blipFill></pic:pic>'
    "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
)
WORD = word_file(
    p("Ugovor")
    + f"<w:p>{run('Cijena je ')}"
    + '<w:commentRangeStart w:id="0"/>'
    + run("100 €")
    + '<w:commentRangeEnd w:id="0"/></w:p>'
    + f"<w:p>{DRAWING}</w:p>",
    media={"rId10": ("image1.png", PNG)},
    comments=COMMENTS,
    theme=theme("Georgia", "Arial"),
)


@pytest.fixture
def ana():
    return person("ana@example.com")


def _sent(data: bytes, fields: dict) -> dict:
    blob = store.put(io.BytesIO(data))
    return {"blob": blob.sha256, "title": "Ugovor", "parent": None, **fields}


def bring(client, data: bytes = WORD, **fields) -> dict:
    return done(client, "import", **_sent(data, fields))


def unbrought(client, data: bytes = WORD, **fields) -> tuple[int, str]:
    return refused(client, "import", **_sent(data, fields))


def state(room) -> Doc:
    doc = Doc()
    for data in Update.objects.filter(room=room).order_by("id").values_list("data", flat=True):
        doc.apply_update(bytes(data))
    return doc


def test_a_word_file_becomes_a_document_with_the_file_beside_it(api):
    response = bring(api)
    found = response
    assert (found["kind"], found["title"], found["original"]) == ("document", "Ugovor", "docx")
    assert found["imported"]["lost"] == {}
    node = Node.objects.get(pk=found["id"])
    assert node.source.media_type == store.DOCX

    own = state(node.room)
    assert dict(own.get(THEME, type=Map)) == {"headings": "Gelasio", "text": "Liberation Sans"}
    assert set(own.get(STYLES, type=Map).keys()) >= {"text", "title", "h1"}

    tab = Tab.objects.get(document=node)
    paragraph, priced, image = Room.of(tab).read()
    assert (paragraph.text, priced.text, image.type) == ("Ugovor", "Cijena je 100 €", "image")
    assert DocumentBlob.objects.filter(document=node, blob=image.attrs["blob"]).exists()

    thread = Thread.objects.get(tab=tab)
    start, end = thread.anchor["from"], thread.anchor["to"]
    assert (start["assoc"], end["assoc"]) == (0, -1)
    assert end["item"]["clock"] - start["item"]["clock"] == 4
    assert thread.quote == "100 €"
    [comment] = Comment.objects.filter(thread=thread)
    assert (comment.author, comment.outside_author, comment.body) == (
        None,
        "Marko Marić",
        "Provjeriti iznos.",
    )
    assert comment.created_at == datetime(2026, 3, 2, 10, 15, tzinfo=UTC)
    [shown] = api.get(f"/api/nodes/{node.pk}/threads").json()["threads"]
    assert (shown["comments"][0]["author"], shown["comments"][0]["outside_author"]) == (
        None,
        "Marko Marić",
    )

    served = api.get(f"/api/nodes/{node.pk}/source")
    assert served.status_code == 200
    assert content(served) == WORD


def test_a_document_imported_was_last_changed_when_its_file_was(api):
    found = bring(api, modified="2024-05-03T10:11:12Z")
    node = Node.objects.get(pk=found["id"])
    assert node.updated_at == datetime(2024, 5, 3, 10, 11, 12, tzinfo=UTC)
    assert found["updated_at"] == "2024-05-03T10:11:12Z"
    assert unbrought(api, modified="3.5.2024.") == (400, "invalid_modified")


def test_a_list_keeps_its_format_in_the_document(api):
    response = bring(api, word_file(numbered("Predmet", 10), numbering=test_docx.FORMATTED))
    node = Node.objects.get(pk=response["id"])
    [(id, format)] = state(node.room).get(lists.LISTS, type=Map).items()
    assert format[0] == {"numbering": "1", "prefix": "Članak ", "suffix": ".", "nested": False}
    [item] = Room.of(Tab.objects.get(document=node)).read()
    assert item.attrs == {"list": "number", "format": id}


def test_tracked_changes_are_written_as_proposals_and_all_accepted_as_word_would(api):
    ana = test_docx.ANA
    data = word_file(
        f'<w:p><w:pPr><w:rPr><w:ins w:id="1" {ana}/></w:rPr></w:pPr>'
        f'<w:ins w:id="2" {ana}>{run("Novi stavak")}</w:ins></w:p>'
        f'<w:p>{run("Rok je ")}<w:del w:id="3" {ana}><w:r><w:delText>30</w:delText></w:r>'
        f'</w:del><w:ins w:id="4" {ana}>{run("15")}</w:ins>'
        + run(" dana", f'<w:b/><w:rPrChange w:id="5" {ana}><w:rPr/></w:rPrChange>')
        + "</w:p>"
        + '<w:tbl><w:tblGrid><w:gridCol w:w="9000"/></w:tblGrid>'
        f"<w:tr><w:tc><w:p>{run('Stari')}</w:p></w:tc></w:tr>"
        f'<w:tr><w:trPr><w:del w:id="6" {ana}/></w:trPr>'
        f'<w:tc><w:p><w:del w:id="7" {ana}><w:r><w:delText>Brisani</w:delText></w:r>'
        "</w:del></w:p></w:tc></w:tr></w:tbl>"
        '<w:p><w:pPr><w:jc w:val="center"/>'
        f'<w:pPrChange w:id="8" {ana}><w:pPr/></w:pPrChange></w:pPr>{run("Kraj")}</w:p>'
    )
    response = bring(api, data)
    tab = Tab.objects.get(document_id=response["id"])
    room = Room.of(tab)
    first, second, table, last = room.read()
    assert "insertion" in first.attrs and "formatting" in last.attrs
    assert {name for run in second.runs for name in run.marks} == {
        "insertion",
        "deletion",
        "strong",
        "formatting",
    }
    assert "proposedRows" in table.attrs
    room.run({"op": "accept"})
    first, second, table, last = room.read()
    assert (first.text, second.text, last.text) == ("Novi stavak", "Rok je 15 dana", "Kraj")
    assert joined(second.runs) == [("Rok je 15", {}), (" dana", {"strong": {}})]
    assert (len(table.grid.rows), table.attrs.get("proposedRows")) == (1, None)
    assert (first.attrs, last.attrs) == ({}, {"align": "center"})


@pytest.fixture
def converter(settings):
    """A converter answering each request with the next of its replies."""
    replies: list[tuple[int, bytes]] = []
    received: list[tuple[str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.rfile.read(int(self.headers["Content-Length"]))))
            status, data = replies.pop(0)
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings.CONVERTER_URL = f"http://127.0.0.1:{server.server_port}"
    yield SimpleNamespace(replies=replies, received=received)
    server.shutdown()
    server.server_close()


def test_an_rtf_file_comes_in_as_libreoffice_makes_it_docx(api, converter):
    rtf = b"{\\rtf1\\ansi Ugovor\\par}"
    converter.replies.append((200, WORD))
    response = bring(api, rtf)
    assert converter.received == [("/docx/rtf", rtf)]
    node = Node.objects.get(pk=response["id"])
    assert node.source.media_type == store.RTF
    served = api.get(f"/api/nodes/{node.pk}/source?download=1")
    assert (served["Content-Type"], content(served)) == (store.RTF, rtf)
    assert 'filename="Ugovor.rtf"' in served["Content-Disposition"]

    converter.replies.extend([(422, b""), (413, b""), (500, b"")])
    assert unbrought(api, rtf) == (422, "unreadable")
    assert unbrought(api, rtf) == (413, "too_large")
    assert unbrought(api, rtf) == (503, "converter_unavailable")
    assert Node.objects.count() == 1


def priced(tmp_path):
    return test_xlsx.book(
        tmp_path,
        {
            "Cijene": {"A1": "2", "B1": "=A1*Porez", "C1": "=FOOBAR(1)"},
            "Popust": {"A1": "=Cijene!B1*0.9"},
        },
        lambda model: model.new_defined_name("Porez", None, "1.25"),
    ).read_bytes()


def test_a_spreadsheet_becomes_a_tab_for_each_sheet_with_its_names(api, tmp_path):
    response = bring(api, priced(tmp_path), title="Cijene")
    node = Node.objects.get(pk=response["id"])
    assert (node.source.media_type, node.imported["functions"]) == (store.XLSX, ["FOOBAR"])
    first, second = Tab.objects.filter(document=node).order_by("position")
    assert (first.title, second.title) == ("Cijene", "Popust")
    room = Room.of(first)
    table, end = room.read()
    assert (table.attrs["name"], end.type) == ("Cijene", "paragraph")
    assert table.grid.values[test_xlsx.key(table, "B1")] == {"text": "2,5", "kind": "number"}
    (other, _) = Room.of(second).read()
    assert other.attrs["name"] == "Popust"
    assert other.grid.values[test_xlsx.key(other, "A1")] == {"text": "2,25", "kind": "number"}
    [(_, name)] = room.names.items()
    assert (name["name"], name["pieces"]) == ("Porez", ["1.25"])
    assert pages.read(state(node.room), grids.of_own(node))[0] == pages.DEFAULT


@pytest.mark.parametrize(
    "made, media_type, extension",
    [
        (lambda tmp_path: WORD, store.DOCM, "docm"),
        (priced, store.XLSM, "xlsm"),
        (lambda tmp_path: powerpoint_file(), store.PPTM, "pptm"),
    ],
)
def test_a_file_with_macros_comes_in_with_their_source_to_read_and_goes_back_with_them(
    api, tmp_path, made, media_type, extension
):
    data = with_macros(made(tmp_path))
    response = bring(api, data)
    imported = response["imported"]
    assert imported["lost"]["macros"] == 1
    assert imported["macros"] == [
        {"name": "Module1", "code": 'Sub Zbroji()\n    Range("A1") = "Šećer"\nEnd Sub'}
    ]
    node = Node.objects.get(pk=response["id"])
    assert node.source.media_type == media_type
    served = api.get(f"/api/nodes/{node.pk}/source?download=1")
    assert (served["Content-Type"], content(served)) == (media_type, data)
    assert f'filename="Ugovor.{extension}"' in served["Content-Disposition"]


def test_an_ods_file_comes_in_as_libreoffice_makes_it_xlsx(api, converter, tmp_path):
    ods = odf(store.ODS)
    converter.replies.append((200, priced(tmp_path)))
    response = bring(api, ods, title="Cijene")
    assert converter.received == [("/xlsx/ods", ods)]
    node = Node.objects.get(pk=response["id"])
    assert node.source.media_type == store.ODS
    served = api.get(f"/api/nodes/{node.pk}/source?download=1")
    assert 'filename="Cijene.ods"' in served["Content-Disposition"]


@pytest.mark.django_db(transaction=True)
def test_a_spreadsheet_imported_into_a_document_takes_its_pages(api, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "announce", lambda room, news: None)
    document = bring(api)["id"]
    node = Node.objects.get(pk=document)
    sent = {"blob": store.put(io.BytesIO(priced(tmp_path))).sha256, "title": "Cijene"}
    assert done(api, "into", document=document, **sent)["report"]["functions"] == ["FOOBAR"]
    first, added, _ = Tab.objects.filter(document=node).order_by("position")
    own = state(node.room)
    assert str(added.pk) not in own.get(pages.TABS, type=Map)
    assert pages.read(own, grids.of_own(node), str(added.pk)) == pages.read(
        own, grids.of_own(node), str(first.pk)
    )
    (table, _) = Room.of(added).read()
    assert table.attrs["name"] == "Cijene"
    done(api, "into", document=document, **sent)
    tabs = Tab.objects.filter(document=node).order_by("position")[1:]
    assert [tab.title for tab in tabs] == ["Cijene", "Popust", "Cijene (2)", "Popust (2)"]
    assert [Room.of(tab).read()[0].attrs["name"] for tab in tabs] == [tab.title for tab in tabs]


def test_a_presentation_becomes_a_document_of_its_sections_in_its_slide_template(api):
    response = bring(api, powerpoint_file(), title="Izvještaj")
    assert (response["original"], response["imported"]["lost"]["positions"]) == (
        "pptx",
        1,
    )
    node = Node.objects.get(pk=response["id"])
    assert node.source.media_type == store.PPTX
    tabs = Tab.objects.filter(document=node).order_by("position")
    assert [tab.title for tab in tabs] == ["Uvod", "Glavno", "Kraj"]
    template = slides.template_of(state(node.room))
    assert (template.width, template.height, template.built_in) == (33.867, 19.05, False)
    names = {layout["id"]: layout["name"] for layout in template.layouts}
    title, subtitle = Room.of(tabs[0]).read()
    assert (names[title.attrs["layout"]], subtitle.text) == ("Naslovni slajd", "Zagreb, 2026")
    image = next(block for block in Room.of(tabs[1]).read() if block.type == "image")
    assert DocumentBlob.objects.filter(document=node, blob=image.attrs["blob"]).exists()


@pytest.mark.parametrize(
    "data, media_type, kind",
    [(odf(store.ODP), store.ODP, "odp"), (ole({"PowerPoint Document": FILLER}), store.PPT, "ppt")],
    ids=["odp", "ppt"],
)
def test_odp_and_ppt_files_come_in_as_libreoffice_makes_them_pptx(
    api, converter, data, media_type, kind
):
    converter.replies.append((200, powerpoint_file()))
    response = bring(api, data, title="Izvještaj")
    assert response["original"] == "pptx"
    assert converter.received == [(f"/pptx/{kind}", data)]
    node = Node.objects.get(pk=response["id"])
    assert node.source.media_type == media_type
    assert Tab.objects.filter(document=node).count() == 3


@pytest.mark.django_db(transaction=True)
def test_a_presentation_imported_into_a_document_brings_its_layouts_after_the_documents(
    api, monkeypatch
):
    monkeypatch.setattr(server, "announce", lambda room, news: None)
    document = bring(api)["id"]
    node = Node.objects.get(pk=document)
    sent = {"blob": store.put(io.BytesIO(powerpoint_file())).sha256, "title": "Prilog"}
    done(api, "into", document=document, **sent)
    template = slides.template_of(state(node.room))
    size = slides.BUILT_IN["size"]
    ours = slides.built_in(*size.values())
    assert (template.width, template.height, template.built_in) == (*size.values(), False)
    assert template.layouts[: len(ours)] == ours
    added = template.layouts[len(ours) :]
    assert [layout["name"] for layout in added][:2] == ["Naslovni slajd", "Naslov i sadržaj"]
    body = added[1]["boxes"]["body"]
    across = size["width"] / 33.867
    assert body["x"] == pytest.approx(1.5 * across, abs=0.001)
    assert body["w"] == pytest.approx(30 * across, abs=0.001)
    first, *imported = Tab.objects.filter(document=node).order_by("position")
    assert [tab.title for tab in imported] == ["Uvod", "Glavno", "Kraj"]
    (title, _) = Room.of(imported[0]).read()
    assert title.attrs["layout"] == added[0]["id"]


def test_without_the_converter_an_odt_file_is_refused_aloud(api, settings):
    settings.CONVERTER_URL = "http://127.0.0.1:9"
    assert unbrought(api, odf(store.ODT)) == (503, "converter_unavailable")


@pytest.mark.django_db(transaction=True)
def test_a_file_imported_into_a_document_follows_its_tabs_in_its_styles(api, ana, monkeypatch):
    announced = []
    monkeypatch.setattr(server, "announce", lambda room, news: announced.append((room, news)))
    document = bring(api)["id"]
    node = Node.objects.get(pk=document)
    text = dict(state(node.room).get(STYLES, type=Map)["text"])
    data = word_file(
        numbered("Predmet", 10) + p("Citat", "Quote1"),
        numbering=test_docx.FORMATTED,
        styles=test_docx.STYLES,
        theme=theme("Arial", "Arial"),
        section=section(landscape=True),
    )
    blob = store.put(io.BytesIO(data)).sha256
    sent = {"blob": blob, "title": "Prilog A"}
    share(api, document, "read", id=ana.user.pk)
    assert refused(ana, "into", document=document, **sent) == (403, "forbidden")

    found = done(api, "into", document=document, **sent)
    first, added = Tab.objects.filter(document=node).order_by("position")
    assert (found["tab"]["id"], found["tab"]["title"]) == (str(added.pk), "Prilog A")
    assert found["report"]["fonts"] == []
    assert announced == [(node.room, "tabs")]
    assert added.title == "Prilog A"
    own = state(node.room)
    assert dict(own.get(THEME, type=Map)) == {"headings": "Gelasio", "text": "Liberation Sans"}
    assert dict(own.get(STYLES, type=Map)["text"]) == text
    assert own.get(STYLES, type=Map)["Quote1"]["name"] == "Citat"
    [(id, _)] = own.get(lists.LISTS, type=Map).items()
    item, quote = Room.of(added).read()
    assert (item.attrs["format"], quote.attrs["style"]) == (id, "Quote1")
    assert pages.read(own, grids.of_own(node), str(first.pk))[0]["width"] == 21.0
    assert pages.read(own, grids.of_own(node), str(added.pk))[0]["width"] == 29.7

    done(api, "into", document=document, **sent)
    assert len(state(node.room).get(lists.LISTS, type=Map)) == 1
    assert Tab.objects.filter(document=node).count() == 3


def test_only_an_office_file_is_imported(api):
    assert unbrought(api, PDF) == (415, "not_importable")
    assert refused(api, "import", blob="0" * 64, title="Ugovor") == (400, "unknown_file")
    broken = io.BytesIO()
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("word/document.xml", "<broken")
    assert unbrought(api, broken.getvalue()) == (422, "unreadable")
    assert not Node.objects.exists()


def test_importing_into_a_folder_needs_the_right_to_edit_it(api, ana):
    folder = create(api, "folder", "Ugovori")
    share(api, folder, "read", id=ana.user.pk)
    assert unbrought(ana, parent=folder) == (403, "forbidden")
    share(api, folder, "edit", id=ana.user.pk)
    response = bring(ana, parent=folder)
    assert response["parent"] == folder


def test_the_report_is_put_away_by_an_editor(api, ana):
    document = bring(api)["id"]
    share(api, document, "read", id=ana.user.pk)
    assert ana.get(f"/api/nodes/{document}/source").status_code == 200
    assert ana.delete(f"/api/nodes/{document}/report").status_code == 403
    response = api.delete(f"/api/nodes/{document}/report")
    assert response.status_code == 200
    assert response.json()["imported"] is None
    assert Node.objects.get(pk=document).source is not None


def test_a_document_is_imported_again_from_its_file_its_own_comments_and_first_tabs_kept(api, ana):
    document = bring(api)["id"]
    node = Node.objects.get(pk=document)
    tab = Tab.objects.get(document=node)
    added = api.post(f"/api/nodes/{document}/tabs", {}, content_type="application/json").json()
    own = Thread.objects.create(tab=tab, anchor={"from": {}, "to": {}}, quote="Ugovor")
    Comment.objects.create(thread=own, author=api.user, body="Pogledati")
    api.delete(f"/api/nodes/{document}/report")
    share(api, document, "read", id=ana.user.pk)
    assert refused(ana, "reimport", document=document) == (403, "forbidden")

    found = done(api, "reimport", document=document)
    assert found["imported"]["lost"] == {}
    again = Node.objects.get(pk=document)
    [kept] = Tab.objects.filter(document=again)
    assert (kept.pk, again.room == node.room, kept.room == tab.room) == (tab.pk, False, False)
    assert [block.text for block in Room.of(kept).read()][:2] == ["Ugovor", "Cijena je 100 €"]
    assert Thread.objects.filter(tab=kept).count() == 2
    assert (
        Comment.objects.get(thread__tab=kept, outside_author="Marko Marić").thread.quote == "100 €"
    )
    assert Thread.objects.filter(pk=own.pk).exists()
    before, after = again.versions.order_by("number")
    assert {part.tab for part in before.tabs.all()} == {tab.pk, UUID(added["id"])}
    assert [part.tab for part in after.tabs.all()] == [tab.pk]

    made = create(api, "document", "Bilješke")
    assert refused(api, "reimport", document=made) == (409, "not_imported")


def test_a_document_made_here_has_no_source(api):
    document = create(api, "document", "Bilješke")
    assert api.get(f"/api/nodes/{document}/source").status_code == 404


def test_sections_come_over_in_one_tab_each_after_the_first_after_its_section_break(api):
    data = word_file(
        p("Ugovor", "Heading1")
        + f"<w:p><w:pPr>{section(named('header', 'default', 'header'))}</w:pPr>"
        + f'{run("Prije ")}<w:commentRangeStart w:id="0"/>{run("kraja")}</w:p>'
        + p("Prilog", "Heading1")
        + f'<w:p>{run("Tablica")}<w:commentRangeEnd w:id="0"/></w:p>',
        section=section(landscape=True),
        header=f"<w:p>{run('Zaglavlje')}</w:p>",
        comments=COMMENTS,
        styles=test_docx.STYLES,
    )
    found = bring(api, data, title="Ponuda")
    assert found["imported"]["lost"] == {}
    node = Node.objects.get(pk=found["id"])
    [tab] = Tab.objects.filter(document=node)
    assert tab.title == ""
    content = Room.of(tab).read()
    assert [block.text or block.type for block in content] == [
        "Ugovor",
        "Prije kraja",
        "sectionBreak",
        "Prilog",
        "Tablica",
    ]
    own = state(node.room)
    setup, parts = pages.read(own, grids.of_own(node), str(tab.pk))
    assert (setup["width"], [block.text for block in parts["header"]]) == (21.0, ["Zaglavlje"])
    setup, parts = pages.section(own, grids.of_own(node), str(tab.pk), content[2].id)
    assert (setup["width"], setup["height"], parts) == (29.7, 21.0, {})
    headings = own.get(tallies.HEADINGS, type=Map)
    assert [entry["text"] for entry in headings[str(tab.pk)]] == ["Ugovor", "Prilog"]
    assert Thread.objects.get().quote == "kraja\nPrilog\nTablica"
