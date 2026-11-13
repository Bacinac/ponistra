"""The images from elsewhere that a message's HTML shows, fetched by PONISTRA rather than the
reader's browser: the sender learns neither the reader's address nor their device, and, as each
is fetched once and kept, nothing of their looking at it again."""

import hashlib
import ipaddress
import socket
from urllib.parse import urljoin

import anyio
import httpx2
from django.core import signing

from apps.blobs.store import sniff

from .safe import SHOWN

LARGEST = 10 * 1024 * 1024
REDIRECTS = 5
WAIT = httpx2.Timeout(10)
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "image/png,image/jpeg,image/gif,image/webp"}
PORTS = {"http": 80, "https": 443}


class Unreachable(Exception):
    """No answer came from the image's server, or its address leads nowhere PONISTRA may go."""


def _salt(message: int) -> str:
    return f"mail-fetched-{message}"


def served(message: int, address: str) -> str:
    """Where PONISTRA serves the image at the address, for that message alone."""
    token = signing.dumps(address, salt=_salt(message), compress=True)
    return f"/api/mail/messages/{message}/fetched/{token}"


def address(message: int, token: str) -> str | None:
    """The address a token of `served` names, or None where the token is not one."""
    try:
        found = signing.loads(token, salt=_salt(message))
    except signing.BadSignature:
        return None
    return found if isinstance(found, str) else None


def key(address: str) -> str:
    return hashlib.sha256(address.encode()).hexdigest()


async def _public(host: str, port: int) -> str:
    """An address of the host on the internet. One inside a private network is refused, since
    a message could otherwise make PONISTRA call the servers beside it."""
    try:
        found = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise Unreachable from error
    addresses = []
    for *_, given in found:
        ip = ipaddress.ip_address(given[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise Unreachable
        addresses.append(ip)
    if not addresses:
        raise Unreachable
    # Docker's networks carry IPv4 unless an installation sets them up for IPv6.
    return str(min(addresses, key=lambda ip: ip.version))


async def fetched(address: str, transport: httpx2.AsyncBaseTransport | None = None):
    """The image at the address as its bytes and type, or None where its server answered with
    no image to show. The connection goes to the address checked, not to what the host's name
    may resolve to a moment later."""
    async with httpx2.AsyncClient(timeout=WAIT, transport=transport, trust_env=False) as client:
        for _ in range(REDIRECTS + 1):
            url = httpx2.URL(address)
            if url.scheme not in PORTS or not url.host:
                raise Unreachable
            ip = await _public(url.host, url.port or PORTS[url.scheme])
            try:
                async with client.stream(
                    "GET",
                    url.copy_with(host=ip),
                    headers=HEADERS | {"Host": url.netloc.decode()},
                    extensions={"sni_hostname": url.host},
                ) as response:
                    if response.is_redirect:
                        address = urljoin(address, response.headers.get("location", ""))
                        continue
                    if response.status_code != 200:
                        return None
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data += chunk
                        if len(data) > LARGEST:
                            return None
            except httpx2.TransportError as error:
                raise Unreachable from error
            kind = sniff(bytes(data[:1024]))
            return (bytes(data), kind) if kind in SHOWN else None
    return None
