"""Passkeys (D15, S1): WebAuthn credentials the device keeps and unlocks with the person's
fingerprint, face or PIN. They are discoverable, so the browser offers them without an email."""

from logging import getLogger
from urllib.parse import urlsplit

from django.contrib.auth import login as start_session
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    options_to_json_dict,
    parse_authentication_credential_json,
)
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

from . import sessions
from .accounts import text, without_passkeys
from .models import Passkey, User
from .views import policy, signed

NAME = 150
CREATING = "passkey_creating"
SIGNING_IN = "passkey_signing_in"

log = getLogger(__name__)


def refused(error: str, why: object) -> Refused:
    log.warning("Passkey refused, %s: %s", error, why)
    return Refused(400, error)


def relying_party(request) -> tuple[str, str]:
    """The origin the browser signs for, and its host. A POST reaches a view only once the CSRF
    check has found that origin to be this site's own."""
    origin = request.headers.get("Origin")
    if not origin:
        raise Refused(400, "invalid_origin")
    return origin, urlsplit(origin).hostname


def handle(user: User) -> bytes:
    return str(user.pk).encode()


def challenge(request, key: str) -> bytes:
    """The challenge the options gave, good for one answer."""
    given = request.session.pop(key, None)
    if given is None:
        raise refused("invalid_passkey", "the session holds no challenge")
    return base64url_to_bytes(given)


def describe(passkey: Passkey) -> dict:
    return {
        "id": passkey.pk,
        "name": passkey.name,
        "created_at": passkey.created_at,
        "used_at": passkey.used_at,
    }


@api("POST", passkey_due=True, confirmed=("POST",))
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


@api("GET", "POST", passkey_due=True, confirmed=("POST",))
def passkeys(request):
    """The user's passkeys, and a new one from what the browser made with the last options."""
    if request.method == "POST":
        data = body(request)
        name = text(data, "name", NAME, required=True)
        expected = challenge(request, CREATING)
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
        request.session.pop(sessions.PASSKEY_DUE, None)
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
        if policy().holds(request.user) and request.user.passkeys.count() == 1:
            raise Refused(400, "last_passkey")
        found.delete()
        without_passkeys(request.user)
        entries.wrote(Kind.PASSKEY_REMOVED, request=request, subject=request.user, name=found.name)
        return HttpResponse(status=204)
    found.name = text(body(request), "name", NAME, required=True)
    found.save(update_fields=["name"])
    return JsonResponse(describe(found))


def asking(request, key: str, offered: list[PublicKeyCredentialDescriptor] | None = None):
    """The options the browser answers with a passkey: any the device keeps, or one of those
    offered."""
    _, rp_id = relying_party(request)
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=offered,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    request.session[key] = bytes_to_base64url(options.challenge)
    return JsonResponse(options_to_json_dict(options))


def answered(request, key: str) -> Passkey:
    """The passkey that signed the challenge the options under `key` gave, marked used."""
    expected = challenge(request, key)
    origin, rp_id = relying_party(request)
    try:
        credential = parse_authentication_credential_json(body(request).get("credential"))
    except (WebAuthnException, ValueError, TypeError) as error:
        raise refused("invalid_passkey", error) from None
    found = Passkey.objects.select_related("user").filter(credential=credential.raw_id).first()
    if found is None:
        # The browser then has the device forget it: a passkey removed here stays on the device.
        raise refused("unknown_passkey", "no account keeps this credential")
    if not found.user.is_active:
        raise refused("invalid_passkey", "the account is deactivated")
    given = credential.response.user_handle
    if given not in (None, handle(found.user)):
        raise refused(
            "invalid_passkey", f"the user handle is {given!r}, the account's {handle(found.user)!r}"
        )
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=expected,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes(found.public_key),
            credential_current_sign_count=found.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError) as error:
        raise refused("invalid_passkey", error) from None
    found.sign_count = verified.new_sign_count
    found.used_at = timezone.now()
    found.save(update_fields=["sign_count", "used_at"])
    return found


@api("POST", signed_in=False)
def signing_in(request):
    """The options the browser signs in with, offering whichever passkey the device keeps."""
    return asking(request, SIGNING_IN)


@api("POST", signed_in=False)
def sign_in(request):
    found = answered(request, SIGNING_IN)
    start_session(request, found.user, backend="django.contrib.auth.backends.ModelBackend")
    sessions.started(request, "passkey")
    return JsonResponse(signed(request))
