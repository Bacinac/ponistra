"""A person erased from the installation (GDPR art. 17): their account and everything that is
theirs alone goes, by the database's own cascade; what they wrote for others stays without
their name, and the documents and shared mailboxes nobody else owns pass to an heir the
administrator names."""

import logging

from axes.models import AccessAttempt, AccessFailureLog, AccessLog
from django.db import transaction
from django.db.models import Q

from apps.access.models import Grant, Role
from apps.access.rights import orphaned
from apps.blobs import store
from apps.collab.server import revoke
from apps.core.api import Refused
from apps.core.asyncdb import notify
from apps.documents.models import Node
from apps.documents.views import created
from apps.journal import entries
from apps.mail import sharing, sync
from apps.retention import kept as retention
from apps.vault.models import Collection, Member
from apps.vault.views import settle

from .models import User

log = logging.getLogger(__name__)


def heir_of(user: User, value) -> User | None:
    if value in (None, ""):
        return None
    try:
        pk = int(value)
    except TypeError, ValueError:
        raise Refused(400, "invalid_heir") from None
    heir = User.objects.filter(pk=pk, is_active=True).exclude(pk=user.pk).first()
    if heir is None:
        raise Refused(400, "invalid_heir")
    return heir


def strands_collection(user: User) -> bool:
    """Whether the user is the last living owner of a shared or company collection of the vault,
    which the server cannot hand on: its key is sealed to its members alone."""
    owning = Member.objects.filter(user=user, role=Role.OWN).values("collection")
    living = (
        Member.objects.filter(role=Role.OWN, collection__in=owning)
        .exclude(user=user)
        .filter(Q(user=None) | Q(user__is_active=True))
    )
    return (
        Collection.objects.filter(pk__in=owning)
        .exclude(pk__in=living.values("collection"))
        .exists()
    )


def handed(user: User, heir: User, nodes: list[Node]) -> None:
    """The company's folders the user alone owned are the heir's to own where they stand; the
    user's own documents go into one folder at the top of the heir's, under the user's name,
    with their notes, links and boards as plain folders there."""
    company = [node for node in nodes if node.company]
    for node in company:
        Grant.objects.create(node=node, user=heir, role=Role.OWN, created_by=heir)
    own = [node for node in nodes if not node.company]
    if not own:
        return
    folder = created(None, Node.Kind.FOLDER, user.get_full_name() or user.email, None, heir)
    for node in own:
        node.parent = folder
        node.position = None
        node.notes = node.links = node.boards = False
        node.updated_by = heir
        node.save()


def erase(user: User, heir: User | None, by: User) -> None:
    with transaction.atomic():
        left = list(orphaned(Grant.objects.filter(user=user)))
        boxes = sharing.stranded(user)
        if (left or boxes) and heir is None:
            raise Refused(400, "heir_required")
        if strands_collection(user):
            raise Refused(400, "collection_owner")
        retention.refuse_erasure(user)
        if left:
            handed(user, heir, left)
        if boxes:
            sharing.inherited(boxes, heir)
        for model in (AccessAttempt, AccessFailureLog, AccessLog):
            model.objects.filter(username__iexact=user.email).delete()
        entries.forgotten(user)
        pk = user.pk
        user.delete()
        settle()
        notify(sync.CHANNEL)
    revoke()
    store.collect_later()
    log.info(
        "User %s erased by %s, %d nodes and %d mailboxes to %s",
        pk,
        by.pk,
        len(left),
        len(boxes),
        heir and heir.pk,
    )
