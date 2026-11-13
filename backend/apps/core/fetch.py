"""Downloads what a user gave only by its address, an image pasted or a link's page, from public
hosts alone: the server must not become a way to reach what sits behind it."""

import http.client
import ipaddress
import socket
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urljoin, urlsplit

TIMEOUT = 10
REDIRECTS = 3
MOVED = {301, 302, 303, 307, 308}
# Many sites refuse a request that names no browser.
AGENT = "Mozilla/5.0 (compatible; Ponistra)"


class Unreachable(Exception):
    pass


def public_address(host: str, port: int) -> str:
    """The address to connect to, once every address the name resolves to is public."""
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror, UnicodeError:
        raise Unreachable from None
    addresses = [info[4][0] for info in found]
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise Unreachable
    return addresses[0]


# Connecting to the address that was checked, not to the name again, leaves no room for
# the name to resolve elsewhere in between.
class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str):
        super().__init__(host, port, timeout=TIMEOUT)
        self.address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str):
        super().__init__(host, port, timeout=TIMEOUT, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class Body:
    """The response's bytes for store.put, the address they came from after redirects and their
    kind; a dropped connection is the host's fault, not ours."""

    def __init__(self, response: http.client.HTTPResponse, url: str):
        self.response = response
        self.url = url
        self.media_type = response.getheader("Content-Type", "")

    def read(self, size: int) -> bytes:
        try:
            return self.response.read(size)
        except OSError, http.client.HTTPException:
            raise Unreachable from None


@contextmanager
def fetched(url: str, accept: str = "image/*") -> Iterator[Body]:
    """The body of a GET of the address, after at most REDIRECTS redirects."""
    for _ in range(REDIRECTS + 1):
        parts = urlsplit(url)
        secure = parts.scheme == "https"
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise Unreachable
        try:
            port = parts.port or (443 if secure else 80)
        except ValueError:
            raise Unreachable from None
        address = public_address(parts.hostname, port)
        connection = (PinnedHTTPS if secure else PinnedHTTP)(parts.hostname, port, address)
        try:
            try:
                target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
                connection.request("GET", target, headers={"Accept": accept, "User-Agent": AGENT})
                response = connection.getresponse()
            except OSError, http.client.HTTPException:
                raise Unreachable from None
            if response.status in MOVED and (location := response.getheader("Location")):
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise Unreachable
            yield Body(response, url)
            return
        finally:
            connection.close()
    raise Unreachable
