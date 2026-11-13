"""Word's colours as our marks carry them: the file's own as #rrggbb, whose dark shade the editor
derives (frontend/src/editor/colors.ts), or a palette's name where it is that colour."""

import colorsys

from apps.content import palette

HIGHLIGHTED = {
    "yellow": "ffff00",
    "green": "00ff00",
    "cyan": "00ffff",
    "blue": "0000ff",
    "magenta": "ff00ff",
    "red": "ff0000",
    "darkBlue": "000080",
    "darkCyan": "008080",
    "darkGreen": "008000",
    "darkMagenta": "800080",
    "darkRed": "800000",
    "darkYellow": "808000",
    "darkGray": "808080",
    "lightGray": "c0c0c0",
    "black": "000000",
}


def _hls(value: str | None) -> tuple[float, float, float] | None:
    if not value or len(value) != 6:
        return None
    try:
        red, green, blue = (int(value[at : at + 2], 16) / 255 for at in (0, 2, 4))
    except ValueError:
        return None
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    return hue * 360, lightness, saturation


def text_color(value: str | None) -> str | None:
    """A w:color value as #rrggbb; None for auto and for black and the dark greys shown in the
    text's own colour, as dark as they were."""
    found = _hls(value)
    if found is None:
        return None
    _, lightness, saturation = found
    if lightness < 0.15 or (saturation < 0.2 and lightness < 0.35):
        return None
    return palette.named("text", f"#{value.lower()}")


def highlight(name: str | None, fill: str | None = None) -> str | None:
    """A w:highlight name or, failing that, a shading fill as #rrggbb; None for none and white."""
    if name:
        return palette.named("highlight", f"#{HIGHLIGHTED[name]}") if name in HIGHLIGHTED else None
    if _hls(fill) is None or fill.lower() == "ffffff":
        return None
    return palette.named("highlight", f"#{fill.lower()}")
