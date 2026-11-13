from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from apps.access.models import Grant
from apps.documents.models import Node
from apps.users.models import User

pytestmark = pytest.mark.django_db

JSON = "application/json"


def person(email: str, **fields) -> Client:
    client = Client()
    client.user = User.objects.create_user(email, "Kamen-Most-Rijeka-71", **fields)
    client.force_login(client.user)
    return client


@pytest.fixture
def ana():
    return person("ana@example.com", first_name="Ana")


def create(client, kind, title, parent=None) -> str:
    response = client.post(
        "/api/nodes", {"kind": kind, "title": title, "parent": parent}, content_type=JSON
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def share(client, node, role, kind="user", id=None):
    grantee = {"kind": kind, "id": id}
    return client.post(
        f"/api/nodes/{node}/grants", {"grantee": grantee, "role": role}, content_type=JSON
    )


def titles(listing) -> list[str]:
    return [child["title"] for child in listing["children"]]


def test_a_new_top_level_node_belongs_to_its_creator_alone(api, ana):
    folder = create(api, "folder", "Ponude")
    assert Grant.objects.get(node=folder).user == api.user
    assert titles(api.get("/api/nodes").json()) == ["Ponude"]
    assert titles(ana.get("/api/nodes").json()) == []
    assert ana.get(f"/api/nodes/{folder}").status_code == 404
    assert ana.get(f"/api/nodes?parent={folder}").status_code == 404


def test_a_reader_opens_but_changes_nothing(api, ana):
    folder = create(api, "folder", "Ponude")
    document = create(api, "document", "Cjenik", folder)
    assert share(api, folder, "read", id=ana.user.pk).status_code == 201
    assert titles(ana.get("/api/nodes/shared").json()) == ["Ponude"]
    opened = ana.get(f"/api/nodes/{document}").json()
    assert (opened["role"], opened["root"]) == ("read", "shared")
    assert ana.patch(f"/api/nodes/{document}", {"title": "X"}, content_type=JSON).status_code == 403
    refused = ana.post("/api/nodes", {"kind": "folder", "title": "X", "parent": folder}, JSON)
    assert refused.status_code == 403
    assert ana.post(f"/api/nodes/{document}/tabs", {}, content_type=JSON).status_code == 403
    assert ana.post(f"/api/nodes/{document}/versions", {"title": "V"}, JSON).status_code == 403
    assert ana.get(f"/api/nodes/{document}/versions").status_code == 200
    trash = ana.post("/api/nodes/trash", {"nodes": [document]}, content_type=JSON)
    assert trash.status_code == 403


def test_an_editor_works_inside_but_neither_shares_nor_deletes_for_good(api, ana):
    folder = create(api, "folder", "Ponude")
    share(api, folder, "edit", id=ana.user.pk)
    document = create(ana, "document", "Cjenik", folder)
    assert not Grant.objects.filter(node=document).exists()
    assert ana.patch(f"/api/nodes/{document}", {"title": "Novi"}, JSON).status_code == 200
    assert share(ana, document, "read", "everyone").status_code == 403
    assert ana.post("/api/nodes/trash", {"nodes": [document]}, JSON).status_code == 204
    trashed = ana.get("/api/trash").json()["items"]
    assert [(item["id"], item["role"]) for item in trashed] == [(document, "edit")]
    assert ana.post("/api/trash/purge", {"nodes": [document]}, JSON).status_code == 403
    assert api.post("/api/trash/purge", {"nodes": [document]}, JSON).status_code == 204


def test_groups_and_everyone_reach_their_members(api, ana):
    marko = person("marko@example.com")
    office = Group.objects.create(name="Ured")
    ana.user.groups.add(office)
    by_group = create(api, "folder", "Ured")
    for_all = create(api, "folder", "Obavijesti")
    share(api, by_group, "read", "group", office.pk)
    share(api, for_all, "read", "everyone")
    assert titles(ana.get("/api/nodes/shared").json()) == ["Obavijesti", "Ured"]
    assert titles(marko.get("/api/nodes/shared").json()) == ["Obavijesti"]


def test_shared_with_me_lists_the_topmost_and_hides_the_folders_above(api, ana):
    clients = create(api, "folder", "Klijenti")
    acme = create(api, "folder", "Acme", clients)
    offer = create(api, "document", "Ponuda", acme)
    share(api, acme, "read", id=ana.user.pk)
    share(api, offer, "edit", id=ana.user.pk)
    assert titles(ana.get("/api/nodes/shared").json()) == ["Acme"]
    opened = ana.get(f"/api/nodes/{offer}").json()
    assert [node["title"] for node in opened["path"]] == ["Acme", "Ponuda"]
    assert opened["role"] == "edit"
    access = ana.get(f"/api/nodes/{offer}/access").json()
    sources = sorted(
        (grant["grantee"]["name"], "" if grant["from"] is None else grant["from"]["title"] or "?")
        for grant in access["grants"]
    )
    assert sources == [("Ana", ""), ("Ana", "Acme"), ("ivo@example.com", "?")]
    hidden = next(grant for grant in access["grants"] if grant["role"] == "own")
    assert hidden["from"] == {"id": None, "title": None}


def test_my_own_top_level_folder_is_mine_not_shared(api, ana):
    folder = create(ana, "folder", "Ana")
    share(ana, folder, "read", "everyone")
    assert titles(ana.get("/api/nodes").json()) == ["Ana"]
    assert titles(ana.get("/api/nodes/shared").json()) == []
    assert titles(api.get("/api/nodes/shared").json()) == ["Ana"]


def test_what_i_share_lists_the_topmost_of_my_own_that_others_may_open(api, ana):
    clients = create(api, "folder", "Klijenti")
    acme = create(api, "folder", "Acme", clients)
    offer = create(api, "document", "Ponuda", acme)
    create(api, "document", "Privatno")
    price = create(api, "document", "Cjenik")
    share(api, acme, "read", id=ana.user.pk)
    share(api, offer, "edit", id=ana.user.pk)
    share(api, price, "read", "everyone")
    theirs = create(ana, "folder", "Anino")
    share(ana, theirs, "read", "everyone")
    assert titles(api.get("/api/nodes/shared?by=me").json()) == ["Acme", "Cjenik"]
    api.post("/api/nodes/trash", {"nodes": [price]}, JSON)
    assert titles(api.get("/api/nodes/shared?by=me").json()) == ["Acme"]
    assert titles(ana.get("/api/nodes/shared?by=me").json()) == ["Anino"]


def test_a_listing_shows_my_role_who_can_open_and_where_access_widens(api, ana):
    folder = create(api, "folder", "Ponude")
    share(api, folder, "edit", id=ana.user.pk)
    plain = create(api, "document", "Bilješke", folder)
    wider = create(api, "document", "Cjenik", folder)
    share(api, wider, "read", "everyone")
    listing = api.get(f"/api/nodes?parent={folder}").json()
    children = {child["id"]: child for child in listing["children"]}
    assert children[plain]["role"] == "own"
    assert [(who["kind"], who["role"]) for who in children[plain]["audience"]] == [
        ("user", "own"),
        ("user", "edit"),
    ]
    assert (children[plain]["wider"], children[wider]["wider"]) == (False, True)
    top = api.get("/api/nodes").json()["children"][0]
    assert top["wider"] is True
    assert ana.get(f"/api/nodes?parent={folder}").json()["role"] == "edit"


def test_the_access_panel_lists_what_below_opens_wider(api, ana):
    folder = create(api, "folder", "Ponude")
    inner = create(api, "folder", "Interno", folder)
    deep = create(api, "document", "Plan", inner)
    create(api, "document", "Bilješke", folder)
    share(api, deep, "edit", id=ana.user.pk)
    below = api.get(f"/api/nodes/{folder}/access").json()["below"]
    assert [(item["path"], item["grants"][0]["grantee"]["name"]) for item in below] == [
        (["Interno", "Plan"], "Ana")
    ]


def test_an_editor_moves_only_inside_the_folder_their_editing_comes_from(api, ana):
    shared = create(api, "folder", "Zajedničko")
    share(api, shared, "edit", id=ana.user.pk)
    inner = create(api, "folder", "Arhiva", shared)
    document = create(api, "document", "Zapisnik", shared)
    own = create(ana, "folder", "Moje")

    def move(client, parent, node):
        return client.post("/api/nodes/move", {"nodes": [node], "parent": parent}, JSON)

    assert move(ana, inner, document).status_code == 200
    assert move(ana, own, document).json() == {"error": "move_out"}
    assert move(ana, None, document).json() == {"error": "move_out"}
    assert move(api, None, document).status_code == 200
    assert Grant.objects.get(node=document).user == api.user


def test_a_top_level_node_keeps_an_owner(api, ana):
    folder = create(api, "folder", "Ponude")
    inner = create(api, "folder", "Interno", folder)
    mine = Grant.objects.get(node=folder)
    assert api.delete(f"/api/grants/{mine.pk}").json() == {"error": "last_owner"}
    assert api.patch(f"/api/grants/{mine.pk}", {"role": "read"}, JSON).status_code == 400
    gone = person("staro@example.com", is_active=False).user
    Grant.objects.create(node_id=folder, user=gone, role="own")
    assert api.delete(f"/api/grants/{mine.pk}").json() == {"error": "last_owner"}
    share(api, folder, "own", id=ana.user.pk)
    assert api.delete(f"/api/grants/{mine.pk}").status_code == 204
    assert api.get(f"/api/nodes/{folder}").status_code == 404
    deep = share(ana, inner, "own", id=ana.user.pk).json()
    assert ana.delete(f"/api/grants/{deep['id']}").status_code == 204


def test_sharing_again_changes_the_role_instead_of_adding_a_grant(api, ana):
    folder = create(api, "folder", "Ponude")
    share(api, folder, "read", id=ana.user.pk)
    assert share(api, folder, "edit", id=ana.user.pk).json()["role"] == "edit"
    assert Grant.objects.filter(node=folder, user=ana.user).count() == 1
    assert share(api, folder, "read", "user", 999999).json() == {"error": "invalid_grantee"}
    assert share(api, folder, "boss", id=ana.user.pk).json() == {"error": "invalid_role"}


def test_restoring_into_a_trashed_folder_puts_the_node_on_top_with_its_owners(api, ana):
    folder = create(api, "folder", "Ponude")
    document = create(api, "document", "Cjenik", folder)
    share(api, folder, "edit", id=ana.user.pk)
    ana.post("/api/nodes/trash", {"nodes": [document]}, content_type=JSON)
    api.post("/api/nodes/trash", {"nodes": [folder]}, content_type=JSON)
    assert ana.post("/api/trash/restore", {"nodes": [document]}, JSON).status_code == 204
    assert Node.objects.get(pk=document).parent is None
    assert list(Grant.objects.filter(node=document).values_list("user", "role")) == [
        (api.user.pk, "own")
    ]
    assert titles(api.get("/api/nodes").json()) == ["Cjenik"]


def test_a_folder_and_what_was_trashed_in_it_come_back_together_in_their_place(api):
    folder = create(api, "folder", "Ponude")
    document = create(api, "document", "Cjenik", folder)
    other = create(api, "document", "Bilješke")
    api.post("/api/nodes/trash", {"nodes": [document]}, content_type=JSON)
    api.post("/api/nodes/trash", {"nodes": [folder, other]}, content_type=JSON)
    restored = api.post("/api/trash/restore", {"nodes": [document, folder]}, JSON)
    assert restored.status_code == 204
    assert str(Node.objects.get(pk=document).parent_id) == folder
    assert titles(api.get("/api/nodes").json()) == ["Ponude"]
    assert api.post("/api/trash/purge", {"nodes": [other, other]}, JSON).status_code == 204
    assert api.get("/api/trash").json()["items"] == []


def test_the_people_to_share_with_are_the_active_users_and_the_groups(api, ana):
    person("staro@example.com", is_active=False)
    office = Group.objects.create(name="Ured")
    ana.user.groups.add(office)
    people = api.get("/api/people").json()
    assert [user["email"] for user in people["users"]] == ["ana@example.com", "ivo@example.com"]
    assert people["users"][0]["groups"] == [office.pk]
    assert people["groups"] == [{"id": office.pk, "name": "Ured"}]


def test_recent_lists_what_i_can_read_the_latest_changed_first(api, ana):
    clients = create(api, "folder", "Klijenti")
    offer = create(api, "document", "Ponuda", clients)
    create(api, "document", "Privatno")
    own = create(ana, "document", "Bilješke")
    gone = create(ana, "document", "Staro")
    share(api, clients, "read", id=ana.user.pk)
    ana.post("/api/nodes/trash", {"nodes": [gone]}, content_type=JSON)
    Node.objects.filter(pk=own).update(updated_at=Node.objects.get(pk=offer).updated_at)
    Node.objects.filter(pk=offer).update(
        updated_at=Node.objects.get(pk=offer).updated_at + timedelta(minutes=1)
    )
    ana.post("/api/nodes", {"kind": "link", "href": "https://alfa.example"}, content_type=JSON)
    items = ana.get("/api/nodes/recent").json()["items"]
    assert [(item["title"], item["root"]) for item in items] == [
        ("Ponuda", "shared"),
        ("Bilješke", "mine"),
    ]
    assert [node["title"] for node in items[0]["path"]] == ["Klijenti"]
    assert items[1]["path"] == []
