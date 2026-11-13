"""An ActiveSync server (MS-ASHTTP, MS-ASCMD) as PONISTRA reaches it: Exchange, HCL Traveler and
the others phones sync with, its commands sent over one kept HTTPS connection as the device the
account registered, which takes the server's policy whenever the server asks for it."""

import base64
import http.client
import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

from django.conf import settings

from ..imap import Failed
from . import wbxml
from .wbxml import Element
from .wbxml import element as e

PATH = "/Microsoft-Server-ActiveSync"
VERSION = "14.1"
TIMEOUT = 60
DEVICE = "PONISTRA"
POLICY = "MS-EAS-Provisioning-WBXML"
WBXML = "application/vnd.ms-sync.wbxml"
# MS-ASCMD 2.2.2: the policy to take again (140 asks the device to wipe itself first).
PROVISION = {"140", "142", "143", "144"}
# The user or the device is not let in: blocked, disabled, over the user's devices, or a policy
# the device cannot meet.
REFUSED = {"126", "127", "129", "130", "131", "139", "141", "145", "177"}


# HCL Traveler ends a device's open request as soon as the device sends another (HTTP 409), so an
# account's sessions take turns; only a Ping, which waits for minutes, is left open to the others.
_turns: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _turn(device: str) -> threading.Lock:
    with _guard:
        return _turns.setdefault(device, threading.Lock())


class Interrupted(Exception):
    """The server ended the Ping for another request of the device."""


class Wiped(Exception):
    """The server's administrator asked the device to wipe what it keeps of the mailbox."""


@dataclass
class Session:
    """The account's device on the server. `policy` is the key of the policy it took;
    `remember` keeps a new one."""

    host: str
    username: str
    password: str
    device: str
    policy: str = ""
    remember: Callable[[str], None] = lambda key: None
    timeout: float = TIMEOUT
    _connection: http.client.HTTPSConnection | None = field(default=None, repr=False)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _sent(
        self,
        method: str,
        url: str,
        body: bytes | None,
        headers: dict,
        timeout: float,
        waits: bool = False,
    ):
        for attempt in (1, 2):
            fresh = self._connection is None
            if fresh:
                # Only towards a host the installation names in PONISTRA_MAIL_PLAIN_HOSTS.
                if urlsplit(f"//{self.host}").hostname in settings.MAIL_PLAIN_HOSTS:
                    self._connection = http.client.HTTPConnection(self.host, timeout=timeout)
                else:
                    self._connection = http.client.HTTPSConnection(
                        self.host, timeout=timeout, context=ssl.create_default_context()
                    )
            self._connection.timeout = timeout
            try:
                if self._connection.sock is not None:
                    self._connection.sock.settimeout(timeout)
                with _turn(self.device):
                    self._connection.request(method, url, body, headers)
                    if not waits:
                        return self._response()
                return self._response()
            except ssl.SSLCertVerificationError:
                self.close()
                raise Failed("activesync_tls") from None
            except OSError, http.client.HTTPException:
                self.close()
                # A connection kept from before may have been closed by the server meanwhile.
                if fresh or attempt == 2:
                    raise Failed("activesync_unreachable") from None
        raise AssertionError

    def _response(self):
        response = self._connection.getresponse()
        return response.status, response.headers, response.read()

    def _headers(self, key: str | None = None) -> dict:
        login = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        return {
            "Authorization": f"Basic {login}",
            "User-Agent": DEVICE,
            "MS-ASProtocolVersion": VERSION,
            "Content-Type": WBXML,
            "X-MS-PolicyKey": self.policy if key is None else key,
        }

    def _answered(self, status: int) -> None:
        if status == 401:
            raise Failed("activesync_login")
        if status == 403:
            raise Failed("activesync_refused")
        if status != 200:
            raise Failed("activesync_unreachable")

    def signed_in(self) -> None:
        """Whether the server speaks the version PONISTRA does and lets the user in."""
        status, headers, _ = self._sent("OPTIONS", PATH, None, self._headers(), self.timeout)
        self._answered(status)
        versions = (headers.get("MS-ASProtocolVersions") or "").replace(" ", "").split(",")
        if VERSION not in versions:
            raise Failed("activesync_version")

    def _post(self, command: str, body: Element, key: str | None, timeout: float):
        query = urlencode(
            {"Cmd": command, "User": self.username, "DeviceId": self.device, "DeviceType": DEVICE}
        )
        given = ("POST", f"{PATH}?{query}", wbxml.encoded(body), self._headers(key), timeout)
        for _ in (1, 2):
            status, headers, data = self._sent(*given, waits=command == "Ping")
            # Ended for the device's next request: a Ping by design, anything else only when
            # it reached the server after a Ping sent just before it.
            if status != 409:
                break
            if command == "Ping":
                raise Interrupted
        if status == 449:
            return None
        self._answered(status)
        if not data or not (headers.get("Content-Type") or "").startswith(WBXML):
            return Element(body.tag)
        try:
            return wbxml.decoded(data)
        except wbxml.Malformed:
            raise Failed("activesync_unreachable") from None

    def command(self, command: str, body: Element, timeout: float | None = None) -> Element:
        """The server's answer to the command, the policy taken first where it asks for it."""
        for attempt in (1, 2):
            answer = self._post(command, body, None, timeout or self.timeout)
            # No answer is the HTTP 449 of a server that wants its policy taken first.
            status = answer.text("Status") if answer is not None else ""
            if status in REFUSED:
                raise Failed("activesync_refused")
            if answer is not None and status not in PROVISION:
                return answer
            if attempt == 2:
                raise Failed("activesync_refused")
            self.provision()
        raise AssertionError

    def provision(self) -> None:
        """Takes the server's policy (MS-ASPROV): asks for it, then says it is applied."""
        asked = self._post(
            "Provision",
            e(
                "Provision:Provision",
                e(
                    "Settings:DeviceInformation",
                    e(
                        "Settings:Set",
                        e("Settings:Model", DEVICE),
                        e("Settings:FriendlyName", DEVICE),
                        e("Settings:OS", DEVICE),
                        e("Settings:UserAgent", DEVICE),
                    ),
                ),
                e("Provision:Policies", e("Provision:Policy", e("Provision:PolicyType", POLICY))),
            ),
            "0",
            self.timeout,
        )
        if asked is None:
            raise Failed("activesync_refused")
        if asked.find("RemoteWipe") is not None:
            self._post(
                "Provision",
                e("Provision:Provision", e("Provision:RemoteWipe", e("Provision:Status", "1"))),
                "0",
                self.timeout,
            )
            raise Wiped
        offered = asked.text("Policies/Policy/PolicyKey")
        if asked.text("Status") != "1" or not offered:
            raise Failed("activesync_refused")
        taken = self._post(
            "Provision",
            e(
                "Provision:Provision",
                e(
                    "Provision:Policies",
                    e(
                        "Provision:Policy",
                        e("Provision:PolicyType", POLICY),
                        e("Provision:PolicyKey", offered),
                        e("Provision:Status", "1"),
                    ),
                ),
            ),
            offered,
            self.timeout,
        )
        key = taken.text("Policies/Policy/PolicyKey") if taken is not None else ""
        if not key:
            raise Failed("activesync_refused")
        self.policy = key
        self.remember(key)
