import base64
import threading
import time
from datetime import timedelta
from email.utils import format_datetime

import pytest
from django.utils import timezone

from apps.core import sealed
from apps.mail import servers, sync, taking
from apps.mail.activesync import sync as activesync
from apps.mail.activesync import wbxml
from apps.mail.activesync.wbxml import element as e
from apps.mail.imap import Failed
from apps.mail.models import Account, Correspondent, Folder, Message, Named, Source
from apps.users.models import User

from . import eas
from .eas import everything, item
from .mox import letter

pytestmark = pytest.mark.django_db(transaction=True)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def box(settings):
    settings.MAIL_PLAIN_HOSTS = {"127.0.0.1"}
    mailbox = eas.Mailbox()
    server = eas.serve(mailbox)
    mailbox.host = f"127.0.0.1:{server.server_address[1]}"
    yield mailbox
    server.shutdown()
    server.server_close()


@pytest.fixture
def account(box):
    owner = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    return Account.objects.create(
        owner=owner,
        address=eas.USER,
        username=eas.USER,
        secret=sealed.seal("mail", eas.PASSWORD),
        protocol=Account.Protocol.ACTIVESYNC,
        activesync_host=box.host,
        device="5c1d" * 8,
    )


def subjects(folder: Folder) -> list[tuple[str, bool, bool]]:
    return list(folder.messages.order_by("subject").values_list("subject", "seen", "flagged"))


def test_wbxml_carries_what_it_was_given():
    tree = e(
        "AirSync:Sync",
        e("AirSync:Collections", e("AirSync:Collection", e("AirSync:SyncKey", "7"))),
        e("AirSyncBase:Data", b"\xff\x00MIME"),
        e("AirSync:MoreAvailable"),
        e("Email:Subject", "Ponuda za Šibenik"),
    )
    found = wbxml.decoded(wbxml.encoded(tree))
    assert found.text("Collections/Collection/SyncKey") == "7"
    assert found.find("Data").value == b"\xff\x00MIME"
    assert found.find("MoreAvailable").children == []
    assert found.text("Subject") == "Ponuda za Šibenik"
    with pytest.raises(wbxml.Malformed):
        wbxml.decoded(wbxml.HEADER + b"\x45")


def test_an_activesync_account_is_kept_once_its_server_lets_it_in(client, box):
    client.force_login(User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71"))

    def connect(**given):
        sent = {
            "address": eas.USER,
            "username": eas.USER,
            "password": eas.PASSWORD,
            "protocol": "activesync",
            "activesync": {"host": f"http://{box.host}/traveler"},
        } | given
        return client.post("/api/mail/accounts", sent, content_type="application/json")

    assert connect(password="wrong").json() == {"error": "activesync_login"}
    assert connect(activesync={"host": "traveler brezik"}).json() == {"error": "invalid_activesync"}
    assert connect(protocol="pop3").json() == {"error": "invalid_protocol"}
    made = connect()
    assert made.status_code == 201
    assert (made.json()["protocol"], made.json()["activesync"]) == (
        "activesync",
        {"host": box.host},
    )
    kept = Account.objects.get()
    assert (kept.imap_host, kept.imap_port, len(kept.device)) == ("", None, 32)
    assert box.commands == []


def test_folders_and_messages_come_in_whole_once_the_policy_is_taken(account, box):
    box.put("1", item("Ponuda", read=True, flagged=True))
    given = item("Račun")
    box.put("1", given)
    box.put("3", item("Nacrt ugovora"))
    everything(account)
    assert box.commands[:4] == ["FolderSync", "Provision", "Provision", "FolderSync"]
    account.refresh_from_db()
    assert (account.state, account.policy_key) == ("ready", "222")
    kinds = {source.name: source.kind for source in account.sources.all()}
    assert kinds == {"Inbox": "inbox", "Sent Items": "sent", "Inbox/Projekti": ""}
    inbox = Folder.objects.get(role="inbox")
    assert subjects(inbox) == [("Ponuda", True, True), ("Račun", False, False)]
    kept = inbox.messages.get(subject="Račun")
    assert (kept.text.strip(), kept.sender["address"]) == ("Pozdrav iz Zagreba.", "ana@example.com")
    assert taking.whole(kept) == given.mime
    projects = Folder.objects.get(name="Projekti")
    assert (projects.parent.account, subjects(projects)) == (
        account,
        [("Nacrt ugovora", False, False)],
    )


def test_new_mail_comes_a_window_at_a_time_and_what_changed_on_the_server_does_not(account, box):
    first = box.put("1", item("Prvo"))
    second = box.put("1", item("Drugo"))
    everything(account)
    box.items["1"][first].read = True
    del box.items["1"][second]
    for number in range(60):
        box.put("1", item(f"Novo {number:03}"))
    inbox = account.sources.get(kind="inbox")
    with activesync.session(account, eas.PASSWORD) as client:
        activesync.caught_up(client, inbox)
    assert Message.objects.count() == 62
    assert not Message.objects.get(subject="Prvo").seen
    assert box.commands.count("Sync") >= 3


def test_a_message_opens_from_what_was_taken_and_its_flags_stay_here(client, account, box):
    message = letter("Ponuda", "Cijena je 100 €.")
    message.add_alternative('<p>Cijena <b>100 €</b>.</p><img src="cid:logo@example.com">', "html")
    message.get_payload()[1].add_related(PNG, "image", "png", cid="<logo@example.com>")
    message.add_attachment(
        b"%PDF-1.7", maintype="application", subtype="pdf", filename="Šibenik.pdf"
    )
    server_id = box.put("1", item("Ponuda", message))
    everything(account)
    asked = len(box.commands)
    kept = Message.objects.get()
    assert kept.message_id == message["Message-ID"]
    client.force_login(account.owner)
    url = f"/api/mail/messages/{kept.pk}"
    del box.items["1"][server_id]
    shown = client.get(url).json()
    image = f"{url}/parts/1.2.2"
    assert "<b>100 €</b>" in shown["html"] and f'src="{image}"' in shown["html"]
    [attachment] = shown["attachments"]
    assert (attachment["name"], attachment["part"]) == ("Šibenik.pdf", "2")
    assert client.patch(url, {"seen": True}, content_type="application/json").json()["seen"]
    assert len(box.commands) == asked


def test_a_wiped_device_loses_the_accounts_mail_and_is_not_followed(account, box):
    box.put("1", item("Povjerljivo"))
    everything(account)
    box.wipe = True
    with pytest.raises(Failed) as wiped:
        sync.keep(account.pk, threading.Event())
    assert wiped.value.code == "activesync_wiped"
    assert not box.wipe
    assert not Source.objects.exists() and not Message.objects.exists()
    sync.failed(account.pk, wiped.value.code)
    assert account.pk not in sync.followed()


def test_new_mail_arrives_while_the_account_is_followed(account, box):
    stop = threading.Event()
    following = threading.Thread(target=sync.keep, args=(account.pk, stop))
    following.start()
    try:
        wait_for(lambda: Account.objects.get(pk=account.pk).state == "ready")
        box.put("1", item("Stiglo"))
        wait_for(lambda: Message.objects.filter(subject="Stiglo").exists())
        box.put("1", item("Stiglo opet"))
        wait_for(lambda: Message.objects.filter(subject="Stiglo opet").exists())
        assert Account.objects.get(pk=account.pk).state == "ready"
    finally:
        stop.set()
        following.join(timeout=eas.HOLD + 5)
    assert not following.is_alive()
    assert box.commands.count("Ping") >= 2


def test_an_activesync_server_is_guessed_where_imap_is_not_let_out(client, monkeypatch):
    client.force_login(User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71"))
    monkeypatch.setattr(servers, "_published", lambda address, domain: None)
    monkeypatch.setattr(servers, "_imap_answers", lambda host: False)
    monkeypatch.setattr(servers, "_activesync_answers", lambda host: host == "traveler.example.org")
    found = client.post(
        "/api/mail/servers", {"address": "ana@example.org"}, content_type="application/json"
    ).json()
    assert found["protocol"] == "activesync"
    assert found["activesync"] == {"host": "traveler.example.org", "username": "ana@example.org"}


def wait_for(condition, seconds: float = 15) -> None:
    until = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > until:
            raise AssertionError("waited in vain")
        time.sleep(0.2)


def domino(subject, item, sender="Ana Horvat/Firma", to="Ivo Boskovic/Firma@Firma", **given):
    """A message as HCL Traveler gives one: its own item id for a Message-ID, Domino names for
    people, the text rendered as HTML."""
    when = given.get("date", timezone.now())
    text = given.get("text", "Pozdrav iz Zagreba.")
    return eas.Item(
        mime=(
            f"Message-ID: {item}\r\nContent-Type: text/html; charset=UTF-8\r\n"
            f"Date: {format_datetime(when)}\r\nFrom: {sender}\r\nTo: {to}\r\n"
            f"Subject: {subject}\r\nMIME-Version: 1.0\r\nX-IBM-UNID: {item.replace(':', 'A')}\r\n"
            f'\r\n<font size="2" face="sans-serif">{text}<br>\r\n</font>'
        ).encode(),
        date="2026-10-24T08:28:56.000Z",
    )


def test_domino_names_become_the_addresses_the_directory_gives(client, account, box):
    box.people = [
        ("Ana Horvat", "Ana.Horvat@firma.test"),
        ("Ana Horvatić", "ana.h@firma.test"),
        ("Marko Marić", "marko@firma.test"),
        ("Marko Marić", "marko.maric@firma.test"),
    ]
    box.put("1", domino("Ponuda", "1:101", to="Ivo Boskovic/Firma@Firma, Marko Marić/Firma"))
    box.put("1", domino("Račun", "1:102"))
    everything(account)
    offer = Message.objects.get(subject="Ponuda")
    assert offer.sender == {"name": "Ana Horvat", "address": "Ana.Horvat@firma.test"}
    assert [each["address"] for each in offer.to] == [
        "Ivo Boskovic/Firma@Firma",
        "Marko Marić/Firma",
    ]
    assert box.commands.count("Search") == 3
    assert set(Named.objects.values_list("name", "address")) == {
        ("Ana Horvat/Firma", "Ana.Horvat@firma.test"),
        ("Ivo Boskovic/Firma@Firma", ""),
        ("Marko Marić/Firma", ""),
    }
    client.force_login(account.owner)
    drafted = client.get(f"/api/mail/messages/{offer.pk}/draft", {"as": "all"}).json()
    assert drafted["to"] == [
        {"name": "Ana Horvat", "address": "Ana.Horvat@firma.test"},
        {"name": "Ivo Boskovic", "address": "Ivo Boskovic/Firma@Firma"},
        {"name": "Marko Marić", "address": "Marko Marić/Firma"},
    ]
    assert [each["name"] for each in drafted["unnamed"]] == ["Ivo Boskovic", "Marko Marić"]
    refused = client.post(
        "/api/mail/send",
        {"account": account.pk, "to": drafted["to"], "subject": "Re: Ponuda", "html": "<p>Da.</p>"},
        content_type="application/json",
    )
    assert (refused.status_code, refused.json()["error"]) == (400, "invalid_recipient")


def test_names_taken_before_the_directory_knew_them_are_written_again(account, box):
    box.put("1", domino("Ponuda", "1:101"))
    everything(account)
    assert Message.objects.get().sender["address"] == "Ana Horvat/Firma"
    box.people = [("Ana Horvat", "Ana.Horvat@firma.test")]
    Named.objects.update(asked_at=timezone.now() - timedelta(days=2))
    everything(account)
    message = Message.objects.get()
    assert message.sender["address"] == "Ana.Horvat@firma.test"
    assert message.fingerprint == taking.fingerprinted(message)


def test_an_address_is_completed_from_the_mail_then_from_the_directory(client, account, box):
    box.people = [
        ("Ana Horvat", "Ana.Horvat@firma.test"),
        ("Ana Kovač", "ANA@firma.test"),
        ("Analitika", "IFXGC3DJORUWWYI=@lnt32.noninternet.sub"),
    ]
    Correspondent.objects.create(
        owner=account.owner, address="ana@firma.test", name="Ana", written=2, last=timezone.now()
    )
    elsewhere = Account.objects.create(
        owner=account.owner,
        address="ivo@zatvoreno.test",
        username="ivo",
        secret=sealed.seal("mail", eas.PASSWORD),
        protocol=Account.Protocol.ACTIVESYNC,
        activesync_host="127.0.0.1:9",
        device="7e2f" * 8,
    )
    client.force_login(account.owner)
    assert client.get("/api/mail/people", {"q": "ana"}).json() == {
        "people": [
            {"name": "Ana", "address": "ana@firma.test"},
            {"name": "Ana Horvat", "address": "Ana.Horvat@firma.test"},
        ],
        "unanswered": [elsewhere.address],
    }


def test_copies_no_message_id_ties_are_one_message_but_two_items_of_a_folder_two(account, box):
    now = timezone.now()
    me = {"sender": "Ana Kovač/Firma", "to": eas.USER}
    box.put("2", domino("Sastanak", "2:101", date=now + timedelta(seconds=1), **me))
    box.put("1", domino("Sastanak", "1:102", date=now, **me))
    box.put("1", domino("Izvještaj", "1:103", date=now))
    box.put("1", domino("Izvještaj", "1:104", date=now))
    box.people = [("Ana Kovač", eas.USER)]
    everything(account)
    meeting = Message.objects.get(subject="Sastanak")
    assert (meeting.folder.role, meeting.arrivals.count()) == ("inbox", 2)
    assert Message.objects.filter(subject="Izvještaj").count() == 2


def test_what_ponistra_sent_and_the_servers_copy_of_it_are_one_message(account, box):
    ours = letter("Ugovor", "Šaljem ugovor.\n\nLijep pozdrav")
    sent = taking.sent(account, ours.as_bytes())
    box.people = [("Ana Kovač", eas.USER)]
    text = "Šaljem ugovor.<br>\r\n<br>\r\nLijep pozdrav"
    box.put("2", domino("Ugovor", "2:105", sender="Ana Kovač/Firma", to="mox@localhost", text=text))
    everything(account)
    assert list(Message.objects.values_list("pk", flat=True)) == [sent.pk]
    assert sent.arrivals.get().item.startswith("2:")


def test_a_message_deleted_for_good_stays_deleted_in_every_copy(client, account, box):
    me = {"sender": "Ana Kovač/Firma", "to": eas.USER}
    box.put("2", domino("Sastanak", "2:101", **me))
    box.put("1", domino("Sastanak", "1:102", **me))
    box.people = [("Ana Kovač", eas.USER)]
    everything(account)
    message = Message.objects.get()
    client.force_login(account.owner)
    deleted = client.post(
        f"/api/mail/folders/{message.folder_id}/chosen",
        {"action": "delete", "where": {"messages": [message.pk]}},
        "application/json",
    )
    assert deleted.json() == {"changed": 1}
    Source.objects.update(sync_key="")
    box.told.clear()
    everything(account)
    assert not Message.objects.exists()
