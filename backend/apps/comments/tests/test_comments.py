import pytest

from apps.access.tests.test_access import JSON, create, person, share
from apps.comments import views
from apps.comments.models import Comment, Thread
from apps.documents.models import Node
from apps.search.tests.test_search import pdf_bytes, upload_file

pytestmark = pytest.mark.django_db

END = {"type": {"client": 1, "clock": 0}, "tname": None, "item": {"client": 1, "clock": 4}}
ANCHOR = {"from": {**END, "assoc": 0}, "to": {**END, "assoc": -1}}


@pytest.fixture
def announced(monkeypatch) -> list[tuple[str, str]]:
    rooms = []
    monkeypatch.setattr(views, "announce", lambda room, news: rooms.append((str(room), news)))
    return rooms


def start(client, document, body="Provjeriti rok", **fields):
    tab = Node.objects.get(pk=document).tabs.filter(parent=None).order_by("position").first()
    data = {"tab": str(tab.pk), "anchor": ANCHOR, "quote": "rok od 30 dana", "body": body}
    return client.post(f"/api/nodes/{document}/threads", {**data, **fields}, content_type=JSON)


def threads(client, document) -> list[dict]:
    response = client.get(f"/api/nodes/{document}/threads")
    assert response.status_code == 200, response.json()
    return response.json()["threads"]


def test_a_reader_starts_a_thread_on_a_tab_and_replies(
    api, announced, django_capture_on_commit_callbacks
):
    ana = person("ana@example.com", first_name="Ana", last_name="Kovač")
    document = create(api, "document", "Ugovor")
    share(api, document, "read", id=ana.user.pk)
    with django_capture_on_commit_callbacks(execute=True):
        response = start(ana, document)
    assert response.status_code == 201, response.json()
    thread = response.json()
    assert (thread["quote"], thread["anchor"], thread["resolved_at"]) == (
        "rok od 30 dana",
        ANCHOR,
        None,
    )
    [first] = thread["comments"]
    assert (first["author"]["name"], first["body"]) == ("Ana Kovač", "Provjeriti rok")
    with django_capture_on_commit_callbacks(execute=True):
        reply = api.post(
            f"/api/threads/{thread['id']}/comments", {"body": "  Može 45  "}, content_type=JSON
        )
    assert reply.status_code == 201
    assert [comment["body"] for comment in reply.json()["comments"]] == [
        "Provjeriti rok",
        "Može 45",
    ]
    assert threads(ana, document) == [reply.json()]
    room = str(Node.objects.get(pk=document).room)
    assert announced == [(room, "comments")] * 2


def test_only_who_reads_the_document_sees_or_starts_its_threads(api):
    ana = person("ana@example.com")
    document = create(api, "document", "Ugovor")
    start(api, document)
    assert start(ana, document).status_code == 404
    assert ana.get(f"/api/nodes/{document}/threads").status_code == 404
    api.post("/api/nodes/trash", {"nodes": [document]}, content_type=JSON)
    assert api.get(f"/api/nodes/{document}/threads").status_code == 404


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"tab": None}, "invalid_tab"),
        ({"anchor": {"from": ANCHOR["from"]}}, "invalid_anchor"),
        ({"anchor": {"from": 1, "to": 2}}, "invalid_anchor"),
        ({"anchor": {"from": {"x": "y" * 10_000}, "to": {}}}, "invalid_anchor"),
        ({"quote": "   "}, "invalid_quote"),
        ({"quote": "r" * 501}, "invalid_quote"),
        ({"body": ""}, "invalid_body"),
        ({"body": "x" * 10_001}, "invalid_body"),
    ],
)
def test_a_thread_needs_a_tab_of_the_document_an_anchor_a_quote_and_words(api, fields, error):
    document = create(api, "document", "Ugovor")
    response = start(api, document, **fields)
    assert (response.status_code, response.json()["error"]) == (400, error)
    assert not Thread.objects.exists()


def test_a_tab_of_another_document_is_refused(api):
    document = create(api, "document", "Ugovor")
    other = create(api, "document", "Ponuda")
    tab = Node.objects.get(pk=other).tabs.get()
    assert start(api, document, tab=str(tab.pk)).json()["error"] == "invalid_tab"


def test_an_editor_resolves_and_reopens_a_thread_which_then_takes_no_replies(api, announced):
    ana = person("ana@example.com")
    document = create(api, "document", "Ugovor")
    share(api, document, "read", id=ana.user.pk)
    thread = start(ana, document).json()["id"]
    resolve = {"resolved": True}
    assert ana.patch(f"/api/threads/{thread}", resolve, content_type=JSON).status_code == 403
    resolved = api.patch(f"/api/threads/{thread}", resolve, content_type=JSON).json()
    assert resolved["resolved_at"] and resolved["resolved_by"]["id"] == api.user.pk
    reply = ana.post(f"/api/threads/{thread}/comments", {"body": "Još"}, content_type=JSON)
    assert (reply.status_code, reply.json()["error"]) == (409, "resolved")
    opened = api.patch(f"/api/threads/{thread}", {"resolved": False}, content_type=JSON).json()
    assert (opened["resolved_at"], opened["resolved_by"]) == (None, None)
    assert (
        api.patch(f"/api/threads/{thread}", {"resolved": 1}, content_type=JSON).status_code == 400
    )


def test_only_its_author_edits_or_deletes_a_comment_and_the_last_takes_its_thread(api):
    ana = person("ana@example.com")
    document = create(api, "document", "Ugovor")
    share(api, document, "edit", id=ana.user.pk)
    thread = start(api, document).json()
    first = thread["comments"][0]["id"]
    reply = ana.post(f"/api/threads/{thread['id']}/comments", {"body": "Da"}, content_type=JSON)
    second = reply.json()["comments"][1]["id"]
    edit = {"body": "Provjeriti rok i cijenu"}
    assert ana.patch(f"/api/comments/{first}", edit, content_type=JSON).status_code == 403
    assert ana.delete(f"/api/comments/{first}").status_code == 403
    assert api.patch(f"/api/comments/{first}", edit, content_type=JSON).status_code == 204
    [shown] = threads(api, document)
    assert shown["comments"][0]["body"] == "Provjeriti rok i cijenu"
    assert shown["comments"][0]["edited_at"]
    assert api.delete(f"/api/comments/{first}").status_code == 204
    assert [comment["id"] for comment in threads(api, document)[0]["comments"]] == [second]
    assert ana.delete(f"/api/comments/{second}").status_code == 204
    assert threads(api, document) == []
    assert not Comment.objects.exists()


def test_a_deleted_tab_takes_its_threads(api):
    document = create(api, "document", "Ugovor")
    start(api, document)
    extra = api.post(f"/api/nodes/{document}/tabs", {"title": "Prilog"}, content_type=JSON).json()
    start(api, document, tab=extra["id"])
    assert api.delete(f"/api/tabs/{extra['id']}").status_code == 204
    assert [thread["quote"] for thread in threads(api, document)] == ["rok od 30 dana"]
    assert Thread.objects.count() == 1


PASSAGE = {"page": 2, "rects": [[72, 716.5, 130.25, 731], [72, 700, 98, 714.5]]}
POINT = {"page": 1, "at": [480, 760]}


def start_on(client, file, anchor, quote, body="Provjeriti iznos"):
    data = {"anchor": anchor, "quote": quote, "body": body}
    return client.post(f"/api/nodes/{file}/threads", data, content_type=JSON)


def test_a_reader_comments_on_a_files_text_or_on_a_point_of_its_page(
    api, announced, django_capture_on_commit_callbacks
):
    ana = person("ana@example.com")
    file = upload_file(api, "Najam", pdf_bytes("Uvod", "Cijena najma"))
    share(api, file, "read", id=ana.user.pk)
    with django_capture_on_commit_callbacks(execute=True):
        passage = start_on(ana, file, PASSAGE, "Cijena najma")
        point = start_on(ana, file, POINT, "", body="Potpis?")
    assert (passage.status_code, point.status_code) == (201, 201)
    assert [(each["tab"], each["anchor"], each["quote"]) for each in threads(ana, file)] == [
        (None, PASSAGE, "Cijena najma"),
        (None, POINT, ""),
    ]
    room = str(Node.objects.get(pk=file).room)
    assert announced == [(room, "comments")] * 2
    assert (
        api.patch(
            f"/api/threads/{point.json()['id']}", {"resolved": True}, content_type=JSON
        ).json()["resolved_by"]["email"]
        == api.user.email
    )


@pytest.mark.parametrize(
    ("anchor", "quote", "error"),
    [
        ({**PASSAGE, "page": 0}, "Cijena", "invalid_anchor"),
        ({**PASSAGE, "page": True}, "Cijena", "invalid_anchor"),
        ({"page": 2, "rects": []}, "Cijena", "invalid_anchor"),
        ({"page": 2, "rects": [[130, 700, 72, 714]]}, "Cijena", "invalid_anchor"),
        ({"page": 2, "rects": [[72, 700, 98]]}, "Cijena", "invalid_anchor"),
        ({"page": 1, "at": [480, "760"]}, "", "invalid_anchor"),
        ({**POINT, "rects": PASSAGE["rects"]}, "", "invalid_anchor"),
        (ANCHOR, "Cijena", "invalid_anchor"),
        (PASSAGE, "  ", "invalid_quote"),
        (POINT, "Cijena", "invalid_quote"),
    ],
)
def test_a_files_thread_needs_its_page_and_the_text_or_point_there(api, anchor, quote, error):
    file = upload_file(api, "Najam", pdf_bytes("Uvod", "Cijena najma"))
    response = start_on(api, file, anchor, quote)
    assert (response.status_code, response.json()["error"]) == (400, error)
    assert not Thread.objects.exists()


def test_a_files_thread_has_no_tab_and_a_folder_has_no_threads(api):
    file = upload_file(api, "Najam", pdf_bytes("Uvod"))
    document = create(api, "document", "Ugovor")
    tab = Node.objects.get(pk=document).tabs.get()
    data = {"tab": str(tab.pk), "anchor": POINT, "quote": "", "body": "Potpis?"}
    response = api.post(f"/api/nodes/{file}/threads", data, content_type=JSON)
    assert response.json()["error"] == "invalid_tab"
    folder = create(api, "folder", "Ugovori")
    assert start_on(api, folder, POINT, "").json()["error"] == "not_a_document"
