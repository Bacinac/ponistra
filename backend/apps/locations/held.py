"""What a file on another server shows of what it holds (VD4), read from a copy of it in a
temporary file as `apps.reader.shown` reads a file of Documents: a location on the network's
(D54) and a project of the workspace's (PJ6). Its address carries the path as one segment, so
that what it shows is served below it."""

import asyncio
import base64
import binascii
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import BinaryIO

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils.http import content_disposition_header

from apps.blobs import store, text
from apps.core.api import Refused
from apps.imports.reading import TooLarge, Unreadable
from apps.reader import shown
from apps.reader.archives import Locked
from apps.reader.client import Unavailable

# A file larger than this is not copied to be read: what it holds is not shown.
COPIED_UP_TO = 512 * 1024 * 1024
FAILURES = (Locked, TooLarge, Unavailable, Unreadable)

Fetch = Callable[[BinaryIO], Awaitable[None]]


def path_of(token: str) -> str:
    """The path a segment of the address carries, base64url without its padding."""
    try:
        return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
    except binascii.Error, UnicodeDecodeError:
        raise Refused(400, "invalid_path") from None


def too_large(size: int | None) -> None:
    if size is not None and size > COPIED_UP_TO:
        raise Refused(413, "too_large")


async def written(kept: BinaryIO, parts) -> None:
    """The parts into the copy, refused once they pass the copy's ceiling."""
    copied = 0
    async for part in parts:
        copied += len(part)
        too_large(copied)
        await asyncio.to_thread(kept.write, part)


async def of(request, name: str, fetch: Fetch) -> JsonResponse:
    """What the file shows; POSTed with the password an archive asks for."""
    # Imported here: Documents' views import the workspace's, which import this.
    from apps.reader.views import _password, _refused

    password = _password(request)
    with tempfile.NamedTemporaryFile() as kept:
        await fetch(kept)
        await asyncio.to_thread(kept.flush)
        try:
            found = await asyncio.to_thread(
                shown.of, Path(kept.name), name, f"{request.path}/", None, password
            )
        except FAILURES as error:
            raise _refused(error) from None
    if found is None:
        raise Refused(404, "not_found")
    return JsonResponse(found)


async def part(request, name: str, number: str, fetch: Fetch) -> HttpResponse:
    """One part of what the file shows: an archive's entry or a message's attachment, saved; a
    picture the browser cannot show, drawn whole."""
    from apps.reader.views import _password, _refused

    password = _password(request)
    with tempfile.NamedTemporaryFile() as kept:
        await fetch(kept)
        await asyncio.to_thread(kept.flush)
        try:
            found = await asyncio.to_thread(
                shown.part, Path(kept.name), name, number, None, password
            )
        except FAILURES as error:
            raise _refused(error) from None
    if found is None:
        raise Refused(404, "not_found")
    headers = {
        "Content-Disposition": content_disposition_header(not found.shown, found.name),
        "Cache-Control": "private, no-cache",
        # Nothing a file holds runs as a page of ours: an HTML attachment is only saved.
        "Content-Security-Policy": "sandbox",
        "X-Content-Type-Options": "nosniff",
    }
    if isinstance(found.data, bytes):
        return HttpResponse(found.data, content_type=found.media_type, headers=headers)
    return StreamingHttpResponse(
        store.streamed(found.data), content_type=found.media_type, headers=headers
    )


def _most(request) -> int:
    from apps.documents.views import TEXT_SHOWN

    try:
        most = int(request.GET.get("most", TEXT_SHOWN))
    except ValueError:
        raise Refused(400, "invalid_most") from None
    if not 1 <= most <= TEXT_SHOWN:
        raise Refused(400, "invalid_most")
    return most


async def text_of(request, fetch: Fetch) -> JsonResponse:
    """At most `most` bytes of a text file decoded, as a text file of Documents is read."""
    most = _most(request)
    with tempfile.NamedTemporaryFile() as kept:
        await fetch(kept)
        await asyncio.to_thread(kept.flush)
        try:
            found = await asyncio.to_thread(text.read_file, Path(kept.name), most)
        except text.NotText:
            raise Refused(422, "not_text") from None
    return JsonResponse(
        {"text": found.text, "encoding": found.encoding, "truncated": found.truncated}
    )
