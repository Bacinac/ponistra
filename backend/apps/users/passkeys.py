"""Passkeys (D15, S1): WebAuthn credentials the device keeps and unlocks with the person's
fingerprint, face or PIN. They are discoverable, so the browser offers them without an email."""

from django.contrib.auth import login as start_session
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json_dict
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.push import notices
from apps.push.models import Notice

from . import factors, sessions
from .accounts import text, without_passkeys
from .ceremony import answered, asking, handle, refused, relying_party
from .models import Passkey, policy
from .views import signed

NAME = 150
CREATING = "passkey_creating"
SIGNING_IN = "passkey_signing_in"


def offered() -> None:
    if not policy().offers_passkeys():
        raise Refused(403, "passkeys_off")


def describe(passkey: Passkey) -> dict:
    return {
        "id": passkey.pk,
        "name": passkey.name,
        "created_at": passkey.created_at,
        "used_at": passkey.used_at,
    }


@api("POST", due=True, confirmed=("POST",))
def creating(request):
    """The options the browser makes the user's next passkey with, one to each device."""
    _, rp_id = relying_party(request)
    user = request.user
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Ponistra",
        user_id=handle(user),
        user_name=user.email,
        user_display_name=user.get_full_name() or user.email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(kept.credential)) for kept in user.passkeys.all()
        ],
    )
    request.session[CREATING] = bytes_to_base64url(options.challenge)
    return JsonResponse(options_to_json_dict(options))


@api("GET", "POST", due=True, confirmed=("POST",))
def passkeys(request):
    """The user's passkeys, and a new one from what the browser made with the last options."""
    if request.method == "POST":
        data = body(request)
        name = text(data, "name", NAME, required=True)
        given = request.session.pop(CREATING, None)
        if given is None:
            raise refused("invalid_passkey", "the session holds no challenge")
        expected = base64url_to_bytes(given)
        origin, rp_id = relying_party(request)
        try:
            verified = verify_registration_response(
                credential=data.get("credential"),
                expected_challenge=expected,
                expected_rp_id=rp_id,
                expected_origin=origin,
                require_user_verification=True,
            )
        except (WebAuthnException, ValueError, TypeError) as error:
            raise refused("invalid_passkey", error) from None
        try:
            with transaction.atomic():
                made = Passkey.objects.create(
                    user=request.user,
                    credential=verified.credential_id,
                    public_key=verified.credential_public_key,
                    sign_count=verified.sign_count,
                    name=name,
                )
        except IntegrityError:
            raise Refused(409, "passkey_exists") from None
        factors.settle(request)
        entries.wrote(Kind.PASSKEY_ADDED, request=request, subject=request.user, name=name)
        notices.tell([request.user.pk], Notice.Kind.SECURITY, {"event": "passkey", "name": name})
        return JsonResponse(describe(made), status=201)
    kept = request.user.passkeys.order_by("created_at")
    return JsonResponse({"passkeys": [describe(passkey) for passkey in kept]})


@api("PATCH", "DELETE", confirmed=("DELETE",))
def passkey(request, pk):
    found = Passkey.objects.filter(pk=pk, user=request.user).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        if request.user.passkeys.count() == 1 and factors.needs_last_passkey(request.user):
            raise Refused(400, "last_passkey")
        found.delete()
        without_passkeys(request.user)
        entries.wrote(Kind.PASSKEY_REMOVED, request=request, subject=request.user, name=found.name)
        return HttpResponse(status=204)
    found.name = text(body(request), "name", NAME, required=True)
    found.save(update_fields=["name"])
    return JsonResponse(describe(found))


@api("POST", signed_in=False)
def signing_in(request):
    """The options the browser signs in with, offering whichever passkey the device keeps."""
    offered()
    return asking(request, SIGNING_IN)


@api("POST", signed_in=False)
def sign_in(request):
    offered()
    found = answered(request, SIGNING_IN)
    start_session(request, found.user, backend="django.contrib.auth.backends.ModelBackend")
    sessions.started(request, "passkey")
    return JsonResponse(signed(request))
