import base64
import secrets
import threading
import time

import anyio
import pytest

from apps.blobs import store
from apps.core import sealed
from apps.mail import sync, taking
from apps.mail.imap import Login, imap
from apps.mail.models import Account, Arrival, Deleted, Message, Source
from apps.mail.views import describe

from .mox import LOGIN, SERVER, letter, own_folder, put, server, synced

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.xdist_group("mox")]

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def given(folder: str) -> list[bytes]:
    """The folder's messages as the server gives them, oldest first."""
    with server() as client:
        client.select_folder(folder, readonly=True)
        found = client.fetch(client.search("ALL"), ["BODY.PEEK[]"])
    return [found[uid][b"BODY[]"] for uid in sorted(found)]


def test_a_folder_comes_in_whole_with_its_flags_and_text(account, folder):
    put(folder, letter("Ponuda za četvrtak"), flags=[b"\\Seen", b"\\Flagged"])
    put(folder, letter("Račun", "Plaćeno."))
    source = synced(account, folder)
    kept = {message.subject: message for message in Message.objects.all()}
    assert set(kept) == {"Ponuda za četvrtak", "Račun"}
    offer = kept["Ponuda za četvrtak"]
    assert offer.sender == {"name": "Ana Kovač", "address": "ana@example.com"}
    assert offer.to == [{"name": "", "address": "mox@localhost"}]
    assert (offer.seen, offer.flagged, kept["Račun"].seen) == (True, True, False)
    assert (offer.text.strip(), offer.preview) == ("Pozdrav iz Zagreba.", "Pozdrav iz Zagreba.")
    assert (offer.owner_id, offer.account_id, offer.folder_id) == (
        account.owner_id,
        account.pk,
        source.folder_id,
    )
    assert taking.whole(offer) == given(folder)[0]
    assert Arrival.objects.filter(source=source).count() == 2


def test_the_folders_of_an_account_make_one_tree_with_its_others(account, folder):
    with imap(*SERVER, LOGIN) as client:
        found = {source.name: source for source in sync.sources(client, account)}
    roles = {name: source.folder.role for name, source in found.items()}
    assert (roles["Inbox"], roles["Sent"], roles["Trash"], roles["Junk"]) == (
        "inbox",
        "sent",
        "trash",
        "junk",
    )
    own = found[folder].folder
    assert (own.name, own.role, own.parent.name, own.parent.account) == (
        folder,
        "",
        "mox@localhost",
        account,
    )
    other = Account.objects.create(
        owner=account.owner, address="druga@localhost", username="mox@localhost", secret=b""
    )
    assert taking.folder(other, "inbox", ["INBOX"]) == found["Inbox"].folder
    assert taking.folder(other, "all", ["[Gmail]", "All Mail"]).role == "archive"
    assert taking.folder(other, "", ["INBOX", "Projekti"]).parent.name == "druga@localhost"


def test_an_archive_the_server_does_not_mark_is_known_by_its_name(account):
    class Outlook:
        def list_folders(self):
            return [
                ((b"\\HasNoChildren",), b"/", "Archive"),
                ((b"\\Marked", b"\\HasNoChildren"), b"/", "Inbox"),
                ((b"\\HasNoChildren",), b"/", "Projekti/Archive"),
            ]

    Source.objects.create(
        account=account, name="Archive", folder=taking.folder(account, "", ["Archive"])
    )
    roles = {source.name: source.folder.role for source in sync.sources(Outlook(), account)}
    assert roles == {"Archive": "archive", "Inbox": "inbox", "Projekti/Archive": ""}
    assert not taking.node(account).children.filter(name="Archive").exists()


def test_files_are_cut_out_of_the_message_and_put_back_where_they_were(account, folder):
    message = letter("Izvještaj", "Tekst izvještaja.")
    message.add_alternative('<p>Tekst <img src="cid:logo@example.com"></p>', subtype="html")
    message.get_payload()[1].add_related(PNG, "image", "png", cid="<logo@example.com>")
    pdf = b"%PDF-1.7\n" + secrets.token_bytes(3000)
    message.add_attachment(pdf, maintype="application", subtype="pdf", filename="Šibenik.pdf")
    put(folder, message)
    synced(account, folder)
    kept = Message.objects.get()
    files = {each.part: each for each in kept.files.all()}
    assert set(files) == {"1.2.2", "2"}
    assert (files["2"].name, files["2"].type, files["2"].inline) == (
        "Šibenik.pdf",
        "application/pdf",
        False,
    )
    assert (files["1.2.2"].cid, files["1.2.2"].inline) == ("logo@example.com", True)
    assert store.path_of(files["2"].blob_id).read_bytes() == pdf
    assert files["2"].offset is not None and files["1.2.2"].offset is not None
    [raw] = given(folder)
    assert kept.raw.size < len(raw) - len(pdf)
    assert kept.attachments and kept.text.strip() == "Tekst izvještaja."
    assert taking.whole(kept) == raw


def test_a_file_its_base64_would_not_give_back_stays_in_the_message(account, folder):
    letters = base64.b64encode(b"x" * 300)
    raw = (
        b"From: ana@example.com\r\nTo: mox@localhost\r\nSubject: Nepravilno\r\n"
        b"Message-ID: <nepravilno@example.com>\r\nMIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n'
        b"--b\r\nContent-Type: text/plain\r\n\r\nTekst.\r\n"
        b"--b\r\nContent-Type: application/pdf\r\n"
        b"Content-Disposition: attachment; filename=a.pdf\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\n"
        + letters[:70]
        + b"\r\n"
        + letters[70:]
        + b"\r\n--b--\r\n"
    )
    with server() as client:
        client.append(folder, raw)
    synced(account, folder)
    kept = Message.objects.get()
    [carried] = kept.files.all()
    assert (carried.offset, carried.name) == (None, "a.pdf")
    assert store.path_of(carried.blob_id).read_bytes() == b"x" * 300
    assert taking.whole(kept) == given(folder)[0]


def test_an_html_message_reads_as_its_text_and_charset(account, folder):
    message = letter("Obavijest")
    message.set_content(
        "<html><style>p{color:red}</style><body><p>Čestitamo,</p>"
        "<p>vaš&nbsp;zahtjev je primljen.</p></body></html>",
        subtype="html",
        charset="iso-8859-2",
        cte="quoted-printable",
    )
    put(folder, message)
    synced(account, folder)
    kept = Message.objects.get()
    assert kept.text == "Čestitamo,\nvaš zahtjev je primljen."
    assert kept.preview == "Čestitamo, vaš zahtjev je primljen."


def test_a_message_in_two_folders_is_kept_once_and_stays_once_the_provider_drops_it(
    account, folder
):
    subject = f"Ugovor {secrets.token_hex(4)}"
    put(folder, letter(subject))
    with own_folder() as archive:
        with server() as client:
            client.select_folder(folder)
            client.copy(client.search("ALL"), archive)
        synced(account, folder)
        synced(account, archive)
        [message] = Message.objects.filter(subject=subject)
        held = message.arrivals.values_list("source__name", flat=True)
        assert sorted(held) == sorted([folder, archive])
        assert message.folder.name == folder
    with server() as client:
        client.select_folder(folder)
        client.delete_messages(client.search("ALL"))
        client.expunge()
    synced(account, folder)
    assert list(Message.objects.filter(subject=subject)) == [message]


def test_a_message_deleted_for_good_does_not_come_back_from_a_folder_given_out_again(
    account, folder
):
    put(folder, letter("Obrisano"))
    put(folder, letter("Ostaje"))
    source = synced(account, folder)
    gone = Message.objects.get(subject="Obrisano")
    Deleted.objects.create(owner=account.owner, key=gone.key)
    gone.delete()
    Source.objects.filter(pk=source.pk).update(uidvalidity=None)
    synced(account, folder)
    assert list(Message.objects.values_list("subject", flat=True)) == ["Ostaje"]


def test_old_mail_is_taken_newest_first_a_batch_at_a_time(account, folder, monkeypatch):
    for subject in ("Prvo", "Drugo", "Treće"):
        put(folder, letter(subject))
    monkeypatch.setattr(sync, "HEADS", 2)
    with imap(*SERVER, LOGIN) as client:
        [source] = [found for found in sync.sources(client, account) if found.name == folder]
        sync.caught_up(client, source)
        assert not Message.objects.exists()
        assert sync.older(client, source)
        assert set(Message.objects.values_list("subject", flat=True)) == {"Drugo", "Treće"}
        assert describe(account)["older"]
        put(folder, letter("Novo"))
        sync.caught_up(client, source)
        assert not sync.older(client, source)
    assert Message.objects.count() == 4
    assert (source.low, source.high) == (1, 4)
    assert not describe(account)["older"]


def test_a_folder_another_client_removes_after_it_was_listed_is_let_go(account, monkeypatch):
    name = f"Test {secrets.token_hex(4)}"
    with server() as client:
        client.create_folder(name)
    put(name, letter("Prolazno"))
    listed = sync.sources

    def sources(client, found):
        taken = listed(client, found)
        with server() as other:
            other.delete_folder(name)
        return taken

    monkeypatch.setattr(sync, "sources", sources)
    with imap(*SERVER, LOGIN) as client:
        sync.everything(client, account)
    assert Account.objects.get(pk=account.pk).state == "ready"
    assert not account.sources.filter(name=name).exists()


def test_a_message_from_inbox_arrives_while_the_account_is_followed(account):
    stop = threading.Event()
    following = threading.Thread(target=sync.keep, args=(account.pk, stop))
    following.start()
    subject = f"Stiglo {secrets.token_hex(4)}"
    try:
        wait_for(lambda: Account.objects.get(pk=account.pk).state == "ready")
        put("INBOX", letter(subject))
        wait_for(lambda: Message.objects.filter(subject=subject, folder__role="inbox").exists())
    finally:
        stop.set()
        following.join(timeout=sync.STEP + 5)
        with server() as client:
            client.select_folder("INBOX")
            client.delete_messages(client.search(["SUBJECT", subject]))
            client.expunge()
    assert not following.is_alive()


def test_a_refused_password_is_said_and_not_tried_again(account):
    account.secret = sealed.seal("mail", "wrong")
    account.save()
    with pytest.raises(sync.imap.Failed) as refused:
        sync.keep(account.pk, threading.Event())
    assert refused.value.code == "imap_login"
    sync.failed(account.pk, refused.value.code)
    assert account.pk not in sync.followed()


def test_a_search_answered_in_several_responses_finds_every_message(folder):
    with server() as client:
        for each in range(150):
            client.append(folder, letter(f"Broj {each}").as_bytes())
        client.select_folder(folder, readonly=True)
        found = sync.imap.searched(client, "ALL")
    assert len(found) == 150 and found == sorted(found)


def test_a_token_the_server_refuses_is_let_go_and_the_account_followed_still(account, monkeypatch):
    forgotten = []
    monkeypatch.setattr(
        sync.signin, "login", lambda found: (Login(LOGIN.username, token="refused"), None)
    )
    monkeypatch.setattr(sync.signin, "forget", lambda found: forgotten.append(found.pk))
    with pytest.raises(sync.imap.Failed) as refused:
        sync.keep(account.pk, threading.Event())
    assert refused.value.code == sync.REFUSED_TOKEN
    assert forgotten == [account.pk]
    sync.failed(account.pk, refused.value.code)
    assert account.pk in sync.followed()


def test_an_account_whose_token_was_refused_is_tried_again_until_it_signs_in(account, monkeypatch):
    tries = []

    def keep(account_id, stop):
        tries.append(account_id)
        if len(tries) == 1:
            raise sync.imap.Failed(sync.REFUSED_TOKEN)

    async def waited(seconds):
        pass

    monkeypatch.setattr(sync, "keep", keep)
    monkeypatch.setattr(sync, "sleep", waited)
    anyio.run(sync.follow, account.pk, anyio.CapacityLimiter(1))
    assert tries == [account.pk, account.pk]
    assert Account.objects.get(pk=account.pk).error == sync.REFUSED_TOKEN


def test_a_connection_ends_before_its_access_token_and_signs_in_again(account, monkeypatch):
    stop = threading.Event()
    logins = []

    def login(found):
        logins.append(found.pk)
        if len(logins) == 2:
            stop.set()
        return LOGIN, time.time()

    monkeypatch.setattr(sync.signin, "login", login)
    sync.keep(account.pk, stop)
    assert logins == [account.pk, account.pk]


def wait_for(condition, seconds: float = 15) -> None:
    until = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > until:
            raise AssertionError("waited in vain")
        time.sleep(0.2)
