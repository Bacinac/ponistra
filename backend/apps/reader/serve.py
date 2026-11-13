"""The reader's server. POST /<kind> with a head and a file (wire.py) answers with the lines its
reading sends, GET /health when the server is up. Each request is served by a process forked
from this one and each reading by a process forked from that, under a ceiling of address space
and of processor time and without core files: a file that ends the reading ends only that
process, and the request's process says what became of it."""

import os
import resource
import signal
import socketserver
import sys
import tempfile
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging import getLogger
from pathlib import Path

from django.db import connections

from . import reads, wire

log = getLogger(__name__)

PORT = 8070
AT_ONCE = 3
LARGEST = 4 * 1024**3
# Of address space, not memory used: what the forked process holds of the server counts too.
MEMORY = 3 * 1024**3
# A backend that stops taking a reading's lines for this long has gone; the reading ends.
STALLED = 600
OVERRAN = {signal.SIGXCPU, signal.SIGKILL}


class Out:
    """Where a reading sends its lines and files."""

    def __init__(self, stream):
        self.stream = stream

    def send(self, value) -> None:
        self.stream.write(wire.line(value))

    def file(self, path: Path) -> None:
        self.stream.write(wire.line({"file": path.stat().st_size}))
        with path.open("rb") as source:
            while chunk := source.read(1 << 20):
                self.stream.write(chunk)

    def data(self, data: bytes) -> None:
        self.stream.write(wire.line({"file": len(data)}))
        self.stream.write(data)


def _refused(*args, **kwargs):
    raise RuntimeError("the reader reaches no database")


def _read(read: reads.Read, paths: list[Path], head: dict, out: Out):
    try:
        return {"end": read.run(paths, head, out)}
    except MemoryError:
        return {"error": "too_large", "detail": "out of memory"}
    except Exception as error:
        name = reads.failure(error)
        if name is None:
            log.error("reader: %s failed\n%s", read.run.__qualname__, traceback.format_exc())
            name = "unreadable"
        return {"error": name, "detail": repr(error)[:500]}


def _work(read: reads.Read, paths: list[Path], head: dict, written: int) -> None:
    """The reading's own process: it never returns."""
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
        resource.setrlimit(resource.RLIMIT_CPU, (read.seconds, read.seconds + 5))
        # Inherited open in a test's process, a connection must not be used here, nor closed.
        for connection in connections.all():
            connection.ensure_connection = _refused
        with os.fdopen(written, "wb", buffering=1 << 16) as stream:
            out = Out(stream)
            ended = _read(read, paths, head, out)
            checkmap = sys.modules.get("apps.core.checkmap")
            if checkmap is not None and (ran := checkmap.ran()) is not None:
                out.send({"ran": ran})
            out.send(ended)
    except BaseException:
        os._exit(1)
    os._exit(0)


def _fate(status: int) -> dict:
    if os.WIFSIGNALED(status):
        overran = os.WTERMSIG(status) in OVERRAN
        name, detail = ("too_large" if overran else "unreadable"), f"signal {os.WTERMSIG(status)}"
    else:
        name, detail = "unreadable", f"exit {os.WEXITSTATUS(status)}"
    return {"error": name, "detail": f"the reading ended by {detail}"}


class Handler(BaseHTTPRequestHandler):
    timeout = STALLED

    def do_GET(self):
        self._reply(HTTPStatus.OK if self.path == "/health" else HTTPStatus.NOT_FOUND)

    def do_POST(self):
        read = reads.READS.get(self.path.removeprefix("/"))
        size = int(self.headers.get("Content-Length") or 0)
        if read is None or size <= 0:
            return self._refuse(HTTPStatus.BAD_REQUEST, size)
        if size > LARGEST:
            return self._refuse(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, size)
        told = self.rfile.readline(32)
        head = wire.parsed(self.rfile.read(int(told)))
        sizes = head.pop("sizes")
        if sum(sizes) != size - len(told) - int(told) or min(sizes, default=0) < 0:
            return self._refuse(HTTPStatus.BAD_REQUEST, size - len(told) - int(told))
        with tempfile.TemporaryDirectory() as work:
            paths = [Path(work) / str(at) for at in range(len(sizes))]
            for path, left in zip(paths, sizes, strict=True):
                with path.open("wb") as file:
                    while left > 0:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            return
                        file.write(chunk)
                        left -= len(chunk)
            self._answer(read, paths, head)

    def _answer(self, read: reads.Read, paths: list[Path], head: dict) -> None:
        taken, written = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(taken)
            _work(read, paths, head, written)
        os.close(written)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            with os.fdopen(taken, "rb") as lines:
                while chunk := lines.read1(1 << 16):
                    self.wfile.write(chunk)
        except OSError:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            return
        _, status = os.waitpid(pid, 0)
        if status:
            self.wfile.write(b"\n" + wire.line(_fate(status)))

    def _refuse(self, status: HTTPStatus, size: int) -> None:
        # Read to its end: answered while still sending, the backend sees a broken connection,
        # which it takes for a reader that is down.
        while size > 0:
            size -= len(self.rfile.read(min(size, 1 << 20))) or size
        self._reply(status)

    def _reply(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_request(self, code="-", size="-"):
        pass


class Server(socketserver.ForkingMixIn, HTTPServer):
    max_children = AT_ONCE
    request_queue_size = 64
    allow_reuse_address = True
    block_on_close = False


def serve(port: int = PORT) -> Server:
    return Server(("", port), Handler)
