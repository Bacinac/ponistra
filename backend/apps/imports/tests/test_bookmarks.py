import base64
import io
from contextlib import contextmanager

import pytest
from PIL import Image

from apps.access.tests.test_access import create
from apps.blobs import store
from apps.core import fetch
from apps.documents import printing
from apps.documents.models import Node
from apps.jobs.tests.handed import done, refused

pytestmark = pytest.mark.django_db


def icon() -> str:
    out = io.BytesIO()
    Image.new("RGBA", (16, 16), (20, 90, 90, 255)).save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


EXPORT = f"""<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file. -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1" PERSONAL_TOOLBAR_FOLDER="true">Traka oznaka</H3>
    <DD>Ono što je uvijek pri ruci
    <DL><p>
        <DT><A HREF="https://www.hzzo.hr/" ADD_DATE="1" ICON="{icon()}">HZZO</A>
        <DT><A HREF="javascript:alert(1)">Knjižna oznaka</A>
        <DT><H3></H3>
        <DL><p>
            <DT><A HREF="https://github.com/">GitHub &amp; ja</A>
            <DD>Kod   i suradnja
        </DL><p>
    </DL><p>
    <DT><A HREF="http://www.example.com/">  </A>
</DL><p>
""".encode()


def children(parent) -> list[tuple]:
    return [
        (node.kind, node.title, node.href, node.description, node.follows_text)
        for node in Node.objects.filter(parent=parent).order_by("kind", "title")
    ]


def test_a_browsers_bookmarks_come_in_as_a_folder_of_links_in_their_folders(api):
    blob = store.put(io.BytesIO(EXPORT))
    assert blob.media_type == store.BOOKMARKS

    answer = done(api, "import", blob=blob.sha256, title="Oznake", parent=None)

    top = Node.objects.get(pk=answer["id"])
    assert (top.kind, top.title, top.parent) == ("folder", "Oznake", None)
    assert children(top) == [
        ("folder", "Traka oznaka", "", "", False),
        ("link", "example.com", "http://www.example.com/", "", True),
    ]
    bar = Node.objects.get(parent=top, kind="folder")
    assert children(bar) == [
        ("link", "GitHub & ja", "https://github.com/", "Kod i suradnja", False),
        ("link", "HZZO", "https://www.hzzo.hr/", "", False),
    ]
    hzzo = Node.objects.get(title="HZZO")
    with Image.open(store.path_of(hzzo.icon_id)) as drawn:
        assert (drawn.format, drawn.size) == ("PNG", (16, 16))
    assert not Node.objects.filter(kind="link", read_at__isnull=False).exists()


SERVICES = b"""
- Nadzor:
    - Mlaka:
        href: https://mlaka-proxmox.example/
        icon: proxmox.png
        description: Hipervizor
        widget:
          type: proxmox
          password: tajna
    - DIDA:
        href: https://dida.example
        icon: /icons/dida.png
    - Samo widget:
        widget:
          type: glances
    - Mreza:
        - Usmjernik:
            href: http://192.168.100.1
            icon: mdi-router-wireless-#00ff00
"""
BOOKMARKS = b"""
- Posao:
    - Gmail:
        - abbr: GM
          href: https://mail.google.com/
    - GitHub:
        - icon: si-github
          href: https://github.com/
"""


@pytest.fixture
def web(monkeypatch):
    """The icons Homepage names, as the web would give them, and the SVGs the printer drew."""
    given = {
        "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/proxmox.png": png(),
        "https://cdn.jsdelivr.net/npm/@mdi/svg@latest/svg/router-wireless.svg": SVG,
        "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/github.svg": SVG,
    }
    asked = []

    @contextmanager
    def fetched(url, accept="image/*"):
        asked.append(url)
        if url not in given:
            raise fetch.Unreachable
        yield io.BytesIO(given[url])

    drawn = []

    def printed(svg, width, height):
        drawn.append(svg)
        return png()

    monkeypatch.setattr(fetch, "fetched", fetched)
    monkeypatch.setattr(printing, "drawn", printed)
    return asked, drawn


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (32, 32), (20, 90, 90, 255)).save(out, "PNG")
    return out.getvalue()


def laid_out(parent) -> list[str]:
    return list(
        Node.objects.filter(parent=parent).order_by("position").values_list("title", flat=True)
    )


def files(*given: tuple[str, bytes]) -> list[dict]:
    return [{"blob": store.put(io.BytesIO(data)).sha256, "name": name} for name, data in given]


def test_a_homepage_dashboard_comes_in_as_groups_of_links_with_the_icons_it_names(api, web):
    asked, drawn = web
    place = create(api, "folder", "Poveznice")
    given = files(("services.yaml", SERVICES), ("bookmarks.yaml", BOOKMARKS), ("dida.png", png()))

    answer = done(api, "links", parent=place, files=given)

    assert answer["links"] == 5
    assert children(place) == [
        ("folder", "Nadzor", "", "", False),
        ("folder", "Posao", "", "", False),
    ]
    watched = Node.objects.get(title="Nadzor")
    assert children(watched) == [
        ("folder", "Mreza", "", "", False),
        ("link", "DIDA", "https://dida.example", "", False),
        ("link", "Mlaka", "https://mlaka-proxmox.example/", "Hipervizor", False),
    ]
    assert children(Node.objects.get(title="Posao")) == [
        ("link", "GitHub", "https://github.com/", "", False),
        ("link", "Gmail", "https://mail.google.com/", "", False),
    ]
    icons = dict(Node.objects.filter(kind="link").values_list("title", "icon"))
    assert icons["Gmail"] is None
    assert all(icons[title] for title in ("Mlaka", "DIDA", "Usmjernik", "GitHub"))
    assert b'fill="#00ff00"' in drawn[0] and b'fill="#808080"' in drawn[1]
    assert not any("tajna" in str(node.description) for node in Node.objects.all())
    assert len(asked) == 3

    assert laid_out(place) == ["Nadzor", "Posao"]
    assert laid_out(watched) == ["Mlaka", "DIDA", "Mreza"]
    assert laid_out(Node.objects.get(title="Posao")) == ["Gmail", "GitHub"]

    again = done(api, "links", parent=place, files=given)
    assert again["links"] == 0
    assert Node.objects.filter(kind="link").count() == 5

    more = b"""
- Posao:
    - Box:
        href: https://box.example
- Kuca:
    - Alfa:
        href: https://alfa.example
"""
    assert done(api, "links", parent=place, files=files(("more.yaml", more)))["links"] == 2
    assert laid_out(place) == ["Nadzor", "Posao", "Kuca"]
    assert laid_out(Node.objects.get(title="Posao")) == ["Gmail", "GitHub", "Box"]


def test_only_bookmarks_and_a_homepage_dashboard_are_brought_in_as_links(api, web):
    place = create(api, "folder", "Poveznice")
    assert refused(api, "links", parent=place, files=files(("ikona.png", png()))) == (
        415,
        "not_importable",
    )
    assert refused(
        api, "links", parent=place, files=files(("docker.yaml", b"my-docker:\n  host: x\n"))
    ) == (
        422,
        "unreadable",
    )
    assert refused(api, "links", parent=place, files=[]) == (400, "invalid_files")
