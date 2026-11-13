"""A table's design (D30) cell by cell, by the rules of the program it came from
(schema/tables.json), as the editor's resolver (editor/design.ts) gives it: the parts in each
cell, its fill, marks, capitals and alignment, and its four edges once the edges two cells
share are settled."""

import json
from dataclasses import dataclass, field

from django.conf import settings

from apps.content import palette

TABLES = json.loads(settings.SCHEMA.with_name("tables.json").read_text())
CATALOGUE = TABLES["designs"]
# The design a new table takes.
NEW = "grid"


def ours(id: str) -> dict:
    """One of our designs as a table carries it, named by its id."""
    return {"name": id, **CATALOGUE[id]}


SIDES = {
    "top": ("insideH", -1, 0),
    "bottom": ("insideH", 1, 0),
    "left": ("insideV", 0, -1),
    "right": ("insideV", 0, 1),
}
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
NONE = "none"
Slot = tuple[int, int]


@dataclass
class Cell:
    parts: list[str]
    fill: str | None = None
    marks: dict = field(default_factory=dict)
    caps: str | None = None
    align: str | None = None
    valign: str | None = None
    edges: dict[str, dict | None] = field(default_factory=dict)


def parts_at(design: dict, row: int, col: int, rows: int, cols: int) -> list[str]:
    """The parts that apply in the cell at row and col (from 0) of a design rows by cols, in
    the order a later one wins."""
    here, _ = _placed(design, row, col, rows, cols)
    return [part for part in TABLES["rules"][design["rules"]]["order"] if part in here]


def _placed(
    design: dict, row: int, col: int, rows: int, cols: int
) -> tuple[set[str], dict[str, tuple[int, int]]]:
    """The parts in a cell, and for each band among them where the cell stands in it and how
    many rows or columns it spans, cut short by the table's end or not."""
    rules = TABLES["rules"][design["rules"]]
    on = design.get("on", {})
    defined = design.get("parts", {})
    here = {"table"}
    if on.get("header") and row == 0:
        here.add("header")
    if on.get("totals") and row == rows - 1:
        here.add("totals")
    if on.get("firstColumn") and col == 0:
        here.add("firstColumn")
    if on.get("lastColumn") and col == cols - 1:
        here.add("lastColumn")

    def claims(part: str) -> bool:
        return (
            part not in rules["claimWhereDefined"]
            or part in defined
            or any(
                part in pair and corner in defined and all(on.get(each) for each in pair)
                for corner, pair in TABLES["corners"].items()
            )
        )

    if rules["lastYields"]:
        for first, last in (("header", "totals"), ("firstColumn", "lastColumn")):
            if first in here and claims(first):
                here.discard(last)
    bands = design.get("bands", {})
    spans: dict[str, tuple[int, int]] = {}
    for kind, at, switch, names in (
        ("rowBands", row, "rowBands", ("rowBand1", "rowBand2")),
        ("columnBands", col, "columnBands", ("columnBand1", "columnBand2")),
    ):
        reach = rules[kind]
        if not on.get(switch) or any(p in here and claims(p) for p in reach["skip"]):
            continue
        after = reach["after"]
        at -= 1 if after and on.get(after) and claims(after) else 0
        first, second = bands.get("rows" if kind == "rowBands" else "columns", (1, 1))
        if first + second:
            offset = at % (first + second)
            if offset < first:
                here.add(names[0])
                spans[names[0]] = (offset, first)
            else:
                here.add(names[1])
                spans[names[1]] = (offset - first, second)
    for corner, (across, down) in TABLES["corners"].items():
        if across in here and down in here:
            here.add(corner)
    return here, spans


def _rgb(color: str | None) -> tuple[int, int, int]:
    hex = palette.text(color) if color else None
    value = int(hex, 16) if hex else 0
    return value >> 16, (value >> 8) & 255, value & 255


def _darkness(rules: dict, edge: dict) -> tuple[int, ...]:
    rgb = _rgb(edge.get("color"))
    return tuple(
        -sum(w * x for w, x in zip(weights, rgb, strict=True)) for weights in rules["darkness"]
    )


def _weight(rules: dict, edge: dict) -> tuple:
    kind = rules["classes"].get(edge["line"], 2)
    code = rules["codes"][edge["line"]]
    eighths = edge["width"] * 8
    return (kind, eighths * code if kind == 2 else eighths, code, _darkness(rules, edge))


def kind_of(rules: dict, edge: dict) -> int:
    """Where among the kinds of line a program's rules rank the one nearest an edge stands: of
    its line, else a single one, the nearest width, the heavier where two are as near."""
    kinds = rules["kinds"]
    same = [i for i, kind in enumerate(kinds) if kind["line"] == edge["line"]] or [
        i for i, kind in enumerate(kinds) if kind["line"] == "single"
    ]
    return min(same, key=lambda i: (abs(kinds[i]["width"] - edge["width"]), -i))


def _rank(rules: dict, edge: dict) -> tuple:
    return (kind_of(rules, edge), _darkness(rules, edge))


def drawn(edge: dict | str | None) -> dict | None:
    """An edge as it draws: None where it draws no line."""
    return None if edge is None or edge == NONE else edge


def resolved(
    design: dict, rows: int, cols: int, own: dict[Slot, dict] | None = None
) -> dict[Slot, Cell]:
    """Each cell of a design rows by cols, with the cells' own edges over it. Cells set apart
    (`spacing`) each draw their own four sides, the table's inner lines on every one of them."""
    return laid([(design, (0, 0, rows - 1, cols - 1))], rows, cols, own)


def laid(
    layers: list[tuple[dict, tuple[int, int, int, int]]],
    rows: int,
    cols: int,
    own: dict[Slot, dict] | None = None,
) -> dict[Slot, Cell]:
    """Each cell of a table rows by cols under its designs, each over its first and last row and
    column, a later one over an earlier, with the cells' own edges over them. An edge two cells
    under one design share is settled by its rules; one between two designs, or beside a cell
    under none, by the rules of the table's first design, Word's in a table without one."""
    own = own or {}
    table = TABLES["rules"][layers[0][0]["rules"] if layers else "word"]
    cells = {
        (r, c): Cell([], edges=dict(own.get((r, c), {}))) for r in range(rows) for c in range(cols)
    }
    sources = {slot: dict.fromkeys(cell.edges, len(table["order"])) for slot, cell in cells.items()}
    under: dict[Slot, int | None] = dict.fromkeys(cells)
    for at, (design, (top, left, bottom, right)) in enumerate(layers):
        inner = {
            (r - top, c - left): edges
            for (r, c), edges in own.items()
            if top <= r <= bottom and left <= c <= right
        }
        found, kept = _raw(design, bottom - top + 1, right - left + 1, inner)
        for (r, c), cell in found.items():
            cells[(r + top, c + left)] = cell
            sources[(r + top, c + left)] = kept[(r, c)]
            under[(r + top, c + left)] = at
    for slot, cell in cells.items():
        for side in ("bottom", "right"):
            _, dr, dc = SIDES[side]
            across = (slot[0] + dr, slot[1] + dc)
            if across not in cells:
                continue
            here, there = under[slot], under[across]
            if any(layers[each][0].get("spacing") for each in (here, there) if each is not None):
                continue
            shared = here is not None and here == there
            rules = TABLES["rules"][layers[here][0]["rules"]] if shared else table
            other = OPPOSITE[side]
            a, b = drawn(cell.edges.get(side)), drawn(cells[across].edges.get(other))
            if rules["shared"] == "later":
                win = a if sources[slot].get(side, -2) >= sources[across].get(other, -2) else b
            elif a is None or b is None or a == b:
                win = a or b
            else:
                key = _weight if rules["shared"] == "weight" else _rank
                win = a if key(rules, a) >= key(rules, b) else b
            cell.edges[side] = cells[across].edges[other] = win
        for side in SIDES:
            cell.edges[side] = drawn(cell.edges.get(side))
    return cells


def _raw(
    design: dict, rows: int, cols: int, own: dict[Slot, dict]
) -> tuple[dict[Slot, Cell], dict[Slot, dict[str, int]]]:
    """Each cell of a design with the lines it takes on each side before two cells settle the
    edge they share, and where among the design's parts each came from."""
    spaced = bool(design.get("spacing"))
    rules = TABLES["rules"][design["rules"]]
    order = rules["order"]
    defined = design.get("parts", {})
    lines = design.get("lines", {})
    slots = [(r, c) for r in range(rows) for c in range(cols)]
    placed = {(r, c): _placed(design, r, c, rows, cols) for r, c in slots}
    names = {slot: [part for part in order if part in placed[slot][0]] for slot in slots}
    nominal = rules["regions"] == "nominal"
    no_inside_v = design.get("bands", {}).get("rows", (1, 1))[0] < rules["insideVWithRows"]
    cells: dict[Slot, Cell] = {}
    sources: dict[Slot, dict[str, int]] = {}
    for slot in slots:
        cell = cells[slot] = Cell(names[slot])
        for name in names[slot]:
            part = defined.get(name)
            if not part:
                continue
            if "fill" in part:
                cell.fill = part["fill"]
            for mark, attrs in part.get("marks", {}).items():
                if attrs is False:
                    cell.marks.pop(mark, None)
                else:
                    cell.marks[mark] = attrs
            for key in ("caps", "align", "valign"):
                if key in part:
                    setattr(cell, key, part[key])
        source = sources[slot] = {}
        for side, (inner, dr, dc) in SIDES.items():
            across = (slot[0] + dr, slot[1] + dc)
            outer = across not in names
            key = side if outer and not spaced else inner
            if key in lines:
                cell.edges[side], source[side] = lines[key], -1
            spans = placed[slot][1]
            for name in names[slot]:
                edges = defined.get(name, {}).get("edges")
                if not edges:
                    continue
                across_band = (side in ("top", "bottom")) == name.startswith("rowBand")
                if nominal and name in spans and across_band:
                    at, length = spans[name]
                    inside = at > 0 if side in ("top", "left") else at < length - 1
                else:
                    inside = not outer and name in names[across]
                key = inner if inside else side
                if key == "insideV" and no_inside_v and name.startswith("columnBand"):
                    continue
                if key in edges:
                    cell.edges[side], source[side] = edges[key], order.index(name)
            mine = own.get(slot, {})
            if side in mine and not (
                rules["own"] == "upperLeft" and not outer and side in ("top", "left")
            ):
                cell.edges[side], source[side] = mine[side], len(order)
    return cells, sources
