from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from apps.core import sealed
from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator

from . import address
from .models import Dns


def _described(found: Dns) -> dict:
    try:
        public = address.public(address.GLANCE)
    except OSError:
        public = None
    return {
        "address": public,
        "reached": address.reached() if public else False,
        "ports": {"udp": settings.LIVEKIT_UDP_PORT, "tcp": settings.LIVEKIT_TCP_PORT},
        "relay": settings.TURN,
        "names": settings.DIRECT_NAMES,
        "dns": {
            "hint": found.hint,
            "lost": bool(found.token) and address.opened(found) is None,
            "error": found.error,
            "changed_at": found.changed_at,
        },
    }


@api("GET", "PATCH")
def network(request):
    """The installation's public address and whether meetings reach it, and the token that keeps
    the names pointing straight at it there; the token given is tried before it is kept, an empty
    one forgets it."""
    administrator(request)
    if request.method == "PATCH":
        token = body(request).get("token")
        if not isinstance(token, str):
            raise Refused(400, "invalid_dns_token")
        token = token.strip()
        if token and not address.verified(token):
            raise Refused(422, "dns_token_refused")
        found = address.setting()
        found.token = sealed.seal(address.SEALED, token) if token else b""
        found.hint, found.error = token[-4:], ""
        found.changed_by, found.changed_at = request.user, timezone.now()
        found.save()
        entries.wrote(
            Kind.SETTING_CHANGED, request=request, setting="network_dns", secret=bool(token)
        )
    return JsonResponse(_described(address.setting()))
