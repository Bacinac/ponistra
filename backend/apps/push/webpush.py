"""Web Push as the browsers take it (RFC 8030, 8291 and 8292), with cryptography and PyJWT alone:
the installation's key pair, a notice encrypted for one subscription and posted to its push
service with the installation's signature."""

import base64
import os
import time
from urllib.parse import urlsplit

import httpx2
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.db import IntegrityError

from apps.users.models import User

from .models import Keys, Subscription

CURVE = ec.SECP256R1()
RECORD = 4096
# How long the signature vouches for the installation, the most a push service accepts.
SIGNED = 12 * 3600
WAIT = 15


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def _private(raw: bytes) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(raw, "big"), CURVE)


def keys() -> Keys:
    try:
        return Keys.objects.get(pk=1)
    except Keys.DoesNotExist:
        key = ec.generate_private_key(CURVE)
        private = key.private_numbers().private_value.to_bytes(32, "big")
        try:
            return Keys.objects.create(
                pk=1, private=private, public=_public_bytes(key.public_key())
            )
        except IntegrityError:
            return Keys.objects.get(pk=1)


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypted(
    p256dh: bytes, auth: bytes, payload: bytes, *, sender: bytes | None = None, salt: bytes = b""
) -> bytes:
    """The payload as RFC 8291 encrypts it for a subscription's keys, in one aes128gcm record;
    the sender's key and the salt are drawn unless given, as the RFC's test vector gives them."""
    key = _private(sender) if sender else ec.generate_private_key(CURVE)
    salt = salt or os.urandom(16)
    receiver = ec.EllipticCurvePublicKey.from_encoded_point(CURVE, p256dh)
    sender_public = _public_bytes(key.public_key())
    shared = key.exchange(ec.ECDH(), receiver)
    ikm = _hkdf(auth, shared, b"WebPush: info\x00" + p256dh + sender_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    header = salt + RECORD.to_bytes(4, "big") + bytes([len(sender_public)]) + sender_public
    return header + AESGCM(cek).encrypt(nonce, payload + b"\x02", None)


def contact() -> str:
    """Whom a push service may write to about the installation: its first administrator."""
    found = User.objects.filter(is_staff=True).order_by("pk").values_list("email", flat=True)
    return f"mailto:{found.first() or 'administrator@localhost'}"


def authorization(endpoint: str, signing: Keys, contact: str, *, now: float | None = None) -> str:
    """The VAPID header a push service checks against the key the subscription was made with."""
    parts = urlsplit(endpoint)
    claims = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int(now or time.time()) + SIGNED,
        "sub": contact,
    }
    token = jwt.encode(claims, _private(bytes(signing.private)), algorithm="ES256")
    return f"vapid t={token}, k={b64(bytes(signing.public))}"


async def posted(
    client: httpx2.AsyncClient,
    subscription: Subscription,
    signing: Keys,
    contact: str,
    payload: bytes,
    *,
    ttl: int,
    urgency: str,
    topic: str,
) -> int:
    """Sends the payload to the subscription's push service; the status it answered."""
    headers = {
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl),
        "Urgency": urgency,
        "Authorization": authorization(subscription.endpoint, signing, contact),
    }
    if topic:
        headers["Topic"] = topic
    body = encrypted(bytes(subscription.p256dh), bytes(subscription.auth), payload)
    answer = await client.post(subscription.endpoint, content=body, headers=headers)
    return answer.status_code
