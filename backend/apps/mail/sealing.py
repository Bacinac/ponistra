"""S/MIME and OpenPGP around a message (RFC 8551, RFC 3156): what of a message is signed or
encrypted, cut from its bytes exactly as they were signed, and the message that carries what the
browser signed or encrypted. The keys never leave the browser: it decrypts, signs and checks
signatures, the server reads and builds the MIME around them."""

import base64
import re
import secrets
from dataclasses import dataclass
from email.message import EmailMessage, Message
from itertools import pairwise

from . import imap, mime

SMIME, PGP = "smime", "pgp"
KINDS = (SMIME, PGP)
SIGNED, ENCRYPTED = "signed", "encrypted"
SMIME_SIGNATURES, SMIME_CARRIED = mime.SMIME_SIGNATURES, mime.SMIME_CARRIED
PGP_SIGNATURE, PGP_ENCRYPTED = mime.PGP_SIGNATURE, mime.PGP_ENCRYPTED
ARMORED_MESSAGE = re.compile(rb"-----BEGIN PGP MESSAGE-----.*?-----END PGP MESSAGE-----", re.S)
ARMORED_SIGNED = re.compile(
    rb"-----BEGIN PGP SIGNED MESSAGE-----.*?-----END PGP SIGNATURE-----", re.S
)
MICALG = re.compile(r"(sha-(256|384|512)|pgp-sha(256|384|512))")
SEPARATOR = re.compile(rb"\r?\n\r?\n")
BARE_NEWLINE = re.compile(rb"(?<!\r)\n")
# A message no larger than what providers carry, sealed and in base64.
LARGEST = 64 * 1024 * 1024


@dataclass(frozen=True)
class Layer:
    """One seal around a message: a signature beside the bytes it signs (`content`, `signature`),
    or bytes only the browser can open (`data`): encrypted, or signed with the content inside."""

    kind: str
    how: str
    content: bytes = b""
    signature: bytes = b""
    data: bytes = b""
    inline: bool = False

    def described(self) -> dict:
        return {
            "kind": self.kind,
            "how": self.how,
            "inline": self.inline,
            "content": _base64(self.content),
            "signature": _base64(self.signature),
            "data": _base64(self.data),
        }


def _base64(data: bytes) -> str | None:
    return base64.b64encode(data).decode("ascii") if data else None


def _body(raw: bytes) -> bytes:
    found = SEPARATOR.search(raw)
    return raw[found.end() :] if found else b""


def _parts(raw: bytes, boundary: str) -> list[bytes]:
    """The bytes of each part of a multipart entity as they travel, each without the line end
    that belongs to the delimiter after it (RFC 2046, 5.1.1)."""
    body = _body(raw)
    delimiter = re.compile(
        rb"(?:\A|\r?\n)--"
        + re.escape(boundary.encode("ascii", "replace"))
        + rb"(--)?[ \t]*(?:\r?\n|\Z)"
    )
    marks = []
    for found in delimiter.finditer(body):
        marks.append(found)
        if found[1]:
            break
    return [body[start.end() : end.start()] for start, end in pairwise(marks)]


def _decoded(entity: bytes) -> bytes:
    """What an entity carries, its transfer encoding undone."""
    part = mime.parsed(entity)
    encoding = mime.header(part, "Content-Transfer-Encoding").lower() or "7bit"
    payload = part.get_payload()
    carried = payload.encode("ascii", "surrogateescape") if isinstance(payload, str) else b""
    return imap.content(carried, encoding)


def canonical(content: bytes) -> bytes:
    """The bytes as they were signed: every line ending CRLF (RFC 8551, 3.1.1)."""
    return BARE_NEWLINE.sub(b"\r\n", content)


def _signed(raw: bytes, message: Message) -> Layer | None:
    protocol = (message.get_param("protocol") or "").lower()
    kind = SMIME if protocol in SMIME_SIGNATURES else PGP if protocol == PGP_SIGNATURE else None
    boundary = message.get_boundary()
    if kind is None or not boundary:
        return None
    parts = _parts(raw, boundary)
    if len(parts) != 2:
        return None
    content, signature = parts
    return Layer(kind, SIGNED, content=canonical(content), signature=_decoded(signature))


def _encrypted(raw: bytes, message: Message) -> Layer | None:
    if (message.get_param("protocol") or "").lower() != PGP_ENCRYPTED:
        return None
    boundary = message.get_boundary()
    parts = _parts(raw, boundary) if boundary else []
    if len(parts) != 2:
        return None
    return Layer(PGP, ENCRYPTED, data=_decoded(parts[1]))


def _inline(message: Message) -> Layer | None:
    """A message whose text is a PGP block of its own, as clients sealed it before PGP/MIME."""
    shown = mime.described(message).get("plain")
    if shown is None:
        return None
    data = mime.raw(message, shown["part"]) or b""
    text = imap.content(data, shown["encoding"])
    if found := ARMORED_MESSAGE.search(text):
        return Layer(PGP, ENCRYPTED, data=found[0], inline=True)
    if found := ARMORED_SIGNED.search(text):
        return Layer(PGP, SIGNED, data=found[0], inline=True)
    return None


def layer(raw: bytes, message: Message | None = None) -> Layer | None:
    """The seal around a message or an entity, if it has one: S/MIME or PGP/MIME around the whole
    of it, or a PGP block written into its text. `message` is `raw` parsed, where it already is."""
    message = message or mime.parsed(raw)
    shape = message.get_content_type()
    if shape == "multipart/signed":
        return _signed(raw, message)
    if shape == "multipart/encrypted":
        return _encrypted(raw, message)
    if shape in SMIME_CARRIED:
        signed = (message.get_param("smime-type") or "").lower() == "signed-data"
        return Layer(SMIME, SIGNED if signed else ENCRYPTED, data=_decoded(raw))
    return _inline(message)


def sealed_state(raw: bytes, message: Message) -> str:
    """How a message is sealed as its list shows it: signed, encrypted, or neither."""
    found = layer(raw, message)
    return found.how if found else ""


@dataclass(frozen=True)
class Seal:
    """What the browser made of a message's entity: its signature (`entity` beside it) or the
    whole sealed (`data`), and the hash that signed it."""

    kind: str
    how: str
    data: bytes
    entity: bytes = b""
    micalg: str = ""


def entity(message: EmailMessage) -> bytes:
    """The body of a composed message as an entity of its own, its content headers with it: what
    a signature covers and what encryption hides."""
    inner = EmailMessage(policy=message.policy)
    for name in ("Content-Type", "Content-Transfer-Encoding", "Content-Disposition"):
        if (value := message.get(name)) is not None:
            inner[name] = value
    inner.set_payload(message.get_payload())
    flat = inner.as_bytes()
    return canonical(flat)


def _boundary(*inside: bytes) -> str:
    while True:
        chosen = f"=_sealed_{secrets.token_hex(12)}"
        if not any(chosen.encode() in each for each in inside):
            return chosen


def _wrapped(data: bytes) -> str:
    letters = base64.b64encode(data).decode("ascii")
    return "\r\n".join(letters[at : at + 76] for at in range(0, len(letters), 76))


def _multipart(message: EmailMessage, subtype: str, params: str, parts: list[bytes]) -> None:
    boundary = _boundary(*parts)
    del message["Content-Type"], message["Content-Transfer-Encoding"], message["MIME-Version"]
    message["MIME-Version"] = "1.0"
    message["Content-Type"] = f'multipart/{subtype}; {params}; boundary="{boundary}"'
    lines = [f"--{boundary}\r\n".encode() + part + b"\r\n" for part in parts]
    # A multipart payload given as text is written as it is (`Generator._handle_multipart`), so
    # the signed bytes travel exactly as they were signed.
    body = b"".join(lines) + f"--{boundary}--\r\n".encode()
    message.set_payload(body.decode("ascii"))


def seal_into(message: EmailMessage, seal: Seal) -> None:
    """Puts what the browser sealed in place of the message's body, its headers kept."""
    if seal.how == SIGNED and seal.kind == SMIME:
        signature = (
            b'Content-Type: application/pkcs7-signature; name="smime.p7s"\r\n'
            b"Content-Transfer-Encoding: base64\r\n"
            b'Content-Disposition: attachment; filename="smime.p7s"\r\n\r\n'
            + _wrapped(seal.data).encode()
        )
        params = f'protocol="application/pkcs7-signature"; micalg={seal.micalg}'
        _multipart(message, "signed", params, [seal.entity, signature])
    elif seal.how == SIGNED:
        signature = (
            b'Content-Type: application/pgp-signature; name="signature.asc"\r\n'
            b'Content-Disposition: attachment; filename="signature.asc"\r\n\r\n'
            + canonical(seal.data).rstrip(b"\r\n")
        )
        params = f'protocol="application/pgp-signature"; micalg={seal.micalg}'
        _multipart(message, "signed", params, [seal.entity, signature])
    elif seal.kind == SMIME:
        for name in (
            "Content-Type",
            "Content-Transfer-Encoding",
            "Content-Disposition",
            "MIME-Version",
        ):
            del message[name]
        message.set_content(
            seal.data,
            maintype="application",
            subtype="pkcs7-mime",
            cte="base64",
            disposition="attachment",
            filename="smime.p7m",
            params={"smime-type": "enveloped-data", "name": "smime.p7m"},
        )
    else:
        version = b"Content-Type: application/pgp-encrypted\r\n\r\nVersion: 1"
        carried = (
            b'Content-Type: application/octet-stream; name="encrypted.asc"\r\n'
            b'Content-Disposition: inline; filename="encrypted.asc"\r\n\r\n'
            + canonical(seal.data).rstrip(b"\r\n")
        )
        _multipart(message, "encrypted", 'protocol="application/pgp-encrypted"', [version, carried])
