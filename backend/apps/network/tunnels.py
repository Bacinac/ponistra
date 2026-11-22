"""The installation's VPN tunnels as the service `tunnel` keeps them (D54). The backend hands the
service every enabled tunnel at once, as a tunnel is saved and whenever the service started again
or holds other tunnels than the database, and writes back each tunnel's state as the service tells
a change. What stands behind a tunnel is reached through the service's SOCKS5 port (`socks`);
the backend never routes into another network itself."""

import hashlib
import json
import urllib.error
import urllib.request
from functools import partial
from logging import getLogger

from anyio import sleep
from django.utils import timezone

from apps.core import sealed
from apps.core.asyncdb import database, waited

from . import wireguard
from .models import Tunnel

log = getLogger(__name__)

CONTROL = "http://tunnel:8090"
SEALED = {Tunnel.Kind.WIREGUARD: "network wireguard", Tunnel.Kind.SOFTETHER: "network softether"}
# The service answers a look once a tunnel changes or after 25 seconds.
LOOK = 35
TIMEOUT = 10
AGAIN = 30


def seal(kind: str, secret: str) -> bytes:
    return sealed.seal(SEALED[kind], secret)


def _spec(tunnel: Tunnel) -> dict | None:
    secret = sealed.opened(SEALED[tunnel.kind], tunnel.sealed) if tunnel.sealed else None
    if secret is None:
        return None
    if tunnel.kind == Tunnel.Kind.WIREGUARD:
        return {"id": str(tunnel.pk), "kind": tunnel.kind, "wireguard": wireguard.parsed(secret)}
    shown = tunnel.shown
    return {
        "id": str(tunnel.pk),
        "kind": tunnel.kind,
        "softether": {
            "server": shown["server"],
            "port": shown["port"],
            "hub": shown["hub"],
            "username": shown["username"],
            "password": secret,
        },
    }


def handed() -> dict:
    """Every enabled tunnel as the service runs it, under a digest that changes with any of them;
    a tunnel whose secret no longer opens, the installation's secret key changed, is left out
    and told as failed."""
    specs = []
    for tunnel in Tunnel.objects.filter(enabled=True).order_by("pk"):
        spec = _spec(tunnel)
        if spec is None:
            _changed(tunnel, Tunnel.State.FAILED, "sealed")
        else:
            specs.append(spec)
    written = json.dumps(specs, sort_keys=True, separators=(",", ":")).encode()
    return {"digest": hashlib.sha256(written).hexdigest(), "tunnels": specs}


def _asked(method: str, path: str, body: dict | None = None, timeout: float = TIMEOUT) -> dict:
    request = urllib.request.Request(
        CONTROL + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.load(answer)
    except urllib.error.HTTPError as refused:
        raise OSError(f"tunnel {refused.code}: {refused.read().decode()}") from None


def _changed(tunnel: Tunnel, state: str, error: str = "", detail: str = "", address: str = ""):
    now = (state, error, detail, address)
    if (tunnel.state, tunnel.error, tunnel.detail, tunnel.address) == now:
        return
    fields = {"state": state, "error": error, "detail": detail, "address": address}
    if tunnel.state != state:
        fields["since"] = timezone.now()
    Tunnel.objects.filter(pk=tunnel.pk).update(**fields)
    for name, value in fields.items():
        setattr(tunnel, name, value)


def told(report: dict) -> None:
    """Writes what the service told of each tunnel; a tunnel it does not hold yet is left as it
    is, and a switched off one is off."""
    states = report.get("tunnels") or {}
    for tunnel in Tunnel.objects.all():
        if not tunnel.enabled:
            _changed(tunnel, Tunnel.State.OFF)
        elif (found := states.get(str(tunnel.pk))) is not None:
            _changed(
                tunnel,
                found.get("state", Tunnel.State.FAILED),
                found.get("error", ""),
                found.get("detail", ""),
                found.get("address", ""),
            )


def unreached() -> None:
    for tunnel in Tunnel.objects.filter(enabled=True):
        _changed(tunnel, Tunnel.State.UNREACHED)


def apply() -> dict:
    """Hands the service the tunnels now, as one is saved; the state it answers is written."""
    try:
        report = _asked("PUT", "/tunnels", handed())
    except OSError:
        unreached()
        raise
    told(report)
    return report


async def follow() -> None:
    """Keeps the service holding the database's tunnels and their states in the database while
    the server runs. An installation without tunnels asks nothing of the service, which may not
    be there at all."""
    boot, gen, answered = None, 0, True
    while True:
        try:
            if not await database(Tunnel.objects.exists, own_thread=True)():
                boot = None
                await sleep(AGAIN)
                continue
            if boot is None:
                given = await database(handed, own_thread=True)()
                report = await waited(partial(_asked, "PUT", "/tunnels", given))
            else:
                look = partial(_asked, "GET", f"/tunnels?after={gen}", timeout=LOOK)
                report = await waited(look)
                given = await database(handed, own_thread=True)()
                if report["boot"] != boot or report["applied"] != given["digest"]:
                    if report["boot"] != boot:
                        log.info("tunnel: the service started again and is handed the tunnels")
                    report = await waited(partial(_asked, "PUT", "/tunnels", given))
            boot, gen, answered = report["boot"], report["gen"], True
            await database(told, own_thread=True)(report)
        except Exception as failed:
            if answered:
                log.warning("tunnel: the service does not answer: %s", failed)
            boot, answered = None, False
            await database(unreached, own_thread=True)()
            await sleep(AGAIN)
