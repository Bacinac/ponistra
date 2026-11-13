"""POST /ocr with a PDF as the body answers with it, the text Tesseract reads in its pages that
carry none laid over them; 409 with "encrypted" or "signed" when reading it would break what
protects the file; GET /health answers when the server is up. One file at a time, killed whole
when it overruns or when the backend stops waiting for it."""

import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from read import ENCRYPTED, SIGNED

PORT = 8060
LARGEST = 256 * 1024 * 1024
TIMEOUT = 20 * 60
READER = str(Path(__file__).with_name("read.py"))
REFUSALS = {ENCRYPTED: b"encrypted", SIGNED: b"signed"}
RUNNING = threading.Lock()


def gone(connection: socket.socket) -> bool:
    readable, _, _ = select.select([connection], [], [], 0)
    return bool(readable) and not connection.recv(1, socket.MSG_PEEK)


def read(data: bytes, connection: socket.socket) -> tuple[HTTPStatus, bytes]:
    with RUNNING, tempfile.TemporaryDirectory() as work:
        source, target = Path(work) / "in.pdf", Path(work) / "out.pdf"
        source.write_bytes(data)
        # ocrmypdf starts Tesseract in processes of its own; a session lets them all go at once.
        process = subprocess.Popen(
            [sys.executable, READER, str(source), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        said = bytearray()
        reader = threading.Thread(target=lambda: said.extend(process.stderr.read()))
        reader.start()
        waited = 0
        while process.poll() is None:
            if waited >= TIMEOUT or gone(connection):
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                reader.join()
                why = f"overran {TIMEOUT} s" if waited >= TIMEOUT else "abandoned"
                print(f"reading {why}", flush=True)
                return HTTPStatus.UNPROCESSABLE_ENTITY, why.encode()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                waited += 1
        reader.join()
        if process.returncode in REFUSALS:
            return HTTPStatus.CONFLICT, REFUSALS[process.returncode]
        if process.returncode != 0 or not target.is_file():
            text = said.decode(errors="replace").strip()
            print(f"reading failed: {text}", flush=True)
            last = text.splitlines()[-1] if text else f"exit {process.returncode}"
            return HTTPStatus.UNPROCESSABLE_ENTITY, last.encode()
        return HTTPStatus.OK, target.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._reply(HTTPStatus.OK if self.path == "/health" else HTTPStatus.NOT_FOUND)

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        if self.path != "/ocr" or not 0 < size <= LARGEST:
            return self._reply(HTTPStatus.BAD_REQUEST)
        self._reply(*read(self.rfile.read(size), self.connection))

    def _reply(self, status: HTTPStatus, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
