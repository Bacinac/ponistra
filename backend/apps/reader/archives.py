"""An archive's entries, one entry's bytes and all its files as a tar, read by libarchive or
7-Zip in the converter service (D23), which reaches nothing but the backend. A password goes with
the request and is never kept."""

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
# The converter answers once it has packed the whole archive, as large as BLOB_MAX_BYTES.
TIMEOUT_ALL = 3600


class Locked(Exception):
    """The archive asks for a password: none was given, or the one given is wrong."""


def _asked(path: Path, address: str, password: str | None, timeout: int = TIMEOUT):
    size = path.stat().st_size
    if size > settings.BLOB_MAX_BYTES:
        raise TooLarge(f"an archive of {size} bytes")
    headers = {"Content-Length": str(size)}
    if password:
        headers["Archive-Password"] = quote(password)
    request = urllib.request.Request(
        f"{settings.CONVERTER_URL}{address}", data=path.open("rb"), headers=headers, method="POST"
    )
    try:
        with request.data:
            return urllib.request.urlopen(request, timeout=timeout)
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
    thousand, how many it holds, and `raw` for one compressed file that holds no archive."""
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
    return _kept(response, number)


def packed(path: Path, name: str, password: str | None = None) -> BinaryIO:
    """Every file among the first ten thousand entries as an uncompressed pax tar, each under its
    path in the archive, in a file of its own at its start, which goes once closed. A zip's times
    are the wall clock it was packed on, read as UTC."""
    response = _asked(path, f"/archive/all?name={quote(name)}", password, TIMEOUT_ALL)
    return _kept(response, "all")[1]


def _kept(response, number: str) -> tuple[str, BinaryIO]:
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
