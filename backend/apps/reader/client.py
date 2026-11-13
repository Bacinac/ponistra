"""The backend's side of the reader: a file sent, its lines read back, a failure the reading
reports raised as the exception the backend knows it by."""

import http.client
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

from apps.imports.reading import TooLarge, Unreadable

from . import reads, wire

# A reading's lines come as it reads, a large workbook's for as long as its rows take to write.
TIMEOUT = 900


class Unavailable(Exception):
    """A service that reads or converts files did not answer."""


class Answer:
    """A reading's lines as they come: `next()` gives each line it sends before the end and
    None at the end, whose value is then `value`; each file it sends is kept in `files` until
    the answer closes."""

    def __init__(self, connection: http.client.HTTPConnection, response):
        self.connection, self.response = connection, response
        self.files: list[Path] = []
        self.value = None
        self.ended = False
        self._held: list = []

    def next(self) -> dict | None:
        if self.ended:
            return None
        while True:
            try:
                raw = self.response.readline()
            except (OSError, http.client.HTTPException) as error:
                raise Unavailable("the reader stopped answering") from error
            if not raw:
                raise Unavailable("the reader stopped answering")
            if raw == b"\n":
                continue
            try:
                found = wire.parsed(raw)
            except ValueError as error:
                raise Unreadable(f"the reader sent {raw[:80]!r}") from error
            if not isinstance(found, dict):
                raise Unreadable(f"the reader sent {raw[:80]!r}")
            if "file" in found:
                self._take(found["file"])
                continue
            if "ran" in found:
                # Only a test's process sends what it ran, and only pytest loads the map.
                sys.modules["apps.core.checkmap"].noted(found["ran"])
                continue
            if "error" in found:
                self.ended = True
                raise reads.raised(found["error"], found.get("detail", ""))
            if "end" in found:
                self.ended, self.value = True, found["end"]
                return None
            return found

    def finish(self):
        """The end's value, each line before it passed over."""
        while self.next() is not None:
            pass
        return self.value

    def _take(self, size: int) -> None:
        file = tempfile.NamedTemporaryFile(delete=False)
        try:
            with file:
                left = size
                while left > 0:
                    chunk = self.response.read(min(left, 1 << 20))
                    if not chunk:
                        raise Unavailable("the reader stopped sending a file")
                    file.write(chunk)
                    left -= len(chunk)
        except BaseException:
            Path(file.name).unlink(missing_ok=True)
            raise
        self.files.append(Path(file.name))

    def close(self) -> None:
        self.connection.close()
        for path in self.files:
            path.unlink(missing_ok=True)
        self.files.clear()


def opened(kind: str, *files: Path | bytes, **head) -> Answer:
    """The answer of the reading `kind` of the files given, each a path or bytes, given the
    head's values; it is the caller's to close."""
    sizes = [each.stat().st_size if isinstance(each, Path) else len(each) for each in files]
    told = wire.line({**head, "sizes": sizes})
    prefix = f"{len(told)}\n".encode() + told
    place = urlsplit(settings.READER_URL)
    connection = http.client.HTTPConnection(place.hostname, place.port, timeout=TIMEOUT)
    try:
        connection.putrequest("POST", f"/{kind}")
        connection.putheader("Content-Length", str(len(prefix) + sum(sizes)))
        connection.endheaders()
        connection.send(prefix)
        for each in files:
            if isinstance(each, Path):
                with each.open("rb") as file:
                    shutil.copyfileobj(file, _Sent(connection), 1 << 20)
            else:
                connection.send(each)
        response = connection.getresponse()
    except OSError as error:
        connection.close()
        raise Unavailable(f"{settings.READER_URL}: {error!r}") from error
    if response.status == 413:
        connection.close()
        raise TooLarge(f"larger than the reader takes: {sum(sizes)} bytes")
    if response.status != 200:
        connection.close()
        raise RuntimeError(f"the reader answered {response.status} to {kind}")
    return Answer(connection, response)


class _Sent:
    def __init__(self, connection: http.client.HTTPConnection):
        self.connection = connection

    def write(self, chunk: bytes) -> None:
        self.connection.send(chunk)


@contextmanager
def answered(kind: str, *files: Path | bytes, **head) -> Iterator[Answer]:
    answer = opened(kind, *files, **head)
    try:
        yield answer
    finally:
        answer.close()


def ask(kind: str, *files: Path | bytes, **head):
    """The value a reading ends with, for one that sends nothing before it but files."""
    with answered(kind, *files, **head) as answer:
        return answer.finish()
