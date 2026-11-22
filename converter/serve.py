"""POST /docx/<odt|doc|rtf>, /xlsx/<ods|xls> or /pptx/<odp|ppt> with the file as the body answers
with it as docx, xlsx or pptx; GET /health answers when the server is up. Each conversion runs
LibreOffice in a profile of its own, two at a time, and is killed whole when it overruns.

POST /archive?name=<its name> with an archive as the body answers with its entries as JSON, POST
/archive/<n>?name=… with entry n's bytes, its name in Entry-Name, POST /archive/all?name=… with
every file among its first ten thousand entries as an uncompressed pax tar; a password comes in
Archive-Password, URL-encoded, and is never kept. 409 asks for one, 413 refuses what unpacks past
the limit, 422 an archive that cannot be read."""

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import archives

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
UNPACKING = threading.BoundedSemaphore(2)
# One at a time: a whole archive unpacked takes its size again on the disk, and its time.
PACKING = threading.BoundedSemaphore(1)


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
        place = urlsplit(self.path)
        if place.path == "/archive" or place.path.startswith("/archive/"):
            return self._archive(place)
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

    def _archive(self, place) -> None:
        size = int(self.headers.get("Content-Length") or 0)
        number = place.path.removeprefix("/archive").removeprefix("/")
        whole = number == "all"
        if size <= 0 or number and not (whole or number.isdigit()):
            return self._refuse(HTTPStatus.BAD_REQUEST, size)
        if size > archives.UNPACKED:
            return self._refuse(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, size)
        name = (parse_qs(place.query).get("name") or ["archive"])[0]
        password = unquote(self.headers.get("Archive-Password") or "") or None
        with PACKING if whole else UNPACKING, tempfile.TemporaryDirectory() as work:
            path = Path(work) / "archive"
            with path.open("wb") as file:
                left = size
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        return self._reply(HTTPStatus.BAD_REQUEST)
                    file.write(chunk)
                    left -= len(chunk)
            try:
                if not number:
                    found = archives.listed(path, name, password)
                    return self._reply(
                        HTTPStatus.OK, json.dumps(found).encode(), "application/json"
                    )
                if whole:
                    tar = Path(work) / "all.tar"
                    archives.packed(path, name, password, tar)
                    path.unlink()
                    return self._sent(tar, "application/x-tar")
                unpacked = archives.unpacked(path, name, int(number), password)
                if unpacked is None:
                    return self._reply(HTTPStatus.NOT_FOUND)
                self._unpacked(*unpacked, work)
            except archives.Locked:
                self._reply(HTTPStatus.CONFLICT, b"locked")
            except archives.Overflow as error:
                print(f"archive entry refused: {error}", flush=True)
                self._reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            except (archives.Unreadable, archives.ArchiveError) as error:
                print(f"archive unreadable: {error}", flush=True)
                self._reply(HTTPStatus.UNPROCESSABLE_ENTITY, str(error)[:300].encode())

    def _unpacked(self, name: str, size: int | None, chunks, work: str) -> None:
        if size is None:
            # A size the archive does not tell is known once the entry is unpacked.
            spooled = Path(work) / "entry"
            with spooled.open("wb") as file:
                for chunk in chunks:
                    file.write(chunk)
            size, chunks = spooled.stat().st_size, _read(spooled)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Entry-Name", quote(name))
        self.end_headers()
        sent = 0
        try:
            for chunk in chunks:
                sent += len(chunk)
                self.wfile.write(chunk)
        except (archives.Overflow, archives.Unreadable, archives.ArchiveError):
            sent = -1
        if sent != size:
            # Cut short, the answer tells the backend it failed; its length never matched.
            print(f"archive entry {name!r} unpacked to {sent} of {size} bytes", flush=True)
            self.close_connection = True
            self.connection.shutdown(2)

    def _sent(self, path: Path, kind: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as file:
            shutil.copyfileobj(file, self.wfile, 1 << 20)

    def _refuse(self, status: HTTPStatus, size: int) -> None:
        # Read to its end: answered while still sending, the backend sees a broken connection,
        # which it takes for a converter that is down and comes back with the same file.
        while size > 0:
            size -= len(self.rfile.read(min(size, 1 << 20))) or size
        self._reply(status)

    def _reply(
        self, status: HTTPStatus, body: bytes = b"", kind: str = "application/octet-stream"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _read(path: Path):
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            yield chunk


if __name__ == "__main__":
    # On the disk, not in memory: an archive can be as large as the installation's largest file.
    # Emptied of what the work held when the service last stopped.
    held = Path(tempfile.gettempdir()) / "work"
    shutil.rmtree(held, ignore_errors=True)
    held.mkdir()
    tempfile.tempdir = str(held)
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
