import json
import threading
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import unquote

import pytest
from PIL import Image

from apps.blobs import store
from apps.imports.reading import Unreadable
from apps.reader import archives, shown
from apps.search.tests.test_search import upload_file

PNG = b"\x89PNG\r\n\x1a\n"


def picture(form: str, **saved) -> bytes:
    out = BytesIO()
    Image.new("RGB", (30, 20), (40, 120, 90)).save(out, form, **saved)
    return out.getvalue()


def message() -> bytes:
    mail = EmailMessage()
    mail["Subject"] = "Ponuda za održavanje"
    mail["From"] = "Ana Kovač <ana@example.com>"
    mail["To"] = "ivo@example.com"
    mail["Date"] = "Sun, 22 Nov 2026 10:15:00 +0100"
    mail.set_content("Pozdrav")
    mail.add_alternative('<p>Pozdrav</p><img src="cid:logo@x">', subtype="html")
    mail.get_payload()[1].add_related(picture("PNG"), "image", "png", cid="<logo@x>")
    mail.add_attachment(b"%PDF-1.4 ponuda", "application", "pdf", filename="ponuda.pdf")
    return bytes(mail)


CARDS = b"""BEGIN:VCARD\r
VERSION:3.0\r
FN:Ana Kova\xc4\x8d\r
EMAIL:ana@example.com\r
TEL:+385 91 000 0000\r
ORG:Lipa Studio\r
END:VCARD\r
BEGIN:VCARD\r
VERSION:3.0\r
FN:Marko Horvat\r
END:VCARD\r
"""

EVENTS = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//test//EN\r
X-WR-CALNAME:Projekt\r
BEGIN:VEVENT\r
UID:2\r
SUMMARY:Predaja\r
DTSTART;VALUE=DATE:20261203\r
DTEND;VALUE=DATE:20261204\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:1\r
SUMMARY:Sastanak\r
LOCATION:Zagreb\r
DTSTART:20261201T090000Z\r
DTEND:20261201T100000Z\r
RRULE:FREQ=WEEKLY\r
END:VEVENT\r
END:VCALENDAR\r
"""


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (picture("BMP"), "image/bmp"),
        (picture("ICO"), "image/vnd.microsoft.icon"),
        (picture("TIFF"), "image/tiff"),
        (b"8BPS\x00\x01" + bytes(40), "image/vnd.adobe.photoshop"),
        (b"PK\x05\x06" + bytes(18), "application/zip"),
        (b"7z\xbc\xaf\x27\x1c" + bytes(30), "application/x-7z-compressed"),
        (bytes(257) + b"ustar\x0000" + bytes(250), "application/x-tar"),
        (b"\x1f\x8b\x08" + bytes(20), "application/gzip"),
    ],
)
def test_pictures_and_archives_are_told_by_their_bytes(data, expected):
    assert store.sniff(data) == expected


def test_a_bitmap_head_without_its_reserved_zeros_is_not_a_picture():
    assert store.sniff(b"BM" + bytes(4) + b"\x01\x00" + bytes(40)) == store.UNKNOWN


def test_a_message_shows_its_headers_body_and_attachments(tmp_path):
    path = tmp_path / "m"
    path.write_bytes(message())
    found = shown.of(path, "Ponuda.eml", "/p/", "text/plain")
    assert found["kind"] == "message"
    assert found["subject"] == "Ponuda za održavanje"
    assert found["from"] == "Ana Kovač <ana@example.com>"
    assert found["date"].startswith("2026-11-22T10:15:00")
    assert "Pozdrav" in found["html"]
    [inline] = [each for each in found["html"].split('"') if each.startswith("/p/")]
    [attached] = found["attachments"]
    assert attached["name"] == "ponuda.pdf"

    image = shown.part(path, "Ponuda.eml", inline.removeprefix("/p/"), "text/plain")
    assert image.shown and image.data.startswith(PNG)
    saved = shown.part(path, "Ponuda.eml", attached["part"], "text/plain")
    assert (saved.name, saved.data, saved.shown) == ("ponuda.pdf", b"%PDF-1.4 ponuda", False)
    assert shown.part(path, "Ponuda.eml", "99", "text/plain") is None


def test_a_message_is_told_by_its_headers_without_its_name(tmp_path):
    path = tmp_path / "m"
    path.write_bytes(message())
    assert shown.of(path, "bez imena", "/p/", "text/plain")["kind"] == "message"
    path.write_bytes(b"Obican tekst\n")
    assert shown.of(path, "biljeska.txt", "/p/", "text/plain") is None


def test_contacts_are_listed_by_name(tmp_path):
    path = tmp_path / "c"
    path.write_bytes(CARDS)
    found = shown.of(path, "kontakti.vcf", "/p/", "text/vcard")
    assert found["kind"] == "cards"
    assert [card["name"] for card in found["people"]] == ["Ana Kovač", "Marko Horvat"]


def test_events_are_listed_in_order_with_their_repetition(tmp_path):
    path = tmp_path / "e"
    path.write_bytes(EVENTS)
    found = shown.of(path, "projekt.ics", "/p/", "text/calendar")
    assert (found["kind"], found["name"], found["count"]) == ("events", "Projekt", 2)
    first, second = found["events"]
    assert (first["summary"], first["location"], first["repeats"]) == ("Sastanak", "Zagreb", True)
    assert (second["summary"], second["all_day"]) == ("Predaja", True)


def test_a_broken_calendar_is_unreadable(tmp_path):
    path = tmp_path / "e"
    path.write_bytes(b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART:nonsense\r\n")
    with pytest.raises(Unreadable):
        shown.of(path, "x.ics", "/p/", "text/calendar")


def test_a_picture_the_browser_cannot_show_is_drawn_whole(tmp_path):
    path = tmp_path / "p"
    path.write_bytes(picture("BMP"))
    assert shown.of(path, "sken.bmp", "/p/", "image/bmp") == {
        "kind": "picture",
        "whole": "/p/whole",
    }
    drawn = shown.part(path, "sken.bmp", "whole", "image/bmp")
    assert (drawn.name, drawn.media_type, drawn.shown) == ("sken.png", "image/png", True)
    assert Image.open(BytesIO(drawn.data)).size == (30, 20)


@pytest.fixture
def converter(settings):
    """The converter's archive door: answers by the path asked, noting the password sent."""
    answers: dict[str, tuple[int, bytes, dict]] = {}
    passwords: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            given = self.headers.get("Archive-Password")
            passwords.append(unquote(given) if given else None)
            status, body, headers = answers.get(self.path.partition("?")[0], (404, b"", {}))
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    settings.CONVERTER_URL = f"http://127.0.0.1:{httpd.server_port}"
    yield answers, passwords
    httpd.shutdown()
    httpd.server_close()


LISTED = {
    "entries": [
        {"n": 0, "path": "a/", "size": 0, "modified": None, "folder": True},
        {"n": 1, "path": "a/ugovor.docx", "size": 4, "modified": None, "folder": False},
    ],
    "count": 2,
}


def test_an_archive_is_listed_and_its_entry_saved_through_the_converter(tmp_path, converter):
    answers, passwords = converter
    answers["/archive"] = (200, json.dumps(LISTED).encode(), {"Content-Type": "application/json"})
    answers["/archive/1"] = (200, b"DOCX", {"Entry-Name": "a%2Fugovor.docx"})
    path = tmp_path / "z"
    path.write_bytes(b"PK\x05\x06" + bytes(18))
    assert shown.of(path, "paket.zip", "/p/", store.ZIP) == {"kind": "archive", **LISTED}
    entry = shown.part(path, "paket.zip", "1", store.ZIP, "lozinka čž")
    assert (entry.name, entry.data.read(), entry.shown) == ("a/ugovor.docx", b"DOCX", False)
    assert entry.media_type.endswith("wordprocessingml.document")
    assert passwords == [None, "lozinka čž"]
    assert shown.part(path, "paket.zip", "7", store.ZIP) is None
    assert shown.part(path, "paket.zip", "../x", store.ZIP) is None


@pytest.mark.parametrize(
    ("status", "raised"),
    [
        (409, archives.Locked),
        (413, archives.TooLarge),
        (422, Unreadable),
        (500, archives.Unavailable),
    ],
)
def test_what_the_converter_refuses_is_told_apart(tmp_path, converter, status, raised):
    answers, _ = converter
    answers["/archive"] = (status, b"no", {})
    path = tmp_path / "z"
    path.write_bytes(b"PK\x05\x06" + bytes(18))
    with pytest.raises(raised):
        shown.of(path, "paket.zip", "/p/", store.ZIP)


@pytest.mark.django_db
def test_a_file_shows_what_it_holds_and_saves_its_parts(api):
    file = upload_file(api, "Ponuda", message())
    found = api.get(f"/api/nodes/{file}/shown").json()
    assert found["kind"] == "message"
    [attached] = found["attachments"]
    saved = api.get(f"/api/nodes/{file}/shown/{attached['part']}")
    assert saved.content == b"%PDF-1.4 ponuda"
    assert saved["Content-Disposition"].startswith("attachment")
    assert saved["Content-Security-Policy"] == "sandbox"
    assert api.get(f"/api/nodes/{file}/shown/99").status_code == 404

    plain = upload_file(api, "Biljeska", b"Obican tekst\n")
    assert api.get(f"/api/nodes/{plain}/shown").json()["error"] == "not_found"


@pytest.mark.django_db
def test_a_locked_archive_asks_for_its_password(api, converter):
    answers, passwords = converter
    answers["/archive"] = (409, b"locked", {})
    file = upload_file(api, "Paket", b"PK\x05\x06" + bytes(18))
    refused = api.get(f"/api/nodes/{file}/shown")
    assert (refused.status_code, refused.json()["error"]) == (409, "archive_locked")
    answers["/archive"] = (200, json.dumps(LISTED).encode(), {})
    opened = api.post(
        f"/api/nodes/{file}/shown", {"password": "tajna"}, content_type="application/json"
    )
    assert opened.json()["count"] == 2
    assert passwords == [None, "tajna"]


@pytest.mark.django_db
def test_someone_without_the_file_is_not_shown_it(api, client):
    from apps.users.models import User

    file = upload_file(api, "Ponuda", message())
    client.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert client.get(f"/api/nodes/{file}/shown").status_code == 404


def test_an_outlook_message_shows_its_headers_body_and_attachments(tmp_path):
    from datetime import UTC, datetime

    from . import outlook

    path = tmp_path / "o"
    path.write_bytes(outlook.message(datetime(2026, 11, 22, 9, 15, tzinfo=UTC)))
    assert store.sniff_ole(path) == store.OUTLOOK
    found = shown.of(path, "Ponuda.msg", "/p/", store.OUTLOOK)
    assert {key: found[key] for key in ("kind", "subject", "from", "to", "date", "text")} == {
        "kind": "outlook",
        "subject": "Ponuda za održavanje",
        "from": "Ana Kovač <ana@example.com>",
        "to": "Ivo <ivo@example.com>",
        "date": "2026-11-22T09:15:00+00:00",
        "text": "Pozdrav iz Outlooka",
    }
    [attached] = found["attachments"]
    assert (attached["part"], attached["name"], attached["size"]) == ("00000000", "ponuda.pdf", 15)
    saved = shown.part(path, "Ponuda.msg", "00000000", store.OUTLOOK)
    assert (saved.name, saved.media_type, saved.data) == (
        "ponuda.pdf",
        "application/pdf",
        b"%PDF-1.4 ponuda",
    )
    assert shown.part(path, "Ponuda.msg", "../00", store.OUTLOOK) is None
