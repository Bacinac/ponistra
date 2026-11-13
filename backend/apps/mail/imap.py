"""The account's servers as PONISTRA reaches them, and the text a message's parts carry."""

import base64
import html
import quopri
import re
import smtplib
import socket
import ssl
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from logging import getLogger
from typing import NamedTuple

import nh3
from django.conf import settings
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError, LoginError
from imapclient.tls import IMAP4_TLS

from .models import Security

TIMEOUT = 30
# How long one of a server's addresses may take over TLS before the next is tried.
HANDSHAKE = 10
TEXT = 256 * 1024
PREVIEW = 200
BLOCKS = re.compile(r"<(?:br|/p|/div|/tr|/li|/h[1-6]|/blockquote)\b", re.IGNORECASE)
log = getLogger(__name__)


class Failed(Exception):
    """Why a server could not be reached or would not let the account in, as `<protocol>_<why>`."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Login(NamedTuple):
    """Who signs in to a server: with a password, or with an OAuth access token through XOAUTH2."""

    username: str
    password: str = ""
    token: str = ""

    def xoauth2(self) -> str:
        return f"user={self.username}\1auth=Bearer {self.token}\1\1"


def _plain_allowed(host: str, security: str, protocol: str) -> None:
    if security == Security.NONE and host not in settings.MAIL_PLAIN_HOSTS:
        raise Failed(f"{protocol}_plain")


def encrypted(host: str, port: int, context: ssl.SSLContext) -> ssl.SSLSocket:
    """The first of the server's addresses that completes the TLS handshake. Behind one name some
    of Outlook.com's servers stall in the handshake while the others answer at once, and the
    socket module moves to the next address only when TCP itself fails."""
    stalled = []
    for family, kind, proto, _, address in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(HANDSHAKE)
            sock.connect(address)
            reached = context.wrap_socket(sock, server_hostname=host)
        except ssl.SSLError:
            sock.close()
            raise
        except OSError as lost:
            sock.close()
            stalled.append(f"{address[0]} {lost}")
            continue
        if stalled:
            log.warning("mail: %s:%s answered past %s", host, port, "; ".join(stalled))
        reached.settimeout(TIMEOUT)
        return reached
    raise OSError("; ".join(stalled) or "no address")


class _Encrypted(IMAP4_TLS):
    def _create_socket(self, timeout: float | None = None) -> socket.socket:
        return encrypted(self.host, self.port, self.ssl_context)


class _Client(IMAPClient):
    # IMAPClient opens its TLS socket only through this method; overriding it is the one way in.
    def _create_IMAP4(self):
        if self.ssl:
            return _Encrypted(self.host, self.port, self.ssl_context)
        return super()._create_IMAP4()


def connected(host: str, port: int, security: str, login: Login) -> IMAPClient:
    """A connection signed in to the account's mail server; whoever opens it logs it out."""
    _plain_allowed(host, security, "imap")
    try:
        client = _Client(
            host,
            port,
            ssl=security == Security.TLS,
            ssl_context=ssl.create_default_context(),
            timeout=TIMEOUT,
        )
        if security == Security.STARTTLS:
            client.starttls(ssl.create_default_context())
    except ssl.SSLError as refused:
        log.warning("mail: %s:%s refused TLS: %s", host, port, refused)
        raise Failed("imap_tls") from None
    except (OSError, IMAPClientError) as lost:
        log.warning("mail: %s:%s cannot be reached: %s", host, port, lost)
        raise Failed("imap_unreachable") from None
    try:
        if login.token:
            client.oauth2_login(login.username, login.token)
        else:
            client.login(login.username, login.password)
        client.normalise_times = False
    except LoginError as refused:
        closed(client)
        if login.token:
            log.warning("mail: %s refused the token of %s: %s", host, login.username, refused)
        raise Failed("imap_oauth_login" if login.token else "imap_login") from None
    except (OSError, IMAPClientError) as lost:
        closed(client)
        log.warning("mail: %s:%s dropped the sign-in: %s", host, port, lost)
        raise Failed("imap_unreachable") from None
    return client


def searched(client: IMAPClient, *criteria: str) -> list[int]:
    """The UIDs in the selected folder that meet the criteria. A server may answer in several
    SEARCH responses (mox gives one to each hundred), which IMAPClient's own search refuses."""
    found = client._raw_command_untagged(b"SEARCH", [each.encode() for each in criteria])
    return [int(uid) for line in found if line for uid in line.split()]


def closed(client: IMAPClient) -> None:
    try:
        client.logout()
    except OSError, IMAPClientError:
        with suppress(OSError):
            client.shutdown()


@contextmanager
def imap(host: str, port: int, security: str, login: Login):
    client = connected(host, port, security, login)
    try:
        yield client
    finally:
        closed(client)


@contextmanager
def smtp(host: str, port: int, security: str, login: Login):
    """A connection signed in to the account's sending server."""
    _plain_allowed(host, security, "smtp")
    try:
        if security == Security.TLS:
            server = smtplib.SMTP_SSL(
                host, port, context=ssl.create_default_context(), timeout=TIMEOUT
            )
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
            if security == Security.STARTTLS:
                server.starttls(context=ssl.create_default_context())
    except ssl.SSLError:
        raise Failed("smtp_tls") from None
    except OSError, smtplib.SMTPException:
        raise Failed("smtp_unreachable") from None
    try:
        try:
            if login.token:
                server.ehlo_or_helo_if_needed()
                # A refused token is answered with a challenge, which takes an empty reply.
                server.auth(
                    "XOAUTH2",
                    lambda challenge=None: login.xoauth2() if challenge is None else "",
                )
            else:
                server.login(login.username, login.password)
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected) as refused:
            if login.token:
                log.warning("mail: %s refused the token of %s: %s", host, login.username, refused)
            # Gmail answers a refused password by closing the connection.
            raise Failed("smtp_oauth_login" if login.token else "smtp_login") from None
        except smtplib.SMTPException:
            raise Failed("smtp_unreachable") from None
        yield server
    finally:
        try:
            server.quit()
        except OSError, smtplib.SMTPException:
            pass


def smtp_checked(host: str, port: int, security: str, login: Login) -> None:
    """Signs in to the account's sending server, so that a wrong one is found when it is
    connected rather than at the first message."""
    with smtp(host, port, security, login):
        pass


def words(raw: bytes | str | None) -> str:
    """A header's text, its encoded words decoded."""
    if not raw:
        return ""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        return str(make_header(decode_header(text))).strip()
    except HeaderParseError, LookupError, ValueError:
        return text.strip()


def references(raw: bytes | str | None) -> str:
    """The Message-IDs a References header names, oldest first."""
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", "replace")
    return " ".join(re.findall(r"<[^<>\s]+>", raw or ""))


def aware(moment: datetime | None) -> datetime | None:
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


def content(data: bytes, encoding: str) -> bytes:
    """A part's bytes as its transfer encoding carried them; a part cut short may end inside an
    encoded group, which is dropped."""
    if encoding == "base64":
        letters = re.sub(rb"[^A-Za-z0-9+/=]", b"", data)
        return base64.b64decode(letters[: len(letters) // 4 * 4])
    if encoding == "quoted-printable":
        return quopri.decodestring(data)
    return data


def decoded(data: bytes, encoding: str, charset: str) -> str:
    """A part's text."""
    data = content(data, encoding)
    try:
        return data.decode(charset or "utf-8", "replace")
    except LookupError:
        return data.decode("utf-8", "replace")


def plain(markup: str) -> str:
    """The text an HTML body reads as, a line for each block."""
    text = html.unescape(nh3.clean(BLOCKS.sub(lambda tag: "\n" + tag[0], markup), tags=set()))
    lines = (re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def preview(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:PREVIEW]
