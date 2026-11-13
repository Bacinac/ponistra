"""Signing in at an OpenID Connect provider (U1): the provider's own description read from its
issuer, the request sent there, and the ID token that comes back checked against its keys."""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx2
import jwt
from django.conf import settings

from apps.core import sealed

from .models import Attempt, Provider
from .people import Person, Refusal

SEALED = "identity provider"
WAIT = httpx2.Timeout(10)
KEPT_FOR = 24 * 3600
ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512")
LEEWAY = 60


def client() -> httpx2.Client:
    return httpx2.Client(timeout=WAIT, trust_env=False)


def _get(url: str) -> dict:
    try:
        with client() as asking:
            answer = asking.get(url, headers={"Accept": "application/json"})
            answer.raise_for_status()
            return answer.json()
    except (httpx2.HTTPError, ValueError) as error:
        raise Refusal("provider_unreachable") from error


def described(provider: Provider, again: bool = False) -> dict:
    """The provider's configuration and keys, read again a day after they were last read or when
    a token names a key they lack."""
    kept = provider.settings.get("discovered") or {}
    if not again and kept and time.time() - kept.get("at", 0) < KEPT_FOR:
        return kept
    issuer = provider.settings["issuer"].rstrip("/")
    found = _get(f"{issuer}/.well-known/openid-configuration")
    if str(found.get("issuer", "")).rstrip("/") != issuer:
        raise Refusal("provider_mismatch")
    for needed in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not str(found.get(needed, "")).startswith("https://") and not settings.DEBUG:
            raise Refusal("provider_mismatch")
    kept = {
        "at": time.time(),
        "issuer": found["issuer"],
        "authorization_endpoint": found["authorization_endpoint"],
        "token_endpoint": found["token_endpoint"],
        "userinfo_endpoint": found.get("userinfo_endpoint", ""),
        "methods": found.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"],
        "algorithms": found.get("id_token_signing_alg_values_supported") or ["RS256"],
        "keys": _get(found["jwks_uri"]),
    }
    provider.settings = {**provider.settings, "discovered": kept}
    provider.save(update_fields=["settings"])
    return kept


def back_to(provider: Provider) -> str:
    return f"{settings.PUBLIC_URL}/api/identity/providers/{provider.pk}/back"


def challenge_of(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def sent(provider: Provider, attempt: Attempt) -> str:
    """Where the browser goes to sign in; a confirmation asks the provider to ask again."""
    attempt.nonce = secrets.token_urlsafe(24)
    attempt.verifier = secrets.token_urlsafe(48)
    asked = {
        "response_type": "code",
        "client_id": provider.settings["client_id"],
        "redirect_uri": back_to(provider),
        "scope": provider.settings.get("scopes") or "openid email profile",
        "state": attempt.state,
        "nonce": attempt.nonce,
        "code_challenge": challenge_of(attempt.verifier),
        "code_challenge_method": "S256",
    }
    if attempt.confirming_id:
        asked["prompt"] = "login"
        asked["max_age"] = "0"
    return f"{described(provider)['authorization_endpoint']}?{urlencode(asked)}"


def secret_of(provider: Provider) -> str:
    secret = provider.sealed and sealed.opened(SEALED, provider.sealed)
    if not secret:
        raise Refusal("provider_secret_lost")
    return secret


def _exchanged(provider: Provider, code: str, attempt: Attempt) -> dict:
    found = described(provider)
    client_id, secret = provider.settings["client_id"], secret_of(provider)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": back_to(provider),
        "code_verifier": attempt.verifier,
    }
    auth = None
    if "client_secret_basic" in found["methods"]:
        auth = httpx2.BasicAuth(client_id, secret)
    else:
        form |= {"client_id": client_id, "client_secret": secret}
    try:
        with client() as asking:
            answer = asking.post(
                found["token_endpoint"],
                data=form,
                auth=auth,
                headers={"Accept": "application/json"},
            )
            answer.raise_for_status()
            given = answer.json()
    except (httpx2.HTTPError, ValueError) as error:
        raise Refusal("provider_refused") from error
    if not isinstance(given, dict) or not isinstance(given.get("id_token"), str):
        raise Refusal("provider_refused")
    return given


def _key(provider: Provider, token: str) -> tuple[object, list[str]]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as error:
        raise Refusal("invalid_token") from error
    allowed = [each for each in described(provider)["algorithms"] if each in ALGORITHMS]
    if header.get("alg") not in allowed:
        raise Refusal("invalid_token")
    for again in (False, True):
        try:
            keys = jwt.PyJWKSet.from_dict(described(provider, again)["keys"])
        except jwt.PyJWTError as error:
            raise Refusal("invalid_token") from error
        for key in keys.keys:
            if header.get("kid") in (None, key.key_id):
                return key, [header["alg"]]
    raise Refusal("invalid_token")


def claims(provider: Provider, token: str, attempt: Attempt) -> dict:
    key, algorithms = _key(provider, token)
    try:
        found = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=provider.settings["client_id"],
            issuer=described(provider)["issuer"],
            leeway=LEEWAY,
            options={"require": ["iss", "aud", "exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise Refusal("invalid_token") from error
    if not secrets.compare_digest(str(found.get("nonce", "")), attempt.nonce):
        raise Refusal("invalid_token")
    return found


def _more(provider: Provider, access: str, subject: str) -> dict:
    """What userinfo adds where the ID token names nobody's address."""
    endpoint = described(provider).get("userinfo_endpoint")
    if not endpoint or not access:
        return {}
    try:
        with client() as asking:
            answer = asking.get(endpoint, headers={"Authorization": f"Bearer {access}"})
            answer.raise_for_status()
            given = answer.json()
    except httpx2.HTTPError, ValueError:
        return {}
    return given if isinstance(given, dict) and given.get("sub") == subject else {}


def _groups(provider: Provider, found: dict) -> list[tuple[str, str]] | None:
    claim = provider.settings.get("groups_claim") or "groups"
    # Entra ID names a source to ask instead of groups too many for a token; the groups held stay.
    if not provider.groups or claim in found.get("_claim_names", {}):
        return None
    given = found.get(claim, [])
    if not isinstance(given, list):
        return None
    return [(str(each), str(each)) for each in given if isinstance(each, str | int)]


def person(provider: Provider, code: str, attempt: Attempt) -> Person:
    given = _exchanged(provider, code, attempt)
    found = claims(provider, given["id_token"], attempt)
    if not found.get("email"):
        found = {**_more(provider, str(given.get("access_token", "")), found["sub"]), **found}
    email = found.get("email") or ""
    # Entra ID names its people by their user principal name, which is their address there.
    if not email and "@" in str(found.get("preferred_username", "")):
        email = found["preferred_username"]
    first, last = found.get("given_name") or "", found.get("family_name") or ""
    if not (first or last) and found.get("name"):
        first, _, last = str(found["name"]).partition(" ")
    return Person(
        subject=str(found["sub"]),
        email=str(email),
        first_name=str(first),
        last_name=str(last),
        groups=_groups(provider, found),
        verified=found.get("email_verified") is not False,
    )
