"""Our font families, from the registry the browser reads too (fonts/fonts.json)."""

import json
from functools import cache

from django.conf import settings


@cache
def families() -> list[dict]:
    return json.loads(settings.FONTS.read_text())["families"]


def _named(names: list[str] | None, wanted: str) -> bool:
    return any(found.lower() == wanted for found in names or [])


def substitute(name: str) -> str | None:
    """The family we show for a name a document carries: ours, the metric equal of an Office
    font, or its look-alike; None where we have no stand-in."""
    wanted = name.strip().lower()
    for test in (
        lambda family: family["name"].lower() == wanted,
        lambda family: _named(family.get("replaces"), wanted),
        lambda family: _named(family.get("resembles"), wanted),
    ):
        for family in families():
            if test(family):
                return family["name"]
    return None


def kept(name: str) -> bool:
    """Whether we show a name in itself or in its metric equal, its lines breaking as in Office."""
    wanted = name.strip().lower()
    return any(
        family["name"].lower() == wanted or _named(family.get("replaces"), wanted)
        for family in families()
    )


def substituted(names: set[str]) -> list[dict]:
    """The fonts of an imported file we show in a face of other widths, or in none of ours."""
    return [
        {"from": name, "to": substitute(name)}
        for name in sorted(names, key=str.lower)
        if not kept(name)
    ]


def office(name: str) -> str:
    """The name an Office file carries for a family: the Office font ours is the metric equal
    or the look-alike of, which every Office installation has."""
    for family in families():
        found = family.get("replaces") or family.get("resembles")
        if family["name"] == name and found:
            return found[0]
    return name


def ours(name: str) -> bool:
    return any(family["name"] == name for family in families())
