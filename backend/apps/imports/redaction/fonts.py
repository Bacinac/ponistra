"""How far each glyph of a font moves the text on and how much of the line it covers, read from the
font's own dictionary, or for the 14 standard fonts that need not say, from pdf.js's tables of them
(standard.json, Apache-2.0, Mozilla Foundation)."""

import json
import math
import re
from functools import cache
from pathlib import Path

from pikepdf import Array, Dictionary, Name, Stream

DESCENT, ASCENT = -0.25, 0.9
# A glyph that moves the text on by nothing, as a combining accent does, is drawn over the one
# before it.
BEHIND = -0.35


class Unmeasurable(Exception):
    """A font whose codes or widths cannot be told, and so neither can where its text lies."""


@cache
def _standard() -> dict:
    return json.loads(Path(__file__).with_name("standard.json").read_text())


def number(value: object, default: float = 0.0) -> float:
    try:
        found = float(value)
    except TypeError, ValueError:
        return default
    return found if math.isfinite(found) else default


def _base_name(font: Dictionary) -> str:
    name = str(font.get("/BaseFont", "/"))[1:]
    name = re.sub(r"^[A-Z]{6}\+", "", name)
    return re.sub(r"\s", "", name.replace(",", "-").replace("_", "-"))


def _widths(listed: object, scale: float) -> dict[int, float]:
    """A CIDFont's /W: a first code and the widths from it, or a first, a last and one width."""
    found: dict[int, float] = {}
    items = list(listed) if isinstance(listed, Array) else []
    index = 0
    while index + 1 < len(items):
        first = int(number(items[index]))
        if isinstance(items[index + 1], Array):
            for offset, width in enumerate(items[index + 1]):
                found[first + offset] = number(width) * scale
            index += 2
        elif index + 2 < len(items):
            last, width = int(number(items[index + 1])), number(items[index + 2]) * scale
            for code in range(first, min(last, first + 65535) + 1):
                found[code] = width
            index += 3
        else:
            break
    return found


def _vertical(listed: object) -> dict[int, tuple[float, float, float]]:
    """A CIDFont's /W2: each code's vertical advance and the place of its vertical origin."""
    found: dict[int, tuple[float, float, float]] = {}
    items = list(listed) if isinstance(listed, Array) else []
    index = 0
    while index + 1 < len(items):
        first = int(number(items[index]))
        if isinstance(items[index + 1], Array):
            values = [number(each) / 1000 for each in items[index + 1]]
            for offset in range(len(values) // 3):
                found[first + offset] = tuple(values[offset * 3 : offset * 3 + 3])
            index += 2
        elif index + 4 < len(items):
            last = int(number(items[index + 1]))
            metrics = tuple(number(each) / 1000 for each in items[index + 2 : index + 5])
            for code in range(first, min(last, first + 65535) + 1):
                found[code] = metrics
            index += 5
        else:
            break
    return found


_TOKEN = re.compile(rb"<([0-9A-Fa-f\s]*)>|/([^\s/<>\[\]()]+)|(-?\d+)|([A-Za-z]+)")


class _CMap:
    """An embedded CMap: the lengths its codes come in and the CID each code stands for."""

    def __init__(self, stream: Stream):
        self.ranges: list[tuple[bytes, bytes]] = []
        self.spans: list[tuple[bytes, bytes, int]] = []
        self.single: dict[bytes, int] = {}
        self.identity = False
        self.vertical = number(stream.get("/WMode", 0)) == 1
        tokens = []
        for match in _TOKEN.finditer(stream.read_bytes()):
            hexa, name, digits, word = match.groups()
            if hexa is not None:
                cleaned = re.sub(rb"\s", b"", hexa)
                tokens.append(
                    ("hex", bytes.fromhex((cleaned + b"0" * (len(cleaned) % 2)).decode()))
                )
            elif name is not None:
                tokens.append(("name", name.decode("latin-1")))
            elif digits is not None:
                tokens.append(("int", int(digits)))
            else:
                tokens.append(("word", word.decode("latin-1")))
        section = None
        held: list = []
        for index, (kind, value) in enumerate(tokens):
            if kind == "word" and value.startswith("begin"):
                section, held = value[5:], []
            elif kind == "word" and value.startswith("end") and section:
                self._take(section, held)
                section = None
            elif kind == "word" and value == "usecmap" and index:
                used = tokens[index - 1][1]
                if used not in ("Identity-H", "Identity-V"):
                    raise Unmeasurable(f"a CMap uses {used}")
                self.identity = True
                self.ranges.append((b"\x00\x00", b"\xff\xff"))
                self.vertical = self.vertical or used == "Identity-V"
            elif kind == "name" and value == "WMode" and index + 1 < len(tokens):
                self.vertical = self.vertical or tokens[index + 1][1] == 1
            elif section:
                held.append(value)
        if not self.ranges:
            raise Unmeasurable("a CMap without code space")

    def _take(self, section: str, held: list) -> None:
        if section == "codespacerange":
            pairs = zip(held[::2], held[1::2], strict=False)
            self.ranges += [(low, high) for low, high in pairs if isinstance(low, bytes)]
        elif section == "cidrange":
            for low, high, cid in zip(held[::3], held[1::3], held[2::3], strict=False):
                if isinstance(low, bytes) and isinstance(high, bytes) and isinstance(cid, int):
                    self.spans.append((low, high, cid))
        elif section == "cidchar":
            for code, cid in zip(held[::2], held[1::2], strict=False):
                if isinstance(code, bytes) and isinstance(cid, int):
                    self.single[code] = cid

    def cid(self, code: bytes) -> int:
        if code in self.single:
            return self.single[code]
        for low, high, cid in self.spans:
            if len(low) == len(code) and low <= code <= high:
                return cid + int.from_bytes(code) - int.from_bytes(low)
        return int.from_bytes(code) if self.identity else 0


def _within(code: bytes, low: bytes, high: bytes) -> bool:
    return len(low) == len(code) and all(
        a <= b <= c for a, b, c in zip(low, code, high, strict=True)
    )


class Font:
    """A font as a content stream shows text in it, in text space units at a size of 1."""

    def __init__(self, font: Dictionary):
        self.vertical = False
        self._cmap: _CMap | None = None
        self._ranges: list[tuple[bytes, bytes]] = []
        self._positions: dict[int, tuple[float, float, float]] = {}
        self._drop = (0.88, -1.0)
        if font.get("/Subtype") == Name.Type0:
            self._composite(font)
        else:
            self._simple(font)

    def _simple(self, font: Dictionary) -> None:
        scale, rise = 0.001, 0.001
        if font.get("/Subtype") == Name.Type3:
            matrix = [number(each) for each in font.get("/FontMatrix", Array())]
            if len(matrix) != 6 or not matrix[0]:
                raise Unmeasurable("a Type 3 font without a font matrix")
            scale, rise = matrix[0], matrix[3]
        descriptor = font.get("/FontDescriptor")
        listed = font.get("/Widths")
        standard = None
        if isinstance(listed, Array):
            first = int(number(font.get("/FirstChar", 0)))
            self._known = {
                first + offset: number(width) * scale for offset, width in enumerate(listed)
            }
            missing = (
                descriptor.get("/MissingWidth") if isinstance(descriptor, Dictionary) else None
            )
            self._missing: float | None = number(missing) * scale
        else:
            tables = _standard()
            standard = tables["names"].get(_base_name(font))
            if standard is None:
                raise Unmeasurable(f"{font.get('/BaseFont')} gives no widths")
            widths = tables["widths"][standard]
            self._known = {
                code: (widths if isinstance(widths, int) else widths[glyph]) * scale
                for code, glyph in enumerate(self._encoding(font, standard))
                if glyph and (isinstance(widths, int) or glyph in widths)
            }
            self._missing = None
        self.descent, self.ascent = self._heights(font, descriptor, standard, rise)

    @staticmethod
    def _encoding(font: Dictionary, standard: str) -> list[str]:
        encodings = _standard()["encodings"]
        builtin = {"Symbol": "SymbolSetEncoding", "ZapfDingbats": "ZapfDingbatsEncoding"}
        base = builtin.get(standard, "StandardEncoding")
        given = font.get("/Encoding")
        differences = None
        if isinstance(given, Name):
            base = str(given)[1:]
        elif isinstance(given, Dictionary):
            base = str(given.get("/BaseEncoding", Name("/" + base)))[1:]
            differences = given.get("/Differences")
        names = list(encodings.get(base) or encodings[builtin.get(standard, "StandardEncoding")])
        code = 0
        for item in differences if isinstance(differences, Array) else []:
            if isinstance(item, Name):
                if 0 <= code < 256:
                    names[code] = str(item)[1:]
                code += 1
            else:
                code = int(number(item))
        return names

    def _composite(self, font: Dictionary) -> None:
        encoding = font.get("/Encoding")
        if isinstance(encoding, Stream):
            self._cmap = _CMap(encoding)
            self._ranges = self._cmap.ranges
            self.vertical = self._cmap.vertical
        elif encoding in (Name("/Identity-H"), Name("/Identity-V")):
            self._ranges = [(b"\x00\x00", b"\xff\xff")]
            self.vertical = encoding == Name("/Identity-V")
        else:
            raise Unmeasurable(f"a font encoded by {encoding}")
        descendants = font.get("/DescendantFonts")
        if not isinstance(descendants, Array) or not len(descendants):
            raise Unmeasurable("a composite font without its CIDFont")
        cid_font = descendants[0]
        self._known = _widths(cid_font.get("/W"), 0.001)
        self._missing = number(cid_font.get("/DW", 1000)) * 0.001
        if self.vertical:
            given = [number(each) / 1000 for each in cid_font.get("/DW2", Array())]
            if len(given) == 2:
                self._drop = (given[0], given[1])
            self._positions = _vertical(cid_font.get("/W2"))
        descriptor = cid_font.get("/FontDescriptor")
        self.descent, self.ascent = self._heights(cid_font, descriptor, None, 0.001)

    @staticmethod
    def _heights(font, descriptor, standard: str | None, rise: float) -> tuple[float, float]:
        if font.get("/Subtype") == Name.Type3:
            box = [number(each) for each in font.get("/FontBBox", Array())]
            if len(box) == 4 and box[1] != box[3]:
                low, high = sorted((box[1] * rise, box[3] * rise))
                return low, high
            return DESCENT, ASCENT
        descent = ascent = None
        if isinstance(descriptor, Dictionary):
            descent = number(descriptor.get("/Descent"), math.nan) / 1000
            ascent = number(descriptor.get("/Ascent"), math.nan) / 1000
        elif standard in _standard()["heights"]:
            heights = _standard()["heights"][standard]
            descent, ascent = heights["descent"] / 1000, heights["ascent"] / 1000
        # Some fonts say nothing sensible of their height; the line is then what most fonts fill.
        return (
            descent if descent is not None and -0.7 <= descent <= 0 else DESCENT,
            ascent if ascent is not None and 0.3 <= ascent <= 1.5 else ASCENT,
        )

    def codes(self, data: bytes) -> list[bytes]:
        if not self._ranges:
            return [data[index : index + 1] for index in range(len(data))]
        found, index = [], 0
        shortest = min(len(low) for low, _ in self._ranges)
        while index < len(data):
            size = next(
                (
                    size
                    for size in (1, 2, 3, 4)
                    if any(_within(data[index : index + size], *each) for each in self._ranges)
                ),
                shortest,
            )
            found.append(data[index : index + size])
            index += size
        return found

    def _cid(self, code: bytes) -> int:
        if self._cmap is not None:
            return self._cmap.cid(code)
        return int.from_bytes(code)

    def advance(self, code: bytes) -> float:
        """The glyph's horizontal advance, w0."""
        key = self._cid(code) if self._ranges else code[0]
        width = self._known.get(key, self._missing)
        if width is None:
            raise Unmeasurable(f"code {code.hex()} has no width")
        return width

    def drop(self, code: bytes) -> float:
        """The glyph's vertical advance, w1, in vertical writing."""
        return self._positions.get(self._cid(code), (self._drop[1],))[0]

    def spaces(self, code: bytes) -> bool:
        """Whether word spacing applies to the glyph: the single-byte code 32."""
        return code == b" "

    def box(self, code: bytes) -> tuple[float, float, float, float]:
        """The part of the line the glyph covers, from where it is drawn."""
        width = self.advance(code)
        left, right = (min(0.0, width), max(0.0, width)) if abs(width) > 0.05 else (BEHIND, 0.0)
        if not self.vertical:
            return left, self.descent, right, self.ascent
        cid = self._cid(code)
        across, down = (
            self._positions[cid][1:] if cid in self._positions else (width / 2, self._drop[0])
        )
        return left - across, self.descent - down, right - across, self.ascent - down
