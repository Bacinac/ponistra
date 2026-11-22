"""A zip written as it is sent: each entry's bytes leave as they are read, the archive assembled
neither on disk nor whole in memory (VD5). Documents, a location on the network and a project of
the workspace each walk their own tree and hand its entries here."""

import asyncio
import re
import zipfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import PurePosixPath

from django.utils import timezone
from django.utils.http import content_disposition_header

UNSAFE = re.compile(r'[\x00-\x1f/\\:*?"<>|]')
# Already compressed, so deflating them again costs time and gains nothing.
PACKED = {
    "zip", "7z", "rar", "gz", "tgz", "bz2", "xz", "zst", "lz4", "cab", "jar", "apk",
    "docx", "docm", "xlsx", "xlsm", "pptx", "pptm", "odt", "ods", "odp", "epub", "ponx",
    "jpg", "jpeg", "png", "gif", "webp", "avif", "heic", "mp3", "m4a", "ogg", "oga", "flac",
    "mp4", "m4v", "mov", "webm", "mkv", "avi", "pdf",
}  # fmt: skip
# Without the zip64 extra an entry holds at most 4 GiB; one that might grow past it while read
# from a server that still writes it carries the extra from the start.
ZIP64_FROM = 2**31
# The earliest moment a zip's DOS time holds.
EARLIEST = (1980, 1, 1, 0, 0, 0)


class _Sink:
    """What the zip writes, kept until it is sent; it has no `tell`, so the zip writes each
    entry's sizes after its bytes."""

    def __init__(self):
        self.parts: list[bytes] = []

    def write(self, data) -> int:
        self.parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass


def _stamp(modified: datetime | None) -> tuple[int, int, int, int, int, int]:
    if modified is None:
        modified = timezone.now()
    if timezone.is_naive(modified):
        modified = modified.replace(tzinfo=UTC)
    local = timezone.localtime(modified)
    return max(EARLIEST, local.timetuple()[:6])


def zip_name(title: str) -> str:
    """The name the browser saves the zip under."""
    return f"{UNSAFE.sub('_', title).strip(' .') or 'Ponistra'}.zip"


def zip_headers(title: str) -> dict:
    return {
        "Content-Disposition": content_disposition_header(True, zip_name(title)),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }


class Zipped:
    def __init__(self):
        self._sink = _Sink()
        self._zip = zipfile.ZipFile(self._sink, "w", allowZip64=True)
        self._taken: set[str] = set()

    def sent(self) -> bytes:
        """What was written since it was last sent."""
        written = b"".join(self._sink.parts)
        self._sink.parts.clear()
        return written

    def named(self, folder: str, title: str) -> str:
        """A path for the entry below the folder, safe on every system it is unpacked on and not
        yet taken there, whatever the case of its letters."""
        clean = UNSAFE.sub("_", title).strip(" ").rstrip(".")[:200] or "_"
        stem, suffix = (clean, "") if clean.startswith(".") else _split(clean)
        candidate, number = clean, 1
        while f"{folder}/{candidate}".lower() in self._taken:
            number += 1
            candidate = f"{stem} ({number}){suffix}"
        path = f"{folder}/{candidate}" if folder else candidate
        self._taken.add(f"{folder}/{candidate}".lower())
        return path

    def folder(self, path: str, modified: datetime | None = None) -> None:
        info = zipfile.ZipInfo(f"{path}/", _stamp(modified))
        info.external_attr = 0o40755 << 16 | 0x10
        self._zip.writestr(info, b"")

    def opened(self, path: str, modified: datetime | None, size: int | None):
        """The entry to write the file's bytes into, deflated unless they are compressed."""
        info = zipfile.ZipInfo(path, _stamp(modified))
        info.external_attr = 0o100644 << 16
        extension = PurePosixPath(path).suffix.lower().lstrip(".")
        info.compress_type = zipfile.ZIP_STORED if extension in PACKED else zipfile.ZIP_DEFLATED
        info.file_size = size or 0
        return self._zip.open(info, "w", force_zip64=size is None or size >= ZIP64_FROM)

    def closed(self) -> bytes:
        self._zip.close()
        return self.sent()


def _split(name: str) -> tuple[str, str]:
    stem, dot, extension = name.rpartition(".")
    return (stem, f".{extension}") if dot and stem else (name, "")


async def written(
    zipped: Zipped, path: str, modified: datetime | None, size: int | None, parts
) -> AsyncIterator[bytes]:
    """One file's entry, its bytes compressed off the event loop and sent as each part is."""
    entry = zipped.opened(path, modified, size)
    try:
        async for part in parts:
            await asyncio.to_thread(entry.write, part)
            if sent := zipped.sent():
                yield sent
    finally:
        await asyncio.to_thread(entry.close)
    if sent := zipped.sent():
        yield sent
