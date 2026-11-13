import email
import secrets
from email import policy

import pytest
from asgiref.sync import async_to_sync

from apps.blobs.tests.uploads import uploaded
from apps.core import sealed
from apps.documents.tests.test_views import PNG
from apps.mail import sending, sync, taking
from apps.mail.imap import Failed, Login, imap
from apps.mail.models import Account, Draft, Message
from apps.users.models import User

from . import eas
from .eas import everything, item
from .mox import LOGIN, SERVER, kept_in_sent, letter, put, server, synced

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.xdist_group("mox")]

PDF = b"%PDF-1.7\n%test"


@pytest.fixture
def writer(client, account):
    client.force_login(account.owner)
    with imap(*SERVER, LOGIN) as connection:
        sync.sources(connection, account)
    return client


def sent(client, **given):
    return client.post("/api/mail/send", given, content_type="application/json")


def test_a_new_message_goes_out_through_smtp_and_is_kept_in_sent(writer, account):
    subject = f"Ponuda {secrets.token_hex(4)}"
    sha256 = uploaded(writer, PDF)["sha256"]
    logo = uploaded(writer, PNG)["sha256"]
    answer = sent(
        writer,
        account=account.pk,
        to=[{"name": "Ana Kovač", "address": "ana@example.com"}, {"address": "iva@example.com"}],
        bcc=[{"name": "", "address": "tajna@example.com"}],
        subject=subject,
        html=(
            "<p>Cijena je <strong>100 €</strong>.</p><p></p><hr>"
            '<p style="line-height: 1.5">'
            '<span style="font-size: 14pt; position: fixed">Rok</span></p>'
            '<p><a href="https://primjer.hr">Ponuda</a> <img src="/api/mail/inline/'
            f'{logo}" alt="logo"></p><script>alert(1)</script>'
        ),
        files=[{"sha256": sha256, "name": "Ponuda Šibenik.pdf"}],
    )
    assert answer.json() == {"refused": [], "kept": True}
    mine = Message.objects.get(folder__role="sent", subject=subject)
    assert (mine.seen, mine.account, mine.files.get(inline=False).name) == (
        True,
        account,
        "Ponuda Šibenik.pdf",
    )
    assert b"Bcc: tajna@example.com" in taking.whole(mine)
    found = kept_in_sent(subject)
    assert found["From"] == "mox@localhost"
    assert found["To"] == "Ana Kovač <ana@example.com>, iva@example.com"
    assert found["Bcc"] == "tajna@example.com"
    assert found["Message-ID"].endswith("@localhost>") and found["In-Reply-To"] is None
    body = found.get_body(("plain",)).get_content()
    assert body.replace("\r\n", "\n") == "Cijena je 100 €.\n\nRok\nPonuda <https://primjer.hr>\n"
    shown = found.get_body(("html",)).get_content()
    assert '<p style="margin:0;">Cijena je <strong>100 €</strong>.</p>' in shown
    assert '<p style="margin:0;"><br></p><hr>' in shown
    assert '<p style="margin:0;line-height:1.5"><span style="font-size:14pt">Rok</span>' in shown
    assert '<span style="font-size:14pt">Rok</span>' in shown
    assert "alert" not in shown and "position" not in shown and logo not in shown
    [image] = [part for part in found.walk() if part.get_content_type() == "image/png"]
    assert image.get_content() == PNG
    assert f'src="cid:{image["Content-ID"].strip("<>")}"' in shown
    [attachment] = found.iter_attachments()
    assert (attachment.get_filename(), attachment.get_content()) == ("Ponuda Šibenik.pdf", PDF)


def test_a_token_the_sending_server_refuses_is_given_up_for_a_new_one(account, monkeypatch):
    tokens = iter(["refused", "fresh"])
    forgotten, tried = [], []

    def smtp_sent(server, login, message):
        tried.append(login.token)
        if login.token == "refused":
            raise Failed("smtp_oauth_login")
        return []

    monkeypatch.setattr(
        sending.signin, "login", lambda found: (Login(found.username, token=next(tokens)), None)
    )
    monkeypatch.setattr(sending.signin, "forget", lambda found: forgotten.append(found.pk))
    monkeypatch.setattr(sending, "smtp_sent", smtp_sent)
    message = email.message.EmailMessage()
    message["From"] = account.address
    async_to_sync(sending.delivered)(account, message)
    assert tried == ["refused", "fresh"]
    assert forgotten == [account.pk]


def test_a_message_is_refused_before_it_goes_out(writer, account):
    other = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    stranger = Account.objects.create(owner=other, address="ana@example.com", username="ana")
    given = {"account": account.pk, "subject": "Ponuda", "html": "<p>Pozdrav</p>"}
    assert sent(writer, **given).json() == {"error": "no_recipients"}
    injected = {"name": "Ana\r\nBcc: x@y.test", "address": "a@b.test"}
    for wrong in ("a@b.test", [{"address": "ana"}], [injected]):
        assert sent(writer, **given, to=wrong).json() == {"error": "invalid_recipient"}
    to = [{"address": "a@b.test"}]
    assert sent(writer, **given | {"to": to, "account": stranger.pk}).status_code == 404
    assert sent(writer, **given, to=to, files=[{"sha256": "0" * 64, "name": "x"}]).json() == {
        "error": "invalid_files"
    }
    assert sent(writer, **given, to=to, **{"as": "reply"}).json() == {"error": "invalid_as"}
    assert sent(writer, **given, to=to, heading=["Ana je napisala:"]).json() == {
        "error": "invalid_heading"
    }


def test_a_reply_goes_to_the_sender_in_the_thread_and_marks_the_message_answered_here(
    writer, account, folder
):
    message = letter("Ponuda")
    message["Cc"] = "Iva Horvat <iva@example.com>, mox@localhost"
    message["References"] = "<prva@example.com>"
    put(folder, message)
    synced(account, folder)
    copy = Message.objects.get()
    url = f"/api/mail/messages/{copy.pk}/draft"
    drafted = writer.get(url, {"as": "reply"}).json()
    assert drafted == {
        "account": account.pk,
        "to": [{"name": "Ana Kovač", "address": "ana@example.com"}],
        "cc": [],
        "unnamed": [],
        "subject": "Re: Ponuda",
        "attachments": [],
    }
    everyone = writer.get(url, {"as": "all"}).json()
    assert (everyone["to"], everyone["cc"]) == (
        [{"name": "Ana Kovač", "address": "ana@example.com"}],
        [{"name": "Iva Horvat", "address": "iva@example.com"}],
    )
    subject = f"Re: Ponuda {secrets.token_hex(4)}"
    # What an outside agent drafted waits apart from the message, which is read once and kept,
    # so a draft made after it was opened still reaches the user; it goes once dropped or answered.
    dropped = Draft.objects.create(owner=account.owner, message=copy, way="all", text="Ne.")
    assert writer.delete(f"/api/mail/drafts/{dropped.pk}").status_code == 204
    assert writer.delete(f"/api/mail/drafts/{dropped.pk}").status_code == 404
    Draft.objects.create(owner=account.owner, message=copy, way="reply", text="Hvala.")
    [waiting] = writer.get("/api/mail/drafts").json()["drafts"]
    assert (waiting["way"], waiting["text"], waiting["by"]) == ("reply", "Hvala.", None)
    assert waiting["message"] == {
        "id": copy.pk,
        "folder": copy.folder_id,
        "subject": "Ponuda",
        "sender": copy.sender,
    }
    assert "drafts" not in writer.get(f"/api/mail/messages/{copy.pk}").json()
    answer = sent(
        writer,
        account=account.pk,
        to=drafted["to"],
        subject=subject,
        html="<p>Hvala.</p>",
        heading=["Ana Kovač je napisala:"],
        original=copy.pk,
        **{"as": "reply"},
    )
    assert answer.json() == {"refused": [], "kept": True}
    assert writer.get("/api/mail/drafts").json()["drafts"] == []
    found = kept_in_sent(subject)
    body = found.get_body(("plain",)).get_content().replace("\r\n", "\n")
    assert body == "Hvala.\n\nAna Kovač je napisala:\n> Pozdrav iz Zagreba.\n"
    shown = found.get_body(("html",)).get_content()
    assert "<div>Ana Kovač je napisala:</div><blockquote" in shown
    assert "Pozdrav iz Zagreba." in shown.partition("<blockquote")[2]
    assert found["In-Reply-To"] == message["Message-ID"]
    assert found["References"] == f"<prva@example.com> {message['Message-ID']}"
    copy.refresh_from_db()
    assert copy.answered
    with server() as client:
        client.select_folder(folder, readonly=True)
        [flags] = client.get_flags(client.search("ALL")).values()
    assert b"\\Answered" not in flags


def test_a_forward_carries_the_files_the_user_kept(writer, account, folder):
    message = letter("Ugovor")
    message.add_attachment(PDF, maintype="application", subtype="pdf", filename="Ugovor.pdf")
    put(folder, message)
    synced(account, folder)
    copy = Message.objects.get()
    drafted = writer.get(f"/api/mail/messages/{copy.pk}/draft", {"as": "forward"}).json()
    assert (drafted["to"], drafted["subject"]) == ([], "Fwd: Ugovor")
    [attachment] = drafted["attachments"]
    subject = f"Fwd: Ugovor {secrets.token_hex(4)}"
    answer = sent(
        writer,
        account=account.pk,
        to=[{"address": "iva@example.com"}],
        subject=subject,
        html="",
        heading=["---------- Proslijeđena poruka ----------"],
        original=copy.pk,
        carried=[attachment["part"]],
        **{"as": "forward"},
    )
    assert answer.status_code == 200
    found = kept_in_sent(subject)
    assert found.get_body(("plain",)).get_content().strip().endswith("Pozdrav iz Zagreba.")
    assert found["In-Reply-To"] is None
    [carried] = found.iter_attachments()
    assert (carried.get_filename(), carried.get_content()) == ("Ugovor.pdf", PDF)
    copy.refresh_from_db()
    assert not copy.answered


def test_activesync_sends_whole_and_from_another_account(client, settings):
    settings.MAIL_PLAIN_HOSTS = {"127.0.0.1"}
    box = eas.Mailbox()
    served = eas.serve(box)
    owner = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    account = Account.objects.create(
        owner=owner,
        address=eas.USER,
        username=eas.USER,
        secret=sealed.seal("mail", eas.PASSWORD),
        protocol=Account.Protocol.ACTIVESYNC,
        activesync_host=f"127.0.0.1:{served.server_address[1]}",
        device="5c1d" * 8,
    )
    other = Account.objects.create(
        owner=owner,
        address="ivo@example.org",
        username=eas.USER,
        secret=sealed.seal("mail", eas.PASSWORD),
        protocol=Account.Protocol.ACTIVESYNC,
        activesync_host=account.activesync_host,
        device="7e2f" * 8,
    )
    client.force_login(owner)
    try:
        message = letter("Ponuda")
        message.replace_header("From", "Iva Horvat <iva@example.com>")
        message.add_attachment(PDF, maintype="application", subtype="pdf", filename="Ponuda.pdf")
        box.put("1", item("Ponuda", message))
        everything(account)
        original = Message.objects.get()
        drafted = client.get(f"/api/mail/messages/{original.pk}/draft", {"as": "reply"}).json()
        assert drafted["to"] == [{"name": "Iva Horvat", "address": "iva@example.com"}]
        given = {"to": drafted["to"], "subject": "Re: Ponuda", "html": "<p>Hvala.</p>"}
        replied = sent(client, account=account.pk, original=original.pk, **given, **{"as": "reply"})
        assert replied.json() == {"refused": [], "kept": True}
        sent(client, account=other.pk, original=original.pk, **given, **{"as": "reply"})
        forwarded = sent(
            client,
            account=account.pk,
            original=original.pk,
            to=[{"address": "iva@example.com"}],
            subject="Fwd: Ponuda",
            html="",
            carried=["2"],
            **{"as": "forward"},
        )
        assert forwarded.status_code == 200
        reply, from_other, forward = box.sent
        found = email.message_from_bytes(reply, policy=policy.default)
        assert (found["From"], found["In-Reply-To"]) == (eas.USER, message["Message-ID"])
        assert "\n> Pozdrav iz Zagreba." in found.get_body(("plain",)).get_content()
        assert email.message_from_bytes(from_other)["From"] == "ivo@example.org"
        [attachment] = email.message_from_bytes(forward, policy=policy.default).iter_attachments()
        assert attachment.get_content() == PDF
        assert len(box.items["2"]) == 3
        original.refresh_from_db()
        assert original.answered
        assert Message.objects.filter(folder__role="sent").count() == 3
        everything(account)
        assert Message.objects.filter(folder__role="sent").count() == 3
    finally:
        served.shutdown()
        served.server_close()


def test_a_message_begun_is_kept_unsent_until_it_goes_out(writer, account):
    sha256 = uploaded(writer, PDF)["sha256"]
    begun = writer.post(
        "/api/mail/unsent",
        {"account": account.pk, "subject": "Ponuda", "html": "<p>Cijena</p>"},
        content_type="application/json",
    )
    assert begun.status_code == 201, begun.json()
    pk = begun.json()["id"]
    assert begun.json()["to"] == [] and begun.json()["files"] == []
    changed = writer.put(
        f"/api/mail/unsent/{pk}",
        {
            "account": account.pk,
            "to": [{"name": "Ana", "address": "ana@example.com"}],
            "subject": "Ponuda za Končar",
            "html": "<p>Cijena je 100 €.</p>",
            "files": [{"sha256": sha256, "name": "Ponuda.pdf", "size": 14}],
        },
        content_type="application/json",
    )
    assert changed.json()["subject"] == "Ponuda za Končar"
    (listed,) = writer.get("/api/mail/unsent").json()["unsent"]
    assert (listed["id"], listed["account"], listed["to"], listed["files"]) == (
        pk,
        account.pk,
        [{"name": "Ana", "address": "ana@example.com"}],
        [{"sha256": sha256, "name": "Ponuda.pdf", "size": 14}],
    )
    refused = writer.put(
        f"/api/mail/unsent/{pk}",
        {"account": account.pk, "to": [{"address": "nije adresa"}]},
        content_type="application/json",
    )
    assert refused.json()["error"] == "invalid_recipient"

    subject = f"Ponuda {secrets.token_hex(4)}"
    answer = sent(
        writer,
        account=account.pk,
        to=[{"address": "ana@example.com"}],
        subject=subject,
        html="<p>Cijena je 100 €.</p>",
        unsent=pk,
    )
    assert answer.json() == {"refused": [], "kept": True}
    assert writer.get("/api/mail/unsent").json() == {"unsent": []}
    kept_in_sent(subject)


def test_another_users_unsent_message_is_not_found(client, account):
    other = User.objects.create_user("drugi@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(account.owner)
    pk = client.post(
        "/api/mail/unsent", {"account": account.pk}, content_type="application/json"
    ).json()["id"]
    client.force_login(other)
    assert client.get(f"/api/mail/unsent/{pk}").status_code == 404
    assert client.delete(f"/api/mail/unsent/{pk}").status_code == 404
    response = client.post(
        "/api/mail/unsent", {"account": account.pk}, content_type="application/json"
    )
    assert response.status_code == 404
