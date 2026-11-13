import pytest

from apps.mail import taking
from apps.mail.models import Message, Source
from apps.users.models import User

from .mox import letter
from .test_views import kept

pytestmark = pytest.mark.django_db


def inbox(account) -> Source:
    return Source.objects.create(
        account=account,
        name="INBOX",
        kind=Source.Kind.INBOX,
        folder=taking.folder(account, Source.Kind.INBOX, ["INBOX"]),
    )


@pytest.fixture
def people():
    ivo = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo")
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana")
    marko = User.objects.create_user("marko@example.com", "Kamen-Most-Rijeka-73")
    return {
        "ivo": kept(ivo, "ivo@firma.test"),
        "ana": kept(ana, "ana@firma.test"),
        "marko": kept(marko, "marko@firma.test"),
    }


def sent(people, subject="Ponuda"):
    """Ivo's message to Ana, Marko and someone outside, as each of them holds it."""
    message = letter(subject)
    message.replace_header("From", "Ivo <ivo@firma.test>")
    message.replace_header("To", "ana@firma.test, marko@firma.test, kupac@example.com")
    raw = message.as_bytes()
    return (
        taking.sent(people["ivo"], raw),
        taking.took(inbox(people["ana"]), raw, {}),
        taking.took(inbox(people["marko"]), raw, {}),
    )


def listed(client, message) -> dict:
    [found] = client.get(f"/api/mail/folders/{message.folder_id}/messages").json()["messages"]
    return found


def test_the_sender_alone_sees_which_colleagues_opened_the_message(client, people):
    mine, anas, markos = sent(people)
    client.force_login(people["ana"].owner)
    seen = client.patch(f"/api/mail/messages/{anas.pk}", {"seen": True}, "application/json")
    assert seen.json()["seen"]
    assert listed(client, anas)["opened"] is None
    assert client.get(f"/api/mail/messages/{anas.pk}").json()["opened_by"] is None
    client.force_login(people["ivo"].owner)
    assert listed(client, mine)["opened"] == {"held": 2, "opened": 1}
    shown = client.get(f"/api/mail/messages/{mine.pk}").json()["opened_by"]
    assert [(each["user"]["name"], bool(each["opened_at"])) for each in shown["colleagues"]] == [
        ("Ana", True),
        ("marko@example.com", False),
    ]
    assert shown["outside"] == 1


def test_marking_a_message_read_is_not_opening_it(client, people):
    mine, anas, _ = sent(people)
    client.force_login(people["ana"].owner)
    folder = anas.folder
    marked = client.post(
        f"/api/mail/folders/{folder.pk}/chosen", {"action": "seen", "where": {}}, "application/json"
    )
    assert marked.json() == {"changed": 1}
    client.patch(f"/api/mail/messages/{anas.pk}", {"seen": False}, "application/json")
    assert Message.objects.get(pk=anas.pk).opened_at is None
    client.force_login(people["ivo"].owner)
    assert listed(client, mine)["opened"] == {"held": 2, "opened": 0}


def test_a_device_keeping_the_mail_for_work_without_the_network_is_not_opening_it(client, people):
    _, anas, _ = sent(people)
    client.force_login(people["ana"].owner)
    assert client.get(f"/api/mail/messages/{anas.pk}?kept=1").status_code == 200
    assert Message.objects.get(pk=anas.pk).opened_at is None


def test_a_copy_without_a_message_id_is_the_colleagues_copy_by_what_it_is_made_of(client, people):
    mine, *_ = sent(people, "Ugovor")
    copy = mine.text.replace("\n", "<br>")
    domino = (
        "Message-ID: 4:8870020\r\nContent-Type: text/html; charset=UTF-8\r\n"
        f"Date: {mine.date:%a, %d %b %Y %H:%M:%S +0000}\r\nFrom: Ivo <ivo@firma.test>\r\n"
        "To: ana@firma.test, marko@firma.test, kupac@example.com\r\nSubject: Ugovor\r\n"
        f"MIME-Version: 1.0\r\n\r\n<font>{copy}</font>"
    )
    dino = kept(
        User.objects.create_user("dino@example.com", "Kamen-Most-Rijeka-74"), "l@firma.test"
    )
    dinos = taking.took(inbox(dino), domino.encode(), {})
    client.force_login(dino.owner)
    client.get(f"/api/mail/messages/{dinos.pk}")
    client.force_login(people["ivo"].owner)
    assert listed(client, mine)["opened"] == {"held": 3, "opened": 1}


def test_the_administrator_turns_it_off_for_everyone_and_what_was_noted_goes(client, people):
    mine, anas, _ = sent(people)
    client.force_login(people["ana"].owner)
    client.get(f"/api/mail/messages/{anas.pk}")
    assert (
        client.patch("/api/mail/setting", {"opened": False}, "application/json").status_code == 403
    )
    admin = people["ivo"].owner
    admin.is_staff = True
    admin.save()
    client.force_login(admin)
    assert client.get("/api/mail/setting").json()["opened"] is True
    turned = client.patch("/api/mail/setting", {"opened": False}, "application/json").json()
    assert (turned["opened"], turned["changed_by"]["name"]) == (False, "Ivo")
    assert not Message.objects.exclude(opened_at=None).exists()
    assert listed(client, mine)["opened"] is None
    client.force_login(people["ana"].owner)
    client.get(f"/api/mail/messages/{anas.pk}")
    assert Message.objects.get(pk=anas.pk).opened_at is None
