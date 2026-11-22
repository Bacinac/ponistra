import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.core import sealed
from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator

from . import address, tunnels, wireguard
from .models import Dns, Tunnel

PLAIN = re.compile(r"[^\s\"/:]{1,200}")


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


def described(tunnel: Tunnel) -> dict:
    return {
        "id": tunnel.pk,
        "name": tunnel.name,
        "kind": tunnel.kind,
        "enabled": tunnel.enabled,
        "shown": tunnel.shown,
        "state": tunnel.state,
        "error": tunnel.error,
        "detail": tunnel.detail,
        "address": tunnel.address,
        "since": tunnel.since,
    }


def _text(given: dict, name: str) -> str:
    value = given.get(name, "")
    if not isinstance(value, str):
        raise Refused(400, f"invalid_{name}")
    return value.strip()


def _filled(tunnel: Tunnel, given: dict) -> None:
    """Fills the tunnel from what was given, a secret left empty keeping the one it has."""
    if "name" in given or not tunnel.pk:
        tunnel.name = _text(given, "name")
        if not 0 < len(tunnel.name) <= 150:
            raise Refused(400, "invalid_name")
    if "enabled" in given:
        if not isinstance(given["enabled"], bool):
            raise Refused(400, "invalid_enabled")
        tunnel.enabled = given["enabled"]
    if tunnel.kind == Tunnel.Kind.WIREGUARD:
        configuration = given.get("configuration", "")
        if not isinstance(configuration, str):
            raise Refused(400, "invalid_wireguard")
        if configuration.strip():
            try:
                spec = wireguard.parsed(configuration)
            except wireguard.Invalid:
                raise Refused(400, "invalid_wireguard") from None
            tunnel.shown = wireguard.shown(spec)
            tunnel.sealed = tunnels.seal(tunnel.kind, configuration)
    else:
        shown = dict(tunnel.shown)
        for name in ("server", "hub", "username"):
            if name in given or not tunnel.pk:
                shown[name] = _text(given, name)
                if not PLAIN.fullmatch(shown[name]):
                    raise Refused(400, f"invalid_{name}")
        if "port" in given or not tunnel.pk:
            port = given.get("port", 443)
            if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
                raise Refused(400, "invalid_port")
            shown["port"] = port
        tunnel.shown = shown
        password = given.get("password", "")
        if not isinstance(password, str) or "\n" in password or "\r" in password:
            raise Refused(400, "invalid_password")
        if password:
            tunnel.sealed = tunnels.seal(tunnel.kind, password)
    if not tunnel.sealed:
        raise Refused(400, "secret_required")
    if not tunnel.enabled:
        tunnel.state, tunnel.error, tunnel.detail, tunnel.address = Tunnel.State.OFF, "", "", ""
    elif tunnel.state == Tunnel.State.OFF or not tunnel.pk:
        tunnel.state = Tunnel.State.CONNECTING
    tunnel.since = timezone.now() if not tunnel.pk else tunnel.since


def _saved(tunnel: Tunnel, request, change: str, status: int = 200) -> JsonResponse:
    try:
        with transaction.atomic():
            tunnel.save()
    except IntegrityError:
        raise Refused(409, "tunnel_taken") from None
    entries.wrote(
        Kind.SETTING_CHANGED,
        request=request,
        setting="network_tunnel",
        name=tunnel.name,
        change=change,
    )
    _applied()
    tunnel.refresh_from_db()
    return JsonResponse(described(tunnel), status=status)


def _applied() -> None:
    # A service that does not answer is told on the tunnel's state; what was saved stays.
    try:
        tunnels.apply()
    except OSError:
        pass


@api("GET", "POST", confirmed=("POST",))
def tunnel_list(request):
    """The installation's VPN tunnels, and a new one."""
    administrator(request)
    if request.method == "GET":
        found = Tunnel.objects.order_by("name", "pk")
        return JsonResponse({"tunnels": [described(each) for each in found]})
    given = body(request)
    if given.get("kind") not in Tunnel.Kind.values:
        raise Refused(400, "invalid_kind")
    tunnel = Tunnel(kind=given["kind"], created_by=request.user)
    _filled(tunnel, given)
    return _saved(tunnel, request, "added", 201)


@api("PATCH", "DELETE", confirmed=("PATCH", "DELETE"))
def tunnel(request, pk: int):
    """A tunnel changed, or removed: the service closes it at once."""
    administrator(request)
    found = Tunnel.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        found.delete()
        entries.wrote(
            Kind.SETTING_CHANGED,
            request=request,
            setting="network_tunnel",
            name=found.name,
            change="removed",
        )
        _applied()
        return HttpResponse(status=204)
    _filled(found, body(request))
    return _saved(found, request, "changed")
