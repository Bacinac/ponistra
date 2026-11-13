from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from django.test import Client
from django.utils import timezone
from pycrdt import Doc, Map

from apps.blobs import store
from apps.blobs.models import Blob
from apps.collab.models import Update
from apps.content import styles
from apps.documents.models import Node, Tab
from apps.users.models import User

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def create(api, kind, title, parent=None, **fields):
    fields |= {"kind": kind, "title": title, "parent": parent}
    response = api.post("/api/nodes", fields, content_type="application/json")
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def add_tab(api, document, **fields):
    return api.post(f"/api/nodes/{document}/tabs", fields, content_type="application/json")


def tabs(api, document):
    return api.get(f"/api/nodes/{document}").json()["tabs"]


def patch(api, node, **fields):
    return api.patch(f"/api/nodes/{node}", fields, content_type="application/json")


def move(api, parent, *nodes):
    body = {"nodes": list(nodes), "parent": parent}
    return api.post("/api/nodes/move", body, content_type="application/json")


def to_trash(api, *nodes):
    return api.post("/api/nodes/trash", {"nodes": list(nodes)}, content_type="application/json")


def from_trash(api, way, *nodes):
    return api.post(f"/api/trash/{way}", {"nodes": list(nodes)}, content_type="application/json")


def titles(api, parent=None):
    query = f"?parent={parent}" if parent else ""
    return [child["title"] for child in api.get(f"/api/nodes{query}").json()["children"]]


def test_the_tree_needs_a_session(client):
    assert client.get("/api/nodes").status_code == 401
    assert client.get("/api/nodes").json() == {"error": "not_signed_in"}


def test_folders_come_first_in_croatian_order(api):
    for title in ["Dom", "Cesta", "Čvor"]:
        create(api, "document", title)
    create(api, "folder", "Žetva")
    assert titles(api) == ["Žetva", "Cesta", "Čvor", "Dom"]


def test_a_folder_lists_its_children_and_its_path(api):
    outer = create(api, "folder", "Ured")
    inner = create(api, "folder", "Ugovori", outer)
    create(api, "document", "Troškovi", inner)
    listing = api.get(f"/api/nodes?parent={inner}").json()
    assert [node["title"] for node in listing["path"]] == ["Ured", "Ugovori"]
    assert [node["title"] for node in listing["children"]] == ["Troškovi"]


@pytest.mark.parametrize(
    "fields, error",
    [
        ({"kind": "text", "title": "Bilješka"}, "invalid_kind"),
        ({"kind": "file", "title": "Ponuda"}, "unknown_file"),
        ({"kind": "folder", "title": "Ured", "blob": "0" * 64}, "unexpected_file"),
        ({"kind": "folder", "title": "  "}, "invalid_title"),
        ({"kind": "folder", "title": "x" * 201}, "invalid_title"),
        ({"kind": "folder", "title": "Ured", "parent": "nije-id"}, "invalid_id"),
    ],
)
def test_invalid_creations_are_refused(api, fields, error):
    response = api.post("/api/nodes", fields, content_type="application/json")
    assert response.status_code == 400
    assert response.json() == {"error": error}


def test_a_document_cannot_hold_children(api):
    document = create(api, "document", "Bilješka")
    response = api.post(
        "/api/nodes",
        {"kind": "document", "title": "Unutra", "parent": document},
        content_type="application/json",
    )
    assert response.json() == {"error": "not_a_folder"}


def test_a_new_document_has_one_untitled_tab(api):
    document = create(api, "document", "Troškovi")
    assert [(tab["parent"], tab["title"]) for tab in tabs(api, document)] == [(None, "")]
    assert tabs(api, create(api, "folder", "Ured")) == []


def test_a_new_document_starts_from_the_template_in_a_room_of_its_own(api):
    document = create(api, "document", "Troškovi")
    placed = api.get(f"/api/nodes/{document}").json()
    assert placed["room"] not in {tab["room"] for tab in placed["tabs"]}
    doc = Doc()
    doc.apply_update(api.get(f"/api/nodes/{document}/state").content)
    assert doc.get(styles.THEME, type=Map).to_py() == styles.TEMPLATE[styles.THEME]
    assert doc.get(styles.STYLES, type=Map).to_py() == styles.TEMPLATE[styles.STYLES]

    folder = api.get(f"/api/nodes/{create(api, 'folder', 'Ured')}/state")
    assert (folder.status_code, folder.json()["error"]) == (400, "not_a_document")
    stranger = Client()
    stranger.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert stranger.get(f"/api/nodes/{document}/state").status_code == 404


def test_tabs_nest(api):
    document = create(api, "document", "Ponuda")
    first = tabs(api, document)[0]["id"]
    prices = add_tab(api, document, title="Cijene").json()
    child = add_tab(api, document, parent=prices["id"]).json()
    listed = tabs(api, document)
    assert [(tab["title"], tab["parent"], tab["position"]) for tab in listed] == [
        ("", None, 0),
        ("Cijene", None, 1),
        ("", prices["id"], 0),
    ]
    assert listed[0]["id"] == first and child["parent"] == prices["id"]


def test_a_tab_belongs_to_a_live_document_and_its_parent_to_the_same_one(api):
    document = create(api, "document", "Ponuda")
    other = create(api, "document", "Drugi")
    foreign = tabs(api, other)[0]["id"]
    assert add_tab(api, document, parent=foreign).json() == {"error": "invalid_parent"}
    assert add_tab(api, create(api, "folder", "Ured")).json() == {"error": "not_a_document"}
    to_trash(api, document)
    assert add_tab(api, document).status_code == 404


def test_rename_a_tab(api):
    document = create(api, "document", "Ponuda")
    tab = tabs(api, document)[0]["id"]
    rename = api.patch(f"/api/tabs/{tab}", {"title": " Uvod "}, content_type="application/json")
    assert rename.json()["title"] == "Uvod"
    clear = api.patch(f"/api/tabs/{tab}", {"title": ""}, content_type="application/json")
    assert clear.json()["title"] == ""


def place_tab(api, tab, parent, position):
    body = {"parent": parent, "position": position}
    return api.patch(f"/api/tabs/{tab}", body, content_type="application/json")


def outline(api, document):
    return [(tab["title"], tab["parent"], tab["position"]) for tab in tabs(api, document)]


def test_a_tab_moves_along_its_row_and_into_another(api):
    document = create(api, "document", "Ponuda")
    first = tabs(api, document)[0]["id"]
    api.patch(f"/api/tabs/{first}", {"title": "Uvod"}, content_type="application/json")
    prices = add_tab(api, document, title="Cijene").json()["id"]
    terms = add_tab(api, document, title="Uvjeti").json()["id"]
    detail = add_tab(api, document, title="Stavke", parent=prices).json()["id"]

    moved = place_tab(api, terms, None, 0).json()
    assert (moved["parent"], moved["position"], moved["title"]) == (None, 0, "Uvjeti")
    assert outline(api, document) == [
        ("Uvjeti", None, 0),
        ("Uvod", None, 1),
        ("Cijene", None, 2),
        ("Stavke", prices, 0),
    ]
    place_tab(api, detail, None, 1)
    place_tab(api, first, prices, 0)
    assert outline(api, document) == [
        ("Uvjeti", None, 0),
        ("Stavke", None, 1),
        ("Cijene", None, 2),
        ("Uvod", prices, 0),
    ]
    assert place_tab(api, terms, None, 99).json()["position"] == 2


def test_a_tab_never_moves_below_itself_or_out_of_its_document(api):
    document = create(api, "document", "Ponuda")
    prices = add_tab(api, document, title="Cijene").json()["id"]
    detail = add_tab(api, document, title="Stavke", parent=prices).json()["id"]
    foreign = tabs(api, create(api, "document", "Drugi"))[0]["id"]
    before = outline(api, document)
    assert place_tab(api, prices, detail, 0).json() == {"error": "tab_cycle"}
    assert place_tab(api, prices, prices, 0).json() == {"error": "tab_cycle"}
    assert place_tab(api, prices, foreign, 0).json() == {"error": "invalid_parent"}
    for position in (-1, "1", True, None):
        assert place_tab(api, prices, None, position).json() == {"error": "invalid_position"}
    assert outline(api, document) == before


def test_every_change_to_the_tabs_is_announced_in_the_documents_own_room(
    api, monkeypatch, django_capture_on_commit_callbacks
):
    announced = []
    monkeypatch.setattr(
        "apps.documents.tabs.announce", lambda room, news: announced.append((room, news))
    )
    document = create(api, "document", "Ponuda")
    first = tabs(api, document)[0]["id"]
    with django_capture_on_commit_callbacks(execute=True):
        second = add_tab(api, document).json()["id"]
        api.patch(f"/api/tabs/{second}", {"title": "Prilog"}, content_type="application/json")
        place_tab(api, second, None, 0)
        api.delete(f"/api/tabs/{first}")
    room = Node.objects.get(pk=document).room
    assert announced == [(room, "tabs")] * 4


def test_deleting_a_tab_takes_its_subtabs_but_never_the_last_tab(api):
    document = create(api, "document", "Ponuda")
    first = tabs(api, document)[0]["id"]
    assert api.delete(f"/api/tabs/{first}").json() == {"error": "last_tab"}
    second = add_tab(api, document).json()["id"]
    add_tab(api, document, parent=second)
    assert api.delete(f"/api/tabs/{second}").status_code == 204
    assert [tab["id"] for tab in tabs(api, document)] == [first]
    assert Tab.objects.count() == 1


def test_a_tab_hands_its_whole_state_to_whoever_may_read_it(api):
    document = create(api, "document", "Ponuda")
    tab = Tab.objects.get(pk=tabs(api, document)[0]["id"])
    doc = Doc()
    doc["notes"] = Map({"intro": "Uvod"})
    Update.objects.create(document=tab.document, tab=tab, room=tab.room, data=doc.get_update())
    read = Doc()
    read.apply_update(api.get(f"/api/tabs/{tab.pk}/state").content)
    assert read.get("notes", type=Map).to_py() == {"intro": "Uvod"}
    stranger = Client()
    stranger.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert stranger.get(f"/api/tabs/{tab.pk}/state").status_code == 404


def test_rename(api):
    document = create(api, "document", "Nacrt")
    renamed = patch(api, document, title=" Konačno ").json()
    assert renamed["node"]["title"] == "Konačno"
    ivo = "ivo@example.com"
    assert renamed["node"]["updated_by"] == {"id": api.user.pk, "email": ivo, "name": ivo}
    assert patch(api, document, title="").json() == {"error": "invalid_title"}


def test_a_document_reads_its_tables_in_its_own_locale(api):
    document = create(api, "document", "Ponuda")
    assert patch(api, document).json()["node"]["locale"] == "hr"
    assert patch(api, document, locale="en-GB").json()["node"]["locale"] == "en-GB"
    assert patch(api, document, locale="hr-HR").json() == {"error": "invalid_locale"}
    folder = create(api, "folder", "Arhiva")
    assert patch(api, folder, locale="en").json() == {"error": "invalid_locale"}


def test_move_several_at_once(api):
    folder = create(api, "folder", "Arhiva")
    first = create(api, "document", "Nacrt")
    second = create(api, "folder", "Stari")
    assert move(api, folder, first, second).status_code == 200
    assert titles(api) == ["Arhiva"]
    assert titles(api, folder) == ["Stari", "Nacrt"]
    move(api, None, first)
    assert titles(api) == ["Arhiva", "Nacrt"]


def test_a_folder_cannot_move_into_itself_or_below_and_nothing_moves_then(api):
    outer = create(api, "folder", "Ured")
    inner = create(api, "folder", "Ugovori", outer)
    loose = create(api, "document", "Dopis")
    assert move(api, outer, outer).json() == {"error": "cycle"}
    assert move(api, inner, loose, outer).json() == {"error": "cycle"}
    assert titles(api) == ["Ured", "Dopis"]


def test_bulk_requests_name_live_nodes(api):
    document = create(api, "document", "Dopis")
    assert to_trash(api).json() == {"error": "invalid_nodes"}
    assert move(api, None, {"id": document}).json() == {"error": "invalid_nodes"}
    to_trash(api, document)
    assert to_trash(api, document).status_code == 404


def test_trash_hides_a_folder_with_everything_below_it(api):
    folder = create(api, "folder", "Stari")
    document = create(api, "document", "Zapisnik", folder)
    assert to_trash(api, folder).status_code == 204
    assert titles(api) == []
    assert api.get(f"/api/nodes/{document}").status_code == 404
    assert api.get(f"/api/nodes?parent={folder}").status_code == 404
    assert [item["title"] for item in api.get("/api/trash").json()["items"]] == ["Stari"]


def test_restore_brings_a_node_back_where_it_was(api):
    folder = create(api, "folder", "Ured")
    document = create(api, "document", "Zapisnik", folder)
    to_trash(api, document)
    assert from_trash(api, "restore", document).status_code == 204
    assert Node.objects.get(pk=document).parent_id == UUID(folder)
    assert titles(api, folder) == ["Zapisnik"]


def test_restore_under_a_trashed_folder_lands_at_the_top(api):
    folder = create(api, "folder", "Ured")
    document = create(api, "document", "Zapisnik", folder)
    to_trash(api, document)
    to_trash(api, folder)
    assert from_trash(api, "restore", document).status_code == 204
    assert Node.objects.get(pk=document).parent is None
    assert titles(api) == ["Zapisnik"]


def test_purge_deletes_only_what_is_in_the_trash(api):
    live = create(api, "document", "Živ")
    gone = create(api, "folder", "Otpad")
    create(api, "document", "Unutra", gone)
    assert from_trash(api, "purge", live).status_code == 404
    to_trash(api, gone)
    assert from_trash(api, "purge", gone).status_code == 204
    assert list(Node.objects.values_list("title", flat=True)) == ["Živ"]
    assert Tab.objects.get().document_id == UUID(live)


def test_an_uploaded_pdf_is_a_file_in_the_tree(api, upload):
    sha256 = upload(PDF)["sha256"]
    file = create(api, "file", "Ponuda", blob=sha256)
    assert titles(api) == ["Ponuda"]
    assert api.get(f"/api/nodes/{file}").json()["tabs"] == []
    response = api.get(f"/api/nodes/{file}/file")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Length"] == str(len(PDF))
    assert response["Content-Disposition"] == 'inline; filename="Ponuda.pdf"'
    download = api.get(f"/api/nodes/{file}/file?download=1")
    assert download["Content-Disposition"].startswith("attachment")


def test_a_file_brought_beside_another_lands_in_its_folder_or_among_ones_own(api, upload):
    folder = create(api, "folder", "Arhiva")
    sha256 = upload(PDF)["sha256"]
    file = create(api, "file", "Ugovor", folder, blob=sha256)
    brought = create(api, "file", "Prilog", blob=sha256, beside=file)
    assert Node.objects.get(pk=brought).parent_id == UUID(folder)
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    grantee = {"kind": "user", "id": ana.pk}
    granted = api.post(
        f"/api/nodes/{folder}/grants",
        {"grantee": grantee, "role": "read"},
        content_type="application/json",
    )
    assert granted.status_code == 201
    reader = Client()
    reader.force_login(ana)
    fields = {"kind": "file", "title": "Moje", "blob": sha256, "beside": file}
    made = reader.post("/api/nodes", fields, content_type="application/json").json()
    assert made["parent"] is None


@pytest.mark.parametrize(
    ("data", "media_type", "name"),
    [(PNG, "image/png", "Plan kata.png"), (SVG, "image/svg+xml", "Plan kata.svg")],
)
def test_an_uploaded_image_is_a_file_served_as_a_sandboxed_picture(
    api, upload, data, media_type, name
):
    file = create(api, "file", "Plan kata", blob=upload(data)["sha256"])
    placement = api.get(f"/api/nodes/{file}").json()
    assert placement["node"]["media_type"] == media_type
    assert placement["pdf"] is None
    response = api.get(f"/api/nodes/{file}/file")
    assert response["Content-Type"] == media_type
    assert response["Content-Security-Policy"] == "sandbox"
    assert response["Content-Disposition"] == f'inline; filename="{name}"'
    download = api.get(f"/api/nodes/{file}/file?download=1")
    assert download["Content-Disposition"] == f'attachment; filename="{name}"'


def test_what_only_a_pdf_has_is_refused_for_an_image(api, upload):
    file = create(api, "file", "Plan kata", blob=upload(PNG)["sha256"])
    for path in ["noted", "original"]:
        assert api.get(f"/api/nodes/{file}/{path}").json() == {"error": "not_a_pdf"}
    assert api.post(f"/api/nodes/{file}/ocr").json() == {"error": "not_a_pdf"}
    document = create(api, "document", "Bilješka")
    assert api.get(f"/api/nodes/{document}/original").json() == {"error": "not_a_file"}


@pytest.mark.parametrize(
    ("data", "extension", "media_type", "served", "name"),
    [
        (b"#!/bin/sh\necho", "sh", "text/plain", "text/plain", "Ponuda.sh"),
        (b"\x00\x01", "", "application/octet-stream", "application/octet-stream", "Ponuda"),
        (b"{\\rtf1 Ponuda}", "", "application/rtf", "application/rtf", "Ponuda.rtf"),
    ],
)
def test_any_other_file_is_kept_by_its_extension_and_only_ever_saved(
    api, upload, data, extension, media_type, served, name
):
    sha256 = upload(data)["sha256"]
    file = create(api, "file", "Ponuda", blob=sha256, extension=extension)
    node = api.get(f"/api/nodes/{file}").json()["node"]
    assert (node["media_type"], node["extension"]) == (media_type, name.partition(".")[2] or None)
    response = api.get(f"/api/nodes/{file}/file")
    assert response["Content-Type"] == served
    assert response["Content-Security-Policy"] == "sandbox"
    assert response["Content-Disposition"] == f'attachment; filename="{name}"'


def test_a_text_file_is_shown_as_its_text_in_the_code_page_it_is_in(api, upload):
    shown = "Šifra artikla;Naziv;Količina\nŽ-104;Žičana mreža, pocinčana;12\nČ-17;Čelična šipka;4\n"
    data = shown.replace("\n", "\r\n").encode("cp1250")
    file = create(api, "file", "Popis", blob=upload(data)["sha256"], extension="csv")
    response = api.get(f"/api/nodes/{file}/text").json()
    assert response == {"text": shown, "encoding": "Windows-1250", "truncated": False}
    pdf = create(api, "file", "Ponuda", blob=upload(PDF)["sha256"])
    assert api.get(f"/api/nodes/{pdf}/text").status_code == 404


def test_a_glance_reads_the_start_of_a_text_file_to_a_whole_line(api, upload):
    data = "".join(f"Redak {n}\n" for n in range(100)).encode()
    file = create(api, "file", "Dnevnik", blob=upload(data)["sha256"], extension="log")
    response = api.get(f"/api/nodes/{file}/text?most=30").json()
    assert (response["text"], response["truncated"]) == ("Redak 0\nRedak 1\nRedak 2\n", True)
    for most in ("0", "x", str(6 * 1024 * 1024)):
        assert api.get(f"/api/nodes/{file}/text?most={most}").json() == {"error": "invalid_most"}


def test_a_file_keeps_the_extension_it_came_with_over_its_bytes_kind(api, upload):
    file = create(api, "file", "Logo", blob=upload(PDF)["sha256"], extension="ai")
    node = api.get(f"/api/nodes/{file}").json()["node"]
    assert (node["media_type"], node["extension"]) == ("application/pdf", "ai")
    response = api.get(f"/api/nodes/{file}/noted?download=1")
    assert response["Content-Disposition"] == 'attachment; filename="Logo.ai"'


def test_an_extension_is_a_few_lowercase_letters_or_digits(api, upload):
    fields = {"kind": "file", "title": "Ponuda", "blob": upload(PDF)["sha256"]}
    for extension in ["PDF", ".pdf", "tar.gz", "a" * 11, 7]:
        response = api.post(
            "/api/nodes", fields | {"extension": extension}, content_type="application/json"
        )
        assert response.json() == {"error": "invalid_extension"}


def test_a_file_was_last_changed_when_its_disk_says_never_after_now(api, upload):
    fields = {"kind": "file", "title": "Ponuda", "blob": upload(PDF)["sha256"]}
    file = create(api, "file", "Ponuda", blob=fields["blob"], modified="2024-05-03T12:11:12+02:00")
    node = Node.objects.get(pk=file)
    assert node.updated_at == datetime(2024, 5, 3, 10, 11, 12, tzinfo=UTC)
    assert node.created_at > node.updated_at
    ahead = create(
        api,
        "file",
        "Ponuda",
        blob=fields["blob"],
        modified=f"{timezone.now().year + 1}-01-01T00:00:00Z",
    )
    assert Node.objects.get(pk=ahead).updated_at <= timezone.now()
    for modified in ["2024-05-03T10:11:12", "jučer", 1714730000000]:
        response = api.post(
            "/api/nodes", fields | {"modified": modified}, content_type="application/json"
        )
        assert response.json() == {"error": "invalid_modified"}


def test_a_file_needs_an_uploaded_blob(api):
    fields = {"kind": "file", "title": "Ponuda"}
    for blob in ["0" * 64, 7]:
        response = api.post("/api/nodes", fields | {"blob": blob}, content_type="application/json")
        assert response.json() == {"error": "unknown_file"}
    assert not Node.objects.exists()


def test_a_file_has_no_tabs_and_only_a_file_has_bytes(api, upload):
    file = create(api, "file", "Ponuda", blob=upload(PDF)["sha256"])
    assert add_tab(api, file).json() == {"error": "not_a_document"}
    document = create(api, "document", "Bilješka")
    assert api.get(f"/api/nodes/{document}/file").status_code == 404


def test_the_bytes_of_a_trashed_file_are_out_of_reach(api, upload):
    file = create(api, "file", "Ponuda", blob=upload(PDF)["sha256"])
    to_trash(api, file)
    assert api.get(f"/api/nodes/{file}/file").status_code == 404


def test_purge_wakes_the_collector_for_the_bytes_nothing_refers_to(api, upload, monkeypatch):
    woken = []
    monkeypatch.setattr(store, "notify", woken.append)
    sha256 = upload(PDF)["sha256"]
    first = create(api, "file", "Ponuda", blob=sha256)
    folder = create(api, "folder", "Arhiva")
    create(api, "file", "Kopija", folder, blob=sha256)
    Blob.objects.update(uploaded_at=timezone.now() - timedelta(days=1))
    for node in [first, folder]:
        to_trash(api, node)
        from_trash(api, "purge", node)
        assert woken.pop() == store.CHANNEL and store.path_of(sha256).exists()
        store.collect()
        assert store.path_of(sha256).exists() == (node == first)
    assert not Blob.objects.exists()
