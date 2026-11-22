"""An archive's entries and one entry's bytes, read by libarchive or 7-Zip in the converter
service (D23), which reaches nothing but the backend. A password goes with the request and is
never kept."""

import http.client
import json
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote, unquote

from django.conf import settings

from apps.imports.reading import TooLarge, Unreadable

from .client import Unavailable

TIMEOUT = 180
# What the converter keeps in its memory while it reads one.
LARGEST = 1024 * 1024 * 1024


class Locked(Exception):
    """The archive asks for a password: none was given, or the one given is wrong."""


def _asked(path: Path, address: str, password: str | None):
    size = path.stat().st_size
    if size > LARGEST:
        raise TooLarge(f"an archive of {size} bytes")
    headers = {"Content-Length": str(size)}
    if password:
        headers["Archive-Password"] = quote(password)
    request = urllib.request.Request(
        f"{settings.CONVERTER_URL}{address}", data=path.open("rb"), headers=headers, method="POST"
    )
    try:
        with request.data:
            return urllib.request.urlopen(request, timeout=TIMEOUT)
    except urllib.error.HTTPError as error:
        if error.code == 409:
            raise Locked from None
        if error.code == 413:
            raise TooLarge from error
        if error.code < 500:
            raise Unreadable(error.read()[:300].decode(errors="replace")) from error
        raise Unavailable from error
    except OSError as error:
        raise Unavailable from error


def listed(path: Path, name: str, password: str | None = None) -> dict:
    """The entries, each {n, path, size, modified, folder}, at most the converter's ten
    thousand, and how many it holds."""
    with _asked(path, f"/archive?name={quote(name)}", password) as response:
        return json.load(response)


def entry(
    path: Path, name: str, number: str, password: str | None = None
) -> tuple[str, BinaryIO] | None:
    """Entry `number`'s name and its bytes in a file of their own, which goes once closed."""
    if not number.isdigit():
        return None
    try:
        response = _asked(path, f"/archive/{number}?name={quote(name)}", password)
    except Unreadable as error:
        if isinstance(error.__cause__, urllib.error.HTTPError) and error.__cause__.code == 404:
            return None
        raise
    found = tempfile.TemporaryFile()
    try:
        with response:
            shutil.copyfileobj(response, found, 1 << 20)
            told = int(response.headers["Content-Length"])
            named = unquote(response.headers.get("Entry-Name") or "") or number
    except http.client.IncompleteRead as error:
        found.close()
        raise Unreadable(f"the converter stopped sending: {error!r}") from None
    except BaseException:
        found.close()
        raise
    if found.tell() != told:
        found.close()
        raise Unreadable(f"the converter sent {found.tell()} of {told} bytes")
    found.seek(0)
    return named, found
