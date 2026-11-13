"""An image file's edits, which its room keeps beside it, and the copy drawn with them: parts
blurred, cropped as the image shows upright, turned, mirrored, made smaller, its tone changed and
marked with arrows, rectangles, lines and text, as the browser shows it. The file stays as it
came."""

import io
import math
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger
from pathlib import Path

from anyio import sleep
from django.conf import settings
from django.db import transaction
from django.db.models import F, Max, OuterRef, Q, Subquery
from django.utils import timezone
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps
from pycrdt import Doc, Map

from apps.collab.kept import finite, moment, whole
from apps.collab.models import Update
from apps.content import palette
from apps.core.asyncdb import database
from apps.documents.models import Node
from apps.imports import reading
from apps.reader import client
from apps.versions.history import state_of

from . import previews, store
from .models import Blob

log = getLogger(__name__)

EVERY = 2
EDITS = "edits"
MARKS = "marks"
FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP", "image/avif": "AVIF"}
KEYS = {"crop", "turn", "flip", "side", "brightness", "contrast", "saturation"}
# Turned clockwise, as the browser shows it; Pillow turns the other way.
TURNS = {
    0: None,
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}
SMALLEST_SIDE = 16
TONE = (0, 2)
SHAPES = {
    "arrow": {"kind", "color", "width", "points", "by", "at"},
    "rectangle": {"kind", "color", "width", "points", "by", "at"},
    "stroke": {"kind", "color", "width", "points", "by", "at"},
    "text": {"kind", "color", "size", "points", "text", "by", "at"},
    "blur": {"kind", "points", "by", "at"},
}
POINTS = {"arrow": 4, "rectangle": 4, "text": 2, "blur": 4}
LARGEST = 4000
LONGEST_TEXT = 500
# A mark is drawn larger and made smaller, as the browser smooths its edges, up to this many
# pixels a mark.
SMOOTHED = 16_000_000
# An arrow's head, long and wide by so many of its line's widths.
HEAD = 4
SPREAD = 2.5
FONT = settings.FONTS.parent / "Inter" / "Inter-Bold.ttf"


class Unreadable(Exception):
    """What the room keeps is not an edit the copy can be drawn with."""


FAILURES = (Unreadable, reading.Unreadable, reading.TooLarge)


@dataclass(frozen=True)
class Mark:
    """An arrow, a rectangle, a line drawn by hand, a text or a blurred part, in the pixels of the
    image upright: a text's point is where its line starts, and it reads across the image as it
    shows."""

    id: str
    kind: str
    points: tuple[float, ...]
    at: datetime
    color: str = ""
    width: float = 0
    size: float = 0
    text: str = ""


@dataclass(frozen=True)
class Edits:
    crop: tuple[int, int, int, int] | None = None
    turn: int = 0
    flip: bool = False
    side: int | None = None
    brightness: float = 1
    contrast: float = 1
    saturation: float = 1
    marks: tuple[Mark, ...] = field(default=())


def _tone(kept: dict, key: str) -> float:
    value = kept.get(key, 1)
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or not TONE[0] <= value <= TONE[1]
    ):
        raise Unreadable(f"{key}: {value!r}")
    return float(value)


def _crop(value: object) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.keys() != {"x", "y", "w", "h"}:
        raise Unreadable(f"crop: {value!r}")
    x, y, w, h = (whole(value[key]) for key in ("x", "y", "w", "h"))
    if None in (x, y, w, h) or x < 0 or y < 0 or w < 1 or h < 1:
        raise Unreadable(f"crop: {value!r}")
    return x, y, w, h


def _measure(value: object) -> float:
    if not finite([value], 1) or not 0 < value <= LARGEST:
        raise Unreadable(f"measure: {value!r}")
    return float(value)


def _mark(key: str, mark: object) -> Mark:
    kind = mark.get("kind") if isinstance(mark, dict) else None
    if kind not in SHAPES or mark.keys() != SHAPES[kind]:
        raise Unreadable(f"mark {key}: {mark!r}")
    points, when = mark["points"], moment(mark["at"])
    if (
        not finite(points, POINTS.get(kind))
        or when is None
        or (whole(mark["by"]) is None and mark["by"] is not None)
    ):
        raise Unreadable(f"mark {key}: {mark!r}")
    if kind == "blur":
        return Mark(key, kind, tuple(points), when)
    color = palette.text(mark["color"])
    if color is None:
        raise Unreadable(f"mark {key}: {mark!r}")
    if kind != "text":
        return Mark(key, kind, tuple(points), when, f"#{color}", _measure(mark["width"]))
    text = mark["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > LONGEST_TEXT or "\n" in text:
        raise Unreadable(f"mark {key}: {mark!r}")
    return Mark(key, kind, tuple(points), when, f"#{color}", size=_measure(mark["size"]), text=text)


def read(kept: dict, marks: dict | None = None) -> Edits:
    if unknown := kept.keys() - KEYS:
        raise Unreadable(f"unknown: {sorted(unknown)}")
    turn, flip, side = whole(kept.get("turn", 0)), kept.get("flip", False), kept.get("side")
    if turn not in TURNS or not isinstance(flip, bool):
        raise Unreadable(f"turn {kept.get('turn')!r}, flip {flip!r}")
    if side is not None and ((side := whole(side)) is None or side < SMALLEST_SIDE):
        raise Unreadable(f"side: {kept['side']!r}")
    return Edits(
        _crop(kept.get("crop")),
        turn,
        flip,
        side,
        _tone(kept, "brightness"),
        _tone(kept, "contrast"),
        _tone(kept, "saturation"),
        tuple(
            sorted(
                (_mark(key, mark) for key, mark in (marks or {}).items()),
                key=lambda mark: (mark.at, mark.id),
            )
        ),
    )


def edits_of(file: Node) -> Edits:
    doc = Doc()
    doc.apply_update(state_of(file.room))
    return read(
        dict(doc.get(EDITS, type=Map).to_py() or {}), dict(doc.get(MARKS, type=Map).to_py() or {})
    )


def _clamped(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _toned(image: Image.Image, edits: Edits) -> Image.Image:
    """The browser's brightness, contrast and saturate filters in that order, each clamped."""
    brightness, contrast, saturation = edits.brightness, edits.contrast, edits.saturation
    if (brightness, contrast, saturation) == (1, 1, 1):
        return image
    alpha = image.getchannel("A") if image.mode == "RGBA" else None
    table = [
        round(_clamped((_clamped(value / 255 * brightness) - 0.5) * contrast + 0.5) * 255)
        for value in range(256)
    ]
    toned = image.convert("RGB").point(table * 3)
    if saturation != 1:
        s = saturation
        toned = toned.convert(
            "RGB",
            (
                0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s, 0,
                0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s, 0,
                0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s, 0,
            ),
        )  # fmt: skip
    if alpha is not None:
        toned.putalpha(alpha)
    return toned


def blur_of(points: tuple[float, ...]) -> float:
    """The blur of a part, enough that what it covers cannot be read."""
    x1, y1, x2, y2 = points
    return min(64.0, max(4.0, min(abs(x2 - x1), abs(y2 - y1)) / 4))


def halo_of(size: int) -> int:
    """The white edge round a text's letters, which keeps them legible on any image."""
    return max(1, round(size / 10))


def _blurred(image: Image.Image, mark: Mark) -> None:
    x1, y1, x2, y2 = mark.points
    left, top = max(0, round(min(x1, x2))), max(0, round(min(y1, y2)))
    right, bottom = min(image.width, round(max(x1, x2))), min(image.height, round(max(y1, y2)))
    if right <= left or bottom <= top:
        return
    radius = blur_of(mark.points)
    margin = math.ceil(radius * 3)
    around = (
        max(0, left - margin),
        max(0, top - margin),
        min(image.width, right + margin),
        min(image.height, bottom + margin),
    )
    part = image.crop(around).filter(ImageFilter.GaussianBlur(radius))
    inner = (left - around[0], top - around[1], right - around[0], bottom - around[1])
    image.paste(part.crop(inner), (left, top))


def _placing(edits: Edits, upright: tuple[int, int], size: tuple[int, int]):
    """Where a point of the image upright lands in its copy, and how much smaller the copy is."""
    x0, y0, w, h = edits.crop or (0, 0, *upright)
    across = h if edits.turn in (90, 270) else w
    scale = size[0] / across

    def place(x: float, y: float) -> tuple[float, float]:
        x, y = x - x0, y - y0
        if edits.turn == 90:
            x, y = h - y, x
        elif edits.turn == 180:
            x, y = w - x, h - y
        elif edits.turn == 270:
            x, y = y, w - x
        if edits.flip:
            x = across - x
        return x * scale, y * scale

    return place, scale


def _shape(draw: ImageDraw.ImageDraw, kind: str, points: list[float], width: float, color):
    if kind == "rectangle":
        x1, y1, x2, y2 = points
        half = width / 2
        box = (min(x1, x2) - half, min(y1, y2) - half, max(x1, x2) + half, max(y1, y2) + half)
        draw.rectangle(box, outline=color, width=round(width))
        return
    if kind == "arrow":
        x1, y1, x2, y2 = points
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            return
        across, down = (x2 - x1) / length, (y2 - y1) / length
        head, spread = min(width * HEAD, length), width * SPREAD
        bx, by = x2 - across * head, y2 - down * head
        draw.polygon(
            [
                (x2, y2),
                (bx - down * spread, by + across * spread),
                (bx + down * spread, by - across * spread),
            ],
            fill=color,
        )
        points = [x1, y1, bx, by]
    pairs = list(zip(points[0::2], points[1::2], strict=True))
    draw.line(pairs, fill=color, width=round(width), joint="curve")
    half = width / 2
    for x, y in (pairs[0], pairs[-1]) if kind == "stroke" else (pairs[0],):
        draw.ellipse((x - half, y - half, x + half, y + half), fill=color)


def _stroked(canvas: Image.Image, mark: Mark, points: list[float], width: float) -> None:
    reach = width * (HEAD if mark.kind == "arrow" else 1) + 2
    xs, ys = points[0::2], points[1::2]
    left, top = max(0, math.floor(min(xs) - reach)), max(0, math.floor(min(ys) - reach))
    right = min(canvas.width, math.ceil(max(xs) + reach))
    bottom = min(canvas.height, math.ceil(max(ys) + reach))
    if right <= left or bottom <= top:
        return
    w, h = right - left, bottom - top
    larger = max(1, min(4, math.isqrt(SMOOTHED // (w * h))))
    color = ImageColor.getrgb(mark.color)
    # Clear in the mark's own colour, so that its smoothed edge does not darken.
    layer = Image.new("RGBA", (w * larger, h * larger), (*color, 0))
    local = [(value - (left, top)[at % 2]) * larger for at, value in enumerate(points)]
    _shape(ImageDraw.Draw(layer), mark.kind, local, width * larger, color)
    if larger > 1:
        layer = layer.resize((w, h), Image.Resampling.BOX)
    canvas.alpha_composite(layer, (left, top))


def _written(canvas: Image.Image, mark: Mark, points: list[float], scale: float) -> None:
    size = max(1, round(mark.size * scale))
    ImageDraw.Draw(canvas).text(
        (points[0], points[1]),
        mark.text,
        fill=mark.color,
        font=ImageFont.truetype(FONT, size),
        anchor="ls",
        stroke_width=halo_of(size),
        stroke_fill="white",
    )


def _marked(image: Image.Image, edits: Edits, place, scale: float) -> Image.Image:
    shown = [mark for mark in edits.marks if mark.kind != "blur"]
    if not shown:
        return image
    canvas = image.convert("RGBA")
    for mark in shown:
        pairs = zip(mark.points[0::2], mark.points[1::2], strict=True)
        points = [value for x, y in pairs for value in place(x, y)]
        if mark.kind == "text":
            _written(canvas, mark, points, scale)
        else:
            _stroked(canvas, mark, points, mark.width * scale)
    return canvas if image.mode == "RGBA" else canvas.convert("RGB")


def drawn(blob: Blob, edits: Edits) -> Blob:
    """The image with the edits drawn in, in its own format and colour profile."""
    with client.answered(
        "edit", store.path_of(blob.sha256), edits=edits, media_type=blob.media_type
    ) as answer:
        answer.finish()
        with answer.files[0].open("rb") as file:
            return store.put(file)


def edited(path: Path, edits: Edits, media_type: str) -> bytes:
    """`drawn`, in the reader."""
    with Image.open(path) as opened:
        profile = opened.info.get("icc_profile") if opened.mode != "CMYK" else None
        image = ImageOps.exif_transpose(opened)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
    upright = image.size
    for mark in edits.marks:
        if mark.kind == "blur":
            _blurred(image, mark)
    if edits.crop is not None:
        x, y, w, h = edits.crop
        if x + w > image.width or y + h > image.height:
            raise Unreadable(f"crop {edits.crop} out of {image.size}")
        image = image.crop((x, y, x + w, y + h))
    if TURNS[edits.turn] is not None:
        image = image.transpose(TURNS[edits.turn])
    if edits.flip:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if edits.side is not None:
        image.thumbnail((edits.side, edits.side), Image.Resampling.LANCZOS)
    image = _toned(image, edits)
    image = _marked(image, edits, *_placing(edits, upright, image.size))
    kind = FORMATS[media_type]
    options = {"icc_profile": profile} if profile else {}
    if kind == "JPEG":
        image = image.convert("RGB")
    if kind != "PNG":
        options["quality"] = 90
    out = io.BytesIO()
    image.save(out, kind, **options)
    return out.getvalue()


def draw(pk) -> Node:
    """Draws the file's copy anew where its room changed since it was last drawn."""
    with transaction.atomic():
        file = (
            Node.objects.select_for_update(no_key=True, of=("self",))
            .select_related("blob")
            .get(pk=pk)
        )
        # Read before the state: an edit landing in between is then drawn again next pass.
        seen = Update.objects.filter(room=file.room).aggregate(at=Max("created_at"))["at"]
        if seen is None or (file.edited_at is not None and seen <= file.edited_at):
            return file
        edits = edits_of(file)
        file.edited = None if edits == Edits() else drawn(file.blob, edits)
        file.edited_at = seen
        Node.objects.filter(pk=file.pk).update(edited=file.edited, edited_at=seen)
    if file.edited is not None:
        previews.wake()
    return file


def current(pk) -> Blob | None:
    """The copy to give out, drawn now where the pass has not come to it yet; none while
    nothing is edited."""
    file = draw(pk)
    if file.edited is None and edits_of(file) != Edits():
        raise Unreadable(f"the copy of {pk} could not be drawn")
    return file.edited


def due(now: datetime):
    last = Update.objects.filter(room=OuterRef("room")).order_by("-id")
    return (
        Node.objects.filter(kind=Node.Kind.FILE, blob__media_type__in=FORMATS)
        .annotate(changed_at=Subquery(last.values("created_at")[:1]))
        .filter(changed_at__lte=now - settings.EDITED_QUIET)
        .filter(Q(edited_at__isnull=True) | Q(changed_at__gt=F("edited_at")))
    )


def tend(now: datetime | None = None) -> None:
    for file in due(now or timezone.now()):
        try:
            draw(file.pk)
        except FAILURES:
            log.exception("edits: the copy of %s could not be drawn", file.pk)
            Node.objects.filter(pk=file.pk).update(edited=None, edited_at=file.changed_at)


async def follow() -> None:
    """Keeps each image file's copy following its edits while the server runs."""
    while True:
        try:
            await database(tend, own_thread=True)()
        except Exception:
            log.exception("edits: a pass failed")
        await sleep(EVERY)
