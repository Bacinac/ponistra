"""Tabs written as an importer writes them (D16): the text into a Yjs state and the tables'
grids into sheets; a tab of the database keeps them as its room's updates and its grids, its
document the defined names, and a room changes them as its server does."""

from collections.abc import Callable
from datetime import datetime

from pycrdt import Doc

from apps.collab import server
from apps.collab.models import Update
from apps.content import blocks, grids, names, placing
from apps.content.blocks import Block
from apps.content.grids import Laid
from apps.content.models import GridRow, Name
from apps.content.operations import (
    Change,
    Prepared,
    Proposer,
    TakeBack,
    carry_out,
    take_back,
    write,
)
from apps.content.sheets import Sheets, apply_stored
from apps.content.table import tables_of
from apps.core.asyncdb import database
from apps.documents.models import Node


def written(
    content: list[Block], doc: Doc | None = None, sheets: Sheets | None = None, **given
) -> tuple[Doc, dict[str, Laid]]:
    """The doc with the blocks written at the end of its text, and every grid there is."""
    doc = Doc() if doc is None else doc
    sheets = Sheets({}) if sheets is None else sheets
    doc.apply_update(write(doc, sheets, content, **given).update)
    return doc, dict(sheets.tables())


def fill(
    tab,
    content: list[Block],
    at: datetime | None = None,
    then: Callable[[Doc], None] | None = None,
) -> tuple[Doc, blocks.Written]:
    """Replaces the tab's text and grids with the blocks, the way a room would leave them,
    the text changed then as given, and where the blocks' text went."""
    Update.objects.filter(room=tab.room).delete()
    tab.grids.all().delete()
    doc, sheets = Doc(), Sheets({})
    prepared = write(doc, sheets, content)
    doc.apply_update(prepared.update)
    if then is not None:
        then(doc)
    edit(tab, doc.get_update(), at)
    for _, laid in sheets.tables():
        grids.put(tab.document, str(tab.pk), laid)
    if at is not None:
        tab.grids.update(edited_at=at)
    return doc, prepared.written


async def afill(tab, content: list[Block], at: datetime | None = None):
    return await database(fill)(tab, content, at)


def regrid(tab, *operations: dict) -> None:
    """The tab's grids changed by the operations, as a browser's edit of its cells changes
    them: its text untouched."""
    server.change(
        tab.room, lambda doc, sheets: carry_out(doc, sheets, list(operations), "hr", "run")
    )


def edit(tab, data: bytes = b"\x00\x00", at: datetime | None = None) -> None:
    update = Update.objects.create(document_id=tab.document_id, tab=tab, room=tab.room, data=data)
    if at is not None:
        Update.objects.filter(pk=update.pk).update(created_at=at)


class Room:
    """A tab's state and grids, and its document's defined names, as its room's server holds
    them, changed as it changes them: a change prepared on them, its patches applied, then the
    rest committed."""

    # Whether rooms keep their grids in Postgres, as a book does, rather than whole in memory.
    stored = False

    def __init__(self, *content: Block, defined: dict[str, dict] | None = None):
        self.doc, self.grids = written(list(content), Doc(skip_gc=True))
        self.names: dict[str, dict] = dict(defined or {})
        self.tab: str | None = None
        self.document = None
        if self.stored:
            self.document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Soba")
            for laid in self.grids.values():
                grids.put(self.document, laid.tab, laid)

    @classmethod
    def of(cls, tab) -> Room:
        """The tab's room as the server holds it, live or stored."""
        mine = str(tab.pk)
        update, held, defined = server.read_grids(
            tab.room,
            lambda doc, found: (
                doc.get_update(),
                {id: laid.copy() for id, laid in found.grids().items() if laid.tab == mine},
                dict(found.names()),
            ),
        )
        room = cls(defined=defined)
        room.doc.apply_update(update)
        room.grids, room.tab = held, mine
        if cls.stored:
            room.document = tab.document
        return room

    def keep(self, tab) -> None:
        """Stores the room's state and grids as the tab's, and its names as its document's, as
        the room would on closing."""
        Update.objects.filter(room=tab.room).delete()
        tab.grids.all().delete()
        edit(tab, self.doc.get_update())
        for laid in self.grids.values():
            grids.put(tab.document, str(tab.pk), laid)
        Name.objects.filter(document=tab.document).delete()
        names.put(tab.document, self.names)

    def perform(self, edit: Callable[[Doc, Sheets], Prepared | TakeBack]):
        order = blocks.table_ids(blocks.body_of(self.doc))
        placed = placing.nodes_of({"tab": placing.of(self.doc)})
        if self.document is not None:
            return self._perform_stored(edit, order, placed)
        prepared = edit(self.doc, Sheets(self.grids, order, self.tab, self.names, placed))
        done = []
        for patch in prepared.patches:
            if names.NAMES in patch:
                self.names, went = names.apply(self.names, patch, prepared.guard)
            else:
                applied = grids.apply(self.grids.get(patch["table"]), patch, prepared.guard)
                if (went := applied.patch) is not None:
                    if applied.laid is None:
                        self.grids.pop(patch["table"], None)
                    else:
                        self.grids[patch["table"]] = applied.laid
            if went is not None:
                done.append(went)
        return prepared.commit(self.doc, done)

    def calculated(self, table: str, row: str, values: dict) -> None:
        """Gives the row the values its cells show, as calculating them would."""
        self.grids[table].row(row).values = values
        if self.document is not None:
            GridRow.objects.filter(grid__document=self.document, grid__table=table, row=row).update(
                values=values
            )

    def _perform_stored(self, edit, order, placed):
        held = tables_of(self.document)
        sheets = Sheets(held, order, self.tab, self.names, placed, document=self.document)
        prepared = edit(self.doc, sheets)
        _, self.names, done, renamed = apply_stored(
            self.document, held, self.names, prepared.patches, prepared.guard
        )
        self.grids = grids.of_document(self.document)
        return prepared.commit(self.doc, [each.patch for each in done] + renamed)

    def run(
        self,
        *operations: dict,
        locale: str = "hr",
        propose: Proposer | None = None,
        origin: str = "run",
    ):
        return self.perform(
            lambda doc, sheets: carry_out(doc, sheets, list(operations), locale, origin, propose)
        )

    def build(self, build: Callable[[Doc, Sheets], list], locale: str = "hr"):
        """Carries out the operations a plan builds from the room's state and grids."""
        return self.perform(
            lambda doc, sheets: carry_out(doc, sheets, build(doc, sheets), locale, "run")
        )

    def take_back(self, change: Change) -> Change:
        return self.perform(lambda doc, sheets: take_back(change))

    def read(self) -> list[Block]:
        return blocks.read(self.doc, self.grids)
