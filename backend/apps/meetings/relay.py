"""The relay those joining a meeting go through where nothing reaches LiveKit inward (S2-7): a
TURN service outside the installation, which LiveKit answers by reaching out to it. Cloudflare's
gives credentials of a day for its key; another provider's are fixed. Without one, browsers get
what LiveKit itself offers, its own relay among them where PONISTRA_TURN names one."""

import re
import threading
import time

import httpx2
from django.utils import timezone

from apps.core import sealed

from .models import Relay

SEALED = "meetings relay"
CLOUDFLARE = "https://rtc.live.cloudflare.com/v1/turn/keys/{}/credentials/generate-ice-servers"
LASTING = 24 * 60 * 60
# A meeting keeps the credentials it joined with for as long as it lasts, so they are minted
# anew once less than this is left of them.
LEFT = 12 * 60 * 60
WAIT = 10
# Browsers refuse port 53, so a TURN address on it only holds up the gathering.
REFUSED_PORT = re.compile(r":53(\?|$)")
ADDRESS = re.compile(r"turns?:[^\s?]+(\?transport=(udp|tcp))?")

_minted: dict = {}
_minting = threading.Lock()


class Unavailable(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def setting() -> Relay:
    return Relay.objects.filter(pk=1).first() or Relay()


def opened(found: Relay) -> str | None:
    """The token or password, none where there is none or the installation's secret has
    changed since it was sealed."""
    if not found.secret:
        return None
    return sealed.opened(SEALED, found.secret)


def describe(found: Relay) -> dict:
    return {
        "provider": found.provider,
        "addresses": found.addresses.split(),
        "name": found.name,
        "hint": found.hint,
        "lost": bool(found.secret) and opened(found) is None,
        "changed_at": found.changed_at,
    }


def change(user, provider: str, addresses: list[str], name: str, secret: str | None) -> Relay:
    """Sets the installation's relay, none for LiveKit's own; a secret not given stays as it
    was for the same provider. Cloudflare's key is tried before it is kept."""
    found = setting()
    if provider == Relay.Provider.NONE:
        found.addresses, found.name, found.secret, found.hint = "", "", b"", ""
    else:
        if not name:
            raise Unavailable("relay_name_needed")
        if provider == Relay.Provider.TURN and not addresses:
            raise Unavailable("relay_address_needed")
        if any(not ADDRESS.fullmatch(each) for each in addresses):
            raise Unavailable("invalid_relay_address")
        if secret is None:
            secret = opened(found) if found.provider == provider else None
            if secret is None:
                raise Unavailable("relay_secret_needed")
        if provider == Relay.Provider.CLOUDFLARE:
            addresses = []
            _mint(name, secret)
        found.addresses, found.name = "\n".join(addresses), name
        found.secret, found.hint = sealed.seal(SEALED, secret), secret[-4:]
    found.provider, found.changed_by, found.changed_at = provider, user, timezone.now()
    found.save()
    _minted.clear()
    return found


def servers(found: Relay | None = None) -> list[dict] | None:
    """The ICE servers a browser joins with, none where LiveKit's own serve; refused loudly
    where the relay is set but cannot be had, rather than joining without it."""
    found = found or setting()
    if not found.provider:
        return None
    secret = opened(found)
    if secret is None:
        raise Unavailable("relay_lost")
    if found.provider == Relay.Provider.TURN:
        return [{"urls": found.addresses.split(), "username": found.name, "credential": secret}]
    with _minting:
        if _minted.get("for") != found.changed_at or _minted["until"] - time.time() < LEFT:
            minted = _mint(found.name, secret)
            _minted.update(
                {"for": found.changed_at, "until": time.time() + LASTING, "servers": minted}
            )
        return _minted["servers"]


def client() -> httpx2.Client:
    return httpx2.Client(timeout=WAIT, trust_env=False)


def _mint(key: str, token: str) -> list[dict]:
    try:
        with client() as each:
            answer = each.post(
                CLOUDFLARE.format(key),
                json={"ttl": LASTING},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx2.HTTPError:
        raise Unavailable("relay_unreachable") from None
    if answer.status_code in (400, 401, 403, 404):
        raise Unavailable("relay_refused")
    if not answer.is_success:
        raise Unavailable("relay_unreachable")
    given = answer.json().get("iceServers")
    minted = []
    for server in given if isinstance(given, list) else [given]:
        urls = server.get("urls") if isinstance(server, dict) else None
        urls = [urls] if isinstance(urls, str) else urls or []
        kept = [each for each in urls if not REFUSED_PORT.search(each)]
        if kept:
            minted.append({**server, "urls": kept})
    if not any(each.startswith("turn") for server in minted for each in server["urls"]):
        raise Unavailable("relay_unreachable")
    return minted
