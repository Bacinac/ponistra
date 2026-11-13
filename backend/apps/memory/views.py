"""The agent's memory on the page of code (MEM1–MEM5), for the workspace's owner alone: what each
store holds and what is wrong with it, the proposals to accept or reject, the history to take back,
an analysis asked of a session and the nightly pass switched on or off. The workspace says when a
store changed with the token it is asked with."""

import hmac

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.workspace.views import owns
from apps.workspace.views import shown as shown_command

from . import ledger
from .models import Nightly

ANSWERS = {"yes": True, "no": False}


def _owner(request) -> None:
    if not owns(request.user):
        raise Refused(403, "not_the_owner")


def _overview() -> dict:
    listed = ledger.read()
    ledger.synced(listed)
    return ledger.overview(listed)


@api("GET")
def memory(request):
    _owner(request)
    return JsonResponse(_overview())


@api("GET")
def waiting(request):
    """How many proposals wait, read here alone, for the list of the page of code."""
    _owner(request)
    return JsonResponse({"count": ledger.waiting_count()})


@api("POST")
def proposal(request, pk: int):
    """Yes or No to one proposal, from the page or a notification's action."""
    _owner(request)
    answer = body(request).get("text")
    if answer not in ANSWERS:
        raise Refused(400, "invalid_text")
    decided = ledger.decided(pk, ANSWERS[answer])
    if decided.state == decided.State.STALE:
        raise Refused(409, "memory_changed")
    return JsonResponse(ledger.shown(decided, changes=False))


@api("POST")
def revert(request, pk: int):
    _owner(request)
    return JsonResponse(ledger.shown(ledger.reverted(pk), changes=False))


@api("POST")
def analyse(request):
    """A session asked to analyse the memory changed since it was last analysed: one store's, or
    every store's without one."""
    _owner(request)
    store = body(request).get("store")
    if store is not None and not isinstance(store, str):
        raise Refused(400, "invalid_store")
    return JsonResponse(shown_command(ledger.analyse(store)))


@api("POST")
def review(request):
    """A session asked to sort the open proposals into groups, each with its advice (MEM6)."""
    _owner(request)
    return JsonResponse(shown_command(ledger.review()))


@api("POST")
def advice(request, pk: int):
    """Yes or No to every open proposal of one group of the review."""
    _owner(request)
    answer = body(request).get("text")
    if answer not in ANSWERS:
        raise Refused(400, "invalid_text")
    return JsonResponse(ledger.followed_advice(pk, ANSWERS[answer]))


@api("POST")
def nightly(request):
    _owner(request)
    on = body(request).get("on")
    if not isinstance(on, bool):
        raise Refused(400, "invalid_on")
    Nightly.objects.update_or_create(pk=1, defaults={"on": on})
    return JsonResponse({"nightly": on})


@csrf_exempt
async def changed(request):
    """The workspace saying a store changed, with the token it is asked with."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    given = request.headers.get("Authorization", "")
    if not settings.WORKSPACE_TOKEN or not hmac.compare_digest(
        given.encode(), f"Bearer {settings.WORKSPACE_TOKEN}".encode()
    ):
        return JsonResponse({"error": "refused"}, status=403)
    await database(ledger.heard, own_thread=True)()
    return HttpResponse(status=204)
