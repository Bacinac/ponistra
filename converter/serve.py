"""POST /docx/<odt|doc|rtf>, /xlsx/<ods|xls> or /pptx/<odp|ppt> with the file as the body answers
with it as docx, xlsx or pptx; GET /health answers when the server is up. Each conversion runs LibreOffice in a profile of its own,
two at a time, and is killed whole when it overruns."""

import os
import signal
import subprocess
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8040
LARGEST = 256 * 1024 * 1024
TIMEOUT = 120
FILTERS = {
    "docx": "MS Word 2007 XML",
    "xlsx": "Calc MS Excel 2007 XML",
    "pptx": "Impress MS PowerPoint 2007 XML",
}
KINDS = {"docx": {"odt", "doc", "rtf"}, "xlsx": {"ods", "xls"}, "pptx": {"odp", "ppt"}}
RUNNING = threading.BoundedSemaphore(2)


def convert(data: bytes, kind: str, target: str) -> bytes | None:
    with RUNNING, tempfile.TemporaryDirectory() as work:
        source = Path(work) / f"file.{kind}"
        source.write_bytes(data)
        command = [
            "soffice",
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--nodefault",
            f"-env:UserInstallation=file://{work}/profile",
            "--convert-to",
            f"{target}:{FILTERS[target]}",
            "--outdir",
            f"{work}/out",
            str(source),
        ]
        # soffice starts soffice.bin as its child; a session of its own lets both go at once.
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            _, said = process.communicate(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            print(f"{kind} conversion overran {TIMEOUT} s", flush=True)
            return None
        result = Path(work) / "out" / f"file.{target}"
        if process.returncode != 0 or not result.is_file():
            print(f"{kind} conversion failed: {said.decode(errors='replace')}", flush=True)
            return None
        return result.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._reply(HTTPStatus.OK if self.path == "/health" else HTTPStatus.NOT_FOUND)

    def do_POST(self):
        target, _, kind = self.path.removeprefix("/").partition("/")
        size = int(self.headers.get("Content-Length") or 0)
        if kind not in KINDS.get(target, ()) or size <= 0:
            return self._refuse(HTTPStatus.BAD_REQUEST, size)
        if size > LARGEST:
            return self._refuse(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, size)
        converted = convert(self.rfile.read(size), kind, target)
        if converted is None:
            return self._reply(HTTPStatus.UNPROCESSABLE_ENTITY)
        self._reply(HTTPStatus.OK, converted)

    def _refuse(self, status: HTTPStatus, size: int) -> None:
        # Read to its end: answered while still sending, the backend sees a broken connection,
        # which it takes for a converter that is down and comes back with the same file.
        while size > 0:
            size -= len(self.rfile.read(min(size, 1 << 20))) or size
        self._reply(status)

    def _reply(self, status: HTTPStatus, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
