import io
import threading
from contextlib import contextmanager

import pytest
from docx import Document

from apps.access.models import Grant, Role
from apps.access.tests.test_access import JSON, person
from apps.documents.models import Node
from apps.drive import google, sync
from apps.drive.models import Drive, Item, Space
from apps.mail.imap import Failed
from apps.mail.tests.test_signin import account_at

pytestmark = pytest.mark.django_db

DOC = "application/vnd.google-apps.document"
FORM = "application/vnd.google-apps.form"
TEXT = "text/plain"


def word(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


class Google:
    """Google's Drive as the tests lay it out: each user's My Drive by its root, shared drives
    with their members, and every change in the order made."""

    roots: dict[str, str] = {}
    files: dict[str, dict] = {}
    data: dict[str, bytes] = {}
    shared: dict[str, str] = {}
    members: dict[str, list[dict]] = {}
    seen: dict[str, set[str]] = {}
    log: list[tuple[str, str]] = []
    taken: list[str] = []
    refused: str | None = None

    def __init__(self, account):
        self.address = account.address

    def root(self):
        if Google.refused:
            raise Failed(Google.refused)
        return Google.roots[self.address]

    def drives(self):
        return [
            {"id": key, "name": name}
            for key, name in Google.shared.items()
            if key in Google.seen.get(self.address, set())
        ]

    def drive(self, drive_id):
        if drive_id not in Google.shared:
            raise google.Missing
        return {"id": drive_id, "name": Google.shared[drive_id]}

    def start(self, drive_id=""):
        return str(len(Google.log))

    def listed(self, drive_id=""):
        return [
            dict(found)
            for found in Google.files.values()
            if found.get("driveId", "") == drive_id and not found.get("trashed")
        ]

    def changes(self, token, drive_id=""):
        found = {}
        for file_id, drive in Google.log[int(token) :]:
            if drive != drive_id:
                continue
            if file_id in Google.files:
                found[file_id] = {"fileId": file_id, "file": dict(Google.files[file_id])}
            else:
                found[file_id] = {"fileId": file_id, "removed": True}
        return list(found.values()), str(len(Google.log))

    def file(self, file_id):
        if file_id in Google.shared:
            return {"id": file_id, "permissionIds": [m["id"] for m in Google.members[file_id]]}
        if file_id not in Google.files:
            raise google.Missing
        return dict(Google.files[file_id])

    def permissions(self, file_id):
        if file_id in Google.shared:
            return Google.members[file_id]
        return Google.files[file_id].get("all", [])

    @contextmanager
    def content(self, found):
        Google.taken.append(found["id"])
        yield io.BytesIO(Google.data[found["id"]])


def put(
    file_id, name, parent, data=b"", kind=TEXT, drive="", modified="2026-03-02T09:00:00Z", **more
):
    found = {
        "id": file_id,
        "name": name,
        "mimeType": kind,
        "parents": [parent],
        "modifiedTime": modified,
        "permissionIds": [],
        **more,
    }
    if drive:
        found["driveId"] = drive
    if kind != google.FOLDER and not kind.startswith(google.NATIVE):
        found["md5Checksum"] = str(hash(data))
    Google.files[file_id] = found
    Google.data[file_id] = data
    Google.log.append((file_id, drive))


def trash(file_id):
    drive = Google.files.pop(file_id).get("driveId", "")
    Google.log.append((file_id, drive))


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    Google.roots = {"ivo@example.com": "root-ivo", "ana@example.com": "root-ana"}
    Google.files, Google.data, Google.shared, Google.members, Google.seen = {}, {}, {}, {}, {}
    Google.log, Google.taken, Google.refused = [], [], None
    monkeypatch.setattr(google, "Google", Google)
    return Google


@pytest.fixture
def ana():
    return person("ana@example.com")


def begun(client, address) -> int:
    account = account_at(client.user, "google", "refresh", address)
    response = client.post("/api/drive", {"account": account.pk}, JSON)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def passed(drive_id) -> Drive | None:
    sync.passed(drive_id, threading.Event())
    return Drive.objects.filter(pk=drive_id).first()


def tree(node) -> dict:
    return {
        child.title: tree(child) if child.kind == Node.Kind.FOLDER else child.kind
        for child in Node.objects.filter(parent=node).order_by("title")
    }


def mine(drive_id) -> Space:
    return Space.objects.get(drive_id=drive_id, shared=False)


def test_a_drive_is_copied_with_its_folders_google_formats_and_who_it_was_shared_with(api, ana):
    put("f1", "Prodaja", "root-ivo", kind=google.FOLDER)
    put(
        "d1",
        "Ponuda Kvarner",
        "f1",
        word("Ponuda za Kvarner"),
        kind=DOC,
        exportLinks={google.EXPORTS[DOC][0]: "https://docs.google.com/x"},
        permissions=[
            {"type": "user", "emailAddress": "ivo@example.com", "role": "owner"},
            {"type": "user", "emailAddress": "Ana@example.com", "role": "writer"},
            {"type": "user", "emailAddress": "netko@drugdje.test", "role": "reader"},
        ],
    )
    put("t1", "Cjenik.txt", "f1", b"Savjetovanje 80 EUR/h\n")
    put("q1", "Anketa", "f1", kind=FORM)
    put("s1", "Prečac", "root-ivo", kind=google.SHORTCUT)
    put("x1", "Tuđe.txt", "root-netko", b"nije moje")

    drive = passed(begun(api, "ivo@example.com"))

    assert (drive.state, drive.error) == ("ready", "")
    space = mine(drive.pk)
    assert (space.folder.title, space.folder.copied, space.folder.parent) == (
        "Google Drive",
        True,
        None,
    )
    assert tree(space.folder) == {"Prodaja": {"Cjenik": "document", "Ponuda Kvarner": "document"}}
    document = Node.objects.get(title="Ponuda Kvarner")
    assert Grant.objects.get(node=document, user=ana.user).role == Role.EDIT
    assert not Grant.objects.filter(node=document).exclude(user=ana.user).exists()
    assert {(each["name"], each["why"]) for each in space.found["left"]} == {
        ("Anketa", "google_only"),
        ("Prečac", "shortcut"),
    }
    assert (space.found["files"], space.found["folders"]) == (2, 1)
    listed = api.get("/api/drive").json()
    assert listed["accounts"][0]["drive"]["spaces"][0]["title"] == "Google Drive"
    assert ana.patch(f"/api/nodes/{document.pk}", {"title": "Moja"}, JSON).status_code == 403


def test_a_pass_takes_only_what_changed(api):
    put("f1", "Prodaja", "root-ivo", kind=google.FOLDER)
    put("f2", "Arhiva", "root-ivo", kind=google.FOLDER)
    put("t1", "Cjenik.txt", "f1", b"80 EUR/h\n")
    put("t2", "Popis.txt", "f1", b"Rijeka\n")
    put("t3", "Stari.txt", "f1", b"staro\n")
    drive_id = begun(api, "ivo@example.com")
    passed(drive_id)
    Google.taken.clear()

    put("t1", "Cjenik 2026.txt", "f2", b"80 EUR/h\n")
    put("t2", "Popis.txt", "f1", b"Rijeka, Pula\n", modified="2026-04-01T09:00:00Z")
    trash("t3")
    put("f3", "Nova", "f2", kind=google.FOLDER)
    put("t4", "Bilješka.txt", "f3", b"nova\n")
    passed(drive_id)

    assert sorted(Google.taken) == ["t2", "t4"]
    assert tree(mine(drive_id).folder) == {
        "Arhiva": {"Cjenik 2026": "document", "Nova": {"Bilješka": "document"}},
        "Prodaja": {"Popis": "document"},
    }
    assert not Item.objects.filter(google_id="t3").exists()
    assert Node.objects.get(title="Popis").source.size == len(b"Rijeka, Pula\n")


def test_a_shared_drive_is_copied_once_and_its_members_reach_it(api, ana):
    Google.shared = {"sd1": "Uprava"}
    Google.members = {
        "sd1": [
            {"id": "p1", "type": "user", "emailAddress": "ivo@example.com", "role": "organizer"},
            {"id": "p2", "type": "user", "emailAddress": "ana@example.com", "role": "reader"},
        ]
    }
    Google.seen = {"ivo@example.com": {"sd1"}, "ana@example.com": {"sd1"}}
    put("u1", "Plan.txt", "sd1", b"plan\n", drive="sd1", permissionIds=["p1", "p2"])
    put(
        "u2",
        "Plaće.txt",
        "sd1",
        b"place\n",
        drive="sd1",
        permissionIds=["p1", "p2", "p3"],
        all=[{"type": "user", "emailAddress": "ana@example.com", "role": "writer"}],
    )

    ivo = passed(begun(api, "ivo@example.com"))
    ana_drive = passed(begun(ana, "ana@example.com"))

    shared = Space.objects.get(shared=True)
    assert (shared.drive_id, shared.folder.title) == (ivo.pk, "Uprava")
    assert Space.objects.filter(google_id="sd1").count() == 1
    assert not Space.objects.filter(drive=ana_drive, shared=True).exists()
    assert Grant.objects.get(node=shared.folder, user=ana.user).role == Role.READ
    assert Grant.objects.get(node__title="Plaće", user=ana.user).role == Role.EDIT
    assert not Grant.objects.filter(node__title="Plan").exists()

    assert api.delete(f"/api/drive/{ivo.pk}").status_code == 204
    passed(ana_drive.pk)
    assert Space.objects.get(shared=True).drive_id == ana_drive.pk


def test_finishing_leaves_the_copies_the_users_own(api):
    put("t1", "Cjenik.txt", "root-ivo", b"80 EUR/h\n")
    drive_id = begun(api, "ivo@example.com")
    assert api.post(f"/api/drive/{drive_id}/finish").json() == {"error": "not_copied"}
    passed(drive_id)
    folder = mine(drive_id).folder

    assert api.post(f"/api/drive/{drive_id}/finish").json()["finishing"]
    assert passed(drive_id) is None

    folder.refresh_from_db()
    assert not folder.copied
    assert not Space.objects.exists()
    assert tree(folder) == {"Cjenik": "document"}


def test_letting_a_drive_go_takes_its_copy_away(api):
    put("t1", "Cjenik.txt", "root-ivo", b"80 EUR/h\n")
    drive_id = begun(api, "ivo@example.com")
    passed(drive_id)

    assert api.delete(f"/api/drive/{drive_id}").status_code == 204

    assert not Node.objects.filter(title__in=["Google Drive", "Cjenik"]).exists()
    assert api.get("/api/drive").json()["accounts"][0]["drive"] is None


def test_a_drive_waits_for_its_user_to_sign_in_again(api):
    drive_id = begun(api, "ivo@example.com")
    Google.refused = "drive_scope"
    with pytest.raises(Failed):
        passed(drive_id)
    sync.failed(drive_id, "drive_scope")
    assert drive_id not in sync.followed()

    Google.refused = None
    assert api.patch(f"/api/drive/{drive_id}", {}, JSON).json()["error"] == ""
    assert drive_id in sync.followed()


def test_only_a_google_account_begins_a_drive_and_only_once(api, ana):
    password = account_at(api.user, "password", "tajna", "ivo@firma.test")
    assert api.post("/api/drive", {"account": password.pk}, JSON).status_code == 404
    drive_id = begun(api, "ivo@example.com")
    account = Drive.objects.get(pk=drive_id).account_id
    assert api.post("/api/drive", {"account": account}, JSON).json() == {"error": "begun"}
    assert ana.get(f"/api/drive/{drive_id}").status_code == 404
