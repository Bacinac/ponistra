import socket
import ssl
import struct
import threading
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from apps.backups import backups
from apps.health import views
from apps.search import extraction
from apps.search.tests.test_search import upload_file
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def places(tmp_path, monkeypatch):
    (tmp_path / "backup").mkdir()
    monkeypatch.setenv("RESTIC_REPOSITORY", str(tmp_path / "backup"))
    monkeypatch.setenv("RESTIC_PASSWORD", "test")
    monkeypatch.setenv("RESTIC_CACHE_DIR", str(tmp_path / "cache"))


@pytest.fixture
def healthy(settings):
    """The ocr service, answering its health."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/health" else 404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    settings.OCR_URL = f"http://127.0.0.1:{httpd.server_port}"
    yield
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def relay(settings, monkeypatch, tmp_path):
    """Meetings' relay under the name localhost, answering a STUN binding over TLS."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(hours=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    pem = certificate.public_bytes(serialization.Encoding.PEM)
    (tmp_path / "relay.pem").write_bytes(
        pem
        + key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(tmp_path / "relay.pem")
    listening = socket.create_server(("127.0.0.1", 0))

    def serve():
        while True:
            try:
                accepted, _ = listening.accept()
            except OSError:
                return
            with accepted, suppress(OSError), server.wrap_socket(accepted, server_side=True) as tls:
                request = tls.makefile("rb").read(20)
                tls.sendall(struct.pack("!HH", 0x0101, 0) + request[4:])

    threading.Thread(target=serve, daemon=True).start()
    monkeypatch.setattr(views, "TLS", ssl.create_default_context(cadata=pem.decode()))
    monkeypatch.setattr(views, "RELAY_PORT", listening.getsockname()[1])
    settings.TURN = "localhost"
    yield
    listening.close()


@pytest.fixture
def admin(client):
    client.force_login(User.objects.create_superuser("ivo@example.com", "Kamen-Most-Rijeka-71"))
    return client


def test_only_an_administrator_reads_the_health(api):
    assert api.get("/api/health").status_code == 403


def test_the_health_says_what_answers_and_what_is_late(admin, settings, healthy):
    settings.CONVERTER_URL = settings.PRINTER_URL = "http://127.0.0.1:9"
    settings.TURN = ""
    health = admin.get("/api/health").json()
    assert health["services"] == {
        "database": True,
        "converter": False,
        "printer": False,
        "ocr": True,
        "meetings": True,
    }
    assert health["snapshots"] == {
        "count": 0,
        "newest": None,
        "due": health["snapshots"]["due"],
        "late": True,
    }
    [disk] = health["disks"]
    assert disk["holds"] == ["files", "snapshots"] and 0 < disk["free"] <= disk["total"]
    assert health["queues"] == {"jobs": 0, "ocr": 0, "text": 0, "unread": 0, "batches": 0}
    assert (health["stored"]["files"], health["stored"]["dead"]) == (0, 0)
    assert set(health["archive"]) == {"at", "error", "late"}


def test_the_queues_show_what_waits_to_be_read_and_what_could_not_be(admin, settings, healthy):
    settings.TURN = ""
    upload_file(admin, "Pokvaren", b"%PDF-1.7\nnot really a pdf")
    assert admin.get("/api/health").json()["queues"]["text"] == 1
    assert extraction.extract_next()
    queues = admin.get("/api/health").json()["queues"]
    assert (queues["text"], queues["unread"]) == (0, 1)


def test_a_repository_that_will_not_open_is_reported(admin, monkeypatch):
    def broken():
        raise backups.Failed("restic snapshots: wrong password")

    monkeypatch.setattr(backups, "snapshots", broken)
    assert admin.get("/api/health").json()["snapshots"] == {
        "error": "restic snapshots: wrong password",
        "late": True,
    }


def test_the_relay_is_checked_under_its_name_where_the_installation_has_one(
    admin, relay, monkeypatch
):
    assert admin.get("/api/health").json()["services"]["relay"] is True
    monkeypatch.setattr(views, "TLS", ssl.create_default_context())
    assert admin.get("/api/health").json()["services"]["relay"] is False
    monkeypatch.setattr(views, "RELAY_PORT", 9)
    assert admin.get("/api/health").json()["services"]["relay"] is False
