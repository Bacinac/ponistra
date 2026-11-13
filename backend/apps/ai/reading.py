"""What a model reads of a tab: its blocks in order, each on a line of its own after its id
and its kind, a table's rows after it as the table shows them; to write it anew, each text
with its formatted parts tagged and each cell after its address; whole, to work on anything
in it; or what changed in it since a version, as code finds it."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from apps.content import blocks, styles
from apps.content.blocks import Block, Note, Run, key_of
from apps.content.formulas import column_name
from apps.content.operations import PROPOSALS, REVIEWED, TEXTBLOCKS, WORDS

KINDS = {"bullet": "bullet item", "number": "numbered item", "check": "checklist item"}


def _kind(block: Block) -> str:
    if block.type == "heading":
        return f"heading {block.attrs.get('level', 1)}"
    if (listed := block.attrs.get("list")) in KINDS:
        return KINDS[listed]
    return block.type


def _rows(block: Block) -> list[str]:
    grid = block.grid
    if grid is None:
        return []
    nodes = {key_of(cell.row, cell.col): cell.text for cell in block.cells}
    rows = []
    for row in grid.rows:
        shown = [
            nodes.get(key) or grid.values.get(key, {}).get("text", "")
            for key in (key_of(row, col) for col in grid.cols)
        ]
        rows.append("| " + " | ".join(each.replace("\n", " ") for each in shown) + " |")
    return rows


def _shown(block: Block) -> str:
    if block.type in {"image", "chart", "pdf"}:
        return str(block.attrs.get("alt") or block.attrs.get("title") or "")
    if block.type == "table":
        return str(block.attrs.get("name") or "")
    return block.text


def text_of(found: list[Block]) -> str:
    lines = []
    for block in found:
        shown = _shown(block)
        if block.type != "table" and not shown.strip():
            continue
        lines.append(f"[{block.id}] {_kind(block)}: {shown}".rstrip())
        if block.type == "table":
            lines += _rows(block)
    return "\n".join(lines)


def _entries(found: list[Block]) -> list[tuple[str, str, str]]:
    """Each block, footnote and table row with text, by id: what it is and its text."""
    entries = []
    for block in found:
        if block.type == "table":
            name = block.attrs.get("name")
            what = f'table "{name}" row' if name else "table row"
            rows = block.grid.rows if block.grid else []
            entries += [
                (f"{block.id} {row}", what, line)
                for row, line in zip(rows, _rows(block), strict=True)
                if line.replace("|", "").strip()
            ]
            continue
        if text := _shown(block).replace("\n", " ").strip():
            entries.append((block.id, _kind(block), text))
        entries += [
            (note.id, f"{note.kind}note", note.text.replace("\n", " "))
            for note in block.notes
            if note.text.strip()
        ]
    return entries


def _worded(old: str, new: str) -> str:
    """The new text with the words taken out and written in marked, a change across spaces
    alone shown as one."""
    before, after = WORDS.findall(old), WORDS.findall(new)
    spans = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        taken, written = "".join(before[i1:i2]), "".join(after[j1:j2])
        if (
            op != "equal"
            and len(spans) > 1
            and spans[-2][0] != "equal"
            and not spans[-1][1].strip()
        ):
            space = spans.pop()[1]
            _, out, into = spans.pop()
            taken, written = out + space + taken, into + space + written
        spans.append((op, taken, written))
    shown = []
    for op, taken, written in spans:
        if op == "equal":
            shown.append(taken)
            continue
        if taken:
            shown.append(f"[-{taken}-]")
        if written:
            shown.append(f"{{+{written}+}}")
    return "".join(shown)


def changes_of(old: list[Block], new: list[Block]) -> list[str]:
    """What changed from the old blocks to the new, as code finds it: each block, footnote and
    row added, removed, moved or changed, on a line of its own after its id, in the new order
    with what was removed where it stood, a changed text word by word."""
    before, after = _entries(old), _entries(new)
    was = {id: (what, text) for id, what, text in before}
    now = {id for id, _, _ in after}
    matched = SequenceMatcher(
        None, [id for id, _, _ in before], [id for id, _, _ in after], autojunk=False
    )
    lines = []
    for op, i1, i2, j1, j2 in matched.get_opcodes():
        lines += [
            f"[{id}] {what} removed: {text}" for id, what, text in before[i1:i2] if id not in now
        ]
        for id, what, text in after[j1:j2]:
            if id not in was:
                lines.append(f"[{id}] {what} added: {text}")
                continue
            old_what, old_text = was[id]
            kind = what if old_what == what else f"{old_what} → {what}"
            shown = text if old_text == text else _worded(old_text, text)
            if op != "equal":
                lines.append(f"[{id}] {kind} moved: {shown}")
            elif (old_what, old_text) != (what, text):
                lines.append(f"[{id}] {kind} changed: {shown}")
    return lines


DESCRIBED = {"chart": "title", "image": "alt"}


@dataclass
class Tagged:
    """A tab as a model reads it to write its words anew, and the ids of what it may write:
    the blocks and notes with text, the tables with cells of text, and the charts and images
    with a title or a description."""

    lines: list[str] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    described: list[str] = field(default_factory=list)

    def text(self, block: Block) -> None:
        if block.text.strip():
            self.lines.append(f"[{block.id}] {_kind(block)}: {blocks.tagged(block.runs)}")
            self.texts.append(block.id)
        for note in block.notes:
            if note.text.strip():
                self.lines.append(f"[{note.id}] {note.kind}note: {blocks.tagged(note.runs)}")
                self.texts.append(note.id)

    def table(self, block: Block) -> None:
        formulas = block.grid.formulas if block.grid is not None else {}
        self.lines.append(f"[{block.id}] table")
        for cell in sorted(block.cells, key=lambda cell: _slot(block, cell)):
            if not cell.light:
                for each in cell.blocks:
                    self.text(each)
            elif key_of(cell.row, cell.col) not in formulas and cell.text.strip():
                self.lines.append(f"[{block.id} {cell.row} {cell.col}] cell: {cell.text}")
                if block.id not in self.tables:
                    self.tables.append(block.id)


def _slot(table: Block, cell) -> tuple[int, int]:
    if table.grid is None:
        return 0, 0
    return table.grid.rows.index(cell.row), table.grid.cols.index(cell.col)


def tagged_of(found: list[Block]) -> Tagged:
    tagged = Tagged()
    for block in found:
        if block.type == "table":
            tagged.table(block)
        elif (name := DESCRIBED.get(block.type)) and (value := block.attrs.get(name)):
            tagged.lines.append(f"[{block.id}] {block.type} {name}: {value}")
            tagged.described.append(block.id)
        elif block.type in TEXTBLOCKS:
            tagged.text(block)
    return tagged


CHANGES = {"insertion": "proposed inserted", "deletion": "proposed deleted"}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _said(name: str, value) -> str:
    """A mark, or a proposal with its author and id."""
    if name in REVIEWED:
        what = CHANGES.get(name, "formatting proposed")
        return f"{what} by {value.get('author')} ({value.get('id')})"
    return f"{name} {_json(value)}" if value else name


def _legend(runs: list) -> str:
    """What each tag of the text holds, numbered as `blocks.tagged` numbers them."""
    said, number = [], 0
    for run in runs:
        if isinstance(run, Run) and not run.marks:
            continue
        number += 1
        if isinstance(run, Run):
            parts = [_said(name, value) for name, value in run.marks.items()]
        else:
            own = f"{run.kind}note {run.id}" if isinstance(run, Note) else f"field {run.kind}"
            parts = [own, *(_said(name, value) for name, value in run.proposed.items())]
        said.append(f"<{number}> {', '.join(parts)}")
    return " · ".join(said)


def _head(block: Block) -> str:
    """A block's id, kind and attributes; a table's designs by their names, the parts they turn
    on and the cells they lie over, without the looks they draw."""
    attrs = {name: value for name, value in block.attrs.items() if name not in PROPOSALS}
    if designs := attrs.get("designs"):
        attrs["designs"] = [
            {key: each[key] for key in ("name", "on", "area") if key in each} for each in designs
        ]
    return f"[{block.id}] {block.type}" + (f" {_json(attrs)}" if attrs else "")


@dataclass
class Whole:
    """A tab as a model reads it to work on anything in it, with the text of each formula of
    its tables by table and cell: of a table longer than `most` rows only its first, saying how
    many it has, of `sizes` where it is cut."""

    formulas: Mapping[str, Mapping[str, str]]
    lines: list[str] = field(default_factory=list)
    most: int | None = None
    sizes: Mapping[str, int] = field(default_factory=dict)

    def block(self, block: Block, indent: str = "") -> None:
        if block.type == "table":
            self.table(block, indent)
            return
        tagged = blocks.tagged(block.runs) if block.type in TEXTBLOCKS else ""
        self.lines.append(f"{indent}{_head(block)}" + (f": {tagged}" if tagged else ""))
        if legend := _legend(block.runs):
            self.lines.append(f"{indent}    tags: {legend}")
        if proposed := [
            _said(name, block.attrs[name]) for name in REVIEWED if block.attrs.get(name)
        ]:
            self.lines.append(f"{indent}    block: {', '.join(proposed)}")
        for note in block.notes:
            self.lines.append(f"{indent}[{note.id}] {note.kind}note: {blocks.tagged(note.runs)}")
            if legend := _legend(note.runs):
                self.lines.append(f"{indent}    tags: {legend}")

    def table(self, block: Block, indent: str) -> None:
        grid = block.grid or blocks.Grid([], [])
        own = self.formulas.get(block.id, {})
        rows = grid.rows[: self.most]
        self.lines += [
            indent + _head(block),
            f"{indent}    rows: " + " ".join(f"{id}={at}" for at, id in enumerate(rows, 1)),
            f"{indent}    columns: "
            + " ".join(f"{id}={column_name(at)}" for at, id in enumerate(grid.cols, 1)),
        ]
        size = self.sizes.get(block.id, len(grid.rows))
        if len(rows) < size:
            self.lines.append(
                f"{indent}    shown: rows 1–{len(rows)} of {size}; the read "
                "tool reads others, the profile tool the whole table"
            )
        if proposed := block.attrs.get("proposedRows"):
            self.lines.append(
                f"{indent}    rows proposed: "
                + ", ".join(
                    f"{row} {_said(name, change)}"
                    for row, changes in proposed.items()
                    for name, change in changes.items()
                )
            )
        for axis, looks in (("row", grid.row_looks), ("column", grid.col_looks)):
            if looks:
                self.lines.append(f"{indent}    {axis} looks: {_json(looks)}")
        placed = {key_of(each.cell.row, each.cell.col): each.cell for each in blocks.placed(block)}
        for key in (key_of(row, col) for row in rows for col in grid.cols):
            cell = placed.get(key)
            if key not in own and cell is None:
                continue
            row, _, col = key.partition(":")
            to = f" to {cell.to}" if cell is not None and cell.to else ""
            at = f"{indent}[{block.id} {row} {col}{to}]"
            format = f" format {_json(grid.formats[key])}" if key in grid.formats else ""
            if key in own:
                shown = grid.values.get(key, {}).get("text", "")
                self.lines.append(f"{at} {own[key]}" + (f" → {shown}" if shown else "") + format)
            elif (light := blocks.look_of(cell.blocks)) is not None:
                text, look = light
                if text or format:
                    self.lines.append(f"{at} {text}" + (f" {_json(look)}" if look else "") + format)
            else:
                self.lines.append(f"{at} cell:{format}")
                for each in cell.blocks:
                    self.block(each, indent + "    ")

    def styles(self, theme: Mapping[str, str], looks: Mapping[str, dict]) -> None:
        self.lines.append("styles:")
        kinds = list(styles.TEMPLATE[styles.STYLES])
        for id, look in sorted(
            looks.items(),
            key=lambda item: (item[0] not in kinds, kinds.index(item[1]["kind"]), item[0]),
        ):
            named = f' "{look["name"]}"' if look.get("name") else ""
            family = styles.family(theme, look["font"])
            font = look["font"] if family == look["font"] else f"{look['font']} ({family})"
            self.lines.append(f"[{id}]{named} {look['kind']}: font {font}, {look['size']:g} pt")


def whole_of(
    found: list[Block],
    formulas: Mapping[str, Mapping[str, str]],
    theme: Mapping[str, str],
    looks: Mapping[str, dict],
    most: int | None = None,
    sizes: Mapping[str, int] | None = None,
) -> list[str]:
    whole = Whole(formulas, most=most, sizes=sizes or {})
    for block in found:
        whole.block(block)
    whole.styles(theme, looks)
    return whole.lines
