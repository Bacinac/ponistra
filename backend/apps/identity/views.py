"""The doors of D38: what the installation says of itself, the sign-in an application sends its
user to, the token and userinfo calls the application makes itself, and the administrator's list
of the applications that sign in here."""

import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator
from apps.users.models import User

from . import tokens
from .models import Application, Code

AUTHORIZE_PATH = "/authorize"
CODE_FOR = timedelta(minutes=5)
SCOPES = ("openid", "email", "profile")
CLAIMS = (
    "sub",
    "email",
    "email_verified",
    "name",
    "given_name",
    "family_name",
    "preferred_username",
)
NOT_KEPT = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def challenge_of(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def allowed(application: Application, user) -> bool:
    return user.is_active and (application.everyone or user.is_staff)


def claims_of(user, scopes: list[str]) -> dict:
    claims = {"sub": str(user.pk)}
    if "email" in scopes:
        claims |= {"email": user.email, "email_verified": True}
    if "profile" in scopes:
        given = {
            "name": user.get_full_name() or user.email,
            "given_name": user.first_name,
            "family_name": user.last_name,
            "preferred_username": user.email,
        }
        claims |= {name: value for name, value in given.items() if value}
    return claims


@api("GET", signed_in=False)
def configuration(request):
    base = tokens.issuer()
    return JsonResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{settings.PUBLIC_URL}{AUTHORIZE_PATH}",
            "token_endpoint": f"{base}/token",
            "userinfo_endpoint": f"{base}/userinfo",
            "jwks_uri": f"{base}/jwks",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": [tokens.ALGORITHM],
            "scopes_supported": list(SCOPES),
            "claims_supported": list(CLAIMS),
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "code_challenge_methods_supported": ["S256"],
        }
    )


@api("GET", signed_in=False)
def jwks(request):
    return JsonResponse({"keys": tokens.published()})


def _back(redirect: str, state: str, **answer: str) -> str:
    parts = urlsplit(redirect)
    given = {**answer, "state": state}
    query = parse_qsl(parts.query, keep_blank_values=True)
    query += [(name, value) for name, value in given.items() if value]
    return urlunsplit(parts._replace(query=urlencode(query)))


@api("GET", "POST", confirmed=("POST",))
def authorize(request):
    """The sign-in an application sent its user to, asked by the page at AUTHORIZE_PATH with the
    request as it came: an unknown application or address back is answered here, never sent on;
    what the request itself got wrong goes back to the application."""
    asked = request.GET
    application = Application.objects.filter(client_id=asked.get("client_id", "")).first()
    if application is None:
        raise Refused(404, "unknown_application")
    redirect = asked.get("redirect_uri", "")
    if redirect not in application.redirect_uris:
        raise Refused(400, "unknown_redirect")
    if not allowed(application, request.user):
        raise Refused(403, "not_allowed")
    if request.method == "GET":
        return JsonResponse({"application": application.name})
    state = asked.get("state", "")
    scopes = list(dict.fromkeys(asked.get("scope", "").split()))
    challenge = asked.get("code_challenge", "")
    if asked.get("response_type") != "code":
        return JsonResponse({"redirect": _back(redirect, state, error="unsupported_response_type")})
    if "openid" not in scopes:
        return JsonResponse({"redirect": _back(redirect, state, error="invalid_scope")})
    if challenge and asked.get("code_challenge_method") != "S256":
        return JsonResponse({"redirect": _back(redirect, state, error="invalid_request")})
    Code.objects.filter(expires_at__lt=timezone.now()).delete()
    code = secrets.token_urlsafe(32)
    Code.objects.create(
        application=application,
        user=request.user,
        digest=digest(code),
        redirect_uri=redirect,
        scopes=[each for each in scopes if each in SCOPES],
        nonce=asked.get("nonce", ""),
        challenge=challenge,
        expires_at=timezone.now() + CODE_FOR,
    )
    entries.wrote(Kind.APPLICATION_SIGNED_IN, request=request, name=application.name)
    return JsonResponse({"redirect": _back(redirect, state, code=code)})


class Failed(Exception):
    def __init__(self, error: str, status: int = 400):
        super().__init__(error)
        self.error = error
        self.status = status


def _client(request) -> Application:
    """The application calling, by HTTP Basic or by the form, as RFC 6749 lets it choose."""
    scheme, _, given = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "basic":
        try:
            client_id, _, secret = base64.b64decode(given.strip()).decode().partition(":")
        except binascii.Error, UnicodeDecodeError:
            raise Failed("invalid_client", 401) from None
        client_id, secret = unquote_plus(client_id), unquote_plus(secret)
    else:
        client_id = request.POST.get("client_id", "")
        secret = request.POST.get("client_secret", "")
    found = Application.objects.filter(client_id=client_id).first()
    if found is None or not hmac.compare_digest(found.secret_digest, digest(secret)):
        raise Failed("invalid_client", 401)
    return found


def _exchanged(request, application: Application) -> Code:
    if request.POST.get("grant_type") != "authorization_code":
        raise Failed("unsupported_grant_type")
    found = (
        Code.objects.select_related("user")
        .filter(digest=digest(request.POST.get("code", "")), application=application)
        .first()
    )
    if found is None or Code.objects.filter(pk=found.pk).delete()[0] != 1:
        raise Failed("invalid_grant")
    verifier = request.POST.get("code_verifier", "")
    if (
        found.expires_at < timezone.now()
        or found.redirect_uri != request.POST.get("redirect_uri")
        or (found.challenge and not hmac.compare_digest(found.challenge, challenge_of(verifier)))
        or not allowed(application, found.user)
    ):
        raise Failed("invalid_grant")
    return found


@csrf_exempt
def token(request):
    """The code exchanged, once, for the ID token that says who signed in and the access token
    the application asks userinfo with."""
    if request.method != "POST":
        return JsonResponse({"error": "invalid_request"}, status=405, headers=NOT_KEPT)
    try:
        application = _client(request)
        code = _exchanged(request, application)
    except Failed as failed:
        challenged = {"WWW-Authenticate": "Basic"} if failed.status == 401 else {}
        return JsonResponse(
            {"error": failed.error}, status=failed.status, headers={**NOT_KEPT, **challenged}
        )
    application.used_at = timezone.now()
    application.save(update_fields=["used_at"])
    access = tokens.access(application.client_id, code.user, code.scopes)
    identity = tokens.identity(
        application.client_id, claims_of(code.user, code.scopes), code.nonce, access
    )
    return JsonResponse(
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int(tokens.LIFETIME.total_seconds()),
            "id_token": identity,
            "scope": " ".join(code.scopes),
        },
        headers=NOT_KEPT,
    )


@csrf_exempt
def userinfo(request):
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "invalid_request"}, status=405)
    scheme, _, given = request.headers.get("Authorization", "").partition(" ")
    claims = tokens.verified(given.strip()) if scheme.lower() == "bearer" else None
    user = claims and User.objects.filter(pk=claims["sub"]).first()
    application = claims and Application.objects.filter(client_id=claims["client_id"]).first()
    if not user or not application or not allowed(application, user):
        return HttpResponse(
            status=401, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}
        )
    return JsonResponse(claims_of(user, claims["scope"].split()), headers=NOT_KEPT)


def describe(application: Application) -> dict:
    return {
        "id": application.pk,
        "name": application.name,
        "client_id": application.client_id,
        "redirect_uris": application.redirect_uris,
        "everyone": application.everyone,
        "created_at": application.created_at,
        "used_at": application.used_at,
    }


def _addresses(given) -> list[str]:
    if not isinstance(given, list) or not all(isinstance(each, str) for each in given):
        raise Refused(400, "redirect_required")
    found = list(dict.fromkeys(each.strip() for each in given if each.strip()))
    if not found:
        raise Refused(400, "redirect_required")
    for each in found:
        parts = urlsplit(each)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.fragment:
            raise Refused(400, "redirect_invalid")
    return found


def _fields(data: dict) -> dict:
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 150:
        raise Refused(400, "name_required")
    if not isinstance(data.get("everyone", False), bool):
        raise Refused(400, "invalid_everyone")
    return {
        "name": name.strip(),
        "redirect_uris": _addresses(data.get("redirect_uris")),
        "everyone": data.get("everyone", False),
    }


def _made(application: Application) -> JsonResponse:
    secret = secrets.token_urlsafe(32)
    application.secret_digest = digest(secret)
    application.save()
    return JsonResponse({**describe(application), "secret": secret}, status=201)


@api("GET", "POST", confirmed=("POST",))
def applications(request):
    """The applications that sign in here, with the issuer each is told; a new one's secret is
    shown once, as it is made."""
    administrator(request)
    if request.method == "GET":
        found = Application.objects.order_by("name", "pk")
        return JsonResponse(
            {"issuer": tokens.issuer(), "applications": [describe(each) for each in found]}
        )
    made = Application(**_fields(body(request)), client_id=secrets.token_urlsafe(16))
    answer = _made(made)
    entries.wrote(Kind.APPLICATION_ADDED, request=request, name=made.name)
    return answer


@api("PATCH", "DELETE", confirmed=("PATCH",))
def application(request, pk):
    administrator(request)
    found = Application.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        found.delete()
        entries.wrote(Kind.APPLICATION_REMOVED, request=request, name=found.name)
        return HttpResponse(status=204)
    for name, value in _fields(body(request)).items():
        setattr(found, name, value)
    found.save()
    entries.wrote(Kind.APPLICATION_CHANGED, request=request, name=found.name)
    return JsonResponse(describe(found))


@api("POST", confirmed=("POST",))
def secret(request, pk):
    """A new secret for the application, the old one no longer accepted."""
    administrator(request)
    found = Application.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    answer = _made(found)
    entries.wrote(Kind.APPLICATION_SECRET, request=request, name=found.name)
    return answer
