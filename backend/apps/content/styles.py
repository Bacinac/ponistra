"""A document's own Yjs state: its theme, the font pair under `theme`, and its named
styles under `styles`, each a map keyed by the style's id. Every style draws on one of
the built-in kinds below, whose ids are the kinds themselves; a font of "headings" or
"text" is the theme's. Sizes and spacing are in points, the line height a multiple."""

from pycrdt import Doc, Map

THEME = "theme"
STYLES = "styles"


def _style(kind: str, font: str, size: float, before: float, after: float, line: float, **look):
    return {
        "kind": kind,
        "name": "",
        "font": font,
        "size": size,
        "bold": False,
        "italic": False,
        "color": None,
        "align": None,
        "before": before,
        "after": after,
        "line": line,
        "numbering": "",
        "prefix": "",
        "suffix": "",
        "nested": False,
        "kerning": True,
        **look,
    }


TEMPLATE = {
    THEME: {"headings": "Inter", "text": "Inter"},
    STYLES: {
        "text": _style("text", "text", 12, 0, 9, 1.6),
        "title": _style("title", "headings", 27, 0, 6, 1.25, bold=True),
        "subtitle": _style("subtitle", "text", 15, 0, 12, 1.25, color="gray"),
        "h1": _style("h1", "headings", 21, 18, 6, 1.25, bold=True),
        "h2": _style("h2", "headings", 16, 15, 6, 1.25, bold=True),
        "h3": _style("h3", "headings", 14, 12, 6, 1.25, bold=True),
        "h4": _style("h4", "headings", 12, 12, 6, 1.25, bold=True),
    },
}


def own(theme: dict, styles: dict) -> Doc:
    """A document's own state of a theme and styles, written by a client of its own."""
    doc = Doc()
    with doc.transaction():
        doc.get(THEME, type=Map).update(theme)
        found = doc.get(STYLES, type=Map)
        for id, style in styles.items():
            found[id] = Map(style)
    return doc


def read(own: Doc) -> tuple[dict[str, str], dict[str, dict]]:
    """The document's theme and styles, each style with its kind's built-in look where it
    lacks a field, and every built-in kind present."""
    theme = dict(TEMPLATE[THEME])
    for side, name in own.get(THEME, type=Map).items():
        if side in theme and isinstance(name, str) and name:
            theme[side] = name
    found = {}
    for id, style in own.get(STYLES, type=Map).items():
        if isinstance(style, Map) and style.get("kind") in TEMPLATE[STYLES]:
            found[id] = {**TEMPLATE[STYLES][style["kind"]], **style.to_py()}
    for kind, look in TEMPLATE[STYLES].items():
        found.setdefault(kind, dict(look))
    return theme, found


def family(theme: dict[str, str], font: str) -> str:
    """A style's font as the family it names: the theme's for "headings" and "text"."""
    return theme.get(font, font)


def template() -> bytes:
    """A new document's own state."""
    return own(TEMPLATE[THEME], TEMPLATE[STYLES]).get_update()
