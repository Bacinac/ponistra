"""The keys the installation signs with and the tokens it signs: an application's ID token, and
the access token it shows when it asks who signed in."""

import base64
import hashlib
import secrets
from datetime import timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.utils import timezone

from apps.core import sealed

from .models import Key

SEALED = "identity key"
ALGORITHM = "RS256"
LIFETIME = timedelta(hours=1)
ACCESS_TYPE = "at+jwt"

_opened: dict[str, rsa.RSAPrivateKey] = {}


def issuer() -> str:
    return f"{settings.PUBLIC_URL}/api/identity"


def _private(key: Key) -> rsa.RSAPrivateKey | None:
    if key.kid not in _opened:
        pem = sealed.opened(SEALED, key.sealed)
        if pem is None:
            return None
        _opened[key.kid] = serialization.load_pem_private_key(pem.encode(), None)
    return _opened[key.kid]


def _keys() -> list[tuple[Key, rsa.RSAPrivateKey]]:
    """The keys that open, newest first. One sealed before the secret key changed opens no more
    and goes, and a key is made where none is left."""
    found, lost = [], []
    for key in Key.objects.order_by("-created_at", "-pk"):
        private = _private(key)
        if private is None:
            lost.append(key.pk)
        else:
            found.append((key, private))
    if lost:
        Key.objects.filter(pk__in=lost).delete()
    if not found:
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        key = Key.objects.create(kid=secrets.token_urlsafe(12), sealed=sealed.seal(SEALED, pem))
        _opened[key.kid] = private
        found.append((key, private))
    return found


def published() -> list[dict]:
    jwks = []
    for key, private in _keys():
        public = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
        # RFC 7517 has a key say what it is for by `use` or by `key_ops`, not by both.
        public.pop("key_ops", None)
        jwks.append({**public, "kid": key.kid, "use": "sig", "alg": ALGORITHM})
    return jwks


def _signed(claims: dict, **headers) -> str:
    key, private = _keys()[0]
    now = timezone.now()
    stamped = {"iss": issuer(), "iat": now, "exp": now + LIFETIME, **claims}
    return jwt.encode(stamped, private, algorithm=ALGORITHM, headers={"kid": key.kid, **headers})


def access(client_id: str, user, scopes: list[str]) -> str:
    return _signed(
        {
            "sub": str(user.pk),
            "aud": issuer(),
            "client_id": client_id,
            "scope": " ".join(scopes),
            "jti": secrets.token_urlsafe(16),
        },
        typ=ACCESS_TYPE,
    )


def identity(client_id: str, claims: dict, nonce: str, access_token: str) -> str:
    half = hashlib.sha256(access_token.encode()).digest()[:16]
    at_hash = base64.urlsafe_b64encode(half).decode().rstrip("=")
    return _signed(
        {**claims, "aud": client_id, "at_hash": at_hash, **({"nonce": nonce} if nonce else {})}
    )


def verified(token: str) -> dict | None:
    """An access token's claims where this installation signed it and it holds."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        return None
    if header.get("typ") != ACCESS_TYPE:
        return None
    keys = {key.kid: private for key, private in _keys()}
    private = keys.get(header.get("kid"))
    if private is None:
        return None
    try:
        return jwt.decode(
            token,
            private.public_key(),
            algorithms=[ALGORITHM],
            audience=issuer(),
            issuer=issuer(),
            options={"require": ["exp", "sub", "client_id"]},
        )
    except jwt.InvalidTokenError:
        return None
