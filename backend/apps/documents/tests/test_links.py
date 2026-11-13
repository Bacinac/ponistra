import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from django.utils import timezone
from PIL import Image

from apps.access.tests.test_access import create, person, share
from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.core import fetch
from apps.documents import links, printing
from apps.documents.models import Node
from apps.search.tests.test_search import search

pytestmark = pytest.mark.django_db

JSON = "application/json"


def png(side: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (side, side), (200, 30, 30, 255)).save(out, "PNG")
    return out.getvalue()


PAGE = (
    '<!doctype html><html><head><meta charset="windows-1250">'
    "<title>  Gradska   knjižnica </title>"
    '<meta name="description" content="Katalog i   radno vrijeme">'
    '<link rel="apple-touch-icon" href="/dodir.png">'
    '<link rel="icon" sizes="32x32" href="/ikona.png">'
    "</head><body><svg><title>Crtež</title></svg></body></html>"
).encode("cp1250")
SITE = {
    "/": (PAGE, "text/html"),
    "/ikona.png": (png(128), "image/png"),
    "/prazno": (b"<html><head></head></html>", "text/html; charset=utf-8"),
    "/crtez": (
        b'<html><head><link rel="icon" sizes="16x16" href="/ikona.png">'
        b'<link rel="icon" type="image/svg+xml" href="./ikona.svg"></head></html>',
        "text/html",
    ),
    "/ikona.svg": (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml"),
}


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        body, kind = SITE.get(self.path, (b"", ""))
        self.send_response(200 if kind else 404)
        if kind:
            self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def site(monkeypatch):
    """A web host named stranica.example that is only pretended public."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    vetted = fetch.public_address
    monkeypatch.setattr(
        fetch,
        "public_address",
        lambda name, port: "127.0.0.1" if name.endswith("stranica.example") else vetted(name, port),
    )
    yield f"http://stranica.example:{server.server_port}"
    server.shutdown()
    server.server_close()


def made(api, **fields) -> dict:
    response = api.post("/api/nodes", {"kind": "link", **fields}, content_type=JSON)
    assert response.status_code == 201, response.json()
    return response.json()


def test_a_link_is_named_by_its_site_until_its_page_is_read(api):
    link = made(api, href="www.example.com/katalog")
    assert (link["kind"], link["title"], link["href"]) == (
        "link",
        "example.com",
        "https://www.example.com/katalog",
    )
    node = Node.objects.get(pk=link["id"])
    assert (node.follows_text, node.read_at) == (True, None)
    named = made(api, href="https://example.com", title="Primjer")
    assert named["title"] == "Primjer"
    assert not Node.objects.get(pk=named["id"]).follows_text


@pytest.mark.parametrize(
    "href", ["", "ftp://example.com", "https://", "https://[::1", "https://e.com/" + "x" * 2000, 7]
)
def test_a_link_takes_only_a_page_of_the_web(api, href):
    response = api.post("/api/nodes", {"kind": "link", "href": href}, content_type=JSON)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_href"}


def test_only_a_link_has_a_page(api):
    folder = create(api, "folder", "Mapa")
    response = api.patch(f"/api/nodes/{folder}", {"href": "https://example.com"}, content_type=JSON)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_href"}


def test_the_page_names_the_link_says_what_it_is_and_gives_its_icon(api, site):
    link = made(api, href=f"{site}/")
    assert links.read_next()
    assert not links.read_next()

    node = Node.objects.get(pk=link["id"])
    assert (node.title, node.description) == ("Gradska knjižnica", "Katalog i radno vrijeme")
    [listed] = api.get("/api/nodes").json()["children"]
    assert listed["picture"] == node.icon_id
    response = api.get(f"/api/nodes/{link['id']}/picture?v={node.icon_id}")
    assert response.status_code == 200
    with Image.open(io.BytesIO(content(response))) as icon:
        assert (icon.format, icon.size) == ("PNG", (64, 64))


def test_a_named_link_keeps_its_name_and_another_page_is_read_anew(api, site):
    link = made(api, href=f"{site}/", title="Knjižnica")
    links.read_next()
    node = Node.objects.get(pk=link["id"])
    assert (node.title, bool(node.icon_id)) == ("Knjižnica", True)

    response = api.patch(f"/api/nodes/{link['id']}", {"href": f"{site}/prazno"}, content_type=JSON)
    changed = response.json()["node"]
    assert (changed["href"], changed["picture"], changed["description"]) == (
        f"{site}/prazno",
        None,
        "",
    )
    node.refresh_from_db()
    assert node.read_at is None
    assert links.read_next()
    node.refresh_from_db()
    assert (node.title, node.description, node.icon_id) == ("Knjižnica", "", None)


def test_a_page_behind_a_sign_in_gives_the_sites_icon_alone(api, site, monkeypatch):
    monkeypatch.setitem(SITE, "/favicon.ico", (png(32), "image/png"))
    link = made(api, href=f"{site}/prijava")
    assert links.read_next()
    node = Node.objects.get(pk=link["id"])
    assert (node.title, node.description, bool(node.icon_id)) == ("stranica.example", "", True)


def test_a_site_without_an_icon_bears_the_icon_of_the_site_a_level_up(api, site):
    link = made(api, href=site.replace("stranica", "posta.stranica") + "/prijava")
    assert links.read_next()
    with Image.open(store.path_of(Node.objects.get(pk=link["id"]).icon_id)) as drawn:
        assert drawn.size == (links.SIDE, links.SIDE)


def test_a_drawn_icon_is_taken_before_a_small_one(api, site, monkeypatch):
    drawn = []

    def printed(svg, width, height):
        drawn.append(svg)
        return png(64)

    monkeypatch.setattr(printing, "drawn", printed)
    link = made(api, href=f"{site}/crtez")
    assert links.read_next()
    assert Node.objects.get(pk=link["id"]).icon_id
    assert drawn == [SITE["/ikona.svg"][0]]


def test_a_page_behind_the_server_is_not_read(api):
    link = made(api, href="http://127.0.0.1:9/")
    assert links.read_next()
    node = Node.objects.get(pk=link["id"])
    assert (node.title, node.description, node.icon_id) == ("127.0.0.1", "", None)
    assert node.read_at is not None


def test_search_finds_a_link_by_its_page_and_by_its_kind(api, site):
    made(api, href=f"{site}/", title="Knjižnica")
    create(api, "document", "Stranica knjige")
    links.read_next()
    assert [(each["title"], each["source"]) for each in search(api, "radno vrijeme")] == [
        ("Knjižnica", "link")
    ]
    assert {each["title"] for each in search(api, "stranica")} == {"Knjižnica", "Stranica knjige"}
    assert [each["title"] for each in search(api, "vrsta:poveznica")] == ["Knjižnica"]


def test_a_link_given_its_own_description_and_icon_keeps_them_when_its_page_is_read(api, site):
    link = made(api, href=f"{site}/")
    given = links.drawn(png(16))
    Node.objects.filter(pk=link["id"]).update(description="Moja knjižnica", icon=given)
    links.read_next()
    node = Node.objects.get(pk=link["id"])
    assert (node.title, node.description, node.icon_id) == (
        "Gradska knjižnica",
        "Moja knjižnica",
        given.sha256,
    )


def place(client) -> str:
    response = client.post("/api/links", {}, content_type=JSON)
    assert response.status_code in (200, 201), response.json()
    return response.json()["id"]


def test_the_folder_of_links_is_made_once_and_stays_at_the_top(api):
    assert api.get("/api/links").json() == {"folder": None, "groups": [], "links": []}
    response = api.post("/api/links", {}, content_type=JSON)
    assert (response.status_code, response.json()["links"]) == (201, True)
    assert place(api) == response.json()["id"]
    assert api.get("/api/nodes").json()["children"][0]["links"] is True
    elsewhere = create(api, "folder", "Drugdje")
    moved = api.post(
        "/api/nodes/move", {"nodes": [place(api)], "parent": elsewhere}, content_type=JSON
    )
    assert (moved.status_code, moved.json()["error"]) == (400, "links_at_top")


def test_the_page_of_links_holds_the_users_groups_and_the_links_others_give(api):
    ana = person("ana@example.com")
    own = place(api)
    work = create(api, "folder", "Posao", own)
    servers = create(api, "folder", "Poslužitelji", work)
    create(api, "folder", "Prazna", own)
    made(api, href="https://alfa.example", title="Alfa", parent=own)
    made(api, href="https://zeta.example", title="Žeta", parent=servers)
    gone = made(api, href="https://staro.example", title="Staro", parent=own)
    api.post("/api/nodes/trash", {"nodes": [gone["id"]]}, content_type=JSON)
    made(api, href="https://drugdje.example", title="Drugdje", parent=create(api, "folder", "Mapa"))
    theirs = create(ana, "folder", "Anine")
    made(ana, href="https://dijeljeno.example", title="Dijeljeno", parent=theirs)
    made(ana, href="https://skriveno.example", title="Skriveno")
    share(ana, theirs, "read", id=api.user.pk)

    page = api.get("/api/links").json()
    assert page["folder"] == own
    assert [
        (each["title"], [above["title"] for above in each["path"]]) for each in page["groups"]
    ] == [
        ("Posao", ["Links"]),
        ("Prazna", ["Links"]),
        ("Poslužitelji", ["Links", "Posao"]),
    ]
    assert sorted(
        (each["title"], [above["title"] for above in each["path"]], each["root"], each["role"])
        for each in page["links"]
    ) == [
        ("Alfa", ["Links"], "mine", "own"),
        ("Dijeljeno", ["Anine"], "shared", "read"),
        ("Žeta", ["Links", "Posao", "Poslužitelji"], "mine", "own"),
    ]


def test_links_and_groups_stand_where_they_are_dropped(api):
    own = place(api)
    work = create(api, "folder", "Posao", own)
    home = create(api, "folder", "Kuća", own)
    alfa = made(api, href="https://alfa.example", title="Alfa", parent=own)["id"]
    beta = made(api, href="https://beta.example", title="Beta", parent=own)["id"]
    gama = made(api, href="https://gama.example", title="Gama", parent=work)["id"]

    def moved(ids, parent, **given):
        return api.post(
            "/api/nodes/move", {"nodes": ids, "parent": parent, **given}, content_type=JSON
        )

    def page():
        shown = api.get("/api/links").json()
        grouped: dict[str, list[str]] = {}
        for each in shown["links"]:
            grouped.setdefault(each["path"][-1]["title"], []).append(each["title"])
        return [each["title"] for each in shown["groups"]], grouped

    assert page() == (["Posao", "Kuća"], {"Links": ["Alfa", "Beta"], "Posao": ["Gama"]})
    assert moved([beta], own, before=alfa).status_code == 200
    assert moved([home], own, before=work).status_code == 200
    assert page() == (["Kuća", "Posao"], {"Links": ["Beta", "Alfa"], "Posao": ["Gama"]})
    assert moved([work], own, before=home).status_code == 200
    assert moved([gama], own, before=None).status_code == 200
    assert moved([alfa], own, before=None).status_code == 200
    assert page() == (["Posao", "Kuća"], {"Links": ["Beta", "Gama", "Alfa"]})
    made(api, href="https://delta.example", title="Delta", parent=home)
    assert moved([beta], home).status_code == 200
    assert moved([alfa], None).status_code == 200
    assert page() == (["Posao", "Kuća"], {"Links": ["Gama"], "Kuća": ["Delta", "Beta"]})
    assert Node.objects.get(pk=alfa).position is None
    response = moved([gama], own, before=beta)
    assert (response.status_code, response.json()["error"]) == (400, "before_gone")


def test_a_link_takes_the_icon_it_is_given_and_its_sites_again_when_it_is_taken_away(api, site):
    link = made(api, href=f"{site}/", title="Knjižnica")
    links.read_next()
    read = Node.objects.get(pk=link["id"]).icon_id

    def given(icon):
        return api.patch(f"/api/nodes/{link['id']}", {"icon": icon}, content_type=JSON)

    out = io.BytesIO()
    Image.new("RGB", (2000, 1000), (20, 90, 200)).save(out, "PNG")
    response = given({"blob": store.put(io.BytesIO(out.getvalue())).sha256})
    assert response.status_code == 200
    picked = response.json()["node"]["picture"]
    assert picked not in (None, read)
    assert given(f"{site}/ikona.png").json()["node"]["picture"] == read
    response = given(f"{site}/nema.png")
    assert (response.status_code, response.json()["error"]) == (422, "icon_unreadable")
    assert (given(5).status_code, given({"blob": "0" * 64}).status_code) == (400, 400)

    taken = given(None).json()["node"]
    assert (taken["picture"], Node.objects.get(pk=link["id"]).read_at) == (None, None)
    links.read_next()
    assert Node.objects.get(pk=link["id"]).icon_id == read
    folder = create(api, "folder", "Mapa")
    response = api.patch(f"/api/nodes/{folder}", {"icon": None}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (400, "invalid_icon")


def test_a_link_given_another_page_or_its_icon_taken_away_wakes_the_reader_once_saved(
    api, monkeypatch
):
    link = made(api, href="https://example.com/", title="Primjer")
    woken = []
    monkeypatch.setattr(
        links, "wake", lambda: woken.append(Node.objects.get(pk=link["id"]).read_at)
    )
    for change in [{"href": "https://example.org/"}, {"icon": None}]:
        Node.objects.filter(pk=link["id"]).update(read_at=timezone.now())
        response = api.patch(f"/api/nodes/{link['id']}", change, content_type=JSON)
        assert response.status_code == 200
    assert woken == [None, None]


def test_a_group_is_laid_out_in_as_many_columns_as_it_is_given(api):
    own = place(api)
    work = create(api, "folder", "Posao", own)

    def given(node, columns):
        return api.patch(f"/api/nodes/{node}", {"columns": columns}, content_type=JSON)

    assert given(work, 3).json()["node"]["columns"] == 3
    assert api.get("/api/links").json()["groups"][0]["columns"] == 3
    assert given(work, None).json()["node"]["columns"] is None
    for wrong in (0, 7, True, "2"):
        response = given(work, wrong)
        assert (response.status_code, response.json()["error"]) == (400, "invalid_columns")
    link = made(api, href="https://alfa.example", parent=own)
    assert given(link["id"], 2).status_code == 400
