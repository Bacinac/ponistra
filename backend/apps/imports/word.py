"""What the parts of a Word file say, as plain values: the look of its styles and runs,
layered as Word layers them, and the numbers its numbering gives."""

import re
from dataclasses import dataclass
from itertools import pairwise

from apps.content import palette
from apps.content.numbering import AFFIX_MAX
from apps.content.schema import DEFS

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DIAGRAM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
V = "urn:schemas-microsoft-com:vml"
VO = "urn:schemas-microsoft-com:office:office"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
MATH = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"

TWIPS_PER_CM = 1440 / 2.54
EMU_PER_CM = 360_000
LEVELS = 9
OFF = {"0", "false", "off"}
FORMATS = {
    "decimal": "1",
    "decimalZero": "1",
    "lowerLetter": "a",
    "upperLetter": "A",
    "lowerRoman": "i",
    "upperRoman": "I",
}
PLACEHOLDER = re.compile(r"%([1-9])")
# The characters a bullet in a symbol font stands for, by the font (frontend editor/lists.ts).
SYMBOLS = {
    "symbol": {"·": "•", "-": "–"},
    "wingdings": {"§": "▪", "Ø": "➢", "ü": "✓", "v": "❖", "q": "❑", "n": "■", "l": "●"},
    "courier new": {"o": "◦"},
}
SYMBOL_FONTS = {"symbol", "wingdings", "wingdings 2", "wingdings 3", "webdings"}
ALIGN = {
    "left": None,
    "start": None,
    "center": "center",
    "right": "right",
    "end": "right",
    "both": "justify",
    "distribute": "justify",
    "lowKashida": "justify",
    "mediumKashida": "justify",
    "highKashida": "justify",
    "thaiDistribute": "justify",
}
# A table style's conditional formats by the parts of a design (D30) they are.
DESIGN_PARTS = {
    "band1Horz": "rowBand1",
    "band2Horz": "rowBand2",
    "band1Vert": "columnBand1",
    "band2Vert": "columnBand2",
    "firstCol": "firstColumn",
    "lastCol": "lastColumn",
    "firstRow": "header",
    "lastRow": "totals",
    "nwCell": "topLeft",
    "neCell": "topRight",
    "swCell": "bottomLeft",
    "seCell": "bottomRight",
}
EDGE_SIDES = {
    "top": "top",
    "bottom": "bottom",
    "left": "left",
    "start": "left",
    "right": "right",
    "end": "right",
    "insideH": "insideH",
    "insideV": "insideV",
}
VALIGN = {"top": "top", "center": "center", "both": "center", "bottom": "bottom"}
STROKES = set(DEFS["stroke"]["enum"])
HEX = re.compile(r"[0-9A-Fa-f]{6}")


def w(name: str) -> str:
    return f"{{{W}}}{name}"


def ns(space: str, name: str) -> str:
    return f"{{{space}}}{name}"


def value(element, name: str = "val") -> str | None:
    return None if element is None else element.get(w(name))


def number(text: str | None) -> float | None:
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def toggle(element) -> bool | None:
    if element is None:
        return None
    found = element.get(w("val"))
    return found is None or found.lower() not in OFF


def run_layer(rpr, theme: dict[str, str]) -> dict:
    """The run properties one layer sets: a style's, or a run's own."""
    if rpr is None:
        return {}
    found: dict = {}
    if (fonts := rpr.find(w("rFonts"))) is not None:
        # A theme slot outranks the name written beside it.
        slot = fonts.get(w("asciiTheme")) or fonts.get(w("hAnsiTheme"))
        name = fonts.get(w("ascii")) or fonts.get(w("hAnsi"))
        if slot:
            side = "headings" if slot.startswith("major") else "text"
            found["font"] = (theme.get(side) or name, side)
        elif name:
            found["font"] = (name, None)
    if (size := number(value(rpr.find(w("sz"))))) is not None:
        found["size"] = size / 2
    if (kern := number(value(rpr.find(w("kern"))))) is not None:
        found["kern"] = kern / 2
    toggles = (("bold", "b"), ("italic", "i"), ("strike", "strike"), ("hidden", "vanish"))
    for key, tag in (*toggles, ("caps", "caps")):
        if (on := toggle(rpr.find(w(tag)))) is not None:
            found[key] = on
    if toggle(rpr.find(w("dstrike"))):
        found["strike"] = True
    if (underline := rpr.find(w("u"))) is not None:
        found["underline"] = (value(underline) or "single") != "none"
    if (align := value(rpr.find(w("vertAlign")))) is not None:
        found["vertAlign"] = align
    if (color := value(rpr.find(w("color")))) is not None:
        found["color"] = None if color == "auto" else color.upper()
    if (marked := value(rpr.find(w("highlight")))) is not None:
        found["highlight"] = None if marked == "none" else marked
    if (shading := rpr.find(w("shd"))) is not None:
        fill = value(shading, "fill")
        found["shading"] = None if fill in (None, "auto") else fill.upper()
    return found


def kerned(look: dict) -> bool:
    """Whether Word kerns text of a look: from the size its kerning starts at, which none or
    zero leaves off."""
    start = look.get("kern") or 0
    return start > 0 and look.get("size", 10.0) >= start


TAB_KINDS = {
    "left": "left",
    "start": "left",
    "center": "center",
    "right": "right",
    "end": "right",
    "decimal": "decimal",
}
LEADERS = {
    "dot": "dot",
    "middleDot": "dot",
    "hyphen": "hyphen",
    "underscore": "underscore",
    "heavy": "underscore",
}


def layered(below: dict, above: dict) -> dict:
    """Paragraph properties with a layer's over another's; its tab stops and borders join those
    below, clearing those it clears."""
    merged = {**below, **above}
    for joined in ("tabs", "borders"):
        if joined in below and joined in above:
            merged[joined] = {**below[joined], **above[joined]}
    return merged


def _tab_stops(tabs) -> dict:
    """A layer's tab stops by their position in twips, None where it clears one below."""
    found: dict = {}
    for tab in tabs.findall(w("tab")):
        position = number(value(tab, "pos"))
        if position is None:
            continue
        kind = value(tab)
        found[int(position)] = (
            (TAB_KINDS[kind], LEADERS.get(value(tab, "leader") or ""))
            if kind in TAB_KINDS
            else None
        )
    return found


def paragraph_layer(ppr) -> dict:
    """The paragraph properties one layer sets."""
    if ppr is None:
        return {}
    found: dict = {}
    if (tabs := ppr.find(w("tabs"))) is not None:
        found["tabs"] = _tab_stops(tabs)
    if (align := value(ppr.find(w("jc")))) is not None:
        found["align"] = align
    if (borders := ppr.find(w("pBdr"))) is not None:
        found["borders"] = {
            side.tag.removeprefix(f"{{{W}}}"): None
            if value(side) in ("nil", "none")
            else (value(side), value(side, "sz"), value(side, "color"))
            for side in borders
        }
    if (spacing := ppr.find(w("spacing"))) is not None:
        for side in ("before", "after"):
            if toggle_of(spacing, f"{side}Autospacing"):
                found[side] = 14.0
            elif (twips := number(value(spacing, side))) is not None:
                found[side] = twips / 20
        if (line := number(value(spacing, "line"))) is not None:
            found["line"] = (line, value(spacing, "lineRule") or "auto")
    if (indent := ppr.find(w("ind"))) is not None:
        left = number(value(indent, "left") or value(indent, "start"))
        if left is not None:
            found["indent"] = left / TWIPS_PER_CM
        right = number(value(indent, "right") or value(indent, "end"))
        if right is not None:
            found["right"] = right / TWIPS_PER_CM
        if (hanging := number(value(indent, "hanging"))) is not None:
            found["first"] = -hanging / TWIPS_PER_CM
        elif (first := number(value(indent, "firstLine"))) is not None:
            found["first"] = first / TWIPS_PER_CM
    if (numbered := ppr.find(w("numPr"))) is not None:
        num = value(numbered.find(w("numId")))
        level = number(value(numbered.find(w("ilvl"))))
        if num is not None:
            found["num"] = None if num == "0" else num
        if level is not None:
            found["ilvl"] = int(level)
    if (outline := number(value(ppr.find(w("outlineLvl"))))) is not None:
        found["outline"] = int(outline)
    if (before := ppr.find(w("pageBreakBefore"))) is not None:
        found["pageBefore"] = (value(before) or "on").lower() not in OFF
    return found


def toggle_of(element, name: str) -> bool:
    found = element.get(w(name))
    return found is not None and found.lower() not in OFF


def _hex(color: str | None) -> str | None:
    return f"#{color.lower()}" if color and HEX.fullmatch(color) else None


def edge(border) -> tuple[dict | str | None, int]:
    """A w:top, w:insideH and the like as a design's edge, and whether its art border was
    drawn as a single line; None where the element is not there."""
    kind = value(border)
    if kind is None:
        return None, 0
    if kind in ("nil", "none"):
        return "none", 0
    eighths = number(value(border, "sz")) or 2
    found: dict = {"line": kind if kind in STROKES else "single", "width": eighths / 8}
    if color := _hex(value(border, "color")):
        found["color"] = palette.named("text", color)
    return found, int(kind not in STROKES)


def edges_of(element) -> tuple[dict, int]:
    """The edges a w:tblBorders or a w:tcBorders sets, and how many it could not hold."""
    found, lost = {}, 0
    for border in element if element is not None else ():
        side = EDGE_SIDES.get(border.tag.removeprefix(f"{{{W}}}"))
        line, art = edge(border)
        if side and line is not None:
            found[side] = line
            lost += art
    return found, lost


def shading(shd) -> tuple[str, int]:
    """A w:shd as a part's fill, "none" taking away a fill beneath; a pattern counts as lost
    and fills with its background."""
    kind = value(shd) or "clear"
    if kind == "nil":
        return "none", 0
    color = _hex(value(shd, "color")) or "#000000"
    fill = color if kind == "solid" else _hex(value(shd, "fill"))
    return (palette.named("highlight", fill) if fill else "none"), int(
        kind not in ("clear", "solid")
    )


def _design_marks(rpr, theme: dict[str, str]) -> dict:
    run = run_layer(rpr, theme)
    marks: dict = {}
    for mark, key in (
        ("strong", "bold"),
        ("em", "italic"),
        ("strike", "strike"),
        ("underline", "underline"),
    ):
        if key in run:
            marks[mark] = {} if run[key] else False
    if "color" in run:
        color = _hex(run["color"])
        marks["color"] = {"color": palette.named("text", color)} if color else False
    if "font" in run:
        marks["font"] = {"family": run["font"][0]}
    if 1 <= run.get("size", 0) <= 400:
        marks["size"] = {"pt": run["size"]}
    return marks


def _design_part(element, theme: dict[str, str], edged: bool = True) -> tuple[dict, int]:
    """What a table style, or one of its conditional formats, sets of a part of a design; the
    edges only where Word draws them, which it never does for a style's own `tcBorders`."""
    part: dict = {}
    lost = 0
    rpr = element.find(w("rPr"))
    if marks := _design_marks(rpr, theme):
        part["marks"] = marks
    if rpr is not None:
        for tag, caps in (("caps", "all"), ("smallCaps", "small")):
            if (on := toggle(rpr.find(w(tag)))) is not None:
                part["caps"] = caps if on else "none"
    if (align := value(element.find(f"{w('pPr')}/{w('jc')}"))) in ALIGN:
        part["align"] = ALIGN[align] or "left"
    tcpr = element.find(w("tcPr"))
    if tcpr is not None:
        if (shd := tcpr.find(w("shd"))) is not None:
            part["fill"], patterned = shading(shd)
            lost += patterned
        if (valign := value(tcpr.find(w("vAlign")))) in VALIGN:
            part["valign"] = VALIGN[valign]
        edges, art = edges_of(tcpr.find(w("tcBorders"))) if edged else ({}, 0)
        if edges:
            part["edges"] = edges
        lost += art + (tcpr.find(w("tcMar")) is not None)
    return part, lost


def _merged(below: dict, above: dict) -> dict:
    merged = below | above
    for key in ("marks", "edges"):
        if key in below and key in above:
            merged[key] = below[key] | above[key]
    return merged


class Styles:
    """The styles part: each style's look as its chain of bases and the document's
    defaults give it."""

    def __init__(self, root, theme: dict[str, str]):
        self.theme = theme
        self.by_id: dict[str, object] = {}
        self.defaults: dict[str, str] = {}
        self.run_defaults: dict = {}
        self.paragraph_defaults: dict = {}
        self.looks: dict[str | None, tuple[dict, dict]] = {}
        self.characters: dict[str | None, dict] = {}
        if root is None:
            return
        for style in root.iterfind(w("style")):
            id = style.get(w("styleId"))
            if not id:
                continue
            self.by_id[id] = style
            if toggle_of(style, "default"):
                self.defaults.setdefault(style.get(w("type")) or "paragraph", id)
        # Files that mark no default name Word's own styles.
        for type, name in (("paragraph", "normal"), ("table", "normal table")):
            if type not in self.defaults and (found := self.named(name, type)):
                self.defaults[type] = found
        if (defaults := root.find(w("docDefaults"))) is not None:
            self.run_defaults = run_layer(defaults.find(f"{w('rPrDefault')}/{w('rPr')}"), theme)
            self.paragraph_defaults = paragraph_layer(
                defaults.find(f"{w('pPrDefault')}/{w('pPr')}")
            )

    def paragraph_style(self, id: str | None) -> str | None:
        return id if id in self.by_id else self.defaults.get("paragraph")

    def named(self, name: str, type: str = "paragraph") -> str | None:
        """The style of one of Word's own names, such as "heading 1"."""
        for id, style in self.by_id.items():
            if (style.get(w("type")) or "paragraph") == type and (
                value(style.find(w("name"))) or ""
            ).lower() == name:
                return id
        return None

    def chain(self, id: str | None) -> list:
        """The style and its bases, the farthest base first."""
        found, seen = [], set()
        while id and id not in seen and (style := self.by_id.get(id)) is not None:
            seen.add(id)
            found.append(style)
            id = value(style.find(w("basedOn")))
        return found[::-1]

    def name(self, id: str) -> str:
        style = self.by_id.get(id)
        return (value(style.find(w("name"))) if style is not None else None) or id

    def paragraph_look(self, id: str | None) -> tuple[dict, dict]:
        """The paragraph and run properties of a paragraph style."""
        if id not in self.looks:
            paragraph, run = dict(self.paragraph_defaults), dict(self.run_defaults)
            for style in self.chain(id):
                paragraph = layered(paragraph, paragraph_layer(style.find(w("pPr"))))
                run.update(run_layer(style.find(w("rPr")), self.theme))
            self.looks[id] = paragraph, run
        return self.looks[id]

    def character_look(self, id: str | None) -> dict:
        if id not in self.characters:
            run: dict = {}
            for style in self.chain(id):
                run.update(run_layer(style.find(w("rPr")), self.theme))
            self.characters[id] = run
        return self.characters[id]

    def design(self, id: str | None, tblpr=None) -> tuple[dict | None, int]:
        """The design (D30) of a table of the style, with the table's own lines, bands,
        spacing and shading over its style's, and how much of it the design could not hold;
        None for a table that draws nothing. Its switches are the table's look. The shading
        shows only between cells set apart, so only those keep it."""
        parts: dict[str, dict] = {}
        lines: dict = {}
        bands: dict[str, int] = {}
        spacing = None
        background = None
        lost = 0
        for layer in [*self.chain(id), None]:
            own = layer.find(w("tblPr")) if layer is not None else tblpr
            if own is not None:
                found, art = edges_of(own.find(w("tblBorders")))
                lines |= found
                lost += art
                for key, tag in (
                    ("rows", "tblStyleRowBandSize"),
                    ("columns", "tblStyleColBandSize"),
                ):
                    if (size := number(value(own.find(w(tag))))) is not None:
                        bands[key] = max(0, min(int(size), 99))
                gap = own.find(w("tblCellSpacing"))
                if gap is not None and (value(gap, "type") or "dxa") == "dxa":
                    spacing = (number(value(gap, "w")) or 0) / 20 or None
                if (shd := own.find(w("shd"))) is not None:
                    background, patterned = shading(shd)
                    lost += patterned
            if layer is None:
                break
            conditions = [(layer, "table")] + [
                (each, DESIGN_PARTS.get(each.get(w("type")) or ""))
                for each in layer.iterfind(w("tblStylePr"))
            ]
            for element, name in conditions:
                if name is None:
                    continue
                part, count = _design_part(element, self.theme, element is not layer)
                lost += count
                if part or (name != "table" and len(element)):
                    parts[name] = _merged(parts.get(name, {}), part)
        background = background if spacing and background != "none" else None
        if (
            not any(parts.values())
            and not background
            and not any(each != "none" for each in lines.values())
        ):
            return None, lost
        design: dict = {"rules": "word"}
        if id in self.by_id:
            design["name"] = self.name(id)
        if parts:
            design["parts"] = parts
        if lines:
            design["lines"] = lines
        sizes = {key: [bands.get(key, 0)] * 2 for key in ("rows", "columns")}
        banded = any(
            name in parts for name in ("rowBand1", "rowBand2", "columnBand1", "columnBand2")
        )
        if banded and any(size != [1, 1] for size in sizes.values()):
            design["bands"] = sizes
        if spacing:
            design["spacing"] = min(spacing, 30)
        if background:
            design["background"] = background
        return design, lost

    def kind(self, id: str | None) -> tuple[str, int]:
        """What a paragraph style is to us: title, subtitle, a heading of a level (1 to 9),
        or text, by the nearest of Word's own styles it is based on."""
        for style in reversed(self.chain(id)):
            name = (value(style.find(w("name"))) or "").lower()
            if name in ("title", "subtitle"):
                return name, 0
            if found := re.fullmatch(r"heading ([1-9])", name):
                return "heading", int(found[1])
        outline = self.paragraph_look(id)[0].get("outline")
        if outline is not None and 0 <= outline < LEVELS:
            return "heading", outline + 1
        return "text", 0


@dataclass
class Level:
    abstract: str
    format: str
    text: str
    start: int
    font: str
    # Word shows the numbers of the levels above in digits, whatever their own form.
    legal: bool

    @property
    def numbering(self) -> str:
        return FORMATS.get(self.format, "1")

    @property
    def placeholders(self) -> list[re.Match]:
        return list(PLACEHOLDER.finditer(self.text))

    @property
    def shown(self) -> bool:
        return self.format != "none" and bool(self.text)

    @property
    def affixes(self) -> tuple[str, str, bool]:
        """The text before the number, after it, and whether the numbers of the levels
        above lead it."""
        found = self.placeholders
        if not found:
            return self.text, "", False
        return self.text[: found[0].start()], self.text[found[-1].end() :], len(found) > 1

    @property
    def bulleted(self) -> bool:
        """Whether every item shows the same mark: a bullet, or words without a number."""
        return self.format == "bullet" or not self.placeholders

    @property
    def symbol(self) -> str | None:
        """The bullet as the characters it shows, which a symbol font draws in its own way."""
        text = "".join(
            chr(ord(char) & 0xFF) if 0xF000 <= ord(char) <= 0xF0FF else char for char in self.text
        )
        font = self.font.lower()
        if text in SYMBOLS.get(font, {}):
            return SYMBOLS[font][text]
        if font in SYMBOL_FONTS or any(0xE000 <= ord(char) <= 0xF8FF for char in text):
            return None
        return text

    def listed(self, ilvl: int, above: list[Level | None]) -> dict | None:
        """The level as our list shows it, if it can: a bullet, or a number in a form between
        words, led by the numbers of all the levels above as Word's "%1.%2." leads it."""
        if self.bulleted:
            symbol = self.symbol
            if not symbol or len(symbol) > AFFIX_MAX:
                return None
            return {"numbering": "", "prefix": symbol, "suffix": "", "nested": False}
        found = self.placeholders
        if self.format not in FORMATS or self.format == "decimalZero":
            return None
        if found[-1].group(1) != str(ilvl + 1):
            return None
        nested = len(found) > 1
        if nested:
            if [int(each.group(1)) for each in found] != list(range(1, ilvl + 2)):
                return None
            if any(self.text[a.end() : b.start()] != "." for a, b in pairwise(found)):
                return None
            for level in above:
                if level is None or level.bulleted or level.format not in FORMATS:
                    return None
                if level.format == "decimalZero" or (self.legal and level.numbering != "1"):
                    return None
        before, after, _ = self.affixes
        if len(before) > AFFIX_MAX or len(after) > AFFIX_MAX:
            return None
        return {"numbering": self.numbering, "prefix": before, "suffix": after, "nested": nested}

    @property
    def worded(self) -> bool:
        """Whether words surround the number, as in "Article 1", which counts on through the
        document as a style's number does rather than as a list's."""
        before, after, _ = self.affixes
        return any(char.isalpha() for char in before + after)


class Numbering:
    """The numbering part, and Word's counters as the paragraphs using it are read: one
    set per abstract numbering, which a numbering's start override sets again the first
    time it is used."""

    def __init__(self, root, styles: Styles):
        self.styles = styles
        self.abstracts: dict[str, dict[int, object]] = {}
        self.links: dict[str, str] = {}
        self.nums: dict[str, tuple[str, dict[int, int], dict[int, object]]] = {}
        self.counters: dict[str, list[int | None]] = {}
        self.overridden: set[tuple[str, int]] = set()
        if root is None:
            return
        for abstract in root.iterfind(w("abstractNum")):
            id = abstract.get(w("abstractNumId"))
            self.abstracts[id] = {
                int(number(lvl.get(w("ilvl"))) or 0): lvl for lvl in abstract.iterfind(w("lvl"))
            }
            if (link := value(abstract.find(w("numStyleLink")))) is not None:
                self.links[id] = link
        for num in root.iterfind(w("num")):
            starts, levels = {}, {}
            for override in num.iterfind(w("lvlOverride")):
                ilvl = int(number(override.get(w("ilvl"))) or 0)
                if (start := number(value(override.find(w("startOverride"))))) is not None:
                    starts[ilvl] = int(start)
                if (lvl := override.find(w("lvl"))) is not None:
                    levels[ilvl] = lvl
            self.nums[num.get(w("numId"))] = (
                value(num.find(w("abstractNumId"))) or "",
                starts,
                levels,
            )

    def _abstract(self, num: str) -> str | None:
        seen = set()
        abstract = self.nums[num][0] if num in self.nums else None
        while abstract in self.links and abstract not in seen:
            seen.add(abstract)
            style = self.styles.by_id.get(self.links[abstract])
            linked = paragraph_layer(style.find(w("pPr")) if style is not None else None)
            abstract = self.nums.get(linked.get("num") or "", (None,))[0]
        return abstract

    def level(self, num: str | None, ilvl: int) -> Level | None:
        if num is None or num not in self.nums or not 0 <= ilvl < LEVELS:
            return None
        abstract = self._abstract(num)
        lvl = self.nums[num][2].get(ilvl)
        if lvl is None and abstract is not None:
            lvl = self.abstracts.get(abstract, {}).get(ilvl)
        if lvl is None or abstract is None:
            return None
        start = number(value(lvl.find(w("start"))))
        fonts = lvl.find(f"{w('rPr')}/{w('rFonts')}")
        font = (fonts.get(w("ascii")) or fonts.get(w("hAnsi"))) if fonts is not None else None
        return Level(
            abstract,
            value(lvl.find(w("numFmt"))) or "decimal",
            value(lvl.find(w("lvlText"))) or "",
            int(start) if start is not None else 1,
            font or "",
            bool(toggle(lvl.find(w("isLgl")))),
        )

    def of_style(self, style: str) -> tuple[str, int] | None:
        """The numbering a level of an abstract numbering ties to a paragraph style."""
        for abstract, levels in self.abstracts.items():
            for ilvl, lvl in levels.items():
                if value(lvl.find(w("pStyle"))) == style:
                    for num, (of, _, _) in self.nums.items():
                        if of == abstract:
                            return num, ilvl
        return None

    def count(self, num: str, ilvl: int) -> int | None:
        """The number Word gives the next paragraph numbered at that level."""
        level = self.level(num, ilvl)
        if level is None:
            return None
        counters = self.counters.setdefault(level.abstract, [None] * LEVELS)
        override = self.nums[num][1].get(ilvl)
        if override is not None and (num, ilvl) not in self.overridden:
            self.overridden.add((num, ilvl))
            counters[ilvl] = override
        else:
            counted = counters[ilvl]
            counters[ilvl] = level.start if counted is None else counted + 1
        for deeper in range(ilvl + 1, LEVELS):
            counters[deeper] = None
        return counters[ilvl]
