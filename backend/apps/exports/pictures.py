"""A document's pictures as Office files keep them, each with its size in pixels: a photo
turned upright, WebP and AVIF as PNG, an SVG as the PNG a browser draws of it, the SVG kept
beside it, and each page a PDF block shows as a PNG of it, which Office has no other way to
show."""

import io
import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from lxml import etree
from PIL import ExifTags, Image, ImageOps

from apps.blobs import store
from apps.documents import printing
from apps.imports import reading
from apps.reader import client

CONVERTED = {"image/webp", "image/avif"}
LENGTH = re.compile(r"\s*([0-9.]+)\s*(px|pt|cm|mm|in)?\s*$")
PIXELS = {None: 1, "px": 1, "pt": 96 / 72, "cm": 96 / 2.54, "mm": 96 / 25.4, "in": 96}
SAFE_XML = etree.XMLParser(resolve_entities=False, no_network=True)
# A PDF's page as a picture, in pixels per inch of the size it shows at.
PAGE_DPI = 200


@dataclass(frozen=True)
class Picture:
    data: bytes
    media_type: str
    size: tuple[float, float]
    svg: bytes | None = None


def _pixels(value: str | None) -> float | None:
    found = LENGTH.match(value or "")
    return float(found[1]) * PIXELS[found[2]] if found and float(found[1]) > 0 else None


class Unreadable(Exception):
    """An image of the document is none its format's reader can read."""


class UnreadablePdf(Unreadable):
    """A PDF the document shows cannot be read."""


def _asked(sha256: str, kind: str, failed: type[Unreadable] = Unreadable, **head):
    """The reader's answer of the picture's reading and the file it sends, if any."""
    try:
        with client.answered(kind, store.path_of(sha256), **head) as answer:
            value = answer.finish()
            return value, answer.files[0].read_bytes() if answer.files else None
    except reading.Unreadable, reading.TooLarge:
        raise failed(sha256) from None


def svg_size(path: Path) -> tuple[float, float]:
    """An SVG's size in pixels as a browser gives an image of it; in the reader."""
    svg = etree.fromstring(path.read_bytes(), SAFE_XML)
    width, height = (_pixels(svg.get(side)) for side in ("width", "height"))
    box = [float(each) for each in re.split(r"[\s,]+", (svg.get("viewBox") or "").strip()) if each]
    ratio = box[3] / box[2] if len(box) == 4 and box[2] > 0 and box[3] > 0 else None
    if width and height:
        return width, height
    if ratio and (width or height):
        return (width, width * ratio) if width else (height / ratio, height)
    if ratio:
        return box[2], box[3]
    return 300, 150


def upright(path: Path, media_type: str, out) -> tuple[str, tuple[int, int]]:
    """A raster image as Office shows it everywhere, sent where it is not so already, and its
    type and size: a photo turned upright, a format other than Office's own as PNG; in the
    reader."""
    with Image.open(path) as image:
        upright = image.getexif().get(ExifTags.Base.Orientation, 1) == 1
        if upright and media_type in store.IMAGES and media_type not in CONVERTED:
            return media_type, image.size
        turned = ImageOps.exif_transpose(image)
        found = io.BytesIO()
        if media_type == "image/jpeg":
            turned.save(found, "JPEG", quality=95)
        else:
            turned.save(found, "PNG")
            media_type = "image/png"
        out.data(found.getvalue())
        return media_type, turned.size


def picture_of(sha256: str) -> Picture:
    data = store.path_of(sha256).read_bytes()
    media_type = store.sniff(data[:1024])
    if media_type == "image/svg+xml":
        size, _ = _asked(sha256, "svg_size")
        return Picture(printing.drawn(data, *size), "image/png", size, data)
    (media_type, size), turned = _asked(sha256, "upright", media_type=media_type)
    return Picture(data if turned is None else turned, media_type, size)


def _number(value) -> int | None:
    whole = isinstance(value, int | float) and not isinstance(value, bool) and value == int(value)
    return int(value) if whole and value >= 1 else None


def pages_of(attrs: dict) -> list[tuple[int, tuple[float, float]]]:
    """The pages a PDF block shows, from its first to its last as far as the file has them,
    each with its size in points."""
    sha256 = attrs.get("blob")
    if not isinstance(sha256, str):
        return []
    sizes, _ = _asked(sha256, "pdf_sizes", UnreadablePdf)
    first = _number(attrs.get("first")) or 1
    last = min(_number(attrs.get("last")) or len(sizes), len(sizes))
    return [(number, sizes[number - 1]) for number in range(first, last + 1)]


def page_picture(sha256: str, number: int, inches: float) -> Picture:
    """The PDF's page as a PNG for showing `inches` across."""
    size, drawn = _asked(sha256, "pdf_page", UnreadablePdf, number=number, inches=inches)
    return Picture(drawn, "image/png", size)


def drawn_page(path: Path, number: int, inches: float, out) -> tuple[int, int]:
    """`page_picture`, in the reader: the PNG sent, its size given."""
    pdf = pdfium.PdfDocument(path)
    try:
        page = pdf[number - 1]
        try:
            drawn = page.render(scale=inches * PAGE_DPI / page.get_width(), may_draw_forms=True)
            image = drawn.to_pil().convert("RGB")
        finally:
            page.close()
    finally:
        pdf.close()
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    out.data(buffer.getvalue())
    return image.size
