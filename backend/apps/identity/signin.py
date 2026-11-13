"""The doors of signing in at an outside provider (U1): the browser sent there with an attempt
bound to it, and the answer it brings back, which signs it in or confirms who is at it."""

import hashlib
import secrets
from datetime import timedelta
from logging import getLogger
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import login as start_session
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.collab.server import revoke
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users import sessions
from apps.users.sessions import SessionStore

from . import oidc, people, saml
from .models import Attempt, Provider
from .people import Person, Refusal

log = getLogger(__name__)

COOKIE = "ponistra_attempt"
COOKIE_PATH = "/api/identity/providers/"
ATTEMPT_FOR = timedelta(minutes=10)
ANSWERED = "sign_in"


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _following(given: str | None) -> str:
    """Where the browser goes after, only ever a path of this installation."""
    given = given or "/"
    if not given.startswith("/") or given.startswith("//") or "\\" in given:
        return "/"
    return given[:500]


def _answered(path: str, code: str) -> HttpResponseRedirect:
    parts = urlsplit(path)
    query = [*parse_qsl(parts.query, keep_blank_values=True), (ANSWERED, code)]
    return HttpResponseRedirect(urlunsplit(parts._replace(query=urlencode(query))))


def _provider(pk: int) -> Provider | None:
    return Provider.objects.filter(
        pk=pk, enabled=True, kind__in=(Provider.Kind.OIDC, Provider.Kind.SAML)
    ).first()


def _secure(request) -> bool:
    return request.is_secure() or not settings.DEBUG


@require_GET
def start(request, pk: int):
    """Sends the browser to the provider. With `confirm`, a signed-in user shows who they are
    there again, for the session they have."""
    provider = _provider(pk)
    following = _following(request.GET.get("next"))
    if provider is None:
        return _answered("/", "unknown_provider")
    confirming = request.GET.get("confirm") == "1"
    if confirming and not request.user.is_authenticated:
        return _answered("/", "not_signed_in")
    Attempt.objects.filter(expires_at__lt=timezone.now()).delete()
    held = secrets.token_urlsafe(32)
    attempt = Attempt(
        provider=provider,
        digest=digest(held),
        state=secrets.token_urlsafe(32),
        following=following,
        confirming=request.user if confirming else None,
        session_key=(request.session.session_key or "") if confirming else "",
        expires_at=timezone.now() + ATTEMPT_FOR,
    )
    try:
        sending = (oidc if provider.kind == Provider.Kind.OIDC else saml).sent(provider, attempt)
    except Refusal as refusal:
        log.warning("identity: %s could not be asked: %s", provider, refusal.code)
        return _answered(following if confirming else "/", refusal.code)
    attempt.save()
    answer = HttpResponseRedirect(sending)
    secure = _secure(request)
    # A SAML provider posts its answer back from its own site, which a Lax cookie would not
    # come along with.
    answer.set_cookie(
        COOKIE,
        held,
        max_age=int(ATTEMPT_FOR.total_seconds()),
        path=COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="None" if secure else "Lax",
    )
    return answer


def _attempt(request, provider: Provider, state: str) -> Attempt:
    """The attempt the answer is for, once: it must have started in this browser."""
    held = request.COOKIES.get(COOKIE, "")
    found = Attempt.objects.filter(state=state, provider=provider).first() if state else None
    if found is None or not held or not secrets.compare_digest(found.digest, digest(held)):
        raise Refusal("unknown_attempt")
    if Attempt.objects.filter(pk=found.pk).delete()[0] != 1:
        raise Refusal("unknown_attempt")
    if found.expires_at < timezone.now():
        raise Refusal("expired_attempt")
    return found


def _finished(request, provider: Provider, attempt: Attempt, person: Person) -> HttpResponse:
    user = people.kept(provider, person)
    if provider.groups:
        revoke()
    if not user.is_active:
        raise Refusal("inactive")
    if attempt.confirming_id is not None:
        if user.pk != attempt.confirming_id:
            raise Refusal("someone_else")
        confirmed = SessionStore(attempt.session_key or None)
        if not confirmed.exists(attempt.session_key) or confirmed.get("_auth_user_id") != str(
            user.pk
        ):
            raise Refusal("not_signed_in")
        sessions.confirm(confirmed)
        confirmed.save()
        return HttpResponseRedirect(attempt.following)
    start_session(request, user, backend="django.contrib.auth.backends.ModelBackend")
    sessions.started(request, provider.kind)
    return HttpResponseRedirect(attempt.following)


def _failed(request, provider: Provider, refusal: Refusal, attempt: Attempt | None, email=""):
    log.warning("identity: sign-in at %s refused: %s", provider, refusal.code)
    entries.wrote(
        Kind.SIGN_IN_FAILED,
        request=request,
        email=email,
        way=provider.kind,
        error=refusal.code,
    )
    confirming = attempt is not None and attempt.confirming_id is not None
    return _answered(attempt.following if confirming else "/", refusal.code)


def _answer(request, provider: Provider, state: str, read) -> HttpResponse:
    attempt, person = None, None
    try:
        attempt = _attempt(request, provider, state)
        person = read(attempt)
        answer = _finished(request, provider, attempt, person)
    except Refusal as refusal:
        answer = _failed(request, provider, refusal, attempt, person.email if person else "")
    answer.delete_cookie(COOKIE, path=COOKIE_PATH)
    return answer


@require_GET
def back(request, pk: int):
    """Where an OpenID Connect provider sends the browser back with its code."""
    provider = _provider(pk)
    if provider is None or provider.kind != Provider.Kind.OIDC:
        return _answered("/", "unknown_provider")

    def read(attempt: Attempt) -> Person:
        if request.GET.get("error"):
            raise Refusal("provider_refused")
        return oidc.person(provider, request.GET.get("code", ""), attempt)

    return _answer(request, provider, request.GET.get("state", ""), read)


@csrf_exempt
@require_POST
def consumed(request, pk: int):
    """Where a SAML provider posts its response, from its own site."""
    provider = _provider(pk)
    if provider is None or provider.kind != Provider.Kind.SAML:
        return _answered("/", "unknown_provider")
    return _answer(
        request,
        provider,
        request.POST.get("RelayState", ""),
        lambda attempt: saml.person(provider, request.POST.get("SAMLResponse", ""), attempt),
    )


@require_GET
def metadata(request, pk: int):
    """What a SAML provider is given to know the installation by."""
    provider = Provider.objects.filter(pk=pk, kind=Provider.Kind.SAML).first()
    if provider is None:
        return HttpResponse(status=404)
    return HttpResponse(saml.metadata(provider), content_type="application/samlmetadata+xml")


@require_GET
def confirmed(request):
    """Where a confirmation in a window of its own ends, which the page that opened it reads."""
    return HttpResponse("", content_type="text/plain")
