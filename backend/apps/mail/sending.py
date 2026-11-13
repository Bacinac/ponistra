"""A message the user writes, made as mail clients make it and sent through the account it goes
from: its SMTP server, with the provider's copy put in its Sent folder, or ActiveSync, whose
server keeps that copy itself."""

import html
import json
import re
import secrets
import smtplib
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from functools import partial

from django.utils import timezone
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

from apps.core.asyncdb import database, waited

from . import imap, signin, taking
from .activesync import sync as activesync_sync
from .activesync.client import Session
from .activesync.wbxml import element as e
from .imap import Failed, Login
from .models import Account, Message, Source

REPLY, ALL, FORWARD = "reply", "all", "forward"
WAYS = (REPLY, ALL, FORWARD)
# Providers whose SMTP server puts what it sends in the account's Sent folder itself.
KEEPS_SENT = {"imap.gmail.com", "outlook.office365.com"}
LINK = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
# Outlook draws HTML without a font of its own in Times New Roman, and a paragraph with the gap of
# a blank line under it; the composer's paragraph is a line, and an empty one without margins
# would have no height but for a break.
LOOK = "font-family:Arial,Helvetica,sans-serif;font-size:11pt;line-height:1.15"
PARAGRAPH = re.compile(r'<p(?: style="([^"]*)")?>(</p>)?')
CITED = 'style="margin:0 0 0 0.8ex;border-left:1px solid #ccc;padding-left:1ex"'
PREFIXES = {REPLY: "Re: ", ALL: "Re: ", FORWARD: "Fwd: "}
ANSWERED = re.compile(r"^\s*(re|aw|sv|odg|odgovor)\s*:", re.IGNORECASE)
FORWARDED = re.compile(r"^\s*(fwd?|wg|tr|proslijeđeno|proslijedi)\s*:", re.IGNORECASE)
# A server answers a message sent with nothing, or some with a status of success.
SENT = {"", "1"}
# Woken by a message handed over to leave later, whose time may have come already.
LATER = "mail_later"


class Invalid(ValueError):
    pass


def address(name: str, given: str) -> Address:
    """The person the user writes to as mail names them; Invalid unless mail reaches the
    address."""
    local, _, domain = given.strip().rpartition("@")
    if not local or not domain or not local.isascii() or not re.fullmatch(r"[^\s@<>]+", local):
        raise Invalid(given)
    if re.search(r"[\r\n]", name):
        raise Invalid(given)
    try:
        domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise Invalid(given) from None
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", domain):
        raise Invalid(given)
    return Address(display_name=name.strip(), addr_spec=f"{local}@{domain}")


def subject(given: str, way: str) -> str:
    prefixed = (FORWARDED if way == FORWARD else ANSWERED).match(given)
    return given if prefixed else PREFIXES[way] + given


def recipients(message: Message, way: str, own: set[str]) -> tuple[list[dict], list[dict]]:
    """Who a reply goes to: whom the message asks replies to go to, else its sender; to answer
    all, also everyone it went to but the user's own accounts."""
    if way == FORWARD:
        return [], []
    to = message.reply_to or [message.sender]
    cc = []
    if way == ALL:
        to = [*to, *message.to]
        cc = message.cc
    seen = set(own)
    kept = []
    for people in (to, cc):
        kept.append([])
        for each in people:
            address = (each.get("address") or "").lower()
            if address and address not in seen:
                seen.add(address)
                kept[-1].append(each)
    # A reply to the user's own message goes where that message went.
    if not kept[0] and not kept[1]:
        kept[0] = [each for each in message.to if each.get("address")]
    return kept[0], kept[1]


def quoted(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def plain(markup: str) -> str:
    """The text the composer's HTML reads as, for a client that shows no HTML: an item of a list
    after a dash, a link's address after its words."""

    def linked(found: re.Match) -> str:
        address = html.unescape(found[1]).removeprefix("mailto:")
        return found[2] if imap.plain(found[2]) == address else f"{found[2]} &lt;{found[1]}&gt;"

    return imap.plain(LINK.sub(linked, markup).replace("<li>", "<li>- "))


def heading_html(heading: list[str]) -> str:
    """The lines saying what the message answers or forwards, as its HTML draws them."""
    return f"<div>{'<br>'.join(html.escape(line) for line in heading)}</div>"


def page(own: str, heading: list[str], quote: str | None, forward: bool) -> str:
    """The HTML the message travels with: what the user wrote and, under the lines saying what it
    answers or forwards, that message's own HTML."""
    body = PARAGRAPH.sub(
        lambda found: f'<p style="margin:0;{found[1] or ""}">{"<br></p>" if found[2] else ""}', own
    )
    if quote is not None:
        cited = quote if forward else f'<blockquote type="cite" {CITED}>{quote}</blockquote>'
        body += f"<br>{heading_html(heading)}{cited}"
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        f'<body><div style="{LOOK}">{body}</div></body></html>'
    )


def alternative(own: str, heading: list[str], quote: str | None, forward: bool) -> str:
    """The same as text: the message answered quoted line by line, the one forwarded as it is."""
    written = plain(own)
    if quote is None:
        return written
    return "\n".join([written, "", *heading, quote if forward else quoted(quote)])


def composed(
    account: Account,
    to: list[Address],
    cc: list[Address],
    bcc: list[Address],
    title: str,
    text: str,
    answered: Message | None,
    files: list[tuple[str, str, bytes]],
    *,
    markup: str = "",
    related: list[tuple[str, str, bytes]] = (),
) -> EmailMessage:
    """The message as it travels; `answered` is the one it replies to, `files` the name, media
    type and bytes of each file it carries. With `markup` it goes as HTML beside the text, `related`
    the content id, media type and bytes of each image the HTML shows."""
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = Address(display_name=account.name, addr_spec=account.address)
    if to:
        message["To"] = to
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    message["Subject"] = title
    message["Date"] = format_datetime(timezone.localtime())
    message["Message-ID"] = make_msgid(domain=account.address.rpartition("@")[2])
    if answered is not None and answered.message_id:
        message["In-Reply-To"] = answered.message_id
        message["References"] = " ".join(filter(None, [answered.references, answered.message_id]))
    message.set_content(text, cte="quoted-printable")
    if markup:
        message.add_alternative(markup, subtype="html", cte="quoted-printable")
        shown = message.get_payload()[1]
        for cid, media_type, data in related:
            maintype, _, subtype = media_type.partition("/")
            shown.add_related(
                data, maintype=maintype, subtype=subtype, cid=f"<{cid}>", disposition="inline"
            )
    for name, media_type, data in files:
        maintype, _, subtype = media_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return message


def reacted(
    account: Account, to: list[Address], cc: list[Address], answered: Message, emoji: str, said: str
) -> EmailMessage:
    """A reaction to the message as Gmail makes one: the emoji for a client that shows reactions,
    between the text and the HTML that say it to one that does not (`reactions`)."""
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = Address(display_name=account.name, addr_spec=account.address)
    if to:
        message["To"] = to
    if cc:
        message["Cc"] = cc
    message["Subject"] = subject(answered.subject, REPLY)
    message["Date"] = format_datetime(timezone.localtime())
    message["Message-ID"] = make_msgid(domain=account.address.rpartition("@")[2])
    message["In-Reply-To"] = answered.message_id
    message["References"] = " ".join(filter(None, [answered.references, answered.message_id]))
    message.set_content(f"{said} {emoji}", cte="quoted-printable")
    reaction = json.dumps({"version": 1, "emoji": emoji}, ensure_ascii=False)
    message.add_alternative(reaction, subtype="vnd.google.email-reaction+json", cte="base64")
    markup = f'<p style="{LOOK}">{html.escape(said)} {emoji}</p>'
    message.add_alternative(markup, subtype="html", cte="quoted-printable")
    return message


def imip(
    account: Account, to: list[Address], title: str, text: str, ics: str, method: str
) -> EmailMessage:
    """A message carrying what iMIP says of a meeting: the text for whoever reads it as mail, the
    calendar part for their calendar."""
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = Address(display_name=account.name, addr_spec=account.address)
    message["To"] = to
    message["Subject"] = title
    message["Date"] = format_datetime(timezone.localtime())
    message["Message-ID"] = make_msgid(domain=account.address.rpartition("@")[2])
    message.set_content(text, cte="quoted-printable")
    message.add_alternative(
        ics, subtype="calendar", charset="utf-8", params={"method": method}, cte="base64"
    )
    return message


def smtp_sent(server: tuple, login: Login, message: EmailMessage) -> list[str]:
    """Sends the message and answers the recipients the server refused while taking the others;
    the Bcc header is left out of what travels."""
    sender = message["From"].addresses[0].addr_spec
    try:
        with imap.smtp(*server, login) as client:
            refused = client.send_message(message, from_addr=sender)
    except smtplib.SMTPRecipientsRefused:
        raise Failed("mail_recipients") from None
    except smtplib.SMTPSenderRefused:
        raise Failed("mail_sender") from None
    except smtplib.SMTPDataError as refused:
        raise Failed("mail_too_large" if refused.smtp_code == 552 else "mail_refused") from None
    except OSError, smtplib.SMTPException:
        raise Failed("smtp_unreachable") from None
    return sorted(refused)


def kept(client: IMAPClient, folder: str, message: EmailMessage) -> None:
    client.append(folder, message.as_bytes(), flags=[b"\\Seen"])


def activesync_sent(client: Session, message: EmailMessage) -> None:
    """Sends the message whole, In-Reply-To and References and files and all."""
    answer = client.command(
        "SendMail",
        e(
            "ComposeMail:SendMail",
            e("ComposeMail:ClientId", secrets.token_hex(16)),
            e("ComposeMail:SaveInSentItems"),
            e("ComposeMail:Mime", message.as_bytes()),
        ),
    )
    if answer.text("Status") not in SENT:
        raise Failed("mail_refused")


def _appended(account: Account, login: Login, folder: str, message: EmailMessage) -> None:
    server = (account.imap_host, account.imap_port, account.imap_security)
    with imap.imap(*server, login) as client:
        kept(client, folder, message)


def _activesync_sent(account: Account, password: str, message: EmailMessage) -> None:
    with activesync_sync.session(account, password) as client:
        activesync_sent(client, message)


async def delivered(account: Account, message: EmailMessage) -> tuple[list[str], bool]:
    """Sends the message from the account: the recipients its server refused, and whether the
    provider keeps its copy in the account's Sent folder."""
    login, _ = await waited(partial(signin.login, account))
    if account.protocol == Account.Protocol.ACTIVESYNC:
        await waited(partial(_activesync_sent, account, login.password, message))
        return [], True
    server = (account.smtp_host, account.smtp_port, account.smtp_security)
    try:
        refused = await waited(partial(smtp_sent, server, login, message))
    except Failed as failed:
        if failed.code != "smtp_oauth_login":
            raise
        signin.forget(account)
        login, _ = await waited(partial(signin.login, account))
        refused = await waited(partial(smtp_sent, server, login, message))
    if account.imap_host in KEEPS_SENT:
        return refused, True
    sent = await database(lambda: account.sources.filter(kind=Source.Kind.SENT).first())()
    if sent is None:
        return refused, False
    try:
        await waited(partial(_appended, account, login, sent.name, message))
    except Failed, IMAPClientError, OSError:
        return refused, False
    return refused, True


def recorded(account: Account, message: EmailMessage, answered: Message | None) -> Message:
    """Keeps what was sent in the user's Sent folder, and the message it answered as answered."""
    kept = taking.sent(account, message.as_bytes())
    if answered is not None:
        Message.objects.filter(pk=answered.pk).update(answered=True)
    return kept
