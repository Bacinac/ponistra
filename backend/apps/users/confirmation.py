"""Showing again who is at the browser before what an open session must not do alone (D33): with
a passkey of the user's, or with their password where the policy lets them sign in with one."""

from django.contrib.auth import authenticate
from django.http import HttpResponse, JsonResponse
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from apps.core.api import Refused, api, body
from apps.identity.models import Provider
from apps.push import notices
from apps.push.models import Notice

from . import sessions
from .passkeys import answered, asking
from .views import directory_password, policy

CONFIRMING = "passkey_confirming"


def signed_in(sender, request, user, **kwargs) -> None:
    """A sign-in shows who is at the browser as a confirmation does, and the user's browsers
    hear of it."""
    sessions.confirm(request.session)
    notices.tell(
        [user.pk],
        Notice.Kind.SECURITY,
        {"event": "sign_in", "address": sessions.address_of(request)},
    )


def by_password(user) -> bool:
    return (user.has_usable_password() or directory_password(user)) and not (
        policy().holds(user) and user.passkeys.exists()
    )


@api("GET", "POST", passkey_due=True)
def confirm(request):
    """How the user can confirm, and the confirmation itself, by the passkey that answered the
    last options or by the password."""
    user = request.user
    if request.method == "GET":
        return JsonResponse(
            {
                "passkey": user.passkeys.exists(),
                "password": by_password(user),
                "providers": Provider.offered(user),
            }
        )
    data = body(request)
    if "credential" in data:
        if answered(request, CONFIRMING).user_id != user.pk:
            raise Refused(400, "invalid_passkey")
    else:
        if not by_password(user):
            raise Refused(403, "passkey_required")
        password = data.get("password")
        if not isinstance(password, str) or (
            authenticate(request, email=user.email, password=password) is None
        ):
            raise Refused(400, "invalid_credentials")
    sessions.confirm(request.session)
    return HttpResponse(status=204)


@api("POST", passkey_due=True)
def confirming(request):
    """The options the browser confirms with, offering only the user's own passkeys."""
    return asking(
        request,
        CONFIRMING,
        [
            PublicKeyCredentialDescriptor(id=bytes(kept.credential))
            for kept in request.user.passkeys.all()
        ],
    )
