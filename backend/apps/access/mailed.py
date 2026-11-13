"""Nodes a mail carries as links instead of files (D39): a colleague among its recipients is given
the node inside the installation, and the others come in by one link of the mail's own, each
under their address once a code sent there shows who they are. The recipient sees the node as it
is now, and the sender sees who opened it."""

import html
from dataclasses import dataclass, field

from django.db import transaction

from apps.collab.server import revoke
from apps.core.api import Refused, optional_id
from apps.documents import views as documents

from . import log, outside, visitors
from .models import RANK, Grant, OutsideLink, Role

MOST = 20
# What the composer shows of a node it carries; the mail itself names the node as it is then.
TITLE = 200


@dataclass
class Shared:
    """What a mail's links gave, taken back where the mail does not leave."""

    markup: str = ""
    links: list = field(default_factory=list)
    grants: list = field(default_factory=list)


def given(data: dict) -> list[dict]:
    """The nodes the composer carries as links, each with the role and download it gives."""
    shared = data.get("shared", [])
    if not isinstance(shared, list) or len(shared) > MOST:
        raise Refused(400, "invalid_shared")
    found = []
    for each in shared:
        if not isinstance(each, dict) or each.get("role") not in (Role.READ, Role.EDIT):
            raise Refused(400, "invalid_shared")
        if not isinstance(each.get("download", True), bool):
            raise Refused(400, "invalid_shared")
        title = each.get("title", "")
        if not isinstance(title, str) or len(title) > TITLE:
            raise Refused(400, "invalid_shared")
        found.append(
            {
                "node": str(optional_id(each.get("node"))),
                "title": title,
                "role": each["role"],
                "download": each.get("download", True),
            }
        )
    return found


def _recipients(addresses: list[str]) -> tuple[dict, list[str]]:
    """The recipients' colleagues by address, and the addresses of those outside."""
    inside = {address: visitors.colleague(address) for address in {a.lower() for a in addresses}}
    return inside, sorted(address for address, member in inside.items() if member is None)


def _reached(user, given: dict, outward: list[str]):
    node, reach = documents.live(user, given["node"], Role.OWN)
    if outward and not visitors.outward(user, reach):
        raise Refused(403, "links_not_allowed")
    return node


def checked(user, nodes: list[dict], addresses: list[str]) -> None:
    """Refuses now what sharing the nodes with these recipients would refuse when the mail
    leaves later."""
    _, outward = _recipients(addresses)
    for each in nodes:
        _reached(user, each, outward)


def shared(user, nodes: list[dict], addresses: list[str]) -> Shared:
    made = Shared()
    if not nodes:
        return made
    inside, outward = _recipients(addresses)
    paragraphs = []
    with transaction.atomic():
        for each in nodes:
            node = _reached(user, each, outward)
            for member in {member for member in inside.values() if member and member != user}:
                grant = Grant.objects.filter(node=node, user=member).first()
                if grant is None:
                    grant = Grant(node=node, user=member, created_by=user)
                    made.grants.append(grant)
                elif RANK[grant.role] >= RANK[each["role"]]:
                    continue
                grant.role = each["role"]
                grant.save()
                log.shared(user, grant, grant.role)
            link = outside.made(
                user,
                node,
                OutsideLink.Kind.PEOPLE,
                role=each["role"],
                download=each["download"],
                addresses=outward,
            )
            made.links.append(link)
            url = html.escape(outside.url_of(link))
            paragraphs.append(f'<p><a href="{url}">{html.escape(node.title)}</a></p>')
    if made.grants:
        revoke()
    made.markup = "".join(paragraphs)
    return made


def withdrawn(made: Shared) -> None:
    with transaction.atomic():
        OutsideLink.objects.filter(pk__in=[link.pk for link in made.links]).delete()
        Grant.objects.filter(pk__in=[grant.pk for grant in made.grants]).delete()
    if made.grants:
        revoke()
