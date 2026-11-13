import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest


@pytest.fixture
def printer(settings):
    """A printer answering each request with the next of its replies, a PDF in the runs
    `printed` is given."""
    replies: list[tuple[int, bytes] | tuple[int, bytes, dict[str, str]]] = []
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            status, data, *headers = replies.pop(0)
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            for name, value in (headers[0] if headers else {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings.PRINTER_URL = f"http://127.0.0.1:{server.server_port}"

    def printed(*runs: bytes) -> None:
        replies.append((200, b"".join(runs), {"X-Runs": " ".join(str(len(run)) for run in runs)}))

    yield SimpleNamespace(replies=replies, received=received, printed=printed)
    server.shutdown()
    server.server_close()
