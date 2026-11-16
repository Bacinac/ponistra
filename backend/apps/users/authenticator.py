"""The user's authenticator app (RFC 6238), the second factor of their sign-in with a password:
a new secret for it to scan, which its first code confirms, and its removal."""

import base64
import secrets
from urllib.parse import quote, urlencode

from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.core.api import Refused, api, body
from apps.core.sealed import seal
from apps.journal import entries
from apps.journal.entries import Kind
from apps.push import notices
from apps.push.models import Notice

from .factors import DIGITS, SEALED, describe, needs_authenticator, settle, taken
from .models import Authenticator


@api("GET", "POST", "DELETE", due=True, confirmed=("POST", "DELETE"))
def authenticator(request):
    """The user's authenticator app: whether they have one, a new secret for it to scan, which
    its first code confirms, and its removal."""
    user = request.user
    found = Authenticator.objects.filter(user=user).first()
    kept = found is not None and found.confirmed_at is not None
    if request.method == "POST":
        if kept:
            raise Refused(409, "authenticator_exists")
        secret = base64.b32encode(secrets.token_bytes(20)).decode()
        Authenticator.objects.update_or_create(user=user, defaults={"secret": seal(SEALED, secret)})
        label = quote(f"Ponistra:{user.email}")
        asked_for = urlencode({"secret": secret, "issuer": "Ponistra", "digits": DIGITS})
        return JsonResponse(
            {"secret": secret, "uri": f"otpauth://totp/{label}?{asked_for}"}, status=201
        )
    if request.method == "DELETE":
        if found is None:
            raise Refused(404, "not_found")
        if kept and needs_authenticator(user):
            raise Refused(400, "last_factor")
        found.delete()
        if kept:
            entries.wrote(Kind.AUTHENTICATOR_REMOVED, request=request, subject=user)
        return HttpResponse(status=204)
    return JsonResponse(describe(found))


@api("POST", due=True)
def confirmed(request):
    """The authenticator app's first code, which makes it the user's second factor."""
    found = Authenticator.objects.filter(user=request.user, confirmed_at__isnull=True).first()
    if found is None:
        raise Refused(404, "not_found")
    if not taken(found, body(request).get("code")):
        raise Refused(400, "invalid_code")
    found.confirmed_at = timezone.now()
    found.save(update_fields=["confirmed_at"])
    settle(request)
    entries.wrote(Kind.AUTHENTICATOR_ADDED, request=request, subject=request.user)
    notices.tell([request.user.pk], Notice.Kind.SECURITY, {"event": "authenticator"})
    return JsonResponse(describe(found))
