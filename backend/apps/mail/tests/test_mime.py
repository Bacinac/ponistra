import base64

import pytest

from apps.mail import mime

from .mox import letter, put, server

pytestmark = pytest.mark.xdist_group("mox")

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_a_whole_message_reads_its_parts_by_their_imap_numbers(folder):
    message = letter("Izvještaj", "Cijena je 100 €.")
    message.add_alternative('<p>Cijena <b>100 €</b>.</p><img src="cid:logo@example.com">', "html")
    message.get_payload()[1].add_related(PNG, "image", "png", cid="<logo@example.com>")
    message.add_attachment(
        b"%PDF-1.7", maintype="application", subtype="pdf", filename="Šibenik.pdf"
    )
    message.add_attachment(letter("Proslijeđeno"))
    put(folder, message)
    with server() as client:
        client.select_folder(folder, readonly=True)
        [uid] = client.search("ALL")
        found = mime.parsed(client.fetch([uid], ["BODY.PEEK[]"])[uid][b"BODY[]"])
        described = mime.described(found)
        assert (described["plain"]["part"], described["html"]["part"]) == ("1.1", "1.2.1")
        assert [each["part"] for each in described["inline"]] == ["1.2.2"]
        assert [each["name"] for each in described["attachments"]] == ["Šibenik.pdf", ""]
        carried = [described["plain"], described["html"], *described["inline"]]
        for part in [*carried, *described["attachments"]]:
            number = part["part"]
            [given] = client.fetch([uid], [f"BODY.PEEK[{number}]"]).values()
            assert mime.raw(found, number) == given[f"BODY[{number}]".encode()], number
    assert mime.raw(found, "9") is None


def test_a_part_whose_headers_carry_bytes_beyond_ascii_is_read_as_utf8():
    raw = (
        b"From: ana@example.com\r\nSubject: Ra\xc4\x8dun\r\nMIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b"\r\n\r\n'
        b"--b\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nVidi privitak.\r\n"
        b"--b\r\nContent-Type: application/pdf\r\n"
        b'Content-Disposition: attachment; filename="ra\xc4\x8dun.pdf"\r\n'
        b"Content-Transfer-Encoding: base64\r\nContent-ID: <ra\xc4\x8dun>\r\n\r\n"
        + base64.b64encode(b"%PDF-1.7")
        + b"\r\n--b--\r\n"
    )
    message = mime.parsed(raw)
    assert mime.header(message, "Subject") == "Račun"
    (attachment,) = mime.described(message)["attachments"]
    assert (attachment["type"], attachment["encoding"], attachment["cid"]) == (
        "application/pdf",
        "base64",
        "račun",
    )
