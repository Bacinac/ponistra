"""Operations on a tab's content (D14), the one way actions, the model and the importer change
a document: blocks put at an address, a block's type and attributes set, a mark put on or
taken off a range of text, a range's text replaced or a block's written anew word by word or
whole, a table made, its cells written or lines
added, blocks moved or deleted, proposals accepted or rejected, a tab opened or copied. An operation
names blocks by their ids, a range by its block or note and the characters of its text, a cell
by its table's, row's and column's ids, never by an index another user's typing moves.

A run's operations are carried out on a copy of the tab's state and of its tables' grids; the
order of the text's blocks, every block they touched and every cell they wrote are then checked
against the schema, and only then does the change reach the tab's room: the grids' patches
first, then the text as one transaction whose origin is the run. A run that fails a check
changes nothing. What the run inserted and deleted is kept by its Yjs ids and its patches with
what they found, so it can be taken back later, leaving what others wrote since, while the room
keeps deleted content."""

import json
import re
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from functools import cache, lru_cache
from itertools import accumulate
from uuid import UUID

from django.db.models import Max
from jsonschema.exceptions import best_match
from prosemirror.model import Node as Checked
from pycrdt import (
    Doc,
    IdSet,
    Map,
    StackItem,
    UndoManager,
    XmlElement,
    XmlFragment,
    XmlText,
)

from apps.collab import server
from apps.documents.models import Node, Tab
from apps.engine.carried import carried, entered
from apps.engine.parse import Held, Ref, Unreadable, parse
from apps.engine.values import loaded

from . import (
    blocks,
    calculation,
    compute,
    data,
    designs,
    filtering,
    finding,
    fonts,
    grids,
    schema,
    sheets,
    styles,
)
from .blocks import (
    CELL,
    FIELD,
    NOTE,
    PROPOSED,
    TEXTBLOCKS,
    Block,
    Field,
    Note,
    Run,
    chunks_of,
    key_of,
    plain_of,
)
from .grids import FORMAT, FORMULA, LOOK, TO, Col, Laid, Row
from .models import DocumentBlob, Grid
from .series import series
from .sheets import Refused, Sheets
from .table import Draft

TABLE = "table"
NODES = schema.SPEC["nodes"]
MARKS = schema.SPEC["marks"]
FORMATTING = tuple(name for name in MARKS if name not in ("link", *PROPOSED, "formatting"))
REVIEWED = (*PROPOSED, "formatting")
PROPOSALS = (*REVIEWED, "proposedRows")
WORDS = re.compile(r"\w+|\s+|[^\w\s]")
TAG = re.compile(r"<br/>|<(/?)([1-9][0-9]*)(/?)>")
# A table's own fields its grid keeps, not its block.
GRID_ATTRS = ("name", "widths", "heights", "hidden", "frozen")


def _given(name: str) -> dict:
    return {key: spec["schema"] for key, spec in schema.attrs_of(MARKS[name]).items()}


def _attributed(name: str) -> dict:
    return {
        "if": {"properties": {"mark": {"const": name}}},
        "then": {
            "properties": {"attrs": {"properties": _given(name), "additionalProperties": False}}
        },
    }


def _one(key: str, value: dict) -> dict:
    return {
        "type": "object",
        "properties": {key: value},
        "required": [key],
        "additionalProperties": False,
    }


def _operation(name: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"op": {"const": name}, **properties},
        "required": ["op", *required],
        "additionalProperties": False,
    }


ID = {"$ref": "#/$defs/id"}
SLOT = {
    "type": "object",
    "properties": {"table": ID, "row": ID, "col": ID},
    "required": ["table", "row", "col"],
    "additionalProperties": False,
}
ADDRESS = {
    "description": "Before or after a block, or at the start or end of the text or of a cell.",
    "oneOf": [
        _one("before", ID),
        _one("after", ID),
        _one("start", {"oneOf": [{"const": "body"}, SLOT]}),
        _one("end", {"oneOf": [{"const": "body"}, SLOT]}),
    ],
}
IDS = {"type": "array", "minItems": 1, "uniqueItems": True, "items": ID}
OFFSET = {"type": "integer", "minimum": 0}
RANGE = {
    "description": "Characters of a block's or a note's text, from and to offsets in it, "
    "a note or a field in it taking none, or the words given, at their first occurrence or the "
    "one counted; without them, the whole text.",
    "type": "object",
    "properties": {
        "block": ID,
        "from": OFFSET,
        "to": OFFSET,
        "words": {"type": "string", "minLength": 1},
        "occurrence": {"type": "integer", "minimum": 1},
    },
    "required": ["block"],
    "dependentSchemas": {"words": {"properties": {"from": False, "to": False}}},
    "dependentRequired": {"occurrence": ["words"]},
    "additionalProperties": False,
}
MARK = {
    "type": "object",
    "properties": {"type": {"type": "string"}, "attrs": {"type": "object"}},
    "required": ["type"],
    "additionalProperties": False,
}
NODE = {
    "description": "A node as ProseMirror writes it in JSON.",
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "attrs": {"type": "object"},
        "content": {"type": "array", "items": {"type": "object"}},
        "text": {"type": "string"},
        "marks": {"type": "array", "items": MARK},
    },
    "required": ["type"],
    "additionalProperties": False,
}
TEXT = {
    "type": "object",
    "properties": {
        "type": {"const": "text"},
        "text": {"type": "string", "minLength": 1},
        "marks": {"type": "array", "items": MARK},
    },
    "required": ["type", "text"],
    "additionalProperties": False,
}
VALUE = {
    "description": "What one types into the cell, in the document's language; a number or a "
    "truth value as that language types it.",
    "type": ["null", "number", "boolean", "string"],
}
CONTENT = {
    "value": VALUE,
    "formula": {
        "description": "In the canonical form xlsx stores, its addresses in the cell's own "
        "table or after another table's name.",
        "type": "string",
        "minLength": 1,
    },
    "format": {
        "description": "A number format as Excel writes it; null takes it off.",
        "type": ["string", "null"],
        "minLength": 1,
        "maxLength": 255,
    },
    "blocks": {"type": "array", "minItems": 1, "items": NODE},
}
FILL = {
    "description": "The colour the cell is filled with; null takes it off.",
    "anyOf": [{"$ref": "#/$defs/color"}, {"type": "null"}],
}
SPAN = {
    "type": "object",
    "properties": {
        "rows": {"type": "integer", "minimum": 1},
        "cols": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": False,
}
BY = {
    "description": "How far a copied formula moved, its relative references with it.",
    "type": "object",
    "properties": {"rows": {"type": "integer"}, "cols": {"type": "integer"}},
    "additionalProperties": False,
}
LENGTHS = {"type": "array", "items": {"type": ["number", "null"], "exclusiveMinimum": 0}}
SIZES = {
    "description": "By line id; null takes the size off.",
    "type": "object",
    "additionalProperties": {"type": ["number", "null"], "exclusiveMinimum": 0},
}
HIDDEN = {
    "description": "By line id, true to hide the line, false to show it again.",
    "type": "object",
    "additionalProperties": {"type": "boolean"},
}

OPERATIONS = {
    "insert": _operation(
        "insert",
        {"at": ADDRESS, "blocks": {"type": "array", "minItems": 1, "items": NODE}},
        ["at", "blocks"],
    ),
    "table": _operation(
        "table",
        {
            "at": ADDRESS,
            "id": ID,
            "name": {"$ref": "#/$defs/tableName"},
            "design": {
                "description": "One of our designs by its id, or plain for a table without lines.",
                "enum": [*designs.CATALOGUE, "plain"],
            },
            "designs": {
                **NODES[TABLE]["attrs"]["designs"]["schema"],
                "description": "The designs a copied table carries, in place of a design.",
            },
            "sized": {"type": "boolean"},
            "widths": LENGTHS,
            "heights": LENGTHS,
            "rowIds": IDS,
            "colIds": IDS,
            "rows": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "anyOf": [
                            VALUE,
                            {
                                "type": "object",
                                "properties": {**CONTENT, "span": SPAN, "by": BY},
                                "additionalProperties": False,
                            },
                        ]
                    },
                },
            },
        },
        ["at", "rows"],
    ),
    "set": _operation(
        "set",
        {
            "block": ID,
            "type": {"enum": list(TEXTBLOCKS)},
            "attrs": {"type": "object", "propertyNames": {"not": {"enum": list(PROPOSALS)}}},
        },
        ["block"],
    ),
    "mark": {
        **_operation(
            "mark",
            {
                "range": RANGE,
                "mark": {"enum": [name for name in MARKS if name not in REVIEWED]},
                "attrs": {
                    # A tool's schema takes no conditions at its top, so the model reads there
                    # what the conditions below check.
                    "description": "The mark's attributes, by mark; the others take none: "
                    + json.dumps(
                        {
                            name: given
                            for name in MARKS
                            if name not in REVIEWED and (given := _given(name))
                        },
                        separators=(",", ":"),
                    ),
                    "type": "object",
                },
                "remove": {"type": "boolean"},
            },
            ["range", "mark"],
        ),
        "allOf": [_attributed(name) for name in MARKS if name not in REVIEWED],
    },
    "text": _operation(
        "text", {"range": RANGE, "content": {"type": "array", "items": TEXT}}, ["range", "content"]
    ),
    "rewrite": _operation(
        "rewrite",
        {"block": ID, "text": {"type": "string", "minLength": 1, "pattern": "^[^\\n]*$"}},
        ["block", "text"],
    ),
    "replace": _operation(
        "replace",
        {"block": ID, "text": {"type": "string", "minLength": 1, "pattern": "^[^\\n]*$"}},
        ["block", "text"],
    ),
    "substitute": _operation(
        "substitute",
        {
            "find": {"type": "string", "minLength": 1},
            "by": {"type": "string", "pattern": "^[^\\n]*$"},
            "case": {"description": "Whether the case of the letters counts.", "type": "boolean"},
            "words": {
                "description": "Whether it is found only as a whole word.",
                "type": "boolean",
            },
            "block": {"description": "The block or footnote it is replaced in, with from.", **ID},
            "from": {
                "description": "Where in its text it starts.",
                "type": "integer",
                "minimum": 0,
            },
            "table": {"description": "The table of the one cell it is replaced in.", **ID},
            "row": ID,
            "col": ID,
        },
        ["find", "by"],
    ),
    "cells": _operation(
        "cells",
        {
            "table": ID,
            "cells": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "row": ID,
                        "col": ID,
                        **CONTENT,
                        "fill": FILL,
                        "span": SPAN,
                        "by": BY,
                    },
                    "required": ["row", "col"],
                    "additionalProperties": False,
                },
            },
        },
        ["table", "cells"],
    ),
    "lines": _operation(
        "lines",
        {
            "table": ID,
            "axis": {"enum": ["rows", "cols"]},
            "ids": {"description": "The new lines' ids, put in.", **IDS},
            "before": ID,
            "remove": {
                "description": "Takes out the lines from one to the other, with from and to.",
                "type": "boolean",
            },
            "hidden": {
                "description": "Hides the lines from one to the other, or with false shows them "
                "again; from or to left out reaches the table's first or last line.",
                "type": "boolean",
            },
            "from": ID,
            "to": ID,
        },
        ["table", "axis"],
    ),
    "fill": _operation(
        "fill",
        {
            "table": ID,
            "from": {"$ref": "#/$defs/point"},
            "to": {"$ref": "#/$defs/point"},
            "until": {
                "description": "The slot the range fills to, below, above, right or left of it.",
                "$ref": "#/$defs/point",
            },
            "copies": {
                "description": "Copies the cells as they are, as a fill down does, rather than "
                "going on with their series.",
                "type": "boolean",
            },
        },
        ["table", "from", "to", "until"],
    ),
    "order": _operation(
        "order",
        {
            "table": ID,
            "col": ID,
            "descending": {"type": "boolean"},
            "from": {
                "description": "The first or last row sorted, with to the other; without them "
                "every row below the header but the totals.",
                **ID,
            },
            "to": ID,
        },
        ["table", "col"],
    ),
    "grid": _operation(
        "grid",
        {
            "table": ID,
            "name": {"anyOf": [{"$ref": "#/$defs/tableName"}, {"const": ""}]},
            "widths": SIZES,
            "heights": SIZES,
            "hidden": {
                "type": "object",
                "properties": {"cols": HIDDEN},
                "additionalProperties": False,
            },
            "frozen": {
                "description": "The last row that stays at the top of the view; null frees them.",
                "anyOf": [ID, {"type": "null"}],
            },
        },
        ["table"],
    ),
    "looks": _operation(
        "looks",
        {
            "table": ID,
            "axis": {"enum": ["rows", "cols"]},
            "from": {"description": "The first or last line formatted, with to the other.", **ID},
            "to": ID,
            "marks": {
                "description": "Marks given with their attributes, or taken off with null.",
                "type": "object",
                "propertyNames": {"enum": sorted(MARKS.keys() - set(blocks.UNLOOKED_MARKS))},
                "additionalProperties": {"type": ["object", "null"]},
            },
            "attrs": {
                "description": "The paragraph's attributes set, or taken off with null.",
                "type": "object",
                "propertyNames": {"enum": list(blocks.LOOK_ATTRS)},
            },
            "fill": FILL,
        },
        ["table", "axis", "from", "to"],
    ),
    "copy": _operation(
        "copy",
        {
            "table": ID,
            "id": ID,
            "name": {"anyOf": [{"$ref": "#/$defs/tableName"}, {"const": ""}]},
            "values": {"type": "boolean"},
        },
        ["table"],
    ),
    "move": _operation("move", {"from": ID, "to": ID, "at": ADDRESS}, ["from", "at"]),
    "delete": _operation("delete", {"from": ID, "to": ID}, ["from"]),
    "accept": _operation("accept", {"ids": IDS}, []),
    "reject": _operation("reject", {"ids": IDS}, []),
}
# On a document's own state, beside its tabs': a style's font or size set.
OWN_OPERATIONS = {
    "style": _operation(
        "style",
        {
            "style": schema.SPEC["attrSets"]["textblock"]["style"]["schema"],
            "font": {"type": "string", "minLength": 1},
            "size": {"type": "number", "minimum": 1, "maximum": 400},
        },
        ["style"],
    ),
}


@cache
def _checking(kind: str):
    return schema.validator({**OPERATIONS, **OWN_OPERATIONS}[kind])


def _kind(operation, known: dict = OPERATIONS) -> str:
    kind = operation.get("op") if isinstance(operation, dict) else None
    if kind not in known:
        raise Refused("unknown_operation", str(kind))
    if (error := best_match(_checking(kind).iter_errors(operation))) is not None:
        raise Refused("invalid", error.message)
    return kind


@cache
def _shape():
    return schema.validator(NODE)


def _proposed(attrs: dict) -> dict[str, dict]:
    return {name: attrs[name] for name in PROPOSED if attrs.get(name)}


def _inline(json: dict) -> Run | Note | Field:
    attrs = json.get("attrs") or {}
    match json["type"]:
        case "text":
            if not json.get("text"):
                raise Refused("schema", "a text node without text")
            return Run(
                json["text"],
                {mark["type"]: mark.get("attrs") or {} for mark in json.get("marks", [])},
            )
        case "footnote":
            runs = [_inline(_checked(each)) for each in json.get("content", [])]
            if not all(isinstance(run, Run) for run in runs):
                raise Refused("schema", "a note holds text only")
            id = attrs.get("id") or blocks.new_id()
            return Note(attrs.get("kind", "foot"), id, runs, _proposed(attrs))
        case "field":
            return Field(attrs.get("kind", "page"), _proposed(attrs))
        case other:
            raise Refused("schema", f"{other} is no inline node")


def _brought(block: Block, change: dict) -> None:
    """Proposes the block inserted whole: its text, notes and fields, and its end or itself."""
    for run in block.runs:
        if isinstance(run, Run):
            run.marks["insertion"] = change
        else:
            run.proposed["insertion"] = change
    block.attrs["insertion"] = change


def _anew(content: list[Block]) -> list[Block]:
    """The blocks under ids of their own, and their notes, to stand beside those they copy."""
    return [
        replace(
            block,
            id=blocks.new_id(),
            runs=[
                replace(run, id=blocks.new_id()) if isinstance(run, Note) else run
                for run in block.runs
            ],
        )
        for block in content
    ]


def _checked(json) -> dict:
    if (error := best_match(_shape().iter_errors(json))) is not None:
        raise Refused("invalid", error.message)
    return json


def block_of(json) -> Block:
    """A block as ProseMirror writes it in JSON, given an id where it has none; a table's
    cells come with the table operation, not as nodes."""
    _checked(json)
    if json["type"] == TABLE:
        raise Refused("table_as_block")
    attrs = {name: value for name, value in (json.get("attrs") or {}).items() if value is not None}
    id = attrs.pop("id", None) or blocks.new_id()
    return Block(
        json["type"], id, attrs, [_inline(_checked(each)) for each in json.get("content", [])]
    )


@dataclass
class Found:
    """An element with an id where it stands: its parent, its index there, the block in the
    text it is or is in and, in a table, its cell as "row:col"; a note is no block."""

    element: XmlElement
    parent: XmlFragment | XmlElement
    at: int
    top: str
    cell: str | None = None
    note: bool = False


@dataclass
class Spot:
    """Where blocks go: their parent, their index there and, in a cell, its table and cell."""

    parent: XmlFragment | XmlElement
    at: int
    table: str | None = None
    cell: str | None = None


KEEP = object()


@dataclass
class Content:
    """What an operation writes into a cell: a value, a formula or blocks, or none of them,
    and a number format, or none, unless the cell's is kept; the look of a value or a
    formula, unless the cell's is kept; and its fill and its edges, or none, unless the
    cell's are kept."""

    given: bool = False
    value: object = None
    formula: str | None = None
    blocks: list[Block] | None = None
    format: object = KEEP
    moved: tuple[int, int] = (0, 0)
    look: object = KEEP
    fill: object = KEEP
    edges: object = KEEP


def _content(given) -> tuple[Content, dict | None]:
    if not isinstance(given, dict):
        given = {"value": given}
    written = [name for name in ("value", "formula", "blocks") if name in given]
    if len(written) > 1:
        raise Refused("contents", " and ".join(written))
    value = given.get("value")
    if isinstance(value, str) and value.startswith("="):
        raise Refused("formula_as_value", value)
    if "by" in given and "formula" not in given:
        raise Refused("invalid", "only a formula moves")
    by = given.get("by", {})
    content = Content(
        bool(written),
        value,
        given.get("formula"),
        [block_of(each) for each in given["blocks"]] if "blocks" in given else None,
        given.get("format", KEEP),
        (by.get("rows", 0), by.get("cols", 0)),
        fill=given.get("fill", KEEP),
    )
    return content, given.get("span")


def _number(value):
    # Yjs has one number type, so a heading level of 2 comes back as 2.0.
    return int(value) if isinstance(value, float) and value.is_integer() else value


def copy_text(source: XmlText, target: XmlText) -> None:
    """The source's text, with its formatting, after the target's."""
    parts = source.diff()
    at = len(plain_of(target).encode())
    target.insert(at, "".join(part for part, _ in parts))
    for part, attributes in parts:
        size = len(part.encode())
        if attributes:
            target.format(at, at + size, attributes)
        at += size


def _occurrence(text: str, words: str, counted: int) -> int | None:
    at = -1
    for _ in range(counted):
        at = text.find(words, at + 1)
        if at < 0:
            return None
    return at


def _spans(chunks: list[tuple[XmlText, int, str]], start: int, end: int) -> Iterator[tuple]:
    """Each text's share of the range, in the UTF-8 bytes pycrdt counts."""
    for text, at, plain in chunks:
        first, last = max(start, at), min(end, at + len(plain))
        if first < last:
            yield text, len(plain[: first - at].encode()), len(plain[: last - at].encode())


def _differing(old: str, new: str) -> list[tuple[int, int, str]]:
    """Where the new text differs from the old, word by word: the characters of the old each
    change replaces and what it writes there, changes apart only by spaces taken as one."""
    before, after = WORDS.findall(old), WORDS.findall(new)
    changes: list[list[int]] = []
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    for tag, first, last, start, end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if changes and all(word.isspace() for word in before[changes[-1][1] : first]):
            changes[-1][1], changes[-1][3] = last, end
        else:
            changes.append([first, last, start, end])
    at = [0, *accumulate(len(word) for word in before)]
    return [(at[first], at[last], "".join(after[start:end])) for first, last, start, end in changes]


def _formatting_at(chunks: list[tuple[XmlText, int, str]], offset: int) -> dict:
    """The formatting of the character at the offset, but for its review."""
    for text, at, plain in chunks:
        if at <= offset < at + len(plain):
            seen = at
            for part, attributes in text.diff():
                if seen <= offset < seen + len(part):
                    return {
                        key: value
                        for key, value in (attributes or {}).items()
                        if key not in REVIEWED
                    }
                seen += len(part)
    return {}


def _proposed_in(found: Found, chunks: list[tuple[XmlText, int, str]]) -> bool:
    return any(found.element.attributes.get(key) is not None for key in REVIEWED) or any(
        set(attributes or {}) & set(REVIEWED)
        for text, _, _ in chunks
        for _, attributes in text.diff()
    )


def _gaps(
    element: XmlElement,
) -> tuple[list[tuple[int, list[XmlText]]], dict[int, dict], list[int]]:
    """The block's or note's texts between its notes and fields, each stretch after the index
    of the child it starts at; and numbered in order as `blocks.tagged` numbers them, the
    formatting of each formatted part and the numbers of the notes and fields."""
    gaps: list[tuple[int, list[XmlText]]] = [(0, [])]
    formats: dict[int, dict] = {}
    inline: list[int] = []
    for index, child in enumerate(element.children):
        if isinstance(child, XmlText):
            gaps[-1][1].append(child)
            for _, attributes in child.diff():
                if attributes:
                    formats[len(formats) + len(inline) + 1] = attributes
        elif isinstance(child, XmlElement) and child.tag in (NOTE, FIELD):
            inline.append(len(formats) + len(inline) + 1)
            gaps.append((index + 1, []))
    return gaps, formats, inline


def _spanned(
    text: str, formats: dict[int, dict], inline: list[int]
) -> list[list[tuple[str, dict]]]:
    """The text as its tags place it between the block's notes and fields: each piece with the
    formatting of the part its tag numbers, or with none."""
    gaps: list[list[tuple[str, dict]]] = [[]]
    open_: int | None = None
    at = 0

    def piece(written: str) -> None:
        if written:
            gaps[-1].append((written, formats[open_] if open_ is not None else {}))

    for found in TAG.finditer(text):
        piece(text[at : found.start()])
        at = found.end()
        if found.group(0) == "<br/>":
            piece("\n")
            continue
        closing, number, alone = found.group(1), int(found.group(2)), found.group(3)
        if closing and alone:
            raise Refused("tags", found.group(0))
        if alone:
            if len(gaps) > len(inline) or number != inline[len(gaps) - 1]:
                raise Refused("tags", f"<{number}/> out of place")
            gaps.append([])
        elif closing:
            if number != open_:
                raise Refused("tags", f"</{number}> closes no <{number}>")
            open_ = None
        elif open_ is not None:
            raise Refused("tags", f"<{number}> inside <{open_}>")
        elif number not in formats:
            raise Refused("tags", f"<{number}> tags no formatted part")
        else:
            open_ = number
    piece(text[at:])
    if open_ is not None:
        raise Refused("tags", f"<{open_}> left open")
    if len(gaps) != len(inline) + 1:
        tags = ", ".join(f"<{number}/>" for number in inline)
        raise Refused("tags", f"{tags} each once, in order")
    return gaps


def _keys(text: XmlText, start: int, end: int) -> set[str]:
    """The formatting a text's bytes between start and end have."""
    keys, at = set(), 0
    for part, attributes in text.diff():
        size = len(part.encode())
        if at < end and at + size > start:
            keys |= set(attributes or {})
        at += size
    return keys


def _excludes(name: str, other: str) -> bool:
    marks = schema.prosemirror().marks
    return other != name and other in marks and marks[name].excludes(marks[other])


def _ids(element: XmlElement) -> Iterator[str]:
    for child in element.children:
        if isinstance(child, XmlElement):
            if isinstance(id := child.attributes.get("id"), str):
                yield id
            yield from _ids(child)


@dataclass
class Review:
    """The proposals a run accepts or rejects, all of them where it names none, and those it
    met."""

    ids: list[str] | None
    accepted: bool
    met: set[str] = field(default_factory=set)

    def chosen(self, change) -> bool:
        if not isinstance(change, dict) or (self.ids is not None and change["id"] not in self.ids):
            return False
        self.met.add(change["id"])
        return True

    def settle(self, held) -> tuple[list[str], bool]:
        """Which of the insertion and the deletion held are chosen, and whether what holds
        them goes: an insertion rejected or a deletion accepted."""
        names = [name for name in PROPOSED if self.chosen(held.get(name))]
        return names, ("deletion" if self.accepted else "insertion") in names

    def missing(self) -> str | None:
        if self.ids is None:
            return None if self.met else ""
        return next((id for id in self.ids if id not in self.met), None)


def _review_text(text: XmlText, review: Review) -> bool:
    edits, at = [], 0
    for part, attributes in text.diff():
        size, attributes = len(part.encode()), attributes or {}
        restyled = review.chosen(attributes.get("formatting"))
        settled, goes = review.settle(attributes)
        if goes:
            edits.append((at, size, None))
        elif settled or restyled:
            off: dict = {name: None for name in settled}
            if restyled:
                off["formatting"] = None
                if not review.accepted:
                    off |= {key: None for key in attributes if blocks.mark_name(key) in FORMATTING}
                    off |= attributes["formatting"]["before"]
            edits.append((at, size, off))
        at += size
    for at, size, off in reversed(edits):
        if off is None:
            del text[at : at + size]
        else:
            text.format(at, at + size, off)
    return bool(edits)


def _inherit(laid: Laid | Draft, rows: list[str]) -> None:
    """A row put into a calculated column takes its formula and number format: what the rows
    above and below it hold alike, or the two on the one side where it stands at an end."""
    new = set(rows)
    places = laid.places(rows)
    if not places:
        return
    near = laid.ids(min(places.values()) - 2, max(places.values()) + 2)
    kept = [row for row in near if row not in new]
    for row in rows:
        at = sum(1 for each in near[: near.index(row)] if each not in new)
        above = kept[max(at - 2, 0) : at][::-1]
        below = kept[at : at + 2]
        pairs = [(above[0], below[0])] if above and below else []
        pairs += [(above[0], above[1])] if len(above) > 1 else []
        pairs += [(below[0], below[1])] if len(below) > 1 else []
        for col in laid.col_ids():
            for one, two in pairs:
                first, second = laid.cell(one, col), laid.cell(two, col)
                held = first.get(FORMULA)
                if held is not None and held == second.get(FORMULA):
                    sheets.write(laid, row, col, {FORMULA: held, FORMAT: first.get(FORMAT)})
                    break


def _written(patch: dict) -> Iterator[tuple[str, dict]]:
    """Every cell a patch writes, by "row:col", with what it holds after; one in a row and a
    column both put, which each carry it, once."""
    for row, cols in patch.get("cells", {}).items():
        for col, (_, after) in cols.items():
            if after:
                yield key_of(row, col), after
    rows = patch.get("rows", {}).get("put", [])
    for id, *_, line in rows:
        for col, cell in line.get("cells", {}).items():
            yield key_of(id, col), cell
    put = {id for id, *_ in rows}
    for id, *_, line in patch.get("cols", {}).get("put", []):
        for row, cell in line.get("cells", {}).items():
            if row not in put:
                yield key_of(row, id), cell


def _line_looks(patch: dict) -> Iterator[tuple[str, dict]]:
    """Every look a patch gives a row or a column, by the line's id."""
    for lines in patch.get("looks", {}).values():
        for id, (_, after) in lines.items():
            if after is not None:
                yield id, after
    for axis in ("rows", "cols"):
        for id, *_, line in patch.get(axis, {}).get("put", []):
            if line.get("look") is not None:
                yield id, line["look"]


def _line_look(looks: Mapping[str, dict], id: str) -> grids.Look | None:
    return grids.look(looks[id]) if looks.get(id) else None


def _changed(
    look: Mapping,
    marks: Mapping[str, dict | None],
    attrs: Mapping[str, object],
    fill: object = KEEP,
) -> dict:
    """The look with the marks given, or taken off, those a mark given excludes taken off with
    them, its paragraph's attributes set, or taken off given as None, and its fill set or
    taken off, unless it is kept."""
    given = [name for name, value in marks.items() if value is not None]
    kept = {
        name: value
        for name, value in (look.get("marks") or {}).items()
        if name not in marks and not any(_excludes(each, name) for each in given)
    }
    kept |= {name: marks[name] for name in given}
    paragraph = {
        name: value
        for name, value in {**(look.get("attrs") or {}), **attrs}.items()
        if value is not None
    }
    filled = look.get("fill") if fill is KEEP else fill
    return {
        **({"marks": kept} if kept else {}),
        **({"attrs": paragraph} if paragraph else {}),
        **({"fill": filled} if filled else {}),
        **({"edges": look["edges"]} if look.get("edges") else {}),
    }


def _filled_with(element: XmlElement, fill: str | None, edges: object = KEEP) -> None:
    for name, value in (("fill", fill), ("edges", edges)):
        if value is KEEP:
            continue
        if value:
            element.attributes[name] = value
        elif element.attributes.get(name) is not None:
            del element.attributes[name]


def _laid_into(laid: Laid, key: str, given: dict) -> None:
    """Writes into a grid being laid out the cell's parts, where its row and column are."""
    row, _, col = key.partition(":")
    if laid.row(row) is not None and laid.col(col) is not None:
        sheets.write(laid, row, col, given)


def _remove_cell(table: XmlElement, row: str, col: str) -> None:
    for at in reversed(range(len(table.children))):
        child = table.children[at]
        if (
            isinstance(child, XmlElement)
            and child.tag == CELL
            and (child.attributes.get("row"), child.attributes.get("col")) == (row, col)
        ):
            del table.children[at : at + 1]


def _filled(element: XmlElement) -> bool:
    return any(isinstance(child, XmlElement) or plain_of(child) for child in element.children)


@dataclass(frozen=True)
class Proposer:
    """Whose proposals a run's text goes in as: the name they carry, the account and when, to
    the second as Word dates a change."""

    author: str
    user: int
    date: str

    def change(self) -> dict:
        return {"id": blocks.new_id(), "author": self.author, "user": self.user, "date": self.date}


class Editing:
    """A run's operations carried out on a copy of a tab's state, and what they touched: of
    each block in the text, the whole of it or, of a table, the cells, none for its own
    attributes. Under a proposer, each operation that writes or takes out text, blocks or a
    table does it as one proposal."""

    def __init__(
        self,
        doc: Doc,
        sheets: Sheets,
        locale: str | None,
        body: XmlFragment | None = None,
        propose: Proposer | None = None,
        seen: Mapping[str, filtering.View] | None = None,
    ):
        self.doc = doc
        self.sheets = sheets
        self.locale = locale
        self.seen = seen or {}
        self.body = blocks.body_of(doc) if body is None else body
        self.written = blocks.Written(doc.client_id)
        self.made: set[str] = set()
        self.touched: dict[str, set[str] | None] = {}
        self.found: dict[str, Found] = {}
        self.plains: dict[str, str] = {}
        self.edits: dict[str, list[tuple[int, int, int]]] = {}
        self.propose = propose
        self.change: dict | None = None

    def carry(self, operation) -> dict:
        kind = _kind(operation)
        self.found = self._index()
        self.made = set()
        self.change = self.propose and self.propose.change()
        return getattr(self, f"_{kind}")(operation)

    def _own(self, change) -> bool:
        """Whether the proposal is one the proposer made."""
        return isinstance(change, dict) and change.get("user") == self.propose.user

    def _index(self) -> dict[str, Found]:
        found: dict[str, Found] = {}

        def walk(parent: XmlFragment | XmlElement, top: str | None, cell: str | None) -> None:
            for at, child in enumerate(parent.children):
                if not isinstance(child, XmlElement):
                    continue
                if child.tag == CELL:
                    walk(
                        child, top, key_of(child.attributes.get("row"), child.attributes.get("col"))
                    )
                    continue
                id = child.attributes.get("id")
                if not isinstance(id, str):
                    continue
                found.setdefault(id, Found(child, parent, at, top or id, cell))
                if child.tag == TABLE and top is None:
                    walk(child, id, None)
                if child.tag not in TEXTBLOCKS:
                    continue
                for index, inner in enumerate(child.children):
                    if isinstance(inner, XmlElement) and inner.tag == NOTE:
                        note = inner.attributes.get("id")
                        if isinstance(note, str):
                            found.setdefault(
                                note, Found(inner, child, index, top or id, cell, True)
                            )

        walk(self.body, None, None)
        return found

    def _touch(self, top: str, cell: str | None = None) -> None:
        if cell is None:
            self.touched[top] = None
        elif (cells := self.touched.setdefault(top, set())) is not None:
            cells.add(cell)

    def _block(self, id: str) -> Found:
        found = self.found.get(id)
        if found is None or found.note:
            raise Refused("no_block", id)
        return found

    def _shown(self, table: str, laid: Laid | Draft, ids: list[str]) -> list[str]:
        """Those of the rows given that the user's filter of the table shows them, the rows the
        edit puts in among them; every row given where the user has no filter of it, as an
        edit over hidden rows reaches them."""
        view = self.seen.get(table)
        cols = set(laid.col_ids())
        if view is None or not isinstance(laid, Draft):
            return ids
        view = replace(view, conditions=tuple(c for c in view.conditions if c["col"] in cols))
        if not view.conditions:
            return ids
        passing = view.passing(laid.base.grid, ids) | laid.made.keys()
        return [id for id in ids if id in passing]

    def _placed(self, id: str) -> tuple[Found, Laid]:
        found = self.found.get(id)
        if found is None or found.element.tag != TABLE or found.top != id or id not in self.sheets:
            raise Refused("no_table", id)
        return found, self.sheets.get(id)

    def _elements_of(self, table: XmlElement) -> dict[str, XmlElement]:
        return {
            key_of(child.attributes.get("row"), child.attributes.get("col")): child
            for child in table.children
            if isinstance(child, XmlElement) and child.tag == CELL
        }

    def _cell(self, table: str, row: str, col: str) -> tuple[XmlElement, str]:
        """The cell's element, made for a cell that has none, with its text in its look if it
        had one."""
        found, laid = self._placed(table)
        key = key_of(row, col)
        if laid.row(row) is None or col not in laid.col_ids():
            raise Refused("no_cell", key)
        if key in sheets.covered(laid):
            raise Refused("covered", key)
        if (element := self._elements_of(found.element).get(key)) is not None:
            return element, key
        look = laid.look_at(row, col)
        own = {name: look[name] for name in ("fill", "edges") if look and look.get(name)}
        element = found.element.children.append(XmlElement(CELL, {"row": row, "col": col, **own}))
        if text := laid.cell(row, col).get(grids.TEXT, ""):
            paragraph = blocks.light_cell(key, text, look).blocks[0]
            paragraph.id = blocks.new_id()
            blocks.write_block(element, paragraph, self.doc, self.written)
        sheets.write(laid, row, col, {grids.TEXT: None, LOOK: None})
        return element, key

    def _spot(self, address: dict) -> Spot:
        ((where, value),) = address.items()
        if where in ("before", "after"):
            found = self._block(value)
            table = found.top if found.cell is not None else None
            return Spot(found.parent, found.at + (where == "after"), table, found.cell)
        if value == "body":
            return Spot(self.body, 0 if where == "start" else len(self.body.children))
        element, key = self._cell(value["table"], value["row"], value["col"])
        return Spot(element, 0 if where == "start" else len(element.children), value["table"], key)

    def _arrived(self, spot: Spot, id: str) -> None:
        if spot.cell is not None:
            self._touch(spot.table, spot.cell)
        else:
            self._touch(id)

    def _take(self, block: Block, freed: set[str] = frozenset()) -> None:
        for id in (block.id, *(note.id for note in block.notes)):
            if id in self.made or (id not in freed and (id in self.found or id in self.sheets)):
                raise Refused("taken", id)
            self.made.add(id)

    def _put(self, spot: Spot, content: list[Block]) -> None:
        for offset, block in enumerate(content):
            self._take(block)
            if block.type != TABLE:
                blocks.write_block(spot.parent, block, self.doc, self.written, spot.at + offset)
                self._arrived(spot, block.id)
                continue
            attrs = {name: value for name, value in block.attrs.items() if name not in GRID_ATTRS}
            element = blocks.write_block(
                spot.parent, replace(block, attrs=attrs), self.doc, self.written, spot.at + offset
            )
            grid = block.grid or blocks.Grid([], [])
            widths = block.attrs.get("widths") or {}
            heights = block.attrs.get("heights") or {}
            hidden = block.attrs.get("hidden") or {}
            rows, cols = set(hidden.get(grids.ROWS, ())), set(hidden.get(grids.COLS, ()))
            laid = Laid(
                block.id,
                self.sheets.tab,
                block.attrs.get("name") or "",
                [
                    Col(id, widths.get(id), _line_look(grid.col_looks, id), id in cols)
                    for id in dict.fromkeys(grid.cols)
                ],
                [
                    Row(id, heights.get(id), look=_line_look(grid.row_looks, id), hidden=id in rows)
                    for id in dict.fromkeys(grid.rows)
                ],
                block.attrs.get("frozen") if block.attrs.get("frozen") in grid.rows else None,
            )
            for key, pieces in grid.formulas.items():
                _laid_into(laid, key, {FORMULA: pieces})
            for key, code in grid.formats.items():
                _laid_into(laid, key, {FORMAT: code})
            for key, text in grid.texts.items():
                _laid_into(laid, key, {grids.TEXT: text})
            for cell in block.cells:
                key = key_of(cell.row, cell.col)
                light = blocks.look_of(cell.blocks, cell.fill, cell.edges)
                if cell.to is not None:
                    _laid_into(laid, key, {TO: cell.to})
                if light is not None:
                    _laid_into(laid, key, {grids.TEXT: light[0], LOOK: light[1]})
                    continue
                self._node(element, cell)
            self.sheets.make(laid)
            self._arrived(spot, block.id)

    def _node(self, element: XmlElement, cell: blocks.Cell) -> None:
        """The cell's node of its own in the text of its table."""
        own = {name: value for name, value in (("fill", cell.fill), ("edges", cell.edges)) if value}
        inner = element.children.append(XmlElement(CELL, {"row": cell.row, "col": cell.col, **own}))
        for each in cell.blocks:
            self._take(each)
            blocks.write_block(inner, each, self.doc, self.written)

    def _insert(self, operation: dict) -> dict:
        made = [block_of(each) for each in operation["blocks"]]
        if self.change is not None:
            for block in made:
                _brought(block, self.change)
        self._put(self._spot(operation["at"]), made)
        return {"blocks": [block.id for block in made]}

    def _pieces(self, text: str, own: str, moved: tuple[int, int]) -> list:
        """A formula as a table keeps it: each reference by the ids of its rows and columns."""
        defined = {each["name"].casefold() for each in self.sheets.names().values()}
        return sheets.pieces_of(self.sheets, text, own, defined, moved)

    @staticmethod
    def _look(cell: XmlElement) -> dict:
        """The look of a cell's text: its first paragraph's and the marks its text starts with,
        or its end's where it has no text, as the editor writes a value into a cell."""
        first = cell.children[0] if len(cell.children) else None
        attrs = (
            {name: value for name, value in first.attributes if name in blocks.LOOK_ATTRS}
            if isinstance(first, XmlElement) and first.tag == "paragraph"
            else {}
        )
        starting = (
            attributes or {}
            for block in cell.children
            if isinstance(block, XmlElement)
            for child in block.children
            if isinstance(child, XmlText)
            for _, attributes in child.diff()
        )
        found = next(starting, None)
        ending = first.attributes.get("endMarks") if isinstance(first, XmlElement) else None
        marks = (
            {blocks.mark_name(key): value for key, value in found.items()}
            if found is not None
            else dict(ending or {})
        )
        marks = {name: value for name, value in marks.items() if name not in blocks.UNLOOKED_MARKS}
        fill, edges = cell.attributes.get("fill"), cell.attributes.get("edges")
        return {
            **({"marks": marks} if marks else {}),
            **({"attrs": attrs} if attrs else {}),
            **({"fill": fill} if fill else {}),
            **({"edges": edges} if edges else {}),
        }

    def _write(
        self,
        table: XmlElement,
        laid: Laid,
        key: str,
        content: Content,
        text: str,
        pieces: list | None,
        elements: dict[str, XmlElement],
        to: str | None = None,
    ) -> None:
        row, _, col = key.partition(":")
        given: dict = {} if to is None else {TO: to}
        if content.format is not KEEP:
            given[FORMAT] = content.format
        element = elements.get(key)
        shown = (
            element.attributes.get("fill")
            if element is not None
            else (laid.look_at(row, col) or {}).get("fill")
        )
        fill = shown if content.fill is KEEP else content.fill
        edges = (
            (
                element.attributes.get("edges")
                if element is not None
                else (laid.look_at(row, col) or {}).get("edges")
            )
            if content.edges is KEEP
            else content.edges
        )
        if not content.given:
            if fill != shown and element is not None:
                _filled_with(element, fill)
            elif fill != shown:
                given[LOOK] = _changed(laid.look_at(row, col) or {}, {}, {}, fill)
            sheets.write(laid, row, col, given)
            return
        given[FORMULA] = pieces
        light = None
        if content.blocks is None:
            if content.look is not KEEP:
                look = content.look
            elif element is not None:
                look = self._look(element)
            else:
                look = laid.look_at(row, col)
            if content.fill is not KEEP and (look or {}).get("fill") != content.fill:
                look = _changed(look or {}, {}, {}, content.fill)
            light = (text, look)
        elif (light := blocks.look_of(content.blocks, fill, edges)) is not None:
            for block in content.blocks:
                self._take(block, set(_ids(element)) if element is not None else frozenset())
        if light is not None:
            if element is not None:
                _remove_cell(table, row, col)
                del elements[key]
            sheets.write(laid, row, col, given | {grids.TEXT: light[0], LOOK: light[1]})
            return
        sheets.write(laid, row, col, given | {grids.TEXT: None, LOOK: None})
        if element is None:
            element = elements[key] = table.children.append(
                XmlElement(CELL, {"row": row, "col": col, **({"edges": edges} if edges else {})})
            )
        _filled_with(element, fill, edges)
        freed = set(_ids(element))
        if len(element.children):
            del element.children[0 : len(element.children)]
        for block in content.blocks:
            self._take(block, freed)
            blocks.write_block(element, block, self.doc, self.written)

    def _write_cells(
        self,
        table: XmlElement,
        id: str,
        cells: dict[str, tuple[Content, str | None]],
        elements: dict[str, XmlElement],
    ) -> None:
        laid = self.sheets.get(id)
        language = calculation.language(self.locale)
        typed = {
            key: calculation.written(content.value, language)
            for key, (content, _) in cells.items()
            if content.given and isinstance(content.value, int | float)
        }
        for key, (content, to) in cells.items():
            text = typed.get(key, content.value if isinstance(content.value, str) else "")
            pieces = (
                self._pieces(content.formula, id, content.moved)
                if content.formula is not None
                else None
            )
            held = laid.cell(*key.split(":")).get(FORMAT) or ""
            if content.format is KEEP and (pieces is not None or isinstance(content.value, str)):
                own = (
                    self._carried(pieces, id)
                    if pieces is not None
                    else calculation.implied(text, language, held)
                )
                if (given := entered(held, own)) != held:
                    content = replace(content, format=given)
            if isinstance(content.value, str):
                holding = held if content.format is KEEP else content.format or ""
                text = calculation.kept(text, language, holding)
            self._write(table, laid, key, content, text, pieces, elements, to)

    def _carried(self, pieces: list, own: str) -> str:
        """The format a formula gives its cell by the cells it reads (engine.carried), a whole
        row or column by its first; none where the engine cannot read it, which shows why."""
        try:
            tree = parse(pieces)
        except Unreadable:
            return ""

        def format_of(ref: Ref | Held) -> str:
            laid = self.sheets.peek(ref.table or own) if isinstance(ref, Held) else None
            if laid is None:
                return ""
            row = ref.start.row or laid.ids_at([0]).get(0)
            col = ref.start.col or next(iter(laid.col_ids()), None)
            return laid.cell(row, col).get(FORMAT) or "" if row and col else ""

        return carried(tree, format_of, self.locale)

    def _table(self, operation: dict) -> dict:
        spot = self._spot(operation["at"])
        id = operation.get("id") or blocks.new_id()
        if id in self.found or id in self.sheets:
            raise Refused("taken", id)
        given = operation["rows"]
        width = max(len(line) for line in given)
        rows = operation.get("rowIds") or [blocks.new_id() for _ in given]
        cols = operation.get("colIds") or [blocks.new_id() for _ in range(width)]
        if len(rows) != len(given) or len(cols) != width:
            raise Refused("lines", "as many ids as lines")
        widths, heights = operation.get("widths", []), operation.get("heights", [])
        if len(widths) > len(cols) or len(heights) > len(rows):
            raise Refused("lines", "more widths or heights than lines")
        name = operation.get("name") or ""
        if name and name.casefold() in sheets.named(self.sheets):
            raise Refused("name_taken", name)
        attrs = {"id": id, **{each: operation[each] for each in ("sized",) if each in operation}}
        if "designs" in operation:
            attrs["designs"] = operation["designs"]
        elif (design := operation.get("design", designs.NEW)) != "plain":
            attrs["designs"] = [designs.ours(design)]
        if self.change is not None:
            attrs["proposedRows"] = {row: {"insertion": self.change} for row in rows}
        element = spot.parent.children.insert(spot.at, XmlElement(TABLE, attrs))
        self.sheets.make(
            Laid(
                id,
                self.sheets.tab,
                name,
                [Col(col, widths[x] if x < len(widths) else None) for x, col in enumerate(cols)],
                [Row(row, heights[y] if y < len(heights) else None) for y, row in enumerate(rows)],
            )
        )
        cells: dict[str, tuple[Content, str | None]] = {}
        covered: set[tuple[int, int]] = set()
        for y, line in enumerate(given):
            for x, each in enumerate(line):
                if (y, x) in covered:
                    if each is not None:
                        raise Refused("covered", f"{y + 1}:{x + 1}")
                    continue
                content, span = _content(each)
                bottom = y + (span or {}).get("rows", 1) - 1
                right = x + (span or {}).get("cols", 1) - 1
                slots = {(row, col) for row in range(y, bottom + 1) for col in range(x, right + 1)}
                if bottom >= len(rows) or right >= len(cols) or slots & covered:
                    raise Refused("span", f"{y + 1}:{x + 1}")
                covered |= slots - {(y, x)}
                to = key_of(rows[bottom], cols[right]) if (bottom, right) != (y, x) else None
                cells[key_of(rows[y], cols[x])] = (content, to)
        self._write_cells(element, id, cells, {})
        self._touch(id)
        return {"table": id, "rows": rows, "cols": cols}

    def _copy(self, operation: dict) -> dict:
        """A copy of the table right after it, under a name of its own: its formulas refer to
        the copy where they referred to their own table, or it holds the values they show."""
        id = operation["table"]
        found, laid = self._placed(id)
        new = operation.get("id") or blocks.new_id()
        if new in self.found or new in self.sheets:
            raise Refused("taken", new)
        name = operation.get("name", sheets.copy_name(self.sheets, laid.name))
        if problem := sheets.name_problem(self.sheets, new, name):
            raise Refused(problem, name)
        if isinstance(laid, Draft):
            self._copied(found, laid, new, name, operation.get("values", False))
            return {"table": new, "name": name}
        block = blocks.table_of(found.element, {id: laid})
        cells = [replace(cell, blocks=_anew(cell.blocks)) for cell in block.cells]
        grid = block.grid or blocks.Grid([], [])
        if operation.get("values", False):
            language = calculation.language(self.locale)
            by_key = {key_of(cell.row, cell.col): cell for cell in cells}
            for key in grid.formulas:
                row, _, col = key.partition(":")
                value = loaded(laid.row(row).values.get(col))
                to = laid.cell(row, col).get(TO)
                text = calculation.written(value, language)
                by_key[key] = blocks.light_cell(key, text, laid.look_at(row, col), to)
            cells = list(by_key.values())
            grid = replace(grid, formulas={}, values={})
        attrs = {each: value for each, value in block.attrs.items() if each != "proposedRows"}
        attrs |= {"id": new, "name": name}
        if self.change is not None:
            attrs["proposedRows"] = {row: {"insertion": self.change} for row in grid.rows}
        self._put(
            self._spot({"after": id}), [replace(block, id=new, attrs=attrs, grid=grid, cells=cells)]
        )
        return {"table": new, "name": name}

    def _copied(self, found: Found, source: Draft, new: str, name: str, values: bool) -> None:
        """The copy of a table Postgres holds: its text here, its rows copied there when the
        change is stored. A change made to the table earlier in the same run is not stored yet,
        so it would be missing from the copy."""
        if source.patch() is not None:
            raise Refused("copy_of_changed", source.table)
        block = blocks.table_of(found.element, {})
        attrs = {
            each: value
            for each, value in block.attrs.items()
            if each not in GRID_ATTRS and each != "proposedRows"
        } | {"id": new}
        if self.change is not None:
            insertion = {"insertion": self.change}
            attrs["proposedRows"] = {row: insertion for row in source.ids(0, source.size - 1)}
        spot = self._spot({"after": source.table})
        made = replace(block, id=new, attrs=attrs, cells=[])
        self._take(made)
        element = blocks.write_block(spot.parent, made, self.doc, self.written, spot.at)
        for cell in block.cells:
            self._node(element, replace(cell, blocks=_anew(cell.blocks)))
        self.sheets.copied(source, new, name, self.locale if values else None)
        self._arrived(spot, new)

    def _cells(self, operation: dict) -> dict:
        """Writes the cells given. A cell given a span is merged over it, what the slots it
        then covers held taken out, or split back to its own slot by a span of that slot."""
        id = operation["table"]
        found, laid = self._placed(id)
        cols = set(laid.col_ids())
        rows = laid.places({each["row"] for each in operation["cells"]})
        covered = sheets.covered(laid)
        cells: dict[str, tuple[Content, str | None]] = {}
        spanned: set[str] = set()
        for each in operation["cells"]:
            key = key_of(each["row"], each["col"])
            if each["row"] not in rows or each["col"] not in cols:
                raise Refused("no_cell", key)
            if key in covered:
                raise Refused("covered", key)
            to = None
            if "span" in each:
                to, slots = self._spanned(laid, each["row"], each["col"], each["span"])
                if slots & spanned:
                    raise Refused("span", key)
                spanned |= slots
            given = {
                name: value for name, value in each.items() if name not in ("row", "col", "span")
            }
            cells[key] = (_content(given)[0], to)
        if taken := sorted(spanned & cells.keys()):
            raise Refused("covered", taken[0])
        elements = self._elements_of(found.element)
        for key in spanned:
            row, _, col = key.partition(":")
            sheets.write(laid, row, col, dict.fromkeys(grids.INPUTS))
            if key in elements:
                _remove_cell(found.element, row, col)
                del elements[key]
            self._touch(id, key)
        self._write_cells(found.element, id, cells, elements)
        for key in cells:
            self._touch(id, key)
        return {}

    def _fill(self, operation: dict) -> dict:
        """Fills the slots from the range to the one given, below, above, right or left of
        it, as a sheet's fill handle does: each line of the range the way it fills goes on as
        a series where its cells make one, unless it only copies them, or else repeats them,
        each with its look and format, a formula moving with it."""
        id = operation["table"]
        found, laid = self._placed(id)
        cols = laid.col_ids()
        ends = laid.places(operation[name]["row"] for name in ("from", "to", "until"))

        def at(point: dict) -> tuple[int, int]:
            if point["row"] not in ends or point["col"] not in cols:
                raise Refused("no_cell", key_of(point["row"], point["col"]))
            return ends[point["row"]], cols.index(point["col"])

        (y0, x0), (y1, x1), (y, x) = (at(operation[name]) for name in ("from", "to", "until"))
        rows = laid.ids_at(range(min(y0, y1, y), max(y0, y1, y) + 1))
        top, bottom, left, right = min(y0, y1), max(y0, y1), min(x0, x1), max(x0, x1)
        down, across = not top <= y <= bottom, not left <= x <= right
        if down == across:
            raise Refused("fill", "one way, out of the range")
        if down:
            along, ahead = range(top, bottom + 1), range(bottom + 1, y + 1)
            if y < top:
                along, ahead = along[::-1], range(top - 1, y - 1, -1)
            shown = set(self._shown(id, laid, list(rows.values())))
            along = [r for r in along if rows[r] in shown]
            ahead = [r for r in ahead if rows[r] in shown]
            if not along:
                raise Refused("fill", "no row of the range shown")
            lines = [
                ([(r, c) for r in along], [(r, c) for r in ahead]) for c in range(left, right + 1)
            ]
        else:
            along, ahead = range(left, right + 1), range(right + 1, x + 1)
            if x < left:
                along, ahead = along[::-1], range(left - 1, x - 1, -1)
            lines = [
                ([(r, c) for c in along], [(r, c) for c in ahead]) for r in range(top, bottom + 1)
            ]
        covered = sheets.covered(laid)
        for slot in (slot for line in lines for part in line for slot in part):
            key = key_of(rows[slot[0]], cols[slot[1]])
            if key in covered or laid.cell(rows[slot[0]], cols[slot[1]]).get(TO):
                raise Refused("covered", key)
        elements = self._elements_of(found.element)
        places = sheets.Places(self.sheets)
        cells: dict[str, tuple[Content, str | None]] = {}
        for sources, targets in lines:
            keys = [key_of(rows[r], cols[c]) for r, c in sources]
            held = [laid.cell(rows[r], cols[c]) for r, c in sources]
            looks = [laid.look_at(rows[r], cols[c]) or {} for r, c in sources]
            texts = None
            if not operation.get("copies") and not any(
                key in elements or FORMULA in cell for key, cell in zip(keys, held, strict=True)
            ):
                given = [(cell.get(grids.TEXT) or "", cell.get(FORMAT)) for cell in held]
                texts = series(given, len(targets), self.locale)
            for k, (r, c) in enumerate(targets):
                source, key, cell = (
                    sources[k % len(sources)],
                    keys[k % len(keys)],
                    held[k % len(held)],
                )
                look, format = looks[k % len(looks)], cell.get(FORMAT)
                if texts is not None:
                    content = Content(True, texts[k], format=format, look=look)
                elif key in elements:
                    copied = [block_of(each) for each in self._json(elements[key])["content"]]
                    content = Content(
                        True,
                        blocks=_anew(copied),
                        format=format,
                        fill=elements[key].attributes.get("fill"),
                        edges=elements[key].attributes.get("edges"),
                    )
                elif FORMULA in cell:
                    text = places.text(cell[FORMULA], id, rows[source[0]], cols[source[1]])
                    moved = (r - source[0], c - source[1])
                    content = Content(True, formula=text, format=format, moved=moved, look=look)
                else:
                    content = Content(True, cell.get(grids.TEXT) or "", format=format, look=look)
                cells[key_of(rows[r], cols[c])] = (content, None)
        self._write_cells(found.element, id, cells, elements)
        for key in cells:
            self._touch(id, key)
        return {}

    @staticmethod
    def _spanned(laid: Laid, row: str, col: str, span: dict) -> tuple[str, set[str]]:
        """The slot a cell merged over the span reaches, or "" for one split back to its own,
        and the slots it covers beyond its own, which no other merged cell may share."""
        col_ids = laid.col_ids()
        y, x = laid.place(row), col_ids.index(col)
        bottom, right = y + span.get("rows", 1) - 1, x + span.get("cols", 1) - 1
        key = key_of(row, col)
        if bottom >= laid.size or right >= len(col_ids):
            raise Refused("span", key)
        merges = sheets.merged(laid)
        row_ids = laid.ids_at(
            {
                *range(y, bottom + 1),
                *(at for each in merges for at in range(each.y, each.y + each.rows)),
            }
        )
        slots = {
            key_of(row_ids[at], col_ids[across])
            for at in range(y, bottom + 1)
            for across in range(x, right + 1)
        } - {key}
        for each in merges:
            if (each.cell.row, each.cell.col) == (row, col):
                continue
            theirs = {
                key_of(row_ids[at], col_ids[across])
                for at in range(each.y, each.y + each.rows)
                for across in range(each.x, each.x + each.cols)
            }
            if theirs & (slots | {key}):
                raise Refused("span", key)
        return (key_of(row_ids[bottom], col_ids[right]) if slots else ""), slots

    @staticmethod
    def _between(laid: Laid | Draft, axis: str, operation: dict) -> list[str]:
        """The ids of the lines from the operation's one to its other, both included."""
        ends = [operation["from"], operation["to"]]
        if axis == grids.ROWS:
            at = laid.places(ends)
            if missing := [end for end in ends if end not in at]:
                raise Refused("no_row", missing[0])
            first, last = sorted(at[end] for end in ends)
            return laid.ids(first, last)
        cols = laid.col_ids()
        if missing := [end for end in ends if end not in cols]:
            raise Refused("no_col", missing[0])
        first, last = sorted(cols.index(end) for end in ends)
        return cols[first : last + 1]

    def _lines(self, operation: dict) -> dict:
        found, laid = self._placed(operation["table"])
        axis = operation["axis"]
        if operation.get("remove", False) or "hidden" in operation:
            if (
                "before" in operation
                or "ids" in operation
                or len({"remove", "hidden"} & operation.keys()) > 1
            ):
                raise Refused("invalid", "lines taken out or hidden are given by their ends alone")
            ends = {**operation}
            if "hidden" in operation:
                lines = laid.col_ids()
                if axis == grids.ROWS:
                    lines = [id for _, id in sorted(laid.ids_at({0, laid.size - 1}).items())]
                if not lines:
                    return {}
                ends.setdefault("from", lines[0])
                ends.setdefault("to", lines[-1])
            if "from" not in ends or "to" not in ends:
                raise Refused("invalid", "lines taken out need from and to")
            between = self._between(laid, axis, ends)
            if axis == grids.ROWS and operation.get("hidden", True):
                between = self._shown(operation["table"], laid, between)
            if "hidden" in operation:
                self._hide(laid, axis, between, operation["hidden"])
            else:
                self._unline(found, axis, set(between))
            return {}
        if "ids" not in operation or "from" in operation or "to" in operation:
            raise Refused("invalid", "lines put in are given by their ids alone")
        sheets.put_lines(laid, axis, operation["ids"], operation.get("before"))
        if operation["axis"] == "rows":
            _inherit(laid, operation["ids"])
        return {}

    @staticmethod
    def _hide(laid: Laid | Draft, axis: str, ids: list[str], hidden: bool) -> None:
        if axis == grids.COLS:
            for id in ids:
                laid.col(id).hidden = hidden
            return
        if isinstance(laid, Draft) and not hidden:
            ids = [id for id in ids if id in laid.base.hidden or id in laid.owned]
        for id in ids:
            if laid.row(id).hidden != hidden:
                laid.own(id).hidden = hidden

    def _rechart(self, table: str, change: sheets.Change) -> None:
        """Every chart of the tab over the table as `change` makes its range: what refers to a
        table beside the formulas and the defined names, which its sheets rewrite."""
        for child in blocks.body_of(self.doc).children:
            if not isinstance(child, XmlElement) or child.tag != "chart":
                continue
            over = child.attributes.get("range")
            if (
                isinstance(over, dict)
                and over.get("table") == table
                and (kept := change([over], None))
            ):
                child.attributes["range"] = kept[0]

    def _unline(self, found: Found, axis: str, gone: set[str]) -> None:
        """Takes the lines out of the table: a merged cell keeps its slots in the others, with
        its formula and number format, and one within them goes, as in the editor."""
        own, table = found.top, found.element
        laid = self.sheets.get(own)
        lines, part = (laid, "row") if axis == "rows" else (sheets.Lines(laid.col_ids()), "col")
        at = lines.places(gone)
        self._rechart(
            own, lambda pieces, owner: sheets.without_lines(pieces, part, lines, at, own, owner)
        )
        moved = sheets.take_lines(self.sheets, own, axis, gone)
        elements = self._elements_of(table)
        for old, new in moved.items():
            if (element := elements.get(old)) is not None:
                element.attributes["row"], element.attributes["col"] = new.split(":")
        for at in reversed(range(len(table.children))):
            child = table.children[at]
            if (
                isinstance(child, XmlElement)
                and child.tag == CELL
                and child.attributes.get(part) in gone
            ):
                del table.children[at : at + 1]
        proposed = table.attributes.get("proposedRows")
        if axis == "rows" and isinstance(proposed, dict) and gone & proposed.keys():
            if left := {row: each for row, each in proposed.items() if row not in gone}:
                table.attributes["proposedRows"] = left
            else:
                del table.attributes["proposedRows"]
        self._touch(own)

    def _grid(self, operation: dict) -> dict:
        """Names the table, an empty name taking its name off, sets its columns' widths and
        its rows' heights, hides lines or shows them again, and freezes the rows down to the one
        given."""
        found, laid = self._placed(operation["table"])
        if "name" in operation:
            name = operation["name"]
            if problem := sheets.name_problem(self.sheets, found.top, name):
                raise Refused(problem, name)
            if not name and compute.referred(
                self.sheets, compute.names_in(self.sheets.names()), found.top
            ):
                raise Refused("name_needed", found.top)
            laid.name = name
        sheets.sized(laid, operation.get("widths", {}), operation.get("heights", {}))
        for id, hidden in operation.get("hidden", {}).get(grids.COLS, {}).items():
            line = laid.col(id)
            if line is None:
                raise Refused("no_col", id)
            line.hidden = hidden
        if "frozen" in operation:
            frozen = operation["frozen"]
            if frozen is not None and laid.row(frozen) is None:
                raise Refused("no_row", frozen)
            laid.frozen = frozen
        self.touched.setdefault(found.top, set())
        return {}

    def _looks(self, operation: dict) -> dict:
        """Formats whole rows or columns as a sheet formats its lines: their looks changed, and
        each cell in them that shows another look, its own or a crossing line's, keeping what it
        showed changed the same way."""
        id = operation["table"]
        found, laid = self._placed(id)
        rows = operation["axis"] == grids.ROWS
        ids = self._between(laid, operation["axis"], operation)
        if rows:
            if isinstance(laid, Draft):
                laid.load(ids)
            lines = {id: laid.row(id) for id in ids}
        else:
            lines = {col.id: col for col in laid.cols}
        marks, attrs = operation.get("marks", {}), operation.get("attrs", {})
        fill = operation.get("fill", KEEP)
        if rows:
            crossing = [col.id for col in laid.cols if col.look is not None]
            slots = {(row, col) for row in ids for col in [*laid.row(row).cells, *crossing]}
        else:
            wanted = set(ids)
            holding = laid.holding(wanted)
            slots = {(row, col) for row in holding for col in laid.row(row).cells.keys() & wanted}
            slots |= {(row, col) for row in laid.looked() for col in ids}
        covered = sheets.covered(laid)
        nodes = self._elements_of(found.element)
        shown = {
            (row, col): laid.look_at(row, col)
            for row, col in slots
            if key_of(row, col) not in covered and key_of(row, col) not in nodes
        }
        for each in ids:
            look = _changed(lines[each].look or {}, marks, attrs, fill) or None
            if rows:
                laid.own(each).look = look and grids.look(look)
            else:
                lines[each].look = look and grids.look(look)
        for (row, col), was in shown.items():
            sheets.write(laid, row, col, {LOOK: _changed(was or {}, marks, attrs, fill)})
        within = set(ids)
        keys = {key for key in nodes if key.partition(":")[0 if rows else 2] in within}
        if fill is not KEEP:
            for key in keys:
                _filled_with(nodes[key], fill)
        self._looked(id, keys, marks, attrs)
        self.touched.setdefault(id, set())
        return {}

    def _looked(self, table: str, cells: set[str], marks: dict, attrs: dict) -> None:
        """The text of the table's cells formatted as `_looks` formats a line: the marks given
        or taken off over all of each paragraph, kept at its end where it has no text."""
        for block, found in list(self.found.items()):
            if found.top != table or found.cell not in cells or found.note:
                continue
            if found.element.tag not in TEXTBLOCKS:
                continue
            if chunks_of(found.element)[1]:
                for name, value in marks.items():
                    given = {"remove": True} if value is None else {"attrs": value}
                    self._mark({"range": {"block": block}, "mark": name, **given})
                changed = attrs
            else:
                ends = found.element.attributes.get("endMarks")
                kept = _changed({"marks": ends if isinstance(ends, dict) else {}}, marks, {})
                changed = {**attrs, "endMarks": kept.get("marks")}
            if changed:
                self._set({"block": block, "attrs": changed})

    def _order(self, operation: dict) -> dict:
        """Sorts the rows from one to the other, or the table's data, by their values in the
        column as Excel sorts them; a range over several rows keeps covering the same places
        and a reference within one row follows it, as in the editor."""
        found, laid = self._placed(operation["table"])
        own = found.top
        rows = None
        if "from" in operation or "to" in operation:
            if "from" not in operation or "to" not in operation:
                raise Refused("invalid", "rows sorted are given by both their ends")
            rows = self._between(laid, grids.ROWS, operation)
        if operation["col"] not in laid.col_ids():
            raise Refused("no_col", operation["col"])
        try:
            ordered = data.order(
                self.sheets.document,
                laid,
                found.element,
                self.locale,
                operation["col"],
                rows,
                operation.get("descending", False),
                lambda ids: self._shown(own, laid, ids),
            )
        except data.Unsortable:
            raise Refused("merged_rows", own) from None
        before, after = sheets.order_rows(self.sheets, own, ordered)
        if before == after:
            return {}
        self._rechart(
            own, lambda pieces, owner: sheets.reordered(pieces, before, after, own, owner)
        )
        self._touch(own)
        return {}

    def _clone(
        self,
        source: XmlElement,
        parent: XmlFragment | XmlElement,
        at: int,
        tag: str | None = None,
        attrs: dict | None = None,
    ) -> XmlElement:
        """A copy of the element, with its ids, at the index of the parent given: Yjs moves
        nothing, so a block moves as a copy of itself."""
        kept = {name: value for name, value in source.attributes} if attrs is None else attrs
        element = parent.children.insert(at, XmlElement(tag or source.tag, kept))
        for child in source.children:
            if isinstance(child, XmlText):
                copy_text(child, element.children.append(XmlText()))
            elif isinstance(child, XmlElement):
                self._clone(child, element, len(element.children))
        return element

    def _set(self, operation: dict) -> dict:
        found = self._block(operation["block"])
        element = found.element
        tag = operation.get("type", element.tag)
        attrs = operation.get("attrs", {})
        allowed = schema.attrs_of(NODES.get(tag, {}))
        if unknown := sorted(attrs.keys() - (allowed.keys() - {"id"})):
            raise Refused("attribute", f"{tag}.{unknown[0]}")
        if tag != element.tag:
            if element.tag not in TEXTBLOCKS:
                raise Refused("retype", element.tag)
            kept = {name: value for name, value in element.attributes if name in allowed}
            element = self._clone(element, found.parent, found.at, tag, kept)
            del found.parent.children[found.at + 1 : found.at + 2]
        for name, value in attrs.items():
            if value is not None:
                element.attributes[name] = value
            elif element.attributes.get(name) is not None:
                del element.attributes[name]
        if found.cell is not None:
            self._touch(found.top, found.cell)
        elif element.tag == TABLE:
            self.touched.setdefault(found.top, set())
        else:
            self._touch(found.top)
        return {}

    def _range(self, given: dict) -> tuple[Found, list[tuple[XmlText, int, str]], int, int]:
        """The texts of the block or note, and the range as it now is in them: counted in its
        text as the run found it, then moved by the run's own replacements before it."""
        id = given["block"]
        found = self.found.get(id)
        if found is None or not (found.note or found.element.tag in TEXTBLOCKS):
            raise Refused("no_text", id)
        chunks, _ = chunks_of(found.element)
        plain = self.plains.setdefault(id, "".join(each for *_, each in chunks))
        if "words" in given:
            start = _occurrence(plain, given["words"], given.get("occurrence", 1))
            if start is None:
                raise Refused("no_words", given["words"])
            end = start + len(given["words"])
        else:
            start, end = given.get("from", 0), given.get("to", len(plain))
        if not start <= end <= len(plain):
            raise Refused("range", f"{start}…{end} of {len(plain)}")
        asked = (start, end)
        for first, last, written in self.edits.get(id, []):
            if (start < last and end > first) if first < last else start < first < end:
                raise Refused("overlap", "…".join(map(str, asked)))
            shift = written - (last - first)
            moved = start + shift if start >= last else start
            end = moved if start == end else end + shift if end > first else end
            start = moved
        self._touch(found.top, found.cell)
        return found, chunks, start, end

    def _mark(self, operation: dict) -> dict:
        _, chunks, start, end = self._range(operation["range"])
        name, attrs = operation["mark"], operation.get("attrs") or {}
        remove = operation.get("remove", False)
        if remove and attrs:
            raise Refused("invalid", "a mark taken off takes no attributes")
        for text, first, last in _spans(chunks, start, end):
            present = _keys(text, first, last)
            off = {
                key: None
                for key in present
                if blocks.mark_name(key) == name
                or (not remove and _excludes(name, blocks.mark_name(key)))
            }
            text.format(first, last, off if remove else {**off, name: attrs})
        return {}

    def _text(self, operation: dict) -> dict:
        pieces = [
            (
                node["text"],
                {mark["type"]: mark.get("attrs") or {} for mark in node.get("marks", [])},
            )
            for node in operation["content"]
        ]
        self._written(operation["range"], pieces, formatted=True)
        return {}

    def _written(
        self, given: dict, pieces: list[tuple[str, dict]], formatted: bool = False
    ) -> None:
        """Writes the pieces in place of the range, or in the formatting of its first character
        where they are not formatted; under a proposer, after the range, which stays proposed
        deleted but for the proposer's own proposed insertions."""
        found, chunks, start, end = self._range(given)
        if not formatted:
            first = _formatting_at(chunks, start)
            pieces = [(written, first) for written, _ in pieces]
        spans = list(_spans(chunks, start, end))
        gone = 0
        for text, first, last in reversed(spans):
            if self.change is None:
                del text[first:last]
            else:
                gone += self._struck(text, first, last)
        kept = end - start - gone if self.change is not None else 0
        written = sum(len(each) for each, _ in pieces)
        self.edits.setdefault(given["block"], []).append((start, end, kept + written))
        if not pieces:
            return
        place = start + kept
        text, at = next(
            (
                (text, len(plain[: place - at].encode()))
                for text, at, plain in chunks_of(found.element)[0]
                if at <= place <= at + len(plain)
            ),
            None,
        ) or (found.element.children.insert(0, XmlText()), 0)
        self._typed(text, at, pieces)

    def _substitute(self, operation: dict) -> dict:
        """Replaces the text sought where it starts in a block or a note, in the one cell given,
        or else everywhere in the tab, its text and its tables' cells but those a formula
        calculates; each replacement in the formatting of the text it replaces."""
        sought = finding.Sought(
            operation["find"], operation.get("case", False), operation.get("words", False)
        )
        by = operation["by"]
        block = "block" in operation
        cell = [name in operation for name in ("table", "row", "col")]
        if block != ("from" in operation) or (any(cell) and not all(cell)) or (block and any(cell)):
            raise Refused("invalid", "block with from, or table with row and col")
        if block:
            id, start = operation["block"], operation["from"]
            found = self.found.get(id)
            if found is None or not (found.note or found.element.tag in TEXTBLOCKS):
                raise Refused("no_text", id)
            ends = {
                at + first: at + last
                for _, at, plain in chunks_of(found.element)[0]
                for first, last in sought.spans(plain)
            }
            if start not in ends:
                raise Refused("no_words", operation["find"])
            self._written({"block": id, "from": start, "to": ends[start]}, [(by, {})])
            return {"replaced": 1}
        if all(cell):
            table, row, col = operation["table"], operation["row"], operation["col"]
            found, laid = self._placed(table)
            element = finding.blocked_cells(found.element).get((row, col))
            if element is not None:
                hits = list(self._hits_in(element, sought))
                if not hits:
                    raise Refused("no_words", operation["find"])
                return {"replaced": self._swapped(hits, by)}
            held = laid.cell(row, col)
            if FORMULA in held:
                raise Refused("formula", key_of(row, col))
            typed = held.get(grids.TEXT)
            if not isinstance(typed, str) or not sought.spans(finding.unquoted(typed)[1]):
                raise Refused("no_words", operation["find"])
            self._retyped(table, [(row, col, typed)], sought, by)
            return {"replaced": 1}
        hits: list[finding.Hit] = []
        typed: dict[str, list[tuple[str, str, str]]] = {}
        for element in self.body.children:
            if not isinstance(element, XmlElement):
                continue
            if element.tag in TEXTBLOCKS:
                hits.extend(finding.in_block(element, sought))
            if element.tag != TABLE or (table := element.attributes.get("id")) not in self.sheets:
                continue
            for cell in finding.blocked_cells(element).values():
                hits.extend(self._hits_in(cell, sought))
            found = finding.text_cells(element, self.sheets.get(table), sought, None)
            typed[table] = [(row, col, text) for row, col, text, formula in found if not formula]
        replaced = self._swapped(hits, by)
        for table, cells in typed.items():
            if cells:
                self._retyped(table, cells, sought, by)
                replaced += len(cells)
        return {"replaced": replaced}

    @staticmethod
    def _hits_in(cell: XmlElement, sought: finding.Sought) -> Iterator[finding.Hit]:
        for child in cell.children:
            if isinstance(child, XmlElement) and child.tag in TEXTBLOCKS:
                yield from finding.in_block(child, sought)

    def _swapped(self, hits: list[finding.Hit], by: str) -> int:
        for hit in hits:
            self._written({"block": hit.block, "from": hit.start, "to": hit.end}, [(by, {})])
        return len(hits)

    def _retyped(
        self, table: str, typed: list[tuple[str, str, str]], sought: finding.Sought, by: str
    ) -> None:
        """Types the cells' text anew with the text sought replaced."""
        pattern = sought.pattern()
        cells = []
        for row, col, text in typed:
            quote, shown = finding.unquoted(text)
            cells.append(
                {"row": row, "col": col, "value": quote + pattern.sub(lambda _: by, shown)}
            )
        self._cells({"op": "cells", "table": table, "cells": cells})

    def _typed(self, text: XmlText, at: int, pieces: list[tuple[str, dict]]) -> None:
        """Writes the pieces from the byte at, each with its formatting, under a proposer as
        proposed insertions."""
        for written, formatting in pieces:
            size = len(written.encode())
            text.insert(at, written, formatting or None)
            if self.change is not None:
                off = {key: None for key in _keys(text, at, at + size) if key in REVIEWED}
                text.format(at, at + size, {**off, "insertion": self.change})
            at += size

    def _replace(self, operation: dict) -> dict:
        """Writes the block's or note's whole text anew as its tags place it: a tagged span
        with the formatting of the part its tag numbers, the rest with none, and each note and
        field where its tag stands. Under a proposer the old text stays, proposed deleted,
        before the new."""
        id = operation["block"]
        found, chunks, start, end = self._range({"block": id})
        if _proposed_in(found, chunks):
            raise Refused("proposed", id)
        gaps, formats, inline = _gaps(found.element)
        written = _spanned(operation["text"], formats, inline)
        kept = 0
        for (index, texts), pieces in reversed(list(zip(gaps, written, strict=True))):
            for text in texts:
                size = len(plain_of(text).encode())
                if self.change is None:
                    del text[0:size]
                else:
                    kept += len(plain_of(text)) - self._struck(text, 0, size)
            if pieces:
                text = texts[-1] if texts else found.element.children.insert(index, XmlText())
                self._typed(text, len(plain_of(text).encode()), pieces)
        length = sum(len(piece) for pieces in written for piece, _ in pieces)
        self.edits.setdefault(id, []).append((start, end, kept + length))
        return {}

    def _rewrite(self, operation: dict) -> dict:
        """Writes the block's text anew, changing only the words that differ: a new word takes
        the formatting of the text it replaces, or of the text before it."""
        id = operation["block"]
        found, chunks, _, _ = self._range({"block": id})
        if found.note:
            raise Refused("no_text", id)
        if _proposed_in(found, chunks):
            raise Refused("proposed", id)
        old = "".join(plain for _, _, plain in chunks)
        changes = [
            (start, end, written, _formatting_at(chunks, start if start < end else start - 1))
            for start, end, written in _differing(old, operation["text"])
        ]
        for start, end, written, formatting in changes:
            marks = [{"type": key, "attrs": value} for key, value in formatting.items()]
            content = [{"type": "text", "text": written, "marks": marks}] if written else []
            self._text({"range": {"block": id, "from": start, "to": end}, "content": content})
        return {}

    def _struck(self, text: XmlText, start: int, end: int) -> int:
        """Proposes the text's bytes between start and end deleted but for the proposer's own
        proposed insertions, which go as if never written; how many characters went."""
        edits, at, gone = [], 0, 0
        for part, attributes in text.diff():
            encoded, attributes = part.encode(), attributes or {}
            first, last = max(at, start), min(at + len(encoded), end)
            if first < last and self._own(attributes.get("insertion")):
                edits.append((first, last, None))
                gone += len(encoded[first - at : last - at].decode())
            elif first < last and not attributes.get("deletion"):
                edits.append((first, last, {"deletion": self.change}))
            at += len(encoded)
        for first, last, mark in reversed(edits):
            if mark is None:
                del text[first:last]
            else:
                text.format(first, last, mark)
        return gone

    def _strike(self, container: XmlFragment | XmlElement, at: int) -> None:
        """Proposes the block deleted, and of a paragraph its text and its end: a table its
        rows, what the proposer proposed inserted going as if never written."""
        element = container.children[at]
        if element.tag == TABLE:
            _, laid = self._placed(element.attributes.get("id"))
            proposed = dict(element.attributes.get("proposedRows") or {})
            for row in laid.row_ids():
                if not (proposed.get(row) or {}).get("deletion"):
                    proposed[row] = {**proposed.get(row, {}), "deletion": self.change}
            element.attributes["proposedRows"] = proposed
            return
        if element.tag in TEXTBLOCKS:
            for index in reversed(range(len(element.children))):
                child = element.children[index]
                if isinstance(child, XmlText):
                    self._struck(child, 0, len(plain_of(child).encode()))
                elif self._own(child.attributes.get("insertion")):
                    del element.children[index : index + 1]
                elif not child.attributes.get("deletion"):
                    child.attributes["deletion"] = self.change
        if self._own(element.attributes.get("insertion")):
            self._goes(container, at, element)
        elif not element.attributes.get("deletion"):
            element.attributes["deletion"] = self.change

    def _run(self, start: str, end: str | None) -> tuple[Found, int]:
        """The sibling blocks from the first to the last given, and how many they are."""
        first = self._block(start)
        last = self._block(end) if end is not None else first
        if last.parent != first.parent or last.at < first.at:
            raise Refused("not_a_run", f"{start}…{end}")
        return first, last.at - first.at + 1

    def _move(self, operation: dict) -> dict:
        first, count = self._run(operation["from"], operation.get("to"))
        moved = [first.parent.children[first.at + offset] for offset in range(count)]
        ids = [element.attributes.get("id") for element in moved]
        spot = self._spot(operation["at"])
        if spot.table in ids:
            raise Refused("into_itself", spot.table)
        same = spot.parent == first.parent
        if same and first.at <= spot.at <= first.at + count:
            return {}
        for offset, element in enumerate(moved):
            self._clone(element, spot.parent, spot.at + offset)
        start = first.at + (count if same and spot.at <= first.at else 0)
        del first.parent.children[start : start + count]
        if first.cell is not None:
            self._touch(first.top, first.cell)
        if spot.cell is not None:
            self._touch(spot.table, spot.cell)
        return {}

    def _delete(self, operation: dict) -> dict:
        first, count = self._run(operation["from"], operation.get("to"))
        if self.change is None:
            del first.parent.children[first.at : first.at + count]
        else:
            ids = [
                first.parent.children[at].attributes.get("id")
                for at in range(first.at, first.at + count)
            ]
            for at in reversed(range(first.at, first.at + count)):
                self._strike(first.parent, at)
            if first.cell is None:
                for id in ids:
                    self.touched.setdefault(id, set() if id in self.sheets else None)
        if first.cell is not None:
            self._touch(first.top, first.cell)
        return {}

    def _accept(self, operation: dict) -> dict:
        return self._review(Review(operation.get("ids"), True))

    def _reject(self, operation: dict) -> dict:
        return self._review(Review(operation.get("ids"), False))

    def _review(self, review: Review) -> dict:
        """Takes the proposals into the text or out of it: an insertion accepted stays and one
        rejected goes, a deletion the other way round, a formatting change keeps the new
        formatting or puts back the old, and a paragraph whose end goes joins the next one,
        whose type and attributes the two keep, as Word's paragraph mark keeps them."""
        self._review_rows(review)
        self.found = self._index()
        # A note first, as its paragraph may take it out.
        for found in sorted(self.found.values(), key=lambda found: not found.note):
            if found.note or found.element.tag in TEXTBLOCKS:
                self._review_inline(found, review)
        for container, table, cell in self._containers():
            self._review_blocks(container, table, cell, review)
        if (missing := review.missing()) is not None:
            raise Refused("no_proposal", missing)
        return {}

    def _review_rows(self, review: Review) -> None:
        tables = [found for found in self.found.values() if found.element.tag == TABLE]
        for found in sorted(tables, key=lambda found: found.at, reverse=True):
            proposed = found.element.attributes.get("proposedRows")
            if not isinstance(proposed, dict):
                continue
            kept, gone = {}, set()
            for row, changes in proposed.items():
                settled, goes = review.settle(changes)
                if goes:
                    gone.add(row)
                elif left := {name: each for name, each in changes.items() if name not in settled}:
                    kept[row] = left
            if kept == proposed:
                continue
            if kept:
                found.element.attributes["proposedRows"] = kept
            else:
                del found.element.attributes["proposedRows"]
            _, laid = self._placed(found.top)
            present = set(laid.places(gone))
            if len(present) >= laid.size:
                del found.parent.children[found.at : found.at + 1]
            elif present:
                self._unline(found, "rows", present)
            self._touch(found.top)

    def _review_inline(self, found: Found, review: Review) -> None:
        changed = False
        for at in reversed(range(len(found.element.children))):
            child = found.element.children[at]
            if isinstance(child, XmlText):
                changed |= _review_text(child, review)
                continue
            settled, goes = review.settle(child.attributes)
            if goes:
                del found.element.children[at : at + 1]
            for name in [] if goes else settled:
                del child.attributes[name]
            changed |= bool(settled)
        if changed:
            self._touch(found.top, found.cell)

    def _containers(self) -> Iterator[tuple[XmlFragment | XmlElement, str | None, str | None]]:
        """The text and its tables' cells, each with its table and its cell."""
        yield self.body, None, None
        for table in self.body.children:
            if isinstance(table, XmlElement) and table.tag == TABLE:
                for cell in table.children:
                    if isinstance(cell, XmlElement) and cell.tag == CELL:
                        key = key_of(cell.attributes.get("row"), cell.attributes.get("col"))
                        yield cell, table.attributes.get("id"), key

    def _review_blocks(
        self,
        container: XmlFragment | XmlElement,
        table: str | None,
        cell: str | None,
        review: Review,
    ) -> None:
        changed = False
        for at in reversed(range(len(container.children))):
            element = container.children[at]
            if not isinstance(element, XmlElement) or element.tag == TABLE:
                continue
            formatting = element.attributes.get("formatting")
            restyled = review.chosen(formatting)
            settled, goes = review.settle(element.attributes)
            if not (restyled or settled):
                continue
            changed = True
            for name in settled:
                del element.attributes[name]
            if restyled:
                del element.attributes["formatting"]
                if not review.accepted:
                    element = self._restyle(container, at, element, formatting["before"])
            if goes:
                element = self._goes(container, at, element)
            if element is not None and table is None:
                self._touch(element.attributes.get("id"))
        if not any(isinstance(child, XmlElement) for child in container.children):
            blocks.write_block(container, Block("paragraph"), self.doc, self.written)
        if changed and table is not None:
            self._touch(table, cell)

    def _restyle(
        self, container: XmlFragment | XmlElement, at: int, element: XmlElement, before: dict
    ) -> XmlElement:
        """The block as it was before its formatting changed: its type and attributes."""
        if before["type"] not in TEXTBLOCKS:
            raise Refused("retype", before["type"])
        kept = {name: value for name, value in element.attributes if name in ("id", *PROPOSED)}
        attrs = {**before["attrs"], **kept}
        if before["type"] != element.tag:
            restyled = self._clone(element, container, at, before["type"], attrs)
            del container.children[at + 1 : at + 2]
            return restyled
        for name in [name for name, _ in element.attributes if name not in attrs]:
            del element.attributes[name]
        for name, value in attrs.items():
            element.attributes[name] = value
        return element

    def _goes(
        self, container: XmlFragment | XmlElement, at: int, element: XmlElement
    ) -> XmlElement | None:
        """The block goes, and of a paragraph its end: the text joins the next paragraph's,
        where there is one, and a paragraph without text goes unless it is its place's only
        block; what stays of it, if anything does."""
        if element.tag in TEXTBLOCKS and _filled(element):
            after = container.children[at + 1] if at + 1 < len(container.children) else None
            if isinstance(after, XmlElement) and after.tag in TEXTBLOCKS:
                return self._join(container, at, element, after)
            return element
        if element.tag in TEXTBLOCKS and len(container.children) == 1:
            return element
        del container.children[at : at + 1]
        return None

    def _join(
        self, container: XmlFragment | XmlElement, at: int, element: XmlElement, after: XmlElement
    ) -> XmlElement:
        attrs = {name: value for name, value in after.attributes if name != "id"}
        attrs["id"] = element.attributes.get("id")
        if after.tag != element.tag:
            element = self._clone(element, container, at, after.tag, attrs)
            del container.children[at + 1 : at + 2]
        else:
            for name in [name for name, _ in element.attributes if name not in attrs]:
                del element.attributes[name]
            for name, value in attrs.items():
                element.attributes[name] = value
        for child in after.children:
            last = element.children[len(element.children) - 1] if element.children else None
            if isinstance(child, XmlText):
                into = last if isinstance(last, XmlText) else element.children.append(XmlText())
                copy_text(child, into)
            elif isinstance(child, XmlElement):
                self._clone(child, element, len(element.children))
        del container.children[at + 1 : at + 2]
        return element

    def _json(self, element: XmlElement, cells: set[str] | None = None) -> dict:
        """The element as ProseMirror JSON, exactly as it is kept; of a table, only the cells
        given, unless none are."""
        spec = NODES.get(element.tag)
        if spec is None:
            raise Refused("schema", f"there is no {element.tag} node")
        attrs = {name: _number(value) for name, value in element.attributes}
        if unknown := sorted(attrs.keys() - schema.attrs_of(spec).keys()):
            raise Refused("schema", f"a {element.tag} has no attribute {unknown[0]}")
        content: list[dict] = []
        for child in element.children:
            if isinstance(child, XmlText):
                for part, attributes in child.diff():
                    marks = [
                        self._mark_json(key, value) for key, value in (attributes or {}).items()
                    ]
                    content.append(
                        {"type": "text", "text": part, **({"marks": marks} if marks else {})}
                    )
            elif isinstance(child, XmlElement):
                key = key_of(child.attributes.get("row"), child.attributes.get("col"))
                if child.tag != CELL or cells is None or key in cells:
                    content.append(self._json(child))
        return {"type": element.tag, "attrs": attrs, **({"content": content} if content else {})}

    @staticmethod
    def _mark_json(key: str, value) -> dict:
        name = blocks.mark_name(key)
        if name not in MARKS or not isinstance(value, dict):
            raise Refused("schema", f"there is no {key} mark")
        if unknown := sorted(value.keys() - schema.attrs_of(MARKS[name]).keys()):
            raise Refused("schema", f"a {name} mark has no attribute {unknown[0]}")
        return {"type": name, "attrs": value}

    def check(self, patches: list[dict]) -> None:
        """Checks the text's blocks, in their order, and every block touched, against the
        schema, as the editor would hold them, the touched tables' names and every cell the
        run wrote into a grid."""
        nodes = schema.prosemirror().nodes
        match = nodes["doc"].content_match
        for child in self.body.children:
            if isinstance(child, XmlElement):
                match = match.match_type(nodes[child.tag]) if child.tag in nodes else None
                if match is None:
                    raise Refused("schema", f"a {child.tag} cannot stand there in the text")
        if not match.valid_end:
            raise Refused("schema", "the text needs a block")
        found = self._index()
        present = {top for top, each in found.items() if each.element.tag == TABLE}
        names = Counter(
            laid.name.casefold()
            for table, laid in self.sheets.tables()
            if laid.name and (table in present or self.sheets.stands(table))
        )
        for top, cells in self.touched.items():
            if (each := found.get(top)) is None:
                continue
            laid = self.sheets.peek(top) if each.element.tag == TABLE else None
            if laid is not None and laid.name and names[laid.name.casefold()] > 1:
                raise Refused("name_taken", laid.name)
            if laid is not None and laid.name and not schema.holds("tableName", laid.name):
                raise Refused("schema", f"{top}: a table cannot be named {laid.name}")
            try:
                Checked.from_json(schema.prosemirror(), self._json(each.element, cells)).check()
            except ValueError as error:
                raise Refused("schema", f"{top}: {error}") from None
        for patch in patches:
            for key, cell in _written(patch):
                self.check_cell(patch["table"], key, cell)
            for id, look in _line_looks(patch):
                self.check_look(patch["table"], id, look)

    @staticmethod
    def check_cell(table: str, key: str, cell: dict) -> None:
        """Checks a cell of a grid: its look as the paragraph and marks a light cell shows,
        its formula's references, its number format and the slot it is merged to."""
        if not schema.holds("gridCell", cell):
            raise Refused("schema", f"{table} {key}: no cell holds {sorted(cell)}")
        look = cell.get(LOOK)
        if look and (problem := _look_problem(json.dumps(look, sort_keys=True))):
            raise Refused("schema", f"{table} {key}: {problem}")

    @staticmethod
    def check_look(table: str, line: str, look: dict) -> None:
        """Checks the look of a row or a column as the light cells in it would show it."""
        if not schema.holds("look", look):
            raise Refused("schema", f"{table} {line}: no look holds {sorted(look)}")
        if problem := _look_problem(json.dumps(look, sort_keys=True)):
            raise Refused("schema", f"{table} {line}: {problem}")

    def check_whole(self) -> None:
        """Checks every block of the text as `check` does those touched, and that each table
        has a grid of a name no other has: a state brought whole from elsewhere, its grids
        checked as they are read."""
        self.touched = {}
        self.check(self.sheets.patches())
        names: Counter[str] = Counter()
        for child in self.body.children:
            if not isinstance(child, XmlElement):
                continue
            try:
                Checked.from_json(schema.prosemirror(), self._json(child)).check()
            except ValueError as error:
                raise Refused("schema", f"{child.tag}: {error}") from None
            if child.tag != TABLE:
                continue
            id = child.attributes.get("id")
            laid = self.sheets.peek(id)
            if laid is None:
                raise Refused("schema", f"{id}: a table has no grid")
            if laid.name:
                names[laid.name.casefold()] += 1
                if names[laid.name.casefold()] > 1:
                    raise Refused("name_taken", laid.name)


# A sheet's thousands of cells share a handful of looks, each checked against the schema once.
@lru_cache(maxsize=4096)
def _look_problem(given: str) -> str | None:
    """What keeps a light cell from showing the look, as JSON, or None where it can."""
    look = json.loads(given)
    attrs = look.get("attrs") or {}
    marks = look.get("marks") or {}
    if set(attrs) - set(blocks.LOOK_ATTRS):
        return "a light cell's paragraph has no such look"
    if set(marks) & set(blocks.UNLOOKED_MARKS):
        return "a light cell carries no proposal"
    try:
        text = {
            "type": "text",
            "text": " ",
            "marks": [Editing._mark_json(name, value) for name, value in marks.items()],
        }
        paragraph = {"type": "paragraph", "attrs": attrs, "content": [text]}
        Checked.from_json(schema.prosemirror(), paragraph).check()
    except Refused as refused:
        return str(refused)
    except ValueError as error:
        return str(error)
    return None


@dataclass(frozen=True)
class Change:
    """What a run changed in a room: what its transaction inserted and deleted, by the Yjs ids
    of the state it was made in, and what it did to the grids of the room's tables, each
    patch with its before as it found it."""

    insertions: bytes
    deletions: bytes
    grids: list[dict] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.insertions or self.deletions or self.grids)


@dataclass
class Performed:
    """What a run did: the update that reached the room, what each operation made, by id,
    where its blocks' texts went, and its change, none where it changed nothing."""

    update: bytes
    made: list[dict]
    written: blocks.Written
    change: Change | None


@dataclass
class Prepared:
    """A change worked out on a copy of a room's state, to be committed to the room: the
    update to its text and the patches to its grids, which the room's server applies first,
    with a guard where the change is taken back. Committed under the origin of a run, the
    text's part is kept so it can be taken back."""

    update: bytes
    patches: list[dict]
    origin: str | None = None
    scopes: Callable[[Doc], list] | None = None
    made: list[dict] = field(default_factory=list)
    written: blocks.Written | None = None
    guard: bool = False

    def commit(self, doc: Doc, applied: list[dict]) -> Performed:
        change = None
        if self.origin is None:
            with doc.transaction():
                doc.apply_update(self.update)
        else:
            manager = UndoManager(scopes=(self.scopes or _scopes)(doc), capture_timeout_millis=0)
            manager.include_origin(self.origin)
            with doc.transaction(origin=self.origin):
                doc.apply_update(self.update)
            item = next(iter(manager.undo_stack), None)
            change = Change(
                item.insertions.encode() if item else b"",
                item.deletions.encode() if item else b"",
                applied,
            )
        return Performed(self.update, self.made, self.written, change or None)


def _scopes(doc: Doc) -> list:
    return [blocks.body_of(doc)]


def _own_scopes(doc: Doc) -> list:
    return [doc.get(styles.THEME, type=Map), doc.get(styles.STYLES, type=Map)]


def carry_out(
    doc: Doc,
    sheets: Sheets,
    operations: list,
    locale: str,
    run: str,
    propose: Proposer | None = None,
    into: Callable[[Doc], XmlFragment] | None = None,
    scopes: Callable[[Doc], list] | None = None,
    seen: Mapping[str, filtering.View] | None = None,
) -> Prepared:
    """Carries out the operations on a copy of the doc's state and of its grids and, all of
    it checked, prepares them for the doc as one transaction whose origin is the run: on the
    tab's text, or the fragment `into` finds in a state, a header's or a footer's, whose
    change `scopes` then keeps; an edit over a range of rows reaching only those the user's
    filter of the table, by table, shows them."""
    copy = Doc()
    copy.apply_update(doc.get_update())
    before = copy.get_state()
    body = into(copy) if into is not None else None
    editing = Editing(copy, sheets, locale, body, propose=propose, seen=seen)
    made = []
    with copy.transaction():
        for at, operation in enumerate(operations):
            try:
                made.append(editing.carry(operation))
            except Refused as refused:
                refused.operation = at
                raise
    patches = sheets.patches()
    editing.check(patches)
    return Prepared(
        copy.get_update(before),
        patches,
        run,
        scopes,
        made=made,
        written=editing.written,
    )


def write(
    doc: Doc,
    sheets: Sheets,
    content: list[Block],
    into: Callable[[Doc], XmlFragment] | None = None,
) -> Prepared:
    """Writes the blocks, tables with their cells, at the end of the tab's text, or of the
    fragment `into` finds in a state, a header's or a footer's, checked as a run's operations
    are: the content an importer or a page setup brings."""
    copy = Doc()
    copy.apply_update(doc.get_update())
    before = copy.get_state()
    editing = Editing(copy, sheets, None, into(copy) if into is not None else None)
    with copy.transaction():
        editing.found = editing._index()
        editing._put(Spot(editing.body, len(editing.body.children)), content)
    patches = sheets.patches()
    if content:
        editing.check(patches)
    return Prepared(copy.get_update(before), patches, written=editing.written)


def carry_out_own(doc: Doc, operations: list, run: str) -> Prepared:
    """Carries out operations on a document's own state, all of them checked first, as one
    transaction whose origin is the run."""
    theme, looks = styles.read(doc)
    names = {family["name"] for family in fonts.families()}
    written: dict[str, dict] = {}
    for at, operation in enumerate(operations):
        try:
            _kind(operation, OWN_OPERATIONS)
            id = operation["style"]
            if id not in looks:
                raise Refused("no_style", id)
            font = operation.get("font")
            if font is not None and font not in theme and font not in names:
                raise Refused("font", font)
        except Refused as refused:
            refused.operation = at
            raise
        given = {key: operation[key] for key in ("font", "size") if key in operation}
        written.setdefault(id, {}).update(given)
    copy = Doc()
    copy.apply_update(doc.get_update())
    before = copy.get_state()
    found = copy.get(styles.STYLES, type=Map)
    with copy.transaction():
        for id, fields in written.items():
            if isinstance(style := found.get(id), Map):
                style.update(fields)
            else:
                found[id] = Map({**looks[id], **fields})
    return Prepared(copy.get_update(before), [], run, _own_scopes)


@dataclass
class TakeBack:
    """A run's change taken back in its room: the text's part by its Yjs ids, keeping what
    others wrote since, its grids' by the patches' inverses, each part only where nobody
    changed it since. What that changed, taken back in turn, does the change again."""

    change: Change
    scopes: Callable[[Doc], list] = _scopes
    guard: bool = True

    @property
    def patches(self) -> list[dict]:
        return [sheets.inverse(patch) for patch in reversed(self.change.grids)]

    def commit(self, doc: Doc, applied: list[dict]) -> Change:
        insertions = deletions = b""
        if self.change.insertions or self.change.deletions:
            item = StackItem(
                doc, IdSet.decode(self.change.deletions), IdSet.decode(self.change.insertions)
            )
            manager = UndoManager(
                scopes=self.scopes(doc), capture_timeout_millis=0, undo_stack=[item]
            )
            if manager.undo():
                redo = manager.redo_stack[-1]
                insertions, deletions = redo.insertions.encode(), redo.deletions.encode()
        change = Change(insertions, deletions, applied)
        if not change:
            raise Refused("undone")
        return change


def take_back(change: Change, scopes: Callable[[Doc], list] | None = None) -> TakeBack:
    return TakeBack(change, scopes or _scopes)


def _blobs(value) -> set[str]:
    """The images and PDFs the operations' nodes and attributes show, by their blobs, a slide's
    background picture among them."""
    if isinstance(value, list):
        return set().union(*map(_blobs, value))
    if isinstance(value, dict):
        found = set().union(*map(_blobs, value.values()))
        background = value.get("background")
        if isinstance(background, dict) and isinstance(background.get("image"), str):
            found.add(background["image"])
        return found | ({value["blob"]} if isinstance(value.get("blob"), str) else set())
    return set()


def _proposal_in(given: object) -> str | None:
    """The first proposal given in the operations, a mark or an attribute holding one, which
    the editor carries with the text it moves but a run never gives: a model would write it in
    another user's name."""
    if isinstance(given, list):
        return next(filter(None, map(_proposal_in, given)), None)
    if not isinstance(given, dict):
        return None
    if given.get("type") in REVIEWED:
        return given["type"]
    attrs = given.get("attrs")
    if isinstance(attrs, dict) and (
        found := next((name for name in PROPOSALS if attrs.get(name) is not None), None)
    ):
        return found
    return next(filter(None, map(_proposal_in, given.values())), None)


def perform(
    tab: Tab,
    operations: list | Callable[[Doc, Sheets], list],
    run: str,
    propose: Proposer | None = None,
) -> Performed:
    """Carries out a run's operations, or those built from the tab's state and grids as the
    room holds them, in the tab's room, opened for it where nobody has it open, and returns
    once the tab's tables are computed again; under a proposer, what they write and take out
    as proposals. An image or a PDF they show must be one of the document's."""
    document = tab.document
    shown = set(DocumentBlob.objects.filter(document=document).values_list("blob_id", flat=True))
    locale = document.locale

    def checked(given: list) -> list:
        if missing := sorted(_blobs(given) - shown):
            raise Refused("blob", missing[0])
        if proposal := _proposal_in(given):
            raise Refused("proposal", f"{proposal} is written by a proposer, never given")
        return given

    def edit(doc: Doc, sheets: Sheets) -> Prepared:
        given = operations(doc, sheets) if callable(operations) else operations
        return carry_out(doc, sheets, checked(given), locale, run, propose)

    if not callable(operations):
        checked(operations)
    return server.perform(tab.room, edit)


def undo(tab: Tab, room: UUID, change: Change) -> Change:
    """Takes back what a run changed in the tab while it was in the room. A tab moved to
    another room since, as restoring a version moves it, no longer holds what the run wrote."""
    if tab.room != room:
        raise Refused("moved", str(tab.pk))
    return server.perform(tab.room, lambda doc, sheets: take_back(change))


def perform_own(
    document: Node, operations: list | Callable[[Doc], list], run: str
) -> Change | None:
    """Carries out a run's operations on the document's own state, or those built from it as
    its room holds it, in its room."""
    build = operations if callable(operations) else lambda _: operations
    return server.perform(
        document.room, lambda doc, sheets: carry_out_own(doc, build(doc), run)
    ).change


def undo_own(document: Node, room: UUID, change: Change) -> Change:
    """Takes back what a run changed in the document's own state while it was in the room,
    which restoring a version moves as it moves the tabs."""
    if document.room != room:
        raise Refused("moved", str(document.pk))
    return server.perform(room, lambda doc, sheets: take_back(change, _own_scopes))


def open_tab(document: Node, title: str = "", parent: Tab | None = None) -> Tab:
    """A new, empty tab, the last of its parent's."""
    last = document.tabs.filter(parent=parent).aggregate(Max("position"))["position__max"]
    position = 0 if last is None else last + 1
    return Tab.objects.create(document=document, parent=parent, title=title, position=position)


@dataclass(frozen=True)
class Copy:
    """A tab's text written again into a state of its own, to open as a new tab under the
    title given: its tables new ones, named apart from the document's, and its blocks as the
    copy has them."""

    tab: Tab
    title: str
    state: bytes
    grids: list[Laid]
    blocks: list[Block]


def copy_of(tab: Tab, title: str) -> Copy:
    content = server.read_grids(tab.room, lambda doc, held: blocks.read(doc, held.grids()))
    doc, held = Doc(), Sheets({})
    doc.apply_update(write(doc, held, blocks.retabled(content)).update)
    laid = [each for _, each in held.tables()]
    taken = Grid.objects.filter(document=tab.document_id).values_list("name", flat=True)
    sheets.apart(laid, taken)
    return Copy(tab, title, doc.get_update(), laid, blocks.read(doc, held.grids()))
