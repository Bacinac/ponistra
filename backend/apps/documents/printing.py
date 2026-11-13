"""The printer: a headless browser that saves the document's print page as PDF, counts each
tab's pages there or measures its slides, loaded in a reader's own session so it lays out what
they may read as they would see it, and draws an SVG image as PNG for a Word file."""

import io
import json
import re
import urllib.error
import urllib.request
import uuid
from contextlib import ExitStack
from email.message import Message
from urllib.parse import urlencode

import pikepdf
from django.conf import settings

from apps.core.asyncdb import released

TIMEOUT = 180
# A picture's longest side, in pixels before the printer doubles them.
DRAWN = 1024
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
RUNS = re.compile(r"[1-9][0-9]*( [1-9][0-9]*)*")


class Unavailable(Exception):
    """The printer did not answer with the pages."""


def compact(id: uuid.UUID) -> str:
    """The id as an address writes it: 22 base62 digits."""
    value, digits = id.int, ""
    for _ in range(22):
        value, digit = divmod(value, 62)
        digits = DIGITS[digit] + digits
    return digits


def _answered(request: urllib.request.Request) -> tuple[bytes, Message]:
    released()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as error:
        raise Unavailable(f"{error.code}: {error.read().decode(errors='replace')}") from error
    except OSError as error:
        raise Unavailable from error


def _laid_out(
    job: str, document_id: uuid.UUID, session: str, page: str = ""
) -> tuple[bytes, Message]:
    asked = {
        "path": f"/print/{compact(document_id)}{page}",
        "cookie": settings.SESSION_COOKIE_NAME,
        "session": session,
        "timezone": settings.TIME_ZONE,
    }
    request = urllib.request.Request(
        f"{settings.PRINTER_URL}/{job}",
        data=json.dumps(asked).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _answered(request)


def printed(document_id: uuid.UUID, session: str) -> bytes:
    """The print page saved as PDF, its runs of pages joined in order."""
    data, headers = _laid_out("pdf", document_id, session)
    told = headers.get("X-Runs", "")
    runs = [int(run) for run in told.split()] if RUNS.fullmatch(told) else []
    if not runs or sum(runs) != len(data):
        raise Unavailable(f"the printer sent runs {told!r} for {len(data)} bytes")
    if len(runs) == 1:
        return data
    with ExitStack() as opened:
        parts, at = [], 0
        for run in runs:
            try:
                parts.append(opened.enter_context(pikepdf.open(io.BytesIO(data[at : at + run]))))
            except pikepdf.PdfError as error:
                raise Unavailable(f"the printer sent a run that is no PDF at {at}") from error
            at += run
        joined, *rest = parts
        for part in rest:
            joined.pages.extend(part.pages)
        buffer = io.BytesIO()
        joined.save(buffer)
        return buffer.getvalue()


def counted(document_id: uuid.UUID, session: str) -> dict[str, int]:
    """Each tab's count of pages, by its id."""
    try:
        pages = json.loads(_laid_out("pages", document_id, session)[0])
    except ValueError as error:
        raise Unavailable from error
    if not isinstance(pages, dict) or not all(
        type(count) is int and count > 0 for count in pages.values()
    ):
        raise Unavailable(f"the printer counted {pages!r}")
    return pages


def measured(document_id: uuid.UUID, session: str) -> dict[str, list]:
    """Each tab's slides as the Slides view lays them out, by its id: where each box and block
    shows and how far its text is shrunk (frontend editor/deck.ts `measuredSlides`)."""
    try:
        slides = json.loads(_laid_out("slides", document_id, session, "/slides")[0])
    except ValueError as error:
        raise Unavailable from error
    if not isinstance(slides, dict) or not all(isinstance(tab, list) for tab in slides.values()):
        raise Unavailable("the printer measured no slides")
    return slides


def drawn(svg: bytes, width: float, height: float) -> bytes:
    """A PNG of the SVG, as a browser shows it as an image of that size in pixels, at most
    DRAWN on its longer side."""
    scale = min(1, DRAWN / max(width, height))
    size = {"width": max(1, round(width * scale)), "height": max(1, round(height * scale))}
    request = urllib.request.Request(
        f"{settings.PRINTER_URL}/png?{urlencode(size)}",
        data=svg,
        headers={"Content-Type": "image/svg+xml"},
        method="POST",
    )
    return _answered(request)[0]
