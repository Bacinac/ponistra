"""A document as a Word file: each tab and each section of one a section on pages of its own,
laid out by its page setup, with its headers and footers; the document's styles and list
formats as Word's, its tables with what their cells show, images, charts, footnotes and
endnotes, page fields, contents and comment threads. A tab's title has no place in Word."""

import io
import json
import re
from dataclasses import dataclass, field
from datetime import UTC
from functools import cached_property
from urllib.parse import urljoin

from django.db.models import Prefetch
from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.package import OpcPackage
from docx.opc.packuri import PackURI
from docx.opc.part import Part, XmlPart
from lxml import etree
from pycrdt import Doc, StickyIndex, XmlElement, XmlText

from apps.blobs import store
from apps.comments.models import Comment
from apps.content import blocks, designs, fonts, grids, lists, numbering, pages, palette, styles
from apps.content import charts as drawn
from apps.content.blocks import PROPOSED, Block, Field, Note, Run, utf16
from apps.content.schema import (
    CONTENTS_DEPTH,
    INDENT_STEP,
    LEADERS,
    LEVELS,
    LISTS,
    TAB_KINDS,
)
from apps.documents.models import Node
from apps.imports.docx import BUILT_IN, COMMENTS_EXTENDED, FIRST, LOOK_BITS, SINGLE
from apps.imports.word import DESIGN_PARTS, MC, PIC, TWIPS_PER_CM, W14, W15, WP, A, R, W

from . import charts, office, pictures, xlsx
from .charts import EMU_PER_CM, EMU_PER_PIXEL
from .xlsx import CHARACTER_CM, doc_of

XML = "http://www.w3.org/XML/1998/namespace"
SVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
NS = {
    "w": W,
    "r": R,
    "wp": WP,
    "a": A,
    "pic": PIC,
    "c": charts.C,
    "w14": W14,
    "w15": W15,
    "mc": MC,
    "asvg": SVG,
}
COMMENTS_EXTENDED_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"
)
# The extension a picture keeps its SVG under, beside the PNG every reader shows.
SVG_BLIP = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
# The editor's: Word's default stops (editor/stops.ts), a list marker's room and the size of
# notes (index.css).
DEFAULT_STOP = 1.25
MARKER_EM = 1.75
NOTE_EM = 0.875
# Kerning from 1 pt up, in Word's half-points: every size, as Word's own templates set it.
KERNED = 2
NAMES = {kind: name or "Normal" for kind, name in BUILT_IN.items()}
IDS = {kind: name.title().replace(" ", "") for kind, name in NAMES.items()}
OWN_STYLES = {
    "Hyperlink": ("character", "Hyperlink"),
    "FootnoteText": ("paragraph", "footnote text"),
    "FootnoteReference": ("character", "footnote reference"),
    "EndnoteText": ("paragraph", "endnote text"),
    "EndnoteReference": ("character", "endnote reference"),
    "CommentText": ("paragraph", "annotation text"),
    "CommentReference": ("character", "annotation reference"),
    **{f"TOC{level}": ("paragraph", f"toc {level}") for level in LEVELS},
}
ALIGNS = {None: "left", "left": "left", "center": "center", "right": "right", "justify": "both"}
PART_TYPES = {part: type for type, part in DESIGN_PARTS.items()}
LOOK_SWITCHES = {
    "firstRow": "header",
    "lastRow": "totals",
    "firstColumn": "firstColumn",
    "lastColumn": "lastColumn",
}
EDGE_ORDER = ("top", "left", "bottom", "right", "insideH", "insideV")
CAPS = {"all": ("w:caps", {}), "small": ("w:smallCaps", {}), "none": ("w:caps", {"w:val": 0})}
NUMBERINGS = {
    "1": "decimal",
    "a": "lowerLetter",
    "A": "upperLetter",
    "i": "lowerRoman",
    "I": "upperRoman",
}
PARTS = {"header": (CT.WML_HEADER, RT.HEADER), "footer": (CT.WML_FOOTER, RT.FOOTER)}
FIELDS = {"page": "PAGE", "pages": "NUMPAGES", "title": "TITLE", "date": "DATE"}
CHECKS = {False: "☐", True: "☑"}
# How a cell aligns the value of each kind its formula or number format makes (index.css).
# A section break in a tab's text parts its sections; one in a header or footer, where Word
# holds none, has nothing to write.
UNWRITTEN = {"slideBreak", "columnBreak", "sectionBreak"}


def q(name: str) -> str:
    prefix, _, local = name.rpartition(":")
    if not prefix:
        return local
    return f"{{{XML if prefix == 'xml' else NS[prefix]}}}{local}"


def sub(parent, tag: str, attrs: dict | None = None, text: str | None = None):
    element = etree.SubElement(parent, q(tag), {q(k): str(v) for k, v in (attrs or {}).items()})
    if text is not None:
        element.text = text
    return element


def root(tag: str):
    element = etree.Element(q(tag), nsmap=NS)
    element.set(q("mc:Ignorable"), "w14 w15")
    return element


def twips(cm: float) -> int:
    return round(cm * TWIPS_PER_CM)


def _length(value) -> float:
    return value if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _fonts(family: str) -> dict:
    return {f"w:{slot}": fonts.office(family) for slot in ("ascii", "hAnsi", "cs", "eastAsia")}


def _index(text: str, units: int) -> int:
    """The index in the text that many UTF-16 units in."""
    count = 0
    for index, char in enumerate(text):
        if count >= units:
            return index
        count += 2 if ord(char) > 0xFFFF else 1
    return len(text)


def _format_of(form: dict) -> str:
    if form["numbering"]:
        return NUMBERINGS[form["numbering"]]
    return "bullet" if form["prefix"] or form["suffix"] else "none"


def _text_of(forms: list[dict], level: int) -> str:
    form = forms[level]
    if not form["numbering"]:
        return form["prefix"] + form["suffix"]
    above = [at for at in range(level) if forms[at]["numbering"]] if form["nested"] else []
    shown = ".".join(f"%{at + 1}" for at in [*above, level])
    return form["prefix"] + shown + form["suffix"]


@dataclass
class Num:
    """One of Word's numberings, with an abstract numbering of its own so that its counts are
    its alone, and the values its levels last showed, as Word counts them: a level shows its
    start the first time, one more each time after, and starts again after a level above."""

    id: int
    forms: list[dict]
    inline: bool
    starts: dict[int, int] = field(default_factory=dict)
    shown: dict[int, int] = field(default_factory=dict)

    def next(self, level: int) -> int:
        return self.shown[level] + 1 if level in self.shown else self.starts.get(level, 1)

    def showing(self, level: int) -> int:
        return self.shown.get(level, self.starts.get(level, 1))

    def use(self, level: int, value: int) -> None:
        self.shown = {at: count for at, count in self.shown.items() if at < level}
        self.shown[level] = value


class Numbers:
    """The numberings the document's lists and numbered styles show, each started anew where
    Word's count would differ from ours."""

    def __init__(self):
        self.made: list[Num] = []
        self.current: dict[tuple, Num] = {}

    def new(self, key: tuple, forms: list[dict], inline: bool, starts=None) -> Num:
        num = Num(len(self.made) + 1, forms, inline, starts or {})
        self.made.append(num)
        self.current[key] = num
        return num

    def use(self, key: tuple, forms, level: int, value=None, above=None, inline=False) -> int:
        num, above = self.current.get(key), above or {}
        nested = forms[level]["nested"]
        if num is not None and value is not None:
            shown = [at for at in above if nested and forms[at]["numbering"]]
            if num.next(level) != value or any(num.showing(at) != above[at] for at in shown):
                num = None
        if num is None:
            starts = {}
            if value is not None:
                # A nested number shows the counts above it as they stand; any other counts
                # on from them.
                starts = {at: count + (0 if nested else 1) for at, count in above.items()}
                starts[level] = value
            num = self.new(key, forms, inline, starts)
        if value is not None:
            num.use(level, value)
        return num.id


def _plain(text: XmlText) -> str:
    return "".join(part for part, _ in text.diff())


def _texts(doc: Doc) -> list[tuple[XmlText, str, int, bool]]:
    """Every text of the tab's blocks: its block, where it starts in the block's text, and
    whether it is a note's, which stands where the note's mark is."""
    found = []

    def read(element: XmlElement) -> None:
        id, offset = element.attributes.get("id"), 0
        for child in element.children:
            if isinstance(child, XmlText):
                found.append((child, id, offset, False))
                offset += utf16(_plain(child))
            elif isinstance(child, XmlElement) and child.tag == blocks.NOTE:
                found.extend(
                    (part, id, offset, True) for part in child.children if isinstance(part, XmlText)
                )

    for element in blocks.body_of(doc).children:
        if not isinstance(element, XmlElement):
            continue
        if element.tag != "table":
            read(element)
            continue
        for cell in element.children:
            for inner in cell.children if isinstance(cell, XmlElement) else []:
                if isinstance(inner, XmlElement):
                    read(inner)
    return found


def _offset(txn, end, clocks: dict[int, int]) -> int | None:
    """The index of a relative position in its text, or None where it names nothing the tab
    holds or its text is gone."""
    named = (end.get("item") or end.get("type")) if isinstance(end, dict) else None
    client, clock = (named.get("client"), named.get("clock")) if isinstance(named, dict) else (0, 0)
    if not (isinstance(client, int) and isinstance(clock, int)):
        return None
    if not 0 <= clock < clocks.get(client, 0):
        return None
    try:
        return StickyIndex.from_json(end).get_index(txn)
    except KeyError, TypeError, ValueError, RuntimeError:
        return None
    except BaseException as error:
        # pycrdt panics on a position whose text is gone, and pyo3's PanicException is no
        # Exception.
        if type(error).__name__ != "PanicException":
            raise
        return None


def _indices(doc: Doc, ends: list) -> list[int | None]:
    known = blocks.clocks(doc)
    with doc.transaction() as txn:
        return [_offset(txn, end, known) for end in ends]


def _sections(content: list[Block]) -> list[tuple[str | None, list[Block]]]:
    """The tab's sections, each after the id of the break it follows."""
    found: list[tuple[str | None, list[Block]]] = [(None, [])]
    for block in content:
        if block.type == "sectionBreak":
            found.append((block.id, []))
        else:
            found[-1][1].append(block)
    return found


def located(doc: Doc, ends: list) -> list[tuple[str, int] | None]:
    """Where each of the comments' ends is, as its block and offset in the block's text.
    pycrdt gives a relative position's index but not the text it is in, so the texts are told
    apart by the indices that move when a character goes in: in a copy of the tab for each bit
    of a text's number, a character at the start of every text whose number has the bit."""
    texts = _texts(doc)
    base = _indices(doc, ends)
    numbers = [0] * len(ends)
    state = doc.get_update()
    for bit in range((len(texts) + 1).bit_length()):
        copy = Doc()
        copy.apply_update(state)
        for number, (text, *_) in enumerate(_texts(copy), 1):
            if number >> bit & 1:
                text.insert(0, "x")
        resolved = [end if base[at] is not None else None for at, end in enumerate(ends)]
        for at, moved in enumerate(_indices(copy, resolved)):
            if base[at] is not None and moved != base[at]:
                numbers[at] |= 1 << bit
    found: list[tuple[str, int] | None] = []
    for at, number in enumerate(numbers):
        if base[at] is None or not 0 < number <= len(texts):
            found.append(None)
            continue
        _, block, offset, note = texts[number - 1]
        found.append((block, offset if note else offset + base[at]))
    return found


class Writer:
    def __init__(self, document: Node, site: str):
        self.document, self.site = document, site
        self.own = doc_of(document.room)
        self.headed = grids.of_own(document)
        self.theme, self.looks = styles.read(self.own)
        self.formats = lists.read(self.own)
        self.size = (
            _length(self.looks["text"]["size"]) or styles.TEMPLATE[styles.STYLES]["text"]["size"]
        )
        self.package = OpcPackage()
        self.root = root("w:document")
        self.main = XmlPart(
            PackURI("/word/document.xml"), CT.WML_DOCUMENT_MAIN, self.root, self.package
        )
        self.package.relate_to(self.main, RT.OFFICE_DOCUMENT)
        self.part: Part = self.main
        self.ids = self._style_ids()
        self.numbers = Numbers()
        self.counts: dict[str, int] = {}
        self.notes: dict[str, list[list[Run]]] = {"foot": [], "end": []}
        self.comments: list[tuple[Comment, int | None, bool]] = []
        self.placed: list[set[str]] = []
        self.points: dict[str, dict[int, list[tuple[str, int]]]] = {}
        self.media: dict[str, tuple[Part, Part | None, tuple[float, float]]] = {}
        self.parts: dict[tuple[str | None, str], str] = {}
        self.headings: list[tuple[int, str]] = []
        self.heading_forms: list[dict] = []
        self.headed = False
        self.style_sheet = None
        self.table_styles: dict[str, str] = {}
        self.table_names: set[str] = set()
        self.under: tuple[dict, str | None, str | None] = ({}, None, None)
        self.above: dict[int, dict] = {}
        self.drawings = 0
        self.charts = 0
        self.revisions = 0
        self.width = 0.0
        self.height = 0.0

    def written(self) -> bytes:
        order = list(self.document.tabs_in_order())
        ids = [tab.pk for tab in order]
        tabs = []
        for tab in order:
            doc = doc_of(tab.room)
            content = blocks.read(doc, grids.of_tab(tab))
            tabs.append((tab, doc, content))
            read = blocks.in_order(content)
            labels, _ = numbering.numbered(read, numbering.numbering_of(self.own, ids, tab.pk))
            for index, block in enumerate(read):
                if block.type == "heading" and block.text.strip():
                    label = labels.get(index)
                    text = f"{label} {block.text}" if label else block.text
                    self.headings.append((block.attrs.get("level", 1), text))
        self._styles()
        body = sub(self.root, "w:body")
        for index, (tab, doc, content) in enumerate(tabs):
            id = str(tab.pk)
            page, parts = pages.read(self.own, self.headed, id)
            owner = id if pages.owns(self.own, id) else None
            numbered = index == 0 or owner is not None
            self.points = self._threads(tab, doc, content)
            self.above = {}
            split = _sections(content)
            for at, (mark, section) in enumerate(split):
                if mark is not None:
                    own, parts = pages.section(self.own, self.headed, id, mark)
                    page, owner, numbered = own or {**page, "start": None}, f"{id}/{mark}", True
                self.width = page["width"] - page["left"] - page["right"]
                self.height = page["height"] - page["top"] - page["bottom"]
                self._content(body, section, "text")
                properties = self._section(page, parts, owner, numbered, mark is None)
                last = body[-1] if len(body) else None
                if last is None or last.tag != q("w:p"):
                    last = sub(body, "w:p")
                if index == len(tabs) - 1 and at == len(split) - 1:
                    body.append(properties)
                    continue
                props = last.find(q("w:pPr"))
                if props is None:
                    props = etree.Element(q("w:pPr"))
                    last.insert(0, props)
                if (change := props.find(q("w:pPrChange"))) is not None:
                    change.addprevious(properties)
                else:
                    props.append(properties)
        self._numbering()
        self._notes()
        self._comments()
        self._settings()
        office.core(self.package, self.document)
        found = io.BytesIO()
        self.package.save(found)
        return found.getvalue()

    def _related(self, name: str, content_type: str, element, reltype: str) -> tuple[XmlPart, str]:
        part = XmlPart(PackURI(name), content_type, element, self.package)
        return part, self.main.relate_to(part, reltype)

    # Styles

    def _style_ids(self) -> dict[str, str]:
        """Each style's id in Word: the built-in kinds Word's own, a style of ours its own id
        where Word's styles leave it free."""
        ids = dict(IDS)
        taken = {*ids.values(), *OWN_STYLES}
        for id in self.looks:
            if id in ids:
                continue
            made, suffix = id, 1
            while made in taken:
                suffix += 1
                made = f"{id}-{suffix}"
            ids[id] = made
            taken.add(made)
        return ids

    def _styles(self) -> None:
        element = root("w:styles")
        defaults = sub(element, "w:docDefaults")
        run = sub(sub(defaults, "w:rPrDefault"), "w:rPr")
        sub(run, "w:rFonts", _fonts(styles.family(self.theme, "text")))
        sub(run, "w:lang", {"w:val": office.language_of(self.document)})
        sub(sub(defaults, "w:pPrDefault"), "w:pPr")
        forms = []
        for level in LEVELS:
            kind = f"h{level}"
            numbered = [look for look in self.looks.values() if look["kind"] == kind]
            numbered = [look for look in numbered if lists.form_of(look)["numbering"]]
            built = self.looks[kind]
            chosen = built if lists.form_of(built)["numbering"] else next(iter(numbered), None)
            forms.append(lists.form_of(chosen) if chosen else lists.NONE)
        self.heading_forms = forms + [lists.NONE] * (lists.LEVELS - len(forms))
        self.headed = any(form["numbering"] for form in forms)
        if self.headed:
            self.numbers.new(("headings", repr(self.heading_forms)), self.heading_forms, True)
        for id, look in self.looks.items():
            if not look["kind"].startswith("h") and lists.form_of(look)["numbering"]:
                self.numbers.new(
                    ("style", id), [lists.form_of(look), *[lists.NONE] * (lists.LEVELS - 1)], True
                )
        for id, look in self.looks.items():
            self._style(element, id, look)
        blue = palette.text("blue")
        for id, (type, name) in OWN_STYLES.items():
            style = sub(element, "w:style", {"w:type": type, "w:styleId": id})
            sub(style, "w:name", {"w:val": name})
            if type == "paragraph":
                sub(style, "w:basedOn", {"w:val": IDS["text"]})
                props = sub(style, "w:pPr")
                sub(props, "w:spacing", {"w:before": 0, "w:after": 0, "w:line": 240})
                if id.startswith("TOC"):
                    sub(props, "w:ind", {"w:left": twips((int(id[3:]) - 1) * INDENT_STEP / 2)})
            props = sub(style, "w:rPr")
            if id == "Hyperlink":
                sub(props, "w:color", {"w:val": blue})
                sub(props, "w:u", {"w:val": "single"})
            elif id.endswith("Reference") and not id.startswith("Comment"):
                sub(props, "w:vertAlign", {"w:val": "superscript"})
            elif id in ("FootnoteText", "EndnoteText"):
                half = round(self.size * NOTE_EM * 2)
                sub(props, "w:sz", {"w:val": half})
                sub(props, "w:szCs", {"w:val": half})
        self.style_sheet = element
        self._related("/word/styles.xml", CT.WML_STYLES, element, RT.STYLES)

    def _style(self, parent, id: str, look: dict) -> None:
        kind = look["kind"]
        built = id == kind
        attrs = {"w:type": "paragraph", "w:styleId": self.ids[id]}
        if kind == "text" and built:
            attrs["w:default"] = 1
        if not built:
            attrs["w:customStyle"] = 1
        style = sub(parent, "w:style", attrs)
        name = look.get("name")
        sub(style, "w:name", {"w:val": NAMES[kind] if built else (name or id)})
        if not (built and kind == "text"):
            sub(style, "w:basedOn", {"w:val": IDS["text"] if built else IDS[kind]})
        if kind != "text":
            sub(style, "w:next", {"w:val": IDS["text"]})
        sub(style, "w:qFormat")
        props = sub(style, "w:pPr")
        if kind.startswith("h") or kind == "title":
            sub(props, "w:keepNext")
        numbered = self._style_number(id, look)
        if numbered is None and not built and self._style_number(kind, self.looks[kind]):
            numbered = 0, 0
        if numbered is not None:
            num, level = numbered
            listed = sub(props, "w:numPr")
            sub(listed, "w:ilvl", {"w:val": level})
            sub(listed, "w:numId", {"w:val": num})
        line = _length(look.get("line")) or SINGLE
        spacing = {
            "w:before": round(_length(look.get("before")) * 20),
            "w:after": round(_length(look.get("after")) * 20),
            "w:line": round(line / SINGLE * 240),
            "w:lineRule": "auto",
        }
        sub(props, "w:spacing", spacing)
        sub(props, "w:jc", {"w:val": ALIGNS.get(look.get("align"), "left")})
        if kind.startswith("h"):
            sub(props, "w:outlineLvl", {"w:val": int(kind[1:]) - 1})
        props = sub(style, "w:rPr")
        font = look.get("font") if isinstance(look.get("font"), str) else "text"
        sub(props, "w:rFonts", _fonts(styles.family(self.theme, font)))
        sub(props, "w:b", {"w:val": int(look.get("bold") is True)})
        sub(props, "w:i", {"w:val": int(look.get("italic") is True)})
        sub(props, "w:color", {"w:val": palette.text(look.get("color")) or "auto"})
        sub(props, "w:kern", {"w:val": KERNED if look.get("kerning") is not False else 0})
        half = round((_length(look.get("size")) or self.size) * 2)
        sub(props, "w:sz", {"w:val": half})
        sub(props, "w:szCs", {"w:val": half})

    def _style_number(self, id: str, look: dict) -> tuple[int, int] | None:
        """The numbering a style carries in Word: a heading's level of the headings' where it
        shows that level's form, another numbered style its own. Word's Normal carries none,
        or every paragraph of another style would number."""
        kind = look["kind"]
        if id == "text":
            return None
        if kind.startswith("h"):
            num = self.numbers.current.get(("headings", repr(self.heading_forms)))
            level = int(kind[1:]) - 1
            if num and lists.form_of(look)["numbering"] and num.forms[level] == lists.form_of(look):
                return num.id, level
            return None
        num = self.numbers.current.get(("style", id))
        return (num.id, 0) if num else None

    def _style_of(self, block: Block, kind: str) -> str:
        own = block.attrs.get("style")
        if isinstance(own, str) and own in self.looks and self.looks[own]["kind"] == kind:
            return own
        return kind

    # Sections

    def _section(
        self,
        page: dict,
        parts: dict[str, list[Block]],
        owner: str | None,
        numbered: bool,
        whole: bool,
    ):
        """A section's properties: a tab's names every header and footer it shows, the first
        page's where it has any, so that a section after a break in it takes from it, as Word
        does, the ones that section does not name."""
        section = etree.Element(q("w:sectPr"))
        for side in ("header", "footer"):
            for name, kind in ((side, "default"), (FIRST[side], "first")):
                if whole and kind == "first" and not (page["firstPage"] or parts.get(name)):
                    continue
                if not whole and name not in parts:
                    continue
                rid = self._part_of(owner, name, side, parts.get(name, []))
                sub(section, f"w:{side}Reference", {"w:type": kind, "r:id": rid})
        width, height = page["width"], page["height"]
        size = {"w:w": twips(width), "w:h": twips(height)}
        if width > height:
            size["w:orient"] = "landscape"
        sub(section, "w:pgSz", size)
        margins = ("top", "right", "bottom", "left", "header", "footer")
        sub(
            section,
            "w:pgMar",
            {**{f"w:{side}": twips(page[side]) for side in margins}, "w:gutter": 0},
        )
        start = page.get("start")
        if numbered and isinstance(start, int | float) and start >= 0:
            sub(section, "w:pgNumType", {"w:start": int(start)})
        if page["firstPage"]:
            sub(section, "w:titlePg")
        return section

    def _part_of(self, owner: str | None, name: str, side: str, content: list[Block]) -> str:
        """A header or footer, written once for every section that shows it."""
        key = (owner, name)
        if key not in self.parts:
            element = root("w:hdr" if side == "header" else "w:ftr")
            content_type, reltype = PARTS[side]
            name = f"/word/{side}{len(self.parts) + 1}.xml"
            part, self.parts[key] = self._related(name, content_type, element, reltype)
            self.part, saved = part, self.part
            self._content(element, content, "part")
            if not len(element):
                sub(element, "w:p")
            self.part = saved
        return self.parts[key]

    # Blocks

    def _content(self, parent, content: list[Block], where: str) -> None:
        """Blocks of the tab's text, of a cell (`cell`), or of a header or footer (`part`),
        where numbered styles neither count nor show."""
        items = lists.Items()
        for block in content:
            if block.type in UNWRITTEN or block.attrs.get("speaker") is True:
                continue
            listed = block.type == "paragraph" and block.attrs.get("list") in LISTS
            if block.type == "table":
                self._table(parent, block, "part" if where == "part" else "cell")
            elif block.type == "image":
                self._image(parent, block)
            elif block.type == "pdf":
                self._pdf(parent, block)
            elif block.type == "pageBreak":
                paragraph = self._proposed(sub(parent, "w:p"), block.attrs)
                sub(sub(paragraph, "w:r"), "w:br", {"w:type": "page"})
            elif block.type == "horizontalRule":
                self._rule(parent, block)
            elif block.type == "contents":
                self._contents(parent, block)
            elif block.type == "chart":
                self._chart(parent, block)
            elif block.type in office.TEXTUAL:
                self._paragraph(parent, block, items.step(block.attrs) if listed else None, where)
            else:
                raise ValueError(f"a {block.type} block has no form in Word")
            if not listed:
                items.end()

    def _paragraph(self, parent, block: Block, item: tuple | None, where: str) -> None:
        kind = numbering.kind_of(block) or "text"
        style = self._style_of(block, kind)
        paragraph = sub(parent, "w:p")
        props = sub(paragraph, "w:pPr")
        numbered = self._listed(block, *item) if item else self._numbered(block, kind, style, where)
        self._layout(props, block, style, numbered, item is None)
        kept = block.attrs.get("endMarks")
        if isinstance(kept, dict) and (marks := self._marks(kept)) is not None:
            props.append(marks)
        self._ended(props, block.attrs)
        if isinstance(formatting := block.attrs.get("formatting"), dict):
            self._restyled(props, formatting)
        self._runs(paragraph, block)

    def _layout(
        self, props, block: Block, style: str, numbered: tuple | None, indented: bool
    ) -> None:
        if self.ids[style] != IDS["text"]:
            sub(props, "w:pStyle", {"w:val": self.ids[style]})
        if numbered is not None:
            num, level = numbered
            listed = sub(props, "w:numPr")
            sub(listed, "w:ilvl", {"w:val": level})
            sub(listed, "w:numId", {"w:val": num})
        if (stops := self._stops(block.attrs.get("tabs"))) is not None:
            props.append(stops)
        if indented and (indents := self._indents(block.attrs)):
            sub(props, "w:ind", indents)
        if (align := block.attrs.get("align") or self.under[2]) in ALIGNS and align:
            sub(props, "w:jc", {"w:val": ALIGNS[align]})

    # Proposals

    def _revision(self, tag: str, change: dict):
        """One of Word's tracked changes for a part of a proposal, by its author and date."""
        self.revisions += 1
        author = change.get("author")
        attrs = {"w:id": self.revisions, "w:author": author if isinstance(author, str) else ""}
        if isinstance(date := change.get("date"), str):
            attrs["w:date"] = date
        return etree.Element(q(tag), {q(name): str(value) for name, value in attrs.items()})

    def _tracked(self, parent, proposed: dict):
        """Where runs inserted or deleted go: in Word's insertion, its deletion or both."""
        for kind, tag in (("insertion", "w:ins"), ("deletion", "w:del")):
            if isinstance(change := proposed.get(kind), dict):
                parent.append(element := self._revision(tag, change))
                parent = element
        return parent

    def _ended(self, props, attrs: dict) -> None:
        """A paragraph's end proposed: Word's paragraph mark inserted or deleted, which comes
        first in the mark's properties."""
        changes = [
            self._revision(tag, change)
            for kind, tag in (("insertion", "w:ins"), ("deletion", "w:del"))
            if isinstance(change := attrs.get(kind), dict)
        ]
        if not changes:
            return
        marks = props.find(q("w:rPr"))
        if marks is None:
            marks = sub(props, "w:rPr")
        marks[0:0] = changes

    def _proposed(self, paragraph, attrs: dict):
        """Where a proposed block's runs go in the paragraph Word holds it in, whose mark is
        proposed with it, so the block comes or goes whole."""
        if not any(isinstance(attrs.get(kind), dict) for kind in PROPOSED):
            return paragraph
        props = paragraph.find(q("w:pPr"))
        if props is None:
            props = etree.Element(q("w:pPr"))
            paragraph.insert(0, props)
        self._ended(props, attrs)
        return self._tracked(paragraph, attrs)

    def _restyled(self, props, formatting: dict) -> None:
        """A block's formatting proposed: Word's change of paragraph properties, holding the
        block's former style, list, tab stops, indents and alignment, which count no number."""
        before = formatting.get("before") if isinstance(formatting.get("before"), dict) else {}
        attrs = before.get("attrs") if isinstance(before.get("attrs"), dict) else {}
        type = before.get("type") if before.get("type") in office.TEXTUAL else "paragraph"
        block = Block(type, attrs=attrs)
        kind = numbering.kind_of(block) or "text"
        listed = type == "paragraph" and attrs.get("list") in LISTS
        numbered = None
        if listed:
            numbered = self._listed(block, attrs["list"], lists.level_of(attrs), None)
        change = self._revision("w:pPrChange", formatting)
        self._layout(sub(change, "w:pPr"), block, self._style_of(block, kind), numbered, not listed)
        props.append(change)

    def _listed(self, block: Block, kind: str, level: int, counts: list | None) -> tuple[int, int]:
        if kind == "check":
            checked = block.attrs.get("checked") is True
            form = {**lists.NONE, "prefix": CHECKS[checked]}
            return self.numbers.use(("check", checked), [form] * lists.LEVELS, level), level
        format = self.formats.get(block.attrs.get("format"))
        forms = [lists.level_in(format, kind, at) for at in range(lists.LEVELS)]
        key = ("list", kind, repr(forms))
        if kind != "number" or counts is None:
            return self.numbers.use(key, forms, level), level
        above = {at: each[1] for at, each in enumerate(counts[:level]) if each and each[0] == kind}
        return self.numbers.use(key, forms, level, counts[level][1], above), level

    def _numbered(self, block: Block, kind: str, style: str, where: str) -> tuple[int, int] | None:
        """A block's number by its style, counted as the editor counts it (content/numbering.py)
        through the tabs; in a cell it counts without showing, as in the editor, and a header's
        neither counts nor shows."""
        look = self.looks[style]
        form = lists.form_of(look)
        heading = kind.startswith("h")
        if not self.headed if heading else not form["numbering"]:
            return None
        if where == "part":
            return 0, 0
        counter = f"#{kind[1:]}" if heading else style
        value = 1 if block.attrs.get("restart") is True else self.counts.get(counter, 0) + 1
        self.counts[counter] = value
        if not heading:
            if where == "cell":
                return 0, 0
            forms = [form, *[lists.NONE] * (lists.LEVELS - 1)]
            return self.numbers.use(("style", style), forms, 0, value, inline=True), 0
        level = int(kind[1:]) - 1
        for below in LEVELS[level + 1 :]:
            self.counts[f"#{below}"] = 0
            self.above.pop(below, None)
        self.above[level + 1] = look
        if where == "cell" or not form["numbering"]:
            return 0, 0
        forms = list(self.heading_forms)
        for at in range(level):
            forms[at] = lists.form_of(self.above.get(at + 1) or self.looks[f"h{at + 1}"])
        forms[level] = form
        above = {at: self.counts.get(f"#{at + 1}", 0) for at in range(level)}
        key = ("headings", repr(forms))
        return self.numbers.use(key, forms, level, value, above, inline=True), level

    @staticmethod
    def _stops(tabs):
        stops = [
            stop
            for stop in (tabs if isinstance(tabs, list) else [])
            if isinstance(stop, dict) and stop.get("kind") in TAB_KINDS and _length(stop.get("at"))
        ]
        if not stops:
            return None
        element = etree.Element(q("w:tabs"))
        for stop in sorted(stops, key=lambda stop: stop["at"]):
            attrs = {"w:val": stop["kind"], "w:pos": twips(stop["at"])}
            if stop.get("leader") in LEADERS:
                attrs["w:leader"] = stop["leader"]
            sub(element, "w:tab", attrs)
        return element

    @staticmethod
    def _indents(attrs: dict) -> dict:
        found = {}
        if (left := _length(attrs.get("indent"))) > 0:
            found["w:left"] = twips(left)
        if (right := _length(attrs.get("right"))) > 0:
            found["w:right"] = twips(right)
        first = _length(attrs.get("firstLine"))
        if first:
            found["w:firstLine" if first > 0 else "w:hanging"] = twips(abs(first))
        return found

    # Text

    def _runs(self, paragraph, block: Block) -> None:
        points = self.points.pop(block.id, {})
        link: list = [None, None]
        at = 0

        def mark(upto: float) -> None:
            for offset in sorted(offset for offset in points if offset <= upto):
                events = points.pop(offset)
                opened = [event for event in events if "start" in self.placed[event[1]]]
                for event in [*opened, *(event for event in events if event not in opened)]:
                    self._point(paragraph, *event)
                link[:] = [None, None]

        for run in block.runs:
            mark(at)
            if isinstance(run, Note):
                link[:] = [None, None]
                self._note(self._tracked(paragraph, run.proposed), run)
            elif isinstance(run, Field):
                link[:] = [None, None]
                self._field(self._tracked(paragraph, run.proposed), run.kind)
            else:
                start, done = at, 0
                at += utf16(run.text)
                for offset in sorted(offset for offset in points if start < offset < at):
                    index = _index(run.text, offset - start)
                    self._text(paragraph, link, run.text[done:index], run.marks)
                    done = index
                    mark(offset)
                self._text(paragraph, link, run.text[done:], run.marks)
        mark(float("inf"))

    def _text(self, paragraph, link: list, text: str, marks: dict) -> None:
        """Text in the paragraph, or in the link it is part of with the text before it."""
        text = office.INVALID.sub("", text)
        if not text:
            return
        href = office.attr(marks, "link", "href")
        if not isinstance(href, str) or not href:
            link[:] = [None, None]
            self._run(paragraph, text, marks)
            return
        href = urljoin(self.site, href)
        if link[1] != href:
            rid = self.part.relate_to(href, RT.HYPERLINK, is_external=True)
            link[:] = [sub(paragraph, "w:hyperlink", {"r:id": rid, "w:history": 1}), href]
        self._run(link[0], text, marks, "Hyperlink")

    def _run(self, parent, text: str, marks: dict, style: str | None = None) -> None:
        parent = self._tracked(parent, marks)
        run = sub(parent, "w:r")
        props = self._marks(marks, style)
        if isinstance(formatting := marks.get("formatting"), dict):
            before = formatting.get("before") if isinstance(formatting.get("before"), dict) else {}
            props = props if props is not None else etree.Element(q("w:rPr"))
            change = self._revision("w:rPrChange", formatting)
            replaced = self._marks(before, style)
            change.append(replaced if replaced is not None else etree.Element(q("w:rPr")))
            props.append(change)
        if props is not None:
            run.append(props)
        shown = "w:delText" if parent.tag == q("w:del") else "w:t"
        for piece in re.split(r"([\t\n])", text):
            if piece == "\t":
                sub(run, "w:tab")
            elif piece == "\n":
                sub(run, "w:br")
            elif piece:
                sub(run, shown, {"xml:space": "preserve"}, piece)

    def _marks(self, marks: dict, style: str | None = None):
        under, caps, _ = self.under
        marks = {**under, **marks}
        props = etree.Element(q("w:rPr"))
        if style:
            sub(props, "w:rStyle", {"w:val": style})
        if isinstance(family := office.attr(marks, "font", "family"), str) and family:
            sub(props, "w:rFonts", _fonts(family))
        for mark, tag in (("strong", "b"), ("em", "i")):
            if mark in marks:
                sub(props, f"w:{tag}")
        if caps in ("all", "small"):
            sub(props, *CAPS[caps])
        if "strike" in marks:
            sub(props, "w:strike")
        if color := palette.text(office.attr(marks, "color", "color")):
            sub(props, "w:color", {"w:val": color})
        if isinstance(kerning := office.attr(marks, "kerning", "on"), bool):
            sub(props, "w:kern", {"w:val": KERNED if kerning else 0})
        if 1 <= (size := _length(office.attr(marks, "size", "pt"))) <= 400:
            sub(props, "w:sz", {"w:val": round(size * 2)})
            sub(props, "w:szCs", {"w:val": round(size * 2)})
        if "underline" in marks:
            sub(props, "w:u", {"w:val": "single"})
        if fill := palette.highlight(office.attr(marks, "highlight", "color")):
            sub(props, "w:shd", {"w:val": "clear", "w:color": "auto", "w:fill": fill})
        if "sup" in marks or "sub" in marks:
            sub(props, "w:vertAlign", {"w:val": "superscript" if "sup" in marks else "subscript"})
        return props if len(props) else None

    def _note(self, paragraph, note: Note) -> None:
        notes = self.notes[note.kind]
        notes.append(note.runs)
        tag = "footnote" if note.kind == "foot" else "endnote"
        run = sub(paragraph, "w:r")
        sub(sub(run, "w:rPr"), "w:rStyle", {"w:val": f"{tag.title()}Reference"})
        sub(run, f"w:{tag}Reference", {"w:id": len(notes)})

    def _field(self, paragraph, kind: str) -> None:
        shown = {"title": self.document.title, "date": office.today(self.document)}.get(kind, "1")
        self._char(paragraph, "begin")
        instruction = sub(paragraph, "w:r")
        tag = "w:delInstrText" if paragraph.tag == q("w:del") else "w:instrText"
        sub(instruction, tag, {"xml:space": "preserve"}, f" {FIELDS.get(kind, 'PAGE')} ")
        self._char(paragraph, "separate")
        self._run(paragraph, shown, {})
        self._char(paragraph, "end")

    @staticmethod
    def _char(paragraph, type: str, dirty: bool = False) -> None:
        attrs = {"w:fldCharType": type, **({"w:dirty": "true"} if dirty else {})}
        sub(sub(paragraph, "w:r"), "w:fldChar", attrs)

    # Tables

    def _table(self, parent, table: Block, where: str) -> None:
        """A table in its design: a design of Word's rules as the table style it is, with its
        cells' own fills and edges over it; else each cell as its designs draw it."""
        listed = table.attrs.get("designs") or []
        styled = (
            listed[0]
            if len(listed) == 1 and listed[0]["rules"] == "word" and "area" not in listed[0]
            else None
        )
        fills, edges = office.own_looks(table)
        looks = office.designed(table)
        table = blocks.visible(table)
        grid = table.grid or blocks.Grid([], [])
        if not grid.rows or not grid.cols:
            return
        attrs = table.attrs
        widths = attrs.get("widths") if isinstance(attrs.get("widths"), dict) else {}
        heights = attrs.get("heights") if isinstance(attrs.get("heights"), dict) else {}
        columns = []
        for col in grid.cols:
            share = _length(widths.get(col))
            if share > 0 and attrs.get("sized"):
                columns.append(twips(share * CHARACTER_CM))
            else:
                columns.append(twips(self.width * (share or 100 / len(grid.cols)) / 100))
        element = sub(parent, "w:tbl")
        props = sub(element, "w:tblPr")
        own_style = styled is not None and bool(styled.get("name") or styled.get("parts"))
        if own_style:
            sub(props, "w:tblStyle", {"w:val": self._table_style(styled)})
        sub(props, "w:tblW", {"w:w": sum(columns), "w:type": "dxa"})
        if styled and (spacing := styled.get("spacing")):
            sub(props, "w:tblCellSpacing", {"w:w": round(spacing * 20), "w:type": "dxa"})
        if styled and not own_style:
            self._edges(props, "w:tblBorders", styled.get("lines") or {})
        if styled and styled.get("spacing") and isinstance(styled.get("background"), str):
            sub(props, "w:shd", self._shading(styled["background"]))
        sub(props, "w:tblLayout", {"w:type": "fixed"})
        if own_style:
            on = styled.get("on") or {}
            flags = {name: bool(on.get(part)) for name, part in LOOK_SWITCHES.items()}
            flags |= {"noHBand": not on.get("rowBands"), "noVBand": not on.get("columnBands")}
            bits = sum(LOOK_BITS[name] for name, set in flags.items() if set)
            looked = {f"w:{name}": int(set) for name, set in flags.items()}
            sub(props, "w:tblLook", {"w:val": f"{bits:04X}", **looked})
        columns_of = sub(element, "w:tblGrid")
        for width in columns:
            sub(columns_of, "w:gridCol", {"w:w": width})
        slots = {}
        for each in blocks.placed(table):
            for y in range(each.y, each.y + each.rows):
                slots[(y, each.x)] = each
        proposed = attrs.get("proposedRows") if isinstance(attrs.get("proposedRows"), dict) else {}
        above = self.under
        frozen = attrs.get("frozen")
        header = grid.rows.index(frozen) + 1 if frozen in grid.rows else 0
        for y, row in enumerate(grid.rows):
            line_of = sub(element, "w:tr")
            trpr = None
            if (height := _length(heights.get(row))) > 0:
                trpr = sub(line_of, "w:trPr")
                sub(trpr, "w:trHeight", {"w:val": round(height * 20), "w:hRule": "atLeast"})
            if y < header:
                trpr = sub(line_of, "w:trPr") if trpr is None else trpr
                sub(trpr, "w:tblHeader")
            changes = proposed.get(row) if isinstance(proposed.get(row), dict) else {}
            for kind, tag in (("insertion", "w:ins"), ("deletion", "w:del")):
                if isinstance(change := changes.get(kind), dict):
                    trpr = sub(line_of, "w:trPr") if trpr is None else trpr
                    trpr.append(self._revision(tag, change))
            x = 0
            while x < len(grid.cols):
                each = slots.get((y, x))
                span = each.cols if each else 1
                cell = sub(line_of, "w:tc")
                cell_props = sub(cell, "w:tcPr")
                sub(cell_props, "w:tcW", {"w:w": sum(columns[x : x + span]), "w:type": "dxa"})
                if span > 1:
                    sub(cell_props, "w:gridSpan", {"w:val": span})
                if each and each.rows > 1:
                    sub(cell_props, "w:vMerge", {"w:val": "restart"} if each.y == y else {})
                slot, last = (row, grid.cols[x]), (row, grid.cols[x + span - 1])
                look = looks[slot]
                if styled:
                    self.under = ({}, None, None)
                    lines = edges.get(slot, {}) | {
                        side: line for side, line in edges.get(last, {}).items() if side == "right"
                    }
                    self._edges(cell_props, "w:tcBorders", lines)
                    if (fill := fills.get(slot)) is not None:
                        sub(cell_props, "w:shd", self._shading(fill))
                else:
                    self.under = (look.marks, look.caps, look.align)
                    lines = look.edges | {"right": looks[last].edges.get("right")}
                    self._edges(
                        cell_props,
                        "w:tcBorders",
                        {side: line for side, line in lines.items() if line is not None},
                    )
                    if look.fill not in (None, designs.NONE):
                        sub(cell_props, "w:shd", self._shading(look.fill))
                    if look.valign:
                        sub(cell_props, "w:vAlign", {"w:val": look.valign})
                if each and each.y == y:
                    self._content(cell, self._shown(table, each.cell), where)
                elif each is None and blocks.key_of(row, grid.cols[x]) in grid.formulas:
                    lone = blocks.Cell(row, grid.cols[x])
                    self._content(cell, self._shown(table, lone), where)
                if cell[-1].tag != q("w:p"):
                    sub(cell, "w:p")
                x += span
        self.under = above

    def _table_style(self, design: dict) -> str:
        """The id of the table style a design of Word's rules is, written once for each design
        and named by it, a later one of the same name but drawn otherwise numbered after it."""
        drawn = {key: design[key] for key in ("name", "parts", "lines", "bands") if key in design}
        key = json.dumps(drawn, sort_keys=True)
        if key in self.table_styles:
            return self.table_styles[key]
        name = design.get("name") or "Table design"
        named, suffix = name, 1
        while named in self.table_names:
            suffix += 1
            named = f"{name} {suffix}"
        taken = {*self.ids.values(), *OWN_STYLES, *self.table_styles.values()}
        id = made = re.sub(r"[^0-9A-Za-z]", "", named) or "TableDesign"
        suffix = 1
        while made in taken:
            suffix += 1
            made = f"{id}{suffix}"
        style = sub(self.style_sheet, "w:style", {"w:type": "table", "w:styleId": made})
        sub(style, "w:name", {"w:val": named})
        parts = design.get("parts") or {}
        banded = any(name.startswith(("rowBand", "columnBand")) for name in parts)
        bands = {
            key: int((design.get("bands") or {}).get(key, [1, 1])[0]) for key in ("rows", "columns")
        }
        table = dict(parts.get("table") or {})
        lines = (design.get("lines") or {}) | table.pop("edges", {})
        self._design_part(style, table, lines, bands if banded else None)
        for part, type in PART_TYPES.items():
            if part in parts:
                conditional = sub(style, "w:tblStylePr", {"w:type": type})
                self._design_part(conditional, parts[part])
        self.table_names.add(named)
        self.table_styles[key] = made
        return made

    def _design_part(self, parent, part: dict, lines=None, bands: dict | None = None) -> None:
        """A part of a design as a table style formats it: paragraph, run, table and cell."""
        if (align := part.get("align")) in ALIGNS and align:
            sub(sub(parent, "w:pPr"), "w:jc", {"w:val": ALIGNS[align]})
        marks = part.get("marks") or {}
        run = etree.Element(q("w:rPr"))
        if isinstance(family := office.attr(marks, "font", "family"), str) and family:
            sub(run, "w:rFonts", _fonts(family))
        for mark, tag in (("strong", "b"), ("em", "i")):
            if mark in marks:
                sub(run, f"w:{tag}", {"w:val": 0} if marks[mark] is False else {})
        if part.get("caps") in CAPS:
            sub(run, *CAPS[part["caps"]])
        if "strike" in marks:
            sub(run, "w:strike", {"w:val": 0} if marks["strike"] is False else {})
        if "color" in marks:
            color = office.solid("text", office.attr(marks, "color", "color"))
            sub(run, "w:color", {"w:val": color or "auto"})
        if 1 <= (size := _length(office.attr(marks, "size", "pt"))) <= 400:
            sub(run, "w:sz", {"w:val": round(size * 2)})
            sub(run, "w:szCs", {"w:val": round(size * 2)})
        if "underline" in marks:
            sub(run, "w:u", {"w:val": "none" if marks["underline"] is False else "single"})
        if len(run):
            parent.append(run)
        if lines or bands:
            table = sub(parent, "w:tblPr")
            for key, tag in (
                ("rows", "w:tblStyleRowBandSize"),
                ("columns", "w:tblStyleColBandSize"),
            ):
                if bands:
                    sub(table, tag, {"w:val": bands[key]})
            self._edges(table, "w:tblBorders", lines or {})
        cell = etree.Element(q("w:tcPr"))
        self._edges(cell, "w:tcBorders", part.get("edges") or {})
        if "fill" in part:
            sub(cell, "w:shd", self._shading(part["fill"]))
        if part.get("valign"):
            sub(cell, "w:vAlign", {"w:val": part["valign"]})
        if len(cell):
            parent.append(cell)

    @staticmethod
    def _edges(parent, tag: str, edges: dict) -> None:
        if not edges:
            return
        found = sub(parent, tag)
        for side in EDGE_ORDER:
            if side not in edges:
                continue
            edge = designs.drawn(edges[side])
            if edge is None:
                sub(found, f"w:{side}", {"w:val": "nil"})
                continue
            color = office.solid("text", edge.get("color")) or "auto"
            sub(
                found,
                f"w:{side}",
                {
                    "w:val": edge["line"],
                    "w:sz": round(edge["width"] * 8),
                    "w:space": 0,
                    "w:color": color,
                },
            )

    @staticmethod
    def _shading(fill: str) -> dict:
        """A fill as cell shading, none taking away a style's."""
        shown = office.solid("highlight", fill) if fill != designs.NONE else None
        return {"w:val": "clear", "w:color": "auto", "w:fill": shown or "auto"}

    def _shown(self, table: Block, cell: blocks.Cell) -> list[Block]:
        found = office.shown(table, cell)
        if cell.blocks and found[0] is not cell.blocks[0]:
            for block in cell.blocks[1:]:
                for offset, events in self.points.pop(block.id, {}).items():
                    self.points.setdefault(found[0].id, {}).setdefault(offset, []).extend(events)
        return found

    # Pictures

    def _image(self, parent, block: Block) -> None:
        paragraph = sub(parent, "w:p")
        if (align := block.attrs.get("align")) in ("center", "right"):
            sub(sub(paragraph, "w:pPr"), "w:jc", {"w:val": align})
        sha256 = block.attrs.get("blob")
        if not isinstance(sha256, str):
            return
        picture, original, (width, height) = self._media(sha256)
        rid = self.part.relate_to(picture, RT.IMAGE)
        svg = self.part.relate_to(original, RT.IMAGE) if original else None
        across = self.width * EMU_PER_CM
        share = _length(block.attrs.get("width"))
        cx = across * share / 100 if 0 < share <= 100 else min(width * EMU_PER_PIXEL, across)
        alt = block.attrs.get("alt") if isinstance(block.attrs.get("alt"), str) else ""
        run = sub(self._proposed(paragraph, block.attrs), "w:r")
        self._drawing(run, rid, svg, round(cx), round(cx * height / width), alt)

    def _pdf(self, parent, block: Block) -> None:
        """Each page the block shows as a picture of it across the block's share of the text,
        no taller than the page's: Word shows a PDF only as an object of Acrobat's."""
        share = _length(block.attrs.get("width"))
        across = self.width * (share if 0 < share <= 100 else 100) / 100
        title = block.attrs.get("title") if isinstance(block.attrs.get("title"), str) else ""
        for number, (width, height) in pictures.pages_of(block.attrs):
            wide = min(across, self.height * width / height)
            paragraph = sub(parent, "w:p")
            if (align := block.attrs.get("align")) in ("center", "right"):
                sub(sub(paragraph, "w:pPr"), "w:jc", {"w:val": align})
            key = f"{block.attrs['blob']}/{number}"
            if key not in self.media:
                picture = pictures.page_picture(block.attrs["blob"], number, wide / 2.54)
                name = f"/word/media/page{len(self.media) + 1}.png"
                self.media[key] = (Part(PackURI(name), "image/png", picture.data), None, (0, 0))
            rid = self.part.relate_to(self.media[key][0], RT.IMAGE)
            cx = wide * EMU_PER_CM
            alt = f"{title} · {number}" if title else str(number)
            run = sub(self._proposed(paragraph, block.attrs), "w:r")
            self._drawing(run, rid, None, round(cx), round(cx * height / width), alt)

    def _media(self, sha256: str) -> tuple[Part, Part | None, tuple[float, float]]:
        """An image's picture in the file, once however often it shows: Word's own formats as
        they are, a photo turned upright, WebP and AVIF as PNG, an SVG beside a PNG of it."""
        if sha256 not in self.media:
            picture = pictures.picture_of(sha256)
            number = len(self.media) + 1
            original = None
            if picture.svg is not None:
                name = f"/word/media/image{number}.svg"
                original = Part(PackURI(name), "image/svg+xml", picture.svg)
            name = f"/word/media/picture{number}.{store.IMAGES[picture.media_type]}"
            part = Part(PackURI(name), picture.media_type, picture.data)
            self.media[sha256] = (part, original, picture.size)
        return self.media[sha256]

    def _drawing(self, run, rid: str, svg: str | None, cx: int, cy: int, alt: str) -> None:
        self.drawings += 1
        number = self.drawings
        inline = sub(sub(run, "w:drawing"), "wp:inline", {f"dist{side}": 0 for side in "TBLR"})
        sub(inline, "wp:extent", {"cx": cx, "cy": cy})
        sub(inline, "wp:docPr", {"id": number, "name": f"Picture {number}", "descr": alt})
        locks = sub(inline, "wp:cNvGraphicFramePr")
        sub(locks, "a:graphicFrameLocks", {"noChangeAspect": 1})
        data = sub(sub(inline, "a:graphic"), "a:graphicData", {"uri": PIC})
        picture = sub(data, "pic:pic")
        names = sub(picture, "pic:nvPicPr")
        sub(names, "pic:cNvPr", {"id": number, "name": f"Picture {number}", "descr": alt})
        sub(names, "pic:cNvPicPr")
        fill = sub(picture, "pic:blipFill")
        blip = sub(fill, "a:blip", {"r:embed": rid})
        if svg:
            extension = sub(sub(blip, "a:extLst"), "a:ext", {"uri": SVG_BLIP})
            sub(extension, "asvg:svgBlip", {"r:embed": svg})
        sub(sub(fill, "a:stretch"), "a:fillRect")
        shape = sub(picture, "pic:spPr")
        frame = sub(shape, "a:xfrm")
        sub(frame, "a:off", {"x": 0, "y": 0})
        sub(frame, "a:ext", {"cx": cx, "cy": cy})
        sub(sub(shape, "a:prstGeom", {"prst": "rect"}), "a:avLst")

    # Charts

    def _chart(self, parent, block: Block) -> None:
        """A chart across the text, over the document's tables as a workbook of its own, so
        Word edits its data in Excel as its own chart's."""
        chart = drawn.chart_of(block.attrs)
        sheet = self.book.sheet(chart.table) if chart is not None and self.book else None
        self.charts += 1
        number = self.charts
        element = charts.space(
            block.attrs, sheet, styles.family(self.theme, self.looks["text"]["font"])
        )
        part = XmlPart(
            PackURI(f"/word/charts/chart{number}.xml"), CT.DML_CHART, element, self.package
        )
        if sheet is not None:
            name = f"/word/embeddings/Microsoft_Excel_Worksheet{number}.xlsx"
            embedded = Part(PackURI(name), CT.SML_SHEET, self.workbook, self.package)
            charts.linked(element, part.relate_to(embedded, RT.PACKAGE))
        rid = self.part.relate_to(part, RT.CHART)
        cx, cy = charts.size(self.width)
        self.drawings += 1
        run = sub(self._proposed(sub(parent, "w:p"), block.attrs), "w:r")
        inline = sub(sub(run, "w:drawing"), "wp:inline", {f"dist{side}": 0 for side in "TBLR"})
        sub(inline, "wp:extent", {"cx": cx, "cy": cy})
        title = block.attrs.get("title") if isinstance(block.attrs.get("title"), str) else ""
        props = {"id": self.drawings, "name": f"Chart {number}", "descr": title.strip()}
        sub(inline, "wp:docPr", props)
        sub(inline, "wp:cNvGraphicFramePr")
        data = sub(sub(inline, "a:graphic"), "a:graphicData", {"uri": charts.C})
        sub(data, "c:chart", {"r:id": rid})

    @cached_property
    def book(self) -> xlsx.Computed | None:
        try:
            return xlsx.computed(self.document)
        except xlsx.Empty:
            return None

    @cached_property
    def workbook(self) -> bytes:
        return self.book.written()

    def _rule(self, parent, block: Block) -> None:
        """A horizontal line as Word's AutoFormat draws one: an empty paragraph's bottom
        border."""
        paragraph = sub(parent, "w:p")
        borders = sub(sub(paragraph, "w:pPr"), "w:pBdr")
        sub(borders, "w:bottom", {"w:val": "single", "w:sz": 4, "w:space": 1, "w:color": "auto"})
        self._proposed(paragraph, block.attrs)

    # Contents

    def _contents(self, parent, block: Block) -> None:
        """Word's table of contents of the document's headings, which Word updates with their
        pages on opening the file."""
        depth = block.attrs.get("depth")
        depth = int(depth) if depth in LEVELS else CONTENTS_DEPTH
        entries = [(level, text) for level, text in self.headings if level <= depth] or [(1, "")]
        paragraphs = []
        for level, text in entries:
            paragraph = sub(parent, "w:p")
            sub(sub(paragraph, "w:pPr"), "w:pStyle", {"w:val": f"TOC{level}"})
            paragraphs.append((self._proposed(paragraph, block.attrs), text))
        first = paragraphs[0][0]
        self._char(first, "begin", dirty=True)
        instruction = f' TOC \\o "1-{depth}" \\h \\z \\u '
        tag = "w:delInstrText" if first.tag == q("w:del") else "w:instrText"
        sub(sub(first, "w:r"), tag, {"xml:space": "preserve"}, instruction)
        self._char(first, "separate")
        for paragraph, text in paragraphs:
            if text:
                self._run(paragraph, office.INVALID.sub("", text), {})
        self._char(paragraphs[-1][0], "end")

    # Comments

    def _threads(self, tab, doc: Doc, content: list[Block]) -> dict:
        """Where the tab's comments start and end, by block and offset; a thread whose text is
        gone, or hidden under a merged cell, stands at the start of the tab's text, in an empty
        paragraph put first where the tab has no text."""
        comments = Prefetch(
            "comments", Comment.objects.select_related("author").order_by("created_at")
        )
        threads = list(tab.threads.order_by("created_at").prefetch_related(comments))
        if not threads:
            return {}
        read = blocks.in_order(content)
        order = {block.id: at for at, block in enumerate(read)}
        ends = []
        for thread in threads:
            anchor = thread.anchor if isinstance(thread.anchor, dict) else {}
            ends += [anchor.get("from"), anchor.get("to")]
        found = located(doc, ends)
        first = next((block for block in read if block.type in office.TEXTUAL), None)
        if first is None:
            first = Block("paragraph")
            content.insert(0, first)
        fallback = (first.id, 0)
        points: dict = {}
        for index, thread in enumerate(threads):
            start, end = found[2 * index], found[2 * index + 1]
            if start is None or end is None or start[0] not in order or end[0] not in order:
                start = end = fallback
            elif (order.get(end[0], 0), end[1]) < (order.get(start[0], 0), start[1]):
                start, end = end, start
            parent = None
            for comment in thread.comments.all():
                id = len(self.comments)
                self.comments.append((comment, parent, thread.resolved_at is not None))
                self.placed.append(set())
                parent = id if parent is None else parent
                points.setdefault(start[0], {}).setdefault(start[1], []).append(("start", id))
                points.setdefault(end[0], {}).setdefault(end[1], []).append(("end", id))
        return points

    def _point(self, paragraph, kind: str, id: int) -> None:
        if kind == "start":
            sub(paragraph, "w:commentRangeStart", {"w:id": id})
        else:
            sub(paragraph, "w:commentRangeEnd", {"w:id": id})
            run = sub(paragraph, "w:r")
            sub(sub(run, "w:rPr"), "w:rStyle", {"w:val": "CommentReference"})
            sub(run, "w:commentReference", {"w:id": id})
        self.placed[id].add(kind)

    def _comments(self) -> None:
        if not self.comments:
            return
        if unplaced := [id for id, kinds in enumerate(self.placed) if kinds != {"start", "end"}]:
            raise RuntimeError(f"comments {unplaced} have no place in the text")
        element, extended = root("w:comments"), root("w15:commentsEx")
        for id, (comment, parent, resolved) in enumerate(self.comments):
            author = comment.author
            name = comment.outside_author or (author and (author.get_full_name() or author.email))
            date = comment.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            attrs = {"w:id": id, "w:author": name or "", "w:date": date}
            written = sub(element, "w:comment", attrs)
            lines = office.INVALID.sub("", comment.body).split("\n")
            for index, line in enumerate(lines):
                paragraph = sub(written, "w:p")
                if index == len(lines) - 1:
                    paragraph.set(q("w14:paraId"), f"{id + 1:08X}")
                sub(sub(paragraph, "w:pPr"), "w:pStyle", {"w:val": "CommentText"})
                if index == 0:
                    run = sub(paragraph, "w:r")
                    sub(sub(run, "w:rPr"), "w:rStyle", {"w:val": "CommentReference"})
                    sub(run, "w:annotationRef")
                if line:
                    self._run(paragraph, line, {})
            attrs = {"w15:paraId": f"{id + 1:08X}", "w15:done": int(resolved and parent is None)}
            if parent is not None:
                attrs["w15:paraIdParent"] = f"{parent + 1:08X}"
            sub(extended, "w15:commentEx", attrs)
        self._related("/word/comments.xml", CT.WML_COMMENTS, element, RT.COMMENTS)
        self._related(
            "/word/commentsExtended.xml", COMMENTS_EXTENDED_TYPE, extended, COMMENTS_EXTENDED
        )

    # The rest of the package

    def _numbering(self) -> None:
        if not self.numbers.made:
            return
        element = root("w:numbering")
        hanging = round(MARKER_EM * self.size * 20)
        for num in self.numbers.made:
            abstract = sub(element, "w:abstractNum", {"w:abstractNumId": num.id})
            sub(abstract, "w:multiLevelType", {"w:val": "multilevel"})
            for level, form in enumerate(num.forms):
                kept = sub(abstract, "w:lvl", {"w:ilvl": level})
                sub(kept, "w:start", {"w:val": num.starts.get(level, 1)})
                sub(kept, "w:numFmt", {"w:val": _format_of(form)})
                text = _text_of(num.forms, level)
                if num.inline:
                    sub(kept, "w:suff", {"w:val": "space" if text else "nothing"})
                sub(kept, "w:lvlText", {"w:val": text})
                sub(kept, "w:lvlJc", {"w:val": "left"})
                if not num.inline:
                    left = twips(level * INDENT_STEP) + hanging
                    sub(sub(kept, "w:pPr"), "w:ind", {"w:left": left, "w:hanging": hanging})
        for num in self.numbers.made:
            sub(sub(element, "w:num", {"w:numId": num.id}), "w:abstractNumId", {"w:val": num.id})
        self._related("/word/numbering.xml", CT.WML_NUMBERING, element, RT.NUMBERING)

    def _notes(self) -> None:
        kinds = (
            ("foot", "footnote", CT.WML_FOOTNOTES, RT.FOOTNOTES),
            ("end", "endnote", CT.WML_ENDNOTES, RT.ENDNOTES),
        )
        for kind, tag, content_type, reltype in kinds:
            if not self.notes[kind]:
                continue
            element = root(f"w:{tag}s")
            self.part, _ = self._related(f"/word/{tag}s.xml", content_type, element, reltype)
            for id, separator in ((-1, "separator"), (0, "continuationSeparator")):
                note = sub(element, f"w:{tag}", {"w:type": separator, "w:id": id})
                sub(sub(sub(note, "w:p"), "w:r"), f"w:{separator}")
            for id, runs in enumerate(self.notes[kind], 1):
                paragraph = sub(sub(element, f"w:{tag}", {"w:id": id}), "w:p")
                sub(sub(paragraph, "w:pPr"), "w:pStyle", {"w:val": f"{tag.title()}Text"})
                run = sub(paragraph, "w:r")
                sub(sub(run, "w:rPr"), "w:rStyle", {"w:val": f"{tag.title()}Reference"})
                sub(run, f"w:{tag}Ref")
                self._run(paragraph, " ", {})
                link: list = [None, None]
                for each in runs:
                    self._text(paragraph, link, each.text, each.marks)
        self.part = self.main

    def _settings(self) -> None:
        element = root("w:settings")
        sub(element, "w:defaultTabStop", {"w:val": twips(DEFAULT_STOP)})
        sub(element, "w:characterSpacingControl", {"w:val": "doNotCompress"})
        for kind, tag, format in (
            ("foot", "footnote", "decimal"),
            ("end", "endnote", "lowerRoman"),
        ):
            if not self.notes[kind]:
                continue
            props = sub(element, f"w:{tag}Pr")
            if kind == "end":
                sub(props, "w:pos", {"w:val": "sectEnd"})
            sub(props, "w:numFmt", {"w:val": format})
            for id in (-1, 0):
                sub(props, f"w:{tag}", {"w:id": id})
        compat = sub(element, "w:compat")
        sub(
            compat,
            "w:compatSetting",
            {
                "w:name": "compatibilityMode",
                "w:uri": "http://schemas.microsoft.com/office/word",
                "w:val": 15,
            },
        )
        self._related("/word/settings.xml", CT.WML_SETTINGS, element, RT.SETTINGS)


def word_file(document: Node, site: str) -> bytes:
    """The document as a docx; `site` is the address its own links are relative to."""
    return Writer(document, site).written()
