"""The colours of a document's text and highlights by the names its marks carry, or as an
imported file's own #rrggbb, and of its charts' series and of the user's calendars, from the
palette the editor reads too (colors/colors.json); a file and a phone take each one's paper
shade."""

import json
import re
from functools import cache

from django.conf import settings


@cache
def _palette() -> dict:
    return json.loads(settings.COLORS.read_text())


def _shade(kind: str, name: object) -> str | None:
    if not isinstance(name, str):
        return None
    if re.fullmatch(r"#[0-9a-f]{6}", name):
        return name[1:].upper()
    swatch = _palette()[kind].get(name)
    return swatch["light"][1:].upper() if swatch else None


def named(kind: str, value: str) -> str:
    """A #rrggbb by the name of the palette's colour it is the paper shade of, so it keeps the
    dark shade drawn for it; else the value itself."""
    for name, swatch in _palette()[kind].items():
        if swatch["light"].lower() == value:
            return name
    return value


def text(name: object) -> str | None:
    """A text colour as RRGGBB; None for a name the palette does not hold."""
    return _shade("text", name)


def highlight(name: object) -> str | None:
    return _shade("highlight", name)


def chart() -> list[str]:
    """The colours of a chart's series in turn, as RRGGBB."""
    return [swatch["light"][1:].upper() for swatch in _palette()["chart"]]


def calendars() -> list[str]:
    """The colours a calendar may take in turn, as #rrggbb."""
    return [swatch["light"] for swatch in _palette()["calendar"]]
