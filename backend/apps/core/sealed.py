"""Secrets the installation keeps in its database, sealed with its secret key. Each purpose seals
with a key of its own, so what one seals no other opens."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet(purpose: str) -> Fernet:
    # The product's old name, kept: another label opens none of the secrets sealed so far.
    digest = hashlib.sha256(f"scriptor {purpose} ".encode() + settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(digest.digest()))


def seal(purpose: str, secret: str) -> bytes:
    return _fernet(purpose).encrypt(secret.encode())


def opened(purpose: str, sealed: bytes) -> str | None:
    """The secret, none where the installation's secret key has changed since it was sealed."""
    try:
        return _fernet(purpose).decrypt(bytes(sealed)).decode()
    except InvalidToken:
        return None
