"""The rights a conversation gives over the files of the tree its messages carry: its members read
them while the file and the member are both in it. They are ordinary grants, shown in a file's
access beside the rest; a grant someone gave by hand is never taken for one of these."""

from django.db import transaction

from apps.access import log
from apps.access.models import Grant, Role
from apps.collab.server import revoke

from .models import Attachment, Given, Member


def _wanted(conversation) -> set[tuple]:
    files = Attachment.objects.filter(message__conversation_id=conversation, node__isnull=False)
    nodes = set(files.values_list("node_id", flat=True))
    users = set(
        Member.objects.filter(conversation_id=conversation).values_list("user_id", flat=True)
    )
    return {(node, user) for node in nodes for user in users}


def _settled(conversation, wanted: set[tuple], by) -> None:
    held = {
        (given.grant.node_id, given.grant.user_id): given
        for given in Given.objects.filter(conversation_id=conversation).select_related(
            "grant__node", "grant__user", "grant__group"
        )
    }
    taken = False
    for key, given in held.items():
        if key in wanted:
            continue
        grant = given.grant
        given.delete()
        if not Given.objects.filter(grant=grant).exists():
            log.shared(by, grant, None)
            grant.delete()
            taken = True
    for node, user in wanted - held.keys():
        grant, made = Grant.objects.get_or_create(
            node_id=node, user_id=user, group=None, defaults={"role": Role.READ, "created_by": by}
        )
        if made:
            log.shared(by, grant, Role.READ)
        if made or Given.objects.filter(grant=grant).exists():
            Given.objects.create(conversation_id=conversation, grant=grant)
    if taken:
        transaction.on_commit(revoke)


def granted(conversation, by=None) -> None:
    """Brings the rights the conversation gives in line with its files and its members."""
    _settled(conversation, _wanted(conversation), by)


def withdrawn(conversation, by=None) -> None:
    """Takes back all the conversation gave, before it goes."""
    _settled(conversation, set(), by)
