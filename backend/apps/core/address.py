"""The installation's public address, and the names that point straight at it (DIRECT_NAMES):
every LOOK the backend asks STUN what address the internet sees it by and, where Cloudflare keeps
those names, points their A records at it, so a line whose address changes keeps its relay and
its app reachable. LiveKit follows the same address by itself (compose.yaml)."""

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

log = getLogger(__name__)

STUN = ("stun.l.google.com", 19302)
COOKIE = 0x2112A442
API = "https://api.cloudflare.com/client/v4"
LOOK = 120
TIMEOUT = 10
TTL = 60


def public() -> str:
    """The address the internet sees this installation by, as STUN tells it."""
    transaction = secrets.token_bytes(12)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.settimeout(TIMEOUT)
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


def _cloudflare(method: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        API + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {settings.CLOUDFLARE_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            return json.load(answer)["result"]
    except urllib.error.HTTPError as refused:
        raise OSError(f"Cloudflare {refused.code}: {refused.read().decode()}") from None


def _zone(name: str) -> str:
    labels = name.split(".")
    for at in range(len(labels) - 1):
        found = _cloudflare("GET", "/zones?" + urlencode({"name": ".".join(labels[at:])}))
        if found:
            return found[0]["id"]
    raise OSError(f"Cloudflare keeps no zone of {name} for this token")


def point(name: str, address: str) -> bool:
    """Points the name's A record at the address, making one where there is none; whether it
    changed."""
    records = f"/zones/{_zone(name)}/dns_records"
    found = _cloudflare("GET", records + "?" + urlencode({"type": "A", "name": name}))
    if not found:
        record = {"type": "A", "name": name, "content": address, "ttl": TTL, "proxied": False}
        _cloudflare("POST", records, record)
        return True
    if found[0]["content"] == address:
        return False
    _cloudflare("PATCH", f"{records}/{found[0]['id']}", {"content": address})
    return True


async def follow() -> None:
    """Keeps the direct names on the installation's address while the server runs."""
    if not (settings.CLOUDFLARE_TOKEN and settings.DIRECT_NAMES):
        return
    pointed = None
    while True:
        try:
            address = await to_thread.run_sync(public)
            if address != pointed:
                for name in settings.DIRECT_NAMES:
                    if await to_thread.run_sync(point, name, address):
                        log.info("address: %s now points at %s", name, address)
                pointed = address
        except Exception:
            log.exception("address: the direct names could not follow the public address")
        await sleep(LOOK)
