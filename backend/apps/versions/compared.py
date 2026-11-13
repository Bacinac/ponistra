"""A tab compared with a file that comes back (D41): the file read as the import reads it,
without making a document of it, or another document's tab, and each difference from the tab,
as code finds it, the operation that proposes it, accepted or rejected one by one."""

import re
from difflib import SequenceMatcher

from apps.actions.language import _proposed
from apps.collab import server
from apps.content import blocks
from apps.content.blocks import Block, Note, Run, key_of
from apps.content.operations import TEXTBLOCKS
from apps.content.sheets import Refused
from apps.documents.models import Node, Tab
from apps.documents.views import live
from apps.imports import convert
from apps.imports.formats import WORD
from apps.imports.reading import TooLarge, Unreadable

ALIKE = 0.5
# Pairing the blocks of a stretch that changed weighs each against each, so a longer stretch
# goes as taken out and written anew.
PAIRED = 40_000
SPACES = re.compile(r"\s+")
KEPT_ATTRS = ("level", "list", "checked", "align")
KEPT_MARKS = ("strong", "em", "underline", "strike", "sub", "sup", "link")


def _said(block: Block) -> str:
    if block.type == "table":
        return "\n".join("\t".join(row) for row in _cells(block))
    return SPACES.sub(" ", block.text).strip()


def _cells(table: Block) -> list[list[str]]:
    grid = table.grid
    if grid is None:
        return []
    nodes = {key_of(cell.row, cell.col): cell.text for cell in table.cells}
    return [
        [
            (nodes.get(key) or grid.values.get(key, {}).get("text", "")).strip()
            for key in (key_of(row, col) for col in grid.cols)
        ]
        for row in grid.rows
    ]


def _compared(found: list[Block]) -> list[Block]:
    """The blocks a comparison reads: those with text, and tables with any in their cells."""
    return [
        block
        for block in found
        if (block.type in TEXTBLOCKS or block.type == "table") and _said(block).strip()
    ]


def _run(run: Run | Note | blocks.Field) -> dict:
    if isinstance(run, Note):
        content = [_run(each) for each in run.runs if each.text]
        return {"type": "footnote", "attrs": {"kind": run.kind}, "content": content}
    if isinstance(run, blocks.Field):
        return {"type": "field", "attrs": {"kind": run.kind}}
    named = {blocks.mark_name(key): value for key, value in run.marks.items()}
    marks = [{"type": name, "attrs": value} for name, value in named.items() if name in KEPT_MARKS]
    return {"type": "text", "text": run.text, **({"marks": marks} if marks else {})}


def node_of(block: Block, id: str) -> dict:
    """The block under the id given as the insert operation takes it: its kind, its words and
    their emphasis, as the file writes them; its look is the document's own."""
    attrs = {name: block.attrs[name] for name in KEPT_ATTRS if block.attrs.get(name) is not None}
    attrs["id"] = id
    content = [_run(run) for run in block.runs if not isinstance(run, Run) or run.text]
    return {"type": block.type, "attrs": attrs, **({"content": content} if content else {})}


def _table(block: Block, at: dict, id: str) -> dict:
    rows = [[value or None for value in row] for row in _cells(block)]
    return {"op": "table", "at": at, "id": id, "rows": rows}


def _paired(old: list[Block], new: list[Block]) -> list[tuple[int | None, int | None]]:
    """The blocks of a changed stretch in order, each old one paired with the new one it
    became, where one is alike enough, so that the most of their text pairs."""
    n, m = len(old), len(new)
    if n * m > PAIRED:
        return [(i, None) for i in range(n)] + [(None, j) for j in range(m)]
    alike = [
        [
            SequenceMatcher(None, _said(a), _said(b), autojunk=False).ratio()
            if (a.type == "table") == (b.type == "table")
            else 0.0
            for b in new
        ]
        for a in old
    ]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            pair = alike[i][j] + best[i + 1][j + 1] if alike[i][j] >= ALIKE else -1.0
            best[i][j] = max(pair, best[i + 1][j], best[i][j + 1])
    walked: list[tuple[int | None, int | None]] = []
    i = j = 0
    while i < n and j < m:
        if alike[i][j] >= ALIKE and best[i][j] == alike[i][j] + best[i + 1][j + 1]:
            walked.append((i, j))
            i, j = i + 1, j + 1
        elif best[i][j] == best[i + 1][j]:
            walked.append((i, None))
            i += 1
        else:
            walked.append((None, j))
            j += 1
    walked += [(each, None) for each in range(i, n)] + [(None, each) for each in range(j, m)]
    return walked


class _Planned:
    """The operations planned so far, and the id of the block after which the next one put in
    goes, none before the first."""

    def __init__(self, first: str | None):
        self.operations: list[dict] = []
        self.first = first
        self.after: str | None = None

    def at(self) -> dict:
        if self.after is not None:
            return {"after": self.after}
        return {"before": self.first} if self.first else {"end": "body"}

    def put(self, written: list[Block]) -> None:
        """The blocks put in where the next goes, the texts between tables each as one
        proposal."""
        texts: list[dict] = []
        for block in [*written, None]:
            if block is not None and block.type != "table":
                texts.append(node_of(block, blocks.new_id()))
                continue
            if texts:
                self.operations.append({"op": "insert", "at": self.at(), "blocks": texts})
                self.after, texts = texts[-1]["attrs"]["id"], []
            if block is not None:
                self.operations.append(_table(block, self.at(), id := blocks.new_id()))
                self.after = id

    def change(self, old: Block, new: Block) -> None:
        """Makes the old block say what the new says: its words where both are texts and the
        new of one line, else it taken out and the new one put after it."""
        self.after = old.id
        if _said(old) == _said(new):
            return
        if old.type != "table" and new.type != "table" and "\n" not in new.text:
            self.operations.append({"op": "rewrite", "block": old.id, "text": new.text})
            return
        self.operations.append({"op": "delete", "from": old.id})
        self.put([new])


def operations(current: list[Block], other: list[Block]) -> list[dict]:
    """The operations that propose the tab's text as the other's, in the tab's order: a block
    with other words rewritten, one the other lacks taken out, and what only the other has put
    in where it stands there."""
    if proposed := [block.id for block in current if _proposed(block)]:
        raise Refused("proposed", ", ".join(proposed))
    old, new = _compared(current), _compared(other)
    planned = _Planned(old[0].id if old else None)
    matched = SequenceMatcher(
        None, [_said(b) for b in old], [_said(b) for b in new], autojunk=False
    )
    for op, i1, i2, j1, j2 in matched.get_opcodes():
        if op == "equal":
            planned.after = old[i2 - 1].id
            continue
        written: list[Block] = []
        for i, j in _paired(old[i1:i2], new[j1:j2]):
            if i is None:
                written.append(new[j1 + j])
                continue
            planned.put(written)
            written = []
            if j is None:
                planned.operations.append({"op": "delete", "from": old[i1 + i].id})
                planned.after = old[i1 + i].id
            else:
                planned.change(old[i1 + i], new[j1 + j])
        planned.put(written)
    return planned.operations


def _read(tab: Tab) -> list[Block]:
    return server.read_grids(tab.room, lambda doc, held: blocks.read(doc, held.grids()))


def _other(node: Node, tab: Tab) -> list[Block]:
    """What the tab is compared with: a Word file's text as the import reads it, or another
    document's tab of the same name, else its first."""
    if node.kind == Node.Kind.DOCUMENT:
        tabs = node.tabs_in_order()
        other = next((each for each in tabs if each.title == tab.title), tabs[0] if tabs else None)
        if other is None or other.pk == tab.pk:
            raise Refused("not_comparable", str(node.pk))
        return _read(other)
    if node.kind != Node.Kind.FILE or node.blob.media_type not in WORD:
        raise Refused("not_comparable", str(node.pk))
    try:
        imported = convert.read(node.blob, tab.document.locale)
    except Unreadable, TooLarge, convert.Unavailable:
        raise Refused("unreadable", str(node.pk)) from None
    return [block for each in imported.tabs for block in each.blocks]


def named(node: Node) -> str:
    """The name the file's differences are proposed under, as the user sees it in its folder."""
    if node.kind == Node.Kind.FILE and node.extension:
        return f"{node.title}.{node.extension}"
    return node.title


def author(parameters: dict) -> str:
    return named(Node.objects.get(pk=parameters["file"]))


def plan(tab: Tab, target: dict, parameters: dict, user) -> list[dict]:
    """Each difference of the file or the document the user reads from the tab, the operation
    that proposes it."""
    node, _ = live(user, parameters["file"])
    if not (planned := operations(_read(tab), _other(node, tab))):
        raise Refused("same_as_file", named(node))
    return planned
