"""The browsers each user is signed in on, which they and an administrator can sign out."""

from django.http import HttpResponse, JsonResponse

from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind

from . import sessions
from .accounts import administrator
from .models import User


@api("GET", "PATCH")
def mine(request):
    """The browsers the user is signed in on; PATCH marks this one to work without the network."""
    if request.method == "PATCH":
        offline = body(request).get("offline")
        if not isinstance(offline, bool):
            raise Refused(400, "invalid")
        request.session[sessions.OFFLINE] = offline
        return HttpResponse(status=204)
    return JsonResponse({"sessions": sessions.listed(request.user, request.session.session_key)})


def ended(request, user, number: str | None = None) -> None:
    count = sessions.ended(user, number)
    if number is not None and not count:
        raise Refused(404, "not_found")
    entries.wrote(Kind.SESSIONS_ENDED, request=request, subject=user, count=count)
    revoke()


@api("DELETE")
def mine_one(request, number):
    ended(request, request.user, number)
    return HttpResponse(status=204)


def found(request, pk) -> User:
    administrator(request)
    user = User.objects.filter(pk=pk).first()
    if user is None:
        raise Refused(404, "not_found")
    return user


@api("GET", "DELETE")
def theirs(request, pk):
    """The browsers a user is signed in on, which an administrator can sign out all at once."""
    user = found(request, pk)
    if request.method == "DELETE":
        ended(request, user)
        return HttpResponse(status=204)
    return JsonResponse({"sessions": sessions.listed(user, request.session.session_key)})


@api("DELETE")
def theirs_one(request, pk, number):
    ended(request, found(request, pk), number)
    return HttpResponse(status=204)
