"""Text Tesseract reads in the pages of a PDF that carry none, in the ocr service, which
reaches nothing but the backend. The file stays as it came: the copy with the text laid over
its pages is a blob of its own, read once for the same bytes, and it is what the file is shown,
searched, written and taken apart from."""

import tempfile
from datetime import timedelta
from logging import getLogger
from pathlib import Path
from urllib.parse import urlsplit

import anyio
from anyio import CancelScope
from anyio.streams.buffered import BufferedByteReceiveStream
from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.ai.detection import language_in
from apps.blobs import store
from apps.blobs.models import Blob
from apps.core.asyncdb import database, drain, notify
from apps.documents.models import Node
from apps.imports.reading import TooLarge, Unreadable

from . import pdf
from .models import BlobPage, BlobText, PdfOcr

log = getLogger(__name__)

CHANNEL = "search_ocr"
CHUNK = 1024 * 1024
HEAD = 16 * 1024
# Longer than the service's own limit, so that it is the service that gives up and says why.
TIMEOUT = 25 * 60
# A claim older than this was left by a process that died while the file was read.
LEASE = timedelta(minutes=30)


class Unavailable(Exception):
    """The service did not answer."""


class Declined(Exception):
    """Reading the file would break what protects it: its encryption or its signatures."""


class Failed(Exception):
    """The file could not be read, or what was read could not be kept."""


def queue(blob: Blob) -> None:
    PdfOcr.objects.create(blob=blob, queued_at=timezone.now())
    notify(CHANNEL)


def retry(blob: Blob) -> bool:
    """Queues a file whose reading failed once more; False when it had not failed."""
    again = PdfOcr.objects.filter(pk=blob.pk, state=PdfOcr.State.FAILED).update(
        state=PdfOcr.State.WAITING,
        reason="",
        queued_at=timezone.now(),
        started_at=None,
        finished_at=None,
    )
    if again:
        notify(CHANNEL)
    return bool(again)


def readable(blob: Blob) -> Blob:
    """The bytes with the text read in their pages when there is any, else as they came."""
    found = PdfOcr.objects.filter(blob=blob).exclude(readable=None).select_related("readable")
    return found[0].readable if found else blob


def _language(blob: Blob) -> str | None:
    pages = (
        BlobPage.objects.filter(source_id=blob.pk).exclude(text__regex=r"^\s*$").order_by("number")
    )
    return language_in("\n".join(pages.values_list("text", flat=True)[:3]))


def described(blob: Blob) -> dict:
    """The bytes the file page shows, where their reading stands, `checking` until the text is
    extracted and it is known whether any page needs reading, and the language of its text once
    the reading is over (D35)."""
    found = PdfOcr.objects.filter(blob=blob).first()
    if found is not None:
        state = found.state
    elif not BlobText.objects.filter(blob=blob).exists():
        state = "checking"
    else:
        state = None
    return {
        "served": found.readable_id if found and found.readable_id else blob.sha256,
        "recognised": bool(found and found.readable_id),
        "ocr": state,
        "reason": found.reason if found and found.state == PdfOcr.State.REFUSED else None,
        "language": None if state in {"checking", PdfOcr.State.WAITING} else _language(blob),
    }


def waiting():
    """The files queued for reading that a folder holds: bytes kept only by a version wait
    until one is restored."""
    return PdfOcr.objects.filter(state=PdfOcr.State.WAITING).filter(
        Exists(Node.objects.filter(blob=OuterRef("blob")))
    )


def claim() -> PdfOcr | None:
    now = timezone.now()
    with transaction.atomic():
        found = (
            waiting()
            .filter(Q(started_at=None) | Q(started_at__lt=now - LEASE))
            .order_by("queued_at")
            .select_for_update(no_key=True, skip_locked=True, of=("self",))
            .first()
        )
        if found is not None:
            found.started_at = now
            found.save(update_fields=["started_at"])
        return found


def mine(claimed: PdfOcr):
    """The row as this run claimed it; none when the file was deleted meanwhile, or another
    run took over a claim it thought dead."""
    return PdfOcr.objects.filter(
        pk=claimed.pk, state=PdfOcr.State.WAITING, started_at=claimed.started_at
    )


def settle(claimed: PdfOcr, read: Path) -> None:
    """Keeps the bytes the service answered with, unless they hold no text the file lacked."""
    try:
        texts = pdf.texts(read)
    except (Unreadable, TooLarge) as error:
        raise Failed(f"the answer cannot be opened: {error!r}") from error
    with transaction.atomic():
        held = mine(claimed).select_for_update(no_key=True).first()
        if held is None:
            return
        text = BlobText.objects.get(blob_id=held.blob_id)
        if len(texts) != text.page_count:
            raise Failed(f"the answer has {len(texts)} pages of {text.page_count}")
        found = [(number, page) for number, page in enumerate(texts, start=1) if page.strip()]
        if len(found) > text.pages.count():
            try:
                with read.open("rb") as stream:
                    held.readable = store.put(stream)
            except store.TooLarge:
                raise Failed("the answer is larger than BLOB_MAX_BYTES") from None
            text.pages.all().delete()
            BlobPage.objects.bulk_create(
                BlobPage(source=text, number=number, text=page) for number, page in found
            )
        held.state = PdfOcr.State.DONE
        held.finished_at = timezone.now()
        held.save()


def finish(claimed: PdfOcr, state: PdfOcr.State, reason: str) -> None:
    mine(claimed).update(state=state, reason=reason, finished_at=timezone.now())


def release(claimed: PdfOcr) -> None:
    mine(claimed).update(started_at=None)


async def asked(source: Path, target: Path) -> None:
    """Has the service read the file at `source` and writes its answer to `target`."""
    # Over anyio rather than urllib in a thread: a thread blocked for the minutes a long file
    # takes would hold the server's shutdown until it is read.
    address = urlsplit(settings.OCR_URL)
    try:
        with anyio.fail_after(TIMEOUT):
            async with await anyio.connect_tcp(address.hostname, address.port) as stream:
                await stream.send(
                    f"POST /ocr HTTP/1.1\r\nHost: {address.hostname}\r\n"
                    f"Content-Length: {source.stat().st_size}\r\nConnection: close\r\n\r\n".encode()
                )
                async with await anyio.open_file(source, "rb") as file:
                    while chunk := await file.read(CHUNK):
                        await stream.send(chunk)
                answer = BufferedByteReceiveStream(stream)
                head = (await answer.receive_until(b"\r\n\r\n", HEAD)).decode("latin-1")
                status, *lines = head.split("\r\n")
                fields = {
                    name.strip().lower(): value.strip()
                    for name, _, value in (line.partition(":") for line in lines)
                }
                code, length = int(status.split()[1]), int(fields["content-length"])
                if code != 200:
                    said = (await answer.receive_exactly(length)).decode(errors="replace")
                    if code == 409:
                        raise Declined(said)
                    if code == 422:
                        raise Failed(said)
                    raise Unavailable(f"{settings.OCR_URL} answered {code}: {said}")
                async with await anyio.open_file(target, "wb") as written:
                    while length:
                        chunk = await answer.receive(min(CHUNK, length))
                        await written.write(chunk)
                        length -= len(chunk)
    except (
        OSError,
        TimeoutError,
        ValueError,
        IndexError,
        KeyError,
        anyio.EndOfStream,
        anyio.IncompleteRead,
        anyio.DelimiterNotFound,
        anyio.BrokenResourceError,
    ) as error:
        raise Unavailable(settings.OCR_URL) from error


async def recognise_next() -> bool:
    """Reads one queued file; False when none is waiting."""
    claimed = await database(claim, own_thread=True)()
    if claimed is None:
        return False
    try:
        with tempfile.TemporaryDirectory() as work:
            read = Path(work) / "read.pdf"
            await asked(store.path_of(claimed.blob_id), read)
            await database(settle, own_thread=True)(claimed, read)
    except Declined as declined:
        await database(finish, own_thread=True)(claimed, PdfOcr.State.REFUSED, str(declined))
    except Failed as failure:
        log.error("ocr: %s could not be read: %s", claimed.blob_id, failure)
        await database(finish, own_thread=True)(claimed, PdfOcr.State.FAILED, str(failure))
    except BaseException:
        with CancelScope(shield=True):
            await database(release, own_thread=True)(claimed)
        raise
    return True


async def recognise() -> None:
    """Reads files while the server runs: as soon as one is queued, and in a sweep every
    SEARCH_SWEEP for whatever a lost notification or an unavailable service left."""
    await drain(CHANNEL, recognise_next, settings.SEARCH_SWEEP, log)
