import asyncio
import re
import shutil

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, HttpResponseNotModified, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header, parse_etags

from apps.core.api import Refused, api, body
from apps.core.asyncdb import database

from . import store
from .models import Blob, Upload

RANGE = re.compile(r"bytes=(\d{0,19})-(\d{0,19})")


class Unsatisfiable(Exception):
    pass


def describe(blob: Blob) -> dict:
    return {"sha256": blob.sha256, "size": blob.size, "media_type": blob.media_type}


def described(upload: Upload) -> dict:
    return {
        "id": upload.pk,
        "size": upload.size,
        "received": upload.received,
        "chunk": settings.UPLOAD_CHUNK_BYTES,
        "blob": describe(upload.blob) if upload.blob else None,
    }


def roomy(size: int) -> None:
    if shutil.disk_usage(store.root()).free < size + settings.UPLOAD_RESERVE_BYTES:
        raise Refused(507, "no_room")


@api("POST", visitors=True)
async def uploads(request):
    """A file to upload in pieces of `chunk` bytes, each sent at the offset it starts at."""
    return await begun(request, request.user)


async def begun(request, user) -> JsonResponse:
    """An upload the user holds, which someone asked for files by a link uploads in their name."""
    size = body(request).get("size")
    if type(size) is not int or size < 0:
        raise Refused(400, "invalid_size")
    if size > settings.BLOB_MAX_BYTES:
        raise Refused(413, "too_large")
    roomy(size)
    made = await database(Upload.objects.create)(user=user, size=size, touched_at=timezone.now())
    return JsonResponse(described(made), status=201)


@api("GET", "PUT", visitors=True)
async def upload(request, pk):
    """Where the upload has got to; with PUT the piece the request brings at the offset its
    Upload-Offset names, which must be what the upload has received, and the last one makes
    the file a Blob. The bytes are written and hashed off the shared thread, which a file of
    several GB would hold for everyone."""
    return await received(request, request.user, pk)


async def received(request, user, pk) -> JsonResponse:
    found = await database(_found)(user, pk)
    if request.method == "GET" or found.blob:
        return JsonResponse(described(found))
    try:
        offset = int(request.headers.get("Upload-Offset", ""))
    except ValueError:
        raise Refused(400, "invalid_offset") from None
    if offset != found.received:
        raise Refused(409, "wrong_offset")
    most = min(settings.UPLOAD_CHUNK_BYTES, found.size - offset)
    roomy(most)
    part = store.part_of(pk)
    try:
        count = await asyncio.to_thread(store.written, request, part, offset, most)
    except store.TooLarge:
        raise Refused(413, "too_large") from None
    advanced = await database(_advanced)(user, pk, offset, count)
    if advanced.received < advanced.size or advanced.blob:
        return JsonResponse(described(advanced))
    try:
        sha256, head = await asyncio.to_thread(store.hashed, part, advanced.size)
    except FileNotFoundError:
        # A retry of the last piece, which the first one moved into place meanwhile.
        sha256 = head = None
    return JsonResponse(described(await database(_adopted)(user, pk, sha256, head)))


def _found(user, pk, *, locked: bool = False) -> Upload:
    found = Upload.objects.select_related("blob")
    if locked:
        found = found.select_for_update(of=("self",))
    if (upload := found.filter(pk=pk, user=user).first()) is None:
        raise Refused(404, "not_found")
    return upload


def _advanced(user, pk, offset: int, count: int) -> Upload:
    # Only from the offset it was written at: a retry of the same piece, written meanwhile with
    # the same bytes, leaves the upload where the first one took it.
    Upload.objects.filter(pk=pk, received=offset).update(
        received=offset + count, touched_at=timezone.now()
    )
    return _found(user, pk)


def _adopted(user, pk, sha256: str | None, head: bytes | None) -> Upload:
    with transaction.atomic():
        upload = _found(user, pk, locked=True)
        if upload.blob is None:
            if sha256 is None:
                raise OSError(f"upload {pk} lost its bytes before it was kept")
            upload.blob = store.adopt(store.part_of(pk), sha256, upload.size, head)
            upload.save(update_fields=["blob"])
        return upload


def byte_range(header: str, size: int) -> tuple[int, int] | None:
    """The first and last byte a single range asks for; None serves the whole file."""
    match = RANGE.fullmatch(header.strip())
    if match is None or match.groups() == ("", ""):
        return None
    first, last = match.groups()
    if not first:
        if int(last) == 0 or size == 0:
            raise Unsatisfiable
        return max(size - int(last), 0), size - 1
    if last and int(last) < int(first):
        return None
    if int(first) >= size:
        raise Unsatisfiable
    return int(first), min(int(last), size - 1) if last else size - 1


async def chunks(path, start: int, length: int):
    with path.open("rb") as file:
        file.seek(start)
        while length > 0:
            chunk = await asyncio.to_thread(file.read, min(store.CHUNK, length))
            if not chunk:
                raise OSError(f"{file.name} ended {length} bytes early")
            length -= len(chunk)
            yield chunk


def serve(
    request, blob: Blob, filename: str, *, shown: bool = True, media_type: str | None = None
) -> HttpResponse:
    """The blob's bytes, or the one byte range pdf.js asks for, as the type its name tells
    where it is given; saved rather than shown when asked to be, or when it may not be shown."""
    etag = f'"{blob.sha256}"'
    if etag in parse_etags(request.headers.get("If-None-Match", "")):
        return HttpResponseNotModified(headers={"ETag": etag})
    span = None
    if "Range" in request.headers and request.headers.get("If-Range", etag) == etag:
        try:
            span = byte_range(request.headers["Range"], blob.size)
        except Unsatisfiable:
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{blob.size}"})
    path = store.path_of(blob.sha256)
    if (found := path.stat().st_size) != blob.size:
        raise OSError(f"{path} holds {found} bytes, its row says {blob.size}")
    start, end = span or (0, blob.size - 1)
    response = StreamingHttpResponse(
        chunks(path, start, end - start + 1),
        status=206 if span else 200,
        content_type=media_type or blob.media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-cache",
            "Content-Disposition": content_disposition_header(
                not shown or request.GET.get("download") == "1", filename
            ),
            "Content-Length": str(end - start + 1),
            "ETag": etag,
        },
    )
    if span:
        response["Content-Range"] = f"bytes {start}-{end}/{blob.size}"
    return response
