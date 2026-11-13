"""What reading a Word file and a PowerPoint file share: the package, its pictures, its charts
over a table of their data, and the file's list numbers made ours."""

import hashlib
import tempfile
import zipfile
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from docx.opc.exceptions import PackageNotFoundError
from docx.opc.package import OpcPackage
from lxml import etree

from apps.blobs import store
from apps.content.blocks import Block
from apps.content.schema import INDENT_STEP

from . import charts, xlsx
from .reading import TooLarge, Unreadable

LARGEST = 256 * 1024 * 1024
MOST_PARTS = 10_000
# Elements, attributes and comments once read: python-docx's tree and our blocks take about
# 0.8 kB and 30 microseconds each, whatever the bytes they came from.
MOST_NODES = 2_000_000
SCHEMES = {"http", "https", "mailto", "tel"}


def bounded(archive: zipfile.ZipFile) -> None:
    """A zip that unpacks to no more than a reader takes on."""
    parts = archive.infolist()
    if len(parts) > MOST_PARTS or sum(part.file_size for part in parts) > LARGEST:
        raise TooLarge


class _Nodes:
    """What a part's XML becomes in memory, counted as a parser passes over it, keeping none."""

    count = 0

    def _add(self, nodes: int) -> None:
        self.count += nodes
        if self.count > MOST_NODES:
            raise TooLarge

    def start(self, tag, attrib, nsmap=None) -> None:
        self._add(1 + len(attrib) + len(nsmap or ()))

    def comment(self, text) -> None:
        self._add(1)

    def pi(self, target, data=None) -> None:
        self._add(1)

    def end(self, tag) -> None:
        pass

    def data(self, text) -> None:
        pass

    def close(self) -> None:
        pass


def _sparse(archive: zipfile.ZipFile) -> None:
    """A package whose XML is no denser than a reader takes on, whatever a part is called: what
    is not XML stops the parser at once, and what breaks half way the reader then refuses."""
    nodes = _Nodes()
    for part in archive.infolist():
        parser = etree.XMLParser(target=nodes, resolve_entities=False, no_network=True)
        with archive.open(part) as stream:
            try:
                while chunk := stream.read(1 << 20):
                    parser.feed(chunk)
                parser.close()
            except etree.LxmlError:
                continue


def opened(path: Path) -> OpcPackage:
    try:
        with zipfile.ZipFile(path) as archive:
            bounded(archive)
            _sparse(archive)
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError) as error:
        raise Unreadable from error
    try:
        return OpcPackage.open(str(path))
    except (PackageNotFoundError, KeyError, ValueError, etree.LxmlError) as error:
        raise Unreadable from error


def safe(href: str) -> str | None:
    href = href.strip()
    return href if href and urlsplit(href).scheme.lower() in SCHEMES else None


def picture(relationship) -> tuple[str, bytes] | None:
    """A picture's bytes and their hash, where the file holds one we can show."""
    if relationship is None or relationship.is_external:
        return None
    data = relationship.target_part.blob
    if store.sniff(data[:1024]) not in store.IMAGES:
        return None
    return hashlib.sha256(data).hexdigest(), data


@dataclass
class Charted:
    """A chart and the table of its data, and what reading them could not carry."""

    blocks: tuple[Block, Block]
    lost: Counter[str] = field(default_factory=Counter)
    fonts: set[str] = field(default_factory=set)


def chart(relationship, locale: str) -> Charted | None:
    """A chart over a table of the sheet its workbook keeps; or, its workbook not in the file,
    over a table of the values it last showed."""
    if relationship is None or relationship.is_external:
        return None
    found = charts.parse(etree.fromstring(relationship.target_part.blob))
    if not found or not found.kind:
        return None
    made = _embedded(relationship.target_part, found, locale)
    if made is None:
        shown = xlsx.shown(found, locale)
        if shown is None:
            return None
        made = Charted(shown)
    made.lost["chartDetails"] += found.details
    return made


def _embedded(part, found: charts.Found, locale: str) -> Charted | None:
    layout = charts.layout(found.series)
    workbook = next(
        (
            relation.target_part.blob
            for relation in part.rels.values()
            if relation.reltype.endswith("/package") and not relation.is_external
        ),
        None,
    )
    if layout is None or workbook is None:
        return None
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "chart.xlsx"
        path.write_bytes(workbook)
        try:
            imported = xlsx.embedded(path, locale, layout.box.sheet)
        except Unreadable, TooLarge:
            imported = None
    if imported is None:
        return None
    table = imported.tabs[0].blocks[0]
    table.attrs.pop("name", None)
    found.details |= not layout.neat
    rows, cols, box = table.grid.rows, table.grid.cols, layout.box
    over = {
        "table": table.id,
        "from": {
            "row": rows[min(box.top, len(rows)) - 1],
            "col": cols[min(box.left, len(cols)) - 1],
        },
        "to": {
            "row": rows[min(box.bottom, len(rows)) - 1],
            "col": cols[min(box.right, len(cols)) - 1],
        },
    }
    return Charted(
        (table, charts.chart(found, layout, over)),
        Counter(imported.report["lost"]),
        {each["from"] for each in imported.report["fonts"]},
    )


def _counted(counts: list, level: int, kind: str) -> tuple[list, int]:
    """The counts down to a level, and the number an item of a kind there gets from them."""
    found = (counts + [None] * (level + 1))[: level + 1]
    before = found[level]
    return found, before[1] + 1 if before and before[0] == kind else 1


def numbered(content: list[Block], numbers: dict[str, int], lost: Counter[str]) -> None:
    """Our list numbers, which count on within a run of items (frontend lists.ts), made the
    file's, by each item's number there: an item the file numbers 1 starts again, one that
    counts on from the last item of its kind before other blocks or kinds came between
    continues it, any other is counted. A nested item that starts a run as the file numbers
    it continues the list above it, so the items after it count on at their own levels."""
    counts: list[tuple[str, int] | None] = []
    last: dict[str, list[tuple[str, int] | None]] = {}
    for block in content:
        for cell in block.cells:
            numbered(cell.blocks, numbers, lost)
        kind = block.attrs.get("list") if block.type == "paragraph" else None
        if not kind:
            counts = []
            continue
        level = round((block.attrs.get("indent") or 0) / INDENT_STEP)
        fresh = not counts
        counts, count = _counted(counts, level, kind)
        theirs = numbers.get(block.id)
        carried, after = _counted(last.get(kind, []), level, kind)
        if kind == "number" and theirs is not None and theirs != count:
            if theirs == 1:
                block.attrs["restart"] = True
                count = 1
            elif after == theirs:
                block.attrs["continued"] = True
                counts, count = carried, after
            else:
                lost["listNumbers"] += 1
        elif kind == "number" and fresh and level and after == theirs and any(carried[:level]):
            block.attrs["continued"] = True
            counts = carried
        counts[level] = (kind, count)
        last[kind] = counts
