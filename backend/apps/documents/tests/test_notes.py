import pytest
from django.test import Client

from apps.content import elements
from apps.content.models import Element
from apps.documents.models import Node, Tab
from apps.users.models import User

pytestmark = pytest.mark.django_db


def note(api, **fields):
    fields = {"title": "Bilješka", **fields}
    response = api.post("/api/notes", fields, content_type="application/json")
    assert response.status_code == 201, response.json()
    return response.json()


def listed(api):
    return api.get("/api/notes").json()


def test_the_first_note_makes_the_notes_folder_at_the_top_of_my_documents(api):
    assert listed(api) == {"folder": None, "notes": []}
    first = note(api)
    second = note(api)

    folder = Node.objects.get(notes=True)
    assert (folder.title, folder.parent, folder.created_by) == ("Notes", None, api.user)
    assert first["parent"] == second["parent"] == str(folder.pk)
    assert first["title"] == "Bilješka"
    assert Node.objects.get(pk=first["id"]).follows_text
    mine = api.get("/api/nodes").json()["children"]
    assert [(each["title"], each["notes"]) for each in mine] == [("Notes", True)]


def test_notes_are_private(api):
    note(api)
    other = Client()
    other.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert other.get("/api/notes").json() == {"folder": None, "notes": []}
    assert other.get("/api/nodes").json()["children"] == []

    note(other)
    assert Node.objects.filter(notes=True).count() == 2


def test_a_shared_text_and_link_become_the_notes_paragraphs(api):
    made = note(api, text="Popis za put\n\nputovnica", link="https://example.com/karte")
    tab = Tab.objects.get(document_id=made["id"])
    elements.derive(tab.pk)

    texts = Element.objects.filter(tab=tab).order_by("position").values_list("text", "type")
    assert [text for text, _ in texts] == ["Popis za put", "putovnica", "https://example.com/karte"]
    assert made["title"] == "Popis za put"
    assert listed(api)["notes"][0]["excerpt"] == "putovnica https://example.com/karte"


def test_a_note_follows_its_first_line_until_it_is_named(api):
    made = note(api, text="Sastanak u ponedjeljak\nponijeti ugovor")
    tab = Tab.objects.get(document_id=made["id"])
    Node.objects.filter(pk=made["id"]).update(title="Bilješka")
    elements.derive(tab.pk)
    assert Node.objects.get(pk=made["id"]).title == "Sastanak u ponedjeljak"

    api.patch(f"/api/nodes/{made['id']}", {"title": "Ugovor"}, content_type="application/json")
    Tab.objects.filter(pk=tab.pk).update(derived_at=None)
    elements.derive(tab.pk)
    named = Node.objects.get(pk=made["id"])
    assert (named.title, named.follows_text) == ("Ugovor", False)


def test_favourite_notes_come_first_then_the_latest(api):
    first = note(api, text="prva")
    second = note(api, text="druga")
    third = note(api, text="treća")
    assert [each["id"] for each in listed(api)["notes"]] == [third["id"], second["id"], first["id"]]

    marked = {"nodes": [first["id"]], "favourite": True}
    api.post("/api/nodes/favourites", marked, content_type="application/json")
    assert [each["id"] for each in listed(api)["notes"]] == [first["id"], third["id"], second["id"]]

    marked = {"nodes": [first["id"]], "favourite": False}
    api.post("/api/nodes/favourites", marked, content_type="application/json")
    assert [each["id"] for each in listed(api)["notes"]] == [third["id"], second["id"], first["id"]]


def test_the_notes_folder_stays_at_the_top_and_a_note_moved_out_is_a_document(api):
    made = note(api)
    folder = Node.objects.get(notes=True)
    other = api.post(
        "/api/nodes", {"kind": "folder", "title": "Projekti"}, content_type="application/json"
    ).json()
    moved = api.post(
        "/api/nodes/move",
        {"nodes": [str(folder.pk)], "parent": other["id"]},
        content_type="application/json",
    )
    assert moved.status_code == 400
    assert moved.json()["error"] == "notes_at_top"

    api.post(
        "/api/nodes/move",
        {"nodes": [made["id"]], "parent": other["id"]},
        content_type="application/json",
    )
    assert listed(api)["notes"] == []
    assert api.get(f"/api/nodes/{made['id']}").json()["node"]["parent"] == other["id"]


def test_a_trashed_notes_folder_gives_way_to_a_new_one(api):
    note(api)
    folder = Node.objects.get(notes=True)
    api.post("/api/nodes/trash", {"nodes": [str(folder.pk)]}, content_type="application/json")
    assert listed(api) == {"folder": None, "notes": []}

    note(api)
    assert Node.objects.filter(notes=True, trashed_at=None).exclude(pk=folder.pk).count() == 1


def test_a_note_is_found_by_its_owner_alone(api):
    made = note(api, text="Popis za put\n\nputovnica i karte")
    elements.derive(Tab.objects.get(document_id=made["id"]).pk)

    def found(client):
        response = client.get("/api/search", {"q": "putovnica", "zone": "Europe/Zagreb"})
        return [each["id"] for each in response.json()["documents"]]

    assert found(api) == [made["id"]]
    other = Client()
    other.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert found(other) == []
