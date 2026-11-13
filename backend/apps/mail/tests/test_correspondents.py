from datetime import UTC, datetime

import pytest

from apps.mail import taking
from apps.mail.models import Account, Correspondent, Folder, Source
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def ivo(client):
    user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(user)
    return user


@pytest.fixture
def account(ivo):
    return Account.objects.create(owner=ivo, address="Ivo@Example.com", username="ivo")


def source(account, role, kind=""):
    folder = Folder.objects.create(owner=account.owner, name=role, role=role)
    return Source.objects.create(account=account, folder=folder, name=role.upper(), kind=kind)


def mail(*headers: str) -> bytes:
    return ("\r\n".join(headers) + "\r\n\r\nx").encode()


def noted(owner) -> dict:
    found = owner.mail_correspondents.all()
    return {each.address: (each.name, each.written, each.heard) for each in found}


def test_whom_the_user_wrote_to_and_who_wrote_to_them_are_noted_apart(account):
    inbox, junk = source(account, "inbox", "inbox"), source(account, "junk", "junk")
    taking.sent(
        account,
        mail(
            "Message-ID: <1@x>",
            "From: ivo@example.com",
            "To: Ana Kovač <Ana@Example.test>, iva@example.test",
            "Cc: Ana <ana@example.test>, Marko Marić/Firma",
        ),
    )
    given = ("Message-ID: <2@x>", "From: Ana Kovač <ana@example.test>", "To: ivo@example.com")
    taking.took(inbox, mail(*given, "Reply-To: ana@example.test"), {})
    taking.took(inbox, mail("Message-ID: <3@x>", "From: Ana Horvat/Firma"), {})
    taking.took(junk, mail("Message-ID: <4@x>", "From: Dobitak <win@example.net>"), {})
    assert noted(account.owner) == {
        "ana@example.test": ("Ana Kovač", 1, 1),
        "iva@example.test": ("", 1, 0),
    }


def test_people_the_directory_named_later_are_noted_once(account):
    inbox = source(account, "inbox", "inbox")
    given = ("Message-ID: <1@x>", "From: Ana Horvat/Firma", "To: ivo@example.com")
    taking.took(inbox, mail(*given), {})
    taking.sent(
        account,
        mail(
            "Message-ID: <2@x>", "From: ivo@example.com", "To: Ana Horvat/Firma, iva@example.test"
        ),
    )
    found = {"Ana Horvat/Firma": "Ana.Horvat@firma.test"}
    assert taking.renamed(account.owner_id, found) == 2
    assert taking.renamed(account.owner_id, found) == 0
    assert noted(account.owner) == {
        "ana.horvat@firma.test": ("Ana Horvat", 1, 1),
        "iva@example.test": ("", 1, 0),
    }


def test_addresses_are_completed_by_the_start_of_a_word_colleagues_and_whom_the_user_wrote_to_first(
    client, ivo
):
    when = datetime(2026, 10, 1, tzinfo=UTC)
    for name, address, written, heard in [
        ("Đurđa Bošković", "durda@x.test", 0, 5),
        ("Ivo Horvat", "ivo.horvat@x.test", 3, 0),
        ("", "noreply@bosko.test", 0, 50),
        ("Ana", "ana.bosko@x.test", 1, 0),
    ]:
        Correspondent.objects.create(
            owner=ivo, name=name, address=address, written=written, heard=heard, last=when
        )
    Correspondent.objects.create(
        owner=User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"),
        address="bosko@tudi.test",
        last=when,
    )

    def completed(typed):
        found = client.get("/api/mail/people", {"q": typed}).json()
        assert found["unanswered"] == []
        return [each["address"] for each in found["people"]]

    assert completed("bos") == ["ana.bosko@x.test", "durda@x.test"]
    assert completed("đurđa") == completed("Durda") == ["durda@x.test"]
    assert completed("ivo hor") == ["ivo.horvat@x.test"]
    assert completed("ana") == ["ana@example.com", "ana.bosko@x.test"]
    assert completed("vat") == completed("  ") == []


def test_a_message_to_someone_goes_from_the_account_the_user_last_wrote_to_them_from(
    client, account
):
    home = Account.objects.create(owner=account.owner, address="ivo@home.test", username="home")
    inbox = source(account, "inbox", "inbox")
    taking.took(
        inbox, mail("Message-ID: <1@x>", "From: ana@example.test", "To: ivo@example.com"), {}
    )
    taking.took(
        inbox, mail("Message-ID: <2@x>", "From: iva@example.test", "To: ivo@example.com"), {}
    )
    sent = ("Message-ID: <3@x>", "From: ivo@home.test", "To: ana@example.test")
    taking.sent(home, mail(*sent, "Date: Mon, 2 Nov 2026 10:00:00 +0100"))

    def sender(address):
        return client.get("/api/mail/sender", {"to": address}).json()["account"]

    assert sender("Ana@Example.test") == home.pk
    assert sender("iva@example.test") == account.pk
    assert sender("nepoznat@example.test") is None


def test_the_mail_waiting_is_unread_from_people_the_user_writes_to_and_what_they_flagged(
    client, account
):
    inbox, archive = source(account, "inbox", "inbox"), source(account, "archive", "archive")
    taking.sent(account, mail("Message-ID: <1@x>", "From: ivo@example.com", "To: ana@example.test"))
    for number, sender in (
        (2, "Ana <Ana@Example.test>"),
        (3, "ana@example.test"),
        (4, "iva@example.test"),
    ):
        taking.took(
            inbox, mail(f"Message-ID: <{number}@x>", f"From: {sender}", f"Subject: {number}"), {}
        )
    taking.took(archive, mail("Message-ID: <5@x>", "From: iva@example.test", "Subject: 5"), {})
    old = "Date: Thu, 10 Oct 2024 17:16:00 +0200"
    taking.took(archive, mail("Message-ID: <6@x>", "From: iva@example.test", "Subject: 6", old), {})
    account.owner.mail_messages.filter(subject="3").update(seen=True)
    account.owner.mail_messages.filter(subject__in=("5", "6")).update(flagged=True)

    found = client.get("/api/mail/waiting").json()
    assert sorted(each["subject"] for each in found["messages"]) == ["2", "5"]
    assert found["count"] == 2
