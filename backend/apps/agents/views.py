"""The user's side of the doors (D18): the consent screen a sign-in waits at, and the agents
let in, listed on the account and revocable there."""

import secrets

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from mcp.server.auth.provider import construct_redirect_uri

from apps.core.api import Refused, api, body, optional_id

from . import oauth
from .models import Authorization, Grant, Token


def _waiting(pk) -> Authorization:
    found = Authorization.objects.select_related("client").filter(pk=pk, user=None).first()
    if found is None or found.expires_at < timezone.now():
        raise Refused(404, "request_expired")
    return found


def _redirect(found: Authorization, **answer) -> dict:
    state = found.params.get("state")
    return {"redirect": construct_redirect_uri(found.params["redirect_uri"], state=state, **answer)}


@api("GET", "POST", confirmed=("POST",))
def consent(request):
    """What a sign-in asks, and the user's answer: allowed, the code goes back to the client with
    the user's grant standing behind it; refused, the client hears that instead."""
    if request.method == "GET":
        found = _waiting(optional_id(request.GET.get("request")))
        return JsonResponse(
            {
                "client": found.client.name or found.client.client_id,
                "redirect": found.params["redirect_uri"],
                "scopes": found.params.get("scopes") or [],
                "expires_at": found.expires_at,
            }
        )
    data = body(request)
    found = _waiting(optional_id(data.get("request")))
    if not data.get("allow"):
        found.delete()
        return JsonResponse(_redirect(found, error="access_denied"))
    found.user = request.user
    found.code = secrets.token_urlsafe(32)
    found.expires_at = timezone.now() + oauth.CODE
    found.save(update_fields=["user", "code", "expires_at"])
    Grant.objects.get_or_create(
        client=found.client,
        user=request.user,
        revoked_at=None,
        defaults={"scopes": found.params.get("scopes") or []},
    )
    return JsonResponse(_redirect(found, code=found.code))


def describe(grant: Grant) -> dict:
    return {
        "id": grant.pk,
        "client": grant.client.name or grant.client.client_id,
        "created_at": grant.created_at,
        "used_at": grant.used_at,
    }


@api("GET")
def clients(request):
    """The agents the user let in, and where an agent signs in."""
    found = (
        Grant.objects.filter(user=request.user, revoked_at=None)
        .select_related("client")
        .order_by("created_at", "pk")
    )
    return JsonResponse(
        {
            "url": oauth.mcp_url(),
            "public_url": settings.PUBLIC_URL,
            "clients": [describe(each) for each in found],
        }
    )


@api("DELETE")
def client(request, pk):
    """Revokes the agent: its tokens go, and the runs it made stay under its name."""
    found = Grant.objects.filter(pk=pk, user=request.user, revoked_at=None).first()
    if found is None:
        raise Refused(404, "not_found")
    found.revoked_at = timezone.now()
    found.save(update_fields=["revoked_at"])
    Token.objects.filter(grant=found).delete()
    return HttpResponse(status=204)
