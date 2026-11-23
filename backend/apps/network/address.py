"""The installation's public address, and the names that point straight at it (DIRECT_NAMES):
every LOOK the backend asks STUN what address the internet sees it by and, where Cloudflare keeps
those names and the administrator gave the token of their zone (`Dns`), points their A records at
it, so a line whose address changes keeps its relay and its app reachable. LiveKit follows the
same address by itself (compose.yaml)."""

import json
import secrets
import socket
import struct
import urllib.error
import urllib.request
from logging import getLogger
from urllib.parse import urlencode

from anyio import sleep, to_thread
from django.conf import settings

from apps.core import sealed
from apps.core.asyncdb import database

from .models import Dns

log = getLogger(__name__)

STUN = ("stun.l.google.com", 19302)
COOKIE = 0x2112A442
API = "https://api.cloudflare.com/client/v4"
LOOK = 120
TIMEOUT = 10
# What the health page waits for each of its own looks.
GLANCE = 3
TTL = 60
SEALED = "network dns"


def public(timeout: float = TIMEOUT) -> str:
    """The address the internet sees this installation by, as STUN tells it."""
    transaction = secrets.token_bytes(12)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.settimeout(timeout)
        udp.sendto(struct.pack("!HHI", 0x0001, 0, COOKIE) + transaction, STUN)
        answer = udp.recv(512)
    if answer[:2] != b"\x01\x01" or answer[8:20] != transaction:
        raise OSError("STUN answered something else")
    at = 20
    while at + 12 <= len(answer):
        kind, length = struct.unpack_from("!HH", answer, at)
        if kind == 0x0020 and answer[at + 5] == 1:
            (address,) = struct.unpack_from("!I", answer, at + 8)
            return socket.inet_ntoa(struct.pack("!I", address ^ COOKIE))
        at += 4 + length + -length % 4
    raise OSError("STUN named no address")


def _cloudflare(token: str, method: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        API + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            return json.load(answer)["result"]
    except urllib.error.HTTPError as refused:
        raise OSError(f"Cloudflare {refused.code}: {refused.read().decode()}") from None


def _zone(token: str, name: str) -> str:
    labels = name.split(".")
    for at in range(len(labels) - 1):
        found = _cloudflare(token, "GET", "/zones?" + urlencode({"name": ".".join(labels[at:])}))
        if found:
            return found[0]["id"]
    raise OSError(f"Cloudflare keeps no zone of {name} for this token")


def point(token: str, name: str, address: str) -> bool:
    """Points the name's A record at the address, making one where there is none; whether it
    changed."""
    records = f"/zones/{_zone(token, name)}/dns_records"
    found = _cloudflare(token, "GET", records + "?" + urlencode({"type": "A", "name": name}))
    if not found:
        record = {"type": "A", "name": name, "content": address, "ttl": TTL, "proxied": False}
        _cloudflare(token, "POST", records, record)
        return True
    if found[0]["content"] == address:
        return False
    _cloudflare(token, "PATCH", f"{records}/{found[0]['id']}", {"content": address})
    return True


def setting() -> Dns:
    return Dns.objects.filter(pk=1).first() or Dns()


def opened(found: Dns) -> str | None:
    """The token, none where there is none or the installation's secret has changed since it was
    sealed."""
    if not found.token:
        return None
    return sealed.opened(SEALED, found.token)


def verified(token: str) -> bool:
    """Whether Cloudflare knows the token as an active one."""
    try:
        return _cloudflare(token, "GET", "/user/tokens/verify")["status"] == "active"
    except OSError, KeyError, TypeError:
        return False


def reached() -> bool:
    """Whether LiveKit's TCP port answers at the public address, the way a browser outside comes
    to it; a router that does not loop its own address back says no here though outside it may
    answer."""
    try:
        with socket.create_connection((public(GLANCE), settings.LIVEKIT_TCP_PORT), timeout=GLANCE):
            return True
    except OSError:
        return False


def _followed(error: str) -> None:
    Dns.objects.filter(pk=1).exclude(error=error).update(error=error)


async def follow() -> None:
    """Keeps the direct names on the installation's address while the server runs, with the token
    as it is at each look, so a token given or changed takes effect without a restart."""
    if not settings.DIRECT_NAMES:
        return
    pointed = None
    while True:
        try:
            token = await database(lambda: opened(setting()), own_thread=True)()
            if token:
                address = await to_thread.run_sync(public)
                if (address, token) != pointed:
                    for name in settings.DIRECT_NAMES:
                        if await to_thread.run_sync(point, token, name, address):
                            log.info("address: %s now points at %s", name, address)
                    pointed = (address, token)
                await database(_followed, own_thread=True)("")
        except Exception as failed:
            log.exception("address: the direct names could not follow the public address")
            pointed = None
            await database(_followed, own_thread=True)(str(failed))
        await sleep(LOOK)
