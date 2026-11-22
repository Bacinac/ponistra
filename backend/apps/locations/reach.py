"""Who reaches a location and with what role, and the location reached on its server."""

from django.contrib.auth.models import Group
from django.db.models import Q

from apps.access.models import RANK, Role
from apps.core.api import Refused
from apps.core.asyncdb import database
from apps.core.sealed import opened

from . import sftp, smbfiles
from .models import Grant, Location
from .remote import Failed, Remote

SEALED = "location"


def _reaching(user) -> Q:
    return Q(user=user) | Q(group__in=user.groups.all()) | Q(user=None, group=None)


def roles(user) -> dict:
    """The locations the user reaches, each with the highest role they hold on it."""
    if user.visitor:
        return {}
    found = {
        pk: Role.OWN for pk in Location.objects.filter(owner=user).values_list("pk", flat=True)
    }
    for location, role in Grant.objects.filter(_reaching(user)).values_list("location", "role"):
        if location not in found or RANK[role] > RANK[found[location]]:
            found[location] = Role(role)
    return found


def role_on(user, location: Location) -> Role | None:
    if user.visitor:
        return None
    if location.owner_id == user.pk:
        return Role.OWN
    held = Grant.objects.filter(_reaching(user), location=location).values_list("role", flat=True)
    return max(held, key=lambda role: RANK[role], default=None)


def location(user, pk, needs: Role = Role.READ) -> tuple[Location, Role]:
    """The location the request names, where the user's role covers what it does."""
    found = Location.objects.select_related("owner").filter(pk=pk).first()
    role = found and role_on(user, found)
    if role is None:
        raise Refused(404, "not_found")
    if RANK[role] < RANK[needs]:
        raise Refused(403, "forbidden")
    return found, role


def target(found: Location, secret: str) -> sftp.Target:
    key = found.auth == Location.Auth.KEY
    return sftp.Target(
        host=found.host,
        port=found.port,
        user=found.username,
        path=found.path,
        password=None if key else secret,
        key=secret if key else None,
        jump=found.jump,
        known_hosts=found.known_hosts,
    )


def _known(pk, known_hosts: str) -> None:
    Location.objects.filter(pk=pk).update(known_hosts=known_hosts)


def key_of(found: Location) -> str:
    return f"{found.pk}:{found.changed_at.timestamp()}"


async def reached(found: Location) -> Remote:
    """The location signed in to on its server; an SFTP server's host keys first found are kept,
    so that another one later is refused as the server's identity changed."""
    secret = opened(SEALED, found.secret)
    if secret is None:
        raise Failed("location_secret_lost")
    if found.kind == Location.Kind.SMB:
        return await smbfiles.reached(found.host, found.port, found.path, found.username, secret)
    link = await sftp.connection(key_of(found), target(found, secret))
    if (known := link.known_hosts()) != found.known_hosts:
        await database(_known)(found.pk, known)
    return sftp.Sftp(link)


async def tried(found: Location, secret: str) -> str:
    """Signs in with a secret not yet kept, and gives the host keys the server showed."""
    if found.kind == Location.Kind.SMB:
        remote = await smbfiles.reached(found.host, found.port, found.path, found.username, secret)
        await remote.close()
        return ""
    link = sftp.Connection(target(found, secret))
    try:
        await link.open()
        return link.known_hosts()
    finally:
        link.end(link.failure or Failed("location_closed"))


def concerned(key: str) -> set[int] | None:
    """Whom a change to a location concerns: its owner and those it is shared with, None where it
    is shared with everyone (`live`)."""
    owner = Location.objects.filter(pk=key).values_list("owner_id", flat=True).first()
    users: set[int] = {owner} if owner else set()
    groups: set[int] = set()
    for user, group in Grant.objects.filter(location_id=key).values_list("user_id", "group_id"):
        if user is None and group is None:
            return None
        if user is None:
            groups.add(group)
        else:
            users.add(user)
    members = Group.user_set.through.objects.filter(group_id__in=groups)
    return users | set(members.values_list("user_id", flat=True))
