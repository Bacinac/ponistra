"""PowerPoint's vocabulary, which reading and writing its files share."""

import json
from functools import cache
from pathlib import Path

from lxml import etree

from .word import A, ns

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
TABLE = "http://schemas.openxmlformats.org/drawingml/2006/table"
SECTIONS = "{521415D9-36F7-43E2-AB2F-B90AF26B5E84}"
NO_STYLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
# What PowerPoint draws for a table style it does not know.
TABLE_GRID = "{5940675A-B579-460E-94D1-54222C63F5DA}"
BUILT_IN = Path(__file__).with_name("tableStyles.json")
DESIGN_PARTS = {
    "wholeTbl": "table",
    "band1H": "rowBand1",
    "band2H": "rowBand2",
    "band1V": "columnBand1",
    "band2V": "columnBand2",
    "lastCol": "lastColumn",
    "firstCol": "firstColumn",
    "lastRow": "totals",
    "seCell": "bottomRight",
    "swCell": "bottomLeft",
    "firstRow": "header",
    "neCell": "topRight",
    "nwCell": "topLeft",
}
SWITCHES = {
    "firstRow": "header",
    "lastRow": "totals",
    "firstCol": "firstColumn",
    "lastCol": "lastColumn",
    "bandRow": "rowBands",
    "bandCol": "columnBands",
}
STROKES = {
    "sng": "single",
    "dbl": "double",
    "tri": "triple",
    "thickThin": "thickThinSmallGap",
    "thinThick": "thinThickSmallGap",
}
DASHES = {
    "dot": "dotted",
    "sysDot": "dotted",
    "dash": "dashed",
    "sysDash": "dashed",
    "lgDash": "dashed",
    "dashDot": "dotDash",
    "sysDashDot": "dotDash",
    "lgDashDot": "dotDash",
    "lgDashDotDot": "dotDotDash",
    "sysDashDotDot": "dotDotDash",
}
EMU_PER_POINT = 12700
LAYOUT_TYPES = {
    "title": "title",
    "content": "obj",
    "two": "twoObj",
    "section": "secHead",
    "titleOnly": "titleOnly",
    "blank": "blank",
}
FIELDS = {"dt": "date", "sldNum": "number"}
ALIGNS = {"left": "l", "center": "ctr", "right": "r", "justify": "just"}
ANCHORS = {"top": "t", "middle": "ctr", "bottom": "b"}
SCHEMES = {
    ("1", "", "."): "arabicPeriod",
    ("1", "", ")"): "arabicParenR",
    ("1", "(", ")"): "arabicParenBoth",
    ("1", "", ""): "arabicPlain",
    **{
        (numbers, prefix, suffix): f"{name}{form}"
        for numbers, name in (
            ("a", "alphaLc"),
            ("A", "alphaUc"),
            ("i", "romanLc"),
            ("I", "romanUc"),
        )
        for (prefix, suffix), form in (
            (("", "."), "Period"),
            (("", ")"), "ParenR"),
            (("(", ")"), "ParenBoth"),
        )
    },
}
CLR_MAP = {
    "bg1": "lt1",
    "tx1": "dk1",
    "bg2": "lt2",
    "tx2": "dk2",
    **{f"accent{at}": f"accent{at}" for at in range(1, 7)},
    "hlink": "hlink",
    "folHlink": "folHlink",
}


@cache
def _built_in() -> dict[str, tuple[str, dict, dict[str, str]]]:
    """Each of PowerPoint's built-in table styles by its id: its name, its family's description
    and the colours the description's @ and @2 stand for in it."""
    styles = {}
    for family in json.loads(BUILT_IN.read_text()):
        name = family["name"]
        if "plain" in family:
            colour = family.get("colour")
            styles[family["plain"]] = (name, family, {"@": colour, "@2": colour})
        for at, id in enumerate(family.get("accents", ())):
            if family.get("paired"):
                one, two = 2 * at + 1, 2 * at + 2
                styles[id] = (
                    f"{name} - Accent {one}/Accent {two}",
                    family,
                    {"@": f"accent{one}", "@2": f"accent{two}"},
                )
            else:
                styles[id] = (f"{name} - Accent {at + 1}", family, {"@": f"accent{at + 1}"})
    return styles


def built_in_id(name: str) -> str | None:
    """The id of PowerPoint's built-in table style of a name; None for a name none has."""
    return next((id for id, (named, *_) in _built_in().items() if named == name), None)


def built_in(id: str):
    """One of PowerPoint's built-in table styles as a:tblStyle, composed from its family's
    description; None for an id it has not."""
    found = _built_in().get(id)
    if found is None:
        return None
    name, family, colours = found

    def add(parent, tag: str, **attrs):
        return etree.SubElement(parent, ns(A, tag), {key: str(each) for key, each in attrs.items()})

    def painted(parent, color: str | dict) -> None:
        given = {"color": color} if isinstance(color, str) else color
        scheme = add(parent, "schemeClr", val=colours.get(given["color"], given["color"]))
        for mod in ("tint", "shade", "alpha"):
            if mod in given:
                add(scheme, mod, val=given[mod] * 1000)

    def referred(parent, tag: str, given: dict) -> None:
        painted(add(parent, tag, idx=given["theme"]), given["color"])

    style = etree.Element(ns(A, "tblStyle"), styleId=id, styleName=name)
    if background := family.get("background"):
        under = add(style, "tblBg")
        for key, tag in (("fill", "fillRef"), ("effect", "effectRef")):
            if key in background:
                referred(under, tag, background[key])
    parts = family.get("parts", {})
    for tag, part in DESIGN_PARTS.items():
        if (look := parts.get(part)) is None:
            continue
        element = add(style, tag)
        if look.get("bold") or "text" in look:
            text = add(element, "tcTxStyle", **({"b": "on"} if look.get("bold") else {}))
            if "text" in look:
                painted(text, look["text"])
        cell = add(element, "tcStyle")
        borders = add(cell, "tcBdr")
        for side, edge in look.get("edges", {}).items():
            holder = add(borders, side)
            if edge == "none":
                add(add(holder, "ln"), "noFill")
            elif "theme" in edge:
                referred(holder, "lnRef", edge)
            else:
                line = add(
                    holder,
                    "ln",
                    w=round(edge["width"] * EMU_PER_POINT),
                    cmpd="dbl" if edge.get("double") else "sng",
                )
                painted(add(line, "solidFill"), edge["color"])
        fill = look.get("fill")
        if fill == "none":
            add(add(cell, "fill"), "noFill")
        elif isinstance(fill, dict) and "theme" in fill:
            referred(cell, "fillRef", fill)
        elif fill is not None:
            painted(add(add(cell, "fill"), "solidFill"), fill)
    return style
