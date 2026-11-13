"""A whole message as the provider sends it, read the way IMAP describes it: its parts by their
IMAP numbers, each as its transfer encoding carries it; and the message cut into what is kept of
it: its bytes without the base64 of its files, and each file's bytes on their own."""

import base64
import binascii
from email import message_from_bytes
from email.header import Header, decode_header
from email.message import Message
from email.policy import compat32

from .imap import words

# Gmail's emoji reaction to the message it answers; RFC 9078 marks its own by the disposition.
REACTION = "text/vnd.google.email-reaction+json"
# The transfer encodings whose bytes are ASCII and which `get_payload(decode=True)` would undo.
ENCODED = {"base64", "quoted-printable", "x-uuencode", "uuencode", "uue", "x-uue"}
SMIME_SIGNATURES = {"application/pkcs7-signature", "application/x-pkcs7-signature"}
SMIME_CARRIED = {"application/pkcs7-mime", "application/x-pkcs7-mime"}
PGP_SIGNATURE = "application/pgp-signature"
PGP_ENCRYPTED = "application/pgp-encrypted"


def parsed(raw: bytes) -> Message:
    # An attached message is written out again, with the line ends it came with.
    policy = compat32.clone(linesep="\r\n") if b"\r\n" in raw else compat32
    return message_from_bytes(raw, policy=policy)


def header(message: Message, name: str) -> str:
    """The header's text, its encoded words decoded."""
    value = message.get(name)
    if isinstance(value, Header):
        # Bytes beyond ASCII written into the header as they are: UTF-8, as mail clients read it.
        chunks = (chunk for chunk, _ in decode_header(value))
        value = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks)
        value = value.decode("utf-8", "replace")
    return words(value)


def _parts(message: Message):
    """Each leaf part with its IMAP number, and whether it sits in a multipart/related."""

    def walk(part: Message, number: str, related: bool):
        # An attached message is one part, as IMAP lists it, however many it holds.
        if part.is_multipart() and part.get_content_type() != "message/rfc822":
            inside = related or part.get_content_subtype() == "related"
            for index, child in enumerate(part.get_payload(), 1):
                yield from walk(child, f"{number}.{index}" if number else str(index), inside)
            return
        yield part, number or "1", related

    yield from walk(message, "", False)


def _carried(part: Message) -> bytes:
    if part.get_content_type() == "message/rfc822" and part.is_multipart():
        return part.get_payload(0).as_bytes()
    payload = part.get_payload()
    if not isinstance(payload, str):
        return b""
    encoding = header(part, "Content-Transfer-Encoding").lower()
    if encoding in ENCODED:
        return payload.encode("ascii", "replace")
    # Undecoded, an 8bit part comes back as text in its charset; decoded, as the bytes it was.
    return part.get_payload(decode=True)


def raw(message: Message, number: str) -> bytes | None:
    """The part's bytes as its transfer encoding carries them."""
    for part, at, _ in _parts(message):
        if at == number:
            return _carried(part)
    return None


def placed(found: dict, leaf: dict, related: bool) -> None:
    """Puts the leaf part where `described` lists it: the body, an image the HTML shows, or an
    attachment."""
    if not leaf["attached"] and (leaf["type"] == REACTION or leaf["reaction"]):
        found.setdefault(
            "reaction", {key: leaf[key] for key in ("part", "type", "charset", "encoding")}
        )
        if leaf["type"] == REACTION:
            return
    body = leaf["type"] in ("text/plain", "text/html") and not leaf["attached"]
    role = "plain" if leaf["type"] == "text/plain" else "html"
    if body and not leaf["name"] and role not in found:
        found[role] = {key: leaf[key] for key in ("part", "charset", "encoding")}
    elif related and leaf["cid"] and leaf["type"].startswith("image/") and not leaf["attached"]:
        found["inline"].append({key: leaf[key] for key in ("part", "cid", "type", "encoding")})
    elif leaf["size"]:
        found["attachments"].append(
            {key: leaf[key] for key in ("part", "name", "type", "size", "encoding", "cid")}
        )


def seals(message: Message) -> set[str]:
    """The IMAP numbers of the parts a seal is made of (`sealing`), which are no files to offer:
    the signature beside signed content, and what an encrypted message carries in its place."""
    shape = message.get_content_type()
    payload = message.get_payload()
    if shape == "multipart/signed" and isinstance(payload, list) and len(payload) == 2:
        signature = payload[1].get_content_type()
        return {"2"} if signature in (*SMIME_SIGNATURES, PGP_SIGNATURE) else set()
    if (
        shape == "multipart/encrypted"
        and (message.get_param("protocol") or "").lower() == PGP_ENCRYPTED
    ):
        return {"1", "2"}
    if shape in SMIME_CARRIED:
        return {"1"}
    return set()


def described(message: Message) -> dict:
    """Where the message's plain text, HTML, attachments, the images its HTML shows and the
    emoji reaction it is are, by their IMAP part numbers; the parts of a seal are none of them."""
    found: dict = {"attachments": [], "inline": []}
    sealed = seals(message)
    for part, number, related in _parts(message):
        if number in sealed:
            continue
        disposition = header(part, "Content-Disposition").split(";", 1)[0].strip().lower()
        leaf = {
            "part": number,
            "type": part.get_content_type(),
            "charset": (part.get_content_charset() or "").lower(),
            "encoding": header(part, "Content-Transfer-Encoding").lower() or "7bit",
            "size": len(_carried(part)),
            "cid": header(part, "Content-ID").strip("<>"),
            "name": words(part.get_filename() or ""),
            "attached": disposition == "attachment",
            "reaction": disposition == "reaction",
        }
        placed(found, leaf, related)
    return found


def encoded(data: bytes, line: int, newline: bytes, ended: bool) -> bytes:
    letters = base64.b64encode(data)
    lines = [letters[at : at + line] for at in range(0, len(letters), line)]
    return newline.join(lines) + (newline if ended else b"")


def cut(raw: bytes, message: Message, numbers: set[str]) -> tuple[bytes, dict[str, dict]]:
    """The message without the base64 of the parts numbered `numbers`, and where each was cut
    from. A part is cut only where encoding its bytes again gives back exactly what was there,
    so that `whole` makes the message as it came."""
    pieces, cuts, at, removed = [], {}, 0, 0
    for part, number, _ in _parts(message):
        encoding = header(part, "Content-Transfer-Encoding").lower()
        payload = part.get_payload()
        if number not in numbers or encoding != "base64" or not isinstance(payload, str):
            continue
        carried = payload.encode("ascii", "surrogateescape")
        newline = b"\r\n" if b"\r\n" in carried else b"\n"
        line = len(carried.split(newline, 1)[0])
        start = raw.find(carried, at) if line else -1
        if start < 0:
            continue
        try:
            data = base64.b64decode(carried)
        except binascii.Error, ValueError:
            continue
        ended = carried.endswith(newline)
        if encoded(data, line, newline, ended) != carried:
            continue
        pieces.append(raw[at:start])
        cuts[number] = {
            "offset": start - removed,
            "line": line,
            "newline": newline.decode(),
            "ended": ended,
            "data": data,
        }
        at = start + len(carried)
        removed += len(carried)
    pieces.append(raw[at:])
    return b"".join(pieces), cuts


def whole(kept: bytes, cuts: list[tuple[int, bytes, int, bytes, bool]]) -> bytes:
    """The message as it came: what was kept of it, each cut part's offset, bytes and lines put
    back where `cut` took them from."""
    pieces, at = [], 0
    for offset, data, line, newline, ended in sorted(cuts, key=lambda each: each[0]):
        pieces += [kept[at:offset], encoded(data, line, newline, ended)]
        at = offset
    pieces.append(kept[at:])
    return b"".join(pieces)
