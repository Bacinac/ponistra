import io
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.blobs import store
from apps.chat.models import Conversation, Member
from apps.chat.models import Message as Said
from apps.core.api import Refused
from apps.documents.models import Node
from apps.documents.views import created
from apps.journal.models import Entry
from apps.mail.models import Deleted, Folder
from apps.mail.models import Message as Mail
from apps.retention import sweep
from apps.retention.models import Hold, Removal, Rule
from apps.users import erasure
from apps.users.models import User

pytestmark = pytest.mark.django_db

JSON = "application/json"
PASSWORD = "Kamen-Most-Rijeka-71"


@pytest.fixture
def ivo(client):
    client.user = User.objects.create_superuser("ivo@example.com", PASSWORD)
    client.force_login(client.user)
    return client


@pytest.fixture
def ana():
    return User.objects.create_user("ana@example.com", PASSWORD, first_name="Ana")


def aged(node: Node, days: int) -> Node:
    Node.objects.filter(pk=node.pk).update(updated_at=timezone.now() - timedelta(days=days))
    node.refresh_from_db()
    return node


def trashed(*nodes: Node) -> None:
    Node.objects.filter(pk__in=[node.pk for node in nodes]).update(trashed_at=timezone.now())


def purged(client, *nodes: Node):
    return client.post(
        "/api/trash/purge", {"nodes": [str(node.pk) for node in nodes]}, content_type=JSON
    )


def rule(client, **given):
    return client.post("/api/retention/rules", given, content_type=JSON)


def test_only_an_administrator_sets_rules_and_holds(client, ana):
    client.force_login(ana)
    assert client.get("/api/retention/rules").status_code == 403
    assert rule(client, what="mail", keep_days=30).status_code == 403
    assert client.post("/api/retention/holds", {}, content_type=JSON).status_code == 403


def test_a_rule_says_something_sensible_once_per_place(ivo):
    folder = created(None, Node.Kind.FOLDER, "Ugovori", None, ivo.user)
    assert rule(ivo, what="mail").json()["error"] == "rule_says_nothing"
    assert rule(ivo, what="mail", keep_days=30, remove_days=10).json()["error"] == (
        "removed_before_kept"
    )
    assert rule(ivo, what="mail", keep_days=0).json()["error"] == "invalid_keep_days"
    assert rule(ivo, what="chat", folder=str(folder.pk), keep_days=5).json()["error"] == (
        "invalid_folder"
    )
    made = rule(ivo, what="files", folder=str(folder.pk), keep_days=5, remove_days=10)
    assert made.status_code == 201
    assert made.json()["folder"] == {"id": str(folder.pk), "title": "Ugovori"}
    again = rule(ivo, what="files", folder=str(folder.pk), keep_days=7)
    assert again.status_code == 409
    assert rule(ivo, what="files", keep_days=7).status_code == 201
    assert rule(ivo, what="files", remove_days=9).status_code == 409
    pk = made.json()["id"]
    changed = ivo.patch(f"/api/retention/rules/{pk}", {"keep_days": 8}, content_type=JSON)
    assert (changed.json()["keep_days"], changed.json()["remove_days"]) == (8, None)
    assert ivo.delete(f"/api/retention/rules/{pk}").status_code == 204
    shown = ivo.get("/api/retention/rules").json()
    assert [each["what"] for each in shown["rules"]] == ["files"]
    changes = Entry.objects.filter(detail__setting="retention").order_by("pk")
    assert [entry.detail["change"] for entry in changes] == ["added", "added", "changed", "removed"]


def test_a_document_younger_than_its_rule_stays_in_the_trash(ivo):
    folder = created(None, Node.Kind.FOLDER, "Ugovori", None, ivo.user)
    inside = created(folder, Node.Kind.DOCUMENT, "Ugovor", None, ivo.user)
    outside = created(None, Node.Kind.DOCUMENT, "Bilješka", None, ivo.user)
    Rule.objects.create(what="documents", folder=folder, keep_days=30)
    trashed(inside, outside, folder)
    listed = {item["title"]: item["kept"] for item in ivo.get("/api/trash").json()["items"]}
    assert listed == {"Ugovori": "retained", "Ugovor": "retained", "Bilješka": None}
    assert purged(ivo, folder).json()["error"] == "retained"
    assert purged(ivo, inside).status_code == 409
    assert purged(ivo, outside).status_code == 204
    aged(inside, 31)
    assert purged(ivo, folder).status_code == 204
    assert not Node.objects.filter(pk=inside.pk).exists()


def test_the_longest_rule_above_a_document_keeps_it(ivo):
    folder = created(None, Node.Kind.FOLDER, "Ugovori", None, ivo.user)
    inside = aged(created(folder, Node.Kind.DOCUMENT, "Ugovor", None, ivo.user), 40)
    Rule.objects.create(what="documents", folder=folder, keep_days=30)
    Rule.objects.create(what="documents", keep_days=365)
    trashed(inside)
    assert purged(ivo, inside).status_code == 409


def test_a_held_folder_or_person_keeps_whatever_lies_in_it(ivo, ana):
    folder = created(None, Node.Kind.FOLDER, "Spor", None, ivo.user)
    below = created(folder, Node.Kind.FOLDER, "Dokazi", None, ivo.user)
    document = aged(created(below, Node.Kind.DOCUMENT, "Zapisnik", None, ivo.user), 400)
    made = ivo.post(
        "/api/retention/holds", {"name": "Spor 14/2026", "folder": str(below.pk)}, content_type=JSON
    )
    assert made.status_code == 201
    trashed(folder)
    assert purged(ivo, folder).json()["error"] == "held"
    assert ivo.delete(f"/api/retention/holds/{made.json()['id']}").status_code == 204
    held = ivo.post(
        "/api/retention/holds", {"name": "Spor", "person": ivo.user.pk}, content_type=JSON
    )
    assert held.json()["person"]["id"] == ivo.user.pk
    assert purged(ivo, folder).json()["error"] == "held"
    assert Node.objects.filter(pk=document.pk).exists()
    both = {"name": "x", "person": ana.pk, "folder": str(folder.pk)}
    assert ivo.post("/api/retention/holds", both, content_type=JSON).status_code == 400
    settings = Entry.objects.filter(detail__setting="legal_hold").order_by("pk")
    assert [entry.detail["change"] for entry in settings] == ["added", "removed", "added"]


def test_a_held_person_is_not_erased_nor_one_whose_mail_is_still_kept(ivo, ana):
    Hold.objects.create(name="Spor", person=ana)
    with pytest.raises(Refused) as refused:
        erasure.erase(ana, None, ivo.user)
    assert refused.value.error == "held"
    Hold.objects.all().delete()
    Rule.objects.create(what="mail", keep_days=30)
    mailed(ana, days=5)
    with pytest.raises(Refused) as refused:
        erasure.erase(ana, None, ivo.user)
    assert refused.value.error == "retained"
    Mail.objects.update(date=timezone.now() - timedelta(days=31))
    erasure.erase(ana, None, ivo.user)
    assert not User.objects.filter(pk=ana.pk).exists()


def mailed(owner, days: int, folder: Folder | None = None) -> Mail:
    folder = folder or Folder.objects.get_or_create(owner=owner, role="inbox", name="inbox")[0]
    return Mail.objects.create(
        owner=owner,
        folder=folder,
        key=f"{owner.pk}-{days}",
        raw=store.put(io.BytesIO(f"Subject: {days}\r\n\r\n".encode())),
        date=timezone.now() - timedelta(days=days),
    )


def deleting(client, folder, *messages):
    return client.post(
        f"/api/mail/folders/{folder.pk}/chosen",
        {"action": "delete", "where": {"messages": [each.pk for each in messages]}},
        content_type=JSON,
    )


def test_mail_younger_than_its_rule_or_of_a_held_person_is_not_deleted(ivo):
    young, old = mailed(ivo.user, 5), mailed(ivo.user, 50)
    Rule.objects.create(what="mail", keep_days=30)
    listed = ivo.get(f"/api/mail/folders/{young.folder_id}/messages").json()["messages"]
    assert {each["id"]: each["kept"] for each in listed} == {
        young.pk: True,
        old.pk: False,
    }
    assert deleting(ivo, young.folder, young, old).json()["error"] == "retained"
    hold = Hold.objects.create(name="Spor", person=ivo.user)
    assert deleting(ivo, old.folder, old).json()["error"] == "held"
    hold.delete()
    assert deleting(ivo, old.folder, old).json() == {"changed": 1}


def channel(owner, *people) -> Conversation:
    found = Conversation.objects.create(kind="channel", title="Prodaja", created_by=owner)
    for each in (owner, *people):
        Member.objects.create(conversation=found, user=each)
    return found


def said(conversation, author, days: int = 0, parent=None) -> Said:
    made = Said.objects.create(
        conversation=conversation, author=author, body="Dobar dan", parent=parent
    )
    Said.objects.filter(pk=made.pk).update(created_at=timezone.now() - timedelta(days=days))
    return made


def test_a_kept_message_is_not_taken_back_and_a_held_one_not_said_otherwise(ivo, ana):
    found = channel(ivo.user, ana)
    message = said(found, ivo.user)
    path = f"/api/conversations/{found.pk}/messages/{message.pk}"
    Rule.objects.create(what="chat", keep_days=30)
    listed = ivo.get(f"/api/conversations/{found.pk}/messages").json()["messages"]
    assert [each["kept"] for each in listed] == ["retained"]
    assert ivo.delete(path).json()["error"] == "retained"
    changed = ivo.patch(path, {"body": "Dobro jutro"}, content_type=JSON)
    assert changed.status_code == 200
    assert changed.json()["kept"] == "retained"
    Hold.objects.create(name="Spor", person=ana)
    assert ivo.patch(path, {"body": "Laku noć"}, content_type=JSON).json()["error"] == "held"
    assert ivo.delete(f"/api/conversations/{found.pk}").json()["error"] == "held"


def test_the_last_one_out_leaves_a_kept_conversation_behind(ivo):
    found = Conversation.objects.create(kind="group", title="Projekt", created_by=ivo.user)
    Member.objects.create(conversation=found, user=ivo.user)
    said(found, ivo.user)
    Rule.objects.create(what="chat", keep_days=30)
    assert ivo.delete(f"/api/conversations/{found.pk}/members").status_code == 204
    assert Conversation.objects.filter(pk=found.pk).exists()


def test_the_sweep_removes_what_the_nearest_rule_says_but_never_what_is_kept(ivo, ana):
    folder = created(None, Node.Kind.FOLDER, "Arhiva", None, ivo.user)
    held = created(None, Node.Kind.FOLDER, "Spor", None, ivo.user)
    gone = aged(created(None, Node.Kind.DOCUMENT, "Staro", None, ivo.user), 100)
    fresh = aged(created(None, Node.Kind.DOCUMENT, "Novo", None, ivo.user), 10)
    archived = aged(created(folder, Node.Kind.DOCUMENT, "U arhivi", None, ivo.user), 100)
    evidence = aged(created(held, Node.Kind.DOCUMENT, "Dokaz", None, ivo.user), 100)
    Rule.objects.create(what="documents", remove_days=60)
    Rule.objects.create(what="documents", folder=folder, keep_days=365)
    Hold.objects.create(name="Spor", folder=held)
    Rule.objects.create(what="mail", remove_days=30)
    Rule.objects.create(what="chat", remove_days=30)
    old_mail, new_mail, anas = mailed(ivo.user, 40), mailed(ivo.user, 5), mailed(ana, 40)
    Hold.objects.create(name="Ana", person=ana)
    room = Conversation.objects.create(kind="group", title="Projekt", created_by=ivo.user)
    Member.objects.create(conversation=room, user=ivo.user)
    lone = said(room, ivo.user, 40)
    answered = said(room, ivo.user, 40)
    said(room, ivo.user, 5, parent=answered)
    removal = sweep.swept()
    assert (removal.documents, removal.files, removal.mail, removal.chat) == (1, 0, 1, 1)
    assert set(Node.objects.filter(kind="document").values_list("pk", flat=True)) == {
        fresh.pk,
        archived.pk,
        evidence.pk,
    }
    assert set(Mail.objects.values_list("pk", flat=True)) == {new_mail.pk, anas.pk}
    assert Deleted.objects.filter(owner=ivo.user, key=old_mail.key).exists()
    assert not Said.objects.filter(pk=lone.pk).exists()
    assert Said.objects.filter(pk=answered.pk).exists()
    assert gone.pk not in Node.objects.values_list("pk", flat=True)
    assert sweep.swept() is None
    assert Removal.objects.count() == 1
    shown = ivo.get("/api/retention/rules").json()["removals"]
    assert [(each["documents"], each["mail"], each["chat"]) for each in shown] == [(1, 1, 1)]
