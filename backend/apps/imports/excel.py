"""What an Excel workbook says beside its cells' values: its theme's colours and the tint Excel
gives them, in Windows' HLS to its rounding, its cells' fills and edges, and its tables' styles
as designs (D30), the built-in ones from ECMA-376's presetTableStyles.xml."""

from functools import cache
from pathlib import Path

from lxml import etree

from apps.content import designs, palette

PRESETS = Path(__file__).with_name("presetTableStyles.xml")
# SpreadsheetML's theme index names the scheme's colours with its first two pairs swapped.
SCHEME = ["lt1", "dk1", "lt2", "dk2", *(f"accent{n}" for n in range(1, 7)), "hlink", "folHlink"]
# The legacy palette an indexed colour names (ECMA-376 §18.8.27); 64 and 65 are the system's.
INDEXED = (
    "000000 FFFFFF FF0000 00FF00 0000FF FFFF00 FF00FF 00FFFF "
    "000000 FFFFFF FF0000 00FF00 0000FF FFFF00 FF00FF 00FFFF "
    "800000 008000 000080 808000 800080 008080 C0C0C0 808080 "
    "9999FF 993366 FFFFCC CCFFFF 660066 FF8080 0066CC CCCCFF "
    "000080 FF00FF FFFF00 00FFFF 800080 800000 008080 0000FF "
    "00CCFF CCFFFF CCFFCC FFFF99 99CCFF FF99CC CC99FF FFCC99 "
    "3366FF 33CCCC 99CC00 FFCC00 FF9900 FF6600 666699 969696 "
    "003366 339966 003300 333300 993300 993366 333399 333333"
).split()
PARTS = {
    "wholeTable": "table",
    "firstRowStripe": "rowBand1",
    "secondRowStripe": "rowBand2",
    "firstColumnStripe": "columnBand1",
    "secondColumnStripe": "columnBand2",
    "firstColumn": "firstColumn",
    "lastColumn": "lastColumn",
    "headerRow": "header",
    "totalRow": "totals",
    "firstHeaderCell": "topLeft",
    "lastHeaderCell": "topRight",
    "firstTotalCell": "bottomLeft",
    "lastTotalCell": "bottomRight",
}
STRIPES = {
    "firstRowStripe": ("rows", 0),
    "secondRowStripe": ("rows", 1),
    "firstColumnStripe": ("columns", 0),
    "secondColumnStripe": ("columns", 1),
}
SIDES = {
    "top": "top",
    "bottom": "bottom",
    "left": "left",
    "start": "left",
    "right": "right",
    "end": "right",
    "horizontal": "insideH",
    "vertical": "insideV",
}
KINDS = {kind["name"]: kind for kind in designs.TABLES["rules"]["excel"]["kinds"]}
OFF = {"0", "false"}
HLSMAX, RGBMAX = 240, 255
UNDEFINED_HUE = HLSMAX * 2 // 3


def _local(element) -> str:
    return etree.QName(element).localname


def scheme(theme) -> list[str]:
    """The theme's colours as RRGGBB, by SpreadsheetML's theme index; black where the theme
    has none."""
    found: dict[str, str] = {}
    colors = theme.find(".//{*}clrScheme") if theme is not None else None
    for slot in colors if colors is not None else ():
        if len(slot):
            given = slot[0].get("lastClr") or slot[0].get("val") or ""
            found[_local(slot)] = given.upper() if len(given) == 6 else "000000"
    return [found.get(name, "000000") for name in SCHEME]


def _to_hls(red: int, green: int, blue: int) -> tuple[int, int, int]:
    high, low = max(red, green, blue), min(red, green, blue)
    lightness = ((high + low) * HLSMAX + RGBMAX) // (2 * RGBMAX)
    if high == low:
        return UNDEFINED_HUE, lightness, 0
    spread = high - low
    if lightness <= HLSMAX // 2:
        saturation = (spread * HLSMAX + (high + low) // 2) // (high + low)
    else:
        rest = 2 * RGBMAX - high - low
        saturation = (spread * HLSMAX + rest // 2) // rest
    r, g, b = (((high - x) * (HLSMAX // 6) + spread // 2) // spread for x in (red, green, blue))
    if red == high:
        hue = b - g
    elif green == high:
        hue = HLSMAX // 3 + r - b
    else:
        hue = 2 * HLSMAX // 3 + g - r
    return hue % HLSMAX if hue < 0 or hue > HLSMAX else hue, lightness, saturation


def _channel(low: int, high: int, hue: int) -> int:
    hue = hue + HLSMAX if hue < 0 else hue - HLSMAX if hue > HLSMAX else hue
    if hue < HLSMAX // 6:
        return low + ((high - low) * hue + HLSMAX // 12) // (HLSMAX // 6)
    if hue < HLSMAX // 2:
        return high
    if hue < HLSMAX * 2 // 3:
        return low + ((high - low) * (HLSMAX * 2 // 3 - hue) + HLSMAX // 12) // (HLSMAX // 6)
    return low


def _to_rgb(hue: int, lightness: int, saturation: int) -> tuple[int, ...]:
    if saturation == 0:
        grey = (lightness * RGBMAX + HLSMAX // 2) // HLSMAX
        return grey, grey, grey
    if lightness <= HLSMAX // 2:
        high = (lightness * (HLSMAX + saturation) + HLSMAX // 2) // HLSMAX
    else:
        high = lightness + saturation - (lightness * saturation + HLSMAX // 2) // HLSMAX
    low = 2 * lightness - high
    return tuple(
        (_channel(low, high, hue + shift) * RGBMAX + HLSMAX // 2) // HLSMAX
        for shift in (HLSMAX // 3, 0, -HLSMAX // 3)
    )


def tinted(rgb: str, tint: float) -> str:
    """RRGGBB with a tint, lighter above 0 and darker below, as Excel draws it."""
    tint = round(tint, 4)
    if not tint:
        return rgb.upper()
    hue, lightness, saturation = _to_hls(*(int(rgb[at : at + 2], 16) for at in (0, 2, 4)))
    lighter = lightness * (1 + tint) if tint < 0 else lightness * (1 - tint) + HLSMAX * tint
    lightness = max(0, min(HLSMAX, int(lighter + 1e-9)))
    return "".join(f"{each:02X}" for each in _to_rgb(hue, lightness, saturation))


def color(element, theme: list[str]) -> str | None:
    """A colour element as RRGGBB; None for the system's own colour."""
    if element is None:
        return None
    if (index := element.get("theme")) is not None and int(index) < len(theme):
        base = theme[int(index)]
    elif len(given := element.get("rgb") or "") >= 6:
        base = given[-6:]
    elif (index := element.get("indexed")) is not None and int(index) < len(INDEXED):
        base = INDEXED[int(index)]
    else:
        return None
    return tinted(base, float(element.get("tint") or 0))


def fill(element, theme: list[str], differential: bool = False) -> tuple[str | None, int]:
    """What a fill element fills with as a design holds it, "none" for no fill, and whether
    its pattern or gradient was lost; None where it says nothing. A cell's format fills solid
    with its pattern's colour, a differential one with its background."""
    if element is None:
        return None, 0
    pattern = element.find("{*}patternFill")
    if pattern is not None:
        kind = pattern.get("patternType") or ("solid" if differential else "none")
        if kind == "none":
            return "none", 0
        order = ("bgColor", "fgColor") if differential else ("fgColor", "bgColor")
        shade = next(
            (found for tag in order if (found := color(pattern.find(f"{{*}}{tag}"), theme))), None
        )
        shown = palette.named("highlight", f"#{shade.lower()}") if shade else "none"
        return shown, int(kind != "solid")
    stop = element.find("{*}gradientFill/{*}stop/{*}color")
    if stop is not None:
        shade = color(stop, theme)
        return (palette.named("highlight", f"#{shade.lower()}") if shade else None), 1
    return None, 0


def _edge(border, theme: list[str]) -> dict | str:
    kind = KINDS.get(border.get("style") or "none")
    if kind is None:
        return "none"
    found: dict = {"line": kind["line"], "width": kind["width"]}
    if shade := color(border.find("{*}color"), theme):
        found["color"] = palette.named("text", f"#{shade.lower()}")
    return found


def edges_of(border, theme: list[str]) -> dict:
    """The edges a border element sets, a side without a style taking a line away."""
    found: dict = {}
    for each in border if border is not None else ():
        if side := SIDES.get(_local(each)):
            found[side] = _edge(each, theme)
    return found


def part(dxf, theme: list[str]) -> tuple[dict, int]:
    """What a differential format sets of a part of a design, and how much of it the part
    could not hold."""
    found: dict = {}
    lost = 0
    marks: dict = {}
    font = dxf.find("{*}font")
    for each in font if font is not None else ():
        tag, on = _local(each), each.get("val") not in OFF
        if tag in ("b", "i", "strike"):
            marks[{"b": "strong", "i": "em", "strike": "strike"}[tag]] = {} if on else False
        elif tag == "u":
            marks["underline"] = {} if (each.get("val") or "single") != "none" else False
        elif tag == "color":
            shade = color(each, theme)
            marks["color"] = (
                {"color": palette.named("text", f"#{shade.lower()}")} if shade else False
            )
        elif tag == "name" and each.get("val"):
            marks["font"] = {"family": each.get("val")}
        elif tag == "sz" and 1 <= float(each.get("val") or 0) <= 400:
            marks["size"] = {"pt": float(each.get("val"))}
    if marks:
        found["marks"] = marks
    pattern = dxf.find("{*}fill/{*}patternFill")
    if pattern is not None:
        kind = pattern.get("patternType") or "solid"
        # A differential format fills solid with its background colour.
        shade = color(pattern.find("{*}bgColor"), theme) or color(pattern.find("{*}fgColor"), theme)
        found["fill"] = (
            palette.named("highlight", f"#{shade.lower()}") if kind != "none" and shade else "none"
        )
        lost += kind not in ("solid", "none")
    lost += dxf.find("{*}fill/{*}gradientFill") is not None
    if edges := edges_of(dxf.find("{*}border"), theme):
        found["edges"] = edges
    return found, lost


def design(style, dxfs: list, theme: list[str], first: int = 0) -> tuple[dict | None, int]:
    """A table style as a design, by its differential formats counted from first, and how
    much of it the design could not hold; None for a style that draws nothing."""
    parts: dict[str, dict] = {}
    bands = {"rows": [1, 1], "columns": [1, 1]}
    lost = 0
    for element in style.iterfind("{*}tableStyleElement"):
        kind = element.get("type") or ""
        if kind in STRIPES:
            axis, at = STRIPES[kind]
            bands[axis][at] = max(1, min(int(element.get("size") or 1), 9))
        at = int(element.get("dxfId") or -1) - first
        if kind not in PARTS or not 0 <= at < len(dxfs):
            continue
        found, count = part(dxfs[at], theme)
        lost += count
        if found:
            parts[PARTS[kind]] = found
    if not parts:
        return None, lost
    made: dict = {"rules": "excel", "name": style.get("name") or "", "parts": parts}
    if not made["name"]:
        del made["name"]
    if any(sizes != [1, 1] for sizes in bands.values()):
        made["bands"] = bands
    return made, lost


@cache
def _presets() -> dict[str, tuple[bytes, ...]]:
    found = {}
    for preset in etree.parse(PRESETS).getroot():
        style = preset.find("tableStyles/tableStyle")
        style.set("name", preset.tag)
        found[preset.tag] = (
            etree.tostring(style),
            *(etree.tostring(each) for each in preset.find("dxfs")),
        )
    return found


def preset(name: str, theme: list[str]) -> tuple[dict | None, int]:
    """One of Excel's built-in table styles as a design; None for a name it has not."""
    found = _presets().get(name)
    if found is None:
        return None, 0
    style, *dxfs = (etree.fromstring(each) for each in found)
    # The presets count their formats from 1.
    return design(style, dxfs, theme, first=1)


class Styles:
    """What a workbook's styles.xml gives its cells: each cell format's fill and edges, and its
    tables' styles as designs."""

    def __init__(self, root, theme: list[str]):
        self.theme = theme
        fills = [fill(each, theme) for each in root.iterfind("{*}fills/{*}fill")]
        borders = [_cell_edges(each, theme) for each in root.iterfind("{*}borders/{*}border")]
        self.cells: list[tuple[str | None, dict | None, int]] = []
        for xf in root.iterfind("{*}cellXfs/{*}xf"):
            shown, patterned = _at(fills, xf.get("fillId"), (None, 0))
            edges, diagonal = _at(borders, xf.get("borderId"), (None, 0))
            self.cells.append((None if shown == "none" else shown, edges, patterned + diagonal))
        self.dxfs = list(root.iterfind("{*}dxfs/{*}dxf"))
        self.tables = {
            style.get("name"): style for style in root.iterfind("{*}tableStyles/{*}tableStyle")
        }

    def look(self, xf: int | None) -> tuple[str | None, dict | None, int]:
        """The fill and the edges a cell format gives, and how much of them was lost."""
        return _at(self.cells, xf, (None, None, 0))

    def design(self, name: str) -> tuple[dict | None, int]:
        """A table style by its name as a design, the workbook's own before Excel's; None for
        one neither has."""
        if name in self.tables:
            return design(self.tables[name], self.dxfs, self.theme)
        return preset(name, self.theme)


def _at(listed: list, index, default):
    at = int(index) if isinstance(index, int) or (index or "").isdigit() else 0
    return listed[at] if at < len(listed) else default


def _cell_edges(border, theme: list[str]) -> tuple[dict | None, int]:
    found = {
        side: edge
        for side, edge in edges_of(border, theme).items()
        if side in ("top", "bottom", "left", "right") and edge != "none"
    }
    diagonal = border.find("{*}diagonal")
    crossed = diagonal is not None and KINDS.get(diagonal.get("style") or "none") is not None
    drawn = crossed and (
        border.get("diagonalUp") in ("1", "true") or border.get("diagonalDown") in ("1", "true")
    )
    return found or None, int(drawn)
