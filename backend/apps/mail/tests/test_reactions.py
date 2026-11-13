import json
import secrets
from email import policy
from email.message import EmailMessage
from email.utils import make_msgid

import pytest

from apps.mail import sync, taking
from apps.mail.imap import imap
from apps.mail.models import Deleted, Folder, Message, Role, Source

from .mox import LOGIN, SERVER, kept_in_sent, letter, put, synced

GMAIL = "text/vnd.google.email-reaction+json"


def reaction(answered: str, part: tuple[str, str], name: str = "Ana Kovač") -> bytes:
    """A reaction as its client writes it: the emoji in `part`, a media type and its content."""
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = f"{name} <ana@example.com>"
    message["To"] = "mox@localhost"
    message["Subject"] = "Re: Ponuda"
    message["Message-ID"] = make_msgid(domain="example.com")
    message["In-Reply-To"] = answered
    message.set_content(f"{name} reacted via Gmail")
    media_type, content = part
    message.add_alternative(content, subtype=media_type.partition("/")[2])
    return message.as_bytes()


@pytest.fixture
def inbox(account):
    folder = Folder.objects.create(owner=account.owner, name="Inbox", role=Role.INBOX)
    return Source.objects.create(account=account, name="INBOX", folder=folder)


@pytest.mark.django_db
def test_a_reaction_shows_on_the_message_it_answers_and_not_as_a_message(client, account, inbox):
    client.force_login(account.owner)
    original = letter("Ponuda")
    answered = original["Message-ID"]
    thumbs = taking.took(inbox, reaction(answered, (GMAIL, '{"version": 1, "emoji": "👍"}')), {})
    listed = f"/api/mail/folders/{inbox.folder_id}/messages"
    # Older mail comes after newer: the reaction waits as a message of its own until it does.
    assert [each["id"] for each in client.get(listed).json()["messages"]] == [thumbs.pk]
    assert (thumbs.reaction, thumbs.in_reply_to, thumbs.seen) == ("👍", answered, True)

    taken = taking.took(inbox, original.as_bytes(), {})
    rfc = taking.took(inbox, _rfc9078(answered), {})
    unknown = taking.took(inbox, reaction(answered, (GMAIL, '{"version": "1", "emoji": "👍"}')), {})
    two = taking.took(inbox, reaction(answered, (GMAIL, '{"version": 1, "emoji": "👍👍"}')), {})
    assert (rfc.reaction, unknown.reaction, two.reaction) == ("❤️", "", "")
    shown = client.get(listed).json()
    assert {each["id"] for each in shown["messages"]} == {taken.pk, unknown.pk, two.pk}
    assert (shown["count"], shown["unseen"]) == (3, 3)
    [folder] = [
        each
        for each in client.get("/api/mail/accounts").json()["folders"]
        if each["id"] == inbox.folder_id
    ]
    assert (folder["count"], folder["unseen"]) == (3, 3)
    read = client.get(f"/api/mail/messages/{taken.pk}").json()
    assert read["reactions"] == [
        {"emoji": "👍", "people": ["Ana Kovač"], "mine": False},
        {"emoji": "❤️", "people": ["Iva Horvat"], "mine": False},
    ]
    assert read["reactable"] is True
    assert client.get(f"/api/mail/messages/{thumbs.pk}").json()["reactable"] is False

    chosen = f"/api/mail/folders/{inbox.folder_id}/chosen"
    marked = client.post(chosen, {"action": "seen", "where": {}}, content_type="application/json")
    assert marked.json() == {"changed": 3}
    where = {"messages": [taken.pk]}
    deleted = client.post(
        chosen, {"action": "delete", "where": where}, content_type="application/json"
    )
    assert deleted.json() == {"changed": 1}
    left = {each["id"] for each in client.get(listed).json()["messages"]}
    assert left == {unknown.pk, two.pk}
    assert Deleted.objects.filter(key__in=[taken.key, thumbs.key, rfc.key]).count() == 3


def _rfc9078(answered: str) -> bytes:
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = "Iva Horvat <iva@example.com>"
    message["To"] = "mox@localhost"
    message["Subject"] = "Re: Ponuda"
    message["Message-ID"] = make_msgid(domain="example.com")
    message["In-Reply-To"] = answered
    message.set_content("❤\r\n", disposition="reaction")
    return message.as_bytes()


@pytest.mark.django_db
def test_no_reaction_to_a_mailing_list_nor_to_mail_sent_to_many(client, account, inbox):
    client.force_login(account.owner)
    listed = letter("Novosti")
    listed["List-Id"] = "<novosti.example.com>"
    many = letter("Svima")
    many["Cc"] = ", ".join(f"osoba{n}@example.com" for n in range(20))
    blind = letter("Skriveno")
    blind.replace_header("To", "ana@example.com")
    for message in (listed, many, blind):
        taken = taking.took(inbox, message.as_bytes(), {})
        assert client.get(f"/api/mail/messages/{taken.pk}").json()["reactable"] is False
        refused = client.post(
            f"/api/mail/messages/{taken.pk}/reaction",
            {"emoji": "👍", "said": "Reakcija na vašu poruku:"},
            content_type="application/json",
        )
        assert (refused.status_code, refused.json()) == (400, {"error": "not_reactable"})


@pytest.mark.django_db(transaction=True)
@pytest.mark.xdist_group("mox")
def test_a_reaction_goes_to_everyone_the_message_went_to_as_gmail_makes_one(
    client, account, folder
):
    client.force_login(account.owner)
    with imap(*SERVER, LOGIN) as connection:
        sync.sources(connection, account)
    subject = f"Ponuda {secrets.token_hex(4)}"
    message = letter(subject)
    message["Cc"] = "Iva Horvat <iva@example.com>, mox@localhost"
    put(folder, message)
    synced(account, folder)
    copy = Message.objects.get()
    path = f"/api/mail/messages/{copy.pk}/reaction"

    def reacted(emoji: str):
        given = {"emoji": emoji, "said": "Reakcija na vašu poruku:"}
        return client.post(path, given, content_type="application/json")

    for wrong in ("👍👍", "a", ""):
        assert reacted(wrong).json() == {"error": "invalid_emoji"}
    answer = reacted("👍")
    assert answer.status_code == 200
    assert answer.json() == {
        "reactions": [{"emoji": "👍", "people": ["mox@localhost"], "mine": True}]
    }

    found = kept_in_sent(f"Re: {subject}")
    assert (found["To"], found["Cc"]) == (
        "Ana Kovač <ana@example.com>",
        "Iva Horvat <iva@example.com>",
    )
    assert found["In-Reply-To"] == message["Message-ID"]
    assert found.get_content_type() == "multipart/alternative"
    parts = found.get_payload()
    assert [part.get_content_type() for part in parts] == ["text/plain", GMAIL, "text/html"]
    assert json.loads(parts[1].get_content()) == {"version": 1, "emoji": "👍"}
    assert parts[0].get_content().strip() == "Reakcija na vašu poruku: 👍"
    kept = Message.objects.get(folder__role=Role.SENT)
    assert (kept.reaction, kept.reacts_to_id) == ("👍", copy.pk)
    assert not Message.objects.get(pk=copy.pk).answered
