import io
import threading
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from docx import Document

from apps.access.tests.test_access import JSON, create, person, titles
from apps.access.tests.test_company import laid_out
from apps.documents.models import Node
from apps.imports import placed
from apps.retention.models import Hold
from apps.shares import smb, sync
from apps.shares.models import Entry, Share

pytestmark = pytest.mark.django_db

LONG_AGO = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)


def word(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def broken_word() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", "<not word")
    return out.getvalue()


class Server:
    """A file server's folder as the tests lay it out: files by path, folders, and what has
    rights narrower than the folder above or may not be deleted."""

    files: dict[str, tuple[bytes, datetime]] = {}
    folders: set[str] = set()
    narrower: set[str] = set()
    kept: set[str] = set()
    refused: str | None = None

    def __init__(self, address, username, password):
        self.address, self.username, self.password = address, username, password

    def __enter__(self):
        if Server.refused:
            raise smb.Failed(Server.refused)
        return self

    def __exit__(self, *_):
        pass

    def walk(self):
        paths = sorted(Server.folders | set(Server.files), key=lambda path: path.split("/"))
        hidden = set()
        for path in paths:
            if any(path.startswith(f"{above}/") for above in hidden):
                continue
            if path in Server.narrower:
                hidden.add(path)
                yield smb.Left(path, "narrower")
            elif path in Server.folders:
                yield smb.Found(path, True, 0, LONG_AGO)
            else:
                data, modified = Server.files[path]
                yield smb.Found(path, False, len(data), modified)

    def read(self, path, alone=False):
        return io.BytesIO(Server.files[path][0])

    def deletable(self, path):
        return path not in Server.kept

    def remove(self, path):
        del Server.files[path]


@pytest.fixture(autouse=True)
def server(monkeypatch):
    Server.files, Server.folders, Server.narrower, Server.kept = {}, set(), set(), set()
    Server.refused = None
    monkeypatch.setattr(smb, "Server", Server)
    return Server


@pytest.fixture
def admin():
    return person("ivo@example.com", is_staff=True)


@pytest.fixture
def finance():
    return Group.objects.create(name="Financije")


@pytest.fixture
def ana(finance):
    client = person("ana@example.com", first_name="Ana")
    client.user.groups.add(finance)
    return client


@pytest.fixture
def folder(admin, finance):
    return laid_out(admin, "Arhiva", {"group": finance.pk, "role": "own"})


def connect(admin, folder, mode="copy", address=r"\\fs01\Podaci\Arhiva"):
    return admin.post(
        f"/api/company/{folder}/share",
        {"address": address, "username": r"FIRMA\ponistra", "password": "tajna", "mode": mode},
        JSON,
    )


def passed(folder) -> Share | None:
    share = Share.objects.filter(folder=folder).first()
    if share is not None:
        sync.passed(share.pk, threading.Event())
    return Share.objects.filter(folder=folder).first()


def children(client, parent) -> list[str]:
    return titles(client.get(f"/api/nodes?parent={parent}").json())


@pytest.mark.parametrize(
    "given, expected",
    [
        (r"\\fs01\Podaci\Arhiva\2025", ("fs01", r"Podaci\Arhiva\2025")),
        ("//nas.local/share/", ("nas.local", "share")),
        ("smb://10.0.0.5/Skeniranje/ulaz", ("10.0.0.5", r"Skeniranje\ulaz")),
        (r"\\fs01", None),
        ("C:\\Podaci", None),
    ],
)
def test_a_folder_is_given_as_windows_names_it(given, expected):
    found = smb.address_of(given)
    assert (found and (found.host, found.path)) == expected


def test_a_file_is_named_as_an_upload_names_it():
    assert placed.named("Ponuda Kvarner.docx") == ("Ponuda Kvarner", "docx")
    assert placed.named("Izvještaj 2025.12") == ("Izvještaj 2025.12", "")
    assert placed.named(".bashrc") == (".bashrc", "")


def test_a_copy_is_read_whole_before_anything_is_copied_and_only_reads(admin, ana, folder, server):
    server.folders = {"Prodaja", "Uprava", "Uprava/Place"}
    server.files = {
        "Prodaja/Ponuda Kvarner.docx": (word("Ponuda za Kvarner"), LONG_AGO),
        "Prodaja/Cjenik.txt": (b"Savjetovanje 80 EUR/h\n", LONG_AGO),
        "Prodaja/Stari ugovor.docx": (broken_word(), LONG_AGO),
        "Uprava/Place/Isplatna lista.docx": (word("Isplatna lista"), LONG_AGO),
    }
    server.narrower = {"Uprava/Place"}

    connected = connect(admin, folder)
    assert connected.status_code == 201, connected.json()
    assert connected.json()["state"] == "reading"
    assert Node.objects.get(pk=folder).copied

    share = passed(folder)
    assert share.state == "read"
    assert {key: share.found[key] for key in ("files", "folders", "left_count")} == {
        "files": 3,
        "folders": 2,
        "left_count": 1,
    }
    assert share.found["left"] == [{"path": "Uprava/Place", "why": "narrower"}]
    assert not Node.objects.filter(parent=folder).exists()

    server.narrower = set()
    assert admin.patch(f"/api/company/{folder}/share", {}, JSON).json()["state"] == "reading"
    share = passed(folder)
    assert (share.state, share.found["files"], share.found["left_count"]) == ("read", 4, 0)
    server.narrower = {"Uprava/Place"}
    admin.patch(f"/api/company/{folder}/share", {}, JSON)
    passed(folder)

    assert admin.patch(f"/api/company/{folder}/share", {"copy": True}, JSON).json()["state"] == (
        "copying"
    )
    share = passed(folder)
    assert share.state == "ready"
    assert share.found["kept"] == [{"path": "Prodaja/Stari ugovor.docx", "kept": "unreadable"}]

    assert children(ana, folder) == ["Prodaja", "Uprava"]
    sales = Entry.objects.get(path="Prodaja").node_id
    assert children(ana, sales) == ["Cjenik", "Ponuda Kvarner", "Stari ugovor"]
    offer = Entry.objects.get(path="Prodaja/Ponuda Kvarner.docx").node
    assert (offer.kind, offer.created_by) == ("document", admin.user)
    placed = ana.get(f"/api/nodes/{offer.pk}").json()
    assert placed["role"] == "read"
    assert (
        ana.post(
            "/api/nodes", {"kind": "folder", "title": "Novo", "parent": str(sales)}, JSON
        ).status_code
        == 403
    )
    assert ana.patch(f"/api/nodes/{offer.pk}", {"title": "Drugo"}, JSON).status_code == 403


def test_a_copy_follows_the_server_until_it_is_moved_in(admin, ana, folder, server):
    server.folders = {"Prodaja"}
    server.files = {
        "Prodaja/Ponuda.docx": (word("Prva ponuda"), LONG_AGO),
        "Prodaja/Cjenik.txt": (b"80 EUR/h\n", LONG_AGO),
    }
    connect(admin, folder)
    passed(folder)
    admin.patch(f"/api/company/{folder}/share", {"copy": True}, JSON)
    passed(folder)
    offer = Entry.objects.get(path="Prodaja/Ponuda.docx").node
    first = offer.source_id

    server.files["Prodaja/Ponuda.docx"] = (word("Druga ponuda"), LONG_AGO + timedelta(days=1))
    del server.files["Prodaja/Cjenik.txt"]
    server.files["Prodaja/Narudžba.txt"] = (b"3 komada\n", LONG_AGO)
    passed(folder)
    offer.refresh_from_db()
    assert offer.source_id != first
    sales = Entry.objects.get(path="Prodaja").node_id
    assert children(ana, sales) == ["Narudžba", "Ponuda"]

    assert admin.post(f"/api/company/{folder}/share/move").status_code == 200
    assert passed(folder) is None
    assert not Node.objects.get(pk=folder).copied
    assert ana.get(f"/api/nodes/{offer.pk}").json()["role"] == "own"
    create(ana, "folder", "Novo", str(sales))


def test_disconnecting_takes_the_copy_away(admin, folder, server):
    server.files = {"Cjenik.txt": (b"80 EUR/h\n", LONG_AGO)}
    connect(admin, folder)
    passed(folder)
    admin.patch(f"/api/company/{folder}/share", {"copy": True}, JSON)
    passed(folder)
    assert Node.objects.filter(parent=folder).count() == 1

    assert admin.delete(f"/api/company/{folder}/share").status_code == 204
    assert not Node.objects.filter(parent=folder).exists()
    assert not Node.objects.get(pk=folder).copied
    assert not Share.objects.exists()


def test_a_held_copy_stays_when_the_server_loses_it_and_is_not_disconnected(admin, folder, server):
    server.folders = {"Spor"}
    server.files = {"Spor/Ugovor.txt": (b"1\n", LONG_AGO), "Cjenik.txt": (b"80\n", LONG_AGO)}
    connect(admin, folder)
    passed(folder)
    admin.patch(f"/api/company/{folder}/share", {"copy": True}, JSON)
    passed(folder)
    dispute = Entry.objects.get(path="Spor").node
    Hold.objects.create(name="Spor 14/2026", folder=dispute)

    server.folders, server.files = set(), {}
    passed(folder)
    assert list(Node.objects.filter(parent=folder).values_list("title", flat=True)) == ["Spor"]
    assert Node.objects.filter(parent=dispute).exists()
    assert not Entry.objects.exists()

    assert admin.delete(f"/api/company/{folder}/share").json() == {"error": "held"}
    assert Share.objects.exists()


def test_an_inbox_moves_each_whole_file_in(admin, ana, folder, server):
    now = timezone.now()
    server.files = {
        "Sken 001.pdf": (b"%PDF-1.7\n%%EOF\n", now - timedelta(minutes=5)),
        "Sken 002.pdf": (b"%PDF-1.7\n%%EOF\n2", now),
    }
    assert connect(admin, folder, "inbox").json()["state"] == "ready"
    assert not Node.objects.get(pk=folder).copied

    passed(folder)
    assert children(ana, folder) == ["Sken 001"]
    assert set(server.files) == {"Sken 002.pdf"}
    taken = Node.objects.get(parent=folder)
    assert ana.get(f"/api/nodes/{taken.pk}").json()["role"] == "own"

    server.files["Sken 002.pdf"] = (b"%PDF-1.7\n%%EOF\n2", now - timedelta(minutes=1))
    server.kept = {"Sken 002.pdf"}
    with pytest.raises(smb.Failed, match="inbox_not_deletable"):
        passed(folder)
    assert children(ana, folder) == ["Sken 001"]


def test_what_the_server_refuses_is_said_before_anything_is_connected(admin, folder, server):
    server.refused = "share_login"
    refused = connect(admin, folder)
    assert (refused.status_code, refused.json()["error"]) == (422, "share_login")
    assert connect(admin, folder, address=r"\\fs01").json()["error"] == "invalid_address"
    assert not Share.objects.exists()

    server.refused = None
    create(admin, "folder", "Ne pripada", None)
    laid = laid_out(admin, "Puna", {"group": None, "role": "own"})
    create(admin, "folder", "Već ima", laid)
    assert connect(admin, laid).json()["error"] == "not_empty"
    assert connect(admin, laid, "inbox").status_code == 201


def test_only_an_administrator_connects(ana, folder):
    assert connect(ana, folder).status_code == 403
