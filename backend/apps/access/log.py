"""The log of who opened, downloaded and shared a node, which its owners read."""

from datetime import timedelta

from django.utils import timezone

from .models import Access, Grant, OutsideLink
from .rights import grantee

# Opening the same node again within this is not logged again.
QUIET = timedelta(hours=1)


def opened(user, node) -> None:
    recently = timezone.now() - QUIET
    kind = Access.Kind.OPENED
    if not Access.objects.filter(node=node, user=user, kind=kind, at__gt=recently).exists():
        Access.objects.create(node=node, user=user, kind=kind)


def downloaded(user, node, format: str) -> None:
    Access.objects.create(
        node=node, user=user, kind=Access.Kind.DOWNLOADED, detail={"format": format}
    )


def shared(user, grant: Grant, role: str | None) -> None:
    """A grant given, changed to another role or, with None, taken away."""
    Access.objects.create(
        node=grant.node,
        user=user,
        kind=Access.Kind.SHARED,
        detail={"grantee": grantee(grant), "role": role},
    )


def linked(user, link: OutsideLink, role: str | None) -> None:
    """An outside link made, with the role it gives or `upload` where it asks for files, or, with
    None, ended."""
    Access.objects.create(
        node=link.node,
        user=user,
        kind=Access.Kind.SHARED,
        detail={"link": str(link.pk), "kind": link.kind, "role": role},
    )


def opened_through(link: OutsideLink, user) -> None:
    """Someone signed in by the link, under their address or as anyone who holds it."""
    recently = timezone.now() - QUIET
    kind = Access.Kind.OPENED
    logged = Access.objects.filter(node=link.node, user=user, kind=kind, at__gt=recently)
    if not logged.filter(detail__link=str(link.pk)).exists():
        Access.objects.create(node=link.node, user=user, kind=kind, detail={"link": str(link.pk)})
