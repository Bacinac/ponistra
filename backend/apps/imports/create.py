"""A document made from an imported file, with the file kept beside it, or the file's tabs
put after a document's own: styles and pages, tabs, images and comments, as their editors
would have written them."""

import io
import uuid
from collections.abc import Callable, Sequence
from typing import NamedTuple

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from pycrdt import Doc, Map

from apps.access.models import Grant, Role
from apps.blobs import store
from apps.blobs.models import Blob
from apps.collab import server
from apps.collab.models import Update
from apps.comments.models import Comment, Thread
from apps.content import (
    blocks,
    calculation,
    grids,
    lists,
    names,
    numbering,
    operations,
    pages,
    placing,
    slides,
    styles,
    tallies,
)
from apps.content.models import DocumentBlob, Grid, Name
from apps.content.sheets import Sheets, apart
from apps.documents.models import Node, Tab
from apps.versions import history

from . import convert, docx, laying, reading, tidy, xlsx

Written = list[tuple[Doc, blocks.Written, Sheets]]
Anchored = list[tuple[reading.Thread, int, dict]]


class Read(NamedTuple):
    """A file as a document's content: its own state, its headers and footers' grids, each tab's
    and where the file's comments stand in them."""

    imported: reading.Imported
    own: Doc
    headed: Sheets
    contents: Written
    anchored: Anchored


def document(
    source: Blob, parent: Node | None, title: str, user, opened: Callable | None = None
) -> Node:
    """A new document of the file; `opened` is given it as soon as its first rows can be read,
    where the file is so large that they are written after the document stands."""
    read = _read(source, Node._meta.get_field("locale").get_default())
    with transaction.atomic():
        node = Node.objects.create(
            parent=parent,
            kind=Node.Kind.DOCUMENT,
            title=title,
            source=source,
            imported=read.imported.report,
            created_by=user,
            updated_by=user,
        )
        if parent is None:
            Grant.objects.create(node=node, user=user, role=Role.OWN, created_by=user)
        tabs = _tabs(node, read, 0, _named(read.imported, title))
        _laid(node, read, tabs)
        laying.bounded(node)
        _held_back(node, read.imported)
    if opened is not None and read.imported.rest is not None:
        opened(node)
    _completed(node, read.imported)
    return node


def reimport(node: Node, user) -> Node:
    """The document read from its file once more, as the import reads it now. Its tabs keep
    their places, the file's comments are read again beside the document's own, and what the
    document held stays in a version; the clients of the old rooms are revoked."""
    read = _read(node.source, node.locale)

    def write() -> Node:
        with transaction.atomic():
            document = history.lock(node.pk)
            history.take(document)
            document.room = uuid.uuid4()
            document.imported = read.imported.report
            document.updated_at = timezone.now()
            document.updated_by = user
            document.save(update_fields=["room", "imported", "updated_at", "updated_by"])
            first = document.tabs.filter(parent=None).order_by("position")
            kept = list(first[: len(read.imported.tabs)])
            document.tabs.exclude(pk__in=[tab.pk for tab in kept]).delete()
            Thread.objects.filter(tab__document=document).exclude(
                comments__outside_author=""
            ).delete()
            Update.objects.filter(document=document).delete()
            Grid.objects.filter(document=document).delete()
            Name.objects.filter(document=document).delete()
            tabs = _tabs(document, read, 0, _named(read.imported, document.title), kept)
            _laid(document, read, tabs)
            laying.bounded(document)
            _held_back(document, read.imported)
            history.take(document, user)
        return document

    document = server.rewrite(node.pk, write)
    server.revoke()
    _completed(document, read.imported)
    if read.imported.rest is not None:
        with transaction.atomic():
            history.take(history.lock(document.pk), user)
    return document


def into(node: Node, source: Blob, title: str, user) -> tuple[Tab, dict]:
    """The file's tabs after the document's last, the first named after the file where
    Word gives it no name, and the import's report. A style or list format the document
    has keeps its look; a tab laid out unlike the document's pages keeps pages of its own,
    and one from a file that sets up no pages takes the document's. A table named as one of
    the document's is named as its copy would be, and so is a tab named after it, a sheet's;
    the file's names join the document's."""
    own = Doc()
    own.apply_update(history.state_of(node.room))
    imported = convert.read(source, node.locale, lists.read(own))
    tidy.tidy(imported, own)
    contents, anchored = _written(imported)
    read = Read(imported, own, Sheets({}), contents, anchored)
    brought = [laid for _, _, held in contents for _, laid in held.tables()]
    titled = [
        (each, laid)
        for each, (_, _, held) in zip(imported.tabs, contents, strict=True)
        for _, laid in held.tables()
        if each.title and laid.name == each.title
    ]

    def write() -> list[Tab]:
        with transaction.atomic():
            apart(brought, Grid.objects.filter(document=node).values_list("name", flat=True))
            for each, laid in titled:
                each.title = laid.name
            last = node.tabs.filter(parent=None).aggregate(Max("position"))["position__max"]
            tabs = _tabs(node, read, 0 if last is None else last + 1, title)
            tables = [laid.table for laid in brought]
            names.put(node, names.joined(names.of_document(node), imported.names, tables))
            _kept(node, imported, tabs, anchored)
            laying.bounded(node)
            _held_back(node, imported)
            history.contributed(node.pk, user.pk)
        return tabs

    tabs = server.rewrite(node.pk, write)
    server.change(node.room, lambda own, sheets: _joined(own, sheets, imported, tabs))
    server.announce(node.room, "tabs")
    _completed(node, imported)
    return tabs[0], imported.report


def _streamed_tables(imported: reading.Imported) -> list[str]:
    return [block.id for each in imported.tabs for block in each.blocks if block.type == "table"]


def _held_back(node: Node, imported: reading.Imported) -> None:
    """Has the tables of a file whose rows are still to come left uncalculated until they are
    all there, what each shows until then the value the file saved with it."""
    if imported.rest is not None:
        Grid.objects.filter(document=node, table__in=_streamed_tables(imported)).update(
            calculated=calculation.calculated(node.locale)
        )


def _completed(node: Node, imported: reading.Imported) -> None:
    """Writes what of the file is still to come, calculates the document and holds it to the
    values the file saved. Rows that could not all be written are reported, the document as
    far as it came kept and the error passed on."""
    written: set[str] = set()
    if imported.rest is not None:
        try:
            written = imported.rest(node)
        except Exception:
            imported.report["lost"] = {**imported.report["lost"], "unfinished": 1}
            node.imported = imported.report
            node.save(update_fields=["imported"])
            laying.end()
            raise
        others = set(_streamed_tables(imported)) - written
        Grid.objects.filter(document=node, table__in=others).update(calculated="")
    nodes = placing.nodes_of(placing.of_document(node))
    calculation.calculate(
        node, nodes.keys(), nodes, dict.fromkeys(written), constants_written=written
    )
    xlsx.compared(node, imported)
    if imported.rest is not None:
        server.grew(node.pk)


def _written(imported: reading.Imported) -> tuple[Written, Anchored]:
    """Each tab's content as its own state, and each comment's place in it; a comment with no
    place left is counted as lost."""
    contents = []
    for each in imported.tabs:
        content, held = Doc(), Sheets({})
        written = operations.write(content, held, each.blocks)
        content.apply_update(written.update)
        contents.append((content, written.written, held))
    anchored = []
    for thread in imported.threads:
        anchor = None
        for at, (_, written, _) in enumerate(contents):
            start = written.position(*thread.start)
            end = written.position(*thread.end, assoc=-1)
            if start is not None and end is not None:
                anchor = (at, {"from": start, "to": end})
                break
        if anchor is None:
            lost = imported.report["lost"]
            lost["comments"] = lost.get("comments", 0) + 1
            continue
        anchored.append((thread, *anchor))
    return contents, anchored


def _read(source: Blob, locale: str) -> Read:
    imported = convert.read(source, locale)
    tidy.tidy(imported)
    own = styles.own(imported.theme, imported.styles)
    headed = Sheets({})
    if imported.page is not None:
        pages.write(own, headed, imported.page, imported.parts)
    lists.write(own, imported.formats)
    if imported.template is not None:
        slides.write(own, imported.template)
    return Read(imported, own, headed, *_written(imported))


def _named(imported: reading.Imported, title: str) -> str:
    """The name of a file's first tab where Word gives it none: the document's, when the file
    has tabs after it."""
    return title if len(imported.tabs) > 1 else ""


def _tabs(
    node: Node, read: Read, start: int, named: str = "", kept: Sequence[Tab] = ()
) -> list[Tab]:
    """The file's tabs from the start, in the kept ones first, each of those in a new room."""
    tabs = []
    for offset, (each, (content, _, sheets)) in enumerate(
        zip(read.imported.tabs, read.contents, strict=True)
    ):
        title = each.title or (named if offset == 0 else "")
        if offset < len(kept):
            tab = kept[offset]
            tab.position, tab.title, tab.room = start + offset, title, uuid.uuid4()
            tab.save(update_fields=["position", "title", "room"])
        else:
            tab = Tab.objects.create(document=node, position=start + offset, title=title)
        Update.objects.create(document=node, tab=tab, room=tab.room, data=content.get_update())
        _gridded(node, str(tab.pk), sheets)
        tabs.append(tab)
    return tabs


def _laid(node: Node, read: Read, tabs: list[Tab]) -> None:
    """The document's own state with each tab's pages and numbering, the headers and footers'
    grids, and the file's names, images and comments."""
    for each, tab in zip(read.imported.tabs, tabs, strict=True):
        if each.page is not None:
            pages.write(read.own, read.headed, each.page, each.parts or {}, tab=str(tab.pk))
        _sectioned(read.own, read.headed, each, str(tab.pk))
        tallies.keep(read.own, str(tab.pk), each.blocks, read.imported.styles)
    Update.objects.create(document=node, room=node.room, data=read.own.get_update())
    _gridded(node, None, read.headed)
    names.put(node, read.imported.names)
    _kept(node, read.imported, tabs, read.anchored)


def _gridded(node: Node, tab: str | None, sheets: Sheets) -> None:
    """Writes the grids the import made, of the tab or, with none, of the headers and
    footers."""
    for _, laid in sheets.tables():
        grids.put(node, tab, laid)


def _kept(node: Node, imported: reading.Imported, tabs: list[Tab], anchored: Anchored) -> None:
    for data in imported.images.values():
        DocumentBlob.objects.get_or_create(document=node, blob=store.put(io.BytesIO(data)))
    for thread, at, anchor in anchored:
        _discussed(tabs[at], thread, anchor)


def _joined(own: Doc, sheets: Sheets, imported: reading.Imported, tabs: list[Tab]) -> None:
    found = own.get(styles.STYLES, type=Map)
    for id, style in imported.styles.items():
        if id not in found:
            found[id] = Map(style)
    lists.write(own, imported.formats)
    if imported.template is not None:
        slides.join(own, imported.template)
    shared = laid_out(*pages.read(own, sheets.grids()))
    counted = numbering.styles_of(own)
    for each, tab in zip(imported.tabs, tabs, strict=True):
        if each.page is not None:
            page, parts = each.page, each.parts or {}
        else:
            page, parts = imported.page, imported.parts
        if page is not None and laid_out(page, parts) != shared:
            pages.write(own, sheets, page, parts, tab=str(tab.pk))
        _sectioned(own, sheets, each, str(tab.pk))
        tallies.keep(own, str(tab.pk), each.blocks, counted)


def _sectioned(own: Doc, sheets: Sheets, imported: reading.Tab, tab: str) -> None:
    for section, (page, parts) in imported.sections.items():
        pages.write_section(own, sheets, tab, section, page, parts)


def laid_out(page: dict, parts: dict[str, list[blocks.Block]]) -> tuple[dict, dict]:
    setup = {name: value for name, value in page.items() if value is not None}
    return {**pages.DEFAULT, **setup}, docx.signature(parts)


def _discussed(tab: Tab, thread: reading.Thread, anchor: dict) -> None:
    now = timezone.now()
    dates = [remark.date or now for remark in thread.remarks]
    discussion = Thread.objects.create(
        tab=tab,
        anchor=anchor,
        quote=thread.quote,
        resolved_at=max(dates) if thread.resolved else None,
    )
    Thread.objects.filter(pk=discussion.pk).update(created_at=dates[0])
    for remark, date in zip(thread.remarks, dates, strict=True):
        comment = Comment.objects.create(
            thread=discussion, outside_author=remark.author, body=remark.text
        )
        Comment.objects.filter(pk=comment.pk).update(created_at=date)
