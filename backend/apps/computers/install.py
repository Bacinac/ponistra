"""Add computer (C4.3): the answers of a stick's `install.conf` (ponistra-os
`/usr/share/ponistra-os/install.conf`), checked as the installer checks them, with a one-time
code to enroll in this Ponistra and the admin password of the machine's own page as its
argon2id hash; and where the sticks are downloaded."""

import base64
import binascii
import ipaddress
import os
import re

import httpx2
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from django.conf import settings
from django.http import JsonResponse

from apps.core.api import Refused, api, body

from . import machine, views

RELEASE = "https://download.boskovic.biz/ponistra-os/release.json"
WAIT = 10
SECRET = re.compile(r"[0-9a-fA-F]{64}")
KEY_TYPES = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
}
KEYS = 32


def hashed(password: str) -> str:
    """The agent's cost (`accounts.go`): OWASP's minimum for argon2id, as it runs in 48 MiB."""
    return Argon2id(
        salt=os.urandom(16), length=32, iterations=2, lanes=1, memory_cost=19 * 1024
    ).derive_phc_encoded(password.encode())


def _choice(given: dict, field: str, allowed: tuple[str, ...]) -> str:
    value = given.get(field, "")
    if value not in allowed:
        raise Refused(400, f"invalid_{field}")
    return value


def _text(given: dict, field: str) -> str:
    value = given.get(field, "")
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise Refused(400, f"invalid_{field}")
    return value.strip()


def _hostname(value: str) -> str:
    if value in ("", "auto"):
        return value
    if not machine.NAME.fullmatch(value):
        raise Refused(400, "invalid_name")
    if machine.taken(value):
        raise Refused(409, "name_taken")
    return value


def _network(value: str) -> str:
    fields = value.lower().split()
    if fields == ["dhcp"]:
        return "dhcp"
    try:
        if len(fields) < 3 or fields[1] != "gateway":
            raise ValueError
        address = ipaddress.IPv4Interface(fields[0])
        gateway = ipaddress.IPv4Address(fields[2])
        prefix = address.network.prefixlen
        if not 8 <= prefix <= 30 or address.ip == address.network.network_address:
            raise ValueError
        if gateway not in address.network or gateway == address.ip:
            raise ValueError
        rest = fields[3:]
        if rest and (rest[0] != "dns" or len(rest) == 1):
            raise ValueError
        for each in rest[1:]:
            ipaddress.ip_address(each)
    except ValueError:
        raise Refused(400, "invalid_network") from None
    return " ".join(fields)


def _key(line: str) -> str:
    if line.lower() == "none" or line.startswith("https://"):
        return line
    parts = line.split()
    try:
        blob = base64.b64decode(parts[1], validate=True) if len(parts) > 1 else b""
    except binascii.Error:
        blob = b""
    size = int.from_bytes(blob[:4]) if len(blob) >= 4 else -1
    if parts[:1] and parts[0] in KEY_TYPES and 0 <= size <= len(blob) - 4:
        if blob[4 : 4 + size] == parts[0].encode():
            return line
    raise Refused(400, "invalid_ssh_key")


def _keys(given) -> list[str]:
    if not isinstance(given, list) or len(given) > KEYS:
        raise Refused(400, "invalid_ssh_key")
    if any(not isinstance(each, str) or "\n" in each or "\r" in each for each in given):
        raise Refused(400, "invalid_ssh_key")
    lines = [each.strip() for each in given if each.strip()]
    if len(lines) > 1 and any(each.lower() == "none" for each in lines):
        raise Refused(400, "invalid_ssh_key")
    return [_key(each) for each in lines]


def _wifi_password(value: str) -> str:
    if value and not SECRET.fullmatch(value):
        if not 8 <= len(value) <= 63 or any(not " " <= each <= "~" for each in value):
            raise Refused(400, "invalid_wifi_password")
    return value


def _password(given) -> str:
    if given in (None, ""):
        return ""
    if not isinstance(given, str) or not 8 <= len(given) <= 128:
        raise Refused(400, "invalid_password")
    return hashed(given)


def ponistra_url() -> str:
    if not settings.PUBLIC_URL.startswith("https://"):
        raise Refused(409, "public_url_not_https")
    return settings.PUBLIC_URL + "/"


def answers(given: dict) -> list[tuple[str, str]]:
    role = _choice(given, "role", ("", "server", "workstation"))
    wifi = _text(given, "wifi")
    wifi_password = _wifi_password(_text(given, "wifi_password"))
    if len(wifi.encode()) > 32:
        raise Refused(400, "invalid_wifi")
    if bool(wifi) != bool(wifi_password):
        raise Refused(400, "invalid_wifi")
    if wifi and role == "server":
        raise Refused(400, "wifi_server")
    erase = given.get("erase", False)
    if type(erase) is not bool:
        raise Refused(400, "invalid_erase")
    keys = _keys(given.get("ssh_key", []))
    return [
        ("language", _choice(given, "language", ("en", "hr"))),
        ("keyboard", _choice(given, "keyboard", ("", "us", "hr"))),
        ("role", role),
        ("ponistra_url", ponistra_url()),
        ("disk", "auto"),
        ("erase", "all" if erase else "empty"),
        ("hostname", _hostname(_text(given, "hostname").lower())),
        ("network", _network(_text(given, "network") or "dhcp")),
        ("wifi", wifi),
        ("wifi_password", wifi_password),
        *(("ssh_key", each) for each in keys or [""]),
        ("password", _password(given.get("password"))),
        ("secret", ""),
    ]


def written(lines: list[tuple[str, str]]) -> str:
    return "# Ponistra OS installation\n" + "".join(f"{key} = {value}\n" for key, value in lines)


@api("POST", confirmed=("POST",))
def install(request):
    """An administrator's answers for a new computer's stick: its `install.conf`, carrying a new
    one-time code, shown only now."""
    if not request.user.is_staff:
        raise Refused(403, "forbidden")
    lines = answers(body(request))
    made = views.made(request.user)
    lines.insert(4, ("ponistra_code", made["code"]))
    return JsonResponse({**made, "conf": written(lines)}, status=201)


def _stick(given) -> dict:
    if not isinstance(given, dict):
        raise ValueError
    url, size, digest = given.get("url"), given.get("size"), given.get("sha256")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError
    if type(size) is not int or not isinstance(digest, str) or not SECRET.fullmatch(digest):
        raise ValueError
    return {"url": url, "size": size, "sha256": digest.lower()}


@api("GET")
def sticks(request):
    """The current release's two sticks: the network one, which downloads the system as it
    installs, and the full one, which carries it."""
    try:
        with httpx2.Client(timeout=WAIT, trust_env=False) as client:
            answer = client.get(RELEASE)
            answer.raise_for_status()
            release = answer.json()
        version = release["version"]
        if not isinstance(version, str):
            raise ValueError
        found = {"version": version, **{k: _stick(release[k]) for k in ("network", "full")}}
    except httpx2.HTTPError, ValueError, KeyError, TypeError:
        raise Refused(502, "release_unreachable") from None
    return JsonResponse(found)
