"""The second factor of a sign-in with a password: an authenticator app's code (RFC 6238), or a
passkey of the user's while the installation offers passkeys. A user with an authenticator app is
always asked for it; the policy's `second_factor` holds everyone to having one. Someone signing in
at an outside provider (U1) shows the provider's second factor, not ours."""

import base64
import hashlib
import hmac
import struct
import time
from datetime import timedelta

from django.contrib.auth.signals import user_login_failed
from django.utils import timezone

from apps.core.api import Refused
from apps.core.sealed import opened

from . import sessions
from .models import Authenticator, Policy, User, policy

SEALED = "authenticator"
STEP = 30
DIGITS = 6
# The steps either side of now a code is still taken at: a phone's clock a little off, or a code
# typed just as it changed.
DRIFT = 1
# Who gave the right password and has the second factor still to show, for how long, and how many
# wrong codes they may type before the password is asked again.
PENDING = "second_factor"
PENDING_FOR = timedelta(minutes=5)
TRIES = 3
SECOND = "passkey_second"


def code_at(secret: bytes, step: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def secret_of(found: Authenticator) -> bytes:
    kept = opened(SEALED, found.secret)
    if kept is None:
        raise Refused(409, "authenticator_unreadable")
    return base64.b32decode(kept)


def taken(found: Authenticator, code) -> bool:
    """Whether the code is the app's at a step near now that no earlier code was taken at; the
    step is kept as used."""
    given = "".join(character for character in str(code or "") if character.isdigit())
    if len(given) != DIGITS:
        return False
    secret = secret_of(found)
    now = int(time.time()) // STEP
    for step in range(now - DRIFT, now + DRIFT + 1):
        if step > found.used_step and hmac.compare_digest(code_at(secret, step), given):
            found.used_step = step
            found.save(update_fields=["used_step"])
            return True
    return False


def confirmed(user: User) -> Authenticator | None:
    return Authenticator.objects.filter(user=user, confirmed_at__isnull=False).first()


def passkey_second(user: User, found: Policy) -> bool:
    return found.offers_passkeys() and user.passkeys.exists()


def offered_to(user: User) -> bool:
    """Whether a sign-in with the user's password waits for a second factor they have."""
    found = policy()
    return confirmed(user) is not None or (found.second_factor and passkey_second(user, found))


def owed(user: User, found: Policy | None = None) -> str | None:
    """What a session signed in with a password must add before anything else: the passkey the
    policy holds the user to, or a second factor they have none of."""
    found = found or policy()
    if found.holds(user) and not user.passkeys.exists():
        return "passkey"
    if found.second_factor and confirmed(user) is None and not passkey_second(user, found):
        return "factor"
    return None


def needs_last_passkey(user: User) -> bool:
    """Whether the policy keeps the user from removing their one passkey: it holds them to
    passkeys, or it is their only second factor."""
    found = policy()
    return found.holds(user) or (
        found.second_factor and found.offers_passkeys() and confirmed(user) is None
    )


def needs_authenticator(user: User) -> bool:
    """Whether the policy keeps the user from removing their authenticator app, their only
    second factor."""
    found = policy()
    return found.second_factor and not passkey_second(user, found)


def describe(found: Authenticator | None) -> dict:
    return {
        "authenticator": found is not None and found.confirmed_at is not None,
        "confirmed_at": found and found.confirmed_at,
    }


def settle(request) -> None:
    """What a session owes once the user added a passkey or an authenticator app."""
    if sessions.DUE not in request.session:
        return
    if still := owed(request.user):
        request.session[sessions.DUE] = still
    else:
        request.session.pop(sessions.DUE)


def pend(request, user: User) -> None:
    """The password was right: the session waits for the second factor before it signs in."""
    request.session[PENDING] = {"user": user.pk, "at": timezone.now().isoformat(), "tries": 0}


def pending(request) -> User | None:
    held = request.session.get(PENDING)
    if not held or not sessions.fresh(held["at"], PENDING_FOR):
        return None
    return User.objects.filter(pk=held["user"], is_active=True).first()


def offered(request) -> dict | None:
    """What the sign-in page asks for while a password waits for its second factor."""
    user = pending(request)
    if user is None:
        return None
    return {"code": confirmed(user) is not None, "passkey": passkey_second(user, policy())}


def failed(request, user: User) -> None:
    """A wrong second factor counts as a failed sign-in, which the guard against guessing holds
    like a wrong password."""
    user_login_failed.send(
        sender=__name__, credentials={"email": user.email, "username": user.email}, request=request
    )


def wrong(request, user: User) -> None:
    """A wrong second factor at sign-in: a few of them and the password is asked again."""
    held = request.session[PENDING]
    held["tries"] += 1
    if held["tries"] >= TRIES:
        request.session.pop(PENDING)
    else:
        request.session[PENDING] = held
    failed(request, user)
