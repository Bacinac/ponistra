import json

from django.conf import settings
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth import login as start_session
from django.contrib.auth import logout as end_session
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from apps.blobs.store import IMAGES
from apps.blobs.views import serve
from apps.core.api import Refused, api, body
from apps.identity.models import Identity, Provider
from apps.journal import entries
from apps.journal.entries import Kind
from apps.workspace.views import workspace_of

from . import factors, sessions
from .ceremony import answered, asking
from .models import CALL, LANGUAGES, PAGE_THEMES, SIGN_INS, THEMES, User, policy

# A picture behind the user in a call, which the browser makes small before sending.
BACKDROPS = {kind: suffix for kind, suffix in IMAGES.items() if kind != "image/svg+xml"}
BACKDROP_BYTES = 8 * 1024 * 1024


def describe(user) -> dict | None:
    if not user.is_authenticated:
        return None
    return {"id": user.pk, "email": user.email, "name": user.get_full_name() or user.email}


def describe_me(user) -> dict | None:
    described = describe(user)
    if described and user.visitor and hasattr(user, "opened_link"):
        described |= {"email": "", "name": ""}
    return described and {
        **described,
        "is_admin": user.is_staff,
        "visitor": user.visitor,
        "workspace": workspace_of(user),
        "language": user.language,
        "theme": user.theme,
        "projects_theme": user.projects_theme,
        "meetings_theme": user.meetings_theme,
        "sign_in": user.sign_in,
        "call": user.call,
        "backdrop": user.backdrop_id,
    }


def signed(request) -> dict:
    """The session as the app reads it: who is signed in, what they must add before anything
    else (a passkey or a second factor), whether the installation still waits for its first
    administrator, whether it offers passkeys, what a password that was right waits for, and the
    address it is reached at from outside, which its own links (a meeting's) carry."""
    user = describe_me(request.user)
    return {
        "user": user,
        "due": request.session.get(sessions.DUE) if user is not None else None,
        "setup": user is None and not User.objects.exists(),
        "site": settings.PUBLIC_URL,
        "passkeys": policy().offers_passkeys(),
        "second_factor": factors.offered(request) if user is None else None,
        "providers": Provider.offered() if user is None else [],
    }


def set_password(user, data: dict, field: str) -> None:
    password = data.get(field)
    if not isinstance(password, str):
        raise Refused(400, "invalid_password")
    try:
        validate_password(password, user)
    except ValidationError as invalid:
        raise Refused(400, invalid.error_list[0].code or "invalid_password") from None
    user.set_password(password)


@require_GET
@ensure_csrf_cookie
def session(request):
    return JsonResponse(signed(request))


@api("PATCH", visitors=True)
def preferences(request):
    """The language, the theme, the themes of Projects and of meetings, the way of signing in the
    sign-in page leads with and what a call does with the camera and the microphone, which the
    account keeps for every device, empty while not chosen."""
    data = body(request)
    given = {
        "language": LANGUAGES,
        "theme": THEMES,
        "projects_theme": PAGE_THEMES,
        "meetings_theme": PAGE_THEMES,
        "sign_in": SIGN_INS,
    }
    fields = [field for field in given if field in data]
    for field in fields:
        if data[field] not in given[field]:
            raise Refused(400, f"invalid_{field}")
        setattr(request.user, field, data[field])
    if "call" in data:
        request.user.call = _call(data["call"])
        fields.append("call")
    request.user.save(update_fields=fields)
    return JsonResponse(signed(request))


def _call(given) -> dict:
    """What a call does with the camera and the microphone, whole, each choice among those it may
    take; a True among booleans is no number."""
    if not isinstance(given, dict) or not set(given) <= set(CALL):
        raise Refused(400, "invalid_call")
    for key, value in given.items():
        if not any(value == allowed and type(value) is type(allowed) for allowed in CALL[key]):
            raise Refused(400, "invalid_call")
    return given


@api("GET", "PUT", "DELETE", visitors=True)
def backdrop(request):
    """The user's own picture behind them in a call, which a call may choose as its background."""
    user = request.user
    if request.method == "GET":
        if user.backdrop_id is None:
            raise Refused(404, "not_found")
        return serve(request, user.backdrop, f"backdrop.{BACKDROPS[user.backdrop.media_type]}")
    if request.method == "PUT":
        # content.views reaches this module through access.rights.
        from apps.content.views import stored

        if int(request.headers.get("Content-Length") or 0) > BACKDROP_BYTES:
            raise Refused(413, "too_large")
        user.backdrop = stored(request, BACKDROPS, "not_a_photo")
    else:
        user.backdrop = None
        if user.call.get("background") == "own":
            user.call = {**user.call, "background": "none"}
    user.save(update_fields=["backdrop", "call"])
    return JsonResponse(signed(request))


@require_POST
def login(request):
    try:
        body = json.loads(request.body)
        email = str(body["email"]).strip().lower()
        password = str(body["password"])
    except ValueError, KeyError, TypeError:
        return JsonResponse({"error": "email and password are required"}, status=400)
    user = authenticate(request, email=email, password=password)
    if user is None:
        return JsonResponse({"error": "invalid_credentials"}, status=400)
    if policy().holds(user) and user.passkeys.exists():
        return JsonResponse({"error": "passkey_required"}, status=403)
    if factors.offered_to(user):
        factors.pend(request, user)
        return JsonResponse(signed(request))
    start_session(request, user)
    sessions.started(request, "password", due=factors.owed(user))
    return JsonResponse(signed(request))


@api("POST", signed_in=False)
def second_options(request):
    """The options a passkey of the user's shows the second factor with."""
    user = factors.pending(request)
    if user is None:
        raise Refused(400, "no_pending_sign_in")
    if not factors.passkey_second(user, policy()):
        raise Refused(400, "no_passkey")
    return asking(
        request,
        factors.SECOND,
        [PublicKeyCredentialDescriptor(id=bytes(kept.credential)) for kept in user.passkeys.all()],
    )


@api("POST", signed_in=False)
def second(request):
    """The second factor, by the authenticator app's code or a passkey of the user's, which
    signs in the one whose password waits for it."""
    user = factors.pending(request)
    if user is None:
        raise Refused(400, "no_pending_sign_in")
    data = body(request)
    if "credential" in data:
        if not factors.passkey_second(user, policy()):
            raise Refused(400, "no_passkey")
        if answered(request, factors.SECOND).user_id != user.pk:
            factors.wrong(request, user)
            raise Refused(400, "invalid_passkey")
    else:
        found = factors.confirmed(user)
        if found is None or not factors.taken(found, data.get("code")):
            factors.wrong(request, user)
            raise Refused(400, "invalid_code")
    request.session.pop(factors.PENDING)
    start_session(request, user, backend="django.contrib.auth.backends.ModelBackend")
    sessions.started(request, "password", due=factors.owed(user))
    return JsonResponse(signed(request))


@require_POST
def logout(request):
    end_session(request)
    return JsonResponse(signed(request))


def directory_password(user) -> bool:
    """Whether the user's password is the LDAP directory's, changed only there."""
    return Identity.objects.filter(
        user=user, provider__kind=Provider.Kind.LDAP, provider__settings__sign_in=True
    ).exists()


@api("POST", confirmed=("POST",))
def password(request):
    if directory_password(request.user):
        raise Refused(400, "password_in_directory")
    data = body(request)
    set_password(request.user, data, "password")
    request.user.save(update_fields=["password"])
    update_session_auth_hash(request, request.user)
    entries.wrote(Kind.PASSWORD_CHANGED, request=request, subject=request.user)
    return JsonResponse(signed(request))


def locked_out(request, response, credentials):
    return JsonResponse({"error": "locked_out"}, status=429)
