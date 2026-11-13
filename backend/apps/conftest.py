import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from anyio import create_task_group
from asgiref.sync import sync_to_async
from django.db import connections

from apps.backups import backups
from apps.blobs.tests.uploads import uploaded
from apps.collab import server
from apps.collab.server import CollabServer
from apps.users.models import User

pytest_plugins = ["apps.core.checkmap", "apps.reader.testing"]


def pytest_make_parametrize_id(config, val, argname):
    """Bytes a case builds, a zip or a PDF, carry the time or a random id of the process that built
    them: named by their argument instead, every worker collects the same cases."""
    if isinstance(val, bytes):
        return argname
    return None


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def mail_server_alone(request, monkeypatch):
    """The test mail server has one account, whose every folder a sync reads: a test that reaches
    it is in the group mox, which runs on one worker."""
    if any(mark.args == ("mox",) for mark in request.node.iter_markers("xdist_group")):
        return
    resolve = socket.getaddrinfo

    def refused(host, *args, **kwargs):
        if host == "mox":
            raise AssertionError("a test that reaches the mail server is marked xdist_group('mox')")
        return resolve(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", refused)


@pytest.fixture(autouse=True)
def blob_root(settings, tmp_path):
    settings.BLOB_ROOT = tmp_path / "blobs"
    settings.BLOB_ROOT.mkdir()
    return settings.BLOB_ROOT


@pytest.fixture(autouse=True)
def help_shelf(settings, tmp_path):
    """An empty help of each test's own: the tree's articles change while they are written, and a
    search would read one half written."""
    settings.HELP = tmp_path / "help-shelf"
    settings.HELP.mkdir()
    (settings.HELP / "sections.json").write_text("[]")


@pytest.fixture(autouse=True)
def backup_base(monkeypatch, tmp_path):
    """The database is copied for a backup to one path of the container, which workers share."""
    monkeypatch.setattr(backups, "BASE", tmp_path / "backup" / "database")


@pytest.fixture
def api(client):
    client.user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(client.user)
    return client


@pytest.fixture
def upload(api):
    return lambda data: uploaded(api, data)


@pytest.fixture
def service(settings):
    """The ocr service, giving each file the next of the answers appended."""
    answers: list[tuple[int, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            status, body = answers.pop(0)
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    settings.OCR_URL = f"http://127.0.0.1:{httpd.server_port}"
    yield answers
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
async def live(monkeypatch):
    fresh = CollabServer()
    monkeypatch.setattr(server, "collab", fresh)
    async with fresh, create_task_group():
        yield fresh
    # The rooms reach the database on the thread Django shares outside a request, whose
    # connection would otherwise outlive the test and hold the test database open.
    await sync_to_async(connections.close_all)()
