"""An image's pixels under boxes cleared, the rest of it as it was: samples a general filter holds
are cleared where they lie, a JPEG is saved again with its own tables, a fax image encoded again as
it came, and a JBIG2 image, which nothing permissive encodes, kept as plain samples."""

import io
import math

import pikepdf
import pypdfium2 as pdfium
from pikepdf import Array, Dictionary, Name, Pdf, Stream
from PIL import Image

from .fonts import number
from .paths import Point, clipped

GENERAL = {
    "/FlateDecode",
    "/Fl",
    "/LZWDecode",
    "/LZW",
    "/RunLengthDecode",
    "/RL",
    "/ASCIIHexDecode",
    "/AHx",
    "/ASCII85Decode",
    "/A85",
}
DROPPED = {
    "/Filter",
    "/DecodeParms",
    "/Length",
    "/SMask",
    "/Mask",
    "/Alternates",
    "/Metadata",
    "/OPI",
}


class Undecodable(Exception):
    """An image whose pixels cannot be read, and so cannot be cleared."""


def _spans(polygons: list[list[Point]], width: int, height: int) -> list[tuple[int, int, int]]:
    """Each pixel row the polygons, given in the image's unit square, touch, from which column to
    which."""
    found: dict[int, tuple[int, int]] = {}
    for polygon in polygons:
        pixels = [(u * width, (1 - v) * height) for u, v in polygon]
        low = max(0, math.floor(min(y for _, y in pixels)))
        high = min(height, math.ceil(max(y for _, y in pixels)))
        for row in range(low, high):
            part = clipped(pixels, (0, row, width, row + 1))
            if len(part) < 3 or _area(part) < 1e-6:
                continue
            first = max(0, math.floor(min(x for x, _ in part) + 1e-9))
            last = min(width, math.ceil(max(x for x, _ in part) - 1e-9))
            if last > first:
                held = found.get(row)
                found[row] = (min(first, held[0]), max(last, held[1])) if held else (first, last)
    return [(row, first, last) for row, (first, last) in sorted(found.items())]


def _area(polygon: list[Point]) -> float:
    return abs(
        sum(
            x1 * y2 - x2 * y1
            for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True)
        )
        / 2
    )


def _filters(image: Stream) -> list[str]:
    given = image.get("/Filter")
    if isinstance(given, Name):
        return [str(given)]
    return [str(each) for each in given] if isinstance(given, Array) else []


def _space(given: object, spaces: Dictionary | None) -> object:
    if isinstance(given, Name) and spaces is not None and given in spaces:
        return spaces[given]
    return given


def _family(space: object) -> str:
    if isinstance(space, Array) and len(space):
        return str(space[0])
    return str(space) if isinstance(space, Name) else ""


def _components(space: object) -> int:
    family = _family(space)
    if family in ("/DeviceRGB", "/RGB", "/CalRGB", "/Lab"):
        return 3
    if family in ("/DeviceCMYK", "/CMYK"):
        return 4
    if family == "/ICCBased":
        return int(number(space[1].get("/N"), 1))
    if family == "/DeviceN":
        return len(space[1])
    return 1


def _lightness(base: object, values: list[int]) -> float:
    family = _family(base)
    if family == "/ICCBased":
        family = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}.get(_components(base), "")
    if family in ("/DeviceGray", "/G", "/CalGray"):
        return values[0]
    if family in ("/DeviceRGB", "/RGB", "/CalRGB"):
        return 0.3 * values[0] + 0.59 * values[1] + 0.11 * values[2]
    if family in ("/DeviceCMYK", "/CMYK"):
        return (255 - values[3]) * (255 - sum(values[:3]) / 3)
    return 0.0


def _darkest(space: Array) -> int:
    base, top, lookup = space[1], int(number(space[2])), space[3]
    table = lookup.read_bytes() if isinstance(lookup, Stream) else bytes(lookup)
    size = _components(base)
    entries = [list(table[index * size : (index + 1) * size]) for index in range(top + 1)]
    entries = [each for each in entries if len(each) == size]
    return min(range(len(entries)), key=lambda index: _lightness(base, entries[index]), default=0)


def _cleared(image: Stream, space: object, role: str) -> tuple[int, int]:
    """The bits of one cleared pixel and how many bits a pixel takes: black where the image is
    painted, opaque where it is a soft mask, so that a pixel half under a box looks as the box."""
    stencil = image.get("/ImageMask") is True
    bits = 1 if stencil else int(number(image.get("/BitsPerComponent"), 8))
    count = 1 if stencil or role != "image" else _components(space)
    top = (1 << bits) - 1
    family = _family(space)
    if role == "smask" or role == "image" and stencil:
        values = [top]
    elif role == "mask":
        values = [0]
    elif family in ("/DeviceCMYK", "/CMYK") or family == "/ICCBased" and count == 4:
        values = [0, 0, 0, top]
    elif family in ("/Separation", "/DeviceN"):
        values = [top] * count
    elif family in ("/Indexed", "/I"):
        values = [min(_darkest(space), top)]
    else:
        values = [0] * count
    decode = [number(each) for each in image.get("/Decode", Array())]
    if len(decode) == 2 * count:
        values = [
            top - value if decode[2 * index] > decode[2 * index + 1] else value
            for index, value in enumerate(values)
        ]
    pixel = 0
    for value in values:
        pixel = (pixel << bits) | value
    return pixel, bits * count


def _clear(
    data: bytearray, width: int, spans: list[tuple[int, int, int]], pixel: int, size: int
) -> None:
    stride = (width * size + 7) // 8
    for row, first, last in spans:
        start = row * stride
        if start + stride > len(data):
            continue
        line = int.from_bytes(data[start : start + stride])
        count = last - first
        shift = stride * 8 - last * size
        run = pixel * (((1 << (count * size)) - 1) // ((1 << size) - 1))
        whole = ((1 << (count * size)) - 1) << shift
        line = (line & ~whole) | (run << shift)
        data[start : start + stride] = line.to_bytes(stride)


def _copy(pdf: Pdf, image: Stream, data: bytes, **given: object) -> Stream:
    kept = Dictionary({key: value for key, value in image.items() if key not in DROPPED})
    for key, value in given.items():
        kept[Name("/" + key)] = value
    return pdf.make_stream(data, kept)


def _encoded(pdf: Pdf, image: Stream, filters: list[str]) -> bytes:
    """The data with every filter but the last undone."""
    if len(filters) == 1:
        return image.read_raw_bytes()
    parms = image.get("/DecodeParms")
    stream = pdf.make_stream(
        image.read_raw_bytes(),
        Filter=Array([Name(each) for each in filters[:-1]]),
        **({"DecodeParms": Array(list(parms)[:-1])} if isinstance(parms, Array) else {}),
    )
    return stream.read_bytes()


def _pillow(encoded: bytes, spans: list[tuple[int, int, int]], kind: str) -> bytes:
    try:
        picture = Image.open(io.BytesIO(encoded))
        picture.load()
    except OSError as error:
        raise Undecodable(f"{kind}: {error}") from error
    black = tuple(255 if band in ("A", "K") else 0 for band in picture.getbands())
    for row, first, last in spans:
        picture.paste(black if len(black) > 1 else black[0], (first, row, last, row + 1))
    written = io.BytesIO()
    if kind == "JPEG":
        picture.save(written, "JPEG", quality="keep", subsampling="keep", comment=b"")
    else:
        picture.save(written, "JPEG2000")
    return written.getvalue()


def _bilevel(pdf: Pdf, image: Stream) -> bytearray:
    """A fax or JBIG2 image's samples, one bit each, read by pdfium: pdfium paints them, and two
    pixels of known samples drawn beside them tell which colour stands for which sample."""
    scratch = pikepdf.new()
    page = scratch.add_blank_page(page_size=(3, 3))
    found = scratch.copy_foreign(image)
    known = scratch.make_stream(
        b"\x40", Dictionary({key: value for key, value in found.items() if key not in DROPPED})
    )
    known.Width, known.Height = 2, 1
    page.Resources = Dictionary(XObject=Dictionary(Found=found, Known=known))
    page.Contents = scratch.make_stream(
        b"q 1 0 0 1 0 0 cm /Found Do Q q 1 0 0 1 1 0 cm /Known Do Q"
    )
    written = io.BytesIO()
    scratch.save(written)
    document = pdfium.PdfDocument(written.getvalue())
    try:
        drawn = [each for each in document[0].get_objects() if isinstance(each, pdfium.PdfImage)]
        if len(drawn) != 2:
            raise Undecodable("pdfium reads no image")
        try:
            pixels, sampled = (each.get_bitmap(render=False).to_pil() for each in drawn)
        except pdfium.PdfiumError as error:
            raise Undecodable(str(error)) from error
    finally:
        document.close()
    zero, one = sampled.getpixel((0, 0)), sampled.getpixel((1, 0))
    zero, one = (zero, one) if isinstance(zero, tuple) else ((zero,), (one,))
    band = next((index for index, (a, b) in enumerate(zip(zero, one, strict=True)) if a != b), None)
    if band is None:
        samples = Image.new("L", pixels.size, 0)
    else:
        middle, rising = (zero[band] + one[band]) / 2, one[band] > zero[band]
        samples = pixels.getchannel(band).point(
            lambda value: 255 if (value > middle) == rising else 0
        )
    return bytearray(samples.convert("1", dither=Image.Dither.NONE).tobytes())


def _fax(data: bytes, width: int, height: int) -> tuple[bytes, Dictionary]:
    written = io.BytesIO()
    Image.frombytes("1", (width, height), data).save(
        written, "TIFF", compression="group4", tiffinfo={278: height}
    )
    tiff = Image.open(io.BytesIO(written.getvalue()))
    start, length = tiff.tag_v2[273][0], tiff.tag_v2[279][0]
    parms = Dictionary(K=-1, Columns=width, Rows=height, BlackIs1=tiff.tag_v2[262] == 1)
    return written.getvalue()[start : start + length], parms


def painted(
    pdf: Pdf,
    image: Stream,
    polygons: list[list[Point]],
    spaces: Dictionary | None,
    role: str = "image",
) -> Stream | None:
    """A copy of the image with every pixel the polygons touch cleared, its masks with it, or None
    where they touch none. The polygons lie in the image's unit square."""
    width, height = int(number(image.get("/Width"))), int(number(image.get("/Height")))
    if width <= 0 or height <= 0:
        return None
    spans = _spans(polygons, width, height)
    if not spans:
        return None
    filters = _filters(image)
    last = filters[-1] if filters else None
    space = _space(image.get("/ColorSpace"), spaces)
    if all(each in GENERAL for each in filters):
        try:
            data = bytearray(image.read_bytes())
        except pikepdf.PdfError as error:
            raise Undecodable(str(error)) from error
        _clear(data, width, spans, *_cleared(image, space, role))
        copy = _copy(pdf, image, bytes(data))
    elif last in ("/DCTDecode", "/DCT"):
        copy = _copy(
            pdf, image, _pillow(_encoded(pdf, image, filters), spans, "JPEG"), Filter=Name.DCTDecode
        )
    elif last == "/JPXDecode":
        copy = _copy(
            pdf,
            image,
            _pillow(_encoded(pdf, image, filters), spans, "JPEG2000"),
            Filter=Name.JPXDecode,
        )
    elif last in ("/CCITTFaxDecode", "/CCF", "/JBIG2Decode"):
        data = _bilevel(pdf, image)
        _clear(data, width, spans, *_cleared(image, space, role))
        if last == "/JBIG2Decode":
            copy = _copy(pdf, image, bytes(data))
        else:
            encoded, parms = _fax(bytes(data), width, height)
            copy = _copy(pdf, image, encoded, Filter=Name.CCITTFaxDecode, DecodeParms=parms)
    else:
        raise Undecodable(f"an image encoded by {last}")
    for key, kind in (("/SMask", "smask"), ("/Mask", "mask")):
        mask = image.get(key)
        if isinstance(mask, Stream):
            cleared = painted(pdf, mask, polygons, spaces, kind)
            copy[key] = mask if cleared is None else cleared
        elif mask is not None:
            copy[key] = mask
    return copy
