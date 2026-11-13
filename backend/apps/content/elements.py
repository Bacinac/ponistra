"""The element table: each tab's blocks and filled table cells as rows, read again from
its Yjs state shortly after the tab changes."""

from datetime import datetime
from logging import getLogger

from anyio import sleep
from django.conf import settings
from django.db import transaction
from django.db.models import F, Max, Min, OuterRef, Q, Subquery
from django.db.models.functions import Greatest
from django.utils import timezone
from pycrdt import Doc

from apps.collab.models import Update
from apps.core.asyncdb import database
from apps.documents import naming
from apps.documents.models import Tab
from apps.versions.history import state_of

from . import blocks, grids, measures
from .models import Element, Grid
from .numbering import numbered, numbering_of

log = getLogger(__name__)

EVERY = 2
DEEPEST = 6


def column(index: int) -> str:
    """The column's letters as a spreadsheet names it: A to Z, then AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def level_of(block: blocks.Block) -> int:
    level = block.attrs.get("level")
    return min(max(level, 1), DEEPEST) if isinstance(level, int) else 1


def runs_of(runs: list[blocks.Run | blocks.Note]) -> list[dict]:
    return [
        {"text": run.text, **({"marks": run.marks} if run.marks else {})}
        for run in runs
        if isinstance(run, blocks.Run)
    ]


def content_of(block: blocks.Block) -> dict:
    return {"type": block.type, "attrs": block.attrs, "runs": runs_of(block.runs)}


def elements_of(content: list[blocks.Block], numbering: dict | None = None) -> list[Element]:
    """Every heading, table, image, PDF and chart, every block with text or a number and every
    note, each with its address: the section its heading numbers, then its place within it. A
    heading that skips a level numbers it 0, as 1.0.1. Where a style numbers a block, its
    number leads its text and the address holds it, and its heading's under `heading`. A
    table's cells with a node of their own are read row by row: a heading in one numbers on as
    any other and an image in one is found at its cell; what the cells show is found in their
    grid's rows. A note is where its mark is; its number counts on through the document's
    tabs, so it is no part of the address."""
    elements: list[Element] = []
    numbers: list[int] = []
    labels = numbered(blocks.in_order(content), numbering)[0] if numbering else {}
    read = -1
    shown = None
    paragraph = table = image = pdf = chart = 0

    def add(block: blocks.Block, type: str, text: str, content: dict, address: dict, **cell):
        elements.append(
            Element(
                position=len(elements),
                block=block.id or "",
                type=type,
                text=text,
                content=content,
                address=address,
                **cell,
            )
        )

    def add_notes(block: blocks.Block, address: dict):
        for note in block.notes:
            elements.append(
                Element(
                    position=len(elements),
                    block=note.id or "",
                    type="endnote" if note.kind == "end" else "footnote",
                    text=note.text,
                    content={"runs": runs_of(note.runs)},
                    address={**address, "note": note.kind},
                )
            )

    def labelled(block: blocks.Block) -> tuple[str | None, str]:
        nonlocal read
        read += 1
        label = labels.get(read)
        return label, f"{label} {block.text}".strip() if label else block.text

    def section(block: blocks.Block, label: str | None) -> dict:
        nonlocal numbers, paragraph, shown
        level = level_of(block)
        numbers = (numbers + [0] * level)[:level]
        numbers[-1] += 1
        paragraph = 0
        shown = label
        address = {"section": ".".join(map(str, numbers))}
        if label:
            address["heading"] = label
        return address

    def add_image(block: blocks.Block, address: dict):
        nonlocal image
        image += 1
        alt = str(block.attrs.get("alt") or "")
        add(block, block.type, alt, {"attrs": block.attrs}, {**address, "image": image})

    def add_cells(block: blocks.Block, address: dict):
        for each in blocks.placed(block):
            at = {**address, "cell": f"{column(each.x)}{each.y + 1}"}
            for inner in each.cell.blocks:
                label, _ = labelled(inner)
                if inner.type == "heading":
                    section(inner, label)
                elif inner.type == "image":
                    add_image(inner, at)

    for block in content:
        within = {"section": ".".join(map(str, numbers))} if numbers else {}
        if shown:
            within["heading"] = shown
        label, text = labelled(block)
        if block.type == "heading":
            address = section(block, label)
            add(
                block,
                block.type,
                text,
                {"attrs": block.attrs, "runs": runs_of(block.runs)},
                address,
            )
            add_notes(block, address)
        elif block.type == "table":
            table += 1
            address = {**within, "table": table}
            add(block, block.type, "", {}, address)
            add_cells(block, address)
        elif block.type == "image":
            add_image(block, within)
        elif block.type == "pdf":
            pdf += 1
            title = block.attrs.get("title")
            title = title if isinstance(title, str) else ""
            add(block, block.type, title, {"attrs": block.attrs}, {**within, "pdf": pdf})
        elif block.type == "chart":
            chart += 1
            title = block.attrs.get("title")
            title = title if isinstance(title, str) else ""
            add(block, block.type, title, {"attrs": block.attrs}, {**within, "chart": chart})
        elif text.strip():
            paragraph += 1
            content = {"attrs": block.attrs, "runs": runs_of(block.runs)}
            address = {**within, "paragraph": paragraph}
            if label:
                address["number"] = label
            add(block, block.type, text, content, address)
            add_notes(block, address)
        else:
            add_notes(block, within)
    return elements


def due(now: datetime) -> list[Tab]:
    """Tabs with content, where it, its grids or the document's own state changed since they
    were last read, once quiet for ELEMENT_QUIET or once their earliest unread edit is
    ELEMENT_INTERVAL old: of a grid's, only its latest is known, so its earliest counts from
    the last read."""
    last_edit = Update.objects.filter(room=OuterRef("room")).order_by("-id")
    last_own = Update.objects.filter(room=OuterRef("document__room")).order_by("-id")
    last_grid = Grid.objects.filter(tab=OuterRef("pk")).order_by("-edited_at")
    edited = Subquery(last_edit.values("created_at")[:1])
    gridded = Subquery(last_grid.values("edited_at")[:1])
    changed = (
        Tab.objects.select_related("document")
        .annotate(
            edited_at=edited,
            gridded_at=gridded,
            changed_at=Greatest(edited, gridded, Subquery(last_own.values("created_at")[:1])),
        )
        .filter(edited_at__isnull=False)
        .filter(Q(derived_at__isnull=True) | Q(changed_at__gt=F("derived_at")))
    )
    tabs = []
    for tab in changed:
        if now - tab.changed_at >= settings.ELEMENT_QUIET:
            tabs.append(tab)
            continue
        # A tab never read counts from its own first edit, not from its document's creation.
        unread = Update.objects.filter(room=tab.room)
        if tab.derived_at is not None:
            unread = Update.objects.filter(
                room__in=[tab.room, tab.document.room], created_at__gt=tab.derived_at
            )
        found = [unread.aggregate(first=Min("created_at"))["first"]]
        if tab.derived_at is not None and tab.gridded_at and tab.gridded_at > tab.derived_at:
            found.append(tab.derived_at)
        first = min((each for each in found if each), default=tab.changed_at)
        if now - first >= settings.ELEMENT_INTERVAL:
            tabs.append(tab)
    return tabs


def derive(tab_id) -> None:
    """Replaces the tab's elements with those of its content now, unless only the document's
    own state changed and nothing the tab's numbers follow, and measures the document."""
    with transaction.atomic():
        tab = Tab.objects.select_for_update().select_related("document").filter(pk=tab_id).first()
        if tab is None:
            return
        rooms = [tab.room, tab.document.room]
        # Read before the state: an edit landing in between is then read again next pass.
        seen = Update.objects.filter(room__in=rooms).aggregate(at=Max("created_at"))["at"]
        gridded = Grid.objects.filter(tab=tab).aggregate(at=Max("edited_at"))["at"]
        seen = max((each for each in (seen, gridded) if each), default=None)
        own = Doc()
        own.apply_update(state_of(tab.document.room))
        order = [each.pk for each in tab.document.tabs_in_order()]
        numbering = numbering_of(own, order, tab.pk)
        edited = (
            tab.derived_at is None
            or Update.objects.filter(room=tab.room, created_at__gt=tab.derived_at).exists()
            or (gridded is not None and gridded > tab.derived_at)
        )
        if not edited and numbering == tab.numbered_by:
            Tab.objects.filter(pk=tab.pk).update(derived_at=seen)
            measures.measure(tab.document, own)
            return
        doc = Doc()
        doc.apply_update(state_of(tab.room))
        elements = elements_of(blocks.read(doc, grids.placing_of_tab(tab), light=False), numbering)
        for element in elements:
            element.tab = tab
        Element.objects.filter(tab=tab).delete()
        Element.objects.bulk_create(elements)
        Tab.objects.filter(pk=tab.pk).update(derived_at=seen, numbered_by=numbering)
        measures.measure(tab.document, own)
        if tab.document.follows_text and tab.parent_id is None and tab.position == 0:
            naming.follow(tab.document, [element.text for element in elements])


def tend(now: datetime | None = None) -> None:
    for tab in due(now or timezone.now()):
        try:
            derive(tab.pk)
        except Exception:
            log.exception("elements: tab %s could not be read", tab.pk)
            Tab.objects.filter(pk=tab.pk).update(derived_at=tab.changed_at)


async def follow() -> None:
    """Keeps the element table following every tab's content while the server runs."""
    while True:
        try:
            await database(tend, own_thread=True)()
        except Exception:
            log.exception("elements: a pass failed")
        await sleep(EVERY)
