"""Web Push: the installation's public key, the browsers a user let it reach, and whether it sends
at all, which an administrator decides."""

from django.http import HttpResponse, JsonResponse

from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator

from . import notices, webpush
from .models import Subscription

LANGUAGES = ("hr", "en")


def describe(found: Subscription, endpoint: str) -> dict:
    return {
        "id": found.pk,
        "agent": found.agent,
        "language": found.language,
        "created_at": found.created_at,
        "used_at": found.used_at,
        "current": found.endpoint == endpoint,
    }


def _listed(user, endpoint: str) -> list[dict]:
    return [describe(each, endpoint) for each in user.push_subscriptions.all()]


@api("GET")
def push(request):
    """The key a browser subscribes with, the user's browsers that did, and whether the
    installation sends; the browser names its own subscription's endpoint to see which is it."""
    endpoint = request.GET.get("endpoint", "")
    return JsonResponse(
        {
            "key": webpush.b64(bytes(webpush.keys().public)),
            "on": notices.setting().on,
            "subscriptions": _listed(request.user, endpoint),
        }
    )


def _key(data: dict, name: str, length: int) -> bytes:
    try:
        decoded = webpush.unb64(str(data.get(name, "")))
    except ValueError:
        raise Refused(400, f"invalid_{name}") from None
    if len(decoded) != length:
        raise Refused(400, f"invalid_{name}")
    return decoded


@api("POST")
def subscriptions(request):
    """Keeps the subscription the browser made, or brings it up to date: the browser sends it
    again each time the app opens, in the language it reads then."""
    data = body(request)
    endpoint = str(data.get("endpoint", ""))
    if not endpoint.startswith("https://") or len(endpoint) > 2000:
        raise Refused(400, "invalid_endpoint")
    keys = data.get("keys")
    if not isinstance(keys, dict):
        raise Refused(400, "invalid_keys")
    p256dh = _key(keys, "p256dh", 65)
    if p256dh[0] != 4:
        raise Refused(400, "invalid_p256dh")
    auth = _key(keys, "auth", 16)
    language = data.get("language", "hr")
    if language not in LANGUAGES:
        raise Refused(400, "invalid_language")
    found, created = Subscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "language": language,
            "agent": request.META.get("HTTP_USER_AGENT", "")[:300],
        },
    )
    return JsonResponse({"subscription": describe(found, endpoint)}, status=201 if created else 200)


@api("DELETE")
def subscription(request, pk):
    if not request.user.push_subscriptions.filter(pk=pk).delete()[0]:
        raise Refused(404, "not_found")
    return HttpResponse(status=204)


@api("GET", "PATCH")
def setting(request):
    """Whether the installation sends notifications to browsers at all."""
    administrator(request)
    if request.method == "PATCH":
        on = body(request).get("on")
        if not isinstance(on, bool):
            raise Refused(400, "invalid_on")
        found = notices.change(request.user, on)
        entries.wrote(Kind.SETTING_CHANGED, request=request, setting="push", enabled=on)
        return JsonResponse(notices.describe_setting(found))
    return JsonResponse(notices.describe_setting(notices.setting()))
