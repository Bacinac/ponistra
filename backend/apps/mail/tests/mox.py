"""The test mail server of the dev and check stacks, and letters put on it."""

import email
import secrets
from contextlib import contextmanager
from email import policy
from email.message import EmailMessage
from email.utils import make_msgid

from imapclient import IMAPClient

from apps.mail import sync
from apps.mail.imap import Login, imap
from apps.mail.models import Account, Source

SERVER = ("mox", 1143, "none")
PASSWORD = "moxmoxmox"
LOGIN = Login("mox@localhost", password=PASSWORD)


def server() -> IMAPClient:
    client = IMAPClient("mox", 1143, ssl=False, timeout=10)
    client.login("mox@localhost", PASSWORD)
    return client


@contextmanager
def own_folder():
    """A folder of the test's own on the server, removed with what was put in it."""
    name = f"Test {secrets.token_hex(4)}"
    with server() as client:
        client.create_folder(name)
    try:
        yield name
    finally:
        with server() as client:
            client.delete_folder(name)


def put(folder: str, message: EmailMessage, flags=()) -> None:
    with server() as client:
        client.append(folder, message.as_bytes(), flags=flags)


def letter(subject: str, text: str = "Pozdrav iz Zagreba.") -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Ana Kovač <ana@example.com>"
    message["To"] = "mox@localhost"
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="example.com")
    message.set_content(text)
    return message


def synced(account: Account, name: str) -> Source:
    """The folder taken, new mail and old."""
    with imap(*SERVER, LOGIN) as client:
        for found in sync.sources(client, account):
            if found.name == name:
                sync.caught_up(client, found)
                while sync.older(client, found):
                    pass
                return found
    raise AssertionError(f"{name} was not listed")


def kept_in_sent(subject: str) -> email.message.EmailMessage:
    """The copy the account's Sent folder keeps of the message, taken off the server."""
    with server() as client:
        client.select_folder("Sent")
        [uid] = client.search(["SUBJECT", subject])
        found = client.fetch([uid], ["FLAGS", "BODY.PEEK[]"])[uid]
        client.delete_messages([uid])
        client.expunge()
    assert b"\\Seen" in found[b"FLAGS"]
    return email.message_from_bytes(found[b"BODY[]"], policy=policy.default)
