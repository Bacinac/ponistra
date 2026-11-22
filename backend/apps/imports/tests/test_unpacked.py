import io
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import pytest

from apps.jobs.models import Job
from apps.jobs.tests.handed import done, refused
from apps.search.tests.test_search import upload_file

ZIP = b"PK\x05\x06" + bytes(18)


def packed(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size, member.mtime = len(data), 1_795_000_000
            tar.addfile(member, io.BytesIO(data))
    return out.getvalue()


@pytest.fixture
def converter(settings):
    """The converter's door for a whole archive, answering as `answer` holds, noting the
    password sent."""
    answer: dict = {"status": 200, "body": b""}
    passwords: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            given = self.headers.get("Archive-Password")
            passwords.append(unquote(given) if given else None)
            found = self.path.partition("?")[0] == "/archive/all"
            status, body = (answer["status"], answer["body"]) if found else (404, b"")
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    settings.CONVERTER_URL = f"http://127.0.0.1:{httpd.server_port}"
    yield answer, passwords
    httpd.shutdown()
    httpd.server_close()


def children(api, parent: str) -> dict[str, dict]:
    listed = api.get("/api/nodes", {"parent": parent}).json()["children"]
    return {each["title"]: each for each in listed}


@pytest.mark.django_db
def test_an_archive_is_unpacked_into_a_folder_named_after_it(api, converter):
    answer, passwords = converter
    answer["body"] = packed(
        {
            "a/ugovor.txt": b"Ugovor",
            "a/b/popis.txt": b"Popis",
            "../izvan.txt": b"Izvan",
            "/apsolutno/c.txt": b"C",
        }
    )
    folder = api.post("/api/nodes", {"kind": "folder", "title": "Mapa"}, "application/json")
    archive = upload_file(api, "Paket", ZIP, parent=folder.json()["id"])
    unpacked = done(api, "unpack", node=archive)
    assert unpacked["count"] == 4
    beside = api.get("/api/nodes", {"parent": folder.json()["id"]}).json()["children"]
    assert sorted((each["title"], each["kind"]) for each in beside) == [
        ("Paket", "file"),
        ("Paket", "folder"),
    ]
    top = children(api, unpacked["folder"])
    assert set(top) == {"a", "izvan", "apsolutno"}
    a = children(api, top["a"]["id"])
    assert set(a) == {"ugovor", "b"}
    assert set(children(api, a["b"]["id"])) == {"popis"}
    assert passwords == [None]


@pytest.mark.django_db
def test_a_locked_archive_is_unpacked_with_its_password_which_the_job_forgets(api, converter):
    answer, passwords = converter
    archive = upload_file(api, "Paket", ZIP)
    answer["status"] = 409
    assert refused(api, "unpack", node=archive) == (409, "archive_locked")
    answer.update(status=200, body=packed({"x.txt": b"X"}))
    assert done(api, "unpack", node=archive, password="tajna čž")["count"] == 1
    assert passwords == [None, "tajna čž"]
    assert not any("password" in each.parameters for each in Job.objects.all())


@pytest.mark.django_db
def test_only_an_archive_is_unpacked(api):
    plain = upload_file(api, "Biljeska", b"Obican tekst\n")
    assert refused(api, "unpack", node=plain) == (400, "not_an_archive")
