import io
from datetime import UTC, datetime, timedelta

import pytest

from apps.blobs import store
from apps.core import sealed
from apps.mail import taking
from apps.mail.models import Account, Arrival, Deleted, Folder, Message, Source
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.xdist_group("mox")]

PASSWORD = "moxmoxmox"
MOX = {
    "address": "mox@localhost",
    "username": "mox@localhost",
    "imap": {"host": "mox", "port": 1143, "security": "none"},
    "smtp": {"host": "mox", "port": 1587, "security": "none"},
}


@pytest.fixture
def ivo(client):
    user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(user)
    return user


def connect(client, **given):
    return client.post("/api/mail/accounts", MOX | given, content_type="application/json")


def chosen(client, folder, action, **given):
    return client.post(
        f"/api/mail/folders/{folder.pk}/chosen", {"action": action, **given}, "application/json"
    )


def kept(owner, address="mox@localhost") -> Account:
    return Account.objects.create(
        owner=owner,
        address=address,
        username=address,
        secret=sealed.seal("mail", PASSWORD),
        imap_host="mox",
        imap_port=1143,
        imap_security="none",
        smtp_host="mox",
        smtp_port=1587,
        smtp_security="none",
    )


def test_an_account_is_kept_once_both_servers_let_it_in(client, ivo):
    response = connect(client, password=PASSWORD, name="Mox")
    assert response.status_code == 201
    made = response.json()
    assert (made["address"], made["name"], made["state"]) == ("mox@localhost", "Mox", "syncing")
    assert "secret" not in made and "password" not in made
    assert sealed.opened("mail", Account.objects.get().secret) == PASSWORD
    listed = client.get("/api/mail/accounts").json()
    assert [account["id"] for account in listed["accounts"]] == [made["id"]]
    assert listed["plain"] == ["mox"]
    assert listed["app_passwords"]["imap.gmail.com"] == "https://myaccount.google.com/apppasswords"
    assert connect(client, password=PASSWORD).json() == {"error": "account_exists"}


def test_a_refused_password_keeps_nothing(client, ivo):
    response = connect(client, password="wrong")
    assert (response.status_code, response.json()) == (400, {"error": "imap_login"})
    assert not Account.objects.exists()


def test_a_server_without_tls_is_refused_unless_it_is_the_test_server(client, ivo):
    given = {"imap": {"host": "imap.example.com", "port": 143, "security": "none"}}
    assert connect(client, password=PASSWORD, **given).json() == {"error": "imap_plain"}
    given = {"smtp": {"host": "smtp.example.com", "port": 587, "security": "none"}}
    assert connect(client, password=PASSWORD, **given).json() == {"error": "smtp_plain"}


def test_servers_are_guessed_from_the_address(client, ivo):
    def guessed(address):
        return client.post(
            "/api/mail/servers", {"address": address}, content_type="application/json"
        ).json()

    gmail = guessed("Ime.Prezime@Gmail.com")
    assert gmail["imap"] == {
        "host": "imap.gmail.com",
        "port": 993,
        "security": "tls",
        "username": "ime.prezime@gmail.com",
    }
    assert gmail["smtp"]["host"] == "smtp.gmail.com"
    assert "signin" not in gmail
    for address in ("ime@outlook.com", "ime@Hotmail.co.uk", "ime@live.com.au", "ime@outlook.hr"):
        assert guessed(address)["signin"] == "microsoft"
    outlook = guessed("ime@outlook.com")
    assert (outlook["imap"]["host"], outlook["smtp"]["host"], outlook["smtp"]["port"]) == (
        "outlook.office365.com",
        "smtp-mail.outlook.com",
        587,
    )
    unknown = guessed("ana@posta.invalid")
    assert (unknown["imap"]["host"], unknown["smtp"]["port"]) == ("imap.posta.invalid", 465)
    assert "signin" not in unknown
    assert guessed("ana") == {"error": "invalid_email"}


def test_an_account_is_changed_and_removed_only_by_its_owner(client, ivo):
    mine = kept(ivo)
    other = kept(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    url = f"/api/mail/accounts/{mine.pk}"
    response = client.patch(url, MOX | {"name": "Posao"}, content_type="application/json")
    assert response.json()["name"] == "Posao"
    assert sealed.opened("mail", Account.objects.get(pk=mine.pk).secret) == PASSWORD
    assert client.delete(f"/api/mail/accounts/{other.pk}").status_code == 404
    assert client.delete(url).status_code == 204
    assert list(Account.objects.values_list("pk", flat=True)) == [other.pk]


def test_the_folders_exchange_keeps_for_outlook_show_only_once_mail_is_in_them(client, ivo):
    account = kept(ivo, "ime@outlook.com")
    root = taking.node(account)
    issues = Folder.objects.create(owner=ivo, parent=root, name="Sync Issues")
    Folder.objects.create(owner=ivo, parent=issues, name="Conflicts")
    outbox = Folder.objects.create(owner=ivo, parent=root, name="Outbox")
    Folder.objects.create(owner=ivo, parent=root, name="Projekti")

    def names():
        return {each["name"] for each in client.get("/api/mail/accounts").json()["folders"]}

    assert names() == {"ime@outlook.com", "Projekti"}
    raw = store.put(io.BytesIO(b"Subject: x\r\n\r\n"))
    Message.objects.create(
        owner=ivo, folder=outbox, account=account, key="1", raw=raw, date=datetime.now(UTC)
    )
    assert names() == {"ime@outlook.com", "Projekti", "Outbox"}


def test_messages_come_a_page_at_a_time_newest_first(client, ivo):
    account = kept(ivo)
    folder = Folder.objects.create(owner=ivo, name="inbox", role="inbox")
    raw = store.put(io.BytesIO(b"Subject: x\r\n\r\n"))
    start = datetime(2026, 10, 1, 9, tzinfo=UTC)
    Message.objects.bulk_create(
        Message(
            owner=ivo,
            folder=folder,
            account=account,
            key=str(number),
            raw=raw,
            subject=str(number),
            date=start + timedelta(hours=number // 3),
            seen=number > 20,
        )
        for number in range(1, 61)
    )
    [listed] = client.get("/api/mail/accounts").json()["folders"]
    assert (listed["count"], listed["unseen"], listed["role"]) == (60, 20, "inbox")
    url = f"/api/mail/folders/{folder.pk}/messages"
    first = client.get(url).json()
    second = client.get(url, {"before": first["before"]}).json()
    subjects = [message["subject"] for message in first["messages"] + second["messages"]]
    assert subjects == [str(number) for number in range(60, 0, -1)]
    assert (len(first["messages"]), second["before"]) == (50, None)
    assert (first["count"], first["unseen"], second["count"]) == (60, 20, 60)
    assert client.get(url, {"before": "yesterday"}).json() == {"error": "invalid_before"}
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    theirs = Folder.objects.create(owner=stranger, name="inbox", role="inbox")
    assert client.get(f"/api/mail/folders/{theirs.pk}/messages").status_code == 404


def test_a_list_is_sorted_by_sender_or_priority_newest_first_among_equals(client, ivo):
    account = kept(ivo)
    folder = Folder.objects.create(owner=ivo, name="inbox", role="inbox")
    raw = store.put(io.BytesIO(b"Subject: x\r\n\r\n"))
    start = datetime(2026, 10, 1, 9, tzinfo=UTC)
    senders = [
        {"name": "Željko", "address": "z@x.test"},
        {"name": "", "address": "ana@x.test"},
        {"name": "Čedo", "address": "c@x.test"},
        {"name": "Bruno", "address": "b@x.test"},
        {"name": "Mail Router", "address": ""},
    ]
    Message.objects.bulk_create(
        Message(
            owner=ivo,
            folder=folder,
            account=account,
            key=str(number),
            raw=raw,
            subject=str(number),
            sender=senders[number % 5],
            priority=number % 3,
            date=start + timedelta(hours=number // 4),
        )
        for number in range(1, 61)
    )
    url = f"/api/mail/folders/{folder.pk}/messages"

    def listed(**given):
        first = client.get(url, given).json()
        second = client.get(url, given | {"before": first["before"]}).json()
        assert second["before"] is None
        return [int(each["subject"]) for each in first["messages"] + second["messages"]]

    newest = sorted(range(1, 61), key=lambda number: (-(number // 4), -number))
    order = ["ana@x.test", "Bruno", "Čedo", "Mail Router", "Željko"]
    name = {
        number: senders[number % 5]["name"] or senders[number % 5]["address"] for number in newest
    }
    assert listed(sort="correspondent", descending="0") == sorted(
        newest, key=lambda number: order.index(name[number])
    )
    assert listed(sort="correspondent", descending="1") == sorted(
        newest, key=lambda number: -order.index(name[number])
    )
    assert listed(sort="priority") == sorted(newest, key=lambda number: -(number % 3))
    assert listed(sort="date", descending="0") == sorted(range(1, 61), key=lambda n: (n // 4, n))
    sent = Folder.objects.create(owner=ivo, name="sent", role="sent")
    for number, person in enumerate(senders[:4]):
        Message.objects.create(
            owner=ivo,
            folder=sent,
            account=account,
            key=f"s{number}",
            raw=raw,
            subject=str(number),
            to=[person],
            date=start,
        )
    to = client.get(
        f"/api/mail/folders/{sent.pk}/messages", {"sort": "correspondent", "descending": "0"}
    )
    assert [each["subject"] for each in to.json()["messages"]] == ["1", "3", "2", "0"]
    assert client.get(url, {"sort": "size"}).json() == {"error": "invalid_sort"}
    wrong = client.get(url, {"sort": "priority", "before": '["x", "2026-10-01", 1]'})
    assert wrong.json() == {"error": "invalid_before"}


def test_a_folder_is_marked_read_at_once_and_only_its_own(client, ivo):
    account = kept(ivo)
    raw = store.put(io.BytesIO(b"Subject: x\r\n\r\n"))
    inbox = Folder.objects.create(owner=ivo, name="inbox", role="inbox")
    junk = Folder.objects.create(owner=ivo, name="junk", role="junk")
    Message.objects.bulk_create(
        Message(
            owner=ivo,
            folder=inbox if number % 2 else junk,
            account=account,
            key=str(number),
            raw=raw,
            date=datetime(2026, 10, 1, 9, number, tzinfo=UTC),
        )
        for number in range(1, 7)
    )
    assert chosen(client, inbox, "seen", where={"seen": False}).json() == {"changed": 3}
    folders = {
        each["id"]: each["unseen"] for each in client.get("/api/mail/accounts").json()["folders"]
    }
    assert folders == {inbox.pk: 0, junk.pk: 3}
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    theirs = Folder.objects.create(owner=stranger, name="inbox", role="inbox")
    assert chosen(client, theirs, "seen").json() == {"error": "not_found"}
    assert chosen(client, junk, "seen").json() == {"changed": 3}


def test_chosen_messages_are_marked_moved_and_deleted_for_good_in_ponistra_only(client, ivo):
    account = kept(ivo)
    raw = store.put(io.BytesIO(b"Subject: x\r\n\r\n"))
    inbox = Folder.objects.create(owner=ivo, name="inbox", role="inbox")
    node = Folder.objects.create(owner=ivo, name="mox@localhost", account=account)
    projects = Folder.objects.create(owner=ivo, name="Projekti", parent=node)
    messages = Message.objects.bulk_create(
        Message(
            owner=ivo,
            folder=inbox,
            account=account,
            key=str(number),
            raw=raw,
            subject=str(number),
            date=datetime(2026, 10, 1, 9, number, tzinfo=UTC),
            seen=number > 3,
        )
        for number in range(1, 7)
    )
    named = [each.pk for each in messages[:2]]
    assert chosen(client, inbox, "flagged", where={"messages": named}).json() == {"changed": 2}
    assert set(Message.objects.filter(flagged=True).values_list("pk", flat=True)) == set(named)
    listed = client.get(f"/api/mail/folders/{inbox.pk}/messages").json()
    assert (listed["count"], listed["unseen"]) == (6, 3)
    assert chosen(client, inbox, "unseen", where={"seen": True}).json() == {"changed": 3}
    moved = chosen(client, inbox, "move", to=projects.pk, where={"messages": named})
    assert moved.json() == {"changed": 2}
    assert chosen(client, projects, "move", to="archive").json() == {"changed": 2}
    archive = Folder.objects.get(owner=ivo, role="archive")
    assert set(archive.messages.values_list("pk", flat=True)) == set(named)
    assert chosen(client, inbox, "move", to="trash").json() == {"changed": 4}
    trash = Folder.objects.get(owner=ivo, role="trash")
    assert chosen(client, trash, "delete").json() == {"changed": 4}
    assert set(Message.objects.values_list("pk", flat=True)) == set(named)
    assert set(Deleted.objects.filter(owner=ivo).values_list("key", flat=True)) == {
        "3",
        "4",
        "5",
        "6",
    }
    for given, error in [
        ({"action": "read"}, "invalid_action"),
        ({"action": "move", "to": node.pk}, "invalid_to"),
        ({"action": "move", "to": "elsewhere"}, "invalid_to"),
        ({"action": "seen", "where": {"messages": ["1"]}}, "invalid_messages"),
        ({"action": "seen", "where": {"seen": "no"}}, "invalid_seen"),
        ({"action": "seen", "where": {"account": "x"}}, "invalid_account"),
        ({"action": "seen", "where": []}, "invalid_where"),
    ]:
        refused = client.post(f"/api/mail/folders/{archive.pk}/chosen", given, "application/json")
        assert refused.json() == {"error": error}
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    theirs = Folder.objects.create(owner=stranger, name="inbox", role="inbox")
    assert chosen(client, archive, "move", to=theirs.pk).json() == {"error": "invalid_to"}


def test_the_flagged_list_holds_them_across_folders_but_trash_and_junk(client, ivo):
    account = kept(ivo)
    raw = store.put(io.BytesIO(b"Subject: x\r\n\r\n"))
    folders = {
        role: Folder.objects.create(owner=ivo, name=role, role=role)
        for role in ("inbox", "archive", "trash", "junk")
    }
    messages = {
        role: Message.objects.create(
            owner=ivo,
            folder=folder,
            account=account,
            key=role,
            raw=raw,
            subject=role,
            date=datetime(2026, 10, 1, 9, at, tzinfo=UTC),
            flagged=True,
        )
        for at, (role, folder) in enumerate(folders.items())
    }
    Message.objects.create(
        owner=ivo,
        folder=folders["inbox"],
        account=account,
        key="plain",
        raw=raw,
        subject="plain",
        date=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
    )
    listed = client.get("/api/mail/folders/flagged/messages").json()
    assert [each["subject"] for each in listed["messages"]] == ["archive", "inbox"]
    assert listed["count"] == 2

    answer = client.post(
        "/api/mail/folders/flagged/chosen",
        {
            "action": "unflagged",
            "where": {"messages": [messages["inbox"].pk, messages["trash"].pk]},
        },
        "application/json",
    )
    assert answer.json() == {"changed": 1}
    listed = client.get("/api/mail/folders/flagged/messages").json()
    assert [each["subject"] for each in listed["messages"]] == ["archive"]

    answer = client.post(
        "/api/mail/folders/flagged/chosen",
        {"action": "move", "to": "trash", "where": {}},
        "application/json",
    )
    assert answer.json() == {"changed": 1}
    assert client.get("/api/mail/folders/flagged/messages").json()["messages"] == []


def test_an_account_kept_apart_shows_its_mail_only_when_it_is_asked_for(client, ivo):
    first, second = kept(ivo), kept(ivo, "druga@localhost")
    raw = store.put(io.BytesIO(b"Subject: x\r\n\r\n"))
    inbox = Folder.objects.create(owner=ivo, name="inbox", role="inbox")
    own, apart, both = Message.objects.bulk_create(
        Message(
            owner=ivo,
            folder=inbox,
            account=account,
            key=subject,
            subject=subject,
            raw=raw,
            date=datetime(2026, 10, 1, 9, minute, tzinfo=UTC),
        )
        for minute, (subject, account) in enumerate(
            [("Prvom", first), ("Drugom", second), ("Oboma", second)]
        )
    )
    source = Source.objects.create(account=first, name="INBOX", kind="inbox", folder=inbox)
    Arrival.objects.create(message=both, source=source, uid=1)
    url = f"/api/mail/accounts/{second.pk}"
    assert (
        client.patch(url, {"together": False}, content_type="application/json").json()["together"]
        is False
    )

    def subjects(**given):
        listed = client.get(f"/api/mail/folders/{inbox.pk}/messages", given).json()["messages"]
        return {each["subject"] for each in listed}

    assert subjects() == {"Prvom", "Oboma"}
    assert subjects(account=second.pk) == {"Drugom", "Oboma"}
    shown = client.get("/api/mail/accounts").json()
    [folder] = shown["folders"]
    assert (folder["count"], folder["unseen"]) == (2, 2)
    assert {each["address"]: each["unseen"] for each in shown["accounts"]} == {
        "mox@localhost": 2,
        "druga@localhost": 2,
    }
    marked = chosen(client, inbox, "seen", where={"account": second.pk, "seen": False})
    assert marked.json() == {"changed": 2}
    assert client.get("/api/mail/accounts").json()["folders"][0]["unseen"] == 1
    assert set(Message.objects.filter(seen=True)) == {apart, both}
    assert own.pk not in Message.objects.filter(seen=True).values_list("pk", flat=True)
    refused = client.patch(url, {"together": "no"}, content_type="application/json")
    assert refused.json() == {"error": "invalid_together"}
    assert client.get(f"/api/mail/folders/{inbox.pk}/messages", {"account": "x"}).json() == {
        "error": "invalid_account"
    }
