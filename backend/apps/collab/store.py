from collections.abc import AsyncIterator, Awaitable, Callable
from logging import Logger, getLogger
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from pycrdt import Doc
from pycrdt.store import BaseYStore

from apps.content import tallies
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab

from .models import Update


class PostgresYStore(BaseYStore):
    """A room's updates as rows in Postgres: a tab's content, or without a tab its
    document's own state. Once the tab or document has moved to another room, what the
    old room still writes stays out of its content."""

    def __init__(
        self,
        path: str,
        document: UUID,
        tab: UUID | None,
        metadata_callback: Callable[[], Awaitable[bytes] | bytes] | None = None,
        log: Logger | None = None,
    ):
        self.path = path
        self.document = document
        self.tab = tab
        self.metadata_callback = metadata_callback
        self.log = log or getLogger(__name__)
        self.changed = False
        # The own state as the room opened with it, which a session leaves unchanged when it
        # writes nothing but what the editors keep of each tab.
        self.opened: bytes | None = None

    async def write(self, data: bytes) -> None:
        self.changed = True
        await database(Update.objects.create)(
            document_id=self.document, tab_id=self.tab, room=self.path, data=data
        )

    async def read(self) -> AsyncIterator[tuple[bytes, bytes, float]]:
        rows = await database(self._rows)()
        for data, created_at in rows:
            yield bytes(data), b"", created_at.timestamp()

    async def compact(self, data: bytes) -> None:
        """Replaces the stored updates with the room's whole state, and marks its
        document modified unless its own state reads as it did; a session that changed
        nothing writes nothing, and a room its holder has left only drops its own rows."""
        if self.changed:
            await database(self._compact)(data)

    def _rows(self):
        updates = Update.objects.filter(room=self.path).order_by("id")
        rows = list(updates.values_list("data", "created_at"))
        if self.tab is None:
            opened = Doc()
            for data, _ in rows:
                opened.apply_update(bytes(data))
            self.opened = opened.get_update()
        return rows

    def _compact(self, data: bytes) -> None:
        with transaction.atomic():
            if self.tab is None:
                holder = Node.objects.select_for_update().filter(pk=self.document).first()
            else:
                holder = Tab.objects.select_for_update().filter(pk=self.tab).first()
            if holder is None:
                return
            if str(holder.room) != self.path:
                Update.objects.filter(room=self.path).delete()
                return
            Update.objects.filter(document=self.document, tab=self.tab).delete()
            Update.objects.create(
                document_id=self.document, tab_id=self.tab, room=holder.room, data=data
            )
            if (
                self.tab is None
                and holder.kind == Node.Kind.DOCUMENT
                and self.opened is not None
                and tallies.written(self.opened) == tallies.written(data)
            ):
                return
            Node.objects.filter(pk=self.document).update(updated_at=timezone.now())
