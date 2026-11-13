from logging import getLogger

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.blobs import store, text
from apps.blobs.models import Blob
from apps.content.blocks import Block, key_of
from apps.content.models import DocumentBlob
from apps.core.asyncdb import database, drain, notify
from apps.documents.models import Node
from apps.imports import convert, reading
from apps.imports.formats import EXTENSIONS
from apps.mail.models import Attachment

from . import ocr, pdf
from .models import BlobPage, BlobText

log = getLogger(__name__)

CHANNEL = "search_text"
# A text file is searched by this much of it, in pages a search vector holds.
SEARCHED = 32 * 1024 * 1024
PAGE = 64 * 1024


def wake() -> None:
    """Has the extractor look for new files once the current transaction commits."""
    notify(CHANNEL)


def waiting():
    """The blobs whose text is still to be read: a PDF a file uses, a document shows or a message
    carries, and an Office or text file a file keeps or a message carries."""
    carried = Exists(Attachment.objects.filter(blob=OuterRef("pk"), inline=False))
    filed = Exists(Node.objects.filter(blob=OuterRef("pk")))
    used = filed | Exists(DocumentBlob.objects.filter(blob=OuterRef("pk")))
    return Blob.objects.filter(text__isnull=True).filter(
        Q(media_type=store.PDF) & (used | carried)
        | (Q(media_type__in=EXTENSIONS) | Q(media_type__startswith="text/")) & (filed | carried)
    )


def _text(blocks: list[Block]) -> str:
    """A tab's text: each paragraph a line, and each table's rows with their cells apart."""
    lines = []
    for block in blocks:
        if block.type != "table":
            lines.append(block.text)
            continue
        grid = block.grid
        cells = (grid.texts if grid else {}) | {
            key_of(cell.row, cell.col): cell.text for cell in block.cells
        }
        for row in grid.rows if grid else []:
            keys = [key_of(row, col) for col in grid.cols]
            shown = [cells.get(key) or grid.values.get(key, {}).get("text", "") for key in keys]
            lines.append(" | ".join(each.replace("\n", " ") for each in shown if each))
    return "\n".join(line for line in lines if line.strip())


def _read(blob: Blob) -> list[str]:
    if blob.media_type == store.PDF:
        return pdf.texts(store.path_of(blob.sha256))
    if blob.media_type == store.HTML:
        return text.pages(text.seen(text.read(blob, SEARCHED).text), PAGE)
    if blob.media_type.startswith("text/"):
        return text.pages(text.read(blob, SEARCHED).text, PAGE)
    return convert.pages(blob, settings.LANGUAGE_CODE)


def paged(tabs) -> list[str]:
    """The pages of an Office file's text, each tab's apart; in the reader."""
    return [page for tab in tabs for page in text.pages(_text(tab.blocks), PAGE) or [""]]


def _keep(blob: Blob) -> None:
    texts = _read(blob)
    found = BlobText.objects.create(blob=blob, page_count=len(texts), extracted_at=timezone.now())
    pages = BlobPage.objects.bulk_create(
        BlobPage(source=found, number=number, text=text)
        for number, text in enumerate(texts, start=1)
        if text.strip()
    )
    if (
        blob.media_type == store.PDF
        and len(pages) < len(texts)
        and (
            Node.objects.filter(blob=blob).exists()
            or Attachment.objects.filter(blob=blob, inline=False).exists()
        )
    ):
        ocr.queue(blob)


def _failed(blob: Blob, error: Exception) -> None:
    BlobText.objects.create(
        blob=blob, page_count=0, failed=repr(error), extracted_at=timezone.now()
    )


def extract_next() -> bool:
    """Extracts the text of one file waiting; False when none is, or when the converter does not
    answer, to try again at the next sweep. A file that cannot be read is recorded as failed, so
    that nothing waits behind it. Only the pages without text of a PDF a file uses or a message
    carries are read by OCR: a document shows its PDF as it came."""
    with transaction.atomic():
        # Waited for, not skipped: the drawer holds a PDF while it draws its picture, and a file
        # skipped would wait for the next sweep. Whoever held it may have read it meanwhile.
        blob = waiting().select_for_update(no_key=True, of=("self",)).first()
        if blob is None:
            return False
        if BlobText.objects.filter(blob=blob).exists():
            return True
        path = store.path_of(blob.sha256)
        # With the store not mounted every file would look gone and be marked failed for good.
        if not path.exists() and not any(store.root().iterdir()):
            raise FileNotFoundError(path)
        try:
            with transaction.atomic():
                _keep(blob)
        except convert.Unavailable:
            log.warning("search: the converter did not answer for %s", blob.sha256)
            return False
        except (reading.Unreadable, reading.TooLarge, text.NotText) as error:
            log.warning("search: no text from %s: %r", blob.sha256, error)
            _failed(blob, error)
        except Exception as error:
            if isinstance(error, OSError) and error.errno and path.exists():
                raise
            log.exception("search: reading %s failed", blob.sha256)
            _failed(blob, error)
        return True


async def extract() -> None:
    """Extracts text while the server runs: as soon as a file is created, and in a sweep every
    SEARCH_SWEEP for whatever a lost notification left."""
    await drain(CHANNEL, database(extract_next, own_thread=True), settings.SEARCH_SWEEP, log)
