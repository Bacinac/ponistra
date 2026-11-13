"""Pages photographed with a phone made into one PDF file (D43): each page's corners found, the
page straightened from them and its paper evened out to white, in the reader (D51); the text is
then read by the ocr service before the file is kept, so it is searchable as it lands."""

import io
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anyio
import numpy as np
import pikepdf
from django.db import transaction
from pikepdf import Dictionary, Name
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from apps.access.models import Grant, Role
from apps.blobs import previews, store
from apps.blobs.models import Blob
from apps.documents.models import Node
from apps.reader import client
from apps.search import extraction, ocr

from .reading import Unreadable

Corners = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]

# The side the corners are looked for at: a page's outline needs no more.
LOOKED_AT = 512
# Below this share of the photo the brightest region is not taken for the page.
SMALLEST_PAGE = 0.15
# The smallest share of the photo the corners may enclose.
SMALLEST_DRAWN = 0.01
# 300 dpi down an A4 page.
LONGEST = 3508
# Each page's longer side is an A4 page's, in points: a photo does not tell the paper's size.
A4_LONG = 841.89
QUALITY = 80
# The paper's own brightness, a little below what the maximum around the writing finds, so that
# its grain turns white rather than grey.
PAPER = 235
WHOLE: Corners = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


@dataclass(frozen=True)
class Page:
    """A photographed page and its corners, top left first and on clockwise, each across and
    down the upright photo from 0 to 1."""

    blob: Blob
    corners: Corners


def quad_of(value: object) -> Corners | None:
    """Four corners within the photo that make a convex page, given clockwise from the top
    left; None for anything else."""
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    points = []
    for point in value:
        if not isinstance(point, list | tuple) or len(point) != 2:
            return None
        if not all(type(each) in (int, float) and 0 <= each <= 1 for each in point):
            return None
        points.append((float(point[0]), float(point[1])))
    turns = [
        (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        for a, b, c in zip(points, points[1:] + points[:1], points[2:] + points[:2], strict=True)
    ]
    after = points[1:] + points[:1]
    area = sum(x * v - u * y for (x, y), (u, v) in zip(points, after, strict=True)) / 2
    if not all(turn > 0 for turn in turns) or area < SMALLEST_DRAWN:
        return None
    return tuple(points)  # type: ignore[return-value]


def _upright(path: Path, mode: str, draft: tuple[int, int] | None = None) -> Image.Image:
    with Image.open(path) as image:
        if draft is not None:
            image.draft(mode, draft)
        return ImageOps.exif_transpose(image).convert(mode)


def _threshold(pixels: np.ndarray) -> int:
    """Otsu's level, which parts the pixels into the two groups that differ the most."""
    counts = np.bincount(pixels.ravel(), minlength=256).astype(np.float64)
    share = counts / counts.sum()
    below = np.cumsum(share)
    mean = np.cumsum(share * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mean[-1] * below - mean) ** 2 / (below * (1 - below))
    return int(np.nanargmax(between))


def _largest(mask: Image.Image) -> np.ndarray:
    """The largest connected region of a mask of 0 and 255, each region flooded with a number
    of its own from seeds across the mask."""
    regions = mask.copy()
    width, height = regions.size
    step = max(1, min(width, height) // 16)
    number = 1
    for y in range(0, height, step):
        for x in range(0, width, step):
            if number < 255 and regions.getpixel((x, y)) == 255:
                ImageDraw.floodfill(regions, (x, y), number)
                number += 1
    counts = regions.histogram()[1:number]
    found = np.asarray(regions)
    return found == (int(np.argmax(counts)) + 1) if counts else np.zeros_like(found, dtype=bool)


def corners(path: Path) -> Corners:
    """Where the page's corners are in the photo: the extremes of the largest bright region,
    taken for paper against what it lies on; the whole photo where none stands out; in the
    reader."""
    small = _upright(path, "L", (LOOKED_AT * 2, LOOKED_AT * 2))
    small.thumbnail((LOOKED_AT, LOOKED_AT))
    small = small.filter(ImageFilter.GaussianBlur(2))
    pixels = np.asarray(small)
    if pixels.min() == pixels.max():
        return WHOLE
    bright = Image.fromarray(np.where(pixels > _threshold(pixels), 255, 0).astype(np.uint8))
    page = _largest(bright.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5)))
    if page.sum() < SMALLEST_PAGE * page.size:
        return WHOLE
    ys, xs = np.nonzero(page)
    sums, differences = xs + ys, xs - ys
    width, height = small.size
    found = [
        (xs[at], ys[at])
        for at in (
            np.argmin(sums),
            np.argmax(differences),
            np.argmax(sums),
            np.argmin(differences),
        )
    ]
    return tuple(  # type: ignore[return-value]
        (round(float(x) / (width - 1), 4), round(float(y) / (height - 1), 4)) for x, y in found
    )


def _perspective(target: list[tuple[float, float]], source: list[tuple[float, float]]) -> list:
    """The coefficients of the transform Pillow maps each point of the new image by to the
    point of the photo it is taken from."""
    rows, values = [], []
    for (x, y), (u, v) in zip(target, source, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        values += [u, v]
    return np.linalg.solve(np.array(rows), np.array(values)).tolist()


def _straightened(path: Path, quad: Corners) -> Image.Image:
    photo = _upright(path, "RGB")
    across, down = photo.size
    tl, tr, br, bl = [(x * across, y * down) for x, y in quad]
    width = max(np.hypot(*np.subtract(tr, tl)), np.hypot(*np.subtract(br, bl)))
    height = max(np.hypot(*np.subtract(bl, tl)), np.hypot(*np.subtract(br, tr)))
    scale = min(1.0, LONGEST / max(width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    corners_out = [(0, 0), (size[0], 0), size, (0, size[1])]
    coefficients = _perspective(corners_out, [tl, tr, br, bl])
    return photo.transform(
        size, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC
    )


def _cleaned(page: Image.Image) -> Image.Image:
    """The page with its paper made white wherever the light fell on it: each pixel divided by
    the brightness of the paper around it, which a wide maximum finds above the writing, and
    every channel by the same, so that the colours keep their hue."""
    width, height = page.size
    small = page.convert("L").resize((max(1, width // 16), max(1, height // 16)), Image.BOX)
    paper = small.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3))
    paper = paper.resize((width, height), Image.Resampling.BILINEAR)
    colours = np.asarray(page, dtype=np.uint16)
    light = np.maximum(np.asarray(paper, dtype=np.uint16), 1)[..., None]
    even = np.minimum(colours * 255 // np.minimum(light, PAPER), 255).astype(np.uint8)
    return Image.fromarray(even)


def made(paths: list[Path], quads: list, out) -> int:
    """Sends the PDF file of the pages photographed, each straightened from its corners and
    cleaned, a page each; it ends with how many; in the reader."""
    pdf = pikepdf.new()
    for path, quad in zip(paths, quads, strict=True):
        page = _cleaned(_straightened(path, tuple(map(tuple, quad))))
        written = io.BytesIO()
        page.save(written, "JPEG", quality=QUALITY, optimize=True)
        width, height = page.size
        scale = A4_LONG / max(width, height)
        drawn = (width * scale, height * scale)
        image = pikepdf.Stream(
            pdf,
            written.getvalue(),
            Type=Name.XObject,
            Subtype=Name.Image,
            Width=width,
            Height=height,
            ColorSpace=Name.DeviceRGB,
            BitsPerComponent=8,
            Filter=Name.DCTDecode,
        )
        added = pdf.add_blank_page(page_size=drawn)
        added.Resources = Dictionary(XObject=Dictionary(Scan=image))
        added.Contents = pdf.make_stream(
            f"q {drawn[0]:.2f} 0 0 {drawn[1]:.2f} 0 0 cm /Scan Do Q".encode()
        )
    with tempfile.NamedTemporaryFile(suffix=".pdf") as file:
        pdf.save(file)
        file.flush()
        out.file(Path(file.name))
    return len(paths)


def found(blob: Blob) -> Corners:
    return client.ask("scan_corners", store.path_of(blob.sha256))


def scanned(pages: list[Page]) -> Blob:
    """The PDF file of the pages, with the text the ocr service reads in them."""
    paths = [store.path_of(page.blob.sha256) for page in pages]
    with client.answered("scan", *paths, corners=[page.corners for page in pages]) as answer:
        answer.finish()
        with tempfile.TemporaryDirectory() as work:
            read = Path(work) / "read.pdf"
            try:
                anyio.run(ocr.asked, answer.files[0], read)
            except ocr.Failed as failure:
                raise Unreadable(f"the scan's text could not be read: {failure}") from failure
            with read.open("rb") as file:
                return store.put(file)


def scan(pages: list[Page], parent: Node | None, title: str, user) -> Node:
    """The new file, in the folder given or at the top of the user's own documents."""
    blob = scanned(pages)
    with transaction.atomic():
        node = Node.objects.create(
            parent=parent,
            kind=Node.Kind.FILE,
            title=title,
            blob=blob,
            created_by=user,
            updated_by=user,
        )
        if parent is None:
            Grant.objects.create(node=node, user=user, role=Role.OWN, created_by=user)
        extraction.wake()
        previews.wake()
    return node
