import pytest
from django.test import Client
from django.utils import timezone

from apps.access.models import Grant, Role
from apps.blobs import store, text
from apps.blobs.tests.test_blobs import content
from apps.core.api import Refused
from apps.documents import boards
from apps.documents.models import Node
from apps.users.models import User
from apps.versions.models import FileVersion

from .test_views import create

pytestmark = pytest.mark.django_db

PAGE = (
    "<!doctype html><html><head><title>Prodaja</title><style>b{color:red}</style></head><body>"
    "<h1>Prodaja po mjesecu</h1><p>Siječanj <b>12</b></p><script>document.title='x'</script>"
    "</body></html>"
)
LATER = PAGE.replace("Siječanj", "Veljača")


def board(api, upload, page: str = PAGE, extension: str = "html") -> str:
    sha256 = upload(page.encode())["sha256"]
    return create(api, "file", "Prodaja", blob=sha256, extension=extension)


@pytest.mark.parametrize(
    "head",
    [
        b"<!DOCTYPE html>\n<html>",
        b"\xef\xbb\xbf  <html lang='hr'>",
        b"<!-- made by Claude -->\n<!doctype HTML><svg></svg>",
    ],
)
def test_a_page_of_html_is_told_by_its_beginning(head):
    assert store.sniff(head + b"<body>Prodaja</body></html>") == store.HTML


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        (b"<div>Prodaja</div>", store.TEXT),
        (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "image/svg+xml"),
        (b"<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<TITLE>Bookmarks</TITLE>", store.BOOKMARKS),
    ],
)
def test_a_fragment_a_picture_and_bookmarks_are_not_pages(head, kind):
    assert store.sniff(head) == kind


def test_the_text_of_a_page_is_what_it_shows():
    assert text.seen(PAGE) == "Prodaja po mjesecu\nSiječanj 12"


def test_a_board_opens_in_a_frame_that_holds_nothing_but_its_page(api, upload):
    node = board(api, upload)
    assert Node.objects.get(pk=node).blob.media_type == store.HTML
    shown = api.get(f"/api/nodes/{node}/board")
    assert shown.status_code == 200
    assert shown["Content-Type"] == "text/html; charset=utf-8"
    page = f"/api/nodes/{node}/board/page"
    assert f"frame-src testserver{page};" in shown["Content-Security-Policy"]
    held = shown.content.decode()
    assert f"script-src 'sha256-{boards.BRIDGE_HASH}'" in shown["Content-Security-Policy"]
    assert f"<script>{boards.BRIDGE}</script>" in held
    assert held.count("<script") == 1
    assert f'<iframe src="{page}" sandbox="allow-scripts"' in held
    assert shown["Referrer-Policy"] == "no-referrer"


def test_a_boards_page_is_sandboxed_whoever_opens_it(api, upload):
    node = board(api, upload)
    shown = api.get(f"/api/nodes/{node}/board/page")
    assert shown.status_code == 200
    assert content(shown) == PAGE.encode()
    assert shown["Content-Type"] == f"{store.HTML}; charset=UTF-8"
    assert shown["Content-Disposition"].startswith("inline")
    policy = dict(rule.split(" ", 1) for rule in shown["Content-Security-Policy"].split("; "))
    assert policy["sandbox"] == "allow-scripts"
    assert policy["default-src"] == "'none'"
    assert policy["connect-src"] == boards.LIBRARIES
    assert policy["form-action"] == "'none'"
    assert policy["frame-ancestors"] == "'self'"
    assert shown["X-DNS-Prefetch-Control"] == "off"
    saved = api.get(f"/api/nodes/{node}/file")
    assert saved["Content-Disposition"].startswith("attachment")


def test_html_under_another_name_is_the_text_it_was_saved_as(api, upload):
    node = board(api, upload, extension="json")
    assert api.get(f"/api/nodes/{node}/board").status_code == 404
    assert api.get(f"/api/nodes/{node}/board/page").status_code == 404
    assert "Prodaja po mjesecu" in api.get(f"/api/nodes/{node}/text").json()["text"]


def test_nobody_without_the_file_opens_its_board(api, upload):
    node = board(api, upload)
    stranger = Client()
    stranger.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert stranger.get(f"/api/nodes/{node}/board").status_code == 404
    assert stranger.get(f"/api/nodes/{node}/board/page").status_code == 404


def filed(api, node: str, group: str):
    return api.post(
        "/api/nodes/boards", {"node": node, "group": group}, content_type="application/json"
    )


def test_the_page_of_boards_holds_those_filed_by_group_and_no_other_page_of_html(api, upload):
    baba = board(api, upload)
    dida = board(api, upload)
    trashed = board(api, upload, page=PAGE.replace("Prodaja", "Stara"))
    assert filed(api, baba, "Baba").status_code == 200
    assert filed(api, dida, "baba").status_code == 200
    assert filed(api, trashed, "Baba").status_code == 200
    Node.objects.filter(pk=trashed).update(trashed_at=timezone.now())
    folder = create(api, "folder", "Izvještaji")
    create(
        api,
        "file",
        "Kvartal",
        parent=folder,
        blob=upload(LATER.encode())["sha256"],
        extension="html",
    )
    board(api, upload, extension="json")

    listed = api.get("/api/nodes/boards").json()["children"]

    assert {node["id"] for node in listed} == {baba, dida}
    assert {node["role"] for node in listed} == {"own"}
    assert {node["kept"] for node in listed} == {False}
    assert {node["root"] for node in listed} == {"mine"}
    assert {tuple(step["title"] for step in node["path"]) for node in listed} == {
        ("Boards", "Baba")
    }
    assert [step["boards"] for step in listed[0]["path"]] == [True, False]
    assert Node.objects.filter(boards=True).count() == 1
    assert {node["title"] for node in api.get("/api/nodes").json()["children"]} >= {"Boards"}


def test_a_board_filed_again_moves_to_the_group_named_and_out_of_its_folder(api, upload):
    folder = create(api, "folder", "Izvještaji")
    node = create(
        api, "file", "Plan", parent=folder, blob=upload(PAGE.encode())["sha256"], extension="html"
    )
    assert filed(api, node, "Baba").json()["parent"] != folder
    assert filed(api, node, "Dida").status_code == 200

    [listed] = api.get("/api/nodes/boards").json()["children"]

    assert [step["title"] for step in listed["path"]] == ["Boards", "Dida"]
    assert api.get(f"/api/nodes?parent={folder}").json()["children"] == []


def test_the_page_of_boards_holds_what_others_share_from_theirs_and_says_what_stays_in(api, upload):
    node = board(api, upload)
    filed(api, node, "Baba")
    mine = board(api, upload)
    filed(api, mine, "Dida")
    plain = board(api, upload)
    group = Node.objects.get(pk=node).parent
    Node.objects.filter(pk=group.pk).update(confined=True)
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    for shared in (group.pk, plain):
        Grant.objects.create(node_id=shared, user=ana, role=Role.READ, created_by=ana)
    colleague = Client()
    colleague.force_login(ana)

    listed = colleague.get("/api/nodes/boards").json()["children"]

    assert [(each["id"], each["role"], each["kept"], each["root"]) for each in listed] == [
        (node, "read", True, "shared")
    ]
    shared = colleague.get("/api/nodes/shared").json()["children"]
    assert [each["id"] for each in shared] == [plain]


def test_the_folder_of_boards_stays_at_the_top_and_takes_only_boards(api, upload):
    node = board(api, upload)
    filed(api, node, "Baba")
    group = Node.objects.get(pk=node).parent
    elsewhere = create(api, "folder", "Izvještaji")
    document = create(api, "document", "Ponuda")

    def moved(moving: str, parent: str):
        return api.post(
            "/api/nodes/move",
            {"nodes": [moving], "parent": parent},
            content_type="application/json",
        )

    assert moved(str(group.parent_id), elsewhere).json()["error"] == "boards_at_top"
    assert moved(document, str(group.pk)).json()["error"] == "not_a_board"
    assert filed(api, document, "Baba").json()["error"] == "not_a_board"
    assert filed(api, node, "").json()["error"] == "invalid_title"


def test_a_rewritten_board_keeps_each_page_and_takes_one_back(api, upload):
    node = Node.objects.get(pk=board(api, upload))
    assert api.get(f"/api/nodes/{node.pk}/versions").json() == {"versions": []}
    boards.rewritten(node, LATER, api.user, "Claude", "Prodaja 2026")
    boards.rewritten(node, LATER, api.user, "Claude")
    listed = api.get(f"/api/nodes/{node.pk}/versions").json()["versions"]
    assert [(each["number"], each["agent"]) for each in listed] == [(2, "Claude"), (1, "")]
    assert listed[1]["editors"][0]["email"] == "ivo@example.com"
    node.refresh_from_db()
    assert node.title == "Prodaja 2026"
    first = listed[1]["id"]
    earlier = api.get(f"/api/nodes/{node.pk}/board/page?version={first}")
    assert content(earlier) == PAGE.encode()
    assert (
        f"?version={first}"
        in api.get(f"/api/nodes/{node.pk}/board?version={first}").content.decode()
    )

    restored = api.post(f"/api/file-versions/{first}/restore")
    assert (restored.json()["number"], restored.json()["restored_from"]) == (3, 1)
    now = api.get(f"/api/nodes/{node.pk}/board/page")
    assert content(now) == PAGE.encode()
    assert FileVersion.objects.filter(node=node).count() == 3


def test_a_version_of_another_board_or_none_at_all_is_not_found(api, upload):
    node = Node.objects.get(pk=board(api, upload))
    other = Node.objects.get(pk=board(api, upload, LATER))
    boards.rewritten(other, PAGE, api.user, "Claude")
    theirs = other.file_versions.first().pk
    assert api.get(f"/api/nodes/{node.pk}/board/page?version={theirs}").status_code == 404
    assert api.get(f"/api/nodes/{node.pk}/board/page?version=7").status_code == 400


def test_only_a_whole_page_is_written_as_a_board(api, upload):
    node = Node.objects.get(pk=board(api, upload))
    with pytest.raises(Refused) as refused:
        boards.page("<div>Prodaja</div>")
    assert refused.value.error == "not_a_page"
    with pytest.raises(Refused) as refused:
        boards.page("<!doctype html>" + "x" * boards.MOST)
    assert refused.value.error == "board_too_large"
    document = Node.objects.get(pk=create(api, "document", "Ponuda"))
    with pytest.raises(Refused) as refused:
        boards.rewritten(document, PAGE, api.user, "Claude")
    assert refused.value.error == "not_a_board"
    assert not node.file_versions.exists()


def test_the_workspace_owner_chooses_the_folder_a_boards_agent_starts_in(api, upload, settings):
    node = board(api, upload)
    before = Node.objects.get(pk=node).updated_at
    chosen = {"agent_folder": "/mnt/docker/ponistra"}
    assert api.patch(f"/api/nodes/{node}", chosen, "application/json").status_code == 403
    settings.WORKSPACE = api.user.email
    answer = api.patch(f"/api/nodes/{node}", chosen, "application/json")
    assert answer.status_code == 200
    assert answer.json()["node"]["agent_folder"] == "/mnt/docker/ponistra"
    assert Node.objects.get(pk=node).updated_at == before
    for wrong in ("ponistra", "/mnt\n/docker", 7, "/" + "x" * 500):
        refused = api.patch(f"/api/nodes/{node}", {"agent_folder": wrong}, "application/json")
        assert refused.json()["error"] == "invalid_agent_folder"
    folder = create(api, "folder", "Mapa")
    refused = api.patch(f"/api/nodes/{folder}", chosen, "application/json")
    assert refused.json()["error"] == "not_a_board"
