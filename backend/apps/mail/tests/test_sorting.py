import pytest

from apps.mail import sorting, taking
from apps.mail.models import Account, Folder, Message, Rule, Source
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def ivo(client):
    user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(user)
    return user


@pytest.fixture
def account(ivo):
    return Account.objects.create(owner=ivo, address="ivo@example.com", username="ivo")


@pytest.fixture
def told(monkeypatch):
    found = []
    monkeypatch.setattr(taking.push, "tell", lambda users, kind, data, **_: found.append(data))
    return found


def source(account, role="", name=""):
    folder = Folder.objects.create(owner=account.owner, name=name or role, role=role)
    return Source.objects.create(account=account, folder=folder, name=(name or role).upper())


def mail(number: int, sender: str) -> bytes:
    return f"Message-ID: <{number}@x>\r\nFrom: {sender}\r\nSubject: {number}\r\n\r\nx".encode()


def numbered(number: int) -> int:
    return Message.objects.get(message_id=f"<{number}@x>").pk


def act(client, name: str, numbers: list[int], **parameters):
    target = {"messages": [numbered(each) for each in numbers]}
    given = {"target": target, "parameters": parameters}
    return client.post(f"/api/mail/actions/{name}", given, "application/json")


def where(*numbers: int) -> list[str]:
    found = Message.objects.filter(message_id__in=[f"<{each}@x>" for each in numbers])
    return [each.folder.role or each.folder.name for each in found.order_by("subject")]


def test_a_rule_is_named_by_the_address_then_each_domain_it_is_under():
    assert sorting.names(" Ana@Mail.Shop.test ") == [
        "ana@mail.shop.test",
        "mail.shop.test",
        "shop.test",
    ]
    assert sorting.names("mox@localhost") == ["mox@localhost"]
    assert sorting.names("Ana Horvat/Firma") == sorting.names("@shop.test") == []


def test_arriving_mail_goes_where_the_narrowest_rule_for_its_sender_sends_it(account, told):
    inbox, sent = source(account, "inbox"), source(account, "sent")
    junk = Folder.objects.create(owner=account.owner, name="junk", role="junk")
    news = Folder.objects.create(owner=account.owner, name="Novosti")
    Rule.objects.create(owner=account.owner, sender="shop.test", folder=junk)
    Rule.objects.create(owner=account.owner, sender="news@mail.shop.test", folder=news)
    given = [
        "Akcija <promo@shop.test>",
        "promo@mail.shop.test",
        "news@mail.shop.test",
        "ana@myshop.test",
        "Ana <ana@example.test>",
    ]
    for number, sender in enumerate(given, 1):
        taking.took(inbox, mail(number, sender), {}, fresh=True)
    taking.took(sent, mail(6, "promo@shop.test"), {})
    assert where(1, 2, 3, 4, 5, 6) == ["junk", "junk", "Novosti", "inbox", "inbox", "sent"]
    assert [each["address"] for each in told] == ["ana@myshop.test", "ana@example.test"]


def test_a_rule_moves_the_mail_the_user_has_but_not_out_of_their_own_or_put_away(
    account, client, told
):
    inbox, archive = source(account, "inbox"), source(account, "archive")
    sent, trash = source(account, "sent"), source(account, "trash")
    news = Folder.objects.create(owner=account.owner, name="Novosti")
    taking.took(inbox, mail(1, "promo@shop.test"), {})
    taking.took(archive, mail(2, "Promo <PROMO@mail.shop.test>"), {})
    taking.took(sent, mail(3, "promo@shop.test"), {})
    taking.took(trash, mail(4, "promo@shop.test"), {})
    taking.took(inbox, mail(5, "news@shop.test"), {})
    taking.took(inbox, mail(6, "ana@example.test"), {})
    kept = act(client, "mail.always", [5], to=news.pk, by="address")
    assert kept.json() == {"changed": 1}
    blocked = act(client, "mail.block", [1], by="domain")
    assert blocked.json() == {"changed": 2}
    junk = Folder.objects.get(owner=account.owner, role="junk")
    rules = [
        {"id": each.pk, "sender": each.sender, "folder": each.folder_id}
        for each in Rule.objects.order_by("sender")
    ]
    assert [each["sender"] for each in rules] == ["news@shop.test", "shop.test"]
    assert [each["folder"] for each in rules] == [news.pk, junk.pk]
    assert where(1, 2, 3, 4, 5, 6) == ["junk", "junk", "sent", "trash", "Novosti", "inbox"]
    assert client.get("/api/mail/accounts").json()["rules"] == rules
    assert client.delete(f"/api/mail/rules/{rules[1]['id']}").status_code == 204
    taking.took(inbox, mail(7, "promo@shop.test"), {})
    assert where(1, 7) == ["junk", "inbox"]
    assert not told


def test_a_rule_names_the_senders_of_messages_and_a_folder_mail_may_go_to(account, client):
    inbox = source(account, "inbox")
    taking.took(inbox, mail(1, "promo@shop.test"), {})
    taking.took(inbox, mail(2, "Ana Horvat/Firma"), {})
    news = Folder.objects.create(owner=account.owner, name="Novosti")
    assert act(client, "mail.always", [2], to=news.pk, by="address").json() == {
        "error": "invalid_senders"
    }
    for to in ("sent", "drafts", 0):
        refused = act(client, "mail.always", [1], to=to, by="domain")
        assert refused.json() == {"error": "invalid_to"}
    for given, error in (
        ({"to": None, "by": "domain"}, "invalid_to"),
        ({"to": news.pk, "by": "name"}, "invalid_by"),
        ({"to": news.pk}, "invalid_by"),
        ({"to": news.pk, "by": "domain", "at": "x"}, "invalid_parameters"),
    ):
        refused = act(client, "mail.always", [1], **given)
        assert refused.json() == {"error": error}
    other = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(other)
    assert act(client, "mail.block", [1], by="domain").json() == {"error": "not_found"}
    assert not Rule.objects.exists()


def test_mail_said_not_to_be_junk_unblocks_the_rule_that_sent_it_there(account, client):
    inbox, junk = source(account, "inbox"), source(account, "junk")
    news = Folder.objects.create(owner=account.owner, name="Novosti")
    for sender in ("shop.test", "promo@shop.test", "win@example.net"):
        Rule.objects.create(owner=account.owner, sender=sender, folder=junk.folder)
    Rule.objects.create(owner=account.owner, sender="news@example.net", folder=news)
    taking.took(inbox, mail(1, "promo@shop.test"), {})
    taking.took(inbox, mail(2, "win@example.net"), {})
    taking.took(junk, mail(3, "news@example.net"), {})
    assert where(1, 2, 3) == ["junk", "junk", "junk"]
    moved = client.post(
        f"/api/mail/folders/{junk.folder.pk}/chosen",
        {"action": "move", "to": "inbox", "where": {}},
        "application/json",
    )
    assert moved.json() == {"changed": 3}
    assert sorted(Rule.objects.values_list("sender", flat=True)) == [
        "news@example.net",
        "shop.test",
    ]
