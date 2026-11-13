import asyncio
import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import timedelta
from logging import getLogger
from pathlib import Path
from typing import IO

import olefile
from django.conf import settings
from django.db import connection, models, transaction
from django.utils import timezone
from lxml import etree

from apps.core.asyncdb import database, drain, notify

from .models import Blob, Upload

log = getLogger(__name__)

CHANNEL = "blobs"

CHUNK = 1024 * 1024
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ODT = "application/vnd.oasis.opendocument.text"
DOC = "application/msword"
RTF = "application/rtf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ODS = "application/vnd.oasis.opendocument.spreadsheet"
XLS = "application/vnd.ms-excel"
DOCM = "application/vnd.ms-word.document.macroEnabled.12"
DOTX = "application/vnd.openxmlformats-officedocument.wordprocessingml.template"
DOTM = "application/vnd.ms-word.template.macroEnabled.12"
XLSM = "application/vnd.ms-excel.sheet.macroEnabled.12"
XLTX = "application/vnd.openxmlformats-officedocument.spreadsheetml.template"
XLTM = "application/vnd.ms-excel.template.macroEnabled.12"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PPTM = "application/vnd.ms-powerpoint.presentation.macroEnabled.12"
POTX = "application/vnd.openxmlformats-officedocument.presentationml.template"
POTM = "application/vnd.ms-powerpoint.template.macroEnabled.12"
PPSX = "application/vnd.openxmlformats-officedocument.presentationml.slideshow"
PPSM = "application/vnd.ms-powerpoint.slideshow.macroEnabled.12"
ODP = "application/vnd.oasis.opendocument.presentation"
PPT = "application/vnd.ms-powerpoint"
PONX = "application/vnd.ponistra.document+zip"
# Bytes of no kind PONISTRA knows, whose kind only their name tells.
UNKNOWN = "application/octet-stream"
TEXT = "text/plain"
HTML = "text/html"
# A page of HTML says so before anything else, but for comments: a fragment is only text.
PAGE = re.compile(rb"(?:<!--.*?-->\s*)*<(?:!doctype\s+html|html)[\s>]", re.IGNORECASE | re.DOTALL)
# The bookmarks a browser exports, in the format Netscape gave them; no registered type names it.
BOOKMARKS = "text/x-netscape-bookmarks"
# How much of a file its kind is told by: a text file's first control character may lie far in.
SAMPLE = 64 * 1024
CONTROLS = bytes(set(range(32)) - {9, 10, 12, 13, 27})
MP4 = {
    b"mp41",
    b"mp42",
    b"mp71",
    b"avc1",
    b"M4V ",
    b"M4VH",
    b"M4VP",
    b"dash",
    b"MSNV",
    b"mmp4",
    b"f4v ",
    b"XAVC",
}
IMAGES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/svg+xml": "svg",
}
VARIANTS = {
    "application/vnd.ms-word.document.macroEnabled.main+xml": DOCM,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml": DOTX,
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml": DOTM,
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml": XLSM,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml": XLTX,
    "application/vnd.ms-excel.template.macroEnabled.main+xml": XLTM,
    "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml": PPTM,
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml": POTX,
    "application/vnd.ms-powerpoint.template.macroEnabled.main+xml": POTM,
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml": PPSX,
    "application/vnd.ms-powerpoint.slideshow.macroEnabled.main+xml": PPSM,
}
TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# Uploads hold it shared until they commit, a snapshot while it reads the files, and
# collect() holds it exclusively, so under collect() a file without a row can only be
# left by an interrupted upload, and a snapshot finds every file its database names.
LOCK = 0x5C21B10B
# The bytes nothing refers to any more wait in dead/ as long as a restore reaches back, since the
# database as it was at any moment of it may name them.
KEPT = timedelta(days=7)


class TooLarge(Exception):
    pass


def root() -> Path:
    return Path(settings.BLOB_ROOT)


def path_of(sha256: str) -> Path:
    return root() / sha256[:2] / sha256[2:4] / sha256


def dead() -> Path:
    return root() / "dead"


def revive(sha256: str) -> bool:
    """Puts the bytes back in place from dead/, where a database restored to an earlier moment
    still names them."""
    path = path_of(sha256)
    for found in sorted(dead().glob(f"*/{sha256}"), reverse=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        found.rename(path)
        return True
    return path.exists()


def dead_bytes() -> int:
    return sum(path.stat().st_size for path in dead().glob("*/*"))


def sniff(sample: bytes) -> str:
    head = sample[:1024]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    if media := sniff_media(head):
        return media
    if b"%PDF-" in head:
        return PDF
    if head.startswith(b"{\\rtf"):
        return RTF
    text = head.lstrip(b"\xef\xbb\xbf").lstrip()
    if PAGE.match(text) and is_text(sample):
        return HTML
    if b"<svg" in head.lower():
        return "image/svg+xml"
    if text.startswith(b"BEGIN:VCALENDAR"):
        return "text/calendar"
    if text.startswith(b"BEGIN:VCARD"):
        return "text/vcard"
    if text[:40].upper().startswith(b"<!DOCTYPE NETSCAPE-BOOKMARK-FILE-1>"):
        return BOOKMARKS
    return TEXT if is_text(sample) else UNKNOWN


def sniff_media(head: bytes) -> str | None:
    """Audio and video in the containers a browser plays."""
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio/mp4"
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4" if brand.startswith(b"iso") or brand in MP4 else None
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm" if b"webm" in head[:64] else "video/x-matroska"
    if head.startswith(b"OggS"):
        voiced = any(codec in head for codec in (b"OpusHead", b"\x01vorbis", b"\x7fFLAC"))
        return "audio/ogg" if voiced else None
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"ID3"):
        return "audio/mpeg"
    if len(head) > 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0:
        # A frame header: AAC's ADTS has no layer, MPEG audio's names layer II or III (layer I's
        # header is a UTF-16 byte order mark), a bit rate and a sampling rate.
        if head[1] & 0xF6 == 0xF0:
            return "audio/aac"
        if (
            head[1] & 0x06 in (0x02, 0x04)
            and head[1] & 0x18 != 0x08
            and head[2] >> 4 != 0xF
            and head[2] & 0x0C != 0x0C
        ):
            return "audio/mpeg"
    return None


def is_text(sample: bytes) -> bool:
    """Bytes that read as text in some code page: UTF-16 or UTF-32 by its byte order mark, else
    no NUL and hardly a control character."""
    if sample.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")):
        return True
    if not sample or b"\0" in sample:
        return False
    return (len(sample) - len(sample.translate(None, CONTROLS))) * 100 <= len(sample)


def sniff_zip(path: Path) -> str | None:
    """An Office file is a zip, told apart by the part its kind cannot do without and its
    macro or template variant by that part's content type, an OpenDocument or PONISTRA file
    by the type it names first."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "mimetype" in names and archive.getinfo("mimetype").file_size < 100:
                named = archive.read("mimetype").decode("ascii", "replace").strip()
                return named if named in (ODT, ODS, ODP, PONX) else None
            for part, plain in (
                ("word/document.xml", DOCX),
                ("xl/workbook.xml", XLSX),
                ("ppt/presentation.xml", PPTX),
            ):
                if part in names:
                    return VARIANTS.get(_content_type(archive, part), plain)
    except zipfile.BadZipFile:
        return None
    return None


def _content_type(archive: zipfile.ZipFile, part: str) -> str | None:
    try:
        if archive.getinfo("[Content_Types].xml").file_size > 1024 * 1024:
            return None
        types = archive.read("[Content_Types].xml")
    except KeyError:
        return None
    # Here, not above: the models import this module, and the reader's client their schema.
    from apps.imports.reading import Unreadable
    from apps.reader import client

    try:
        return client.ask("content_type", types, part=part)
    except Unreadable:
        return None


def typed(path: Path, part: str) -> str | None:
    """The content type a package's [Content_Types].xml at `path` gives the part, in the reader
    (D51)."""
    try:
        types = etree.fromstring(path.read_bytes())
    except etree.XMLSyntaxError:
        return None
    for override in types.iter(f"{TYPES}Override"):
        if (override.get("PartName") or "").lower() == f"/{part}":
            return override.get("ContentType")
    return None


def sniff_ole(path: Path) -> str | None:
    """Word 97–2003 keeps its text in a stream of that name, Excel 97–2003 its sheets in
    one named Workbook, Excel 5 in Book, PowerPoint 97–2003 its slides in one named PowerPoint
    Document."""
    try:
        with olefile.OleFileIO(path) as container:
            if container.exists("WordDocument"):
                return DOC
            if container.exists("PowerPoint Document"):
                return PPT
            return XLS if container.exists("Workbook") or container.exists("Book") else None
    except OSError:
        return None


def put(stream) -> Blob:
    """Stores what the stream yields and returns its Blob; the same bytes give the same Blob."""
    incoming = root() / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    with transaction.atomic():
        shared()
        digest, size, head = hashlib.sha256(), 0, b""
        with tempfile.NamedTemporaryFile(dir=incoming, delete_on_close=False) as temp:
            while chunk := stream.read(CHUNK):
                size += len(chunk)
                if size > settings.BLOB_MAX_BYTES:
                    raise TooLarge
                head += chunk[: SAMPLE - len(head)]
                digest.update(chunk)
                temp.write(chunk)
            temp.flush()
            os.fsync(temp.fileno())
            return kept(Path(temp.name), digest.hexdigest(), size, head)


def part_of(upload) -> Path:
    return root() / "uploads" / str(upload)


def written(stream, path: Path, offset: int, most: int) -> int:
    """Writes what the stream yields into the file from offset on and returns how much it
    wrote, refusing more than most bytes."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        fsync_dir(path.parent)
    count = 0
    with path.open("r+b") as file:
        if (length := file.seek(0, os.SEEK_END)) < offset:
            raise OSError(f"{path} holds {length} bytes, its upload {offset}")
        file.seek(offset)
        while chunk := stream.read(CHUNK):
            count += len(chunk)
            if count > most:
                raise TooLarge
            file.write(chunk)
        file.flush()
        os.fsync(file.fileno())
    return count


def hashed(path: Path, size: int) -> tuple[str, bytes]:
    """The SHA-256 of the first size bytes of the file, and its head to sniff."""
    digest, head, left = hashlib.sha256(), b"", size
    with path.open("rb") as file:
        while left and (chunk := file.read(min(CHUNK, left))):
            left -= len(chunk)
            head += chunk[: SAMPLE - len(head)]
            digest.update(chunk)
    if left:
        raise OSError(f"{path} ended {left} bytes before its upload")
    return digest.hexdigest(), head


def adopt(path: Path, sha256: str, size: int, head: bytes) -> Blob:
    """Stores the file an upload wrote under BLOB_ROOT by moving it into place."""
    with transaction.atomic():
        shared()
        return kept(path, sha256, size, head)


def shared() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock_shared(%s)", [LOCK])


def kept(path: Path, sha256: str, size: int, head: bytes) -> Blob:
    target = path_of(sha256)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(path, target)
    # The rename must be on disk before the row commits, or a crash leaves a
    # row whose bytes are gone.
    fsync_dir(target.parent)
    media_type = sniff(head)
    if head.startswith(b"PK\x03\x04"):
        media_type = sniff_zip(target) or media_type
    elif head.startswith(OLE):
        media_type = sniff_ole(target) or media_type
    Blob.objects.bulk_create(
        [Blob(sha256=sha256, size=size, media_type=media_type, uploaded_at=timezone.now())],
        update_conflicts=True,
        unique_fields=["sha256"],
        # The same bytes always sniff the same, so this only corrects rows that an
        # older sniff typed.
        update_fields=["uploaded_at", "media_type"],
    )
    return Blob.objects.get(pk=sha256)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def unreferenced(blobs):
    # What is derived from the bytes, such as their extracted text, cascades with
    # them; a reference the database leaves alone keeps them, as it refuses their deletion.
    for relation in Blob._meta.related_objects:
        if relation.on_delete is models.DO_NOTHING:
            blobs = blobs.filter(**{f"{relation.name}__isnull": True})
    return blobs


@contextmanager
def exclusive():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK])


@contextmanager
def held():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock_shared(%s)", [LOCK])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock_shared(%s)", [LOCK])


def collect() -> None:
    """Moves the bytes nothing refers to any more into dead/, sparing uploads younger than
    BLOB_GRACE that are about to be referred to, deletes those dead for KEPT, what interrupted
    uploads left and uploads in pieces abandoned for UPLOAD_ABANDONED."""
    with exclusive():
        with transaction.atomic():
            stale = Blob.objects.filter(uploaded_at__lt=timezone.now() - settings.BLOB_GRACE)
            locked = unreferenced(stale).select_for_update(of=("self",))
            candidates = list(locked.values_list("pk", flat=True))
            # A reference created while the lock was awaited is visible only now.
            doomed = unreferenced(Blob.objects.filter(pk__in=candidates))
            Blob.objects.filter(pk__in=list(doomed.values_list("pk", flat=True))).delete()
        known = set(Blob.objects.values_list("pk", flat=True))
        today = timezone.localdate()
        for path in root().glob("??/??/*"):
            if path.name not in known:
                (dead() / today.isoformat()).mkdir(parents=True, exist_ok=True)
                path.rename(dead() / today.isoformat() / path.name)
        for day in dead().glob("*"):
            if day.name < (today - KEPT).isoformat():
                shutil.rmtree(day)
        for path in root().glob("incoming/*"):
            path.unlink()
        # A file goes by its own age, not by a row naming it: one begun after the rows were
        # read would look abandoned.
        abandoned = timezone.now() - settings.UPLOAD_ABANDONED
        Upload.objects.filter(touched_at__lt=abandoned).delete()
        for path in root().glob("uploads/*"):
            if path.stat().st_mtime < abandoned.timestamp():
                path.unlink()


def collect_later() -> None:
    """Has the collector run once the current transaction commits: it walks every file kept,
    which no request should wait for."""
    notify(CHANNEL)


def collected() -> bool:
    collect()
    return False


async def collecting() -> None:
    """Deletes the bytes nothing refers to while the server runs: as soon as something is
    purged, and in a sweep every BLOB_SWEEP for whatever a lost notification left."""
    await drain(CHANNEL, database(collected, own_thread=True), settings.BLOB_SWEEP, log)


async def streamed(file: IO[bytes]):
    """The file in chunks, closed at the end, for a response that holds none of it in memory."""
    with file:
        while chunk := await asyncio.to_thread(file.read, CHUNK):
            yield chunk
