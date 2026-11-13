"""App passwords (D15, S4): what a phone's own apps sign in with over CardDAV, where a passkey
cannot reach. Each is random, named for its device, shown once and kept only as its digest;
removing it signs that device out."""

import hashlib
import secrets
from datetime import timedelta

from django.core import signing
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.push import notices
from apps.push.models import Notice

from .accounts import text
from .models import AppPassword, User

NAME = 150
# Letters and digits no one takes for one another when typing them from the screen.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
LENGTH = 16
GROUP = 4
# How often a device's use of its password is noted.
NOTED = timedelta(minutes=10)
PAIRING = signing.TimestampSigner(salt="ponistra.device-pairing")
PAIRING_AGE = timedelta(minutes=10)
PHONE = "Android"


def digest(secret: str) -> str:
    plain = "".join(secret.split()).replace("-", "").lower()
    return hashlib.sha256(plain.encode()).hexdigest()


def made() -> str:
    plain = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return "-".join(plain[at : at + GROUP] for at in range(0, LENGTH, GROUP))


def holder(secret: str, email: str | None = None) -> AppPassword | None:
    """The app password of an active user, of the one with this email where it is given."""
    found = AppPassword.objects.select_related("user").filter(digest=digest(secret)).first()
    if found is None or not found.user.is_active:
        return None
    if email is not None and found.user.email != email.strip().lower():
        return None
    now = timezone.now()
    if found.used_at is None or found.used_at < now - NOTED:
        AppPassword.objects.filter(pk=found.pk).update(used_at=now)
    return found


def user_of(email: str, secret: str) -> User | None:
    """The active user whose app password it is, signing in with their email."""
    found = holder(secret, email)
    return found.user if found else None


def describe(password: AppPassword) -> dict:
    return {
        "id": password.pk,
        "name": password.name,
        "created_at": password.created_at,
        "used_at": password.used_at,
    }


def told(user: int, name: str) -> None:
    notices.tell([user], Notice.Kind.SECURITY, {"event": "app_password", "name": name})


@api("GET", "POST", confirmed=("POST",))
def app_passwords(request):
    """The user's app passwords, and a new one, whose secret this answer alone shows."""
    if request.method == "POST":
        name = text(body(request), "name", NAME, required=True)
        secret = made()
        kept = AppPassword.objects.create(user=request.user, name=name, digest=digest(secret))
        told(request.user.pk, name)
        entries.wrote(Kind.APP_PASSWORD_ADDED, request=request, subject=request.user, name=name)
        return JsonResponse({**describe(kept), "password": secret}, status=201)
    kept = request.user.app_passwords.order_by("created_at", "pk")
    return JsonResponse({"app_passwords": [describe(each) for each in kept]})


@api("DELETE")
def app_password(request, pk):
    found = AppPassword.objects.filter(pk=pk, user=request.user).first()
    if found is None:
        raise Refused(404, "not_found")
    found.delete()
    entries.wrote(Kind.APP_PASSWORD_REMOVED, request=request, subject=request.user, name=found.name)
    return HttpResponse(status=204)


@api("GET", "PATCH", "DELETE", device=True)
def device(request):
    """The app password the phone's own app signs in with (D26): whose it is, the phone's name
    as the app gives it, and signing the phone out."""
    held = request.device
    if held is None:
        raise Refused(403, "app_password_required")
    if request.method == "DELETE":
        held.delete()
        entries.wrote(Kind.APP_PASSWORD_REMOVED, request=request, subject=held.user, name=held.name)
        return HttpResponse(status=204)
    if request.method == "PATCH":
        held.name = text(body(request), "name", NAME, required=True)
        held.save(update_fields=["name"])
    user = held.user
    return JsonResponse({"email": user.email, "name": user.get_full_name(), "device": held.name})


@api("POST", confirmed=("POST",))
def pairing(request):
    """A code with which the phone's own app claims a password of its own (D26), from a link on the
    phone or the QR code it scans. The password waits unused and unknown until the claim tells it,
    so it never travels in a link or a browser's history."""
    kept = AppPassword.objects.create(user=request.user, name=PHONE, digest=digest(made()))
    return JsonResponse({**describe(kept), "code": PAIRING.sign(str(kept.pk))}, status=201)


# The app holds no session a forged request could ride on; the code alone stands for the user.
@csrf_exempt
@api("POST", signed_in=False)
def claim(request):
    """The password a pairing code stands for, told once and within ten minutes of its making."""
    try:
        pk = PAIRING.unsign(text(body(request), "code", 200, required=True), max_age=PAIRING_AGE)
    except signing.BadSignature:
        raise Refused(400, "invalid_code") from None
    secret = made()
    claimed = AppPassword.objects.filter(pk=pk, used_at=None, user__is_active=True).update(
        digest=digest(secret), used_at=timezone.now()
    )
    if not claimed:
        raise Refused(400, "invalid_code")
    paired = AppPassword.objects.select_related("user").get(pk=pk)
    told(paired.user_id, PHONE)
    entries.wrote(
        Kind.APP_PASSWORD_ADDED, request=request, actor=paired.user, subject=paired.user, name=PHONE
    )
    return JsonResponse({"password": secret}, status=201)
