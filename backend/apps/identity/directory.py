"""An LDAP directory (Active Directory, OpenLDAP) read on a schedule (U1): its people become the
installation's accounts and its groups the installation's groups, and where it says so a
person's password is checked by binding to the directory as them."""

import hashlib
import tempfile
import uuid
from contextlib import suppress
from logging import getLogger
from pathlib import Path

import ldap
from django.db import transaction
from django.utils import timezone
from ldap.controls import SimplePagedResultsControl

from apps.collab.server import revoke
from apps.core import sealed

from . import people
from .models import Identity, Provider
from .people import Person, Refusal

log = getLogger(__name__)

SEALED = "identity directory"
PAGE = 500
WAIT = 15
# Active Directory's userAccountControl bit for an account that is turned off.
DISABLED = 0x2
USERS = "(&(mail=*)(|(objectClass=inetOrgPerson)(&(objectClass=user)(!(objectClass=computer)))))"
GROUPS = "(|(objectClass=group)(objectClass=groupOfNames)(objectClass=groupOfUniqueNames))"
IDS = ("objectGUID", "entryUUID")
MEMBERS = ("member", "uniqueMember")


def _ca(pem: str) -> str:
    """The file the directory's certificate authority is read from, as the client library reads
    no other way."""
    named = hashlib.sha256(pem.encode()).hexdigest()
    path = Path(tempfile.gettempdir()) / f"ponistra-ldap-{named}.pem"
    if not path.exists():
        path.write_text(pem)
    return str(path)


def connected(provider: Provider):
    found = provider.settings
    connection = ldap.initialize(found["url"])
    connection.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
    connection.set_option(ldap.OPT_REFERRALS, 0)
    connection.set_option(ldap.OPT_NETWORK_TIMEOUT, WAIT)
    connection.set_option(ldap.OPT_TIMEOUT, WAIT)
    connection.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
    if found.get("ca"):
        connection.set_option(ldap.OPT_X_TLS_CACERTFILE, _ca(found["ca"]))
    connection.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
    try:
        if found.get("starttls"):
            connection.start_tls_s()
    except ldap.LDAPError as error:
        raise Refusal(failure(error)) from error
    return connection


def closed(connection) -> None:
    with suppress(ldap.LDAPError):
        connection.unbind_s()


def failure(error: Exception) -> str:
    if isinstance(error, ldap.INVALID_CREDENTIALS):
        return "directory_refused"
    if isinstance(error, ldap.SERVER_DOWN | ldap.TIMEOUT | ldap.CONNECT_ERROR):
        return "directory_unreachable"
    return "directory_failed"


def bound(provider: Provider):
    """A connection signed in as the account the installation reads the directory with."""
    password = provider.sealed and sealed.opened(SEALED, provider.sealed)
    if not password:
        raise Refusal("provider_secret_lost")
    connection = connected(provider)
    try:
        connection.simple_bind_s(provider.settings["bind_dn"], password)
    except ldap.LDAPError as error:
        closed(connection)
        raise Refusal(failure(error)) from error
    return connection


def tried(provider: Provider) -> None:
    """Signs in to the directory and reads one entry, as an administrator saves its settings."""
    connection = bound(provider)
    try:
        connection.search_ext_s(
            provider.settings["base_dn"],
            ldap.SCOPE_BASE,
            "(objectClass=*)",
            ["1.1"],
            sizelimit=1,
        )
    except ldap.LDAPError as error:
        raise Refusal(failure(error)) from error
    finally:
        closed(connection)


def searched(connection, base: str, condition: str, attributes: list[str]):
    """Every entry the search finds, a page at a time, as Active Directory gives no more than a
    thousand at once."""
    paging = SimplePagedResultsControl(True, size=PAGE, cookie="")
    while True:
        asked = connection.search_ext(
            base, ldap.SCOPE_SUBTREE, condition, attributes, serverctrls=[paging]
        )
        _, found, _, controls = connection.result3(asked)
        for name, values in found:
            # A referral to another server comes back without a name.
            if name:
                yield name, values
        cookie = next(
            (
                each.cookie
                for each in controls
                if each.controlType == SimplePagedResultsControl.controlType
            ),
            None,
        )
        if not cookie:
            return
        paging.cookie = cookie


def _first(values: dict, name: str) -> str:
    found = values.get(name) or []
    return found[0].decode("utf-8", "replace").strip() if found else ""


def subject_of(name: str, values: dict) -> str:
    """What names an entry for good: Active Directory's objectGUID, OpenLDAP's entryUUID, or else
    its DN."""
    if values.get("objectGUID"):
        return str(uuid.UUID(bytes_le=values["objectGUID"][0]))
    return _first(values, "entryUUID") or name.lower()


def person_of(provider: Provider, name: str, values: dict) -> Person:
    found = provider.settings
    control = _first(values, "userAccountControl")
    return Person(
        subject=subject_of(name, values),
        email=_first(values, found.get("email_attribute") or "mail"),
        first_name=_first(values, "givenName"),
        last_name=_first(values, "sn"),
        active=not (control.isdigit() and int(control) & DISABLED),
        detail={"dn": name},
    )


def _attributes(provider: Provider) -> list[str]:
    email = provider.settings.get("email_attribute") or "mail"
    return list(dict.fromkeys([email, "givenName", "sn", "userAccountControl", *IDS]))


def synced(provider_id: int) -> None:
    """Reads the directory's people and groups into the installation. Nothing changes unless the
    whole directory was read: a search that fails half way leaves everyone as they were."""
    provider = Provider.objects.filter(pk=provider_id, kind=Provider.Kind.LDAP).first()
    if provider is None:
        return
    found = provider.settings
    connection = bound(provider)
    try:
        entries = list(
            searched(
                connection,
                found["base_dn"],
                found.get("user_filter") or USERS,
                _attributes(provider),
            )
        )
        groups = (
            list(
                searched(
                    connection,
                    found.get("group_base_dn") or found["base_dn"],
                    found.get("group_filter") or GROUPS,
                    ["cn", *MEMBERS, *IDS],
                )
            )
            if provider.groups
            else []
        )
    except ldap.LDAPError as error:
        raise Refusal(failure(error)) from error
    finally:
        closed(connection)
    listed: dict[str, int] = {}
    for name, values in entries:
        try:
            user = people.kept(provider, person_of(provider, name, values))
        except Refusal:
            continue
        listed[name.lower()] = user.pk
        # Its password is the directory's; an administrator keeps their own for when the
        # directory cannot be reached.
        if found.get("sign_in") and not user.is_staff and user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=["password"])
    for identity in (
        Identity.objects.filter(provider=provider)
        .exclude(user__in=listed.values())
        .select_related("user")
    ):
        people.left(provider, identity.user)
    if provider.groups:
        _grouped(provider, groups, listed)
    provider.synced_at, provider.error = timezone.now(), ""
    provider.save(update_fields=["synced_at", "error"])
    revoke()


def _grouped(provider: Provider, groups: list, listed: dict[str, int]) -> None:
    kept = set()
    with transaction.atomic():
        for name, values in groups:
            group = people.group(provider, subject_of(name, values), _first(values, "cn"))
            members = {
                listed[member.decode("utf-8", "replace").lower()]
                for attribute in MEMBERS
                for member in values.get(attribute, [])
                if member.decode("utf-8", "replace").lower() in listed
            }
            group.user_set.set(members)
            kept.add(group.pk)
    for each in provider.kept.exclude(group__in=kept).select_related("group"):
        people.gone(provider, each.group)


def checked(provider: Provider, name: str, password: str) -> bool:
    """Whether the password is the directory's for the entry, by binding as it. An empty
    password would bind anonymously, which proves nothing."""
    if not password:
        return False
    connection = connected(provider)
    try:
        connection.simple_bind_s(name, password)
    except ldap.INVALID_CREDENTIALS:
        return False
    except ldap.LDAPError as error:
        raise Refusal(failure(error)) from error
    finally:
        closed(connection)
    return True
