"""A tab's content in its Yjs state: the text as y-prosemirror lays it out under
`body`, each note inside the text where its mark is and, in a table, the cells whose content
is more than one look of plain text; the tab's defined names under `names`. A table's rows,
columns and the cells beside the text are its grid, kept in Postgres (`grids`). A header or
footer is laid out the same way in a fragment of the document's own state."""

import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from pycrdt import Doc, XmlElement, XmlFragment, XmlText

from apps.content import schema
from apps.content.grids import FORMAT, FORMULA, TEXT, TO, Laid, pieces_rekeyed

BODY = "body"
NOTE = "footnote"
FIELD = "field"
CELL = "cell"
PROPOSED = ("insertion", "deletion")
# What a light cell's paragraph may carry: its look, nothing that makes it a list or a proposal.
LOOK_ATTRS = ("align", "indent", "firstLine", "right", "style")
UNLOOKED_MARKS = (*PROPOSED, "formatting")
TEXTBLOCKS = tuple(
    name for name, spec in schema.SPEC["nodes"].items() if spec.get("content") == "inline*"
)


def new_id() -> str:
    return secrets.token_urlsafe(9)


@dataclass
class Run:
    text: str
    marks: dict[str, dict] = field(default_factory=dict)


@dataclass
class Note:
    """A footnote or, of kind "end", an endnote: its text where its mark is."""

    kind: str = "foot"
    id: str = field(default_factory=new_id)
    runs: list[Run] = field(default_factory=list)
    proposed: dict[str, dict] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


@dataclass
class Field:
    """A value the page fills in where it stands: "page", "pages", "title" or "date"."""

    kind: str
    proposed: dict[str, dict] = field(default_factory=dict)


@dataclass
class Grid:
    """A table's rows and columns and its cells' parts by "row:col": the text typed into a
    cell an importer brings plain, with no Cell of its own as a large sheet's are, formulas,
    formats and computed values; and the looks of its lines."""

    rows: list[str]
    cols: list[str]
    formulas: dict[str, list] = field(default_factory=dict)
    formats: dict[str, str] = field(default_factory=dict)
    values: dict[str, dict] = field(default_factory=dict)
    row_looks: dict[str, dict] = field(default_factory=dict)
    col_looks: dict[str, dict] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)


@dataclass
class Cell:
    """A cell of a table, in the slot of its row and column and, merged, down and right to
    the slot `to` names as "row:col", and the colour it is filled with and the lines it draws on
    its sides over its table's design. A light cell is plain text in one paragraph of one look,
    kept in the table's grid without a node of its own, as a sheet's thousands are."""

    row: str
    col: str
    blocks: list[Block] = field(default_factory=list)
    to: str | None = None
    light: bool = False
    fill: str | None = None
    edges: dict | None = None

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks if block.text)


@dataclass
class Placed:
    cell: Cell
    y: int
    x: int
    rows: int = 1
    cols: int = 1


@dataclass
class Block:
    type: str
    id: str = field(default_factory=new_id)
    attrs: dict = field(default_factory=dict)
    runs: list[Run | Note | Field] = field(default_factory=list)
    grid: Grid | None = None
    cells: list[Cell] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs if isinstance(run, Run))

    @property
    def notes(self) -> list[Note]:
        return [run for run in self.runs if isinstance(run, Note)]


def plain_of(text: XmlText) -> str:
    return "".join(part for part, _ in text.diff())


def chunks_of(element: XmlElement) -> tuple[list[tuple[XmlText, int, str]], int]:
    """The block's or note's texts, each with where it starts in their characters, and how
    many those are."""
    chunks, length = [], 0
    for child in element.children:
        if isinstance(child, XmlText):
            plain = plain_of(child)
            chunks.append((child, length, plain))
            length += len(plain)
    return chunks, length


def body_of(doc: Doc) -> XmlFragment:
    return doc.get(BODY, type=XmlFragment)


def table_ids(fragment: XmlFragment) -> list[str]:
    """The ids of the tables in the text, in its order."""
    return [
        element.attributes.get("id")
        for element in fragment.children
        if isinstance(element, XmlElement) and element.tag == "table"
    ]


def rekey_tables(fragments: list[XmlFragment], by: Mapping[str, str]) -> None:
    """The tables of the fragments under the new ids given, and the charts over them."""
    for fragment in fragments:
        for element in fragment.children:
            if not isinstance(element, XmlElement):
                continue
            if element.tag == "table" and (id := element.attributes.get("id")) in by:
                element.attributes["id"] = by[id]
            over = element.attributes.get("range") if element.tag == "chart" else None
            if isinstance(over, dict) and over.get("table") in by:
                element.attributes["range"] = {**over, "table": by[over["table"]]}


def retabled(content: list[Block]) -> list[Block]:
    """The blocks again, each table under a new id and what among them refers to one by its
    id, the charts and the formulas, referring to it by that: a copy that can stand beside
    the blocks it was made from."""
    by = {block.id: new_id() for block in content if block.type == "table"}
    found = []
    for block in content:
        if block.type == "table":
            grid = block.grid and replace(
                block.grid,
                formulas={
                    key: pieces_rekeyed(pieces, by) for key, pieces in block.grid.formulas.items()
                },
            )
            block = replace(block, id=by[block.id], grid=grid)
        elif block.type == "chart" and (over := block.attrs.get("range", {})).get("table") in by:
            block = replace(
                block, attrs={**block.attrs, "range": {**over, "table": by[over["table"]]}}
            )
        found.append(block)
    return found


def mark_name(name: str) -> str:
    # A mark that may overlap itself is stored as "name--<hash of its attributes>".
    return name.split("--", 1)[0]


def tagged(runs: list[Run | Note | Field]) -> str:
    """The text with each formatted part between tags numbered in order, <1>…</1>, each note
    and field a tag of its own, <2/>, and each line break <br/>: as a model reads a text to
    write it anew, the operation replace numbering them alike."""
    parts, number = [], 0
    for run in runs:
        text = run.text.replace("\n", "<br/>") if isinstance(run, Run) else ""
        if isinstance(run, Run) and not run.marks:
            parts.append(text)
            continue
        number += 1
        parts.append(f"<{number}>{text}</{number}>" if isinstance(run, Run) else f"<{number}/>")
    return "".join(parts)


def _text(text: XmlText) -> list[Run]:
    return [
        Run(part, {mark_name(name): value for name, value in (attributes or {}).items()})
        for part, attributes in text.diff()
    ]


def _proposed(element: XmlElement) -> dict[str, dict]:
    return {name: change for name in PROPOSED if (change := element.attributes.get(name))}


def _runs(element: XmlElement) -> list[Run | Note | Field]:
    runs: list[Run | Note | Field] = []
    for child in element.children:
        if isinstance(child, XmlText):
            runs.extend(_text(child))
        elif isinstance(child, XmlElement) and child.tag == NOTE:
            kind = "end" if child.attributes.get("kind") == "end" else "foot"
            text = [
                run for part in child.children if isinstance(part, XmlText) for run in _text(part)
            ]
            runs.append(Note(kind, child.attributes.get("id"), text, _proposed(child)))
        elif isinstance(child, XmlElement) and child.tag == FIELD:
            runs.append(Field(str(child.attributes.get("kind")), _proposed(child)))
    return runs


def placed(table: Block) -> list[Placed]:
    """The table's cells as it shows them, row by row. A cell whose row or column is gone,
    or whose slot an earlier merged cell covers, as two people's edits can leave it, is
    not shown; a merge that would overlap another covers its own slot alone."""
    grid = table.grid or Grid([], [])
    rows = {id: index for index, id in enumerate(grid.rows)}
    cols = {id: index for index, id in enumerate(grid.cols)}
    return spanned(table.cells, rows, cols)


def spanned(
    cells: Iterable[Cell], rows: Mapping[str, int], cols: Mapping[str, int]
) -> list[Placed]:
    """The cells as a table shows them, given where their rows and columns stand: those of
    `placed`, of a table read only as far as its cells and the slots they reach."""
    found = sorted(
        (
            (rows[cell.row], cols[cell.col], cell)
            for cell in cells
            if cell.row in rows and cell.col in cols
        ),
        key=lambda each: each[:2],
    )
    taken: set[tuple[int, int]] = set()
    shown = []
    for y, x, cell in found:
        if (y, x) in taken:
            continue
        to_row, _, to_col = (cell.to or "").partition(":")
        bottom, right = rows.get(to_row, y), cols.get(to_col, x)
        slots = {(row, col) for row in range(y, bottom + 1) for col in range(x, right + 1)}
        if bottom < y or right < x or slots & taken:
            bottom, right, slots = y, x, {(y, x)}
        taken |= slots
        shown.append(Placed(cell, y, x, bottom - y + 1, right - x + 1))
    return shown


def visible(table: Block) -> Block:
    """The table as it prints, without the rows and columns it hides: a merged cell keeps the
    part of its span still shown, one whose own slot is hidden is not shown, and the rows kept
    at the top end at the last of them still shown."""
    hidden = table.attrs.get("hidden") or {}
    out_rows, out_cols = set(hidden.get("rows", ())), set(hidden.get("cols", ()))
    if not out_rows and not out_cols or table.grid is None:
        return table
    grid = table.grid
    at_row = {id: y for y, id in enumerate(grid.rows)}
    at_col = {id: x for x, id in enumerate(grid.cols)}

    def last(lines: list[str], at: dict, out: set, start: str, end: str) -> str:
        span = lines[at[start] : max(at.get(end, at[start]), at[start]) + 1]
        return [id for id in span if id not in out][-1]

    cells = []
    for cell in table.cells:
        if cell.row in out_rows or cell.col in out_cols:
            continue
        if cell.row in at_row and cell.col in at_col and cell.to:
            to_row, _, to_col = cell.to.partition(":")
            bottom = last(grid.rows, at_row, out_rows, cell.row, to_row)
            right = last(grid.cols, at_col, out_cols, cell.col, to_col)
            cell = replace(
                cell, to=None if (bottom, right) == (cell.row, cell.col) else key_of(bottom, right)
            )
        cells.append(cell)
    attrs = {key: value for key, value in table.attrs.items() if key != "hidden"}
    if attrs.get("frozen") in at_row:
        kept = [id for id in grid.rows[: at_row[attrs["frozen"]] + 1] if id not in out_rows]
        if kept:
            attrs["frozen"] = kept[-1]
        else:
            del attrs["frozen"]
    rows = [id for id in grid.rows if id not in out_rows]
    cols = [id for id in grid.cols if id not in out_cols]
    return replace(table, attrs=attrs, grid=replace(grid, rows=rows, cols=cols), cells=cells)


def in_order(content: list[Block]) -> list[Block]:
    """Every block as it is read: after a table, the blocks of its cells row by row."""
    found = []
    for block in content:
        found.append(block)
        if block.type == "table":
            found.extend(inner for each in placed(block) for inner in each.cell.blocks)
    return found


def _attrs(element: XmlElement) -> dict:
    # Yjs has one number type, so a heading level of 2 can come back as 2.0.
    return {
        name: int(value) if isinstance(value, float) and value.is_integer() else value
        for name, value in element.attributes
        if name != "id"
    }


def blocks_in(parent: XmlFragment | XmlElement) -> list[Block]:
    return [
        Block(element.tag, element.attributes.get("id"), _attrs(element), _runs(element))
        for element in parent.children
        if isinstance(element, XmlElement)
    ]


def read(
    doc: Doc, grids: Mapping[str, Laid], of: XmlFragment | None = None, light: bool = True
) -> list[Block]:
    """The tab's blocks, or those of the fragment given, a header's or a footer's, each table
    with its grid; without the light cells, a table's cells are those with a node of their own
    and the light ones that place or number them, as the table shows them."""
    blocks = []
    for element in (of if of is not None else body_of(doc)).children:
        if not isinstance(element, XmlElement):
            continue
        if element.tag == "table":
            blocks.append(table_of(element, grids, light))
        else:
            blocks.append(
                Block(element.tag, element.attributes.get("id"), _attrs(element), _runs(element))
            )
    return blocks


def table_of(element: XmlElement, grids: Mapping[str, Laid], light: bool = True) -> Block:
    id = element.attributes.get("id")
    laid = grids.get(id)
    nodes = [
        (
            cell.attributes.get("row"),
            cell.attributes.get("col"),
            blocks_in(cell),
            cell.attributes.get("fill"),
            cell.attributes.get("edges"),
        )
        for cell in element.children
        if isinstance(cell, XmlElement) and cell.tag == CELL
    ]
    attrs = _attrs(element)
    if laid is None:
        return Block(
            element.tag,
            id,
            attrs,
            cells=[
                Cell(row, col, content, fill=fill, edges=edges)
                for row, col, content, fill, edges in nodes
            ],
        )
    for name, value in (
        ("name", laid.name or None),
        ("widths", laid.widths()),
        ("heights", laid.heights()),
        ("hidden", laid.hidden()),
        ("frozen", laid.frozen),
    ):
        if value is not None:
            attrs[name] = value
    if light:
        grid = Grid(
            laid.row_ids(),
            laid.col_ids(),
            laid.entries(FORMULA),
            laid.entries(FORMAT),
            laid.told(),
            {row.id: row.look for row in laid.rows if row.look is not None},
            {col.id: col.look for col in laid.cols if col.look is not None},
        )
    else:
        grid = Grid(laid.row_ids(), laid.col_ids())
    merges = laid.entries(TO)
    cells = [
        Cell(row, col, content, merges.get(key_of(row, col)), fill=fill, edges=edges)
        for row, col, content, fill, edges in nodes
    ]
    held = {key_of(row, col) for row, col, *_ in nodes}
    for row in laid.rows:
        for col, cell in row.cells.items():
            key = key_of(row.id, col)
            if key in held:
                continue
            look = laid.look_at(row.id, col)
            if (TEXT in cell or look or TO in cell) if light else _placing(cell, look):
                cells.append(light_cell(key, cell.get(TEXT, ""), look, cell.get(TO)))
    return Block(element.tag, id, attrs, grid=grid, cells=cells)


def _placing(cell: dict, look: dict | None) -> bool:
    """Whether a light cell bears on how the table's other cells are placed and numbered:
    merged, or in a style that can number it."""
    return TO in cell or "style" in ((look or {}).get("attrs") or {})


def node_texts(table: XmlElement) -> dict[str, str]:
    """The text of each cell of the table that has a node in the text, by "row:col"."""
    return {
        key_of(cell.attributes.get("row"), cell.attributes.get("col")): Cell(
            "", "", blocks_in(cell)
        ).text
        for cell in table.children
        if isinstance(cell, XmlElement) and cell.tag == CELL
    }


def key_of(row: str, col: str) -> str:
    return f"{row}:{col}"


def light_cell(key: str, text: str, look: dict | None = None, to: str | None = None) -> Cell:
    """A cell of plain text in one look, its paragraph's attributes and the marks over all of
    its text, or at its end where it has none, and its fill and edges."""
    row, _, col = key.partition(":")
    marks = dict((look or {}).get("marks") or {})
    attrs = dict((look or {}).get("attrs") or {})
    if marks and not text:
        attrs["endMarks"] = marks
    runs = [Run(text, marks)] if text else []
    fill, edges = (look or {}).get("fill"), (look or {}).get("edges")
    return Cell(
        row, col, [Block("paragraph", key, attrs, runs)], to, light=True, fill=fill, edges=edges
    )


def look_of(
    content: list[Block], fill: str | None = None, edges: dict | None = None
) -> tuple[str, dict] | None:
    """The text and the look of a cell's content where it is one paragraph of plain text in
    one look, which a light cell holds, with the cell's fill and edges; None where it needs a
    node of its own."""
    if len(content) != 1 or content[0].type != "paragraph" or content[0].cells:
        return None
    block = content[0]
    given = {
        name: value
        for name, value in block.attrs.items()
        if not schema.at_default("paragraph", name, value)
    }
    if set(given) - {*LOOK_ATTRS, "endMarks"}:
        return None
    runs = block.runs
    if any(not isinstance(run, Run) for run in runs):
        return None
    marks = runs[0].marks if runs else dict(given.get("endMarks") or {})
    if any(run.marks != marks for run in runs) or set(marks) & set(UNLOOKED_MARKS):
        return None
    attrs = {name: given[name] for name in LOOK_ATTRS if given.get(name) is not None}
    look = {
        **({"marks": marks} if marks else {}),
        **({"attrs": attrs} if attrs else {}),
        **({"fill": fill} if fill else {}),
        **({"edges": edges} if edges else {}),
    }
    return "".join(run.text for run in runs), look


def utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return value, at


def clocks(doc: Doc) -> dict[int, int]:
    """The doc's state vector: the clock each client's next item gets."""
    state = doc.get_state()
    count, at = _varint(state, 0)
    found = {}
    for _ in range(count):
        client, at = _varint(state, at)
        found[client], at = _varint(state, at)
    return found


def _clock(doc: Doc) -> int:
    """The clock the doc's own next item gets."""
    return clocks(doc).get(doc.client_id, 0)


@dataclass
class Written:
    """Where a write put each block's text, so a position in it can be given as Yjs gives
    one, following the text's later edits: per block, each stretch one XmlText holds, as
    its offset in the block's text and length (UTF-16 units, as Yjs counts) and the clock
    of its first character."""

    client: int
    texts: dict[str, list[tuple[int, int, int]]] = field(default_factory=dict)

    def position(self, block: str, offset: int, assoc: int = 0) -> dict | None:
        """The relative position of the character at the offset, as Y.relativePositionToJSON
        writes it."""
        for start, length, clock in self.texts.get(block, []):
            if start <= offset < start + length:
                item = {"client": self.client, "clock": clock + offset - start}
                return {"item": item, "assoc": assoc}
        return None


def _write_text(text: XmlText, runs: list[Run]) -> None:
    # The plain text goes in as one item, so its characters' ids run on without gaps;
    # pycrdt counts the formatted ranges in UTF-8 bytes.
    text.insert(0, "".join(run.text for run in runs))
    at = 0
    for run in runs:
        size = len(run.text.encode())
        if run.marks:
            text.format(at, at + size, run.marks)
        at += size


def write_block(
    parent: XmlFragment | XmlElement,
    block: Block,
    doc: Doc,
    written: Written,
    at: int | None = None,
) -> XmlElement:
    """The block, its text and notes but not a table's cells, at the end of its parent or
    at the index given."""
    prelim = XmlElement(block.type, {"id": block.id, **block.attrs})
    element = parent.children.append(prelim) if at is None else parent.children.insert(at, prelim)
    stretches = written.texts.setdefault(block.id, [])
    offset = 0
    pending: list[Run] = []

    def flush() -> None:
        nonlocal offset
        if not pending:
            return
        text = element.children.append(XmlText())
        clock = _clock(doc)
        _write_text(text, pending)
        length = sum(utf16(run.text) for run in pending)
        stretches.append((offset, length, clock))
        offset += length
        pending.clear()

    for run in block.runs:
        if isinstance(run, Note):
            flush()
            attrs = {"id": run.id, "kind": run.kind, **run.proposed}
            note = element.children.append(XmlElement(NOTE, attrs))
            if run.runs:
                _write_text(note.children.append(XmlText()), run.runs)
        elif isinstance(run, Field):
            flush()
            element.children.append(XmlElement(FIELD, {"kind": run.kind, **run.proposed}))
        elif run.text:
            pending.append(run)
    flush()
    return element
