"""A PowerPoint file (pptx) as a document's tabs and slide template: each section a tab, each
slide its title, then its text, pictures, tables and charts in reading order, a second column's
after a column break, and its notes as speaker notes; the masters and their layouts the
document's template, flattened. What it holds that we cannot show is counted in the import's
report, never guessed at."""

import colorsys
import copy
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import parse_xml
from lxml import etree

from apps.content import designs, fonts, lists, palette, slides
from apps.content import styles as our
from apps.content.blocks import Block, Cell, Field, Grid, Run, new_id
from apps.content.schema import DEEPEST, INDENT_STEP

from . import colors, office, vba
from .docx import VBA_PROJECT
from .powerpoint import (
    ALIGNS,
    ANCHORS,
    CLR_MAP,
    DASHES,
    DESIGN_PARTS,
    EMU_PER_POINT,
    FIELDS,
    P14,
    SCHEMES,
    SECTIONS,
    STROKES,
    SWITCHES,
    TABLE,
    TABLE_GRID,
    P,
    built_in,
)
from .reading import Imported, Tab, Unreadable
from .word import CHART, DIAGRAM, EMU_PER_CM, MC, A, R, ns, number

MODERN_COMMENTS = "http://schemas.microsoft.com/office/2018/10/relationships/comments"
TITLES = {"title", "ctrTitle"}
FOOTERS = {**FIELDS, "ftr": "text"}
UNPLACED = TITLES | set(FOOTERS) | {"subTitle", "hdr"}
OBJECTS = {"pic", "tbl", "chart", "media", "clipArt", "dgm"}
KINDS = {"title": "title", "secHead": "section", "titleOnly": "titleOnly", "blank": "blank"}
ALIGNED = {code: name for name, code in ALIGNS.items()} | {"dist": "justify"}
ANCHORED = {code: name for name, code in ANCHORS.items()}
NUMBERED = {scheme: form for form, scheme in SCHEMES.items()}
SYMBOLS = {"wingdings", "wingdings 2", "wingdings 3", "webdings", "symbol"}
MEDIA = {"videoFile", "audioFile", "quickTimeFile", "wavAudioFile", "audioCd", "media"}
ANIMATED = {"anim", "animClr", "animEffect", "animMotion", "animRot", "animScale", "set", "bldP"}
LEVELS = 9
LARGEST_CM = 200
SLACK_CM = 0.5
LONGEST_TEXT = 1000
MOST_SHAPES = 200
LINE_POINTS = 0.75
SIZE = slides.BUILT_IN["$defs"]["size"]["properties"]["width"]

Rect = tuple[float, float, float, float]
Place = Callable[[Rect], Rect]


def p(name: str) -> str:
    return ns(P, name)


def a(name: str) -> str:
    return ns(A, name)


def _local(element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def _cm(emu: str | None) -> float | None:
    found = number(emu)
    return None if found is None else round(found / EMU_PER_CM, 3)


def _on(text: str | None) -> bool:
    return text in ("1", "true", "on")


def _off(text: str | None) -> bool:
    return text in ("0", "false", "off")


def _rect(holder) -> Rect | None:
    """Where a shape's frame (a:xfrm, or a graphic frame's p:xfrm) sets it, in cm."""
    xfrm = None if holder is None else holder.find(a("xfrm"))
    if xfrm is None and holder is not None:
        xfrm = holder.find(p("xfrm"))
    if xfrm is None:
        return None
    off, ext = xfrm.find(a("off")), xfrm.find(a("ext"))
    if off is None or ext is None:
        return None
    found = (_cm(off.get("x")), _cm(off.get("y")), _cm(ext.get("cx")), _cm(ext.get("cy")))
    return None if None in found else found


def _area(rect: Rect | None) -> float:
    return rect[2] * rect[3] if rect else 0


def _union(rects: list[Rect]) -> Rect:
    left = min(rect[0] for rect in rects)
    top = min(rect[1] for rect in rects)
    right = max(rect[0] + rect[2] for rect in rects)
    bottom = max(rect[1] + rect[3] for rect in rects)
    return left, top, right - left, bottom - top


def _inside(rect: Rect | None, box: Rect) -> bool:
    if rect is None:
        return False
    x, y, w, h = rect
    left, top, width, height = box
    return (
        x >= left - SLACK_CM
        and y >= top - SLACK_CM
        and x + w <= left + width + SLACK_CM
        and y + h <= top + height + SLACK_CM
    )


def _within(rect: Rect) -> dict:
    x, y, w, h = rect
    return {
        "x": round(min(max(x, -LARGEST_CM), LARGEST_CM), 3),
        "y": round(min(max(y, -LARGEST_CM), LARGEST_CM), 3),
        "w": round(min(max(w, 0), LARGEST_CM), 3),
        "h": round(min(max(h, 0), LARGEST_CM), 3),
    }


def _same(rect: Rect) -> Rect:
    return rect


def _moving(transition) -> bool:
    """Whether a slide's transition does anything: an effect or a sound, or moving on by itself."""
    return transition.get("advTm") is not None or any(
        _local(each) != "extLst" for each in transition
    )


def _ph(shape):
    return shape.find(f"./*/{p('nvPr')}/{p('ph')}")


def _plain(body) -> str:
    return "\n".join(
        "".join(each.text or "" for each in para.iter(a("t"))) for para in body.iterfind(a("p"))
    ).strip()


def _texted(body) -> bool:
    return body is not None and any((each.text or "").strip() for each in body.iter(a("t")))


def _chosen(alternate):
    """What PowerPoint draws of content it may not read: the fallback, a picture of it."""
    found = alternate.find(ns(MC, "Fallback"))
    if found is None:
        found = alternate.find(ns(MC, "Choice"))
    return [] if found is None else found


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _gamma(channel: float) -> float:
    channel = min(max(channel, 0), 1)
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _modified(value: str | None, color) -> tuple[str, float] | None:
    """A colour with its changes, and its opacity; PowerPoint tints and shades in linear RGB."""
    if not value or len(value) != 6:
        return None
    try:
        rgb = [int(value[at : at + 2], 16) / 255 for at in (0, 2, 4)]
    except ValueError:
        return None
    alpha = 1.0
    for change in color:
        amount = (number(change.get("val")) or 0) / 100000
        local = _local(change)
        if local == "tint":
            rgb = [_gamma(_linear(each) * amount + 1 - amount) for each in rgb]
        elif local == "shade":
            rgb = [_gamma(_linear(each) * amount) for each in rgb]
        elif local in ("lumMod", "lumOff"):
            hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)
            lightness = lightness * amount if local == "lumMod" else lightness + amount
            rgb = list(colorsys.hls_to_rgb(hue, min(max(lightness, 0), 1), saturation))
        elif local == "alpha":
            alpha = min(max(amount, 0), 1)
    return "".join(f"{int(min(max(each, 0), 1) * 255 + 0.5):02X}" for each in rgb), alpha


def _hex(color: str | None) -> str | None:
    return f"#{color.lower()}" if color else None


def _tint(painted: tuple[str, float] | None, kind: str) -> str | None:
    """A colour as a design holds it: the palette's name or #rrggbb, with its alpha where it
    lets what is beneath show through."""
    if painted is None:
        return None
    color, alpha = painted
    if alpha < 1:
        return f"#{color.lower()}{int(alpha * 255 + 0.5):02x}"
    return palette.named(kind, f"#{color.lower()}")


def _points(emu: str | None) -> float:
    return round(min((number(emu) or 0) / EMU_PER_POINT, 100), 2)


@dataclass
class Master:
    """A master's, or the notes master's, colours, fonts and text styles, and its placeholders
    by their type."""

    part: object
    root: object
    scheme: dict[str, str]
    map: dict[str, str]
    fonts: dict[str, str]
    styles: dict[str, object]
    holders: dict[str, Holder] = field(default_factory=dict)
    formats: object = None

    def color(self, parent, given: str | None = None) -> str | None:
        """The colour a fill, or any element holding a colour, gives."""
        painted = self.paint(parent, given)
        return painted[0] if painted else None

    def paint(self, parent, given: str | None = None) -> tuple[str, float] | None:
        """The colour and the opacity a fill, or any element holding a colour, gives."""
        for color in parent if parent is not None else []:
            local = _local(color)
            if local == "srgbClr":
                value = color.get("val")
            elif local == "schemeClr":
                name = color.get("val")
                value = given if name == "phClr" else self.scheme.get(self.map.get(name, name))
            elif local == "sysClr":
                value = color.get("lastClr")
            elif local == "scrgbClr":
                value = "".join(
                    f"{round(min(max((number(color.get(at)) or 0) / 100000, 0), 1) * 255):02X}"
                    for at in ("r", "g", "b")
                )
            elif local == "prstClr":
                value = {"black": "000000", "white": "FFFFFF"}.get(color.get("val"))
            else:
                continue
            return _modified(value, color)
        return None

    def formatted(self, ref):
        """The theme's line, fill or effect style a reference names by its index; None for
        none."""
        index = int(number(ref.get("idx")) or 0)
        kind = {"lnRef": "lnStyleLst", "fillRef": "fillStyleLst", "effectRef": "effectStyleLst"}[
            _local(ref)
        ]
        if kind == "fillStyleLst" and index > 1000:
            kind, index = "bgFillStyleLst", index - 1000
        found = self.formats.find(a(kind)) if self.formats is not None else None
        styles = list(found) if found is not None else []
        return styles[index - 1] if 0 < index <= len(styles) else None

    def font(self, face: str) -> tuple[str, str | None]:
        if face.startswith("+mj"):
            return self.fonts.get("headings", face), "headings"
        if face.startswith("+mn"):
            return self.fonts.get("text", face), "text"
        return face, None


@dataclass(eq=False)
class Holder:
    """A placeholder of a master, a layout or a slide, and the one above it it takes what it
    does not set from."""

    type: str
    idx: str | None
    shape: object
    above: Holder | None
    style: object
    role: str | None = None

    @property
    def rect(self) -> Rect | None:
        own = _rect(self.shape.find(p("spPr")))
        return own if own is not None or self.above is None else self.above.rect

    def lists(self) -> list:
        """Its text styles, the most general first."""
        above = self.above.lists() if self.above else [self.style]
        return [*above, self.shape.find(f"{p('txBody')}/{a('lstStyle')}")]

    def anchor(self) -> str | None:
        body = self.shape.find(f"{p('txBody')}/{a('bodyPr')}")
        own = ANCHORED.get(body.get("anchor")) if body is not None else None
        return own or (self.above.anchor() if self.above else None)


@dataclass(eq=False)
class Laid:
    """A layout as ours: its placeholders and the box each of them fills, whether a slide is laid
    out by it, and the slide number, date and footer the slides laid out by it show."""

    id: str
    part: object
    root: object
    master: Master
    holders: list[Holder]
    kind: str = "blank"
    boxes: dict[str, tuple[Rect, Holder]] = field(default_factory=dict)
    used: bool = False
    shown: dict[str, str] = field(default_factory=dict)

    def holder(self, type: str, idx: str | None) -> Holder | None:
        """The placeholder a slide's placeholder takes after: the title the title, any other the
        one of its index where it gives one, else the first of its type or, holding content,
        the first holding content."""
        if type in TITLES:
            return next((each for each in self.holders if each.type in TITLES), None)
        others = [each for each in self.holders if each.type not in TITLES]
        if type not in FOOTERS and idx is not None:
            found = next((each for each in others if (each.idx or "0") == idx), None)
            if found is not None:
                return found
        return next((each for each in others if each.type == type), None) or next(
            (each for each in others if type not in UNPLACED and each.type not in UNPLACED),
            None,
        )

    def column(self, rect: Rect | None) -> str:
        second = self.boxes.get("second")
        if second and rect and rect[0] + rect[2] / 2 >= second[0][0]:
            return "second"
        return "body"


@dataclass
class Item:
    role: str
    rect: Rect | None
    blocks: list[Block]
    title: bool = False


def read(path: Path, locale: str, formats: dict[str, list[dict]] | None = None) -> Imported:
    """The file's slides as tabs and its layouts as the slide template, its lists sharing the
    formats a document already has and its charts' tables typed as the locale types them."""
    package = office.opened(path)
    try:
        return Reader(package, formats or {}, locale).read()
    except (etree.LxmlError, KeyError) as error:
        raise Unreadable from error


def themed(theme) -> tuple[dict[str, str], dict[str, str], object]:
    """A theme's colours by their slot, its fonts for headings and for text, and its formats."""
    scheme, faces = {}, {}
    if theme is None:
        return scheme, faces, None
    colours = theme.find(f"{a('themeElements')}/{a('clrScheme')}")
    for slot in colours if colours is not None else []:
        color = next(iter(slot), None)
        if color is not None:
            system = _local(color) == "sysClr"
            scheme[_local(slot)] = color.get("lastClr" if system else "val")
    for side, tag in (("headings", "majorFont"), ("text", "minorFont")):
        latin = theme.find(f"{a('themeElements')}/{a('fontScheme')}/{a(tag)}/{a('latin')}")
        if latin is not None and latin.get("typeface"):
            faces[side] = latin.get("typeface")
    return scheme, faces, theme.find(f"{a('themeElements')}/{a('fmtScheme')}")


class Looks:
    """What a table's style, its cells' fills and lines and its shadow give, read against a
    master and counting into `lost` what a table cannot hold."""

    def __init__(self, lost: Counter[str]):
        self.lost = lost

    def design(self, props, master: Master) -> dict:
        """The design a table's style gives it, with the parts its switches turn on and the
        background and shadow the table's own properties put over the style's. PowerPoint draws
        only its own styles, whatever the file defines, Table Grid for a table that names none
        and for any style it has not."""
        id = props.findtext(a("tableStyleId")) if props is not None else None
        style = built_in(id or TABLE_GRID)
        if style is None:
            self.lost["tableStyles"] += 1
            style = built_in(TABLE_GRID)
        parts = {}
        for element in style:
            if (name := DESIGN_PARTS.get(_local(element))) and (part := self.part(element, master)):
                parts[name] = part
        design: dict = {"rules": "powerpoint", "name": style.get("styleName")}
        if parts:
            design["parts"] = parts
        switched = props if props is not None else {}
        if on := {ours: True for theirs, ours in SWITCHES.items() if _on(switched.get(theirs))}:
            design["on"] = on
        background = style.find(a("tblBg"))
        shown = shadow = None
        if background is not None:
            fill, ref = background.find(a("fill")), background.find(a("fillRef"))
            shown = self.filled(fill, master) if fill is not None else self.referred(ref, master)
            effect, ref = background.find(a("effect")), background.find(a("effectRef"))
            if effect is not None:
                shadow = self.shadow(effect, master)
            elif ref is not None and (themed := master.formatted(ref)) is not None:
                given = master.paint(ref)
                shadow = self.shadow(themed, master, given[0] if given else None)
        if props is not None and (own := self.filled(props, master)) is not None:
            shown = own
        if props is not None and props.find(a("effectLst")) is not None:
            shadow = self.shadow(props, master)
        if shown not in (None, "none"):
            design["background"] = shown
        if shadow:
            design["shadow"] = shadow
        return design

    def part(self, element, master: Master) -> dict:
        """What a part of a table style sets: its text's marks, its cells' fill and edges."""
        part: dict = {}
        marks: dict = {}
        text = element.find(a("tcTxStyle"))
        if text is not None:
            for attr, mark in (("b", "strong"), ("i", "em")):
                if text.get(attr) in ("on", "off"):
                    marks[mark] = {} if text.get(attr) == "on" else False
            ref = text.find(a("fontRef"))
            painted = master.paint(text) or (master.paint(ref) if ref is not None else None)
            if painted:
                marks["color"] = {"color": palette.named("text", f"#{painted[0].lower()}")}
            latin = text.find(f"{a('font')}/{a('latin')}")
            if latin is not None and latin.get("typeface"):
                marks["font"] = {"family": master.font(latin.get("typeface"))[0]}
            elif ref is not None and ref.get("idx") == "major":
                marks["font"] = {"family": master.font("+mj-lt")[0]}
        if marks:
            part["marks"] = marks
        cell = element.find(a("tcStyle"))
        if cell is None:
            return part
        fill, ref = cell.find(a("fill")), cell.find(a("fillRef"))
        shown = self.filled(fill, master) if fill is not None else self.referred(ref, master)
        if shown is not None:
            part["fill"] = self.flat(shown)
        edges = {}
        borders = cell.find(a("tcBdr"))
        for side in borders if borders is not None else ():
            local = _local(side)
            if local in ("tl2br", "tr2bl"):
                self.lost["tableStyles"] += 1
                continue
            line, ref = side.find(a("ln")), side.find(a("lnRef"))
            if line is not None:
                edge = self.stroke(line, master)
            elif ref is not None:
                given = master.paint(ref)
                edge = self.stroke(master.formatted(ref), master, given[0] if given else None)
            else:
                edge = None
            if edge is not None:
                edges[local] = edge
        if edges:
            part["edges"] = edges
        self.lost["tableStyles"] += cell.find(a("cell3D")) is not None
        return part

    def edges(self, props, master: Master) -> dict | None:
        """The lines a cell draws on its own sides over its table's design."""
        edges = {}
        for tag, side in (("lnL", "left"), ("lnR", "right"), ("lnT", "top"), ("lnB", "bottom")):
            line = props.find(a(tag)) if props is not None else None
            if line is not None and any(_local(each) in ("noFill", "solidFill") for each in line):
                edges[side] = self.stroke(line, master)
        for tag in ("lnTlToBr", "lnBlToTr"):
            self.lost["tableStyles"] += props is not None and props.find(a(tag)) is not None
        return edges or None

    def stroke(self, line, master: Master, given: str | None = None) -> dict | str | None:
        """An edge as an a:ln draws it, phClr standing for given; "none" for no line."""
        if line is None:
            return None
        if line.find(a("noFill")) is not None:
            return "none"
        dash = line.find(a("prstDash"))
        kind = DASHES.get(dash.get("val")) if dash is not None else None
        edge: dict = {
            "line": kind or STROKES.get(line.get("cmpd") or "sng", "single"),
            "width": max(_points(line.get("w") or str(EMU_PER_POINT)), 0.01),
        }
        if (fill := line.find(a("solidFill"))) is not None:
            if color := _tint(master.paint(fill, given), "text"):
                edge["color"] = color
        elif any(line.find(a(other)) is not None for other in ("gradFill", "pattFill")):
            self.lost["tableStyles"] += 1
        return edge

    def filled(self, holder, master: Master, given: str | None = None) -> str | dict | None:
        """What the fill a holder carries gives a table: a colour, a gradient, or "none"; None
        where it carries none."""
        for fill in holder if holder is not None else ():
            kind = _local(fill)
            if kind == "noFill":
                return "none"
            if kind == "solidFill":
                return _tint(master.paint(fill, given), "highlight")
            if kind == "gradFill":
                stops = [
                    {"at": round((number(stop.get("pos")) or 0) / 1000, 1), "color": color}
                    for stop in fill.iterfind(f"{a('gsLst')}/{a('gs')}")
                    if (color := _tint(master.paint(stop, given), "highlight"))
                ]
                linear = fill.find(a("lin"))
                self.lost["tableStyles"] += linear is None
                if len(stops) < 2:
                    return stops[0]["color"] if stops else None
                angle = (number(linear.get("ang")) or 0) / 60000 if linear is not None else 90
                return {
                    "angle": round(angle % 360, 2),
                    "stops": sorted(stops, key=lambda stop: stop["at"]),
                }
            if kind in ("pattFill", "blipFill", "grpFill"):
                self.lost["tableStyles"] += 1
                return None
        return None

    def flat(self, shown: str | dict | None) -> str | None:
        """A fill as a cell holds it: a gradient's first colour, the rest of it lost."""
        if isinstance(shown, dict):
            self.lost["tableStyles"] += 1
            return shown["stops"][0]["color"]
        return shown

    def referred(self, ref, master: Master) -> str | dict | None:
        """The fill a theme's fill style gives in the colour a reference names."""
        themed = master.formatted(ref) if ref is not None else None
        if themed is None:
            return None
        given = master.paint(ref)
        return self.filled([themed], master, given[0] if given else None)

    def shadow(self, effects, master: Master, given: str | None = None) -> dict | None:
        """The shadow a list of effects casts; the others it holds are lost."""
        listed = effects.find(a("effectLst"))
        self.lost["tableStyles"] += any(
            effects.find(a(each)) is not None for each in ("scene3d", "sp3d")
        )
        if listed is None:
            self.lost["tableStyles"] += effects.find(a("effectDag")) is not None
            return None
        found = None
        for effect in listed:
            if _local(effect) == "outerShdw" and (
                color := _tint(master.paint(effect, given), "text")
            ):
                found = {
                    "color": color,
                    "blur": _points(effect.get("blurRad")),
                    "distance": _points(effect.get("dist")),
                    "angle": round((number(effect.get("dir")) or 0) / 60000 % 360, 2),
                }
            else:
                self.lost["tableStyles"] += 1
        return found


class Reader:
    def __init__(self, package, formats: dict[str, list[dict]], locale: str):
        self.locale = locale
        self.part = package.main_document_part
        self.root = parse_xml(self.part.blob)
        if self.root.tag != p("presentation"):
            raise Unreadable
        self.defaults = self.root.find(p("defaultTextStyle"))
        self.lost: Counter[str] = Counter()
        self.looks = Looks(self.lost)
        self.fonts: set[str] = set()
        self.images: dict[str, bytes] = {}
        self.known = formats
        self.formats: dict[str, list[dict]] = {}
        self.numbers: dict[str, int] = {}
        self.parsed: dict[str, object] = {}
        self.masters: dict[str, Master] = {}
        self.laid: dict[str, Laid] = {}
        self.behind: dict[str, list[dict]] = {}
        self.backdrops: dict[str, dict | None] = {}

    def read(self) -> Imported:
        size = self.root.find(p("sldSz"))
        width = _cm(size.get("cx")) if size is not None else None
        height = _cm(size.get("cy")) if size is not None else None
        width, height = (
            min(max(each or default, SIZE["minimum"]), SIZE["maximum"])
            for each, default in zip((width, height), slides.BUILT_IN["size"].values(), strict=True)
        )
        self.size = (width, height)
        for master in self.root.iterfind(f"{p('sldMasterIdLst')}/{p('sldMasterId')}"):
            part = self.part.related_parts[master.get(ns(R, "id"))]
            for layout in self._parsed(part).iterfind(f"{p('sldLayoutIdLst')}/{p('sldLayoutId')}"):
                self._layout(part.related_parts[layout.get(ns(R, "id"))])
        made: dict[str, list[Block]] = {}
        order: list[str] = []
        for slide in self.root.iterfind(f"{p('sldIdLst')}/{p('sldId')}"):
            order.append(slide.get("id"))
            made[slide.get("id")] = self._slide(self.part.related_parts[slide.get(ns(R, "id"))])
        tabs = [
            Tab(name, [block for id in ids if id in made for block in made[id]])
            for name, ids in self._sections(order)
        ]
        tabs = [tab for tab in tabs if tab.blocks] or [Tab("", [])]
        for tab in tabs:
            office.numbered(tab.blocks, self.numbers, self.lost)
        layouts = [self._template(laid) for laid in self.laid.values()]
        project = self._related(self.part, VBA_PROJECT)
        self.lost["macros"] += project is not None
        report = {
            "fonts": fonts.substituted(self.fonts),
            "lost": {key: count for key, count in sorted(self.lost.items()) if count},
            **({"macros": vba.source(project.blob)} if project is not None else {}),
        }
        return Imported(
            tabs,
            None,
            {},
            self._theme(),
            {},
            self.images,
            [],
            report,
            self.formats,
            {"width": width, "height": height, "layouts": layouts},
        )

    # The package

    def _parsed(self, part):
        if part.partname not in self.parsed:
            self.parsed[part.partname] = parse_xml(part.blob)
        return self.parsed[part.partname]

    @staticmethod
    def _related(part, reltype: str):
        try:
            return part.part_related_by(reltype)
        except KeyError:
            return None

    def _sections(self, order: list[str]) -> list[tuple[str, list[str]]]:
        listed = self.root.find(
            f"{p('extLst')}/{p('ext')}[@uri='{SECTIONS}']/{ns(P14, 'sectionLst')}"
        )
        if listed is None:
            return [("", order)]
        found = [
            (
                (section.get("name") or "").strip()[:200],
                [
                    each.get("id")
                    for each in section.iterfind(f"{ns(P14, 'sldIdLst')}/{ns(P14, 'sldId')}")
                ],
            )
            for section in listed.iterfind(ns(P14, "section"))
        ]
        placed = {id for _, ids in found for id in ids}
        if left := [id for id in order if id not in placed]:
            found.insert(0, ("", left))
        return found

    def _theme(self) -> dict[str, str]:
        theme = dict(our.TEMPLATE[our.THEME])
        first = next(iter(self.masters.values()), None)
        for side, named in (first.fonts if first else {}).items():
            self.fonts.add(named)
            if shown := fonts.substitute(named):
                theme[side] = shown
        return theme

    # Masters and layouts

    def _master(self, part, notes: bool = False) -> Master:
        if part.partname in self.masters:
            return self.masters[part.partname]
        root = self._parsed(part)
        theme = self._related(part, RT.THEME)
        scheme, faces, formats = themed(parse_xml(theme.blob) if theme is not None else None)
        mapped = root.find(p("clrMap"))
        styles = (
            {"body": root.find(p("notesStyle"))}
            if notes
            else {
                kind: root.find(f"{p('txStyles')}/{p(f'{kind}Style')}")
                for kind in ("title", "body", "other")
            }
        )
        master = Master(
            part,
            root,
            scheme,
            dict(mapped.attrib) if mapped is not None else dict(CLR_MAP),
            faces,
            styles,
            formats=formats,
        )
        for shape in root.iterfind(f"{p('cSld')}/{p('spTree')}/{p('sp')}"):
            if (ph := _ph(shape)) is not None:
                type = self._general(ph.get("type", "obj"))
                style = styles.get(type) if type in styles else styles.get("other")
                master.holders.setdefault(type, Holder(type, None, shape, None, style))
        self.masters[part.partname] = master
        return master

    @staticmethod
    def _general(type: str) -> str:
        """The master placeholder a placeholder of a type takes what it does not set from."""
        if type in TITLES:
            return "title"
        return type if type in FOOTERS or type == "hdr" else "body"

    def _layout(self, part) -> Laid:
        if part.partname in self.laid:
            return self.laid[part.partname]
        root = self._parsed(part)
        master = self._master(part.part_related_by(RT.SLIDE_MASTER))
        holders = []
        for shape in root.iterfind(f"{p('cSld')}/{p('spTree')}/{p('sp')}"):
            if (ph := _ph(shape)) is not None:
                type = ph.get("type", "obj")
                above = master.holders.get(self._general(type))
                holders.append(Holder(type, ph.get("idx"), shape, above, None))
        laid = Laid(new_id(), part, root, master, holders)
        title = next((each for each in holders if each.type in TITLES), None)
        subtitle = next((each for each in holders if each.type == "subTitle"), None)
        content = [each for each in holders if each.type not in UNPLACED and each.rect]
        columns = self._columns(content)
        for role, holder in (("title", title), ("subtitle", subtitle)):
            if holder is not None and holder.rect:
                holder.role = role
                laid.boxes[role] = (holder.rect, holder)
        for role, column in zip(("body", "second"), columns, strict=False):
            for holder in column:
                holder.role = role
            texts = [each for each in column if each.type not in OBJECTS] or column
            laid.boxes[role] = (
                _union([each.rect for each in column]),
                max(texts, key=lambda each: _area(each.rect)),
            )
        laid.kind = KINDS.get(root.get("type")) or (
            "two"
            if len(columns) > 1
            else "content"
            if columns
            else "titleOnly"
            if title
            else "blank"
        )
        self.laid[part.partname] = laid
        return laid

    @staticmethod
    def _columns(holders: list[Holder]) -> list[list[Holder]]:
        """The placeholders side by side as two columns where none of the left reaches into
        the right, else as one."""
        ordered = sorted(holders, key=lambda each: each.rect[0])
        right = None
        for at, holder in enumerate(ordered):
            x, _, w, _ = holder.rect
            if right is not None and x >= right - 0.01:
                return [ordered[:at], ordered[at:]]
            right = max(right or 0, x + w)
        return [ordered] if ordered else []

    def _template(self, laid: Laid) -> dict:
        name = laid.root.find(p("cSld")).get("name") or ""
        layout = {"id": laid.id, "name": name[:200], "kind": laid.kind, "shapes": [], "boxes": {}}
        if background := self._backdrop(laid):
            layout["background"] = background
        shapes: list[dict] = []
        if not _off(laid.root.get("showMasterSp")):
            shapes.extend(copy.deepcopy(self._behind(laid.master)))
        self._drawn(
            laid.root.find(f"{p('cSld')}/{p('spTree')}"), laid.part, laid.master, _same, shapes
        )
        if not laid.used:
            self._offered(laid)
        for type, content in laid.shown.items():
            holder = laid.holder(type, None)
            if holder is not None and holder.rect:
                kind = FOOTERS[type] if not content else "text"
                shape = {
                    "type": kind,
                    **_within(holder.rect),
                    "text": self._box_text(holder, laid.master),
                }
                if content:
                    shape["content"] = content[:LONGEST_TEXT]
                shapes.append(shape)
        if len(shapes) > MOST_SHAPES:
            self.lost["templateShapes"] += len(shapes) - MOST_SHAPES
        layout["shapes"] = shapes[:MOST_SHAPES]
        for role, (rect, holder) in laid.boxes.items():
            layout["boxes"][role] = {
                **_within(rect),
                "text": self._box_text(holder, laid.master, role),
            }
        if not slides.LAYOUT.is_valid(layout):
            raise ValueError(f"layout {name!r} is not one the template takes")
        return layout

    def _box_text(self, holder: Holder, master: Master, role: str | None = None) -> dict:
        looks = [self._look(holder.lists(), level, master) for level in range(LEVELS)]
        first = looks[0]
        text: dict = {}
        if font := first.get("font"):
            text["font"] = font[1] or font[0][:64]
            self.fonts.add(font[0])
        sizes = [min(max(look.get("size") or 18, 1), 400) for look in looks]
        text["size"] = sizes[0]
        while len(sizes) > 1 and sizes[-1] == sizes[0]:
            sizes.pop()
        if role in ("body", "second") and len(sizes) > 1:
            text["levels"] = sizes
        if color := _hex(first.get("color")):
            text["color"] = color
        for key in ("bold", "italic"):
            text[key] = first.get(key) is True
        if first.get("align"):
            text["align"] = first["align"]
        if anchor := holder.anchor():
            text["anchor"] = anchor
        return text

    def _backdrop(self, laid: Laid) -> dict | None:
        """The background a layout gives its slides, its own or else its master's, each read
        once for all the layouts and slides that show it."""
        for root, part in ((laid.root, laid.part), (laid.master.root, laid.master.part)):
            if part.partname not in self.backdrops:
                found, exact = self._background(root, part, laid.master)
                self.lost["templateLooks"] += not exact
                self.backdrops[part.partname] = found
            if self.backdrops[part.partname] is not None:
                return self.backdrops[part.partname]
        return None

    def _background(self, root, part, master: Master) -> tuple[dict | None, bool]:
        """A background as ours, and whether it is the one the file draws rather than its
        nearest colour."""
        found = root.find(f"{p('cSld')}/{p('bg')}")
        if found is None:
            return None, True
        props, ref = found.find(p("bgPr")), found.find(p("bgRef"))
        if props is not None:
            if (fill := props.find(a("solidFill"))) is not None:
                color = master.color(fill)
                return ({"color": _hex(color)} if color else {}), color is not None
            if (picture := props.find(a("blipFill"))) is not None:
                blip = picture.find(a("blip"))
                rid = blip.get(ns(R, "embed")) if blip is not None else None
                if found := office.picture(part.rels.get(rid) if rid else None):
                    self.images[found[0]] = found[1]
                    return {"image": found[0]}, True
            if (gradient := props.find(a("gradFill"))) is not None:
                stop = gradient.find(f"{a('gsLst')}/{a('gs')}")
                color = master.color(stop) if stop is not None else None
                return ({"color": _hex(color)} if color else {}), False
            return {}, False
        if ref is not None and (color := master.color(ref)):
            return {"color": _hex(color)}, True
        return {}, False

    def _behind(self, master: Master) -> list[dict]:
        """The shapes a master draws, read once for all its layouts."""
        if master.part.partname not in self.behind:
            drawn: list[dict] = []
            tree = master.root.find(f"{p('cSld')}/{p('spTree')}")
            self._drawn(tree, master.part, master, _same, drawn)
            self.behind[master.part.partname] = drawn
        return self.behind[master.part.partname]

    def _drawn(self, tree, part, master: Master, place: Place, out: list[dict]) -> None:
        """The shapes a master or layout draws behind the slides' text."""
        for shape in tree if tree is not None else []:
            local = _local(shape)
            if shape.tag == ns(MC, "AlternateContent"):
                self._drawn(_chosen(shape), part, master, place, out)
            elif local == "grpSp":
                self._drawn(shape, part, master, self._grouped(shape, place), out)
            elif local in ("sp", "cxnSp") and _ph(shape) is None:
                if (drawn := self._shape(shape, master, place)) is not None:
                    out.append(drawn)
            elif local == "pic" and _ph(shape) is None:
                blip = shape.find(f"{p('blipFill')}/{a('blip')}")
                rid = blip.get(ns(R, "embed")) if blip is not None else None
                rect = _rect(shape.find(p("spPr")))
                found = office.picture(part.rels.get(rid) if rid else None)
                if found is None or rect is None:
                    self.lost["templateShapes"] += 1
                    continue
                self.images[found[0]] = found[1]
                out.append({"type": "image", **_within(place(rect)), "blob": found[0]})
            elif local in ("graphicFrame", "contentPart"):
                self.lost["templateShapes"] += 1

    def _shape(self, shape, master: Master, place: Place) -> dict | None:
        props = shape.find(p("spPr"))
        rect = _rect(props)
        geometry = props.find(a("prstGeom")) if props is not None else None
        kind = geometry.get("prst") if geometry is not None else None
        body = shape.find(p("txBody"))
        if rect is None:
            self.lost["templateShapes"] += 1
            return None
        drawn = {"type": "rect", **_within(place(rect))}
        if _local(shape) == "cxnSp" or kind in ("line", "straightConnector1"):
            drawn["type"] = "line"
            xfrm = props.find(a("xfrm"))
            if _on(xfrm.get("flipH")) != _on(xfrm.get("flipV")):
                drawn["flip"] = True
        elif _texted(body):
            drawn["type"] = "text"
            drawn["content"] = _plain(body)[:LONGEST_TEXT]
            para = body.find(a("p"))
            look = self._look([master.styles.get("other"), body.find(a("lstStyle"))], 0, master)
            look.update(self._layer(para.find(a("pPr")), master))
            run = para.find(f"{a('r')}/{a('rPr')}")
            look.update(self._run_layer(run, master))
            drawn["text"] = self._shape_text(look, body)
        elif kind == "ellipse":
            drawn["type"] = "ellipse"
        elif kind != "rect":
            self.lost["templateShapes"] += 1
            return None
        style = shape.find(p("style"))
        if drawn["type"] != "line" and (fill := self._fill(props, style, master)):
            drawn["fill"] = fill
        if line := self._line(props, style, master):
            drawn["line"] = line
        return drawn

    def _shape_text(self, look: dict, body) -> dict:
        text: dict = {"size": min(max(look.get("size") or 18, 1), 400)}
        if font := look.get("font"):
            text["font"] = font[1] or font[0][:64]
            self.fonts.add(font[0])
        if color := _hex(look.get("color")):
            text["color"] = color
        for key in ("bold", "italic"):
            text[key] = look.get(key) is True
        if look.get("align"):
            text["align"] = look["align"]
        props = body.find(a("bodyPr"))
        if props is not None and (anchor := ANCHORED.get(props.get("anchor"))):
            text["anchor"] = anchor
        return text

    def _fill(self, props, style, master: Master) -> str | None:
        if props is not None:
            if props.find(a("noFill")) is not None:
                return None
            if (fill := props.find(a("solidFill"))) is not None:
                return _hex(master.color(fill))
            for other in ("gradFill", "pattFill", "blipFill"):
                if (fill := props.find(a(other))) is not None:
                    self.lost["templateLooks"] += 1
                    stop = fill.find(f"{a('gsLst')}/{a('gs')}")
                    return _hex(master.color(stop)) if stop is not None else None
        ref = style.find(a("fillRef")) if style is not None else None
        if ref is not None and (number(ref.get("idx")) or 0) > 0:
            return _hex(master.color(ref))
        return None

    def _line(self, props, style, master: Master) -> dict | None:
        line = props.find(a("ln")) if props is not None else None
        ref = style.find(a("lnRef")) if style is not None else None
        index = int(number(ref.get("idx")) or 0) if ref is not None else 0
        themed = master.formatted(ref) if index > 0 else None
        width = (
            (number(themed.get("w")) or 9525) / EMU_PER_POINT if themed is not None else LINE_POINTS
        )
        color = master.color(ref) if index > 0 else None
        if line is not None:
            if line.find(a("noFill")) is not None:
                return None
            if (fill := line.find(a("solidFill"))) is not None:
                color = master.color(fill)
            if (own := number(line.get("w"))) is not None:
                width = own / EMU_PER_POINT
        if color is None:
            return None
        return {"color": _hex(color), "width": round(min(max(width, 0), 100), 2)}

    @staticmethod
    def _grouped(group, place: Place) -> Place:
        xfrm = group.find(f"{p('grpSpPr')}/{a('xfrm')}")
        found = [
            xfrm.find(a(tag)) if xfrm is not None else None
            for tag in ("off", "ext", "chOff", "chExt")
        ]
        if None in found:
            return place
        (x, y), (w, h), (cx, cy), (cw, ch) = (
            (_cm(each.get(first)) or 0, _cm(each.get(second)) or 0)
            for each, (first, second) in zip(
                found, (("x", "y"), ("cx", "cy"), ("x", "y"), ("cx", "cy")), strict=True
            )
        )
        across, down = (w / cw if cw else 1), (h / ch if ch else 1)

        def grouped(rect: Rect) -> Rect:
            left, top, wide, tall = rect
            return place(
                (x + (left - cx) * across, y + (top - cy) * down, wide * across, tall * down)
            )

        return grouped

    # Text looks

    def _look(self, chain: list, level: int, master: Master) -> dict:
        look: dict = {}
        for styles in chain:
            if styles is not None:
                look.update(self._layer(styles.find(a(f"lvl{level + 1}pPr")), master))
        return look

    def _layer(self, props, master: Master) -> dict:
        """What a paragraph's properties, or a level's of a list style, set."""
        if props is None:
            return {}
        found: dict = {}
        if (align := props.get("algn")) in ALIGNED:
            found["align"] = ALIGNED[align]
        for child in props:
            local = _local(child)
            if local == "buNone":
                found["bullet"] = ("none",)
            elif local == "buChar":
                found["bullet"] = ("char", child.get("char") or "•")
            elif local == "buAutoNum":
                start = int(number(child.get("startAt")) or 1)
                found["bullet"] = ("auto", child.get("type") or "arabicPeriod", start)
            elif local == "buBlip":
                found["bullet"] = ("char", "•")
            elif local == "buFont":
                found["symbols"] = (child.get("typeface") or "").lower() in SYMBOLS
        found.update(self._run_layer(props.find(a("defRPr")), master))
        return found

    def _run_layer(self, props, master: Master) -> dict:
        if props is None:
            return {}
        found: dict = {}
        if (size := number(props.get("sz"))) is not None:
            found["size"] = size / 100
        for key, attr in (("bold", "b"), ("italic", "i")):
            if (on := props.get(attr)) is not None:
                found[key] = _on(on)
        if (underline := props.get("u")) is not None:
            found["underline"] = underline != "none"
        if (strike := props.get("strike")) is not None:
            found["strike"] = strike != "noStrike"
        if (baseline := number(props.get("baseline"))) is not None:
            found["baseline"] = baseline
        if (fill := props.find(a("solidFill"))) is not None:
            found["color"] = master.color(fill)
        if (marked := props.find(a("highlight"))) is not None:
            found["highlight"] = master.color(marked)
        latin = props.find(a("latin"))
        if latin is not None and latin.get("typeface"):
            found["font"] = master.font(latin.get("typeface"))
        return found

    def _box_of(self, laid: Laid, role: str) -> tuple[str | None, object]:
        """The box a role's text goes in (frontend editor/slides.ts `boxOf`): the layout's own,
        as its frame and placeholder, else the built-in layout's of a kind, as its box."""
        steps = {
            "title": [(None, "title"), (laid.kind, "title"), ("content", "title")],
            "subtitle": [(None, "subtitle"), (laid.kind, "subtitle")],
            "body": [
                (None, "body"),
                (laid.kind, "body"),
                (None, "subtitle"),
                (laid.kind, "subtitle"),
                ("content", "body"),
            ],
            "second": [(None, "second"), (laid.kind, "second"), ("two", "second")],
        }
        built_in = {layout["kind"]: layout for layout in slides.built_in(*self.size)}
        for kind, name in steps[role] + (steps["body"] if role == "subtitle" else []):
            found = laid.boxes.get(name) if kind is None else built_in[kind]["boxes"].get(name)
            if found:
                return kind, found
        raise LookupError(role)

    def _base(self, laid: Laid, role: str, level: int) -> dict:
        """The look the box a role's text goes in gives it at a level; a built-in box's is
        bold for a title, as our styles have it."""
        kind, found = self._box_of(laid, role)
        if kind is None:
            return self._look(found[1].lists(), level, laid.master)
        return {
            "bold": role == "title",
            **self._built_in(found.get("text", {}), level, laid.master),
        }

    def _box_width(self, laid: Laid, role: str) -> float:
        kind, found = self._box_of(laid, role)
        return found[0][2] if kind is None else found["w"]

    @staticmethod
    def _built_in(text: dict, level: int, master: Master) -> dict:
        sizes = text.get("levels") or []
        look: dict = {"size": sizes[level] if level < len(sizes) else text.get("size")}
        if font := text.get("font"):
            look["font"] = (
                master.fonts.get(font, font),
                font if font in ("headings", "text") else None,
            )
        if color := text.get("color"):
            look["color"] = color.removeprefix("#").upper()
        for key in ("bold", "italic", "align"):
            if key in text:
                look[key] = text[key]
        return look

    # Slides

    def _slide(self, part) -> list[Block]:
        root = self._parsed(part)
        laid = self._layout(part.part_related_by(RT.SLIDE_LAYOUT))
        laid.used = True
        items: list[Item] = []
        self._shapes(root.find(f"{p('cSld')}/{p('spTree')}"), part, laid, items, _same)
        own, exact = self._background(root, part, laid.master)
        backed = own is not None and own != self._backdrop(laid)
        self.lost["slideBackgrounds"] += backed and not exact
        timing = root.find(p("timing"))
        self.lost["animations"] += timing is not None and any(
            _local(each) in ANIMATED for each in timing.iter()
        )
        self.lost["transitions"] += any(_moving(each) for each in root.iter(p("transition")))
        for reltype in (RT.COMMENTS, MODERN_COMMENTS):
            if (comments := self._related(part, reltype)) is not None:
                self.lost["slideComments"] += sum(
                    1 for each in parse_xml(comments.blob) if _local(each) == "cm"
                )
        title = next((item for item in items if item.title), None)
        if title is None:
            start = Block("slideBreak")
        elif laid.kind == "title":
            start = Block("title")
        else:
            start = Block("heading", attrs={"level": 1})
        if title is not None:
            for at, block in enumerate(title.blocks):
                if at:
                    self._add(start.runs, "\n", {})
                start.runs.extend(block.runs)
        start.attrs["layout"] = laid.id
        if backed and own:
            start.attrs["background"] = own
        if _off(root.get("show")):
            start.attrs["hidden"] = True
        content = [start]
        for item in items:
            if item.role == "subtitle":
                for block in item.blocks:
                    content.append(self._subtitle(block))
        placed = sorted(
            (item for item in items if item is not title and item.role in ("body", "second")),
            key=lambda item: (item.rect[1], item.rect[0]) if item.rect else (0, 0),
        )
        for role in ("body", "second"):
            column = [block for item in placed if item.role == role for block in item.blocks]
            if role == "second" and column:
                content.append(Block("columnBreak"))
            content.extend(column)
        content.extend(self._notes(part))
        return content

    @staticmethod
    def _subtitle(block: Block) -> Block:
        if block.type != "paragraph":
            return block
        attrs = {key: value for key, value in block.attrs.items() if key == "align"}
        return Block("subtitle", id=block.id, attrs=attrs, runs=block.runs)

    def _shapes(self, tree, part, laid: Laid, items: list[Item], place: Place) -> None:
        for shape in tree if tree is not None else []:
            local = _local(shape)
            if shape.tag == ns(MC, "AlternateContent"):
                self._shapes(_chosen(shape), part, laid, items, place)
            elif local == "sp":
                self._text_shape(shape, part, laid, items, place)
            elif local == "pic":
                self._picture(shape, part, laid, items, place)
            elif local == "graphicFrame":
                self._frame(shape, part, laid, items, place)
            elif local == "grpSp":
                self._shapes(shape, part, laid, items, self._grouped(shape, place))
            elif local in ("cxnSp", "contentPart"):
                self.lost["shapes"] += 1

    def _placed(
        self, shape, frame, laid: Laid, place: Place
    ) -> tuple[str, Rect | None, list, bool] | None:
        """Where a shape's content goes, where it stands, its text styles and whether it is
        its slide's title; None for a slide number, date or footer, which the layout shows."""
        ph = _ph(shape)
        own = _rect(frame)
        if ph is None:
            rect = place(own) if own else None
            role = next(
                (
                    role
                    for role in ("body", "second")
                    if role in laid.boxes and _inside(rect, laid.boxes[role][0])
                ),
                None,
            )
            if role is None:
                self.lost["positions"] += 1
                role = laid.column(rect)
            return role, rect, [self.defaults], False
        type, idx = ph.get("type", "obj"), ph.get("idx")
        if type in FOOTERS or type == "hdr":
            return None
        holder = laid.holder(type, idx)
        rect = own or (holder.rect if holder else None)
        rect = place(rect) if rect else None
        if type in TITLES:
            role = "title"
        elif type == "subTitle":
            role = "subtitle"
        elif holder is not None and holder.role and idx is not None:
            role = holder.role
        else:
            role = laid.column(rect)
        if holder is not None:
            chain = holder.lists()
        else:
            style = laid.master.styles["title" if type in TITLES else "body"]
            chain = [style]
        return role, rect, chain, type in TITLES

    def _text_shape(self, shape, part, laid: Laid, items: list[Item], place: Place) -> None:
        body = shape.find(p("txBody"))
        ph = _ph(shape)
        if ph is not None and ph.get("type") in FOOTERS:
            self._footer(laid, ph.get("type"), body)
            return
        if ph is None and not _texted(body):
            self.lost["shapes"] += 1
            return
        placed = self._placed(shape, shape.find(p("spPr")), laid, place)
        if placed is None or body is None:
            return
        role, rect, chain, title = placed
        chain = [*chain, body.find(a("lstStyle"))]
        blocks = self._paragraphs(
            body, chain, lambda level: self._base(laid, role, level), part, laid.master
        )
        if title or blocks:
            items.append(Item(role, rect, blocks, title))

    def _footer(self, laid: Laid, type: str, body) -> None:
        """A slide number, date or footer a slide shows, which its layout then shows: a date
        as the date the slides are shown on, unless the slide writes one of its own."""
        content = ""
        dated = body is not None and body.find(f".//{a('fld')}") is not None
        if type == "ftr" or (type == "dt" and not dated):
            content = _plain(body) if body is not None else ""
            if not content:
                return
        laid.shown.setdefault(type, content)

    def _offered(self, laid: Laid) -> None:
        """The slide number, date and footer a layout no slide is laid out by gives a new slide,
        as the header and footer settings of the layout, or else of its master, say."""
        settings = laid.root.find(p("hf"))
        if settings is None:
            settings = laid.master.root.find(p("hf"))
        if settings is None:
            return
        for holder in laid.holders:
            if holder.type in FOOTERS and not _off(settings.get(holder.type)):
                self._footer(laid, holder.type, holder.shape.find(p("txBody")))

    def _picture(self, shape, part, laid: Laid, items: list[Item], place: Place) -> None:
        props = shape.find(f"{p('nvPicPr')}/{p('nvPr')}")
        if props is not None and any(_local(each) in MEDIA for each in props.iter()):
            self.lost["media"] += 1
            return
        blip = shape.find(f"{p('blipFill')}/{a('blip')}")
        rid = blip.get(ns(R, "embed")) if blip is not None else None
        found = office.picture(part.rels.get(rid) if rid else None)
        if found is None:
            self.lost["images"] += 1
            return
        placed = self._placed(shape, shape.find(p("spPr")), laid, place)
        if placed is None:
            return
        role, rect, _, _ = placed
        self.images[found[0]] = found[1]
        named = shape.find(f"{p('nvPicPr')}/{p('cNvPr')}")
        alt = (named.get("descr") or named.get("title") or "") if named is not None else ""
        image = Block("image", attrs={"blob": found[0], "alt": alt.strip()[:500]})
        if rect:
            wide = round(rect[2] / self._box_width(laid, role) * 100)
            if wide < 100:
                image.attrs["width"] = max(wide, 5)
        items.append(Item("body" if role in ("title", "subtitle") else role, rect, [image]))

    def _frame(self, shape, part, laid: Laid, items: list[Item], place: Place) -> None:
        data = shape.find(f"{a('graphic')}/{a('graphicData')}")
        uri = data.get("uri", "") if data is not None else ""
        if uri.startswith(DIAGRAM):
            self.lost["diagrams"] += 1
            return
        if uri not in (TABLE, CHART):
            self.lost["objects"] += 1
            return
        placed = self._placed(shape, shape, laid, place)
        if placed is None:
            return
        role, rect, _, _ = placed
        role = "body" if role in ("title", "subtitle") else role
        if uri == TABLE:
            table = data.find(a("tbl"))
            made = self._table(table, part, laid, role) if table is not None else None
            if made is not None:
                items.append(Item(role, rect, [made]))
            return
        chart = data.find(f"{ns(CHART, 'chart')}")
        rid = chart.get(ns(R, "id")) if chart is not None else None
        charted = office.chart(part.rels.get(rid) if rid else None, self.locale)
        if charted is None:
            self.lost["charts"] += 1
            return
        self.lost.update(charted.lost)
        self.fonts.update(charted.fonts)
        items.append(Item(role, rect, list(charted.blocks)))

    def _table(self, tbl, part, laid: Laid, role: str) -> Block | None:
        grid = [
            number(col.get("w")) or 0.0 for col in tbl.iterfind(f"{a('tblGrid')}/{a('gridCol')}")
        ]
        rows = tbl.findall(a("tr"))
        if not rows or not grid:
            return None
        row_ids, col_ids = [new_id() for _ in rows], [new_id() for _ in grid]
        known = [width for width in grid if width > 0]
        fallback = sum(known) / len(known) if known else 1.0
        widths = [width if width > 0 else fallback for width in grid]
        total = sum(widths)
        percent = {
            col: round(width / total * 100, 1) for col, width in zip(col_ids, widths, strict=True)
        }
        design = self.looks.design(tbl.find(a("tblPr")), laid.master)
        table = Block(
            "table",
            attrs={"widths": percent, "designs": [design]},
            grid=Grid(row_ids, col_ids),
        )
        floor = self._base(laid, role, 0)
        for y, tr in enumerate(rows):
            for x, tc in enumerate(tr.findall(a("tc"))):
                if x >= len(col_ids):
                    self.lost["tableCells"] += 1
                    break
                if _on(tc.get("hMerge")) or _on(tc.get("vMerge")):
                    continue
                body = tc.find(a("txBody"))
                blocks = []
                if body is not None:
                    chain = [self.defaults, body.find(a("lstStyle"))]
                    blocks = self._paragraphs(body, chain, lambda _: floor, part, laid.master)
                props = tc.find(a("tcPr"))
                cell = Cell(
                    row_ids[y],
                    col_ids[x],
                    blocks or [Block("paragraph")],
                    fill=self.looks.flat(self.looks.filled(props, laid.master)),
                    edges=self.looks.edges(props, laid.master),
                )
                across = max(int(number(tc.get("gridSpan")) or 1), 1)
                down = max(int(number(tc.get("rowSpan")) or 1), 1)
                if across > 1 or down > 1:
                    cell.to = (
                        f"{row_ids[min(y + down, len(row_ids)) - 1]}:"
                        f"{col_ids[min(x + across, len(col_ids)) - 1]}"
                    )
                if (
                    cell.to
                    or cell.fill
                    or cell.edges
                    or any(each.runs or each.type != "paragraph" for each in cell.blocks)
                ):
                    table.cells.append(cell)
        self._cast(table, design)
        return table

    def _cast(self, table: Block, design: dict) -> None:
        """PowerPoint casts a table's shadow from what it fills: none from a table that fills
        nothing, and one the table's box cannot draw from a table that fills only some of it."""
        if "shadow" not in design or "background" in design or table.grid is None:
            return
        rows, cols = table.grid.rows, table.grid.cols
        fills = {}
        for cell in table.cells:
            if cell.fill is None:
                continue
            bottom, right = cell.to.split(":") if cell.to else (cell.row, cell.col)
            for y in range(rows.index(cell.row), rows.index(bottom) + 1):
                for x in range(cols.index(cell.col), cols.index(right) + 1):
                    fills[(y, x)] = cell.fill
        drawn = designs.resolved(design, len(rows), len(cols))
        filled = [
            fills.get(slot, each.fill) not in (None, designs.NONE) for slot, each in drawn.items()
        ]
        if not all(filled):
            self.lost["tableStyles"] += any(filled)
            del design["shadow"]

    def _notes(self, part) -> list[Block]:
        notes = self._related(part, RT.NOTES_SLIDE)
        if notes is None:
            return []
        root = self._parsed(notes)
        held = self._related(notes, RT.NOTES_MASTER)
        master = self._master(held, notes=True) if held is not None else None
        if master is None:
            return []
        found = []
        for shape in root.iterfind(f"{p('cSld')}/{p('spTree')}/{p('sp')}"):
            ph = _ph(shape)
            body = shape.find(p("txBody"))
            if ph is None or ph.get("type") != "body" or body is None:
                continue
            above = master.holders.get("body")
            chain = [
                *(above.lists() if above else [master.styles["body"]]),
                body.find(a("lstStyle")),
            ]
            base = chain[:-1]
            for block in self._paragraphs(
                body, chain, lambda level, base=base: self._look(base, level, master), notes, master
            ):
                block.attrs["speaker"] = True
                found.append(block)
        return found

    # Paragraphs

    def _paragraphs(
        self, body, chain: list, base: Callable[[int], dict], part, master: Master
    ) -> list[Block]:
        """A text body's paragraphs as blocks, at its edges without empty ones, each run's
        marks what it shows unlike the box its text goes in."""
        found: list[Block] = []
        counts: dict[int, tuple[str, int]] = {}
        for para in body.iterfind(a("p")):
            props = para.find(a("pPr"))
            level = min(int(number(props.get("lvl")) or 0) if props is not None else 0, DEEPEST)
            look = self._look(chain, level, master)
            look.update(self._layer(props, master))
            floor = base(level)
            block = Block("paragraph")
            self._runs(para, look, floor, part, master, block.runs)
            for deeper in [at for at in counts if at > level]:
                del counts[deeper]
            bullet = look.get("bullet") if block.runs else None
            if bullet and bullet[0] != "none":
                self._listed(block, bullet, level, look, chain, master, counts)
            elif block.runs:
                counts.pop(level, None)
            if level:
                block.attrs["indent"] = level * INDENT_STEP
            if look.get("align") and look["align"] != (floor.get("align") or "left"):
                block.attrs["align"] = look["align"]
            found.append(block)
        while found and not found[0].runs:
            found.pop(0)
        while found and not found[-1].runs:
            found.pop()
        return found

    def _listed(
        self,
        block: Block,
        bullet: tuple,
        level: int,
        look: dict,
        chain: list,
        master: Master,
        counts: dict[int, tuple[str, int]],
    ) -> None:
        kind = "bullet" if bullet[0] == "char" else "number"
        block.attrs["list"] = kind
        levels = [
            self._form(look if at == level else self._look(chain, at, master), at)
            for at in range(lists.LEVELS)
        ]
        if levels[level] == lists.standard(kind, level) and bullet[0] == "auto":
            self.lost["listFormats"] += bullet[1] not in NUMBERED
        if not lists.is_standard(levels):
            had = {**self.known, **self.formats}
            id = next((id for id, known in had.items() if known == levels), None)
            if id is None:
                id = new_id()
                self.formats[id] = levels
            block.attrs["format"] = id
        if kind == "number":
            _, scheme, start = bullet
            before = counts.get(level)
            count = before[1] + 1 if before and before[0] == scheme else start
            counts[level] = (scheme, count)
            self.numbers[block.id] = count

    def _form(self, look: dict, level: int) -> dict:
        bullet = look.get("bullet") or ("none",)
        if bullet[0] == "char":
            mark = lists.BULLETS[level % 3] if look.get("symbols") else bullet[1][: lists.AFFIX_MAX]
            return {"numbering": "", "prefix": mark, "suffix": "", "nested": False}
        if bullet[0] == "auto":
            form = NUMBERED.get(bullet[1])
            if form is None:
                return lists.standard("number", level)
            numbering, prefix, suffix = form
            return {"numbering": numbering, "prefix": prefix, "suffix": suffix, "nested": False}
        return lists.standard("bullet", level)

    def _runs(self, para, look: dict, floor: dict, part, master: Master, out: list) -> None:
        for child in para:
            local = _local(child)
            if local not in ("r", "br", "fld"):
                continue
            props = child.find(a("rPr"))
            shown = {**look, **self._run_layer(props, master)}
            marks = self._marks(shown, floor, self._link(props, part))
            if local == "br":
                self._add(out, "\n", marks)
            elif local == "fld" and child.get("type") == "slidenum":
                out.append(Field("page"))
            elif local == "fld" and (child.get("type") or "").startswith("datetime"):
                out.append(Field("date"))
            else:
                self._add(out, child.findtext(a("t")) or "", marks)

    @staticmethod
    def _add(out: list, text: str, marks: dict) -> None:
        if not text:
            return
        if out and isinstance(out[-1], Run) and out[-1].marks == marks:
            out[-1].text += text
        else:
            out.append(Run(text, marks))

    def _link(self, props, part) -> str | None:
        click = props.find(a("hlinkClick")) if props is not None else None
        if click is None:
            return None
        rid = click.get(ns(R, "id"))
        relationship = part.rels.get(rid) if rid else None
        if relationship is None or not relationship.is_external:
            self.lost["internalLinks"] += 1
            return None
        href = office.safe(relationship.target_ref)
        self.lost["links"] += href is None
        return href

    def _marks(self, look: dict, base: dict, link: str | None) -> dict:
        marks: dict[str, dict] = {}
        if link:
            marks["link"] = {"href": link}
        for mark, key in (("strong", "bold"), ("em", "italic"), ("strike", "strike")):
            if look.get(key) and not base.get(key):
                marks[mark] = {}
        if look.get("underline") and not base.get("underline") and not link:
            marks["underline"] = {}
        if baseline := look.get("baseline"):
            marks["sup" if baseline > 0 else "sub"] = {}
        if not link and look.get("color") != base.get("color"):
            if color := colors.text_color(look.get("color")):
                marks["color"] = {"color": color}
        if shade := colors.highlight(None, look.get("highlight")):
            marks["highlight"] = {"color": shade}
        font, plain = look.get("font"), base.get("font")
        if font and (plain is None or font[0] != plain[0]):
            marks["font"] = {"family": font[0]}
            self.fonts.add(font[0])
        size = look.get("size")
        if size is not None and size != base.get("size") and 1 <= size <= 400:
            marks["size"] = {"pt": size}
        return marks
