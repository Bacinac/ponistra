"""What the rules of retention and the legal holds keep from deletion, and what a rule removes once
its time has come. Every place that deletes content for good asks here first."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import connection
from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Exists,
    ExpressionWrapper,
    OuterRef,
    Q,
    Value,
    When,
)
from django.db.models.expressions import Expression
from django.utils import timezone

from apps.access.models import Grant, Role
from apps.core.api import Refused
from apps.documents.models import Node

from .models import Hold, Rule, What

KINDS = {Node.Kind.DOCUMENT: What.DOCUMENTS, Node.Kind.FILE: What.FILES}
NODES = {what: kind for kind, what in KINDS.items()}
HELD = "held"
RETAINED = "retained"


@dataclass(frozen=True)
class Policy:
    rules: dict[tuple[str, UUID | None], Rule]
    people: frozenset[int]
    folders: frozenset[UUID]
    now: datetime

    def keep(self, what: str, chain: Iterable[UUID] = ()) -> int | None:
        """The longest any rule over the content keeps it."""
        found = [self.rules.get((what, place)) for place in (None, *chain)]
        days = [rule.keep_days for rule in found if rule and rule.keep_days is not None]
        return max(days, default=None)

    def removal(self, what: str, chain: tuple[UUID, ...] | list[UUID] = ()) -> int | None:
        """The age the rule nearest the content removes it at, never before it may go."""
        nearest = next(
            (self.rules[what, place] for place in reversed(chain) if (what, place) in self.rules),
            self.rules.get((what, None)),
        )
        if nearest is None or nearest.remove_days is None:
            return None
        return max(nearest.remove_days, self.keep(what, chain) or 0)

    def since(self, days: int | None) -> datetime | None:
        return None if days is None else self.now - timedelta(days=days)


def policy() -> Policy:
    holds = list(Hold.objects.values_list("person_id", "folder_id"))
    return Policy(
        {(rule.what, rule.folder_id): rule for rule in Rule.objects.all()},
        frozenset(person for person, _ in holds if person is not None),
        frozenset(folder for _, folder in holds if folder is not None),
        timezone.now(),
    )


@dataclass(frozen=True)
class Placed:
    id: UUID
    kind: str
    updated_at: datetime
    created_by: int | None
    chain: list[UUID]


def _subtrees(roots: list[UUID]) -> dict[UUID, list[Placed]]:
    """Each node with everything below it, trashed or not, as a purge takes it, each with the
    folders above it, root first."""
    chains = {pk: [node.pk for node in chain] for pk, chain in Node.ancestries(roots).items()}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH RECURSIVE tree AS (
                SELECT id AS root, id, parent_id, kind, updated_at, created_by_id, 0 AS depth
                FROM documents_node WHERE id = ANY(%s)
                UNION ALL
                SELECT tree.root, node.id, node.parent_id, node.kind, node.updated_at,
                    node.created_by_id, tree.depth + 1
                FROM documents_node node JOIN tree ON node.parent_id = tree.id
            )
            SELECT root, id, parent_id, kind, updated_at, created_by_id FROM tree ORDER BY depth
            """,
            [list(roots)],
        )
        rows = cursor.fetchall()
    found: dict[UUID, list[Placed]] = {pk: [] for pk in chains}
    for root, pk, parent, kind, updated_at, created_by in rows:
        chain = chains[pk] if pk == root else [*chains[parent], pk]
        chains[pk] = chain
        found[root].append(Placed(pk, kind, updated_at, created_by, chain))
    return found


def _owned(p: Policy, ids: set[UUID]) -> set[UUID]:
    """The nodes among these a held person owns, and so everything below them."""
    if not p.people:
        return set()
    grants = Grant.objects.filter(role=Role.OWN, user_id__in=p.people, node_id__in=ids)
    return set(grants.values_list("node_id", flat=True))


def _node_held(p: Policy, node: Placed, owned: set[UUID]) -> bool:
    return node.created_by in p.people or any(
        place in p.folders or place in owned for place in node.chain
    )


def kept_nodes(roots: Iterable[UUID], p: Policy | None = None) -> dict[UUID, str]:
    """The nodes among these that may not be deleted for good, as a hold or a rule keeps
    something in them, each with the reason."""
    p = p or policy()
    if not (p.rules or p.people or p.folders):
        return {}
    trees = _subtrees(list(roots))
    owned = _owned(p, {place for tree in trees.values() for n in tree for place in n.chain})
    kept: dict[UUID, str] = {}
    for root, tree in trees.items():
        for node in tree:
            if _node_held(p, node, owned):
                kept[root] = HELD
                break
            what = KINDS.get(node.kind)
            since = what and p.since(p.keep(what, node.chain[:-1]))
            if since and node.updated_at > since:
                kept[root] = RETAINED
    return kept


def refuse_nodes(nodes: Iterable[Node]) -> None:
    kept = kept_nodes([node.pk for node in nodes])
    if kept:
        raise Refused(409, HELD if HELD in kept.values() else RETAINED)


def due_nodes(after: UUID | None, most: int, p: Policy) -> tuple[list[UUID], UUID | None]:
    """The documents and files a rule removes, of the next `most` old enough for any rule to,
    and where the next look starts."""
    oldest: dict[str, int] = {}
    for (what, _), rule in p.rules.items():
        kind = NODES.get(what)
        if kind is not None and rule.remove_days is not None:
            oldest[kind] = min(oldest.get(kind, rule.remove_days), rule.remove_days)
    if not oldest:
        return [], None
    old = Q()
    for kind, days in oldest.items():
        old |= Q(kind=kind, updated_at__lt=p.now - timedelta(days=days))
    looked = Node.objects.filter(old).order_by("pk")
    if after is not None:
        looked = looked.filter(pk__gt=after)
    page = list(looked.values_list("pk", flat=True)[:most])
    if not page:
        return [], None
    trees = _subtrees(page)
    owned = _owned(p, {place for tree in trees.values() for n in tree for place in n.chain})
    due = []
    for pk in page:
        node = trees[pk][0]
        since = p.since(p.removal(KINDS[node.kind], node.chain[:-1]))
        if since and node.updated_at < since and not _node_held(p, node, owned):
            due.append(pk)
    kept = kept_nodes(due, p)
    return [pk for pk in due if pk not in kept], page[-1] if len(page) == most else None


def _kept_by_rule(field: str, keep: int | None, p: Policy) -> Q | None:
    since = p.since(keep)
    return None if since is None else Q(**{f"{field}__gt": since})


def mail_kept(owner_id: int, p: Policy | None = None) -> Expression:
    """Whether each of the owner's messages may not be deleted, as an annotation."""
    p = p or policy()
    if owner_id in p.people:
        return Value(True)
    kept = _kept_by_rule("date", p.keep(What.MAIL), p)
    return Value(False) if kept is None else ExpressionWrapper(kept, output_field=BooleanField())


def refuse_mail(owner_id: int, messages) -> None:
    p = policy()
    if owner_id in p.people and messages.exists():
        raise Refused(409, HELD)
    kept = _kept_by_rule("date", p.keep(What.MAIL), p)
    if kept is not None and messages.filter(kept).exists():
        raise Refused(409, RETAINED)


def mail_due(p: Policy) -> Q | None:
    """The messages a rule removes."""
    since = p.since(p.removal(What.MAIL))
    if since is None:
        return None
    return Q(date__lt=since) & ~Q(owner_id__in=p.people)


def _chat_held(p: Policy) -> Q:
    from apps.chat.models import Member

    witnessed = Member.objects.filter(conversation=OuterRef("conversation"), user_id__in=p.people)
    return Q(author_id__in=p.people) | Q(Exists(witnessed))


def chat_kept(p: Policy | None = None) -> Expression:
    """Why each message of a conversation may not be deleted, if it may not, as an annotation."""
    p = p or policy()
    reasons = []
    if p.people:
        reasons.append(When(_chat_held(p), then=Value(HELD)))
    retained = _kept_by_rule("created_at", p.keep(What.CHAT), p)
    if retained is not None:
        reasons.append(When(retained, then=Value(RETAINED)))
    return (
        Case(*reasons, default=None, output_field=CharField())
        if reasons
        else Value(None, CharField())
    )


def chat_message_kept(pk: int) -> str | None:
    from apps.chat.models import Message

    found = Message.objects.filter(pk=pk).annotate(kept=chat_kept())
    return found.values_list("kept", flat=True).first()


def chat_reason(messages, *, editing: bool = False) -> str | None:
    """Why the messages may not be deleted, or one of them said otherwise, which only a hold
    forbids."""
    p = policy()
    if p.people and messages.filter(_chat_held(p)).exists():
        return HELD
    kept = None if editing else _kept_by_rule("created_at", p.keep(What.CHAT), p)
    if kept is not None and messages.filter(kept).exists():
        return RETAINED
    return None


def refuse_chat(messages, *, editing: bool = False) -> None:
    if reason := chat_reason(messages, editing=editing):
        raise Refused(409, reason)


def chat_due(p: Policy) -> Q | None:
    """The messages a rule removes; one with a reply that stays stays with it, as the reply goes
    with what it answers."""
    since = p.since(p.removal(What.CHAT))
    if since is None:
        return None
    due = Q(created_at__lt=since)
    if p.people:
        due &= ~_chat_held(p)
    from apps.chat.models import Message

    staying = Message.objects.filter(parent=OuterRef("pk")).exclude(due)
    return due & ~Q(Exists(staying))


def refuse_erasure(user) -> None:
    """A person under a hold is not erased, nor one whose mail a rule still keeps, as the erasure
    takes their mail with them."""
    from apps.mail.models import Message

    p = policy()
    if user.pk in p.people:
        raise Refused(409, HELD)
    kept = _kept_by_rule("date", p.keep(What.MAIL), p)
    if kept is not None and Message.objects.filter(kept, owner=user).exists():
        raise Refused(409, RETAINED)
