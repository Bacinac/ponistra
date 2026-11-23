"""A source of Files by the key the page knows it by: a location of the network
(`location:<id>`), a project of the workspace (`workspace:<folder>`) or Ponistra's own tree
(`ponistra:mine|company|shared`, its paths chains of node ids, the last one the node)."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from apps.access.models import Role
from apps.core.api import Refused
from apps.locations import reach
from apps.locations.models import Location
from apps.locations.remote import Remote
from apps.users.sessions import CONFIRMED, CONFIRMED_FOR, fresh
from apps.workspace.remote import Workspace
from apps.workspace.views import CONFIRMED_FOR as WORKSPACE_CONFIRMED_FOR
from apps.workspace.views import owns

KEY = 200
TREES = {"mine", "company", "shared"}


@dataclass(frozen=True)
class Source:
    key: str
    kind: str  # location, workspace, ponistra
    name: str
    # The workspace's project folder, the tree's root.
    of: str
    # How recently a change to it needs the user to have shown who they are (D33), None where
    # Ponistra's own rights hold.
    confirmed_for: timedelta | None
    location: Location | None = None


def source(user, key: object, needs: Role = Role.READ) -> Source:
    """The source the key names, where the user's role on it covers what is done."""
    if not isinstance(key, str) or len(key) > KEY or ":" not in key:
        raise Refused(400, "invalid_source")
    kind, of = key.split(":", 1)
    if kind == "location":
        try:
            pk = uuid.UUID(of)
        except ValueError:
            raise Refused(400, "invalid_source") from None
        found, _ = reach.location(user, pk, needs)
        return Source(f"location:{pk}", kind, found.name, str(pk), CONFIRMED_FOR, found)
    if kind == "workspace":
        if not owns(user):
            raise Refused(403, "not_the_owner")
        folder = Workspace(of).folder
        name = folder.rstrip("/").rsplit("/", 1)[-1] or folder
        return Source(f"workspace:{folder}", kind, name, folder, WORKSPACE_CONFIRMED_FOR)
    if kind == "ponistra" and of in TREES:
        if user.visitor:
            raise Refused(403, "visitors_not_allowed")
        return Source(key, kind, of, of, None)
    raise Refused(400, "invalid_source")


def confirmed(request, changed: list[Source]) -> None:
    """Refuses a change to a source whose own changes wait for a recent confirmation."""
    since = request.session.get(CONFIRMED)
    for each in changed:
        if each.confirmed_for is not None and not fresh(since, each.confirmed_for):
            raise Refused(403, "confirm_required")


async def opened(found: Source) -> Remote:
    """The location signed in to on its server, or the project of the workspace."""
    if found.location is not None:
        return await reach.reached(found.location)
    if found.kind == "workspace":
        return Workspace(found.of)
    raise Refused(400, "invalid_source")
