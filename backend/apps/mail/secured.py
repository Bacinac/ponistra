"""Signed and encrypted mail (U5): the seal of a message for the browser to open or check, what it
opened read as any message is read, the body of a message the browser is about to seal, and the
certificates and public keys that encrypt to an address."""

import base64
import binascii
from datetime import datetime
from email import policy
from email.message import EmailMessage

from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.access import mailed
from apps.blobs import store
from apps.blobs.models import Blob
from apps.core.api import Refused, api, body

from . import imap, mime, safe, sealing, sending, sharing, taking, views
from .models import Key, Message

KEYS_SHOWN = 200


def _layer(message: Message) -> sealing.Layer:
    found = sealing.layer(taking.whole(message))
    if found is None:
        raise Refused(404, "not_sealed")
    return found


@api("GET")
@sharing.boxed(of=sharing.MESSAGE)
def sealed(request, pk):
    """What seals the message, for the browser to open or check with the keys only it holds."""
    return JsonResponse(_layer(views.loaded(request.user, pk)).described())


def _entity(request) -> bytes:
    """What the browser opened, as bytes of their own: a request this large is no JSON."""
    data = request.read(sealing.LARGEST + 1)
    if not data or len(data) > sealing.LARGEST:
        raise Refused(413 if data else 400, "invalid_entity")
    return data


def _shown(entity) -> dict:
    """The entity as a message shows: its HTML safe to show with its own images in it and nothing
    from elsewhere, as an opened seal may not tell anyone it was opened, or its text; and its
    files with their bytes, which exist nowhere but in the browser that opened them."""
    parsed = mime.parsed(entity)
    parts = mime.described(parsed)

    def carried(number: str, encoding: str) -> bytes:
        return imap.content(mime.raw(parsed, number) or b"", encoding)

    def shown_at(each: dict) -> str:
        data = base64.b64encode(carried(each["part"], each["encoding"])).decode()
        return f"data:{each['type']};base64,{data}"

    inline = {each["cid"]: shown_at(each) for each in parts["inline"] if each["type"] in safe.SHOWN}
    html = text = None
    remote = False
    if shown := parts.get("html"):
        markup = imap.decoded(
            mime.raw(parsed, shown["part"]) or b"", shown["encoding"], shown["charset"]
        )
        html, remote = safe.cleaned(markup, inline, None)
    elif shown := parts.get("plain"):
        text = imap.decoded(
            mime.raw(parsed, shown["part"]) or b"", shown["encoding"], shown["charset"]
        )
    files = [
        {
            "part": each["part"],
            "name": each["name"],
            "type": each["type"],
            "data": base64.b64encode(carried(each["part"], each["encoding"])).decode(),
        }
        for each in parts["attachments"]
    ]
    return {"html": html, "text": text if html is None else None, "remote": remote, "files": files}


@api("POST")
@sharing.boxed(of=sharing.MESSAGE)
def unsealed(request, pk):
    """What the browser opened of the message, read: another seal inside it for the browser to
    open or check in turn, or the message to show. Nothing of it is kept."""
    views.loaded(request.user, pk)
    entity = _entity(request)
    if inner := sealing.layer(entity):
        return JsonResponse({"layer": inner.described()})
    return JsonResponse(_shown(entity))


def _decoded(given, name: str, largest: int) -> bytes:
    if not isinstance(given, str):
        raise Refused(400, f"invalid_{name}")
    try:
        data = base64.b64decode(given, validate=True)
    except binascii.Error, ValueError:
        raise Refused(400, f"invalid_{name}") from None
    if not data or len(data) > largest:
        raise Refused(400, f"invalid_{name}")
    return data


def _address(given) -> str:
    if not isinstance(given, str):
        raise Refused(400, "invalid_address")
    try:
        return sending.address("", given).addr_spec.lower()
    except sending.Invalid:
        raise Refused(400, "invalid_address") from None


def describe_key(key: Key, user) -> dict:
    return {
        "id": key.pk,
        "kind": key.kind,
        "address": key.address,
        "fingerprint": key.fingerprint,
        "data": base64.b64encode(bytes(key.data)).decode(),
        "own": key.own,
        "mine": key.owner_id == user.pk,
        "expires_at": key.expires_at,
        "seen_at": key.seen_at,
    }


def _expires(given) -> datetime | None:
    if given is None:
        return None
    try:
        found = datetime.fromisoformat(given) if isinstance(given, str) else None
    except ValueError:
        found = None
    if found is None or found.tzinfo is None:
        raise Refused(400, "invalid_expires")
    return found


def _kept(user, data: dict) -> Key:
    kind = data.get("kind")
    fingerprint = data.get("fingerprint")
    if kind not in sealing.KINDS:
        raise Refused(400, "invalid_kind")
    if (
        not isinstance(fingerprint, str)
        or not 16 <= len(fingerprint) <= 64
        or not fingerprint.isalnum()
    ):
        raise Refused(400, "invalid_fingerprint")
    own = data.get("own", False)
    if not isinstance(own, bool):
        raise Refused(400, "invalid_own")
    key, _ = Key.objects.update_or_create(
        owner=user,
        kind=kind,
        address=_address(data.get("address")),
        fingerprint=fingerprint.lower(),
        defaults={
            "data": _decoded(data.get("data"), "data", 1024 * 1024),
            "own": own,
            "expires_at": _expires(data.get("expires_at")),
            "seen_at": timezone.now(),
        },
    )
    return key


@api("GET", "POST")
def keys(request):
    """The keys that encrypt to the addresses asked for: the user's own, those they met on signed
    messages, and those colleagues hold as their own; or one more the user met or made."""
    if request.method == "POST":
        return JsonResponse(
            describe_key(_kept(request.user, body(request)), request.user), status=201
        )
    asked = [_address(each) for each in request.GET.getlist("address")]
    found = Key.objects.filter(Q(owner=request.user) | Q(own=True))
    if asked:
        found = found.filter(address__in=asked)
    else:
        found = found.filter(owner=request.user)
    found = found.order_by("address", "kind", "-own", "-seen_at")[:KEYS_SHOWN]
    return JsonResponse({"keys": [describe_key(each, request.user) for each in found]})


@api("DELETE")
def key(request, pk):
    deleted, _ = Key.objects.filter(owner=request.user, pk=pk).delete()
    if not deleted:
        raise Refused(404, "not_found")
    return HttpResponse(status=204)


@api("POST")
def sealing_entity(request):
    """The body of the message the user wrote, made as sending makes it, for the browser to sign
    or encrypt before it goes (`views.sent` with `sealed`). A document shared by a link cannot
    go with it: the link would grant access before the message is sure to leave."""
    data = body(request)
    if mailed.given(data):
        raise Refused(400, "sealed_shared")
    given = views._sending(request.user, data, sharing=False)
    composed = sending.composed(
        given["account"],
        *given["people"],
        given["subject"],
        given["text"],
        given["answered"],
        given["files"],
        markup=given["markup"],
        related=given["related"],
    )
    entity = sealing.entity(composed)
    return JsonResponse({"entity": base64.b64encode(entity).decode()})


@api("POST")
def signed_entity(request):
    """The body the browser signed with its S/MIME signature beside it, as one entity for the
    browser to encrypt in turn: S/MIME signs and encrypts in two layers, the signature inside."""
    seal = sealed_given(body(request))
    if (seal.kind, seal.how) != (sealing.SMIME, sealing.SIGNED):
        raise Refused(400, "invalid_sealed")
    message = EmailMessage(policy=policy.SMTP)
    sealing.seal_into(message, seal)
    return JsonResponse({"entity": base64.b64encode(sealing.entity(message)).decode()})


def sealed_given(given) -> sealing.Seal:
    """The seal the browser made, as a message sending it carries it: blobs it uploaded, by their
    hashes."""
    if not isinstance(given, dict):
        raise Refused(400, "invalid_sealed")
    kind, how, micalg = given.get("kind"), given.get("how"), given.get("micalg", "")
    if kind not in sealing.KINDS or how not in (sealing.SIGNED, sealing.ENCRYPTED):
        raise Refused(400, "invalid_sealed")

    def read(name: str) -> bytes:
        sha256 = given.get(name)
        if not isinstance(sha256, str) or not Blob.objects.filter(pk=sha256).exists():
            raise Refused(400, "invalid_sealed")
        return store.path_of(sha256).read_bytes()

    if how == sealing.SIGNED:
        if not isinstance(micalg, str) or not sealing.MICALG.fullmatch(micalg):
            raise Refused(400, "invalid_sealed")
        entity = read("entity")
        if not entity.isascii():
            raise Refused(400, "invalid_sealed")
        return sealing.Seal(kind, how, read("data"), sealing.canonical(entity), micalg)
    return sealing.Seal(kind, how, read("data"))


def sealed_blobs(given) -> set[str]:
    """The hashes of the blobs a message waiting to leave sealed carries."""
    if not isinstance(given, dict):
        return set()
    return {given[name] for name in ("entity", "data") if isinstance(given.get(name), str)}
