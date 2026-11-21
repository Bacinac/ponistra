"""Removes for good, every hour, what a rule of retention says is old enough to go (U4), and
trashes what was opened from the computer and left in no folder (D53)."""

from datetime import timedelta
from logging import getLogger

from anyio import sleep
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from apps.access.models import Access
from apps.blobs import store
from apps.chat import files
from apps.chat.models import Conversation, Member
from apps.chat.models import Message as Said
from apps.collab.server import revoke
from apps.core.asyncdb import database
from apps.documents.models import Node
from apps.mail import forgetting, reactions
from apps.mail.models import Message as Mail

from . import kept
from .models import Removal

log = getLogger(__name__)

EVERY = timedelta(hours=1)
PAGE = 500
UNPLACED_FOR = timedelta(days=30)


def _nodes(p: kept.Policy, removal: Removal) -> None:
    after = None
    while True:
        due, after = kept.due_nodes(after, PAGE, p)
        if due:
            gone = Node.objects.filter(pk__in=due)
            counted = dict(gone.values_list("kind").annotate(count=Count("pk")).order_by())
            gone.delete()
            removal.documents += counted.get(Node.Kind.DOCUMENT, 0)
            removal.files += counted.get(Node.Kind.FILE, 0)
        if after is None:
            return


def _mail(p: kept.Policy, removal: Removal) -> None:
    due = kept.mail_due(p)
    if due is None:
        return
    found = Mail.objects.filter(due).exclude(reactions.ATTACHED)
    for owner in found.values_list("owner_id", flat=True).distinct().order_by():
        removal.mail += forgetting.forgotten(owner, found.filter(owner_id=owner))


def _chat(p: kept.Policy, removal: Removal) -> None:
    due = kept.chat_due(p)
    if due is None:
        return
    with transaction.atomic():
        gone = Said.objects.filter(due)
        touched = set(gone.values_list("conversation_id", flat=True).distinct().order_by())
        removal.chat += gone.delete()[1].get(Said._meta.label, 0)
        for conversation in touched:
            files.granted(conversation)
        Conversation.objects.filter(pk__in=touched).update(changed_at=timezone.now())
        left = Member.objects.filter(conversation=OuterRef("pk"))
        said = Said.objects.filter(conversation=OuterRef("pk"))
        empty = Conversation.objects.filter(pk__in=touched).exclude(Exists(left) | Exists(said))
        empty.exclude(kind=Conversation.Kind.CHANNEL, private=False).delete()


def swept() -> Removal | None:
    p = kept.policy()
    if not any(rule.remove_days is not None for rule in p.rules.values()):
        return None
    removal = Removal()
    _nodes(p, removal)
    _mail(p, removal)
    _chat(p, removal)
    if not (removal.documents or removal.files or removal.mail or removal.chat):
        return None
    removal.save()
    if removal.documents or removal.files:
        store.collect_later()
        revoke()
    log.info(
        "retention removed %d documents, %d files, %d messages, %d said",
        removal.documents,
        removal.files,
        removal.mail,
        removal.chat,
    )
    return removal


def abandoned() -> int:
    """Trashes the documents and files opened from the computer that nobody saved into a folder,
    opened or changed for `UNPLACED_FOR`."""
    now = timezone.now()
    since = now - UNPLACED_FOR
    opened = Access.objects.filter(node=OuterRef("pk"), kind=Access.Kind.OPENED, at__gte=since)
    left = Node.objects.filter(
        unplaced=True, trashed_at=None, created_at__lt=since, updated_at__lt=since
    ).exclude(Exists(opened))
    trashed = left.update(trashed_at=now)
    if trashed:
        revoke()
        log.info("retention trashed %d documents and files left unplaced", trashed)
    return trashed


async def sweeping() -> None:
    while True:
        try:
            await database(abandoned, own_thread=True)()
        except Exception:
            log.exception("retention: trashing what was left unplaced failed")
        try:
            await database(swept, own_thread=True)()
        except Exception:
            log.exception("retention: the sweep failed")
        await sleep(EVERY.total_seconds())
