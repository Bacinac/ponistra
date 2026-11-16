"""Each tab's count of pages in its document's own state, as the print lays them out, so the
tabs after it number on without being opened: the printer counts a document's tabs at once if
they were never counted, else once it has been quiet for PAGES_QUIET or its earliest uncounted
change is PAGES_INTERVAL old, in a session opened for the count as a reader of it. The printer
counts one document at a time, so a document someone has open goes first and the rest by their
oldest change."""

from datetime import datetime
from logging import getLogger

from anyio import sleep, to_thread
from django.conf import settings
from django.db.models import F, Max, Min, OuterRef, Q, Subquery
from django.utils import timezone
from pycrdt import Doc, Map

from apps.access import rights
from apps.collab import server
from apps.collab.models import Update
from apps.content.pages import COUNTS
from apps.content.sheets import Sheets
from apps.core.asyncdb import database
from apps.users import sessions
from apps.versions.models import Contribution

from . import printing
from .models import Node

log = getLogger(__name__)

EVERY = 2


def due(now: datetime) -> list[Node]:
    """Documents never counted, and those changed since their tabs' pages were last counted,
    once quiet for PAGES_QUIET or once their earliest uncounted change is PAGES_INTERVAL old."""
    last_change = Update.objects.filter(document=OuterRef("pk")).order_by("-created_at")
    changed = (
        Node.objects.filter(kind=Node.Kind.DOCUMENT, trashed_at__isnull=True)
        .annotate(changed_at=Subquery(last_change.values("created_at")[:1]))
        .filter(changed_at__isnull=False)
        .filter(Q(paged_at__isnull=True) | Q(changed_at__gt=F("paged_at")))
    )
    documents = []
    for document in changed:
        if document.paged_at is None or now - document.changed_at >= settings.PAGES_QUIET:
            documents.append(document)
            continue
        uncounted = Update.objects.filter(document=document, created_at__gt=document.paged_at)
        first = uncounted.aggregate(first=Min("created_at"))["first"] or document.changed_at
        if now - first >= settings.PAGES_INTERVAL:
            documents.append(document)
    return documents


def reader_of(document: Node):
    """Whoever changed the document last and may still read it, else its author."""
    ancestry = document.ancestry()
    contributions = Contribution.objects.filter(document=document).order_by("-edited_at")
    users = [each.user for each in contributions.select_related("user")]
    if document.created_by is not None:
        users.append(document.created_by)
    return next((user for user in users if rights.reach(user, ancestry).role is not None), None)


def _opened(document: Node) -> tuple[datetime | None, str]:
    """The document's latest change, read before the printer reads its state so a change
    landing in between is counted next pass, and a reader's session to count it in."""
    seen = Update.objects.filter(document=document).aggregate(at=Max("created_at"))["at"]
    reader = reader_of(document)
    if reader is None:
        raise LookupError(f"nobody may read document {document.pk}")
    return seen, sessions.opened(reader, printing.TIMEOUT)


def _current(document: Node) -> bool:
    """The document is still there, live and in the room it was counted for: a reimport or a
    version restored moves it to a fresh room, whose changes are counted again."""
    node = Node.objects.filter(pk=document.pk).first()
    return node is not None and node.room == document.room and node.is_live()


def _counted(document: Node, at: datetime | None) -> None:
    Node.objects.filter(pk=document.pk).update(paged_at=at)


async def count(document: Node) -> None:
    """Writes each tab's count of pages where it differs from the one kept, so a count that
    finds them as they were changes nothing."""
    seen, session = await database(_opened)(document)
    try:
        pages = await to_thread.run_sync(printing.counted, document.pk, session)
    finally:
        await database(sessions.closed)(session)

    def write(own: Doc, sheets: Sheets) -> None:
        counts = own.get(COUNTS, type=Map)
        with own.transaction():
            for tab, pages_of_tab in pages.items():
                if counts.get(tab) != pages_of_tab:
                    counts[tab] = pages_of_tab

    await server.collab.change(str(document.room), write)
    await database(_counted)(document, seen)


def _next(now: datetime, tried: set, open_rooms: set[str]) -> Node | None:
    waiting = [document for document in due(now) if document.pk not in tried]
    return min(
        waiting,
        key=lambda document: (str(document.room) not in open_rooms, document.changed_at),
        default=None,
    )


async def tend(now: datetime | None = None) -> None:
    tried = set()
    while document := await database(_next)(now or timezone.now(), tried, set(server.collab.rooms)):
        tried.add(document.pk)
        try:
            await count(document)
        except Exception:
            if not await database(_current)(document):
                continue
            log.exception("pages: document %s could not be counted", document.pk)
            await database(_counted)(document, document.changed_at)


async def paginate() -> None:
    """Keeps every tab's count of pages following its document while the server runs."""
    while True:
        try:
            await tend()
        except Exception:
            log.exception("pages: a pass failed")
        await sleep(EVERY)
