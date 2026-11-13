from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.access import rights
from apps.access.tests.test_access import create, person, share
from apps.blobs import store
from apps.blobs.models import Blob
from apps.blobs.tests.uploads import held, uploaded
from apps.content import elements, words
from apps.content.blocks import Block, Grid, Run, light_cell
from apps.content.models import GridRow
from apps.content.tests.helpers import fill
from apps.documents import board_data
from apps.documents.models import Node
from apps.imports.tests.word_files import p, word_file
from apps.search import extraction
from apps.search.models import BlobPage, BlobText
from apps.search.views import matching

pytestmark = pytest.mark.django_db

JSON = "application/json"
MARK, END = "", ""


def pdf_bytes(*pages: str) -> bytes:
    """A PDF with one line of Helvetica text per page."""
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    kids = []
    for index, text in enumerate(pages):
        page, content = 4 + 2 * index, 5 + 2 * index
        line = text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(")
        stream = b"BT /F1 12 Tf 72 720 Td (" + line.replace(b")", b"\\)") + b") Tj ET"
        objects[content] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        objects[page] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]"
            b" /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content
        )
        kids.append(b"%d 0 R" % page)
    objects[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))
    out = bytearray(b"%PDF-1.7\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n%s\nendobj\n" % (number, objects[number])
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for number in sorted(objects):
        out += b"%010d 00000 n \n" % offsets[number]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def upload_file(client, title, data: bytes, parent=None) -> str:
    sha256 = uploaded(client, data)["sha256"]
    response = client.post(
        "/api/nodes",
        {"kind": "file", "title": title, "blob": sha256, "parent": parent},
        content_type=JSON,
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def extract_all() -> None:
    while extraction.extract_next():
        pass


def search(client, q, **params) -> list[dict]:
    response = client.get("/api/search", {"q": q, **params})
    assert response.status_code == 200, response.json()
    return response.json()["documents"]


def titles(results) -> list[str]:
    return [result["title"] for result in results]


def test_a_place_of_the_users_own_is_no_hit_as_its_name_depends_on_the_language(api):
    api.post("/api/links", {}, content_type="application/json")
    assert titles(search(api, "links")) == []


@pytest.mark.parametrize("q", ["izvještaj", "izvjestaj", "IZVJEŠTAJ", "izvje", "ponuda", "ponude"])
def test_a_title_is_found_by_its_stem_with_or_without_accents(api, q):
    create(api, "document", "Izvještaj o ponudama")
    assert titles(search(api, q)) == ["Izvještaj o ponudama"]


def test_a_typo_still_finds_a_title(api):
    create(api, "document", "Ugovor o održavanju")
    assert titles(search(api, "ugvor")) == ["Ugovor o održavanju"]


def test_part_of_a_number_finds_a_title(api):
    create(api, "document", "Ponuda 2026-114")
    assert titles(search(api, "114")) == ["Ponuda 2026-114"]


def test_a_tab_title_leads_to_its_tab(api):
    document = create(api, "document", "Ponuda")
    tab = api.post(f"/api/nodes/{document}/tabs", {"title": "Cjenik rada"}, JSON).json()
    [result] = search(api, "cjenik")
    assert (result["id"], result["source"]) == (document, "tab")
    assert result["tab"] == {"id": tab["id"], "title": "Cjenik rada"}


def test_text_in_a_tab_leads_to_its_block_with_its_address(api):
    ana = person("ana@example.com")
    document = create(api, "document", "Ponuda")
    tab = Node.objects.get(pk=document).tabs.get()
    heading = Block("heading", "h1", {"level": 1}, [Run("Troškovi")])
    fill(tab, [heading, Block("paragraph", "p1", runs=[Run("Cijena dostave u Rijeku")])])
    elements.tend(timezone.now() + timedelta(minutes=1))
    [result] = search(api, "dostava")
    assert (result["id"], result["source"], result["tab"]["id"]) == (document, "block", str(tab.pk))
    assert (result["block"], result["address"]) == ("p1", {"section": "1", "paragraph": 1})
    assert f"{MARK}dostave{END}" in result["snippet"]
    assert search(ana, "dostava") == []
    share(api, document, "read", id=ana.user.pk)
    assert [result["block"] for result in search(ana, "dostava")] == ["p1"]
    api.post("/api/nodes/trash", {"nodes": [document]}, content_type=JSON)
    assert search(ana, "dostava") == search(api, "dostava") == []


def test_a_pdf_a_tab_shows_leads_to_its_block_and_page_within_the_pages_it_shows(api):
    ana = person("ana@example.com")
    document = create(api, "document", "Ponuda")
    data = pdf_bytes("Sadrzaj", "Cijena dostave", "Popust")
    shown = api.post(f"/api/nodes/{document}/pdfs", data, content_type="application/pdf")
    sha256 = shown.json()["blob"]
    tab = Node.objects.get(pk=document).tabs.get()
    intro = Block("paragraph", "p1", runs=[Run("Uvod")])
    fill(tab, [intro, Block("pdf", "f1", {"blob": sha256, "title": "Cjenik", "first": 2})])
    elements.tend(timezone.now() + timedelta(minutes=1))
    extract_all()
    [result] = search(api, "dostava")
    assert (result["id"], result["source"], result["tab"]["id"]) == (document, "block", str(tab.pk))
    assert (result["block"], result["page"], result["address"]) == ("f1", 2, {"pdf": 1})
    assert f"{MARK}dostave{END}" in result["snippet"]
    assert search(api, "sadrzaj") == []
    assert search(ana, "dostava") == []

    fill(tab, [Block("pdf", "f1", {"blob": sha256, "last": 2.0})], timezone.now())
    elements.tend(timezone.now() + timedelta(minutes=2))
    assert [result["page"] for result in search(api, "sadrzaj")] == [1]
    assert search(api, "popust") == []


def test_a_cell_leads_to_its_table_and_its_place_there_by_what_it_shows(api):
    document = create(api, "document", "Ponuda")
    tab = Node.objects.get(pk=document).tabs.get()
    cells = [light_cell("r1:c2", "Dostava u Rijeku")]
    table = Block(
        "table", "t", {"name": "Rute"}, grid=Grid(["r1", "r2"], ["c1", "c2"]), cells=cells
    )
    fill(tab, [Block("heading", "h1", {"level": 1}, [Run("Troškovi")]), table])
    GridRow.objects.filter(grid__tab=tab, row="r2").update(shown={"c1": "Zagreb"})
    elements.tend(timezone.now() + timedelta(minutes=1))
    words.read()
    [result] = search(api, "dostava")
    assert (result["source"], result["tab"]["id"], result["block"]) == ("block", str(tab.pk), "t")
    assert result["address"] == {"section": "1", "table": 1, "cell": "B1", "name": "Rute"}
    [result] = search(api, "zagreb")
    assert (result["block"], result["address"]["cell"]) == ("t", "A2")


def test_a_comment_on_a_file_leads_to_its_thread_there(api):
    file = upload_file(api, "Najam", pdf_bytes("Cijena najma"))
    thread = api.post(
        f"/api/nodes/{file}/threads",
        {"anchor": {"page": 1, "at": [72, 760]}, "quote": "", "body": "Treba li jamstvo?"},
        content_type=JSON,
    ).json()
    [result] = search(api, "jamstva")
    assert (result["id"], result["source"], result["tab"], result["thread"]) == (
        file,
        "comment",
        None,
        thread["id"],
    )


def test_a_comment_leads_to_its_thread_on_its_tab(api):
    ana = person("ana@example.com")
    document = create(api, "document", "Ponuda")
    tab = Node.objects.get(pk=document).tabs.get()
    end = {"type": None, "tname": "body", "item": None, "assoc": 0}
    thread = api.post(
        f"/api/nodes/{document}/threads",
        {
            "tab": str(tab.pk),
            "anchor": {"from": end, "to": end},
            "quote": "rok",
            "body": "Treba li jamstvo za isporuku?",
        },
        content_type=JSON,
    ).json()
    [result] = search(api, "jamstva")
    assert (result["source"], result["tab"]["id"], result["thread"]) == (
        "comment",
        str(tab.pk),
        thread["id"],
    )
    assert f"{MARK}jamstvo{END}" in result["snippet"]
    assert search(ana, "jamstva") == []


def test_pdf_pages_are_found_with_their_number_and_a_marked_snippet(api):
    file = upload_file(api, "Ugovor 2025", pdf_bytes("Predmet ugovora", "Kalibracija osi godisnje"))
    assert search(api, "kalibracija") == []
    extract_all()
    [result] = search(api, "kalibracija")
    assert (result["id"], result["source"], result["page"], result["hits"]) == (file, "page", 2, 1)
    assert f"{MARK}Kalibracija{END} osi godisnje" == result["snippet"]
    assert BlobText.objects.get().page_count == 2
    assert not extraction.extract_next()


def test_an_office_file_kept_as_a_file_is_found_by_its_text(api):
    file = upload_file(api, "Uvjeti", word_file(p("Uvjeti") + p("Jamstveni rok dvije godine")))
    extract_all()
    [result] = search(api, "jamstveni")
    assert (result["id"], result["source"]) == (file, "page")


def test_a_board_is_found_by_what_its_page_shows_and_what_it_keeps(api):
    page = (
        b"<!doctype html><html><body><p>Kalibracija osi</p><script>skripta()</script></body></html>"
    )
    file = upload_file(api, "Plan", page)
    extract_all()
    [shown] = search(api, "kalibracija")
    assert (shown["id"], shown["source"]) == (file, "page")
    assert search(api, "skripta") == []

    kept = {"naslov": "Jamstveni rok", "koraci": [{"opis": "Servis stroja"}], "broj": 7}
    board_data.written(
        Node.objects.get(pk=file),
        [{"op": "set", "collection": "stavke", "key": "a", "data": kept}],
        api.user,
    )
    [found] = search(api, "jamstveni")
    assert (found["id"], found["source"]) == (file, "data")
    assert f"{MARK}Jamstveni{END} rok" in found["snippet"]
    assert [each["id"] for each in search(api, "servis")] == [file]
    assert search(api, "naslov") == []

    ana = person("ana@example.com")
    assert search(ana, "jamstveni") == []


def test_a_text_file_is_found_by_its_text(api):
    file = upload_file(api, "Postavke", "kalibracija_osi = 0,02\n".encode("utf-16"))
    extract_all()
    [result] = search(api, "kalibracija_osi")
    assert (result["id"], result["source"]) == (file, "page")


def test_titles_rank_above_content(api):
    upload_file(api, "Zapisnik", pdf_bytes("Kalibracija osi"))
    create(api, "document", "Kalibracija")
    extract_all()
    assert titles(search(api, "kalibracija")) == ["Kalibracija", "Zapisnik"]


def test_one_result_per_node_with_its_best_hit_and_a_count(api):
    upload_file(api, "Kalibracija", pdf_bytes("Kalibracija X", "Kalibracija Y"))
    extract_all()
    [result] = search(api, "kalibracija")
    assert (result["source"], result["hits"]) == ("title", 3)


def test_the_same_bytes_in_two_files_are_extracted_once(api):
    data = pdf_bytes("Kalibracija osi")
    upload_file(api, "Prvi", data)
    upload_file(api, "Drugi", data)
    extract_all()
    assert BlobText.objects.count() == 1
    assert sorted(titles(search(api, "osi"))) == ["Drugi", "Prvi"]


@pytest.mark.django_db(transaction=True)
def test_a_pdf_the_drawer_holds_is_read_as_soon_as_it_lets_go(api):
    file = Node.objects.get(pk=upload_file(api, "Ponuda", pdf_bytes("Kalibracija osi")))
    with held(file.blob_id):
        assert extraction.extract_next()
    assert titles(search(api, "osi")) == ["Ponuda"]


def test_an_unreadable_pdf_is_recorded_once(api):
    upload_file(api, "Pokvaren", b"%PDF-1.7\nnot really a pdf")
    assert extraction.extract_next()
    assert BlobText.objects.get().failed
    assert not extraction.extract_next()


def test_extracted_text_goes_with_its_bytes(api, settings):
    file = upload_file(api, "Zapisnik", pdf_bytes("Kalibracija osi"))
    extract_all()
    settings.BLOB_GRACE = timedelta(0)
    store.collect()
    assert BlobPage.objects.count() == 1
    api.post("/api/nodes/trash", {"nodes": [file]}, content_type=JSON)
    assert api.post("/api/trash/purge", {"nodes": [file]}, JSON).status_code == 204
    store.collect()
    assert (Blob.objects.count(), BlobText.objects.count(), BlobPage.objects.count()) == (0, 0, 0)


def test_search_shows_only_what_the_user_can_read(api):
    ana = person("ana@example.com")
    folder = create(api, "folder", "Ponude")
    create(api, "document", "Ponuda za Rijeku", folder)
    assert search(ana, "rijeka") == []
    assert share(api, folder, "read", id=ana.user.pk).status_code == 201
    [result] = search(ana, "rijeka")
    assert result["root"] == "shared"
    assert [above["title"] for above in result["path"]] == ["Ponude"]
    [mine] = search(api, "rijeka")
    assert (mine["root"], [above["title"] for above in mine["path"]]) == ("mine", ["Ponude"])


def test_a_grant_under_a_trashed_folder_finds_nothing(api):
    ana = person("ana@example.com")
    folder = create(api, "folder", "Ponude")
    document = create(api, "document", "Ponuda za Rijeku", folder)
    share(api, document, "read", id=ana.user.pk)
    assert titles(search(ana, "rijeka")) == ["Ponuda za Rijeku"]
    api.post("/api/nodes/trash", {"nodes": [folder]}, content_type=JSON)
    assert search(ana, "rijeka") == []
    assert search(api, "rijeka") == []


def test_an_inactive_user_reads_nothing(api):
    create(api, "document", "Ponuda")
    api.user.is_active = False
    sql, params = rights.readable(api.user)
    assert Node.objects.raw(sql, params)[:] == []


def test_filters_narrow_by_kind_folder_and_creator(api):
    folder = create(api, "folder", "Ponude")
    create(api, "document", "Ponuda Rijeka", folder)
    create(api, "document", "Ponuda Split")
    assert titles(search(api, "ponud vrsta:mapa")) == ["Ponude"]
    assert titles(search(api, "ponud", **{"in": folder})) == ["Ponuda Rijeka"]
    assert titles(search(api, "ponud mapa:ponude")) == ["Ponuda Rijeka"]
    assert len(search(api, "ponud od:ivo")) == 3
    assert search(api, "ponud od:ana") == []


def test_a_period_is_when_a_node_was_made_or_on_a_click_when_it_was_changed(api):
    made = create(api, "document", "Ponuda Rijeka")
    create(api, "document", "Ponuda Split")
    Node.objects.filter(pk=made).update(created_at=datetime(2025, 2, 10, 9, tzinfo=UTC))
    assert titles(search(api, "ponud datum:2025-02")) == ["Ponuda Rijeka"]
    assert titles(search(api, "ponud datum:10.2.2025.")) == ["Ponuda Rijeka"]
    assert titles(search(api, "ponud datum:..2025")) == ["Ponuda Rijeka"]
    assert search(api, "ponud izmjena:2025-02") == []
    assert len(search(api, "ponud izmjena:tjedan")) == 2


def test_filters_alone_list_the_newest_first(api):
    create(api, "document", "Ponuda Rijeka")
    create(api, "document", "Ugovor Split")
    assert titles(search(api, "vrsta:dokument")) == ["Ugovor Split", "Ponuda Rijeka"]


def test_web_search_syntax(api):
    create(api, "document", "Ponuda Rijeka")
    create(api, "document", "Ponuda Split")
    assert titles(search(api, "ponuda -split")) == ["Ponuda Rijeka"]
    assert titles(search(api, '"ponuda rijeka"')) == ["Ponuda Rijeka"]
    assert sorted(titles(search(api, "rijeka or split"))) == ["Ponuda Rijeka", "Ponuda Split"]


@pytest.mark.parametrize(
    "q, params",
    [
        ("ponuda rij", ["ponuda ", "'rij':*"]),
        ("rij", ["", "'rij':*"]),
        ("ponuda rij ", ["ponuda rij "]),
        ('"ponuda rij', ['"ponuda rij']),
        ("ponuda -rij", ["ponuda -rij"]),
        ("ponuda or rij", ["ponuda or rij"]),
    ],
)
def test_only_a_plain_last_word_is_a_prefix(q, params):
    assert matching(q)[1] == params


def test_a_short_query_finds_nothing(api):
    create(api, "document", "P")
    assert search(api, "p") == []


@pytest.mark.parametrize(
    "params, error",
    [
        ({"limit": "0"}, "invalid_limit"),
        ({"limit": "x"}, "invalid_limit"),
        ({"q": "x" * 201}, "query_too_long"),
    ],
)
def test_invalid_parameters_are_refused(api, params, error):
    response = api.get("/api/search", {"q": "ponuda", **params})
    assert (response.status_code, response.json()["error"]) == (400, error)


@pytest.mark.parametrize(
    "q, error",
    [
        ("ponuda vrsta:slika", "invalid_kind"),
        ("ponuda datum:jučer", "invalid_date"),
        ("ponuda datum:2025-02..2025-01", "invalid_date"),
        ("ponuda ima:sliku", "invalid_has"),
        ("ponuda od:", "empty"),
    ],
)
def test_a_filter_it_cannot_read_finds_nothing_and_says_why(api, q, error):
    create(api, "document", "Ponuda")
    found = api.get("/api/search", {"q": q}).json()
    assert (found["documents"], found["mail"]) == ([], [])
    assert [each.get("error") for each in found["filters"]] == [error]


def test_searching_in_a_folder_needs_access_to_it(api):
    ana = person("ana@example.com")
    folder = create(api, "folder", "Ponude")
    assert ana.get("/api/search", {"q": "ponuda", "in": folder}).status_code == 404
    document = create(api, "document", "Ponuda", folder)
    assert api.get("/api/search", {"q": "ponuda", "in": document}).status_code == 400


def test_search_needs_a_session(client):
    assert client.get("/api/search", {"q": "ponuda"}).status_code == 401


def found_in(client, file, q, status=200) -> dict:
    response = client.get(f"/api/nodes/{file}/found", {"q": q})
    assert response.status_code == status, response.json()
    return response.json()


def test_a_file_shows_where_its_text_holds_the_query_with_or_without_accents(api):
    file = upload_file(api, "Ugovor", pdf_bytes("Bez pogotka", "Iz Šibenika u  SIBENIK"))
    hits = found_in(api, file, "šibenik")["hits"]
    assert [hit["page"] for hit in hits] == [2, 2]
    assert found_in(api, file, "SIBENIK")["hits"] == hits
    first, second = (hit["rects"] for hit in hits)
    assert len(first) == len(second) == 1 and first[0][2] < second[0][0]
    assert all(left < right and bottom < top for left, bottom, right, top in first + second)
    assert [hit["page"] for hit in found_in(api, file, "u sibenik")["hits"]] == [2]
    assert found_in(api, file, "  ")["hits"] == []


def test_finding_in_a_file_says_when_it_cannot(api, monkeypatch):
    file = upload_file(api, "Ugovor", pdf_bytes("Ana i Ana i Ana"))
    monkeypatch.setattr("apps.search.views.MOST_HITS", 2)
    assert found_in(api, file, "ana", status=422)["error"] == "too_many_hits"
    assert found_in(api, file, "x" * 201, status=400)["error"] == "query_too_long"
    document = create(api, "document", "Ponuda")
    assert found_in(api, document, "ana", status=400)["error"] == "not_a_file"
    ana = person("ana@example.com")
    assert found_in(ana, file, "ana", status=404)["error"] == "not_found"
