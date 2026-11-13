import pytest
from django.contrib.auth.models import Group

from apps.access.models import Access, Grant
from apps.access.tests.test_access import JSON, create, person, share, titles
from apps.documents.models import Node
from apps.retention.models import Hold

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


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
def marko():
    return person("marko@example.com", first_name="Marko")


def laid_out(admin, title, *grants, **fields) -> str:
    answer = admin.post("/api/company", {"title": title, "grants": list(grants), **fields}, JSON)
    assert answer.status_code == 201, answer.json()
    return answer.json()["id"]


def test_an_administrator_lays_out_company_folders_without_reading_them(admin, ana, marko, finance):
    books = laid_out(admin, "Računovodstvo", {"group": finance.pk, "role": "own"})
    rules = laid_out(
        admin, "Pravilnici", {"group": finance.pk, "role": "own"}, {"group": None, "role": "read"}
    )
    assert admin.get(f"/api/nodes/{books}").status_code == 404
    assert titles(admin.get("/api/nodes/company").json()) == ["Pravilnici"]

    assert titles(ana.get("/api/nodes/company").json()) == ["Pravilnici", "Računovodstvo"]
    assert titles(ana.get("/api/nodes").json()) == []
    assert titles(ana.get("/api/nodes/shared").json()) == []
    assert titles(marko.get("/api/nodes/company").json()) == ["Pravilnici"]
    assert marko.get(f"/api/nodes/{books}").status_code == 404

    invoice = create(ana, "document", "Račun 1", books)
    placed = ana.get(f"/api/nodes/{invoice}").json()
    assert (placed["root"], placed["role"], placed["confined"]) == ("company", "own", False)
    assert [above["title"] for above in placed["path"]] == ["Računovodstvo", "Račun 1"]
    assert marko.get(f"/api/nodes/{rules}").json()["root"] == "company"

    assert admin.get("/api/company").json()["folders"] == [
        {
            "id": rules,
            "title": "Pravilnici",
            "confined": False,
            "share": None,
            "grants": [
                {"group": None, "role": "read"},
                {"group": {"id": finance.pk, "name": "Financije"}, "role": "own"},
            ],
        },
        {
            "id": books,
            "title": "Računovodstvo",
            "confined": False,
            "share": None,
            "grants": [{"group": {"id": finance.pk, "name": "Financije"}, "role": "own"}],
        },
    ]


def test_the_members_work_inside_a_company_folder_but_leave_the_folder_itself_alone(
    admin, ana, finance
):
    books = laid_out(admin, "Računovodstvo", {"group": finance.pk, "role": "own"})
    inside = create(ana, "folder", "2026", books)
    assert ana.patch(f"/api/nodes/{inside}", {"title": "2027"}, JSON).status_code == 200
    refused = {"error": "company_folder"}
    assert ana.patch(f"/api/nodes/{books}", {"title": "Moje"}, JSON).json() == refused
    assert ana.post("/api/nodes/move", {"nodes": [books], "parent": None}, JSON).json() == refused
    assert ana.post("/api/nodes/trash", {"nodes": [books]}, JSON).json() == refused
    assert share(ana, books, "read", kind="everyone").json() == refused
    grant = Grant.objects.get(node=books)
    assert ana.delete(f"/api/grants/{grant.pk}").json() == refused
    assert ana.patch(f"/api/nodes/{books}", {"confined": True}, JSON).status_code == 200


def test_an_administrator_renames_regroups_and_removes_an_empty_company_folder(
    admin, ana, marko, finance
):
    books = laid_out(admin, "Računovodstvo", {"group": finance.pk, "role": "own"})
    url = f"/api/company/{books}"
    assert marko.patch(url, {"title": "Moje"}, JSON).json() == {"error": "forbidden"}
    assert admin.patch(url, {"grants": [{"group": finance.pk, "role": "read"}]}, JSON).json() == {
        "error": "owner_required"
    }
    assert admin.patch(url, {"grants": [{"group": 999, "role": "own"}]}, JSON).json() == {
        "error": "invalid_grantee"
    }
    sales = Group.objects.create(name="Prodaja")
    marko.user.groups.add(sales)
    changed = admin.patch(
        url,
        {"title": "Knjige", "confined": True, "grants": [{"group": sales.pk, "role": "own"}]},
        JSON,
    ).json()
    assert (changed["title"], changed["confined"]) == ("Knjige", True)
    assert titles(ana.get("/api/nodes/company").json()) == []
    assert titles(marko.get("/api/nodes/company").json()) == ["Knjige"]
    assert [entry.detail["role"] for entry in Access.objects.order_by("at", "pk")] == [
        "own",
        None,
        "own",
    ]

    create(marko, "document", "Bilanca", books)
    assert admin.delete(url).json() == {"error": "not_empty"}
    Node.objects.filter(parent=books).delete()
    hold = Hold.objects.create(name="Revizija", folder_id=books)
    assert admin.delete(url).json() == {"error": "held"}
    hold.delete()
    assert admin.delete(url).status_code == 204
    assert not Node.objects.filter(pk=books).exists()


def test_the_owners_read_who_opened_downloaded_and_shared_what_is_in_a_folder(
    api, ana, marko, upload
):
    folder = create(api, "folder", "Ponude")
    offer = create(api, "document", "Ponuda", folder)
    sha256 = upload(PDF)["sha256"]
    scan = api.post(
        "/api/nodes", {"kind": "file", "title": "Sken", "parent": folder, "blob": sha256}, JSON
    ).json()["id"]
    share(api, folder, "read", id=ana.user.pk)
    ana.get(f"/api/nodes/{offer}")
    ana.get(f"/api/nodes/{offer}")
    ana.get(f"/api/nodes/{folder}")
    assert ana.get(f"/api/nodes/{scan}/original").status_code == 200

    entries = api.get(f"/api/nodes/{folder}/log").json()["entries"]
    assert [(e["node"]["title"], e["user"]["name"], e["kind"]) for e in entries] == [
        ("Sken", "Ana", "downloaded"),
        ("Ponuda", "Ana", "opened"),
        ("Ponude", "ivo@example.com", "shared"),
    ]
    assert entries[0]["detail"] == {"format": "pdf"}
    assert entries[2]["detail"]["grantee"]["name"] == "Ana"
    assert entries[2]["detail"]["role"] == "read"
    assert [e["kind"] for e in api.get(f"/api/nodes/{offer}/log").json()["entries"]] == ["opened"]
    assert ana.get(f"/api/nodes/{folder}/log").json() == {"error": "forbidden"}
    assert marko.get(f"/api/nodes/{folder}/log").status_code == 404


def test_a_folder_without_downloads_keeps_its_documents_in_the_browser_except_for_owners(
    api, ana, upload
):
    folder = create(api, "folder", "Plaće")
    inner = create(api, "folder", "Listopad", folder)
    payslip = create(api, "document", "Ana", inner)
    sha256 = upload(PDF)["sha256"]
    scan = api.post(
        "/api/nodes", {"kind": "file", "title": "Sken", "parent": inner, "blob": sha256}, JSON
    ).json()["id"]
    other = create(api, "folder", "Drugo")
    share(api, folder, "edit", id=ana.user.pk)
    share(api, other, "edit", id=ana.user.pk)
    assert ana.patch(f"/api/nodes/{folder}", {"confined": True}, JSON).json() == {
        "error": "forbidden"
    }
    assert api.patch(f"/api/nodes/{payslip}", {"confined": True}, JSON).json() == {
        "error": "invalid_confined"
    }
    assert api.patch(f"/api/nodes/{folder}", {"confined": True}, JSON).status_code == 200

    assert ana.get(f"/api/nodes/{payslip}").json()["confined"] is True
    assert api.get(f"/api/nodes/{payslip}").json()["confined"] is False
    refused = {"error": "confined"}
    for path in ("original", "noted", "file?download=1"):
        assert ana.get(f"/api/nodes/{scan}/{path}").json() == refused
    assert ana.get(f"/api/nodes/{scan}/file").status_code == 200
    for kind in ("docx", "pdf", "ponx"):
        assert ana.post("/api/jobs", {"kind": kind, "document": payslip}, JSON).json() == refused
    assert api.post("/api/jobs", {"kind": "docx", "document": payslip}, JSON).status_code == 202
    copy = {"kind": "copy", "document": payslip, "title": "Kopija"}
    assert ana.post("/api/jobs", copy, JSON).status_code == 202

    moves = ana.post("/api/nodes/move", {"nodes": [payslip], "parent": other}, JSON)
    assert moves.json() == refused
    assert (
        ana.post("/api/nodes/move", {"nodes": [payslip], "parent": folder}, JSON).status_code == 200
    )
    assert ana.post("/api/nodes/move", {"nodes": [inner], "parent": other}, JSON).json() == refused
    archive = create(api, "folder", "Arhiva", other)
    secret = create(api, "folder", "Tajno", other)
    note = create(api, "document", "Bilješka", secret)
    api.patch(f"/api/nodes/{secret}", {"confined": True}, JSON)
    assert ana.post("/api/nodes/move", {"nodes": [note], "parent": archive}, JSON).json() == refused
    moved = ana.post("/api/nodes/move", {"nodes": [secret], "parent": archive}, JSON)
    assert moved.status_code == 200
    assert ana.get(f"/api/nodes/{note}").json()["confined"] is True
