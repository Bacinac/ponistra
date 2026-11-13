from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.api import Refused
from apps.documents.models import Node
from apps.users.models import Policy, User
from apps.users.views import describe as describe_user

from .models import RANK, Grant, Role


def reaching(user) -> Q:
    """Grants that reach the user: their own, their groups', and everyone's. Someone visiting
    from outside (D39) only their own, while the link they came by lasts and the installation
    lets anything out."""
    if user.visitor:
        if Policy.objects.filter(pk=1, outside=Policy.Outside.NOBODY).exists():
            return Q(pk__in=[])
        lasting = Q(link=None) | Q(link__expires_at=None) | Q(link__expires_at__gt=timezone.now())
        return Q(user=user) & lasting
    return Q(user=user) | Q(group__in=user.groups.all()) | Q(user=None, group=None)


def readable(user) -> tuple[str, tuple]:
    """A query for the ids of every live node the user can read: the live subtrees
    under the nodes their grants reach, where everything above is live too."""
    if not user.is_active:
        return "SELECT NULL::uuid AS id WHERE false", ()
    grants, params = Grant.objects.filter(reaching(user)).values("node").query.sql_with_params()
    return (
        f"""
        WITH RECURSIVE up AS (
            SELECT node.id AS start, node.parent_id, node.trashed_at
            FROM documents_node node WHERE node.id IN ({grants})
            UNION ALL
            SELECT up.start, node.parent_id, node.trashed_at
            FROM up JOIN documents_node node ON node.id = up.parent_id
        ),
        down AS (
            SELECT start AS id FROM up GROUP BY start HAVING bool_and(trashed_at IS NULL)
            UNION
            SELECT node.id FROM documents_node node JOIN down ON node.parent_id = down.id
            WHERE node.trashed_at IS NULL
        )
        SELECT id FROM down
        """,
        params,
    )


def strongest(roles: Iterable[str | None]) -> Role | None:
    return max((Role(role) for role in roles if role), key=RANK.__getitem__, default=None)


def covers(role: str | None, needs: Role) -> bool:
    return role is not None and RANK[role] >= RANK[needs]


def held(user, nodes: Iterable[Node]) -> tuple[dict[UUID, Role], set[UUID]]:
    """The strongest role the user's grants give on each of these nodes itself, and the nodes
    where one of them lets what it reaches be downloaded."""
    if not user.is_active:
        return {}, set()
    roles: dict[UUID, Role] = {}
    free: set[UUID] = set()
    found = Grant.objects.filter(reaching(user), node__in=[node.pk for node in nodes])
    for node, role, download in found.values_list("node", "role", "download"):
        roles[node] = strongest([roles.get(node), role])
        if download:
            free.add(node)
    return roles, free


def granted(user, nodes: Iterable[Node]) -> dict[UUID, Role]:
    return held(user, nodes)[0]


@dataclass(frozen=True)
class Reach:
    """What a user's grants give along one node's ancestry, root first."""

    ancestry: list[Node]
    roles: dict[UUID, Role]
    # Whether one of the user's grants along the ancestry lets it be downloaded (D39).
    free: bool = True

    @property
    def copied(self) -> bool:
        """Whether the node is in a copy of a file server's folder or a Google Drive, which only
        reads (D37, D44)."""
        return bool(self.ancestry) and self.ancestry[0].copied

    @property
    def role(self) -> Role | None:
        role = strongest(self.roles.values())
        return Role.READ if role and self.copied else role

    def first(self, needs: Role) -> Node | None:
        """The topmost node from which the user holds at least this role."""
        if self.copied and needs != Role.READ:
            return None
        return next(
            (node for node in self.ancestry if covers(self.roles.get(node.pk), needs)), None
        )

    @property
    def path(self) -> list[Node]:
        top = self.first(Role.READ)
        return [] if top is None else self.ancestry[self.ancestry.index(top) :]

    @property
    def root(self) -> str:
        """Where the path starts: the company's folders, the user's own documents, or what is
        shared with them."""
        top = self.ancestry[0] if self.ancestry else None
        if top is None or top.pk not in self.roles:
            return "shared"
        if top.company:
            return "company"
        return "mine" if self.roles[top.pk] == Role.OWN else "shared"

    @property
    def confined(self) -> bool:
        """Whether a folder on the way, or every grant that gives it to this user, keeps the node
        in the browser for them."""
        return self.role != Role.OWN and (
            not self.free or any(node.confined for node in self.ancestry)
        )

    def escapes(self, into: list[Node], moved: bool = False) -> bool:
        """Whether the node moved below the last of these folders, or what is made from it
        there, would leave every folder that keeps it in the browser; a folder that keeps its
        documents there takes that along when it moves."""
        if not self.confined or (moved and self.ancestry[-1].confined):
            return False
        keeping = {node.pk for node in self.ancestry if node.confined}
        return not keeping & {node.pk for node in into}


def _reach(chain: list[Node], roles: dict[UUID, Role], free: set[UUID]) -> Reach:
    on = {node.pk: roles[node.pk] for node in chain if node.pk in roles}
    return Reach(chain, on, not on or any(node.pk in free for node in chain))


def reach(user, ancestry: list[Node]) -> Reach:
    return _reach(ancestry, *held(user, ancestry))


def reaches(user, ids: Iterable[UUID]) -> dict[UUID, Reach]:
    """Each node's reach, with every ancestry and the user's grants along them read at once."""
    chains = Node.ancestries(ids)
    roles, free = held(user, [node for chain in chains.values() for node in chain])
    return {pk: _reach(chain, roles, free) for pk, chain in chains.items()}


def require(user, ancestry: list[Node], needs: Role) -> Reach:
    reached = reach(user, ancestry)
    if reached.role is None:
        raise Refused(404, "not_found")
    if not covers(reached.role, needs):
        raise Refused(403, "forbidden")
    return reached


def concerned(key: str) -> set[int] | None:
    """Whom a change to the node concerns: the users its grants and its folders' reach, None where
    one reaches everyone, nobody once it is gone (`live`)."""
    node = UUID(key)
    chain = Node.ancestries([node]).get(node, [])
    users: set[int] = set()
    groups: set[int] = set()
    for user, group in Grant.objects.filter(node__in=chain).values_list("user_id", "group_id"):
        if user is None and group is None:
            return None
        if user is None:
            groups.add(group)
        else:
            users.add(user)
    members = User.groups.through.objects.filter(group_id__in=groups)
    return users | set(members.values_list("user_id", flat=True))


def mine(user):
    """The top-level nodes the user owns, outside the company's folders: their own documents."""
    owned = Grant.objects.filter(reaching(user), role=Role.OWN).values("node")
    return Node.objects.filter(parent=None, trashed_at=None, company=False, pk__in=owned)


def company(user):
    """The company's folders the user's grants reach."""
    reached = Grant.objects.filter(reaching(user)).values("node")
    return Node.objects.filter(parent=None, trashed_at=None, company=True, pk__in=reached)


def shared_with(user) -> list[list[Node]]:
    """Ancestries of the topmost live nodes granted to the user that neither their
    own documents, the company's folders nor another of these reaches."""
    candidates = Grant.objects.filter(reaching(user), node__trashed_at=None).values("node")
    chains = Node.ancestries(Node.objects.filter(pk__in=candidates).values_list("pk", flat=True))
    roles = granted(user, [node for chain in chains.values() for node in chain])
    found = []
    for chain in chains.values():
        if not chain[-1].is_live(chain) or any(node.pk in roles for node in chain[:-1]):
            continue
        if len(chain) == 1 and (chain[0].company or roles.get(chain[0].pk) == Role.OWN):
            continue
        found.append(chain)
    return found


def shared_by(user) -> list[list[Node]]:
    """The topmost nodes of the user's own documents that someone besides the user may open."""
    given = (
        Grant.objects.filter(node__trashed_at=None)
        .exclude(user=user)
        .values_list("node", flat=True)
    )
    chains = Node.ancestries(set(given))
    roots = set(mine(user).values_list("pk", flat=True))
    return [
        chain
        for chain in chains.values()
        if chain[0].pk in roots
        and chain[-1].is_live(chain)
        and not any(node.pk in chains for node in chain[:-1])
    ]


def keep_owners(node: Node, ancestry: list[Node], by) -> None:
    """A node that lands at the top keeps the owners it inherited, so nobody loses
    it by a move and every top-level node has an owner."""
    inherited = Grant.objects.filter(node__in=[above.pk for above in ancestry[:-1]], role=Role.OWN)
    for grant in inherited:
        Grant.objects.update_or_create(
            node=node,
            user_id=grant.user_id,
            group_id=grant.group_id,
            defaults={"role": Role.OWN},
            create_defaults={"role": Role.OWN, "created_by": by},
        )


def orphaned(gone: QuerySet[Grant]) -> QuerySet[Node]:
    """The top-level nodes these owner grants would leave without a living owner:
    an active user, a group (which an administrator can refill) or everyone."""
    living = (
        Grant.objects.filter(role=Role.OWN)
        .filter(Q(user=None) | Q(user__is_active=True))
        .exclude(pk__in=gone.values("pk"))
    )
    return Node.objects.filter(
        parent=None, pk__in=gone.filter(role=Role.OWN).values("node")
    ).exclude(pk__in=living.values("node"))


def grantee(grant: Grant) -> dict:
    if grant.user_id:
        return {"kind": "user", **describe_user(grant.user), "outside": grant.user.visitor}
    if grant.group_id:
        return {"kind": "group", "id": grant.group_id, "name": grant.group.name}
    return {"kind": "everyone", "id": None, "name": None}


def key(grant: Grant) -> tuple:
    return grant.user_id, grant.group_id


def audience(grants: Iterable[Grant]) -> dict[tuple, Grant]:
    """The strongest grant per grantee."""
    best: dict[tuple, Grant] = {}
    for grant in grants:
        held = best.get(key(grant))
        if held is None or RANK[grant.role] > RANK[held.role]:
            best[key(grant)] = grant
    return best


def ordered(grants: Iterable[Grant]) -> list[Grant]:
    return sorted(grants, key=lambda grant: (-RANK[grant.role], grantee(grant)["name"] or ""))


def visible_grants(nodes: Iterable[Node]):
    """The grants a node's audience is read from: those of active people, and none a link gave,
    which stands for them itself."""
    return (
        Grant.objects.filter(node__in=[node.pk for node in nodes], link=None)
        .exclude(user__is_active=False)
        .select_related("user", "group")
    )


def listed(user, chains: list[list[Node]]) -> list[dict]:
    """For each node at the end of a chain: the user's role on it, who can open it,
    and whether its own grants open it wider than its folder."""
    nodes = {node for chain in chains for node in chain}
    grants = list(visible_grants(nodes))
    roles = granted(user, nodes)
    on: dict[UUID, list[Grant]] = {}
    for grant in grants:
        on.setdefault(grant.node_id, []).append(grant)
    found = []
    for chain in chains:
        above = [grant for node in chain[:-1] for grant in on.get(node.pk, [])]
        own = on.get(chain[-1].pk, [])
        base = {k: RANK[grant.role] for k, grant in audience(above).items()} or {
            (user.pk, None): RANK[Role.OWN]
        }
        found.append(
            {
                "role": strongest(roles.get(node.pk) for node in chain),
                "audience": [
                    {**grantee(grant), "role": grant.role}
                    for grant in ordered(audience(above + own).values())
                ],
                "wider": any(RANK[grant.role] > base.get(key(grant), 0) for grant in own),
            }
        )
    return found
