import hashlib
import json
import tempfile
import uuid
import zlib
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import groupby
from logging import getLogger
from operator import itemgetter

from anyio import sleep
from django.conf import settings
from django.db import transaction
from django.db.models import F, Min, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from pycrdt import Doc

from apps.collab.models import Update
from apps.content import blocks, calculation, grids, names, placing, tallies
from apps.content import rows as stored
from apps.content.blocks import Block
from apps.content.grids import Laid
from apps.content.models import Grid, GridRow, Name, Shared
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab

from .models import Contribution, Piece, State, Version, VersionGrid, VersionTab

EVERY = 60
DAY = timedelta(days=1)
MONTH = timedelta(days=30)
# A grid's rows are kept in pieces that end after a row whose id hashes to a multiple of
# PIECE, so a row put in or taken out changes the one piece it is in, however long the grid.
PIECE = 128
LONGEST = 1024
PIECES_AT_ONCE = 32
READ = 2000

log = getLogger(__name__)


def contributed(document_id, user_id) -> None:
    now = timezone.now()
    Contribution.objects.bulk_create(
        [Contribution(document_id=document_id, user_id=user_id, edited_at=now)],
        update_conflicts=True,
        unique_fields=["document", "user"],
        update_fields=["edited_at"],
    )
    Node.objects.filter(pk=document_id).update(updated_at=now, updated_by_id=user_id)


def state_of(room) -> bytes:
    """The room's whole Yjs state without the content deleted from it, which its room keeps,
    so the same content always gives the same bytes."""
    # A throwaway Doc forms no reference cycle, so it is freed here, on the thread that
    # made it, even while the collab server keeps the cyclic collector off.
    doc = Doc()
    for data in Update.objects.filter(room=room).order_by("id").values_list("data", flat=True):
        doc.apply_update(bytes(data))
    return doc.get_update()


def lock(document_id) -> Node:
    return Node.objects.select_for_update().get(pk=document_id)


def pieces_of(rows: Iterable[list]) -> Iterator[list[list]]:
    piece: list[list] = []
    for row in rows:
        piece.append(row)
        if len(piece) >= LONGEST or zlib.crc32(row[0].encode()) % PIECE == 0:
            yield piece
            piece = []
    if piece:
        yield piece


def digest(piece: list[list]) -> str:
    text = json.dumps(piece, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def piece_text(piece: list[list]) -> str:
    """What the piece's cells show, which the search over versions reads: what was calculated
    where it shows, else what was typed."""
    texts = []
    for line in piece:
        _, _, cells, _, _, figures = grids.line_parts(line)
        shown = figures.get("shown", {})
        for col in cells.keys() | shown.keys():
            text = shown.get(col) or (cells.get(col) or {}).get(grids.TEXT)
            if isinstance(text, str) and text:
                texts.append(text)
    return " ".join(texts)


def tab_text(data: bytes) -> str:
    """The text of a tab's blocks as its state holds them; of a table, of the cells with a node
    of their own, the rest being in the version's pieces."""
    doc = Doc()
    doc.apply_update(data)
    return "\n".join(block.text for block in blocks.in_order(blocks.read(doc, {})) if block.text)


def lines_of(document_id, digests: list[str]) -> Iterator[list]:
    """The rows of the pieces given, in their order, a few pieces at a time."""
    for at in range(0, len(digests), PIECES_AT_ONCE):
        part = digests[at : at + PIECES_AT_ONCE]
        found = dict(
            Piece.objects.filter(document=document_id, sha256__in=part).values_list(
                "sha256", "rows"
            )
        )
        for sha256 in part:
            yield from found[sha256]


class Pieces:
    """Writes a document's pieces as they are made, those it does not yet hold, a few at a time."""

    def __init__(self, document_id):
        self.document_id = document_id
        self.waiting: dict[str, list[list]] = {}

    def add(self, piece: list[list]) -> str:
        sha256 = digest(piece)
        self.waiting[sha256] = piece
        if len(self.waiting) >= PIECES_AT_ONCE:
            self.flush()
        return sha256

    def flush(self) -> None:
        held = set(
            Piece.objects.filter(
                document=self.document_id, sha256__in=list(self.waiting)
            ).values_list("sha256", flat=True)
        )
        Piece.objects.bulk_create(
            Piece(
                document_id=self.document_id,
                sha256=sha256,
                rows=rows,
                size=len(rows),
                shown=sum(1 for line in rows if not grids.line_parts(line)[4]),
                text=piece_text(rows),
            )
            for sha256, rows in self.waiting.items()
            if sha256 not in held
        )
        self.waiting.clear()


@dataclass
class Kept:
    """A grid as a version keeps it: its pieces by digest in order and how it is laid out."""

    tab: uuid.UUID | None
    table: str
    name: str
    cols: list[list]
    frozen: str
    pieces: list[str] = field(default_factory=list)
    size: int = 0
    outline: dict = field(
        default_factory=lambda: {"heights": {}, "looks": {}, "hidden": [], "merges": {}}
    )
    at: dict[str, int] = field(default_factory=dict)
    keys: set[str] = field(default_factory=set)
    first: str | None = None
    last: tuple[str, int] | None = None

    def content(self) -> tuple:
        return (
            self.tab,
            self.table,
            self.name,
            json.dumps(self.cols),
            self.frozen,
            tuple(self.pieces),
        )

    def line(self, id, height, cells, values, shown, look, hidden) -> list:
        """Notes the next row, in order, and gives it as the version keeps it."""
        place, outline = self.size, self.outline
        self.size += 1
        self.keys |= stored._keys(cells)
        if look:
            self.keys.add(look)
            outline["looks"][id] = look
        if height is not None:
            outline["heights"][id] = height
        named = height is not None or bool(look) or hidden or id == self.frozen
        if hidden:
            outline["hidden"].append(id)
        else:
            if self.first is None:
                self.first = id
                named = True
            self.last = (id, place)
        for col, cell in cells.items():
            if to := cell.get(grids.TO):
                outline["merges"][f"{id}:{col}"] = to
                named = True
        if named:
            self.at[id] = place
        return grids.kept_line(id, height, cells, values, shown, look, hidden)


def _referred(formula: list, table: str) -> Iterator[tuple[str, str]]:
    """The rows a formula kept names by id, each with its table."""
    for piece in formula:
        if isinstance(piece, dict):
            for end in ("from", "to"):
                row = (piece.get(end) or {}).get("row")
                if isinstance(row, str) and row != grids.OWN:
                    yield piece.get("table", table), row


def _located(standing: Mapping[int, Grid], kept: Mapping[int, Kept], shared: Mapping) -> None:
    """Notes where the rows stand that the formulas kept name by id or the merged cells reach."""
    pks = {grid.table: pk for pk, grid in standing.items()}
    wanted: dict[str, set[str]] = {}
    for grid, each in kept.items():
        table = standing[grid].table
        for key in each.keys:
            if isinstance(value := shared.get(key), list):
                for target, row in _referred(value, table):
                    wanted.setdefault(target, set()).add(row)
        for to in each.outline["merges"].values():
            wanted.setdefault(table, set()).add(to.partition(":")[0])
    for table, ids in wanted.items():
        if table in pks:
            kept[pks[table]].at |= stored.places_of(pks[table], ids)


def kept_grids(document: Node, pieces: Pieces) -> tuple[list[Kept], dict]:
    """The document's grids as they stand, one query over their rows, each piece written as it
    is made, and what their cells and lines share, by key."""
    standing = {grid.pk: grid for grid in Grid.objects.filter(document=document)}
    kept = {
        pk: Kept(
            grid.tab_id,
            grid.table,
            grid.name,
            [grids.kept_col(col) for col in grid.cols],
            grid.frozen,
        )
        for pk, grid in standing.items()
    }
    found = (
        GridRow.objects.filter(grid__in=list(standing))
        .order_by("grid", "position")
        .values_list("grid", "row", "height", "cells", "values", "shown", "look", "hidden")
        .iterator(chunk_size=READ)
    )
    for pk, lines in groupby(found, key=itemgetter(0)):
        each = kept[pk]
        made = (each.line(*line[1:]) for line in lines)
        each.pieces.extend(pieces.add(piece) for piece in pieces_of(made))
    pieces.flush()
    for pk, each in kept.items():
        each.keys |= {col["look"] for col in standing[pk].cols if "look" in col}
        if each.last is not None:
            each.at[each.last[0]] = each.last[1]
    keys = {key for each in kept.values() for key in each.keys}
    shared = dict(
        Shared.objects.filter(document=document, key__in=keys).values_list("key", "value")
    )
    _located(standing, kept, shared)
    return list(kept.values()), shared


def grids_of(version: Version) -> dict[str, Laid]:
    """The grids the version holds whole, by table, for what reads a bounded table's text."""
    shared = grids.shared_of(version.shared)
    return {
        part.table: grids.from_whole(
            part.table,
            {
                "tab": part.tab and str(part.tab),
                "name": part.name,
                "cols": [grids.unkept_col(col, shared) for col in part.cols],
                "rows": grids.unkept_rows(list(lines_of(version.document_id, part.pieces)), shared),
                "frozen": part.frozen or None,
            },
        )
        for part in version.grids.all()
    }


def blocks_of(version: Version, tab: Tab) -> list[Block]:
    """The tab's blocks as the version holds them, none where it holds no such tab."""
    part = version.tabs.select_related("state").filter(tab=tab.pk).first()
    if part is None:
        return []
    doc = Doc()
    doc.apply_update(bytes(part.state.data))
    mine = str(tab.pk)
    held = {table: laid for table, laid in grids_of(version).items() if laid.tab == mine}
    return blocks.read(doc, held)


def _holds(latest: Version, content: tuple, own: bytes) -> bool:
    """Whether the version holds the content, its own state compared as its users wrote it."""
    held = latest.content()
    if held[1:] != content[1:]:
        return False
    return held[0] == content[0] or tallies.written(bytes(latest.state.data)) == tallies.written(
        own
    )


def take(document: Node, by=None, title: str = "", restored_from: int | None = None):
    """Records the document as it stands, its editors being whoever changed it since
    the version before, and `by`. An automatic version (no `by`) is skipped when the
    latest one holds the same content, which then counts as checked."""
    with transaction.atomic():
        lock(document.pk)
        now = timezone.now()
        own = state_of(document.room)
        own_digest = hashlib.sha256(own).hexdigest()
        tabs = [(tab, state_of(tab.room)) for tab in document.tabs.all()]
        digests = {tab.pk: hashlib.sha256(data).hexdigest() for tab, data in tabs}
        calculation.refresh(document)
        kept, shared = kept_grids(document, Pieces(document.pk))
        defined = names.of_document(document)
        content = (
            own_digest,
            {(tab.pk, tab.parent_id, tab.position, tab.title, digests[tab.pk]) for tab, _ in tabs},
            {each.content() for each in kept},
            json.dumps(defined, sort_keys=True),
        )
        latest = document.versions.select_related("state").order_by("-number").first()
        if by is None and latest is not None and _holds(latest, content, own):
            latest.checked_at = now
            latest.save(update_fields=["checked_at"])
            return None
        states = {
            state.sha256: state
            for state in State.objects.filter(
                document=document, sha256__in=[own_digest, *digests.values()]
            )
        }
        if own_digest not in states:
            states[own_digest] = State.objects.create(
                document=document, sha256=own_digest, data=own
            )
        for tab, data in tabs:
            if digests[tab.pk] in states:
                continue
            states[digests[tab.pk]] = State.objects.create(
                document=document, sha256=digests[tab.pk], data=data, text=tab_text(data)
            )
        version = Version.objects.create(
            document=document,
            number=latest.number + 1 if latest else 1,
            title=title,
            created_at=now,
            checked_at=now,
            restored_from=restored_from,
            state=states[own_digest],
            names=defined,
            shared=shared,
        )
        VersionTab.objects.bulk_create(
            VersionTab(
                version=version,
                tab=tab.pk,
                parent=tab.parent_id,
                position=tab.position,
                title=tab.title,
                state=states[digests[tab.pk]],
            )
            for tab, _ in tabs
        )
        VersionGrid.objects.bulk_create(
            VersionGrid(
                version=version,
                tab=each.tab,
                table=each.table,
                name=each.name,
                cols=each.cols,
                frozen=each.frozen,
                pieces=each.pieces,
                size=each.size,
                outline=each.outline,
                at=each.at,
            )
            for each in kept
        )
        since = Contribution.objects.filter(document=document)
        if latest is not None:
            since = since.filter(edited_at__gt=latest.created_at)
        version.editors.set([*since.values_list("user", flat=True), *([by.pk] if by else [])])
        return version


def put_back(version: Version, document: Node) -> None:
    """Writes the version's grids as the document's, row by row as the pieces are read."""
    Shared.objects.bulk_create(
        [Shared(document=document, key=key, value=value) for key, value in version.shared.items()],
        batch_size=2000,
        ignore_conflicts=True,
    )
    for part in version.grids.all():
        grid = Grid.objects.create(
            document=document,
            tab_id=part.tab,
            table=part.table,
            name=part.name,
            cols=[grids.stored_col(line) for line in part.cols],
            frozen=part.frozen,
        )
        made = []
        for place, line in enumerate(lines_of(version.document_id, part.pieces), 1):
            id, height, cells, look, hidden, figures = grids.line_parts(line)
            made.append(
                GridRow(
                    grid=grid,
                    row=id,
                    position=place * grids.STEP,
                    height=height,
                    cells=cells,
                    values=figures.get("values", {}),
                    shown=figures.get("shown", {}),
                    look=look or "",
                    hidden=hidden,
                )
            )
            if len(made) >= READ:
                GridRow.objects.bulk_create(made)
                made.clear()
        GridRow.objects.bulk_create(made)


class _Spooled(Pieces):
    """Pieces made where nothing written stays, kept in a file to be written after."""

    def __init__(self, document_id):
        super().__init__(document_id)
        self.file = tempfile.TemporaryFile("w+", encoding="utf-8")

    def add(self, piece: list[list]) -> str:
        self.file.write(json.dumps(piece, ensure_ascii=False) + "\n")
        return digest(piece)

    def flush(self) -> None:
        pass

    def written(self) -> Iterator[list[list]]:
        self.file.seek(0)
        for line in self.file:
            yield json.loads(line)


def settle(version: Version) -> None:
    """Calculates the grids of a version that was kept without their values, as they stood in
    it, by putting them back where the document's grids are and undoing that after."""
    if not version.grids.exists():
        return
    document = version.document
    placings = {}
    for part in version.tabs.select_related("state"):
        doc = Doc()
        doc.apply_update(bytes(part.state.data))
        placings[str(part.tab)] = placing.of(doc)
    nodes = placing.nodes_of(placings)
    spooled = _Spooled(document.pk)
    with spooled.file, transaction.atomic():
        point = transaction.savepoint_create()
        Grid.objects.filter(document=document).delete()
        put_back(version, document)
        calculation.calculate(document, nodes.keys(), nodes)
        kept, shared = kept_grids(document, spooled)
        transaction.savepoint_rollback(point)
        written = Pieces(document.pk)
        for piece in spooled.written():
            written.add(piece)
        written.flush()
        version.shared = shared
        version.save(update_fields=["shared"])
        parts = {part.table: part for part in version.grids.all()}
        for each in kept:
            part = parts[each.table]
            part.pieces, part.size, part.outline, part.at = (
                each.pieces,
                each.size,
                each.outline,
                each.at,
            )
        VersionGrid.objects.bulk_update(parts.values(), ["pieces", "size", "outline", "at"])


def collect_pieces(document_id) -> None:
    """Deletes the document's pieces no version holds."""
    held = {
        sha256
        for pieces in VersionGrid.objects.filter(version__document=document_id).values_list(
            "pieces", flat=True
        )
        for sha256 in pieces
    }
    Piece.objects.filter(document=document_id).exclude(sha256__in=held).delete()


def restore(version: Version, by) -> Version:
    """Brings the document back to the version: tabs it lacks return, tabs it gained go,
    and the document and every tab move to fresh rooms. The replaced content stays in a
    version of its own; the clients of the old rooms are for the caller to revoke once
    this commits."""
    with transaction.atomic():
        document = lock(version.document_id)
        take(document)
        document.room = uuid.uuid4()
        document.save(update_fields=["room"])
        current = {tab.pk: tab for tab in document.tabs.all()}
        restored = [Update(document=document, room=document.room, data=version.state.data)]
        for part in version.tabs.select_related("state"):
            tab = current.pop(part.tab, None) or Tab(pk=part.tab, document=document)
            tab.parent_id = part.parent
            tab.position = part.position
            tab.title = part.title
            tab.room = uuid.uuid4()
            tab.save()
            restored.append(Update(document=document, tab=tab, room=tab.room, data=part.state.data))
        Tab.objects.filter(pk__in=current).delete()
        Update.objects.filter(document=document).delete()
        Update.objects.bulk_create(restored)
        Grid.objects.filter(document=document).delete()
        put_back(version, document)
        Name.objects.filter(document=document).delete()
        names.put(document, version.names)
        Node.objects.filter(pk=document.pk).update(updated_at=timezone.now(), updated_by=by)
        return take(document, by, restored_from=version.number)


def due(now: datetime) -> list[Node]:
    """Documents changed since their latest version was checked, in their text or their
    grids, once they have been quiet for VERSION_QUIET or their earliest unrecorded edit is
    VERSION_INTERVAL old: of a grid's, only its latest is known, so its earliest counts from
    the check."""
    last_edit = Update.objects.filter(document=OuterRef("pk")).order_by("-created_at")
    last_grid = Grid.objects.filter(document=OuterRef("pk")).order_by("-edited_at")
    latest = Version.objects.filter(document=OuterRef("pk")).order_by("-number")
    changed = (
        Node.objects.filter(kind=Node.Kind.DOCUMENT)
        .annotate(
            changed_at=Greatest(
                "updated_at",
                Coalesce(Subquery(last_edit.values("created_at")[:1]), "updated_at"),
                Coalesce(Subquery(last_grid.values("edited_at")[:1]), "updated_at"),
            ),
            gridded_at=Subquery(last_grid.values("edited_at")[:1]),
            last_checked=Subquery(latest.values("checked_at")[:1]),
        )
        .filter(Q(last_checked__isnull=True) | Q(changed_at__gt=F("last_checked")))
    )
    documents = []
    for document in changed:
        if now - document.changed_at >= settings.VERSION_QUIET:
            documents.append(document)
            continue
        unrecorded = Update.objects.filter(document=document)
        checked = document.last_checked
        if checked is not None:
            unrecorded = unrecorded.filter(created_at__gt=checked)
        found = [unrecorded.aggregate(first=Min("created_at"))["first"]]
        if checked is not None and document.gridded_at and document.gridded_at > checked:
            found.append(checked)
        first = min((each for each in found if each), default=document.changed_at)
        if now - first >= settings.VERSION_INTERVAL:
            documents.append(document)
    return documents


def thin(now: datetime) -> None:
    """Keeps every titled version and, of the automatic ones, all from the last day,
    the latest of each day for a month and the latest of each week before that."""
    old = (
        Version.objects.filter(title="", created_at__lt=now - DAY)
        .order_by("document", "-created_at")
        .values_list("pk", "document", "created_at")
    )
    kept = set()
    doomed = defaultdict(list)
    for pk, document, created_at in old:
        day = timezone.localdate(created_at)
        period = day if now - created_at < MONTH else day.isocalendar()[:2]
        if (document, period) in kept:
            doomed[document].append(pk)
        else:
            kept.add((document, period))
    for document, versions in doomed.items():
        with transaction.atomic():
            lock(document)
            Version.objects.filter(pk__in=versions).delete()
            State.objects.filter(
                document=document, version_tabs__isnull=True, versions__isnull=True
            ).delete()
            held = {
                sha256
                for pieces in VersionGrid.objects.filter(version__document=document).values_list(
                    "pieces", flat=True
                )
                for sha256 in pieces
            }
            Piece.objects.filter(document=document).exclude(sha256__in=held).delete()


def tend(now: datetime | None = None) -> None:
    now = now or timezone.now()
    for document in due(now):
        take(document)
    thin(now)


async def keep() -> None:
    """Takes the automatic versions and thins the old ones while the server runs."""
    while True:
        try:
            await database(tend)()
        except Exception:
            log.exception("versions: a pass failed")
        await sleep(EVERY)
