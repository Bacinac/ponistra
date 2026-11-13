import pytest
from django.test import Client

from apps.access.models import Grant, Role
from apps.documents.models import Favourite, Node
from apps.users.models import User

pytestmark = pytest.mark.django_db

JSON = "application/json"


def made(api, title="Ugovor", kind="document", parent=None):
    response = api.post(
        "/api/nodes", {"kind": kind, "title": title, "parent": parent}, content_type=JSON
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def mark(api, ids, favourite=True):
    return api.post(
        "/api/nodes/favourites", {"nodes": ids, "favourite": favourite}, content_type=JSON
    )


def titles(api):
    return [each["title"] for each in api.get("/api/nodes/favourites").json()["children"]]


def colleague():
    other = Client()
    other.user = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    other.force_login(other.user)
    return other


def test_favourites_are_marked_and_unmarked_folders_first(api):
    assert titles(api) == []
    document, folder = made(api, "Aneks"), made(api, "Zbirka", kind="folder")
    assert mark(api, [document, folder]).status_code == 204
    assert mark(api, [document]).status_code == 204
    assert Favourite.objects.count() == 2
    assert titles(api) == ["Zbirka", "Aneks"]

    assert mark(api, [folder], favourite=False).status_code == 204
    assert titles(api) == ["Aneks"]


def test_a_favourite_says_where_it_lives(api):
    folder = made(api, "Zbirka", kind="folder")
    mark(api, [made(api, "Aneks", parent=folder)])
    [listed] = api.get("/api/nodes/favourites").json()["children"]
    assert [step["title"] for step in listed["path"]] == ["Zbirka"]
    assert listed["root"] == "mine"
    assert listed["role"] == "own"


def test_a_favourite_is_its_users_alone(api):
    document = made(api)
    other = colleague()
    Grant.objects.create(node_id=document, user=other.user, role=Role.READ)
    mark(api, [document])
    assert titles(other) == []

    assert mark(other, [document]).status_code == 204
    mark(api, [document], favourite=False)
    assert titles(api) == []
    assert titles(other) == ["Ugovor"]


def test_only_what_the_user_can_read_is_marked(api):
    document = made(api)
    assert mark(colleague(), [document]).status_code in (403, 404)
    assert not Favourite.objects.exists()


def test_a_favourite_leaves_with_the_trash_or_the_grant_and_returns_with_them(api):
    document = made(api)
    other = colleague()
    grant = Grant.objects.create(node_id=document, user=other.user, role=Role.READ)
    mark(api, [document])
    mark(other, [document])

    grant.delete()
    assert titles(other) == []
    Grant.objects.create(node_id=document, user=other.user, role=Role.READ)
    assert titles(other) == ["Ugovor"]

    api.post("/api/nodes/trash", {"nodes": [document]}, content_type=JSON)
    assert titles(api) == []
    Node.objects.filter(pk=document).update(trashed_at=None)
    assert titles(api) == ["Ugovor"]


def test_a_request_without_the_choice_is_refused(api):
    document = made(api)
    response = api.post("/api/nodes/favourites", {"nodes": [document]}, content_type=JSON)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_favourite"
