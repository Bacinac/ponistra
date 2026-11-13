"""The administrator's list of where the installation's people come from besides its own
accounts (U1): each provider's settings, checked against the provider as they are saved, and
what the provider is to be told of the installation."""

import re
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponse, JsonResponse

from apps.core import sealed
from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator

from . import directories, directory, oidc, saml, scim
from .models import Provider
from .people import Refusal

DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
SHOWN = {
    Provider.Kind.OIDC: ("issuer", "client_id", "scopes", "groups_claim"),
    Provider.Kind.SAML: (
        "metadata_url",
        "entity_id",
        "sso_url",
        "email_attribute",
        "groups_attribute",
    ),
    Provider.Kind.LDAP: (
        "url",
        "starttls",
        "bind_dn",
        "base_dn",
        "user_filter",
        "group_base_dn",
        "group_filter",
        "email_attribute",
        "sign_in",
        "every",
        "ca",
    ),
    Provider.Kind.SCIM: (),
}
SECRETS = {Provider.Kind.OIDC: oidc.SEALED, Provider.Kind.LDAP: directory.SEALED}
LONGEST = 2000


def _here(provider: Provider) -> dict:
    """What the provider is told of the installation."""
    if provider.kind == Provider.Kind.OIDC:
        return {"redirect_uri": oidc.back_to(provider)}
    if provider.kind == Provider.Kind.SAML:
        return {
            "entity_id": saml.entity_of(provider),
            "acs_url": saml.consumer_of(provider),
            "metadata_url": saml.entity_of(provider),
        }
    if provider.kind == Provider.Kind.SCIM:
        return {"scim_url": scim.base()}
    return {}


def describe(provider: Provider) -> dict:
    return {
        "id": provider.pk,
        "name": provider.name,
        "kind": provider.kind,
        "enabled": provider.enabled,
        "creates": provider.creates,
        "groups": provider.groups,
        "domains": provider.domains,
        "settings": {
            name: provider.settings[name]
            for name in SHOWN[provider.kind]
            if name in provider.settings
        },
        "certificates": len(provider.settings.get("certificates", [])),
        "has_secret": bool(provider.sealed or provider.token_digest),
        "people": provider.identities.count(),
        "here": _here(provider),
        "created_at": provider.created_at,
        "synced_at": provider.synced_at,
        "error": provider.error,
    }


def _text(given: dict, name: str, required: bool = False, longest: int = 500) -> str:
    value = given.get(name, "")
    if not isinstance(value, str) or len(value.strip()) > longest:
        raise Refused(400, f"invalid_{name}")
    value = value.strip()
    if required and not value:
        raise Refused(400, f"{name}_required")
    return value


def _flag(given: dict, name: str, default: bool = False) -> bool:
    value = given.get(name, default)
    if not isinstance(value, bool):
        raise Refused(400, f"invalid_{name}")
    return value


def _address(given: dict, name: str, schemes: tuple[str, ...], required: bool = True) -> str:
    value = _text(given, name, required)
    if value:
        parts = urlsplit(value)
        if parts.scheme not in schemes or not parts.hostname:
            raise Refused(400, f"invalid_{name}")
    return value


def _domains(given) -> list[str]:
    if not isinstance(given, list) or not all(isinstance(each, str) for each in given):
        raise Refused(400, "invalid_domains")
    found = list(dict.fromkeys(each.strip().lower().lstrip("@") for each in given if each.strip()))
    if not all(DOMAIN.match(each) for each in found):
        raise Refused(400, "invalid_domains")
    return found


def _secure() -> tuple[str, ...]:
    return ("https", "http") if settings.DEBUG else ("https",)


def _settings(kind: str, given: dict, was: dict, enabled: bool) -> dict:
    """The kind's settings from what the administrator gave; what is read from the provider
    itself (an OIDC description, SAML metadata) is read anew as they are saved. A provider saved
    off may lack what it is told only once it knows the installation's addresses for it."""
    if kind == Provider.Kind.OIDC:
        return {
            "issuer": _address(given, "issuer", _secure()).rstrip("/"),
            "client_id": _text(given, "client_id", required=enabled),
            "scopes": _text(given, "scopes") or "openid email profile",
            "groups_claim": _text(given, "groups_claim") or "groups",
        }
    if kind == Provider.Kind.SAML:
        found = {
            "metadata_url": _address(given, "metadata_url", _secure(), required=False),
            "email_attribute": _text(given, "email_attribute"),
            "groups_attribute": _text(given, "groups_attribute"),
        }
        metadata = given.get("metadata", "")
        if not isinstance(metadata, str):
            raise Refused(400, "invalid_metadata")
        try:
            if metadata.strip():
                found |= saml.described(metadata.strip().encode())
            elif found["metadata_url"]:
                found |= saml.fetched(found["metadata_url"])
            elif was.get("entity_id"):
                found |= {name: was[name] for name in ("entity_id", "sso_url", "certificates")}
            elif enabled:
                raise Refused(400, "metadata_required")
        except Refusal as refusal:
            raise Refused(400, refusal.code) from None
        return found
    if kind == Provider.Kind.LDAP:
        url = _address(given, "url", ("ldaps", "ldap"))
        starttls = _flag(given, "starttls")
        if urlsplit(url).scheme == "ldap" and not starttls:
            raise Refused(400, "unencrypted_directory")
        every = given.get("every", directories.EVERY_MINUTES)
        if not isinstance(every, int) or not 5 <= every <= 24 * 60:
            raise Refused(400, "invalid_every")
        return {
            "url": url,
            "starttls": starttls,
            "bind_dn": _text(given, "bind_dn", required=True),
            "base_dn": _text(given, "base_dn", required=True),
            "user_filter": _text(given, "user_filter", longest=LONGEST),
            "group_base_dn": _text(given, "group_base_dn"),
            "group_filter": _text(given, "group_filter", longest=LONGEST),
            "email_attribute": _text(given, "email_attribute"),
            "sign_in": _flag(given, "sign_in"),
            "every": every,
            "ca": _text(given, "ca", longest=20000),
        }
    return {}


def _filled(provider: Provider, given: dict) -> str | None:
    """Sets what the request carries; returns the SCIM token where a new one was made."""
    provider.name = _text(given, "name", required=True, longest=150)
    provider.enabled = _flag(given, "enabled", True)
    provider.creates = _flag(given, "creates", provider.kind == Provider.Kind.SCIM)
    provider.groups = _flag(given, "groups")
    provider.domains = _domains(given.get("domains", []))
    if provider.creates and provider.signs_in and not provider.domains:
        # Anyone with an account at a public provider would otherwise get one here.
        raise Refused(400, "domains_required")
    kept = provider.settings.get("discovered")
    provider.settings = _settings(provider.kind, given, provider.settings, provider.enabled)
    if kept and provider.kind == Provider.Kind.OIDC:
        provider.settings["discovered"] = kept
    if provider.kind in SECRETS and given.get("secret"):
        provider.sealed = sealed.seal(SECRETS[provider.kind], _text(given, "secret"))
    if provider.kind in SECRETS and provider.enabled and not provider.sealed:
        raise Refused(400, "secret_required")
    if provider.kind == Provider.Kind.SCIM and not provider.token_digest:
        return _token(provider)
    return None


def _token(provider: Provider) -> str:
    token = secrets.token_urlsafe(32)
    provider.token_digest = scim.digest(token)
    return token


def _tried(provider: Provider) -> None:
    """The provider asked once as it is saved, so a wrong setting is told now and not at the
    first sign-in."""
    if not provider.enabled:
        return
    try:
        if provider.kind == Provider.Kind.OIDC:
            provider.settings.pop("discovered", None)
            oidc.described(provider, again=True)
        elif provider.kind == Provider.Kind.LDAP:
            directory.tried(provider)
    except Refusal as refusal:
        raise Refused(400, refusal.code) from None


def _saved(provider: Provider, token: str | None, status: int = 200) -> JsonResponse:
    if provider.kind == Provider.Kind.LDAP:
        provider.synced_at = None
    provider.error = ""
    provider.save()
    if provider.kind == Provider.Kind.LDAP:
        directories.wake()
    answer = describe(provider)
    if token:
        answer["token"] = token
    return JsonResponse(answer, status=status)


@api("GET", "POST", confirmed=("POST",))
def providers(request):
    administrator(request)
    if request.method == "GET":
        found = Provider.objects.order_by("name", "pk")
        return JsonResponse({"providers": [describe(each) for each in found]})
    given = body(request)
    if given.get("kind") not in Provider.Kind.values:
        raise Refused(400, "invalid_kind")
    provider = Provider(kind=given["kind"])
    token = _filled(provider, given)
    if provider.kind == Provider.Kind.OIDC:
        # The redirect address names the provider by its id, so it is asked once it has one.
        provider.save()
        try:
            _tried(provider)
        except Refused:
            provider.delete()
            raise
    else:
        _tried(provider)
    entries.wrote(Kind.PROVIDER_ADDED, request=request, name=provider.name, way=provider.kind)
    return _saved(provider, token, 201)


def _found(pk: int) -> Provider:
    found = Provider.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


@api("PATCH", "DELETE", confirmed=("PATCH", "DELETE"))
def provider(request, pk: int):
    """A provider changed, or removed: the people and groups it brought stay, as the
    installation's own."""
    administrator(request)
    found = _found(pk)
    if request.method == "DELETE":
        found.delete()
        entries.wrote(Kind.PROVIDER_REMOVED, request=request, name=found.name, way=found.kind)
        return HttpResponse(status=204)
    _filled(found, body(request))
    _tried(found)
    entries.wrote(Kind.PROVIDER_CHANGED, request=request, name=found.name, way=found.kind)
    return _saved(found, None)


@api("POST", confirmed=("POST",))
def token(request, pk: int):
    """A new token for a SCIM directory, the old one no longer accepted."""
    administrator(request)
    found = _found(pk)
    if found.kind != Provider.Kind.SCIM:
        raise Refused(400, "not_scim")
    made = _token(found)
    found.save(update_fields=["token_digest"])
    entries.wrote(Kind.PROVIDER_SECRET, request=request, name=found.name, way=found.kind)
    return JsonResponse({**describe(found), "token": made})


@api("POST")
def synced(request, pk: int):
    """Reads an LDAP directory, or a SAML provider's metadata, now rather than at its turn."""
    administrator(request)
    found = _found(pk)
    if found.kind not in (Provider.Kind.LDAP, Provider.Kind.SAML):
        raise Refused(400, "not_synced")
    found.synced_at = None
    found.save(update_fields=["synced_at"])
    directories.wake()
    return JsonResponse(describe(found))
