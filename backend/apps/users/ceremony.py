"""A WebAuthn ceremony's two halves: the options the browser answers with a passkey, and the
answer checked against the challenge they gave."""

import json
from logging import getLogger
from urllib.parse import urlsplit

from django.http import JsonResponse
from django.utils import timezone
from webauthn import generate_authentication_options, verify_authentication_response
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    options_to_json_dict,
    parse_authentication_credential_json,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from apps.core.api import Refused, body

from .models import Passkey, User

# The challenges a session keeps under one key: the sign-in page asks for options for the list
# under the email field and again for its button, and the browser answers whichever the person
# used, in whatever order the two reached the server.
KEPT = 4

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


def keep(request, key: str, challenge: bytes) -> None:
    request.session[key] = [
        *request.session.get(key, [])[1 - KEPT :],
        bytes_to_base64url(challenge),
    ]


def challenge(request, key: str, client_data: bytes) -> bytes:
    """The challenge one of the options under `key` gave and the browser signed, good for one
    answer."""
    try:
        signed = json.loads(client_data)["challenge"]
    except (ValueError, KeyError, TypeError) as error:
        raise refused("invalid_passkey", error) from None
    given = request.session.get(key, [])
    if signed not in given:
        raise refused("invalid_passkey", "the session holds no such challenge")
    request.session[key] = [each for each in given if each != signed]
    return base64url_to_bytes(signed)


def asking(request, key: str, offered: list[PublicKeyCredentialDescriptor] | None = None):
    """The options the browser answers with a passkey: any the device keeps, or one of those
    offered."""
    _, rp_id = relying_party(request)
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=offered,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    keep(request, key, options.challenge)
    return JsonResponse(options_to_json_dict(options))


def answered(request, key: str) -> Passkey:
    """The passkey that signed a challenge the options under `key` gave, marked used."""
    origin, rp_id = relying_party(request)
    try:
        credential = parse_authentication_credential_json(body(request).get("credential"))
    except (WebAuthnException, ValueError, TypeError) as error:
        raise refused("invalid_passkey", error) from None
    expected = challenge(request, key, credential.response.client_data_json)
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
