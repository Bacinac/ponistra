import base64
import io

import pytest

from apps.access.models import Grant
from apps.blobs import store
from apps.chat.models import Attachment, Given
from apps.documents.models import Node

from .test_conversations import posted, signed

pytestmark = pytest.mark.django_db

PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def direct(mine, other) -> str:
    return posted(mine, "/api/conversations", people=[{"address": other.email}]).json()["id"]


def group(mine, other, title="Nabava") -> str:
    made = posted(mine, "/api/conversations", people=[{"address": other.email}], title=title)
    return made.json()["id"]


def file_of(owner, title="Ponuda", **more) -> Node:
    blob = store.put(io.BytesIO(PIXEL))
    node = Node.objects.create(
        kind=Node.Kind.FILE, title=title, blob=blob, created_by=owner, **more
    )
    Grant.objects.create(node=node, user=owner, role="own")
    return node


def sent(client, conversation, **data):
    return posted(client, f"/api/conversations/{conversation}/messages", **data)


def listed(client, conversation) -> list[dict]:
    return client.get(f"/api/conversations/{conversation}/messages").json()["messages"]


def test_a_message_carries_uploaded_bytes_and_says_nothing_if_it_likes(owner, ana):
    mine, hers = signed(owner), signed(ana)
    at = direct(mine, ana)
    blob = store.put(io.BytesIO(PIXEL))

    response = sent(mine, at, body="", attachments=[{"blob": blob.pk, "name": "slika.png"}])
    assert response.status_code == 201

    [message] = listed(hers, at)
    assert message["text"] == ""
    [carried] = message["files"]
    assert (carried["name"], carried["size"]) == ("slika.png", len(PIXEL))
    assert carried["media_type"] == "image/png"
    assert carried["picture"] is True
    served = hers.get(carried["href"])
    assert served.status_code == 200
    assert served["Content-Disposition"].startswith("inline")
    assert hers.get(f"{carried['href']}/picture").status_code == 200

    assert sent(mine, at, body="  ").status_code == 400
    outsider = signed(_third())
    assert outsider.get(carried["href"]).status_code == 404


def test_html_in_a_conversation_is_saved_and_never_shown(owner, ana):
    mine, hers = signed(owner), signed(ana)
    at = direct(mine, ana)
    blob = store.put(io.BytesIO(b"<html><script>alert(1)</script></html>"))
    sent(mine, at, body="", attachments=[{"blob": blob.pk, "name": "stranica.html"}])
    [message] = listed(hers, at)
    served = hers.get(message["files"][0]["href"])
    assert served["Content-Disposition"].startswith("attachment")
    assert served["Content-Security-Policy"] == "sandbox"


def test_a_file_of_the_tree_gives_its_members_the_right_to_read_it_while_it_stays(owner, ana):
    mine, hers = signed(owner), signed(ana)
    at = group(mine, ana)
    node = file_of(owner)
    assert hers.get(f"/api/nodes/{node.pk}").status_code == 404

    made = sent(mine, at, body="Pogledaj", attachments=[{"node": str(node.pk)}])
    assert made.status_code == 201
    grant = Grant.objects.get(node=node, user=ana)
    assert grant.role == "read"
    assert hers.get(f"/api/nodes/{node.pk}").status_code == 200
    [message] = listed(hers, at)
    assert message["files"][0]["node"]["id"] == str(node.pk)

    mid = made.json()["id"]
    assert mine.delete(f"/api/conversations/{at}/messages/{mid}").status_code == 204
    assert not Grant.objects.filter(node=node, user=ana).exists()
    assert hers.get(f"/api/nodes/{node.pk}").status_code == 404


def test_a_right_given_by_hand_outlives_the_conversation(owner, ana):
    mine, hers = signed(owner), signed(ana)
    at = group(mine, ana)
    node = file_of(owner)
    Grant.objects.create(node=node, user=ana, role="edit", created_by=owner)
    mid = sent(mine, at, body="x", attachments=[{"node": str(node.pk)}]).json()["id"]
    assert not Given.objects.exists()
    mine.delete(f"/api/conversations/{at}/messages/{mid}")
    assert Grant.objects.get(node=node, user=ana).role == "edit"
    assert hers.get(f"/api/nodes/{node.pk}").status_code == 200


def test_someone_who_comes_later_reads_and_someone_who_leaves_no_longer_does(owner, ana):
    mine, hers = signed(owner), signed(ana)
    at = group(mine, ana)
    node = file_of(owner)
    sent(mine, at, body="x", attachments=[{"node": str(node.pk)}])
    third = _third()
    posted(mine, f"/api/conversations/{at}/members", people=[{"address": third.email}])
    assert Grant.objects.filter(node=node, user=third).exists()

    assert hers.delete(f"/api/conversations/{at}/members").status_code == 204
    assert not Grant.objects.filter(node=node, user=ana).exists()
    [message] = listed(mine, at)
    assert message["files"][0]["name"] == "Ponuda"


def test_only_what_the_user_owns_goes_in_and_nothing_of_a_kept_folder(owner, ana):
    mine, hers = signed(owner), signed(ana)
    at = direct(mine, ana)
    foreign = file_of(ana, "Tuđa")
    assert sent(mine, at, body="x", attachments=[{"node": str(foreign.pk)}]).status_code == 404
    Grant.objects.create(node=foreign, user=owner, role="read", created_by=ana)
    assert sent(mine, at, body="x", attachments=[{"node": str(foreign.pk)}]).status_code == 403

    kept = Node.objects.create(
        kind=Node.Kind.FOLDER, title="Tajno", confined=True, created_by=owner
    )
    Grant.objects.create(node=kept, user=owner, role="own")
    inside = file_of(owner, "Unutra", parent=kept)
    response = sent(mine, at, body="x", attachments=[{"node": str(inside.pk)}])
    assert (response.status_code, response.json()["error"]) == (403, "confined")
    assert not Attachment.objects.exists()
    assert hers.get(f"/api/nodes/{inside.pk}").status_code == 404


def test_a_link_to_an_item_is_shown_only_to_those_who_may_read_it(owner, ana):
    from apps.chat.attaching import DIGITS

    mine, hers = signed(owner), signed(ana)
    at = direct(mine, ana)
    node = file_of(owner)
    value, digits = node.pk.int, ""
    for _ in range(22):
        digits = DIGITS[value % 62] + digits
        value //= 62
    sent(mine, at, body=f"Vidi http://testserver/p/ponuda-{digits} i to je sve")

    assert [each["id"] for each in listed(mine, at)[0]["items"]] == [str(node.pk)]
    assert listed(hers, at)[0]["items"] == []


def test_those_in_a_conversation_see_how_far_the_others_have_read(owner, ana):
    mine, hers = signed(owner), signed(ana)
    at = direct(mine, ana)
    made = sent(mine, at, body="Dobro jutro").json()["id"]
    assert mine.get(f"/api/conversations/{at}/messages").json()["readers"] == []
    posted(hers, f"/api/conversations/{at}/read", message=made)
    assert mine.get(f"/api/conversations/{at}/messages").json()["readers"] == [
        {"name": "Ana Kovač", "read": made}
    ]


def _third():
    from .test_conversations import person

    return person("bruno@example.com", "Bruno", "Babić")


def test_the_search_box_finds_what_was_written_where_the_user_may_read_it(owner, ana):
    mine, hers = signed(owner), signed(ana)
    made = sent(mine, group(mine, ana, "Ponude"), body="Stigla je kalkulacija za Rijeku")
    assert made.status_code == 201
    third = signed(_third())

    [found] = hers.get("/api/search?q=kalkulacija").json()["conversations"]
    assert found["id"] == made.json()["id"]
    assert (found["title"], found["by"], found["parent"]) == ("Ponude", "Ivo Bošković", None)
    assert third.get("/api/search?q=kalkulacija").json()["conversations"] == []
    only = hers.get("/api/search?q=vrsta:razgovor kalkulacija").json()
    assert (len(only["conversations"]), only["documents"]) == (1, [])
    assert hers.get("/api/search?q=vrsta:posta kalkulacija").json()["conversations"] == []
