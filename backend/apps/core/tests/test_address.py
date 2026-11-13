import json
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from apps.core import address


@pytest.fixture
def stun(monkeypatch):
    """A STUN server that sees this installation at 203.0.113.139, naming its software first."""
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))

    def answer():
        request, reader = server.recvfrom(512)
        seen = struct.unpack("!I", socket.inet_aton("203.0.113.139"))[0] ^ address.COOKIE
        attributes = struct.pack("!HH4s", 0x8022, 4, b"test")
        attributes += struct.pack("!HHBBHI", 0x0020, 8, 0, 1, 0, seen)
        header = struct.pack("!HH", 0x0101, len(attributes)) + request[4:20]
        server.sendto(header + attributes, reader)

    threading.Thread(target=answer, daemon=True).start()
    monkeypatch.setattr(address, "STUN", server.getsockname())
    yield
    server.close()


def test_stun_names_the_address_the_internet_sees(stun):
    assert address.public() == "203.0.113.139"


@pytest.fixture
def cloudflare(monkeypatch, settings):
    """Cloudflare keeping example.org, with what it has been asked."""
    records: dict[str, dict] = {}
    asked: list[tuple[str, str, dict | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def answer(self, result, status=200):
            body = json.dumps({"success": status == 200, "result": result}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def handle_one(self, method):
            url = urlparse(self.path)
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            asked.append((method, url.path, body))
            if self.headers["Authorization"] != "Bearer token":
                return self.answer({"errors": [{"code": 9109}]}, 403)
            if url.path == "/zones":
                return self.answer([{"id": "z1"}] if query["name"] == "example.org" else [])
            if url.path == "/zones/z1/dns_records" and method == "GET":
                kept = records.get(query["name"])
                return self.answer([kept] if kept and kept["type"] == query["type"] else [])
            if url.path == "/zones/z1/dns_records" and method == "POST":
                records[body["name"]] = {**body, "id": "r1"}
                return self.answer(records[body["name"]])
            if url.path == "/zones/z1/dns_records/r1" and method == "PATCH":
                record = next(each for each in records.values() if each["id"] == "r1")
                record.update(body)
                return self.answer(record)
            return self.answer(None, 404)

        def do_GET(self):
            self.handle_one("GET")

        def do_POST(self):
            self.handle_one("POST")

        def do_PATCH(self):
            self.handle_one("PATCH")

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(address, "API", f"http://127.0.0.1:{httpd.server_port}")
    settings.CLOUDFLARE_TOKEN = "token"
    yield records, asked
    httpd.shutdown()
    httpd.server_close()


def test_a_direct_name_follows_the_address(cloudflare, settings):
    records, asked = cloudflare
    assert address.point("turn.example.org", "203.0.113.81") is True
    assert records["turn.example.org"] == {
        "type": "A",
        "name": "turn.example.org",
        "content": "203.0.113.81",
        "ttl": 60,
        "proxied": False,
        "id": "r1",
    }
    assert address.point("turn.example.org", "203.0.113.81") is False
    asked.clear()
    assert address.point("turn.example.org", "203.0.113.139") is True
    assert asked[-1] == ("PATCH", "/zones/z1/dns_records/r1", {"content": "203.0.113.139"})
    assert records["turn.example.org"]["content"] == "203.0.113.139"

    settings.CLOUDFLARE_TOKEN = "revoked"
    with pytest.raises(OSError, match="Cloudflare 403"):
        address.point("turn.example.org", "203.0.113.139")
    settings.CLOUDFLARE_TOKEN = "token"
    with pytest.raises(OSError, match="no zone of turn.example.com"):
        address.point("turn.example.com", "203.0.113.139")


class _Stopped(Exception):
    pass


@pytest.mark.anyio
async def test_a_broken_answer_leaves_the_names_to_be_followed_at_the_next_look(
    settings, monkeypatch, caplog
):
    settings.CLOUDFLARE_TOKEN = "token"
    settings.DIRECT_NAMES = ["turn.example.org"]
    looks = []

    def public():
        looks.append(len(looks))
        if len(looks) == 1:
            raise struct.error("unpack requires a buffer of 8 bytes")
        return "203.0.113.139"

    async def slept(seconds):
        if len(looks) == 2:
            raise _Stopped

    monkeypatch.setattr(address, "public", public)
    monkeypatch.setattr(address, "point", lambda name, at: True)
    monkeypatch.setattr(address, "sleep", slept)
    with pytest.raises(_Stopped):
        await address.follow()
    assert looks == [0, 1]
    assert "could not follow the public address" in caplog.text
    assert "turn.example.org now points at 203.0.113.139" in caplog.text
