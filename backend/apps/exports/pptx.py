"""A document as a PowerPoint file: every tab's slides in order, each tab a section; the slide
template as one master with its layouts, each layout's boxes its placeholders; a slide's text in
the placeholders of its layout, shrunk as far as the Slides view shrinks it, its pictures, tables
and charts where that view shows them, as the printer measures it there (frontend editor/deck.ts
`measuredSlides`), its speaker notes as its notes, its own background over its layout's, and a
hidden slide hidden. A proposal is not
the text until it is accepted, so the file holds the text as it was before its proposals."""

import io
import re
import uuid
from collections import Counter
from dataclasses import replace
from functools import cached_property
from urllib.parse import urljoin

from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.package import OpcPackage
from docx.opc.packuri import PackURI
from docx.opc.part import Part, XmlPart
from lxml import etree

from apps.blobs import store
from apps.content import blocks, designs, fonts, grids, lists, numbering, palette, slides, styles
from apps.content import charts as drawn
from apps.content.blocks import Block, Field, Run
from apps.content.numbering import numeral
from apps.content.schema import LISTS
from apps.documents.models import Node
from apps.imports.powerpoint import (
    ALIGNS,
    ANCHORS,
    CLR_MAP,
    DASHES,
    EMU_PER_POINT,
    FIELDS,
    LAYOUT_TYPES,
    NO_STYLE,
    P14,
    SCHEMES,
    SECTIONS,
    STROKES,
    SWITCHES,
    TABLE,
    P,
    built_in_id,
)
from apps.imports.pptx import Looks, Master, themed

from . import charts, office, pictures, xlsx
from .charts import EMU_PER_CM
from .docx import SVG, SVG_BLIP
from .xlsx import CHARACTER_CM, doc_of

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"p": P, "a": A, "r": R, "c": charts.C, "p14": P14}
FIRST_MASTER = 2147483648
FIRST_FIELD = 10
# The Slides view's (index.css, deck.ts): a slide's line height and space before a block, in em;
# a list marker's room, in em; a text box's inset, in cm.
LINE = 1.15
BEFORE = 0.35
MARKER = 1.75
INSET = (0.254, 0.127)
STROKE_OF = {ours: theirs for theirs, ours in STROKES.items()}
DASH_OF = {ours: theirs for theirs, ours in reversed(DASHES.items())}
VALIGNS = {"top": "t", "center": "ctr", "bottom": "b"}
# PowerPoint's single line spacing is 1.2 times the font's size.
SINGLE = 1.2
NOTES_SIZE = (6858000, 9144000)
LAYOUT_NAMES = {
    "hr": {
        "title": "Naslovni slajd",
        "content": "Naslov i sadržaj",
        "two": "Dva sadržaja",
        "section": "Zaglavlje odjeljka",
        "titleOnly": "Samo naslov",
        "blank": "Prazno",
    },
    "en": {
        "title": "Title Slide",
        "content": "Title and Content",
        "two": "Two Content",
        "section": "Section Header",
        "titleOnly": "Title Only",
        "blank": "Blank",
    },
}
CHECKS = {False: "☐", True: "☑"}
OBJECTS = {"image", "pdf", "table", "chart", "horizontalRule"}
# As thick as the line the page draws: one CSS pixel.
RULE_POINTS = 0.75
COLOR = re.compile(r"^#[0-9a-f]{6}$")


class Unmeasured(Exception):
    """The printer measured slides other than the document's as it is now."""


def q(name: str) -> str:
    prefix, _, local = name.partition(":")
    return f"{{{NS[prefix]}}}{local}"


def sub(parent, tag: str, attrs: dict | None = None, text: str | None = None):
    element = etree.SubElement(
        parent, q(tag), {q(k) if ":" in k else k: str(v) for k, v in (attrs or {}).items()}
    )
    if text is not None:
        element.text = text
    return element


def root(tag: str):
    return etree.Element(q(tag), nsmap={"a": A, "r": R, "p": P})


def emu(cm: float) -> int:
    return round(cm * EMU_PER_CM)


def _number(value) -> float | None:
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool) and value == value
        else None
    )


def _points(value) -> float | None:
    size = _number(value)
    return size if size and 1 <= size <= 400 else None


def _color(value) -> str | None:
    return value[1:].upper() if isinstance(value, str) and COLOR.match(value) else None


def _typeface(font) -> str | None:
    if font == "headings":
        return "+mj-lt"
    if font == "text":
        return "+mn-lt"
    return fonts.office(font) if isinstance(font, str) and font else None


def _size(look: dict, level: int) -> float | None:
    levels = look.get("levels") if isinstance(look.get("levels"), list) else []
    return (_points(levels[level]) if level < len(levels) else None) or _points(look.get("size"))


def _frame(parent, x: float, y: float, w: float, h: float, tag="a:xfrm", flip=False):
    frame = sub(parent, tag, {"flipV": 1} if flip else None)
    sub(frame, "a:off", {"x": emu(x), "y": emu(y)})
    sub(frame, "a:ext", {"cx": max(emu(w), 0), "cy": max(emu(h), 0)})
    return frame


def _solid(parent, color: str) -> None:
    sub(sub(parent, "a:solidFill"), "a:srgbClr", {"val": color})


def _painted(parent, tint: str, kind: str) -> None:
    """A tint as a colour of DrawingML, its alpha kept."""
    if re.fullmatch(r"#[0-9a-f]{8}", tint):
        color = sub(parent, "a:srgbClr", {"val": tint[1:7].upper()})
        sub(color, "a:alpha", {"val": round(int(tint[7:], 16) / 255 * 100000)})
    else:
        shown = palette.text(tint) if kind == "text" else palette.highlight(tint)
        sub(parent, "a:srgbClr", {"val": shown or "000000"})


def _filled(parent, fill: str | dict) -> None:
    """A design's fill, a tint, a gradient or none, as DrawingML's."""
    if fill == designs.NONE:
        sub(parent, "a:noFill")
    elif isinstance(fill, dict):
        gradient = sub(parent, "a:gradFill", {"rotWithShape": 1})
        stops = sub(gradient, "a:gsLst")
        for stop in fill["stops"]:
            _painted(sub(stops, "a:gs", {"pos": round(stop["at"] * 1000)}), stop["color"], "fill")
        sub(gradient, "a:lin", {"ang": round(fill["angle"] * 60000), "scaled": 0})
    else:
        _painted(sub(parent, "a:solidFill"), fill, "fill")


def _stroked(parent, tag: str, edge: dict | str | None) -> None:
    """An edge as an a:ln, or the like, draws it."""
    line = designs.drawn(edge)
    if line is None:
        sub(sub(parent, tag, {"w": 0}), "a:noFill")
        return
    dash = DASH_OF.get(line["line"])
    element = sub(
        parent,
        tag,
        {"w": round(line["width"] * EMU_PER_POINT), "cmpd": STROKE_OF.get(line["line"], "sng")},
    )
    if line.get("color"):
        _painted(sub(element, "a:solidFill"), line["color"], "text")
    else:
        sub(sub(element, "a:solidFill"), "a:schemeClr", {"val": "tx1"})
    if dash:
        sub(element, "a:prstDash", {"val": dash})


def _tree(site):
    tree = sub(site, "p:spTree")
    names = sub(tree, "p:nvGrpSpPr")
    sub(names, "p:cNvPr", {"id": 1, "name": ""})
    sub(names, "p:cNvGrpSpPr")
    sub(names, "p:nvPr")
    frame = sub(sub(tree, "p:grpSpPr"), "a:xfrm")
    for tag in ("a:off", "a:chOff"):
        sub(frame, tag, {"x": 0, "y": 0})
    for tag in ("a:ext", "a:chExt"):
        sub(frame, tag, {"cx": 0, "cy": 0})
    return tree


def _named(tree, tag: str, kind: str):
    """A new shape on the tree, by its tag, and its non-visual properties, its id after the
    tree's own and the shapes before it."""
    id = len(tree)
    shape = sub(tree, tag)
    prefix, local = tag.split(":")
    names = sub(shape, f"{prefix}:nv{local[0].upper()}{local[1:]}Pr")
    sub(names, "p:cNvPr", {"id": id, "name": f"{kind} {id}"})
    return shape, names


def _spacing(props, size: float, before: bool) -> None:
    sub(sub(props, "a:lnSpc"), "a:spcPct", {"val": round(LINE / SINGLE * 100000)})
    sub(sub(props, "a:spcBef"), "a:spcPts", {"val": round(BEFORE * size * 100) if before else 0})


def _list_style(parent, tag: str, look: dict):
    """A box's text look as the list style its placeholder or text box keeps for each level."""
    style = sub(parent, tag)
    for level in range(9):
        props = sub(style, f"a:lvl{level + 1}pPr")
        if (align := look.get("align")) in ALIGNS:
            props.set("algn", ALIGNS[align])
        size = _size(look, level)
        _spacing(props, size or 18, True)
        sub(props, "a:buNone")
        defaults = sub(props, "a:defRPr")
        if size:
            defaults.set("sz", str(round(size * 100)))
        for name, attr in (("bold", "b"), ("italic", "i")):
            if isinstance(look.get(name), bool):
                defaults.set(attr, "1" if look[name] else "0")
        if color := _color(look.get("color")):
            _solid(defaults, color)
        if typeface := _typeface(look.get("font")):
            sub(defaults, "a:latin", {"typeface": typeface})
    return style


def _body_props(parent, anchor=None, fit: float | None = 1) -> None:
    """A text body's properties: its text shrunk to fit its shape, by `fit` so far, or not
    shrunk where `fit` is None."""
    props = sub(parent, "a:bodyPr", {"wrap": "square"})
    if anchor in ANCHORS:
        props.set("anchor", ANCHORS[anchor])
    if fit is None:
        sub(props, "a:noAutofit")
        return
    autofit = sub(props, "a:normAutofit")
    if fit < 1:
        autofit.set("fontScale", str(round(fit * 100000)))


def _sized(size: float | None, emphasis: dict) -> float | None:
    """A run's size in points: its own, or its paragraph's where that is written out, shrunk
    as far as the paragraph is."""
    return size * emphasis.get("scale", 1) if size else emphasis.get("size")


class Numbers:
    """Where PowerPoint's own numbers start for the items of a text, which it counts on through
    the items of a level written in one scheme, from the start of their first."""

    def __init__(self):
        self.runs: dict[int, tuple[str, int, int]] = {}

    def drop(self, level: int = 0) -> None:
        self.runs = {at: run for at, run in self.runs.items() if at < level}

    def start(self, level: int, scheme: str, value: int) -> int | None:
        """The start to write for an item numbered `value`; None where PowerPoint would count it
        on from the items before, though it starts again, so its number is written out."""
        run = self.runs.get(level)
        self.drop(level)
        if run and run[0] == scheme and run[2] + 1 == value:
            self.runs[level] = (scheme, run[1], value)
            return run[1]
        if run and run[0] == scheme and run[1] == value:
            return None
        self.runs[level] = (scheme, value, value)
        return value


class Writer:
    def __init__(self, document: Node, site: str, measured: dict[str, list]):
        self.document, self.site, self.measured = document, site, measured
        self.own = doc_of(document.room)
        self.theme, self.looks = styles.read(self.own)
        self.formats = lists.read(self.own)
        self.template = slides.template_of(self.own)
        self.built_in = slides.built_in(self.template.width, self.template.height)
        self.language = office.language_of(document)
        self.today = office.today(document)
        self.package = OpcPackage()
        self.root = root("p:presentation")
        self.root.set("saveSubsetFonts", "1")
        self.main = XmlPart(
            PackURI("/ppt/presentation.xml"), CT.PML_PRESENTATION_MAIN, self.root, self.package
        )
        self.package.relate_to(self.main, RT.OFFICE_DOCUMENT)
        self.layouts: list[dict] = list(self.template.layouts)
        self.layout_parts: list[XmlPart] = []
        self.media: dict[str, tuple[Part, Part | None]] = {}
        self.notes = self.charts = self.number = self.total = 0

    def written(self) -> bytes:
        tabs = []
        for tab in self.document.tabs_in_order():
            content = blocks.read(doc_of(tab.room), grids.of_tab(tab))
            measured = self.measured.get(str(tab.pk))
            if not isinstance(measured, list) or len(measured) != len(slides.slides_of(content)):
                raise Unmeasured(str(tab.pk))
            for slide in measured:
                if not isinstance(slide, dict):
                    raise Unmeasured(f"a slide measured as {slide!r}")
                slide["layout"] = self._layout_index(slide.get("layout"))
            self.total += len(measured)
            tabs.append((tab, content, measured))
        theme = self._theme(1)
        scheme, faces, formats = themed(theme.element)
        self.drawing = Master(None, None, scheme, dict(CLR_MAP), faces, {}, formats=formats)
        master = self._master(theme)
        listed = sub(self.root, "p:sldMasterIdLst")
        rid = self.main.relate_to(master, RT.SLIDE_MASTER)
        sub(listed, "p:sldMasterId", {"id": FIRST_MASTER, "r:id": rid})
        self.notes_master = self._notes_master()
        listed = sub(self.root, "p:notesMasterIdLst")
        rid = self.main.relate_to(self.notes_master, RT.NOTES_MASTER)
        sub(listed, "p:notesMasterId", {"r:id": rid})
        listed = sub(self.root, "p:sldIdLst")
        sections = []
        for tab, content, measured in tabs:
            ids = []
            for slide, run in zip(measured, slides.slides_of(content), strict=True):
                self.number += 1
                own = run[0].attrs.get("background") if slides.starts_slide(run[0]) else None
                rid = self.main.relate_to(self._slide(content, slide, own), RT.SLIDE)
                ids.append(255 + self.number)
                sub(listed, "p:sldId", {"id": ids[-1], "r:id": rid})
            sections.append((tab, ids))
        if not len(listed):
            self.root.remove(listed)
        sub(self.root, "p:sldSz", {"cx": emu(self.template.width), "cy": emu(self.template.height)})
        sub(self.root, "p:notesSz", {"cx": NOTES_SIZE[0], "cy": NOTES_SIZE[1]})
        self._sections(sections)
        self.main.relate_to(theme, RT.THEME)
        self._props()
        office.core(self.package, self.document)
        found = io.BytesIO()
        self.package.save(found)
        return found.getvalue()

    # The template

    def _layout_index(self, layout) -> int:
        """The place of a measured slide's layout among the master's: the template's, or its
        kind's, the built-in one added where the template has none of it."""
        if type(layout) is int and 0 <= layout < len(self.template.layouts):
            return layout
        if layout not in slides.KINDS:
            raise Unmeasured(f"a slide's layout {layout!r}")
        for index, each in enumerate(self.layouts):
            if each["kind"] == layout:
                return index
        self.layouts.append(next(each for each in self.built_in if each["kind"] == layout))
        return len(self.layouts) - 1

    def _name_of(self, layout: dict) -> str:
        if isinstance(layout.get("name"), str) and layout["name"].strip():
            return layout["name"].strip()
        names = LAYOUT_NAMES.get(self.language.split("-")[0], LAYOUT_NAMES["en"])
        return names[layout["kind"]]

    def _theme(self, number: int) -> XmlPart:
        element = etree.Element(q("a:theme"), {"name": "Ponistra"}, nsmap={"a": A})
        elements = sub(element, "a:themeElements")
        scheme = sub(elements, "a:clrScheme", {"name": "Ponistra"})
        accents = palette.chart()
        for name, color in (
            ("dk1", "000000"),
            ("lt1", "FFFFFF"),
            ("dk2", palette.text("gray")),
            ("lt2", "F2F2F2"),
            *((f"accent{at + 1}", accents[at % len(accents)]) for at in range(6)),
            ("hlink", palette.text("blue")),
            ("folHlink", palette.text("purple")),
        ):
            sub(sub(scheme, f"a:{name}"), "a:srgbClr", {"val": color})
        scheme = sub(elements, "a:fontScheme", {"name": "Ponistra"})
        for tag, side in (("a:majorFont", "headings"), ("a:minorFont", "text")):
            font = sub(scheme, tag)
            sub(font, "a:latin", {"typeface": fonts.office(styles.family(self.theme, side))})
            sub(font, "a:ea", {"typeface": ""})
            sub(font, "a:cs", {"typeface": ""})
        formats = sub(elements, "a:fmtScheme", {"name": "Ponistra"})
        fills = sub(formats, "a:fillStyleLst")
        for _ in range(3):
            sub(sub(fills, "a:solidFill"), "a:schemeClr", {"val": "phClr"})
        lines = sub(formats, "a:lnStyleLst")
        for width in (6350, 12700, 19050):
            line = sub(lines, "a:ln", {"w": width, "cap": "flat", "cmpd": "sng", "algn": "ctr"})
            sub(sub(line, "a:solidFill"), "a:schemeClr", {"val": "phClr"})
            sub(line, "a:prstDash", {"val": "solid"})
            sub(line, "a:miter", {"lim": 800000})
        effects = sub(formats, "a:effectStyleLst")
        for _ in range(3):
            sub(sub(effects, "a:effectStyle"), "a:effectLst")
        backgrounds = sub(formats, "a:bgFillStyleLst")
        for _ in range(3):
            sub(sub(backgrounds, "a:solidFill"), "a:schemeClr", {"val": "phClr"})
        sub(element, "a:objectDefaults")
        sub(element, "a:extraClrSchemeLst")
        name = PackURI(f"/ppt/theme/theme{number}.xml")
        return XmlPart(name, CT.OFC_THEME, element, self.package)

    def _master(self, theme: XmlPart) -> XmlPart:
        element = root("p:sldMaster")
        site = sub(element, "p:cSld")
        sub(sub(sub(site, "p:bg"), "p:bgRef", {"idx": 1001}), "a:schemeClr", {"val": "bg1"})
        tree = _tree(site)
        main = next((each for each in self.layouts if each["kind"] == "content"), None)
        built = next(each for each in self.built_in if each["kind"] == "content")
        looks = {}
        for role, placeholder in (
            ("title", {"type": "title"}),
            ("body", {"type": "body", "idx": 1}),
        ):
            box = (main or built)["boxes"].get(role) or built["boxes"][role]
            looks[role] = box.get("text") or {}
            shape = self._placeholder(tree, placeholder, role.title(), box)
            body = sub(shape, "p:txBody")
            _body_props(body, looks[role].get("anchor"))
            sub(body, "a:lstStyle")
            sub(sub(body, "a:p"), "a:endParaRPr", {"lang": self.language})
        sub(element, "p:clrMap", CLR_MAP)
        part = XmlPart(
            PackURI("/ppt/slideMasters/slideMaster1.xml"),
            CT.PML_SLIDE_MASTER,
            element,
            self.package,
        )
        part.relate_to(theme, RT.THEME)
        listed = sub(element, "p:sldLayoutIdLst")
        for index, layout in enumerate(self.layouts):
            self.layout_parts.append(self._layout(layout, index + 1, part))
            rid = part.relate_to(self.layout_parts[-1], RT.SLIDE_LAYOUT)
            sub(listed, "p:sldLayoutId", {"id": FIRST_MASTER + index + 1, "r:id": rid})
        kept = sub(element, "p:txStyles")
        _list_style(kept, "p:titleStyle", looks["title"])
        _list_style(kept, "p:bodyStyle", looks["body"])
        _list_style(kept, "p:otherStyle", {})
        return part

    def _layout(self, layout: dict, number: int, master: XmlPart) -> XmlPart:
        element = root("p:sldLayout")
        element.set("type", LAYOUT_TYPES[layout["kind"]])
        element.set("preserve", "1")
        site = sub(element, "p:cSld", {"name": self._name_of(layout)})
        part = XmlPart(
            PackURI(f"/ppt/slideLayouts/slideLayout{number}.xml"),
            CT.PML_SLIDE_LAYOUT,
            element,
            self.package,
        )
        part.relate_to(master, RT.SLIDE_MASTER)
        self._background(site, layout.get("background"), part)
        tree = _tree(site)
        field = FIRST_FIELD
        for shape in layout["shapes"]:
            if shape["type"] in ("number", "date"):
                field += 1
            self._shape(tree, shape, part, field)
        for role, placeholder in self._placeholders(layout).items():
            box = layout["boxes"][role]
            look = box.get("text") or {}
            body = sub(self._placeholder(tree, placeholder, role.title(), box), "p:txBody")
            _body_props(body, look.get("anchor"))
            _list_style(body, "a:lstStyle", look)
            sub(sub(body, "a:p"), "a:endParaRPr", {"lang": self.language})
        sub(sub(element, "p:clrMapOvr"), "a:masterClrMapping")
        drawn = {shape["type"] for shape in layout["shapes"]}
        if drawn & set(FIELDS.values()):
            offered = {type: "0" for type, kind in FIELDS.items() if kind not in drawn}
            sub(element, "p:hf", {"hdr": "0", "ftr": "0", **offered})
        return part

    @staticmethod
    def _placeholders(layout: dict) -> dict[str, dict]:
        """Each box's placeholder: of the type its role takes in a layout of the kind, the title
        the layout's one, the others numbered in the order of their roles."""
        found = {}
        kind = layout["kind"]
        index = 0
        for role in slides.ROLES:
            if role not in layout["boxes"]:
                continue
            if role == "title":
                found[role] = {"type": "ctrTitle" if kind == "title" else "title"}
                continue
            index += 1
            if role == "subtitle":
                found[role] = {"type": "subTitle", "idx": index}
            elif kind in ("title", "section"):
                found[role] = {"type": "body", "idx": index}
            else:
                found[role] = {"idx": index}
        return found

    def _background(self, site, background, part: XmlPart) -> None:
        if not isinstance(background, dict):
            return
        props = sub(sub(site, "p:bg"), "p:bgPr")
        if isinstance(background.get("image"), str):
            fill = sub(props, "a:blipFill", {"dpi": 0, "rotWithShape": 1})
            self._blip(fill, part, background["image"])
            sub(sub(fill, "a:stretch"), "a:fillRect")
        elif color := _color(background.get("color")):
            _solid(props, color)
        else:
            sub(props, "a:noFill")
        sub(props, "a:effectLst")

    def _shape(self, tree, shape: dict, part: XmlPart, field: int) -> None:
        """A layout's shape, behind its slides' text; the slide's number and the date as the
        placeholders PowerPoint fills on each slide."""
        kind = shape["type"]
        frame = (shape["x"], shape["y"], shape["w"], shape["h"])
        if kind == "image":
            self._pictured(tree, part, shape.get("blob"), frame, "")
            return
        if kind == "line":
            line, names = _named(tree, "p:cxnSp", "Line")
            sub(names, "p:cNvCxnSpPr")
            sub(names, "p:nvPr")
            props = sub(line, "p:spPr")
            _frame(props, *frame, flip=shape.get("flip") is True)
            sub(sub(props, "a:prstGeom", {"prst": "line"}), "a:avLst")
            self._line(props, shape.get("line"))
            return
        if kind in ("number", "date"):
            type = "sldNum" if kind == "number" else "dt"
            found = self._placeholder(
                tree, {"type": type, "sz": "quarter", "idx": field}, kind.title(), shape
            )
            props = found.find(q("p:spPr"))
        else:
            found, names = _named(tree, "p:sp", kind.title())
            sub(names, "p:cNvSpPr", {"txBox": 1} if kind == "text" else None)
            sub(names, "p:nvPr")
            props = sub(found, "p:spPr")
            _frame(props, *frame)
        geometry = "ellipse" if kind == "ellipse" else "rect"
        sub(sub(props, "a:prstGeom", {"prst": geometry}), "a:avLst")
        if fill := _color(shape.get("fill")):
            _solid(props, fill)
        else:
            sub(props, "a:noFill")
        self._line(props, shape.get("line"))
        if kind in ("rect", "ellipse"):
            return
        look = shape.get("text") or {}
        body = sub(found, "p:txBody")
        _body_props(body, look.get("anchor"), None)
        _list_style(body, "a:lstStyle", look)
        paragraph = sub(body, "a:p")
        if kind == "text":
            self._run(paragraph, part, shape.get("content") or "", {})
        else:
            self._field(paragraph, kind, "‹#›" if kind == "number" else self.today, {})

    @staticmethod
    def _line(props, line) -> None:
        if not isinstance(line, dict) or not (color := _color(line.get("color"))):
            sub(sub(props, "a:ln"), "a:noFill")
            return
        width = _number(line.get("width")) or 0
        _solid(sub(props, "a:ln", {"w": round(width * EMU_PER_POINT)}), color)

    @staticmethod
    def _placeholder(tree, placeholder: dict, kind: str, place=None, locks: dict | None = None):
        """A placeholder shape, where `place` (a box, or x, y, w and h) puts it, else where its
        layout or master does."""
        shape, names = _named(tree, "p:sp", kind)
        sub(sub(names, "p:cNvSpPr"), "a:spLocks", {"noGrp": 1, **(locks or {})})
        sub(sub(names, "p:nvPr"), "p:ph", placeholder)
        props = sub(shape, "p:spPr")
        if isinstance(place, dict):
            place = (place["x"], place["y"], place["w"], place["h"])
        if place:
            _frame(props, *place)
        return shape

    def _notes_master(self) -> XmlPart:
        element = root("p:notesMaster")
        site = sub(element, "p:cSld")
        sub(sub(sub(site, "p:bg"), "p:bgRef", {"idx": 1001}), "a:schemeClr", {"val": "bg1"})
        tree = _tree(site)
        across, down = NOTES_SIZE
        for placeholder, kind, place in (
            ({"type": "sldImg", "idx": 2}, "Slide Image", (1 / 8, 1 / 12, 3 / 4, 3 / 8)),
            ({"type": "body", "sz": "quarter", "idx": 3}, "Notes", (1 / 10, 1 / 2, 4 / 5, 2 / 5)),
        ):
            locks = {"noRot": 1, "noChangeAspect": 1} if placeholder["type"] == "sldImg" else None
            shape = self._placeholder(tree, placeholder, kind, None, locks)
            frame = sub(shape.find(q("p:spPr")), "a:xfrm")
            x, y, w, h = place
            sub(frame, "a:off", {"x": round(across * x), "y": round(down * y)})
            sub(frame, "a:ext", {"cx": round(across * w), "cy": round(down * h)})
            sub(sub(shape.find(q("p:spPr")), "a:prstGeom", {"prst": "rect"}), "a:avLst")
            if placeholder["type"] == "body":
                body = sub(shape, "p:txBody")
                sub(body, "a:bodyPr")
                sub(body, "a:lstStyle")
                sub(sub(body, "a:p"), "a:endParaRPr", {"lang": self.language})
        sub(element, "p:clrMap", CLR_MAP)
        _list_style(element, "p:notesStyle", {"font": "text", "size": 12})
        part = XmlPart(
            PackURI("/ppt/notesMasters/notesMaster1.xml"),
            CT.PML_NOTES_MASTER,
            element,
            self.package,
        )
        part.relate_to(self._theme(2), RT.THEME)
        return part

    # Slides

    def _slide(self, content: list[Block], slide: dict, background: dict | None) -> XmlPart:
        layout = self.layouts[slide["layout"]]
        element = root("p:sld")
        if slide.get("hidden") is True:
            element.set("show", "0")
        part = XmlPart(
            PackURI(f"/ppt/slides/slide{self.number}.xml"), CT.PML_SLIDE, element, self.package
        )
        part.relate_to(self.layout_parts[slide["layout"]], RT.SLIDE_LAYOUT)
        site = sub(element, "p:cSld")
        self._background(site, background, part)
        tree = _tree(site)
        placeholders = self._placeholders(layout)
        for box in slide.get("boxes") if isinstance(slide.get("boxes"), list) else []:
            if not isinstance(box, dict):
                raise Unmeasured(f"a box measured as {box!r}")
            self._box(tree, part, content, box, placeholders)
        field = FIRST_FIELD
        for shape in layout["shapes"]:
            if shape["type"] not in ("number", "date"):
                continue
            field += 1
            kind = shape["type"]
            placeholder = {"type": "sldNum" if kind == "number" else "dt", "sz": "quarter"}
            found = self._placeholder(tree, {**placeholder, "idx": field}, kind.title())
            body = sub(found, "p:txBody")
            sub(body, "a:bodyPr")
            sub(body, "a:lstStyle")
            shown = str(self.number) if kind == "number" else self.today
            self._field(sub(body, "a:p"), kind, shown, {})
        sub(sub(element, "p:clrMapOvr"), "a:masterClrMapping")
        said = []
        for index in slide.get("notes") if isinstance(slide.get("notes"), list) else []:
            block = self._block(content, index)
            if block.type in office.TEXTUAL:
                said.append(block)
        if said:
            self._notes(part, said)
        return part

    @staticmethod
    def _block(content: list[Block], index) -> Block:
        if type(index) is not int or not 0 <= index < len(content):
            raise Unmeasured(f"a block at {index!r}")
        return content[index]

    def _box(self, tree, part, content, box: dict, placeholders: dict) -> None:
        """A box's blocks: its text in its layout's placeholder, or a text box where the box is
        not the layout's own; around a picture, table or chart, each run of text in a shape of
        its own where the view shows it, and the object where it shows."""
        placeholder = placeholders.get(box.get("key"))
        look = box.get("look") if isinstance(box.get("look"), dict) else {}
        fit = min(max(_number(box.get("fit")) or 1, 0.05), 1)
        placed = []
        for each in box.get("blocks") if isinstance(box.get("blocks"), list) else []:
            if not isinstance(each, list) or len(each) != 5:
                raise Unmeasured(f"a block measured as {each!r}")
            block = self._block(content, each[0])
            frame = [_number(value) for value in each[1:]]
            if None in frame:
                raise Unmeasured(f"a block measured as {each!r}")
            if block.type in OBJECTS and isinstance(block.attrs.get("insertion"), dict):
                continue
            if block.type in office.TEXTUAL or block.type in OBJECTS:
                placed.append((block, frame))
        if not any(block.type in OBJECTS for block, _ in placed):
            shown = [block for block, _ in placed]
            if placeholder is not None:
                self._text(tree, part, shown, look, fit, placeholder)
            elif shown:
                frame = [_number(box.get(side)) for side in ("x", "y", "w", "h")]
                if None in frame:
                    raise Unmeasured(f"a box measured as {box!r}")
                self._text(tree, part, shown, look, fit, None, frame)
            return
        runs: list[list] = []
        for block, frame in placed:
            if block.type in office.TEXTUAL and runs and runs[-1][0].type in office.TEXTUAL:
                runs[-1].append((block, frame))
            elif block.type in office.TEXTUAL:
                runs.append([block, (block, frame)])
            else:
                runs.append([block, frame])
        for run in runs:
            block = run[0]
            if block.type == "image":
                alt = block.attrs.get("alt") if isinstance(block.attrs.get("alt"), str) else ""
                self._pictured(tree, part, block.attrs.get("blob"), run[1], alt)
            elif block.type == "pdf":
                self._pdf(tree, part, block, run[1])
            elif block.type == "table":
                self._table(tree, part, block, run[1], look, fit)
            elif block.type == "chart":
                self._chart(tree, part, block, run[1])
            elif block.type == "horizontalRule":
                self._rule(tree, run[1], look)
            else:
                frames = [frame for _, frame in run[1:]]
                left = min(x for x, _, _, _ in frames)
                top = min(y for _, y, _, _ in frames)
                right = max(x + w for x, _, w, _ in frames)
                bottom = max(y + h for _, y, _, h in frames)
                frame = (
                    left - INSET[0],
                    top - INSET[1],
                    right - left + 2 * INSET[0],
                    bottom - top + 2 * INSET[1],
                )
                shown = [block for block, _ in run[1:]]
                self._text(tree, part, shown, look, fit, placeholder, frame, split=True)
                placeholder = None

    @staticmethod
    def _rule(tree, frame, look) -> None:
        """A horizontal line across the middle of its block's place, in the text's colour."""
        x, y, width, height = frame
        line, names = _named(tree, "p:cxnSp", "Line")
        sub(names, "p:cNvCxnSpPr")
        sub(names, "p:nvPr")
        props = sub(line, "p:spPr")
        _frame(props, x, y + height / 2, width, 0)
        sub(sub(props, "a:prstGeom", {"prst": "line"}), "a:avLst")
        fill = sub(sub(props, "a:ln", {"w": round(RULE_POINTS * EMU_PER_POINT)}), "a:solidFill")
        if color := _color(look.get("color")):
            sub(fill, "a:srgbClr", {"val": color})
        else:
            sub(fill, "a:schemeClr", {"val": "tx1"})

    def _text(self, tree, part, shown, look, fit, placeholder, frame=None, split=False) -> None:
        """Blocks of a box as text, in its placeholder or in a text box at `frame`, so far
        shrunk: by PowerPoint's own shrinking where they are the whole box's, at their sizes
        shrunk where they are a part of it between objects, which keep their places."""
        if placeholder is not None:
            shape = self._placeholder(tree, placeholder, "Text", frame)
        else:
            shape, names = _named(tree, "p:sp", "Text")
            sub(names, "p:cNvSpPr", {"txBox": 1})
            sub(names, "p:nvPr")
            props = sub(shape, "p:spPr")
            _frame(props, *frame)
            sub(sub(props, "a:prstGeom", {"prst": "rect"}), "a:avLst")
            sub(props, "a:noFill")
        body = sub(shape, "p:txBody")
        anchor = "top" if split else None if placeholder else look.get("anchor")
        _body_props(body, anchor, None if split else fit)
        if placeholder is None:
            _list_style(body, "a:lstStyle", look)
        else:
            sub(body, "a:lstStyle")
        self._paragraphs(body, part, shown, look, fit, split)

    def _paragraphs(self, body, part, shown: list[Block], look, fit: float, scaled: bool) -> None:
        items, numbers = lists.Items(), Numbers()
        last = None
        for block in shown:
            if isinstance(block.attrs.get("insertion"), dict) and last is not None:
                held = etree.Element(q("a:p"))
                self._runs(held, part, block, last[1])
                for each in held:
                    last[0][-1].addprevious(each)
                continue
            block = self._before(block)
            listed = block.type == "paragraph" and block.attrs.get("list") in LISTS
            if not listed:
                items.end()
                numbers.drop()
            item = items.step(block.attrs) if listed else None
            first = last is None
            last = self._paragraph(body, part, block, look, fit, item, numbers, first, scaled)
        if not len(body.findall(q("a:p"))):
            sub(sub(body, "a:p"), "a:endParaRPr", {"lang": self.language})

    @staticmethod
    def _before(block: Block) -> Block:
        """A block whose formatting is proposed, as it was before."""
        formatting = block.attrs.get("formatting")
        before = formatting.get("before") if isinstance(formatting, dict) else None
        if not isinstance(before, dict):
            return block
        attrs = before.get("attrs") if isinstance(before.get("attrs"), dict) else {}
        type = before.get("type") if before.get("type") in office.TEXTUAL else "paragraph"
        return Block(type, block.id, attrs, block.runs)

    def _emphasis(self, block: Block, look: dict) -> dict:
        """What a block's style gives its text where the box's look leaves it."""
        kind = numbering.kind_of(block) or "text"
        own = block.attrs.get("style")
        style = self.looks[own if own in self.looks and self.looks[own]["kind"] == kind else kind]
        found = {name: True for name in ("bold", "italic") if name not in look and style[name]}
        if "color" not in look and (color := palette.text(style.get("color"))):
            found["color"] = color
        return found

    def _paragraph(self, body, part, block, look, fit, item, numbers, first: bool, scaled: bool):
        paragraph = sub(body, "a:p")
        props = sub(paragraph, "a:pPr")
        level = item[1] if item else 0
        size = (_size(look, level) or 18) * fit
        if item:
            props.set("lvl", str(level))
        if (align := block.attrs.get("align")) in ALIGNS:
            props.set("algn", ALIGNS[align])
        indent = _number(block.attrs.get("indent")) or 0
        marker = self._marker(block, item, numbers) if item else None
        if item:
            hanging = MARKER * size * EMU_PER_POINT
            props.set("marL", str(round(emu(indent) + hanging)))
            props.set("indent", str(-round(hanging)))
        else:
            if indent:
                props.set("marL", str(emu(indent)))
            if first_line := _number(block.attrs.get("firstLine")):
                props.set("indent", str(emu(first_line)))
        if right := _number(block.attrs.get("right")):
            props.set("marR", str(emu(right)))
        _spacing(props, size, not first)
        emphasis = self._emphasis(block, look)
        if scaled:
            emphasis |= {"size": size, "scale": fit}
        if marker is None or marker[0] == "text":
            sub(props, "a:buNone")
        elif marker[0] == "char":
            sub(props, "a:buFontTx")
            sub(props, "a:buChar", {"char": marker[1]})
        else:
            sub(props, "a:buFontTx")
            sub(props, "a:buAutoNum", {"type": marker[1], "startAt": marker[2]})
        if marker and marker[0] == "text":
            self._run(paragraph, part, marker[1] + "\t", {}, emphasis)
        self._runs(paragraph, part, block, emphasis)
        ended = sub(paragraph, "a:endParaRPr", {"lang": self.language})
        kept = block.attrs.get("endMarks")
        pt = _points(office.attr(kept, "size", "pt")) if isinstance(kept, dict) else None
        if ended_size := _sized(pt, emphasis):
            ended.set("sz", str(round(ended_size * 100)))
        return paragraph, emphasis

    def _marker(self, block: Block, item, numbers: Numbers):
        """An item's marker: a character, PowerPoint's own number where it counts in the form,
        else the number written out."""
        kind, level, counts = item
        if kind == "check":
            numbers.drop(level)
            return "char", CHECKS[block.attrs.get("checked") is True]
        format = self.formats.get(block.attrs.get("format"))
        form = lists.level_in(format, kind, level)
        if not form["numbering"]:
            numbers.drop(level)
            shown = form["prefix"] + form["suffix"]
            return ("char", shown) if shown else None
        value = counts[level][1]
        above = [
            numeral(count[1], lists.level_in(format, "number", at)["numbering"])
            for at, count in enumerate(counts[:level])
            if form["nested"]
            and count
            and count[0] == "number"
            and lists.level_in(format, "number", at)["numbering"]
        ]
        scheme = SCHEMES.get((form["numbering"], form["prefix"], form["suffix"]))
        start = numbers.start(level, scheme, value) if scheme and not above else None
        if start is not None:
            return "number", scheme, start
        numbers.drop(level)
        shown = ".".join([*above, numeral(value, form["numbering"])])
        return "text", form["prefix"] + shown + form["suffix"]

    def _runs(self, paragraph, part, block: Block, emphasis: dict) -> None:
        for run in block.runs:
            if isinstance(run, Field):
                if isinstance(run.proposed.get("insertion"), dict):
                    continue
                if run.kind in ("page", "date"):
                    kind = "number" if run.kind == "page" else "date"
                    shown = str(self.number) if kind == "number" else self.today
                    self._field(paragraph, kind, shown, emphasis)
                else:
                    shown = self.document.title if run.kind == "title" else str(self.total)
                    self._run(paragraph, part, shown, {}, emphasis)
            elif isinstance(run, Run) and "insertion" not in run.marks:
                formatting = run.marks.get("formatting")
                before = formatting.get("before") if isinstance(formatting, dict) else None
                marks = before if isinstance(before, dict) else run.marks
                self._run(paragraph, part, run.text, marks, emphasis)

    def _run(self, paragraph, part, text: str, marks: dict, emphasis=None) -> None:
        for at, piece in enumerate(office.INVALID.sub("", text).split("\n")):
            if at:
                sub(paragraph, "a:br").append(self._marks(part, marks, emphasis))
            if piece:
                run = sub(paragraph, "a:r")
                run.append(self._marks(part, marks, emphasis))
                sub(run, "a:t", None, piece)

    def _marks(self, part, marks: dict, emphasis: dict | None):
        emphasis = emphasis or {}
        props = etree.Element(q("a:rPr"), {"lang": self.language})
        if size := _sized(_points(office.attr(marks, "size", "pt")), emphasis):
            props.set("sz", str(round(size * 100)))
        if "strong" in marks or emphasis.get("bold"):
            props.set("b", "1")
        if "em" in marks or emphasis.get("italic"):
            props.set("i", "1")
        if "underline" in marks:
            props.set("u", "sng")
        if "strike" in marks:
            props.set("strike", "sngStrike")
        if caps := emphasis.get("caps"):
            props.set("cap", caps)
        if "sup" in marks or "sub" in marks:
            props.set("baseline", "30000" if "sup" in marks else "-25000")
        if color := palette.text(office.attr(marks, "color", "color")) or emphasis.get("color"):
            _solid(props, color)
        if fill := palette.highlight(office.attr(marks, "highlight", "color")):
            sub(sub(props, "a:highlight"), "a:srgbClr", {"val": fill})
        family = office.attr(marks, "font", "family")
        if typeface := (
            fonts.office(family) if isinstance(family, str) and family else emphasis.get("font")
        ):
            sub(props, "a:latin", {"typeface": typeface})
        href = office.attr(marks, "link", "href")
        if isinstance(href, str) and href:
            rid = part.relate_to(urljoin(self.site, href), RT.HYPERLINK, is_external=True)
            sub(props, "a:hlinkClick", {"r:id": rid})
        return props

    def _field(self, paragraph, kind: str, shown: str, emphasis: dict) -> None:
        type = "slidenum" if kind == "number" else "datetime1"
        found = sub(paragraph, "a:fld", {"id": "{" + str(uuid.uuid4()).upper() + "}", "type": type})
        found.append(self._marks(None, {}, emphasis))
        sub(found, "a:t", None, shown)

    def _notes(self, slide: XmlPart, said: list[Block]) -> None:
        self.notes += 1
        element = root("p:notes")
        part = XmlPart(
            PackURI(f"/ppt/notesSlides/notesSlide{self.notes}.xml"),
            CT.PML_NOTES_SLIDE,
            element,
            self.package,
        )
        tree = _tree(sub(element, "p:cSld"))
        locks = {"noRot": 1, "noChangeAspect": 1}
        self._placeholder(tree, {"type": "sldImg"}, "Slide Image", None, locks)
        body = sub(self._placeholder(tree, {"type": "body", "idx": 1}, "Notes"), "p:txBody")
        sub(body, "a:bodyPr")
        sub(body, "a:lstStyle")
        for block in said:
            paragraph = sub(body, "a:p")
            self._runs(paragraph, part, self._before(block), {})
            sub(paragraph, "a:endParaRPr", {"lang": self.language})
        sub(sub(element, "p:clrMapOvr"), "a:masterClrMapping")
        part.relate_to(self.notes_master, RT.NOTES_MASTER)
        part.relate_to(slide, RT.SLIDE)
        slide.relate_to(part, RT.NOTES_SLIDE)

    # Pictures, tables and charts

    def _blip(self, parent, part: XmlPart, sha256: str, page: tuple[int, float] | None = None):
        """The picture's reference in the part, the picture once in the file however often it
        shows; an SVG beside a PNG of it, for PowerPoints that draw no SVG; a PDF's page, by its
        number and the inches it shows across, as a PNG of it."""
        key = sha256 if page is None else f"{sha256}/{page[0]}"
        if key not in self.media:
            number = len(self.media) + 1
            original = None
            if page is not None:
                picture = pictures.page_picture(sha256, *page)
                name = f"/ppt/media/page{number}.png"
            else:
                picture = pictures.picture_of(sha256)
                if picture.svg is not None:
                    name = f"/ppt/media/image{number}.svg"
                    original = Part(PackURI(name), "image/svg+xml", picture.svg)
                name = f"/ppt/media/picture{number}.{store.IMAGES[picture.media_type]}"
            self.media[key] = (Part(PackURI(name), picture.media_type, picture.data), original)
        found, original = self.media[key]
        blip = sub(parent, "a:blip", {"r:embed": part.relate_to(found, RT.IMAGE)})
        if original is not None:
            extension = sub(sub(blip, "a:extLst"), "a:ext", {"uri": SVG_BLIP})
            embed = {q("r:embed"): part.relate_to(original, RT.IMAGE)}
            etree.SubElement(extension, f"{{{SVG}}}svgBlip", embed, nsmap={"asvg": SVG})
        return blip

    def _pictured(self, tree, part, sha256, frame, alt: str, page=None) -> None:
        if not isinstance(sha256, str):
            return
        found, names = _named(tree, "p:pic", "Picture")
        names.find(q("p:cNvPr")).set("descr", alt)
        sub(sub(names, "p:cNvPicPr"), "a:picLocks", {"noChangeAspect": 1})
        sub(names, "p:nvPr")
        fill = sub(found, "p:blipFill")
        self._blip(fill, part, sha256, page)
        sub(sub(fill, "a:stretch"), "a:fillRect")
        props = sub(found, "p:spPr")
        _frame(props, *frame)
        sub(sub(props, "a:prstGeom", {"prst": "rect"}), "a:avLst")

    def _pdf(self, tree, part, block: Block, frame) -> None:
        """The pages the block shows, one below another in its frame as the view lays them,
        each a picture of it."""
        pages = pictures.pages_of(block.attrs)
        if not pages:
            return
        x, y, w, h = frame
        tall = sum(w * height / width for _, (width, height) in pages)
        scale = min(1, h / tall)
        gap = (h - tall) / (len(pages) - 1) if scale == 1 and len(pages) > 1 else 0
        title = block.attrs.get("title") if isinstance(block.attrs.get("title"), str) else ""
        for number, (width, height) in pages:
            across = w * scale
            shown = (x + (w - across) / 2, y, across, across * height / width)
            alt = f"{title} · {number}" if title else str(number)
            self._pictured(tree, part, block.attrs["blob"], shown, alt, (number, across / 2.54))
            y += shown[3] + gap

    @staticmethod
    def _graphic(tree, kind: str, frame, uri: str):
        found, names = _named(tree, "p:graphicFrame", kind)
        locks = sub(names, "p:cNvGraphicFramePr")
        if kind == "Table":
            sub(locks, "a:graphicFrameLocks", {"noGrp": 1})
        sub(names, "p:nvPr")
        _frame(found, *frame, tag="p:xfrm")
        return sub(sub(found, "a:graphic"), "a:graphicData", {"uri": uri})

    def _table(self, tree, part, table: Block, frame, look: dict, fit: float) -> None:
        """A table where the view shows it, its text as far shrunk, since a table does not
        shrink in PowerPoint; in its design, one of PowerPoint's own styles as that style with its
        cells' own fills and edges over it, else each cell as its designs draw it."""
        listed = table.attrs.get("designs") or []
        style = self._style_of(listed[0]) if len(listed) == 1 else None
        styled = listed[0] if style else None
        fills, edges = office.own_looks(table)
        looks = office.designed(table)
        table = blocks.visible(table)
        grid = table.grid or blocks.Grid([], [])
        if not grid.rows or not grid.cols:
            return
        attrs = table.attrs
        widths = attrs.get("widths") if isinstance(attrs.get("widths"), dict) else {}
        shares = []
        for col in grid.cols:
            share = _number(widths.get(col)) or 0
            sized = share > 0 and attrs.get("sized")
            shares.append(share * CHARACTER_CM if sized else share or 100 / len(grid.cols))
        element = sub(self._graphic(tree, "Table", frame, TABLE), "a:tbl")
        on = (styled or {}).get("on") or {}
        props = sub(
            element,
            "a:tblPr",
            {theirs: int(bool(on.get(ours))) for theirs, ours in SWITCHES.items()},
        )
        whole = next((each for each in listed if "area" not in each), {}) if not styled else {}
        if background := whole.get("background"):
            _filled(props, background)
        if shadow := whole.get("shadow"):
            cast = sub(
                sub(props, "a:effectLst"),
                "a:outerShdw",
                {
                    "blurRad": round(shadow["blur"] * EMU_PER_POINT),
                    "dist": round(shadow["distance"] * EMU_PER_POINT),
                    "dir": round(shadow["angle"] * 60000),
                    "rotWithShape": 0,
                },
            )
            _painted(cast, shadow["color"], "text")
        sub(props, "a:tableStyleId", None, style or NO_STYLE)
        columns = sub(element, "a:tblGrid")
        for share in shares:
            sub(columns, "a:gridCol", {"w": emu(frame[2] * share / sum(shares))})
        slots = {}
        for each in blocks.placed(table):
            for y in range(each.y, each.y + each.rows):
                for x in range(each.x, each.x + each.cols):
                    slots[(y, x)] = each
        size = (_size(look, 0) or 18) * fit
        for y, _ in enumerate(grid.rows):
            row = sub(element, "a:tr", {"h": emu(frame[3] / len(grid.rows))})
            for x, _ in enumerate(grid.cols):
                each = slots.get((y, x))
                cell = sub(row, "a:tc")
                origin = each is not None and (each.y, each.x) == (y, x)
                if origin and each.rows > 1:
                    cell.set("rowSpan", str(each.rows))
                if origin and each.cols > 1:
                    cell.set("gridSpan", str(each.cols))
                if each is not None and each.x != x:
                    cell.set("hMerge", "1")
                if each is not None and each.y != y:
                    cell.set("vMerge", "1")
                slot = (grid.rows[y], grid.cols[x])
                drawn = looks[slot]
                under = designs.Cell([]) if styled else drawn
                body = sub(cell, "a:txBody")
                sub(body, "a:bodyPr")
                sub(body, "a:lstStyle")
                if each is None:
                    shown = office.shown(table, blocks.Cell(*slot))
                else:
                    shown = office.shown(table, each.cell) if origin else [Block("paragraph")]
                for block in shown:
                    self._cell_paragraph(body, part, block, look, size, fit, under)
                cell_props = sub(cell, "a:tcPr")
                if under.valign:
                    cell_props.set("anchor", VALIGNS[under.valign])
                own = edges.get(slot, {}) if styled else drawn.edges
                for side, tag in (
                    ("left", "a:lnL"),
                    ("right", "a:lnR"),
                    ("top", "a:lnT"),
                    ("bottom", "a:lnB"),
                ):
                    if side in own:
                        _stroked(cell_props, tag, own[side])
                fill = fills.get(slot) if styled else drawn.fill
                if fill is not None:
                    _filled(cell_props, fill)

    def _style_of(self, design: dict) -> str | None:
        """The id of the one of PowerPoint's own styles a design is as this deck's theme draws
        it; None for any other, which PowerPoint would draw as Table Grid."""
        id = built_in_id(design.get("name") or "")
        if id is None or design.get("rules") != "powerpoint" or "area" in design:
            return None
        on = design.get("on") or {}
        props = etree.Element(
            q("a:tblPr"), {theirs: "1" for theirs, ours in SWITCHES.items() if on.get(ours)}
        )
        sub(props, "a:tableStyleId", None, id)
        drawn = Looks(Counter()).design(props, self.drawing)
        return id if {**drawn, "on": on} == {**design, "on": on} else None

    def _cell_paragraph(
        self, body, part, block: Block, look: dict, size: float, fit: float, under: designs.Cell
    ):
        paragraph = sub(body, "a:p")
        props = sub(paragraph, "a:pPr")
        if (align := block.attrs.get("align") or under.align) in ALIGNS:
            props.set("algn", ALIGNS[align])
        sub(props, "a:buNone")
        if under.marks:
            block = replace(
                block,
                runs=[
                    replace(run, marks={**under.marks, **run.marks})
                    if isinstance(run, Run)
                    else run
                    for run in block.runs
                ],
            )
        typeface = _typeface(look.get("font"))
        emphasis = {
            "size": size,
            "scale": fit,
            **({"caps": under.caps} if under.caps else {}),
            **({"bold": True} if look.get("bold") is True else {}),
            **({"italic": True} if look.get("italic") is True else {}),
            **({"color": color} if (color := _color(look.get("color"))) else {}),
            **({"font": typeface} if typeface else {}),
        }
        if block.type in office.TEXTUAL:
            self._runs(paragraph, part, block, emphasis)
        ended = sub(paragraph, "a:endParaRPr", {"lang": self.language, "sz": round(size * 100)})
        if typeface:
            sub(ended, "a:latin", {"typeface": typeface})

    def _chart(self, tree, part, block: Block, frame) -> None:
        """A chart over the document's tables as a workbook of its own, so PowerPoint edits its
        data in Excel as its own chart's."""
        chart = drawn.chart_of(block.attrs)
        sheet = self.book.sheet(chart.table) if chart is not None and self.book else None
        self.charts += 1
        font = styles.family(self.theme, self.looks["text"]["font"])
        element = charts.space(block.attrs, sheet, font)
        chart_part = XmlPart(
            PackURI(f"/ppt/charts/chart{self.charts}.xml"), CT.DML_CHART, element, self.package
        )
        if sheet is not None:
            name = f"/ppt/embeddings/Microsoft_Excel_Worksheet{self.charts}.xlsx"
            embedded = Part(PackURI(name), CT.SML_SHEET, self.workbook, self.package)
            charts.linked(element, chart_part.relate_to(embedded, RT.PACKAGE))
        data = self._graphic(tree, "Chart", frame, charts.C)
        sub(data, "c:chart", {"r:id": part.relate_to(chart_part, RT.CHART)})

    @cached_property
    def book(self) -> xlsx.Computed | None:
        try:
            return xlsx.computed(self.document)
        except xlsx.Empty:
            return None

    @cached_property
    def workbook(self) -> bytes:
        return self.book.written()

    # The rest of the package

    def _sections(self, sections: list) -> None:
        extension = sub(sub(self.root, "p:extLst"), "p:ext", {"uri": SECTIONS})
        listed = etree.SubElement(extension, q("p14:sectionLst"), nsmap={"p14": P14})
        for tab, ids in sections:
            name = tab.title or self.document.title
            id = "{" + str(tab.pk).upper() + "}"
            kept = sub(sub(listed, "p14:section", {"name": name, "id": id}), "p14:sldIdLst")
            for slide in ids:
                sub(kept, "p14:sldId", {"id": slide})

    def _props(self) -> None:
        for name, content_type, tag, reltype in (
            ("/ppt/presProps.xml", CT.PML_PRES_PROPS, "p:presentationPr", RT.PRES_PROPS),
            ("/ppt/viewProps.xml", CT.PML_VIEW_PROPS, "p:viewPr", RT.VIEW_PROPS),
        ):
            part = XmlPart(PackURI(name), content_type, root(tag), self.package)
            self.main.relate_to(part, reltype)
        listed = etree.Element(q("a:tblStyleLst"), {"def": NO_STYLE}, nsmap={"a": A})
        part = XmlPart(PackURI("/ppt/tableStyles.xml"), CT.PML_TABLE_STYLES, listed, self.package)
        self.main.relate_to(part, RT.TABLE_STYLES)


def presentation(document: Node, site: str, measured: dict[str, list]) -> bytes:
    """The document as a pptx, its slides laid out as the printer `measured` them; `site` is the
    address its own links are relative to."""
    return Writer(document, site, measured).written()
