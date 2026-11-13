"""A Word file (docx) as a tab, the styles and the pages of a document: each section after the
first that starts a page, lays out its pages otherwise or names headers and footers of its own
follows a section break. What it holds that we cannot show is counted in the import's report,
never guessed at."""

import copy
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.package import OpcPackage
from docx.oxml import parse_xml
from lxml import etree

from apps.content import fonts, lists, pages
from apps.content import styles as our
from apps.content.blocks import (
    PROPOSED,
    Block,
    Cell,
    Field,
    Grid,
    Note,
    Run,
    in_order,
    new_id,
    utf16,
)
from apps.content.schema import DEEPEST, INDENT_MAX, INDENT_STEP, TAB_MAX

from . import charts, colors, office, vba
from .reading import Imported, Remark, Tab, Thread, Unreadable
from .word import (
    ALIGN,
    CHART,
    DIAGRAM,
    EMU_PER_CM,
    MATH,
    MC,
    PIC,
    TWIPS_PER_CM,
    VO,
    W14,
    W15,
    WP,
    A,
    Level,
    Numbering,
    R,
    Styles,
    V,
    edges_of,
    kerned,
    layered,
    ns,
    number,
    paragraph_layer,
    run_layer,
    shading,
    toggle,
    toggle_of,
    value,
    w,
)

COMMENTS_EXTENDED = "http://schemas.microsoft.com/office/2011/relationships/commentsExtended"
VBA_PROJECT = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"
# Word's single line is about 1.15 of the font size, where a CSS line height counts from 1.
SINGLE = 1.15
LONGEST_QUOTE = 500
LONGEST_BODY = 10_000
BUILT_IN = {
    "text": None,
    "title": "title",
    "subtitle": "subtitle",
    "h1": "heading 1",
    "h2": "heading 2",
    "h3": "heading 3",
    "h4": "heading 4",
}
WRAPPERS = {w("smartTag"), w("customXml"), w("dir"), w("bdo")}
INSERTED = {w("ins"), w("moveTo")}
DELETED = {w("del"), w("moveFrom")}
# Tracked changes of what a proposal cannot hold, taken as Word shows them.
ACCEPTED = [
    w(tag)
    for tag in (
        "tblPrChange",
        "tblGridChange",
        "trPrChange",
        "tcPrChange",
        "cellIns",
        "cellDel",
        "cellMerge",
        "sectPrChange",
        "numberingChange",
    )
]
SECTION = "section"
SECTION_BREAK = "sectionBreak"
PAGE_BREAK = "pageBreak"
RULE = "horizontalRule"
EDGES = {"top", "bottom"}
LISTED = ("list", "format")
# Word's fields a page fills in, as ours; elsewhere a field is the text it last showed.
PAGE_FIELDS = {
    "PAGE": "page",
    "NUMPAGES": "pages",
    "SECTIONPAGES": "pages",
    "TITLE": "title",
    "DATE": "date",
}
FIRST = {"header": "headerFirst", "footer": "footerFirst"}
DEPTH = re.compile(r'\\o\s*"\s*\d\s*-\s*(\d)\s*"')


@dataclass
class Section:
    """A section's pages, the headers and footers it shows and those it names itself, its
    blocks, and whether it goes on from the page before."""

    page: dict
    parts: dict[str, list[Block]]
    named: dict[str, list[Block]]
    blocks: list[Block]
    continuous: bool


@dataclass
class WordField:
    instruction: str = ""
    result: bool = False
    # The field is one of ours, which shows no text of its own.
    ours: bool = False

    @property
    def kind(self) -> str:
        return self.instruction.split()[0].upper() if self.instruction.split() else ""


@dataclass
class Context:
    """What the text being read hangs on: the part whose relationships its ids name, the
    run look of its paragraph's style, the link it is in and the proposals it is part of."""

    part: object
    base: dict
    link: str | None = None
    note: bool = False
    header: bool = False
    cell: bool = False
    proposed: dict = field(default_factory=dict)

    @property
    def blocked(self) -> dict:
        """The proposals a block or a note in this text is part of: inserted or deleted."""
        return {kind: change for kind, change in self.proposed.items() if kind in PROPOSED}


# What a table's look turns on, as a design's switches.
SWITCHES = {
    "firstRow": "header",
    "lastRow": "totals",
    "firstColumn": "firstColumn",
    "lastColumn": "lastColumn",
    "hBand": "rowBands",
    "vBand": "columnBands",
}
LOOK_BITS = {
    "firstRow": 0x20,
    "lastRow": 0x40,
    "firstColumn": 0x80,
    "lastColumn": 0x100,
    "noHBand": 0x200,
    "noVBand": 0x400,
}


def _looked(look) -> set[str]:
    """The parts a w:tblLook turns on, by its flags or the older bits of its value."""
    if look is None:
        return set()
    given = value(look) or ""
    bits = int(given, 16) if re.fullmatch(r"[0-9A-Fa-f]{1,4}", given) else 0
    on = {
        name
        for name, bit in LOOK_BITS.items()
        if (toggle_of(look, name) if look.get(w(name)) is not None else bits & bit)
    }
    return (on - {"noHBand", "noVBand"}) | {
        band for band, off in (("hBand", "noHBand"), ("vBand", "noVBand")) if off not in on
    }


@dataclass
class Edge:
    """The last paragraph's borders, drawn where its blocks end in the list they went to, and
    whether a line below it is the last of them."""

    out: list
    end: int
    drawn: dict
    below: bool


@dataclass
class PageBreak:
    """A page break in a paragraph's text, where it falls: its offset in UTF-16 units, the
    number of the paragraph's images before it and, once taken out, of its runs."""

    offset: int
    after: int
    run: int = 0
    proposed: dict = field(default_factory=dict)


@dataclass
class Text:
    """The runs of one block, or of a note where `id` is None, as they are read; its length
    in UTF-16 units, and the blocks that follow it: its images and text boxes."""

    id: str | None
    runs: list[Run | Note | Field | PageBreak] = field(default_factory=list)
    length: int = 0
    after: list[Block] = field(default_factory=list)
    toc: bool = False

    def add(self, chars: str, marks: dict) -> None:
        last = self.runs[-1] if self.runs else None
        if isinstance(last, Run) and last.marks == marks:
            last.text += chars
        else:
            self.runs.append(Run(chars, marks))
        self.length += utf16(chars)

    @property
    def plain(self) -> str:
        return "".join(run.text for run in self.runs if isinstance(run, Run))


def read(path: Path, locale: str, formats: dict[str, list[dict]] | None = None) -> Imported:
    """The file's content, its lists sharing the formats a document already has and its
    charts' tables typed as the locale types them."""
    package = office.opened(path)
    try:
        return Reader(package, formats or {}, locale).read()
    except etree.LxmlError as error:
        raise Unreadable from error


def _proposed(blocks: list[Block], proposed: dict) -> None:
    """The blocks a picture made, part of the proposals its run is: an image, a chart and the
    table of its data, all its rows."""
    for block in blocks if proposed else []:
        if block.type == "table" and block.grid:
            block.attrs["proposedRows"] = {row: dict(proposed) for row in block.grid.rows}
        elif block.type in ("image", "chart"):
            block.attrs |= proposed


def _taken_breaks(text: Text) -> list[PageBreak]:
    """The page breaks of a paragraph's text, taken out of its runs."""
    runs: list[Run | Note | Field] = []
    breaks: list[PageBreak] = []
    for run in text.runs:
        if isinstance(run, PageBreak):
            breaks.append(replace(run, run=len(runs)))
        else:
            runs.append(run)
    text.runs = runs
    return breaks


def _unlisted(attrs: dict) -> dict:
    return {key: item for key, item in attrs.items() if key not in LISTED}


def _tabs(look: dict) -> list[dict]:
    """A paragraph's tab stops in cm from the margin, as Word measures them; a stop before the
    margin is Word's alone."""
    stops = []
    for position, stop in sorted((look.get("tabs") or {}).items()):
        at = round(position / TWIPS_PER_CM, 2)
        if stop is None or not 0 <= at <= TAB_MAX:
            continue
        kind, leader = stop
        stops.append({"at": at, "kind": kind, **({"leader": leader} if leader else {})})
    return stops


def _drawn(look: dict) -> dict:
    return {side: line for side, line in (look.get("borders") or {}).items() if line is not None}


def _indents(look: dict) -> dict:
    """A paragraph's own indents in cm, its first line never before the text's left edge."""
    left = min(max(look.get("indent") or 0, 0), INDENT_MAX)
    lengths = {
        "indent": left,
        "firstLine": min(max(look.get("first") or 0, -left), INDENT_MAX),
        "right": min(max(look.get("right") or 0, 0), INDENT_MAX),
    }
    return {name: round(length, 2) for name, length in lengths.items() if round(length, 2)}


def _sliced(text: str, start: int, end: int | None = None) -> str:
    units = text.encode("utf-16-le")
    return units[start * 2 : None if end is None else end * 2].decode("utf-16-le", "replace")


def _past(text: str, offset: int) -> int:
    """The offset after the character at an offset, which a surrogate pair takes two of."""
    unit = text.encode("utf-16-le")[offset * 2 : offset * 2 + 2]
    high = len(unit) == 2 and 0xD800 <= int.from_bytes(unit, "little") <= 0xDBFF
    return offset + (2 if high else 1)


def _shows_any(block: Block) -> bool:
    if block.type == "table":
        return any(_shows_any(inner) for cell in block.cells for inner in cell.blocks)
    if block.type not in ("paragraph", "heading"):
        return True
    return bool(block.text.strip()) or any(not isinstance(run, Run) for run in block.runs)


def signature(parts: dict[str, list[Block]]) -> dict:
    """What headers and footers say, which two sections' parts that Word keeps apart can
    share."""

    def said(content: list[Block]) -> list:
        return [
            (
                block.type,
                block.attrs.get("blob"),
                "".join(
                    run.text if isinstance(run, Run) else f"\0{run.kind}" for run in block.runs
                ),
                [said(cell.blocks) for cell in block.cells],
            )
            for block in content
        ]

    return {name: said(content) for name, content in parts.items()}


def _date(text: str | None) -> datetime | None:
    try:
        found = datetime.fromisoformat(text) if text else None
    except ValueError:
        return None
    return found.replace(tzinfo=UTC) if found and found.tzinfo is None else found


def _length(style: str | None, name: str) -> float | None:
    """A length in a VML style, in cm."""
    found = re.search(rf"(?:^|;)\s*{name}\s*:\s*([\d.]+)\s*(pt|in|cm|mm|px)?", style or "")
    if not found or number(found[1]) is None:
        return None
    per_cm = {"pt": 72 / 2.54, "in": 1 / 2.54, "cm": 1, "mm": 10, "px": 96 / 2.54}
    return float(found[1]) / per_cm[found[2] or "px"]


class Reader:
    def __init__(self, package: OpcPackage, formats: dict[str, list[dict]], locale: str):
        self.locale = locale
        self.part = package.main_document_part
        self.root = parse_xml(self.part.blob)
        self.word_theme = self._theme()
        self.styles = Styles(self._xml(RT.STYLES), self.word_theme)
        self.numbering = Numbering(self._xml(RT.NUMBERING), self.styles)
        self.lost: Counter[str] = Counter()
        self.accepted = sum(1 for _ in self.root.iter(*ACCEPTED))
        self.revision: tuple[str, str | None, str] | None = None
        self.fonts: set[str] = set()
        self.images: dict[str, bytes] = {}
        self.fields: list[WordField] = []
        self.reading = (self.part, False)
        self.contents: int | None = None
        self.edge: Edge | None = None
        self.inherited: dict[str, list[Block]] = {}
        self.headers: dict[str, list[Block]] = {}
        self.even = toggle(self._xml_of(RT.SETTINGS, w("evenAndOddHeaders"))) is True
        self.threads: dict[str, Thread] = {}
        self.pending: list[str] = []
        self.last: tuple[str, int] | None = None
        self.order: list[tuple[str, str]] = []
        self.word_numbers: dict[str, int] = {}
        self.known = formats
        self.formats: dict[str, list[dict]] = {}
        self.list_formats: dict[str, tuple[str | None, set[int]]] = {}
        self.roots: dict[str, object] = {}
        self.notes = {
            "foot": (self._part(RT.FOOTNOTES), w("footnote")),
            "end": (self._part(RT.ENDNOTES), w("endnote")),
        }
        self.sized: dict[str, float] = {}
        self.theme = self._our_theme()
        self.custom: dict[str, dict] = {}
        self.assigned: dict[str | None, str | None] = {}
        self.adopted = self._adopted()
        self.built_in = {kind: self._fields(self._source(kind), kind) for kind in BUILT_IN}
        for kind in ("text", "title", "subtitle"):
            self.built_in[kind].update(numbering="", prefix="", suffix="", nested=False)

    def read(self) -> Imported:
        body = self.root.find(w("body"))
        if body is None:
            raise Unreadable
        self._comments()
        content: list[Block] = []
        self._content(body, content)
        sections, current = [], []
        for block in content:
            if block.type == SECTION:
                sections.append(self._section(block.attrs["element"], current))
                current = []
            else:
                current.append(block)
        sections.append(self._section(body.find(w("sectPr")), current))
        page, parts, tabs = self._sectioned(sections)
        for tab in tabs:
            office.numbered(tab.blocks, self.word_numbers, self.lost)
        threads = self._placed()
        project = self._part(VBA_PROJECT)
        self.lost["macros"] += project is not None
        styles = {**self.built_in, **self.custom}
        report = {
            "fonts": fonts.substituted(self.fonts),
            "lost": {key: count for key, count in sorted(self.lost.items()) if count},
            "accepted": self.accepted,
            **({"macros": vba.source(project.blob)} if project is not None else {}),
        }
        return Imported(
            tabs,
            page,
            parts,
            self.theme,
            styles,
            self.images,
            threads,
            report,
            self.formats,
        )

    # The package

    def _part(self, reltype: str, of=None):
        try:
            return (of or self.part).part_related_by(reltype)
        except KeyError:
            return None

    def _xml(self, reltype: str, of=None):
        part = self._part(reltype, of)
        return None if part is None else parse_xml(part.blob)

    def _theme(self) -> dict[str, str]:
        root = self._xml(RT.THEME)
        found: dict[str, str] = {}
        if root is None:
            return found
        for side, tag in (("headings", "majorFont"), ("text", "minorFont")):
            latin = root.find(f".//{ns(A, tag)}/{ns(A, 'latin')}")
            if latin is not None and latin.get("typeface"):
                found[side] = latin.get("typeface")
        return found

    def _xml_of(self, reltype: str, tag: str):
        root = self._xml(reltype)
        return None if root is None else root.find(tag)

    # Sections, pages, headers and footers

    def _section(self, element, content: list[Block]) -> Section:
        """The section, its images sized as shares of its own text width."""
        page, (parts, named) = self._page(element), self._parts(element)
        across = page["width"] - page["left"] - page["right"]
        if across <= 0:
            across = pages.DEFAULT["width"] - pages.DEFAULT["left"] - pages.DEFAULT["right"]
        for block in in_order([*content, *(block for part in parts.values() for block in part)]):
            if (width := self.sized.pop(block.id, None)) is not None:
                block.attrs["width"] = max(5, min(100, round(width / across * 100)))
        kind = element.find(w("type")) if element is not None else None
        return Section(page, parts, named, content, value(kind, "val") == "continuous")

    @staticmethod
    def _page(element) -> dict:
        def cm(found, name: str, fallback: float) -> float:
            twips = number(value(found, name)) if found is not None else None
            return round(abs(twips) / TWIPS_PER_CM, 2) if twips is not None else fallback

        size = element.find(w("pgSz")) if element is not None else None
        margins = element.find(w("pgMar")) if element is not None else None
        numbered = element.find(w("pgNumType")) if element is not None else None
        width, height = (
            cm(size, "w", pages.DEFAULT["width"]),
            cm(size, "h", pages.DEFAULT["height"]),
        )
        if value(size, "orient") == "landscape" and width < height:
            width, height = height, width
        start = number(value(numbered, "start")) if numbered is not None else None
        return {
            "width": width,
            "height": height,
            **{
                side: cm(margins, side, pages.DEFAULT[side])
                for side in ("top", "right", "bottom", "left")
            },
            "header": cm(margins, "header", pages.DEFAULT["header"]),
            "footer": cm(margins, "footer", pages.DEFAULT["footer"]),
            "firstPage": element is not None and toggle(element.find(w("titlePg"))) is True,
            "start": int(start) if start is not None else None,
        }

    def _parts(self, element) -> tuple[dict[str, list[Block]], dict[str, list[Block]]]:
        """The headers and footers the section shows, one it does not name the section's
        before, and those it names otherwise than the section before shows them."""
        before = dict(self.inherited)
        named: dict[str, list[Block]] = {}
        for reference in element if element is not None else []:
            side = "header" if reference.tag == w("headerReference") else None
            side = "footer" if reference.tag == w("footerReference") else side
            if side is None:
                continue
            kind = reference.get(w("type")) or "default"
            content = self._part_blocks(reference.get(ns(R, "id")))
            if kind == "even":
                self.lost["evenHeaders"] += self.even and bool(content)
            else:
                name = side if kind == "default" else FIRST[side]
                self.inherited[name] = content
                if signature({name: content}) != signature({name: before.get(name, [])}):
                    named[name] = content
        first = element is not None and toggle(element.find(w("titlePg"))) is True
        shown = {
            name: content
            for name, content in self.inherited.items()
            if content and (first or name in ("header", "footer"))
        }
        return shown, named

    def _part_blocks(self, rid: str | None) -> list[Block]:
        relationship = self.part.rels.get(rid) if rid else None
        if relationship is None or relationship.is_external:
            return []
        if rid not in self.headers:
            part = relationship.target_part
            saved = self.reading, self.fields
            self.reading, self.fields = (part, True), []
            content: list[Block] = []
            root = parse_xml(part.blob)
            self.accepted += sum(1 for _ in root.iter(*ACCEPTED))
            self._content(root, content)
            self.reading, self.fields = saved
            office.numbered(content, self.word_numbers, self.lost)
            self.headers[rid] = content if any(map(_shows_any, content)) else []
        return self.headers[rid]

    def _sectioned(self, sections: list[Section]) -> tuple[dict, dict, list[Tab]]:
        """The document's pages and headers and footers, from its first section, and its tab:
        a section that goes on from the page before with the same pages and headers and
        footers goes on in the text, any other follows a section break, which keeps what the
        section sets itself."""
        sections = [section for section in sections if section.blocks] or sections[-1:]
        content = list(sections[0].blocks)
        kept: dict[str, tuple[dict | None, dict[str, list[Block]]]] = {}
        for before, section in pairwise(sections):
            page = section.page if section.page != {**before.page, "start": None} else None
            if section.continuous and page is None and not section.named:
                content.extend(section.blocks)
                continue
            mark = Block(SECTION_BREAK)
            kept[mark.id] = (page, section.named)
            content += [mark, *section.blocks]
        if not content:
            content.append(Block("paragraph"))
        return sections[0].page, sections[0].parts, [Tab("", content, sections=kept)]

    # Styles

    def _our_theme(self) -> dict[str, str]:
        default = self.styles.paragraph_style(None)
        heading = self.styles.named("heading 1")
        theme = dict(our.TEMPLATE[our.THEME])
        for side, style in (("text", default), ("headings", heading or default)):
            named = self.word_theme.get(side) or self._font_of(style)
            if named and (shown := fonts.substitute(named)):
                theme[side] = shown
        return theme

    def _font_of(self, style: str | None) -> str | None:
        font = self.styles.paragraph_look(style)[1].get("font")
        return font[0] if font else None

    def _source(self, kind: str) -> str | None:
        """The Word style one of our built-in styles takes its look from."""
        if BUILT_IN[kind] is None:
            return self.styles.paragraph_style(None)
        return self.styles.named(BUILT_IN[kind])

    def _style_level(self, style: str | None) -> Level | None:
        look = self.styles.paragraph_look(style)[0]
        if look.get("num"):
            return self.numbering.level(look["num"], look.get("ilvl", 0))
        if style and (tied := self.numbering.of_style(style)):
            return self.numbering.level(*tied)
        return None

    def _adopted(self) -> dict[str, Level]:
        """The numbering most paragraphs of a heading style carry, and no other, where the
        style numbers none itself and no paragraph without it comes before one with it, which
        becomes the style's: ours numbers headings by style alone, and so counts each one."""
        body = self.root.find(w("body"))
        found: dict[str, list[tuple]] = {}
        for ppr in body.iter(w("pPr")) if body is not None else ():
            style = self.styles.paragraph_style(value(ppr.find(w("pStyle"))))
            if ppr.getparent().tag != w("p") or style is None:
                continue
            if not self._kind(style)[0].startswith("h") or self._style_level(style):
                continue
            own = paragraph_layer(ppr)
            found.setdefault(style, []).append((own.get("num"), own.get("ilvl", 0)))
        adopted = {}
        for style, numbers in found.items():
            numbered = [at for at, number in enumerate(numbers) if number[0]]
            if not numbered or len(numbered) * 2 <= len(numbers):
                continue
            if numbered[-1] + 1 != len(numbered) or len({numbers[at] for at in numbered}) > 1:
                continue
            level = self.numbering.level(*numbers[0])
            if level is not None and level.shown and not level.bulleted:
                adopted[style] = level
        return adopted

    def _numbers_by_style(self, style: str | None, kind: str) -> Level | None:
        """The numbering a style shows on its blocks: a heading's, or words and a number,
        as articles count through a contract."""
        level = self._style_level(style) or (self.adopted.get(style) if style else None)
        if level is None or not level.shown or level.bulleted:
            return None
        return level if kind.startswith("h") or (kind == "text" and level.worded) else None

    def _font_field(self, font: tuple[str, str | None] | None, kind: str) -> str:
        sides = ("text", "headings") if kind in ("text", "subtitle") else ("headings", "text")
        if font is None:
            return sides[0]
        name, side = font
        if side:
            return side
        shown = fonts.substitute(name)
        for each in sides:
            if shown and shown == self.theme[each]:
                return each
        return shown or "text"

    def _fields(self, style: str | None, kind: str) -> dict:
        if style is None and BUILT_IN.get(kind):
            fields = copy.deepcopy(our.TEMPLATE[our.STYLES][kind])
            return fields | {"kerning": kerned(self.styles.run_defaults | {"size": fields["size"]})}
        paragraph, run = self.styles.paragraph_look(style)
        size = run.get("size", 10.0)
        fields = {
            "kind": kind,
            "name": "",
            "font": self._font_field(run.get("font"), kind),
            "size": size,
            "bold": bool(run.get("bold")),
            "italic": bool(run.get("italic")),
            "color": colors.text_color(run.get("color")),
            "align": ALIGN.get(paragraph.get("align") or "left"),
            "before": round(paragraph.get("before", 0.0), 1),
            "after": round(paragraph.get("after", 0.0), 1),
            "line": self._line(paragraph.get("line"), size),
            "numbering": "",
            "prefix": "",
            "suffix": "",
            "nested": False,
            "kerning": kerned(run),
        }
        if (level := self._numbers_by_style(style, kind)) is not None:
            before, after, nested = level.affixes
            fields.update(
                numbering=level.numbering,
                prefix=before,
                suffix=after,
                nested=nested and kind.startswith("h"),
            )
        return fields

    @staticmethod
    def _line(spacing: tuple[float, str] | None, size: float) -> float:
        if spacing is None:
            return SINGLE
        amount, rule = spacing
        found = amount / 240 * SINGLE if rule == "auto" else amount / 20 / size
        return round(min(max(found, 0.5), 5.0), 2)

    def _kind(self, style: str | None) -> tuple[str, str, int]:
        """Our kind of a paragraph style, the block type it makes and its heading level."""
        kind, level = self.styles.kind(style)
        if kind == "heading":
            level = min(level, 4)
            return f"h{level}", "heading", level
        return kind, ("paragraph" if kind == "text" else kind), 0

    def _custom_id(self, style: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_-]", "", style)[:28] or "style"
        found, suffix = base, 1
        while found in BUILT_IN or found in self.custom:
            suffix += 1
            found = f"{base}-{suffix}"
        return found

    def _ours(self, style: str | None, kind: str) -> str | None:
        """Our custom style for a Word style that looks unlike the built-in of its kind."""
        if style not in self.assigned:
            fields = self._fields(style, kind)
            different = {key: item for key, item in fields.items() if key != "name"} != {
                key: item for key, item in self.built_in[kind].items() if key != "name"
            }
            custom = None
            if style is not None and style != self._source(kind) and different:
                custom = self._custom_id(style)
                self.custom[custom] = {**fields, "name": self.styles.name(style)}
            self.assigned[style] = custom
        return self.assigned[style]

    # Body

    def _content(self, parent, out: list[Block], cell: bool = False) -> None:
        for child in parent:
            tag = child.tag
            if tag == w("p"):
                self._paragraph(child, out, cell)
            elif tag == w("tbl"):
                if cell:
                    self.lost["nestedTables"] += 1
                    for inner in self._descend(child, w("tr")):
                        for each in self._descend(inner, w("tc")):
                            self._content(each, out, cell=True)
                else:
                    self._table(child, out)
            elif tag == w("sdt"):
                if (content := child.find(w("sdtContent"))) is not None:
                    self._content(content, out, cell)
            elif tag == w("customXml"):
                self._content(child, out, cell)
            elif tag == ns(MC, "AlternateContent"):
                self._content(self._chosen(child), out, cell)
            elif tag in (w("commentRangeStart"), w("commentRangeEnd")):
                self._comment_mark(child)
            elif tag == w("altChunk"):
                self.lost["objects"] += 1

    @staticmethod
    def _chosen(alternate):
        found = alternate.find(ns(MC, "Choice"))
        if found is None:
            found = alternate.find(ns(MC, "Fallback"))
        return [] if found is None else found

    @staticmethod
    def _descend(parent, tag: str):
        """The children of a tag, also those wrapped in content controls and custom XML."""
        for child in parent:
            if child.tag == tag:
                yield child
            elif child.tag == w("sdt"):
                if (content := child.find(w("sdtContent"))) is not None:
                    yield from Reader._descend(content, tag)
            elif child.tag == w("customXml"):
                yield from Reader._descend(child, tag)

    def _paragraph(self, p, out: list[Block], cell: bool = False) -> None:
        ppr = p.find(w("pPr"))
        self._paragraph_blocks(p, ppr, out, cell)
        section = ppr.find(w("sectPr")) if ppr is not None else None
        if section is not None and not cell and not self.reading[1]:
            out.append(Block(SECTION, attrs={"element": section}))

    def _paragraph_blocks(self, p, ppr, out: list[Block], cell: bool) -> None:
        named = value(ppr.find(w("pStyle"))) if ppr is not None else None
        style = self.styles.paragraph_style(named)
        styled, base = self.styles.paragraph_look(style)
        look = layered(styled, paragraph_layer(ppr))
        drawn = _drawn(look)
        edge, self.edge = self.edge, None
        text = Text(new_id())
        part, header = self.reading
        self._inline(p, text, Context(part, base, header=header, cell=cell))
        end = self._end(ppr, cell)
        breaks = _taken_breaks(text)
        if self.contents is not None:
            out.append(Block("contents", attrs={"depth": self.contents}))
            self.contents = None
        if look.get("pageBefore") and not header:
            if cell:
                self.lost["pageBreaks"] += 1
            elif out and out[-1].type not in (SECTION, PAGE_BREAK):
                out.append(Block(PAGE_BREAK))
        name = self.styles.name(style).lower() if style else ""
        if re.fullmatch(r"toc [1-9]", name) or (text.toc and not text.runs):
            self.lost["pageBreaks"] += len(breaks)
            out.extend(text.after)
            return
        lone = all(isinstance(run, Run) for run in text.runs) and not text.plain.strip()
        # An empty paragraph drawing one line, as Word's AutoFormat makes of ---, is the line.
        if lone and not text.after and not breaks and len(drawn) == 1 and {*drawn} <= EDGES:
            self._edged(out, drawn, edge, cell, lambda: None)
            return
        block_type, attrs = self._shaped(ppr, text.id)
        change = ppr.find(f"{w('pPrChange')}") if ppr is not None else None
        if change is not None and header:
            self.accepted += 1
        elif change is not None:
            before_type, before = self._shaped(change.find(w("pPr")), None)
            if (before_type, before) != (block_type, attrs):
                before = {"type": before_type, "attrs": before}
                attrs["formatting"] = {**self._change(change), "before": before}
        attrs |= end
        align = ALIGN.get(look.get("align") or "left")
        for image in text.after:
            if image.type == "image" and align in ("center", "right"):
                image.attrs["align"] = align
        if text.after and lone:
            self._edged(out, drawn, edge, cell, lambda: self._broken(out, None, text, breaks))
            return
        if not text.runs and not breaks and ppr is not None:
            if marks := self._marks(self._run_look(ppr.find(w("rPr")), base), base, None):
                attrs["endMarks"] = marks
        block = Block(block_type, text.id, attrs)
        self._edged(
            out,
            drawn,
            edge,
            cell,
            lambda: self._broken(out, block, text, breaks, ordered=not header),
        )

    def _edged(self, out: list[Block], drawn: dict, edge: Edge | None, cell: bool, emit) -> None:
        """A paragraph's blocks between the lines its borders draw, as Word draws them for
        paragraphs of the same borders one after another: above the first, between them where
        it draws that, below the last. A cell holds no line of ours, nor is there one at a
        paragraph's side."""
        if drawn and cell:
            self.lost["paragraphBorders"] += 1
            emit()
            return
        if {*drawn} - EDGES - {"between"}:
            self.lost["paragraphBorders"] += 1
        grouped = edge is not None and edge.out is out and edge.end == len(out)
        grouped = grouped and bool(drawn) and edge.drawn == drawn
        if grouped and edge.below:
            out.pop()
        if ("between" if grouped else "top") in drawn:
            out.append(Block(RULE))
        emit()
        if "bottom" in drawn:
            out.append(Block(RULE))
        if drawn:
            self.edge = Edge(out, len(out), drawn, "bottom" in drawn)

    def _shaped(self, ppr, block: str | None) -> tuple[str, dict]:
        """The block type and attributes a paragraph's properties make; without a block, those a
        formatting change replaced."""
        own = paragraph_layer(ppr)
        named = value(ppr.find(w("pStyle"))) if ppr is not None else None
        style = self.styles.paragraph_style(named)
        styled, _ = self.styles.paragraph_look(style)
        look = layered(styled, own)
        name = self.styles.name(style).lower() if style else ""
        # The contents' own heading is a line above them, not one of the headings they list.
        kind, block_type, level = (
            ("text", "paragraph", 0) if name == "toc heading" else self._kind(style)
        )
        attrs: dict = {"level": level} if block_type == "heading" else {}
        if custom := self._ours(style, kind):
            attrs["style"] = custom
        align = ALIGN.get(look.get("align") or "left")
        if "align" in own and align != ALIGN.get(styled.get("align") or "left"):
            attrs["align"] = align or "left"
        if not self._listed(look, style, kind, custom, block, attrs):
            attrs.update(_indents(look))
        if tabs := _tabs(look):
            attrs["tabs"] = tabs
        return block_type, attrs

    def _end(self, ppr, cell: bool) -> dict:
        """What is proposed for a paragraph's end, Word's paragraph mark, which Word does not
        track at the end of a cell."""
        mark = ppr.find(w("rPr")) if ppr is not None else None
        changes = list(mark) if mark is not None else []
        proposed = {}
        for kind, tags in (("insertion", INSERTED), ("deletion", DELETED)):
            found = next((each for each in changes if each.tag in tags), None)
            if found is None:
                continue
            if self.reading[1]:
                self.accepted += 1
            else:
                proposed[kind] = self._change(found)
        if not proposed and not cell:
            self.revision = None
        return proposed

    def _change(self, element) -> dict:
        """A tracked change as a part of a proposal: its author and date, and the proposal of
        the changes just before it by the same author at the same time, which Word shows as one
        change."""
        author = " ".join((element.get(w("author")) or "").split())[:200] or "Word"
        date = element.get(w("date"))
        try:
            datetime.fromisoformat(date or "")
        except ValueError:
            date = None
        if self.revision is None or self.revision[:2] != (author, date):
            self.revision = (author, date, new_id())
        return {"id": self.revision[2], "author": author, **({"date": date} if date else {})}

    def _broken(
        self,
        out: list[Block],
        block: Block | None,
        text: Text,
        breaks: list[PageBreak],
        ordered: bool = False,
    ) -> None:
        """The paragraph's block, or none, and its images, with a page break block at each of
        its page breaks. The text after one is a paragraph of its own, outside the list the
        paragraph is in, and the comments anchored there move with it."""
        cuts = [
            PageBreak(0, 0, 0),
            *breaks,
            PageBreak(text.length, len(text.after), len(text.runs)),
        ]
        pieces = [
            (start, text.runs[start.run : end.run], text.after[start.after : end.after])
            for start, end in zip(cuts, cuts[1:], strict=False)
        ]
        shown = [at for at, (_, runs, _) in enumerate(pieces) if block and (runs or not breaks)]
        names = {at: text.id if order == 0 else new_id() for order, at in enumerate(shown)}
        if breaks and shown:
            self._moved(text.id, [(names[at], pieces[at][0].offset) for at in shown])
        for at, (_, runs, after) in enumerate(pieces):
            if at:
                out.append(Block(PAGE_BREAK, attrs=dict(cuts[at].proposed)))
            if block and at in names:
                piece = names[at]
                attrs = block.attrs if piece == text.id else _unlisted(block.attrs)
                # The paragraph's end is the last piece's.
                if at != shown[-1]:
                    attrs = {key: item for key, item in attrs.items() if key not in PROPOSED}
                out.append(Block(block.type, piece, attrs, runs))
                if ordered:
                    plain = "".join(run.text for run in runs if isinstance(run, Run))
                    self.order.append((piece, plain))
            out.extend(after)

    def _moved(self, block: str, pieces: list[tuple[str, int]]) -> None:
        """Comment anchors in a block split at page breaks, into the piece each falls in."""

        def moved(at: tuple[str, int] | None) -> tuple[str, int] | None:
            if at is None or at[0] != block:
                return at
            piece, start = next(
                (piece for piece in reversed(pieces) if piece[1] <= at[1]), pieces[0]
            )
            return (piece, at[1] - start)

        for thread in self.threads.values():
            thread.start, thread.end = moved(thread.start), moved(thread.end)
        self.last = moved(self.last)

    def _listed(
        self,
        look: dict,
        style: str | None,
        kind: str,
        custom: str | None,
        block: str | None,
        attrs: dict,
    ) -> bool:
        """A paragraph's list, and Word's number for it, by its numbering; a heading's
        number, or one with words, is its style's. Whether the paragraph is numbered, which
        lays it out as its number does rather than by its own indents. Without a block, the
        properties a formatting change replaced, which neither count nor lose a number."""
        level, counted = None, None
        if look.get("num"):
            ilvl = look.get("ilvl", 0)
            level = self.numbering.level(look["num"], ilvl)
            counted = self.numbering.count(look["num"], ilvl) if level and block else None
        by_style = self._numbers_by_style(style, kind)
        if kind.startswith("h") or (custom and by_style is not None):
            mine = level if level is not None and level.shown else None
            if "num" not in look and style and (tied := self.numbering.of_style(style)):
                mine = self.numbering.level(*tied)
            if block and (
                (mine is None) != (by_style is None)
                or (
                    mine
                    and by_style
                    and (mine.format, mine.text) != (by_style.format, by_style.text)
                )
            ):
                self.lost["listNumbers"] += 1
            return by_style is not None
        if level is None or not level.shown:
            return False
        if level.bulleted:
            attrs["list"] = "bullet"
        else:
            attrs["list"] = "number"
            if counted is not None:
                self.word_numbers[block] = counted
        ilvl = min(look.get("ilvl", 0), DEEPEST)
        format, unshown = self._list_format(look["num"])
        if format is not None:
            attrs["format"] = format
        self.lost["listFormats"] += bool(block) and ilvl in unshown
        if ilvl > 0:
            attrs["indent"] = ilvl * INDENT_STEP
        return True

    def _list_format(self, num: str) -> tuple[str | None, set[int]]:
        """The format a Word list shows its levels in, kept once however many lists show it
        and none where it is the standard one, and the levels it cannot show as Word does."""
        if num in self.list_formats:
            return self.list_formats[num]
        levels = [self.numbering.level(num, ilvl) for ilvl in range(lists.LEVELS)]
        format, unshown = [], set()
        for ilvl, level in enumerate(levels):
            shown = level is not None and level.shown
            form = level.listed(ilvl, levels[:ilvl]) if shown else None
            if shown and form is None:
                unshown.add(ilvl)
            kind = "bullet" if shown and level.bulleted else "number"
            format.append(form or lists.standard(kind, ilvl))
        id = None
        if not lists.is_standard(format):
            had = {**self.known, **self.formats}
            id = next((id for id, known in had.items() if known == format), None)
            if id is None:
                id = new_id()
                self.formats[id] = format
        self.list_formats[num] = (id, unshown)
        return id, unshown

    # Tables

    def _table(self, tbl, out: list[Block]) -> None:
        grid = [
            number(value(col, "w")) or 0.0 for col in tbl.findall(f"{w('tblGrid')}/{w('gridCol')}")
        ]
        rows = list(self._descend(tbl, w("tr")))
        shapes = []
        tall: dict[int, float] = {}
        changed: dict[int, list] = {}
        header = 0
        for y, tr in enumerate(rows):
            trpr = tr.find(w("trPr"))
            if header == y and trpr is not None and toggle(trpr.find(w("tblHeader"))):
                header += 1
            for each in trpr if trpr is not None else []:
                if each.tag in INSERTED | DELETED and self.reading[1]:
                    self.accepted += 1
                elif each.tag in INSERTED | DELETED:
                    changed.setdefault(y, []).append(each)
            skipped = trpr.find(w("gridBefore")) if trpr is not None else None
            before = int(number(value(skipped)) or 0)
            # An exact height is kept as the least, since a row here never cuts its text.
            height = trpr.find(w("trHeight")) if trpr is not None else None
            twips = number(value(height))
            if twips and twips > 0 and height.get(w("hRule")) != "auto":
                tall[y] = round(twips / 20, 1)
            spans = []
            for tc in self._descend(tr, w("tc")):
                tcpr = tc.find(w("tcPr"))
                span = number(value(tcpr.find(w("gridSpan")) if tcpr is not None else None))
                spans.append((tc, max(int(span or 1), 1)))
            shapes.append((before, spans))
        cols = max(
            [len(grid), *(before + sum(each for _, each in spans) for before, spans in shapes)]
        )
        if not rows or not cols:
            return
        row_ids, col_ids = [new_id() for _ in rows], [new_id() for _ in range(cols)]
        known = [width for width in grid if width > 0]
        fallback = sum(known) / len(known) if known else 1.0
        widths = [(grid[x] if x < len(grid) and grid[x] > 0 else fallback) for x in range(cols)]
        total = sum(widths)
        percent = {
            col: round(width / total * 100, 1) for col, width in zip(col_ids, widths, strict=True)
        }
        design = self._design(tbl.find(w("tblPr")))
        spacing = (design or {}).get("spacing", 0) * 20
        self.lost["tableStyles"] += any(
            (number(value(gap, "w")) or 0) != spacing
            for tr in rows
            for gap in tr.iterfind(f"{w('trPr')}/{w('tblCellSpacing')}")
        )
        attrs = {"widths": percent, **({"designs": [design]} if design else {})}
        if tall:
            attrs["heights"] = {row_ids[y]: height for y, height in tall.items()}
        if header:
            attrs["frozen"] = row_ids[header - 1]
        table = Block("table", attrs=attrs, grid=Grid(row_ids, col_ids))
        open: dict[int, tuple[Cell, int]] = {}
        proposed: dict[str, dict] = {}
        for y, (before, spans) in enumerate(shapes):
            if y not in changed:
                self.revision = None
            for each in changed.get(y, []):
                kind = "insertion" if each.tag in INSERTED else "deletion"
                proposed.setdefault(row_ids[y], {})[kind] = self._change(each)
            x = before
            for tc, span in spans:
                tcpr = tc.find(w("tcPr"))
                merge = tcpr.find(w("vMerge")) if tcpr is not None else None
                right = col_ids[min(x + span, cols) - 1]
                if merge is not None and (value(merge) or "continue") == "continue" and x in open:
                    origin, wide = open[x]
                    origin.to = f"{row_ids[y]}:{col_ids[min(x + wide, cols) - 1]}"
                else:
                    blocks: list[Block] = []
                    self._content(tc, blocks, cell=True)
                    cell = Cell(
                        row_ids[y],
                        col_ids[x],
                        blocks,
                        fill=self._cell_fill(tcpr),
                        edges=self._cell_edges(tcpr),
                    )
                    if span > 1:
                        cell.to = f"{row_ids[y]}:{right}"
                    table.cells.append(cell)
                    if merge is not None and value(merge) == "restart":
                        open[x] = (cell, span)
                    else:
                        open.pop(x, None)
                x += span
        table.cells = [
            cell
            for cell in table.cells
            if cell.to or cell.fill or cell.edges or any(self._shows(each) for each in cell.blocks)
        ]
        for cell in table.cells:
            cell.blocks = cell.blocks or [Block("paragraph")]
        if proposed:
            table.attrs["proposedRows"] = proposed
        out.append(table)

    @staticmethod
    def _shows(block: Block) -> bool:
        return block.type != "paragraph" or bool(block.runs) or bool(block.attrs.get("list"))

    def _design(self, tblpr) -> dict | None:
        """The design the table's style and its own lines give it, with the parts its look
        turns on."""
        style = value(tblpr.find(w("tblStyle"))) if tblpr is not None else None
        design, lost = self.styles.design(style or self.styles.defaults.get("table"), tblpr)
        self.lost["tableStyles"] += lost
        if design is None:
            return None
        looked = _looked(tblpr.find(w("tblLook")) if tblpr is not None else None)
        if on := {ours: True for theirs, ours in SWITCHES.items() if theirs in looked}:
            design["on"] = on
        return design

    def _cell_fill(self, tcpr) -> str | None:
        """The cell's own shading over its table's design, "none" taking the design's away."""
        found = tcpr.find(w("shd")) if tcpr is not None else None
        if found is None:
            return None
        fill, patterned = shading(found)
        self.lost["tableStyles"] += patterned
        return fill

    def _cell_edges(self, tcpr) -> dict | None:
        """The lines the cell draws on its own sides over its table's design."""
        borders = tcpr.find(w("tcBorders")) if tcpr is not None else None
        found, lost = edges_of(borders)
        own = {side: found[side] for side in ("top", "bottom", "left", "right") if side in found}
        diagonal = (
            sum(borders.find(w(tag)) is not None for tag in ("tl2br", "tr2bl"))
            if borders is not None
            else 0
        )
        self.lost["tableStyles"] += lost + len(found) - len(own) + diagonal
        return own or None

    # Text

    def _showing(self) -> bool:
        return all(each.result and each.kind != "TOC" and not each.ours for each in self.fields)

    def _field_link(self) -> str | None:
        for each in reversed(self.fields):
            if each.kind == "HYPERLINK" and each.result:
                quoted = re.findall(r'"([^"]*)"', each.instruction)
                return office.safe(quoted[0]) if quoted else None
        return None

    def _inline(self, parent, text: Text, context: Context) -> None:
        for child in parent:
            tag = child.tag
            if tag == w("r"):
                self._run(child, text, context)
            elif tag == w("hyperlink"):
                self._inline(child, text, replace(context, link=self._href(child, context)))
            elif tag in INSERTED | DELETED and context.header:
                self.accepted += 1
                if tag in INSERTED:
                    self._inline(child, text, context)
            elif tag in INSERTED | DELETED:
                kind = "insertion" if tag in INSERTED else "deletion"
                proposed = {**context.proposed, kind: self._change(child)}
                self._inline(child, text, replace(context, proposed=proposed))
            elif tag in WRAPPERS:
                self._inline(child, text, context)
            elif tag == w("sdt"):
                if (content := child.find(w("sdtContent"))) is not None:
                    self._inline(content, text, context)
            elif tag == w("fldSimple"):
                self._opened_field(WordField(child.get(w("instr")) or "", True), text, context)
                self._inline(child, text, context)
                self.fields.pop()
            elif tag == ns(MC, "AlternateContent"):
                self._inline(self._chosen(child), text, context)
            elif tag in (w("commentRangeStart"), w("commentRangeEnd")):
                if context.note:
                    self.lost["noteComments"] += tag == w("commentRangeStart")
                else:
                    self._comment_mark(child)
            elif tag in (ns(MATH, "oMath"), ns(MATH, "oMathPara")):
                self.lost["equations"] += 1

    def _href(self, hyperlink, context: Context) -> str | None:
        if not self._showing():
            return context.link
        rid = hyperlink.get(ns(R, "id"))
        relationship = context.part.rels.get(rid) if rid else None
        if relationship is None or not relationship.is_external:
            if hyperlink.get(w("anchor")):
                self.lost["internalLinks"] += 1
            return context.link
        anchor = hyperlink.get(w("anchor"))
        href = relationship.target_ref + (f"#{anchor}" if anchor else "")
        if (safe := office.safe(href)) is None:
            self.lost["links"] += 1
            return context.link
        return safe

    def _opened_field(self, opened: WordField, text: Text, context: Context) -> None:
        self.fields.append(opened)
        if opened.result:
            self._resulted(opened, text, context)

    def _resulted(self, done: WordField, text: Text, context: Context) -> None:
        """A field reaches the text it shows: a page's field becomes ours in a header or
        footer, the contents ours anywhere outside a table."""
        ours = PAGE_FIELDS.get(done.kind) if context.header else None
        if ours and self._showing():
            done.ours = True
            text.runs.append(Field(ours))
        elif done.kind == "TOC" and not context.note and not context.header:
            found = DEPTH.search(done.instruction)
            self.contents = min(max(int(found.group(1)), 1), 4) if found else 3
        else:
            self._counted(done)

    def _counted(self, done: WordField) -> None:
        if done.kind == "TOC":
            self.lost["toc"] = 1
        elif done.kind == "HYPERLINK":
            if self._field_link() is None:
                self.lost["internalLinks"] += 1
        elif done.kind and not any(each.kind == "TOC" for each in self.fields):
            self.lost["fields"] += 1

    def _run(self, r, text: Text, context: Context) -> None:
        rpr = r.find(w("rPr"))
        change = rpr.find(w("rPrChange")) if rpr is not None else None
        if change is not None and context.header:
            self.accepted += 1
        elif change is not None:
            look = self._run_look(change.find(w("rPr")), context.base)
            before = self._marks(look, context.base, None)
            formatting = {**self._change(change), "before": before}
            context = replace(context, proposed={**context.proposed, "formatting": formatting})
        self._pieces(r, self._run_look(rpr, context.base), text, context)

    def _run_look(self, rpr, base: dict) -> dict:
        """The look of a run, or of a paragraph's mark, over its paragraph style's."""
        character = value(rpr.find(w("rStyle"))) if rpr is not None else None
        return {
            **base,
            **self.styles.character_look(character),
            **run_layer(rpr, self.styles.theme),
        }

    def _pieces(self, parent, look: dict, text: Text, context: Context) -> None:
        for child in parent:
            tag = child.tag
            if tag in (w("t"), w("delText")):
                self._show(child.text or "", look, text, context)
            elif tag in (w("tab"), w("ptab")):
                self._show("\t", look, text, context)
            elif tag == w("br"):
                kind = child.get(w("type"))
                if kind == "page" and not (context.note or context.header or context.cell):
                    if self._showing():
                        cut = PageBreak(text.length, len(text.after), proposed=context.blocked)
                        text.runs.append(cut)
                elif kind in ("page", "column"):
                    self.lost["pageBreaks"] += self._showing()
                else:
                    self._show("\n", look, text, context)
            elif tag == w("cr"):
                self._show("\n", look, text, context)
            elif tag == w("noBreakHyphen"):
                self._show("‑", look, text, context)
            elif tag == w("softHyphen"):
                self._show("­", look, text, context)
            elif tag == w("sym"):
                self.lost["symbols"] += self._showing()
            elif tag == w("fldChar"):
                self._field_char(child, text, context)
            elif tag in (w("instrText"), w("delInstrText")):
                if self.fields and not self.fields[-1].result:
                    self.fields[-1].instruction += child.text or ""
            elif tag in (w("footnoteReference"), w("endnoteReference")):
                self._note(child, text, context)
            elif tag == w("commentReference"):
                self._comment_reference(child, context)
            elif tag in (w("drawing"), w("pict")):
                start = len(text.after)
                if tag == w("drawing"):
                    self._drawing(child, text, context)
                else:
                    self._pict(child, text, context)
                _proposed(text.after[start:], context.blocked)
            elif tag == w("object"):
                self.lost["objects"] += self._showing()
            elif tag == ns(MC, "AlternateContent"):
                self._pieces(self._chosen(child), look, text, context)
            elif tag == w("ruby"):
                if (ruby := child.find(w("rubyBase"))) is not None:
                    self._inline(ruby, text, context)

    def _field_char(self, char, text: Text, context: Context) -> None:
        kind = char.get(w("fldCharType"))
        if kind == "begin":
            self.fields.append(WordField())
        elif kind == "separate" and self.fields and not self.fields[-1].result:
            self.fields[-1].result = True
            self._resulted(self.fields[-1], text, context)
        elif kind == "end" and self.fields:
            done = self.fields.pop()
            # A page's field Word has not yet laid out has no text to show, only its kind.
            if not done.result and context.header and done.kind in PAGE_FIELDS:
                self.fields.append(done)
                done.result = True
                self._resulted(done, text, context)
                self.fields.pop()

    def _show(self, chars: str, look: dict, text: Text, context: Context) -> None:
        if not chars:
            return
        if not self._showing():
            text.toc = text.toc or any(each.kind == "TOC" for each in self.fields)
            return
        if look.get("hidden"):
            self.lost["hiddenText"] += 1
            return
        if look.get("caps"):
            chars = chars.upper()
        if (font := look.get("font")) and font[0]:
            self.fonts.add(font[0])
        marks = self._marks(look, context.base, context.link or self._field_link())
        marks |= self._proposals(marks, context)
        if context.note or text.id is None:
            text.add(chars, marks)
            return
        at = text.length
        for id in self.pending:
            thread = self.threads[id]
            thread.start = (text.id, at)
            if thread.closed:
                thread.end = (text.id, at)
        self.pending.clear()
        text.add(chars, marks)
        self.last = (text.id, text.length - utf16(chars[-1]))

    def _proposals(self, marks: dict, context: Context) -> dict:
        """The proposals text is part of; a formatting change only where it changed one of the
        marks."""
        proposed = dict(context.proposed)
        formatting = proposed.get("formatting")
        if formatting and formatting["before"] == {
            name: attrs for name, attrs in marks.items() if name != "link"
        }:
            del proposed["formatting"]
        if not proposed:
            self.revision = None
        return proposed

    def _marks(self, look: dict, base: dict, link: str | None) -> dict:
        marks: dict[str, dict] = {}
        if link:
            marks["link"] = {"href": link}
        for mark, key in (("strong", "bold"), ("em", "italic"), ("strike", "strike")):
            if look.get(key) and not base.get(key):
                marks[mark] = {}
        if look.get("underline") and not base.get("underline") and not link:
            marks["underline"] = {}
        if (align := look.get("vertAlign")) in ("superscript", "subscript"):
            marks["sup" if align == "superscript" else "sub"] = {}
        if not link and look.get("color") != base.get("color"):
            if color := colors.text_color(look.get("color")):
                marks["color"] = {"color": color}
        shade = colors.highlight(look.get("highlight"), look.get("shading"))
        if shade and shade != colors.highlight(base.get("highlight"), base.get("shading")):
            marks["highlight"] = {"color": shade}
        font, plain = look.get("font"), base.get("font")
        if font and (plain is None or font[0] != plain[0]):
            marks["font"] = {"family": font[0]}
        size = look.get("size")
        if size is not None and size != base.get("size") and 1 <= size <= 400:
            marks["size"] = {"pt": size}
        if (kerning := kerned(look)) != kerned(base):
            marks["kerning"] = {"on": kerning}
        return marks

    # Notes

    def _note(self, reference, text: Text, context: Context) -> None:
        if context.note or context.header or not self._showing():
            return
        kind = "foot" if reference.tag == w("footnoteReference") else "end"
        revision = self.revision
        runs = self._note_runs(kind, reference.get(w("id")))
        self.revision = revision
        text.runs.append(Note(kind, runs=runs, proposed=context.blocked))

    def _note_runs(self, kind: str, id: str | None) -> list[Run]:
        part, tag = self.notes[kind]
        if part is None or id is None:
            return []
        root = self._parsed(part)
        found = next((each for each in root.iterfind(tag) if each.get(w("id")) == id), None)
        if found is None:
            return []
        saved, self.fields = self.fields, []
        text = Text(None)
        for p in found.iter(w("p")):
            if text.runs:
                text.add(" ", {})
            ppr = p.find(w("pPr"))
            style = self.styles.paragraph_style(
                value(ppr.find(w("pStyle"))) if ppr is not None else None
            )
            styled, base = self.styles.paragraph_look(style)
            if _drawn(layered(styled, paragraph_layer(ppr))):
                self.lost["paragraphBorders"] += 1
            self._inline(p, text, Context(part, base, note=True))
        self.fields = saved
        runs = [run for run in text.runs if isinstance(run, Run)]
        if runs:
            runs[0].text = runs[0].text.lstrip()
            runs[-1].text = runs[-1].text.rstrip()
        return [run for run in runs if run.text]

    def _parsed(self, part):
        if part.partname not in self.roots:
            self.roots[part.partname] = parse_xml(part.blob)
        return self.roots[part.partname]

    # Pictures and boxes

    def _drawing(self, drawing, text: Text, context: Context) -> None:
        if not self._showing():
            return
        for frame in drawing:
            data = frame.find(f"{ns(A, 'graphic')}/{ns(A, 'graphicData')}")
            uri = data.get("uri", "") if data is not None else ""
            if uri == PIC:
                blip = data.find(f".//{ns(A, 'blip')}")
                extent = frame.find(ns(WP, "extent"))
                props = frame.find(ns(WP, "docPr"))
                cx = number(extent.get("cx")) if extent is not None else None
                alt = (props.get("descr") or props.get("title") or "") if props is not None else ""
                rid = blip.get(ns(R, "embed")) if blip is not None else None
                self._image(rid, cx / EMU_PER_CM if cx else None, alt, text, context)
            elif uri == CHART:
                self._chart(data, text, context)
            elif uri.startswith(DIAGRAM):
                self.lost["diagrams"] += 1
            elif data is not None and (box := data.find(f".//{w('txbxContent')}")) is not None:
                self._boxed(box, text, context)
            else:
                self.lost["shapes"] += 1

    def _chart(self, data, text: Text, context: Context) -> None:
        """A chart, after the paragraph it hangs on, over a table of its data."""
        chart = data.find(f"{charts.C}chart")
        rid = chart.get(ns(R, "id")) if chart is not None else None
        relationship = context.part.rels.get(rid) if rid else None
        made = None
        if not (context.cell or context.note or context.header):
            made = office.chart(relationship, self.locale)
        if made is None:
            self.lost["charts"] += 1
            return
        self.lost.update(made.lost)
        self.fonts.update(made.fonts)
        text.after.extend(made.blocks)

    def _pict(self, pict, text: Text, context: Context) -> None:
        if not self._showing():
            return
        if (box := pict.find(f".//{w('txbxContent')}")) is not None:
            self._boxed(box, text, context)
        elif any(shape.get(ns(VO, "hr")) in ("t", "true") for shape in pict.iter(ns(V, "rect"))):
            self._rule(text, context)
        elif (data := pict.find(f".//{ns(V, 'imagedata')}")) is not None:
            shape = data.getparent()
            width = _length(shape.get("style"), "width")
            alt = shape.get("alt") or ""
            self._image(data.get(ns(R, "id")), width, alt, text, context)
        else:
            self.lost["shapes"] += 1

    def _rule(self, text: Text, context: Context) -> None:
        """Word's horizontal line, after the paragraph it is drawn in; a cell or a note holds no
        line of ours."""
        if context.cell or context.note:
            self.lost["shapes"] += 1
            return
        text.after.append(Block(RULE))

    def _boxed(self, box, text: Text, context: Context) -> None:
        """A text box's text, after the paragraph it hangs on; the box itself is not kept."""
        self.lost["textBoxes"] += 1
        if context.note:
            return
        saved, self.fields = self.fields, []
        self._content(box, text.after, cell=True)
        self.fields = saved

    def _image(self, rid, width: float | None, alt: str, text: Text, context: Context) -> None:
        relationship = context.part.rels.get(rid) if rid else None
        found = None if context.note else office.picture(relationship)
        if found is None:
            self.lost["images"] += 1
            return
        sha256, self.images[found[0]] = found
        image = Block("image", attrs={"blob": sha256, "alt": alt.strip()[:500]})
        if width:
            self.sized[image.id] = width
        text.after.append(image)

    # Comments

    def _comments(self) -> None:
        root = self._xml(RT.COMMENTS)
        if root is None:
            return
        remarks: dict[str, Remark] = {}
        by_paragraph: dict[str, str] = {}
        for comment in root.iterfind(w("comment")):
            id = comment.get(w("id"))
            paragraphs = comment.findall(f".//{w('p')}")
            words = "\n".join(
                "".join(t.text or "" for t in p.iter(w("t"))) for p in paragraphs
            ).strip()
            remarks[id] = Remark(
                (comment.get(w("author")) or "").strip()[:200],
                _date(comment.get(w("date"))),
                words[:LONGEST_BODY],
            )
            if paragraphs and (paragraph := paragraphs[-1].get(ns(W14, "paraId"))):
                by_paragraph[paragraph] = id
        parents: dict[str, str] = {}
        done: set[str] = set()
        extended = self._xml(COMMENTS_EXTENDED)
        for each in extended.iterfind(ns(W15, "commentEx")) if extended is not None else []:
            id = by_paragraph.get(each.get(ns(W15, "paraId")) or "")
            parent = by_paragraph.get(each.get(ns(W15, "paraIdParent")) or "")
            if id and parent and parent != id:
                parents[id] = parent
            if id and (each.get(ns(W15, "done")) or "0").lower() in ("1", "true", "on"):
                done.add(id)
        for id, remark in remarks.items():
            if id not in parents:
                self.threads[id] = Thread([remark], id in done)
        for id, parent in parents.items():
            while parent in parents:
                parent = parents[parent]
            if parent in self.threads:
                self.threads[parent].remarks.append(remarks[id])
        for thread in self.threads.values():
            thread.remarks.sort(key=lambda remark: remark.date or datetime.min.replace(tzinfo=UTC))

    def _comment_mark(self, mark) -> None:
        thread = self.threads.get(mark.get(w("id")))
        if thread is None:
            return
        id = mark.get(w("id"))
        if mark.tag == w("commentRangeStart"):
            if thread.start is None and id not in self.pending:
                self.pending.append(id)
            return
        thread.closed = True
        if thread.start is not None and thread.end is None:
            thread.end = self.last

    def _comment_reference(self, reference, context: Context) -> None:
        id = reference.get(w("id"))
        thread = self.threads.get(id)
        if thread is None or context.note:
            return
        if thread.start is None and id not in self.pending:
            if self.last is None:
                thread.closed = True
                self.pending.append(id)
            else:
                thread.start = thread.end = self.last

    def _placed(self) -> list[Thread]:
        """Threads with their stretch and quote; one whose text did not come over is counted."""
        index = {id: at for at, (id, _) in enumerate(self.order)}
        placed = []
        for thread in self.threads.values():
            start, end = thread.start, thread.end
            if start is None or end is None or start[0] not in index or end[0] not in index:
                self.lost["comments"] += 1
                continue
            first, last = index[start[0]], index[end[0]]
            if (last, end[1]) < (first, start[1]):
                start, end, first, last = end, start, last, first
            parts = []
            for at in range(first, last + 1):
                id, plain = self.order[at]
                parts.append(
                    _sliced(
                        plain,
                        start[1] if id == start[0] else 0,
                        _past(plain, end[1]) if id == end[0] else None,
                    )
                )
            thread.start, thread.end = start, end
            thread.quote = "\n".join(parts).strip()[:LONGEST_QUOTE]
            placed.append(thread)
        return placed
