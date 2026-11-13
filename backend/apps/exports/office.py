"""What every Office file of a document shares: its language, today's date as its language writes
it, its core properties, the characters XML cannot hold, and what a table's cell shows and how
its design draws it."""

import re
from datetime import datetime, time

import icu
from django.utils import timezone
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.package import OpcPackage
from docx.opc.parts.coreprops import CorePropertiesPart

from apps.content import blocks, designs, palette
from apps.content.blocks import Block, Run
from apps.documents.models import Node

TEXTUAL = {"paragraph", "title", "subtitle", "heading"}
KIND_ALIGNS = {"number": "right", "bool": "center", "error": "center"}
INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def attr(marks: dict, name: str, key: str):
    value = marks.get(name)
    return value.get(key) if isinstance(value, dict) else None


def solid(kind: str, tint: object) -> str | None:
    """A tint as the RRGGBB a program without transparency draws, a translucent one over white
    paper; None for none."""
    if isinstance(tint, str) and re.fullmatch(r"#[0-9a-f]{8}", tint):
        alpha = int(tint[7:], 16) / 255
        return "".join(
            f"{round(int(tint[at : at + 2], 16) * alpha + 255 * (1 - alpha)):02X}"
            for at in (1, 3, 5)
        )
    return palette.text(tint) if kind == "text" else palette.highlight(tint)


Slot = tuple[str, str]


def own_looks(table: Block) -> tuple[dict[Slot, str], dict[Slot, dict]]:
    """The fill and the edges each slot of a table keeps over its design, by row and column:
    a cell's own, its merge's outer sides where it is merged, else its row's or its column's."""
    grid = table.grid or blocks.Grid([], [])
    fills: dict[Slot, str] = {}
    edges: dict[Slot, dict] = {}
    taken = set()
    for each in blocks.placed(table):
        for y in range(each.y, each.y + each.rows):
            for x in range(each.x, each.x + each.cols):
                slot = (grid.rows[y], grid.cols[x])
                taken.add(slot)
                if each.cell.fill:
                    fills[slot] = each.cell.fill
                outer = {
                    "top": y == each.y,
                    "bottom": y == each.y + each.rows - 1,
                    "left": x == each.x,
                    "right": x == each.x + each.cols - 1,
                }
                if mine := {
                    side: line for side, line in (each.cell.edges or {}).items() if outer[side]
                }:
                    edges[slot] = mine
    for row in grid.rows:
        for col in grid.cols:
            if (row, col) in taken:
                continue
            look = grid.row_looks.get(row) or grid.col_looks.get(col) or {}
            if look.get("fill"):
                fills[(row, col)] = look["fill"]
            if look.get("edges"):
                edges[(row, col)] = look["edges"]
    return fills, edges


def area(design: dict, grid: blocks.Grid) -> tuple[int, int, int, int] | None:
    """The first and last row and column, from 0, a design lies over; None where its ends are
    gone."""
    given = design.get("area")
    if not given:
        return 0, 0, len(grid.rows) - 1, len(grid.cols) - 1
    (top, left), (bottom, right) = (
        str(given.get(end) or "").partition(":")[::2] for end in ("from", "to")
    )
    if not {top, bottom} <= set(grid.rows) or not {left, right} <= set(grid.cols):
        return None
    return (
        grid.rows.index(top),
        grid.cols.index(left),
        grid.rows.index(bottom),
        grid.cols.index(right),
    )


def designed(table: Block) -> dict[Slot, designs.Cell]:
    """Each slot of a table, by row and column, as its designs (D30) draw it with the fills and
    edges its cells keep over them: its parts, fill, marks, capitals, alignment and four edges."""
    grid = table.grid or blocks.Grid([], [])
    fills, edges = own_looks(table)
    rows = {row: y for y, row in enumerate(grid.rows)}
    cols = {col: x for x, col in enumerate(grid.cols)}
    layers = [
        (design, bounds)
        for design in table.attrs.get("designs") or []
        if (bounds := area(design, grid)) is not None
    ]
    own = {(rows[row], cols[col]): mine for (row, col), mine in edges.items()}
    found = {
        (grid.rows[y], grid.cols[x]): cell
        for (y, x), cell in designs.laid(layers, len(grid.rows), len(grid.cols), own).items()
    }
    for slot, fill in fills.items():
        found[slot].fill = fill
    return found


def shown(table: Block, cell: blocks.Cell) -> list[Block]:
    """What a cell shows: its value where a formula or a number format makes one, in its text's
    look (frontend editor/tables.ts retyped), else its blocks."""
    grid = table.grid
    key = blocks.key_of(cell.row, cell.col)
    value = grid.values.get(key) if isinstance(grid.values.get(key), dict) else None
    if key not in grid.formulas and (key not in grid.formats or value is None):
        return cell.blocks or [Block("paragraph")]
    first = cell.blocks[0] if cell.blocks else Block("paragraph")
    runs = [run for block in cell.blocks for run in block.runs if isinstance(run, Run) and run.text]
    attrs = dict(first.attrs) if first.type == "paragraph" else {}
    kept = attrs.get("endMarks")
    marks = runs[0].marks if runs else (kept if isinstance(kept, dict) else {})
    kind = (value or {}).get("kind")
    if not attrs.get("align") and kind in KIND_ALIGNS:
        attrs["align"] = KIND_ALIGNS[kind]
    text = (value or {}).get("text")
    text = text if isinstance(text, str) else ""
    if not text:
        attrs["endMarks"] = marks
    return [Block("paragraph", first.id, attrs, [Run(text, marks)] if text else [])]


def language_of(document: Node) -> str:
    found = icu.Locale.addLikelySubtags(icu.Locale(document.locale.replace("-", "_")))
    return f"{found.getLanguage()}-{found.getCountry()}"


def today(document: Node) -> str:
    locale = icu.Locale(document.locale.replace("-", "_"))
    format = icu.DateFormat.createDateInstance(icu.DateFormat.SHORT, locale)
    return format.format(datetime.combine(timezone.localdate(), time(12)))


def core(package: OpcPackage, document: Node) -> None:
    part = CorePropertiesPart.default(package)
    props = part.core_properties
    props.title = document.title
    props.last_modified_by = ""
    props.language = language_of(document)
    props.created = document.created_at
    props.modified = document.updated_at
    package.relate_to(part, RT.CORE_PROPERTIES)
