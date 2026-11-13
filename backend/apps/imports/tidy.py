"""An import's direct formatting made into its styles, wherever code can tell what it meant,
without changing how anything shows."""

import operator
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, replace

from pycrdt import Doc

from apps.content import fonts, schema, styles
from apps.content.blocks import Block, Run

from .reading import Imported

# Word's AutoFormat takes a line for a heading only while it is short and does not end as a
# sentence or a list's lead-in does.
LONGEST = 100
ENDED = re.compile(r"[.,;:]$")
LEVELS = 4
KINDS = {"paragraph": "text", "title": "title", "subtitle": "subtitle"}
HEADINGS = ("title", "subtitle", *(f"h{level}" for level in range(1, LEVELS + 1)))
HEADED = set(schema.attrs_of(schema.SPEC["nodes"]["heading"]))


@dataclass(frozen=True)
class Look:
    """How a run of text shows: its family, its size in points, bold, italic, colour and
    kerning."""

    family: str
    size: float
    bold: bool
    italic: bool
    color: str | None
    kerning: bool


@dataclass(frozen=True)
class Heading:
    """A paragraph made a heading: its block type and attributes, and the style it shows."""

    type: str
    attrs: dict
    style: str


def _kind(block: Block) -> str:
    return f"h{block.attrs.get('level', 1)}" if block.type == "heading" else KINDS[block.type]


def _style(block: Block, looks: dict[str, dict]) -> str:
    """The style the block shows: its own where that is of its kind, else its kind's."""
    own, kind = block.attrs.get("style"), _kind(block)
    return own if own in looks and looks[own]["kind"] == kind else kind


def _family(font: str) -> str:
    return fonts.substitute(font) or font


def _look(style: dict, theme: dict[str, str]) -> Look:
    family = styles.family(theme, style["font"])
    return Look(
        family, style["size"], style["bold"], style["italic"], style["color"], style["kerning"]
    )


def _shown(run: Run, style: Look) -> Look:
    marks = run.marks
    font = marks.get("font", {}).get("family")
    return Look(
        _family(font) if font else style.family,
        marks.get("size", {}).get("pt", style.size),
        "strong" in marks or style.bold,
        "em" in marks or style.italic,
        marks.get("color", {}).get("color", style.color),
        marks.get("kerning", {}).get("on", style.kerning),
    )


def _textblocks(content: list[Block]) -> Iterator[Block]:
    for block in content:
        if block.type in (*KINDS, "heading"):
            yield block
        for cell in block.cells:
            yield from _textblocks(cell.blocks)


def _written(block: Block) -> list[Run]:
    return [run for run in block.runs if isinstance(run, Run) and run.text.strip()]


def _text_style(content: list[list[Block]], looks: dict[str, dict]) -> tuple[str | None, float]:
    """The font, as a style names it, and size most of the text shows by hand, where a run's
    marks rather than its style give it; a part not given by hand is None or the style's."""
    weights: Counter[tuple[str | None, float | None]] = Counter()
    for blocks_of_tab in content:
        for block in blocks_of_tab:
            if block.type != "paragraph" or _style(block, looks) != "text":
                continue
            for run in _written(block):
                font = run.marks.get("font", {}).get("family")
                weights[(font, run.marks.get("size", {}).get("pt"))] += len(run.text)
    text = looks["text"]
    if not weights:
        return None, text["size"]
    (font, size), weight = weights.most_common(1)[0]
    if weight * 2 <= weights.total():
        return None, text["size"]
    return (_family(font) if font else None), (size if size is not None else text["size"])


def _named(family: str | None, theme: dict[str, str]) -> str | None:
    """A family as a style names it: the theme's side it is, else one of ours."""
    if family is None:
        return None
    for side in ("text", "headings"):
        if theme[side] == family:
            return side
    return family if any(each["name"] == family for each in fonts.families()) else None


def _emphatic(look: Look, text: Look) -> bool:
    """Whether a line stands out from the text as a heading does: bold or in a colour of its own,
    at the text's size or larger."""
    return look.size >= text.size and (look.bold or look.color != text.color)


def _lines(
    content: list[list[Block]], looks: dict[str, dict], text: Look
) -> Iterator[tuple[Block, Look]]:
    """The paragraphs of text that show throughout in one look standing out from the text, in a
    short line that does not end as a sentence does, each with how it shows."""
    for blocks_of_tab in content:
        for block in blocks_of_tab:
            line = block.text.strip()
            if block.type != "paragraph" or block.attrs.get("list") or not line:
                continue
            if len(line) > LONGEST or ENDED.search(line) or _style(block, looks) != "text":
                continue
            shown = {_shown(run, text) for run in _written(block)}
            if len(shown) == 1 and _emphatic(look := shown.pop(), text):
                yield block, look


def _planned(
    content: list[list[Block]], looks: dict[str, dict], theme: dict[str, str]
) -> tuple[dict[str, Heading], dict[str, Look]]:
    """The lines made headings, by id, and the heading styles no block shows yet with the look of
    their lines. A line that shows exactly as a heading style takes that style. The others go by
    their look, a heading where it is larger than the text or where two lines or more share it:
    a level for each look, the largest first and, of one size, the first to come. A single line
    at the text's size, a heading or emphasis, is no heading."""
    text = _look(looks["text"], theme)
    styled = {id: _look(style, theme) for id, style in looks.items() if style["kind"] in HEADINGS}
    used = {_style(block, looks) for found in content for block in _textblocks(found)}
    found = list(_lines(content, looks, text))
    counts = Counter(look for _, look in found)
    ranked = sorted(
        (
            look
            for look in dict.fromkeys(look for _, look in found)
            if look not in styled.values() and (look.size > text.size or counts[look] > 1)
        ),
        key=lambda look: -look.size,
    )
    levels = {look: min(at + 1, LEVELS) for at, look in enumerate(ranked)}
    restyled: dict[str, Look] = {}
    for look, level in levels.items():
        restyled.setdefault(f"h{level}", look)
    headings: dict[str, Heading] = {}
    for block, look in found:
        style = next((each for each, shows in styled.items() if shows == look), None)
        if style is not None:
            kind = looks[style]["kind"]
            own = {"style": style} if style != kind else {}
            if kind.startswith("h"):
                headings[block.id] = Heading("heading", {"level": int(kind[1:]), **own}, style)
            else:
                headings[block.id] = Heading(kind, own, style)
        elif (level := levels.get(look)) is not None:
            headings[block.id] = Heading("heading", {"level": level}, f"h{level}")
    return headings, {kind: look for kind, look in restyled.items() if kind not in used}


def _fields(look: Look, style: dict, theme: dict[str, str]) -> dict:
    """What a style takes to show as the look, where it does not already."""
    taken = {
        "font": _named(look.family, theme),
        "size": look.size,
        "bold": look.bold,
        "italic": look.italic,
        "color": look.color,
        "kerning": look.kerning,
    }
    return {
        key: value
        for key, value in taken.items()
        if (value is not None or key == "color") and value != style[key]
    }


def _kept(marks: dict, shows: Look) -> dict:
    """The marks that say more than the style of their block shows."""
    font = marks.get("font", {}).get("family")
    again = {
        "font": font is not None and _family(font) == shows.family,
        "size": "size" in marks and marks["size"].get("pt") == shows.size,
        "strong": "strong" in marks and shows.bold,
        "em": "em" in marks and shows.italic,
        "color": "color" in marks and marks["color"].get("color") == shows.color,
        "kerning": "kerning" in marks and marks["kerning"].get("on") == shows.kerning,
    }
    return {name: value for name, value in marks.items() if not again.get(name)}


def _tidied(
    content: list[Block],
    looks: dict[str, dict],
    theme: dict[str, str],
    headings: dict[str, Heading],
) -> list[Block]:
    """The blocks with the planned paragraphs made headings and every mark that only says again
    what its block's style shows taken off, in tables too; the very list where none changes, so
    the cells of a large sheet are not made again."""
    tidied = [_block(block, looks, theme, headings) for block in content]
    return content if all(map(operator.is_, tidied, content, strict=True)) else tidied


def _block(
    block: Block, looks: dict[str, dict], theme: dict[str, str], headings: dict[str, Heading]
) -> Block:
    cells = [
        cell
        if (blocks := _tidied(cell.blocks, looks, theme, headings)) is cell.blocks
        else replace(cell, blocks=blocks)
        for cell in block.cells
    ]
    same = all(map(operator.is_, cells, block.cells, strict=True))
    if block.type not in (*KINDS, "heading"):
        return block if same else replace(block, cells=cells)
    kind, attrs = block.type, dict(block.attrs)
    heading = headings.get(block.id)
    if heading:
        kind = heading.type
        attrs = {
            name: value for name, value in attrs.items() if name in HEADED and name != "style"
        } | heading.attrs
    shows = _look(looks[heading.style if heading else _style(block, looks)], theme)
    runs = [
        run
        if not isinstance(run, Run) or (marks := _kept(run.marks, shows)) == run.marks
        else replace(run, marks=marks)
        for run in block.runs
    ]
    if "endMarks" in attrs:
        attrs["endMarks"] = _kept(attrs["endMarks"], shows)
        if not attrs["endMarks"]:
            del attrs["endMarks"]
    kept = all(map(operator.is_, runs, block.runs, strict=True))
    if same and kept and kind == block.type and attrs == block.attrs:
        return block
    return replace(block, type=kind, attrs=attrs, runs=runs, cells=block.cells if same else cells)


def tidy(imported: Imported, document: Doc | None = None) -> None:
    """Makes the direct formatting of the file's tabs into styles. The text style takes the font
    and size most of its text shows by hand, paragraphs that show as headings become them, a
    heading style no block shows yet taking their look, and marks that only say again what a
    block's style shows come off. Into a document, its own state given, its styles keep their
    looks and a heading keeps its line's in marks. A file of slides keeps its formatting, as a
    heading there starts a slide."""
    if imported.template is not None:
        return
    theme, looks = styles.read(styles.own(imported.theme, imported.styles))
    if document is not None:
        theme, kept = styles.read(document)
        looks |= kept
    content = [tab.blocks for tab in imported.tabs]
    restyled: dict[str, dict] = {}
    if document is None:
        family, size = _text_style(content, looks)
        given = (("font", _named(family, theme)), ("size", size))
        restyled["text"] = {
            key: value for key, value in given if value is not None and value != looks["text"][key]
        }
        looks["text"] |= restyled["text"]
    headings, unused = _planned(content, looks, theme)
    if document is None:
        for kind, look in unused.items():
            restyled[kind] = _fields(look, looks[kind], theme)
            looks[kind] |= restyled[kind]
    for kind, fields in restyled.items():
        if fields:
            imported.styles[kind] = looks[kind]
    for tab in imported.tabs:
        tab.blocks = _tidied(tab.blocks, looks, theme, headings)
