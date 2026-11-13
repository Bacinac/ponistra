import io
from logging import getLogger
from pathlib import Path

import pypdfium2 as pdfium
from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from PIL import Image, ImageOps

from apps.core.asyncdb import database, drain, notify
from apps.documents.models import Node
from apps.imports.reading import TooLarge, Unreadable
from apps.reader import client

from . import store
from .models import Blob, Preview

log = getLogger(__name__)

CHANNEL = "previews"
# The longest side in pixels: twice what a folder's pane shows, for a screen of two pixels a point.
SIDE = 800
DRAWN = {media for media in store.IMAGES if media != "image/svg+xml"} | {store.PDF}


def wake() -> None:
    """Has the drawer look for new files once the current transaction commits."""
    notify(CHANNEL)


def _waiting():
    """The images and PDFs a file keeps, or its edited copy, that have no picture yet."""
    filed = Exists(Node.objects.filter(Q(blob=OuterRef("pk")) | Q(edited=OuterRef("pk"))))
    return Blob.objects.filter(preview__isnull=True, media_type__in=DRAWN).filter(filed)


def _page(file) -> Image.Image:
    pdf = pdfium.PdfDocument(file)
    try:
        page = pdf[0]
        width, height = page.get_size()
        return page.render(scale=SIDE / max(width, height)).to_pil()
    finally:
        pdf.close()


def _image(file) -> Image.Image:
    with Image.open(file) as opened:
        # A JPEG is decoded at the smallest scale that still covers SIDE, not whole.
        opened.draft("RGB", (SIDE, SIDE))
        image = ImageOps.exif_transpose(opened)
    image.thumbnail((SIDE, SIDE))
    return image


def picture(path: Path, pdf: bool) -> bytes:
    """The picture of an image, or of a PDF's first page, as WEBP; in the reader."""
    with path.open("rb") as file:
        image = _page(file) if pdf else _image(file)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
    out = io.BytesIO()
    image.save(out, "WEBP", quality=80)
    return out.getvalue()


def _draw(blob: Blob) -> Preview:
    try:
        drawn = client.ask("preview", store.path_of(blob.sha256), pdf=blob.media_type == store.PDF)
    except (Unreadable, TooLarge) as error:
        log.warning("previews: no picture of %s: %r", blob.sha256, error)
        return Preview.objects.create(source=blob, failed=repr(error), drawn_at=timezone.now())
    return Preview.objects.create(
        source=blob, picture=store.put(io.BytesIO(drawn)), drawn_at=timezone.now()
    )


def drawn(blob: Blob) -> Preview | None:
    """The picture of an image or a PDF, drawn now where the drawer has not come to it yet, as
    for a file just uploaded; None for bytes of any other kind."""
    if blob.media_type not in DRAWN:
        return None
    with transaction.atomic():
        Blob.objects.select_for_update(no_key=True).get(pk=blob.pk)
        return Preview.objects.filter(source=blob).first() or _draw(blob)


def draw_next() -> bool:
    """Draws the picture of one file waiting; False when none is."""
    with transaction.atomic():
        # Waited for, not skipped: the extractor holds a PDF while it reads its text, and a file
        # skipped would wait for the next sweep. Whoever held it may have drawn it meanwhile.
        blob = _waiting().select_for_update(no_key=True, of=("self",)).first()
        if blob is None:
            return False
        if not Preview.objects.filter(source=blob).exists():
            _draw(blob)
        return True


async def draw() -> None:
    """Draws pictures while the server runs: as soon as a file is created, and in a sweep every
    PREVIEW_SWEEP for whatever a lost notification left."""
    await drain(CHANNEL, database(draw_next, own_thread=True), settings.PREVIEW_SWEEP, log)
