import secrets

import pytest

from apps.blobs.tests.uploads import uploaded
from apps.documents.tests.test_views import PNG
from apps.mail.models import Account, Folder, Message, SignatureImage
from apps.users.models import User

from .mox import letter, put, server, synced
from .test_views import MOX, PASSWORD, connect, kept

pytestmark = [pytest.mark.django_db, pytest.mark.xdist_group("mox")]


@pytest.fixture
def ivo(client):
    user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(user)
    return user


def test_accounts_take_colours_in_turn_and_the_first_sends_new_mail(client, ivo):
    first = connect(client, password=PASSWORD).json()
    second = connect(client, password=PASSWORD, address="druga@localhost").json()
    assert [(first["color"], first["default"]), (second["color"], second["default"])] == [
        (0, True),
        (2, False),
    ]
    url = f"/api/mail/accounts/{second['id']}"
    shown = client.patch(url, {"color": 4, "default": True}, content_type="application/json")
    assert (shown.json()["color"], shown.json()["default"]) == (4, True)
    assert not Account.objects.get(pk=first["id"]).default
    for wrong, error in [({"color": -1}, "invalid_color"), ({"default": False}, "invalid_default")]:
        assert client.patch(url, wrong, content_type="application/json").json() == {"error": error}
    assert connect(client, password=PASSWORD, address="treca@localhost").json()["color"] == 2
    client.delete(url)
    assert Account.objects.get(pk=first["id"]).default
    changed = client.patch(
        f"/api/mail/accounts/{first['id']}",
        MOX | {"name": "Posao"},
        content_type="application/json",
    )
    assert changed.json()["name"] == "Posao"
    named = f"/api/mail/accounts/{first['id']}"
    for given, label in [("Privatno", "Privatno"), (first["address"].upper(), "")]:
        shown = client.patch(named, {"label": given}, content_type="application/json")
        assert shown.json()["label"] == label
    long = client.patch(named, {"label": "x" * 201}, content_type="application/json")
    assert long.json() == {"error": "invalid_label"}
    logo = uploaded(client, PNG)["sha256"]
    stranger = "b" * 64
    signed = client.patch(
        named,
        {
            "signature": f'<p><strong>Ivo</strong></p><p><img src="/api/mail/inline/{logo}">'
            f'<img src="/api/mail/inline/{stranger}"><img src="https://x.test/a.png"></p>'
        },
        content_type="application/json",
    )
    shown = f'<p><strong>Ivo</strong></p><p><img src="/api/mail/inline/{logo}"></p>'
    assert signed.json()["signature"] == shown
    assert client.get(f"/api/mail/inline/{logo}").status_code == 200
    assert client.get(f"/api/mail/inline/{stranger}").status_code == 404
    assert signed.json()["own_signature"]
    images = SignatureImage.objects.filter(signature__account_id=first["id"])
    assert list(images.values_list("blob", flat=True)) == [logo]
    emptied = client.patch(named, {"signature": "<p> </p>"}, content_type="application/json")
    assert (emptied.json()["signature"], emptied.json()["own_signature"]) == ("", True)
    assert not images.exists()
    for wrong in ["x" * 100_001, 7]:
        refused = client.patch(named, {"signature": wrong}, content_type="application/json")
        assert refused.json() == {"error": "invalid_signature"}
        refused = client.put("/api/mail/signature", {"html": wrong}, "application/json")
        assert refused.json() == {"error": "invalid_signature"}

    common = client.put("/api/mail/signature", {"html": "<p>Svima</p>"}, "application/json")
    assert common.json() == {"signature": "<p>Svima</p>"}
    listed = client.get("/api/mail/accounts").json()
    assert listed["signature"] == "<p>Svima</p>"
    by_id = {each["id"]: each for each in listed["accounts"]}
    assert (by_id[first["id"]]["signature"], by_id[first["id"]]["own_signature"]) == ("", True)
    others = [each for each in listed["accounts"] if each["id"] != first["id"]]
    assert others and all(each["signature"] == "<p>Svima</p>" for each in others)
    shared = client.patch(named, {"signature": None}, content_type="application/json")
    assert (shared.json()["signature"], shared.json()["own_signature"]) == ("<p>Svima</p>", False)


def test_a_message_delivered_to_two_accounts_is_one_message_in_one_inbox(client, ivo):
    first, second = kept(ivo), kept(ivo, "druga@localhost")
    subject = f"Oboma {secrets.token_hex(4)}"
    put("INBOX", letter(subject))
    try:
        synced(first, "Inbox")
        synced(second, "Inbox")
    finally:
        with server() as found:
            found.select_folder("INBOX")
            found.delete_messages(found.search(["SUBJECT", subject]))
            found.expunge()
    [message] = Message.objects.filter(subject=subject)
    inbox = Folder.objects.get(owner=ivo, role="inbox")
    assert (message.folder, message.account) == (inbox, first)
    listed = client.get(f"/api/mail/folders/{inbox.pk}/messages").json()["messages"]
    [shown] = [each for each in listed if each["subject"] == subject]
    assert (shown["account"], shown["accounts"]) == (first.pk, [first.pk, second.pk])
    folders = client.get("/api/mail/accounts").json()["folders"]
    assert [each["id"] for each in folders if each["role"] == "inbox"] == [inbox.pk]


def test_the_mail_of_a_removed_account_stays_where_it_was(client, ivo, folder):
    account = kept(ivo)
    put(folder, letter("Ostaje"))
    synced(account, folder)
    node = Folder.objects.get(account=account)
    empty = Folder.objects.create(owner=ivo, parent=node, name="Prazno")
    assert client.delete(f"/api/mail/accounts/{account.pk}").status_code == 204
    assert not Folder.objects.filter(pk=empty.pk).exists()
    message = Message.objects.get(subject="Ostaje")
    assert (message.account, message.folder.parent) == (None, node)
    node.refresh_from_db()
    assert (node.name, node.account) == ("mox@localhost", None)
    again = Account.objects.get(pk=connect(client, password=PASSWORD).json()["id"])
    synced(again, folder)
    assert Folder.objects.get(account=again) == node
    assert Message.objects.filter(subject="Ostaje").count() == 1
