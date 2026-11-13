"""Files other than docx, xlsx and pptx made one of them by LibreOffice in the converter
service, and every file read by the reader service: both reach nothing but the backend."""

import shutil
import tempfile
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path

from django.conf import settings

from apps.blobs import store
from apps.blobs.models import Blob
from apps.reader import client
from apps.reader.client import Unavailable

from . import laying, reading
from .formats import EXTENSIONS, OPEN_XML, read_as

TIMEOUT = 180


@contextmanager
def converted(source: Blob, target: str) -> Iterator[Path]:
    path = store.path_of(source.sha256)
    if source.media_type in OPEN_XML[target]:
        yield path
        return
    kind = EXTENSIONS[source.media_type]
    request = urllib.request.Request(
        f"{settings.CONVERTER_URL}/{target}/{kind}",
        data=path.open("rb"),
        headers={"Content-Length": str(path.stat().st_size)},
        method="POST",
    )
    with tempfile.NamedTemporaryFile(suffix=f".{target}") as found:
        try:
            with request.data, urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                shutil.copyfileobj(response, found)
        except urllib.error.HTTPError as error:
            if error.code == 413:
                raise reading.TooLarge from error
            if error.code < 500:
                raise reading.Unreadable from error
            raise Unavailable from error
        except OSError as error:
            raise Unavailable from error
        found.flush()
        yield Path(found.name)


@contextmanager
def _sent(source: Blob) -> Iterator[tuple[Path, str]]:
    """The file as the reader takes it, and the kind it reads it as."""
    if source.media_type == store.TEXT:
        yield store.path_of(source.sha256), "csv"
        return
    target = read_as(source.media_type)
    with converted(source, target) as path:
        yield path, target


def pages(source: Blob, locale: str) -> list[str]:
    """The file's text in pages, as search keeps it."""
    with _sent(source) as (path, target):
        return client.ask("import_pages", path, target=target, locale=locale)


def read(
    source: Blob, locale: str, formats: dict[str, list[dict]] | None = None
) -> reading.Imported:
    """The file's tabs; a spreadsheet's cells typed as the document's locale types them. A file
    whose rows come after the document stands keeps the reader's answer open until `rest`."""
    with _sent(source) as (path, target):
        answer = client.opened("import", path, target=target, locale=locale, formats=formats)
    try:
        found = answer.next()
        if found is None or not isinstance(found.get("imported"), reading.Imported):
            raise reading.Unreadable("the reader sent no document")
        imported = found["imported"]
        if not found["streams"]:
            answer.finish()
            answer.close()
            return imported
    except BaseException:
        answer.close()
        raise
    imported.rest = partial(_rest, answer)
    return imported


def _rest(answer: client.Answer, document) -> set[str]:
    """Writes the rows the reader sends; the tables it sent them for."""
    try:
        laying.begin()
        laying.written(document, iter(answer.next, None))
        ended = answer.value
    finally:
        answer.close()
    if "report" in ended:
        document.imported = ended["report"]
        document.save(update_fields=["imported"])
    return set(ended["written"])
