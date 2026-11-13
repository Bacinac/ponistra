import pytest

from apps.mail import mime, taking
from apps.mail.models import Priority


def parsed(*headers: str):
    return mime.parsed(("\r\n".join(headers) + "\r\n\r\nx").encode())


def test_people_written_as_domino_names_are_kept_by_their_common_name():
    message = parsed(
        "From: Nevenka Sabol/Brezik",
        "To: Ivo Boskovic/Brezik@Brezik, CN=Ana Horvat/OU=Prodaja/O=Brezik, b@x.test",
        "Cc: Mail Router",
        "Reply-To: undisclosed-recipients:;",
    )
    assert taking.addresses(message, "From") == [
        {"name": "Nevenka Sabol", "address": "Nevenka Sabol/Brezik"}
    ]
    assert taking.addresses(message, "To") == [
        {"name": "Ivo Boskovic", "address": "Ivo Boskovic/Brezik@Brezik"},
        {"name": "Ana Horvat", "address": "CN=Ana Horvat/OU=Prodaja/O=Brezik"},
        {"name": "", "address": "b@x.test"},
    ]
    assert taking.addresses(message, "Cc") == [{"name": "Mail Router", "address": ""}]
    assert taking.addresses(message, "Reply-To") == []
    quoted = parsed('From: "Bošković, Ivo" <ivo@x.test>, a/b@x.test')
    assert taking.addresses(quoted, "From") == [
        {"name": "Bošković, Ivo", "address": "ivo@x.test"},
        {"name": "", "address": "a/b@x.test"},
    ]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ((), Priority.NORMAL),
        (("X-Priority: 1 (Highest)",), Priority.HIGH),
        (("X-Priority: 2 (High)",), Priority.HIGH),
        (("X-Priority: 3 (Normal)", "Importance: High"), Priority.NORMAL),
        (("X-Priority: 5",), Priority.LOW),
        (("Importance: high",), Priority.HIGH),
        (("Priority: non-urgent",), Priority.LOW),
        (("X-MSMail-Priority: Low",), Priority.LOW),
        (("X-IBM-UNID: 734525B8", "X-Priority: 1"), Priority.HIGH),
        (("X-IBM-UNID: 734525B8", "X-Priority: 2"), Priority.NORMAL),
        (("X-IBM-UNID: 734525B8", "X-Priority: 3"), Priority.LOW),
    ],
)
def test_the_priority_is_read_on_the_scale_its_writer_uses(headers, expected):
    assert taking.priority(parsed("Subject: x", *headers)) == expected


def test_a_copy_exchange_gave_its_own_message_id_is_the_message_as_it_was_written():
    written = b"Message-ID: <ours@example.com>\r\nSubject: Test\r\n\r\n"
    sent = (
        b"Message-ID: <VI0P193MB@PROD.OUTLOOK.COM>\r\nSubject: Test\r\n"
        b"X-Microsoft-Original-Message-ID: <ours@example.com>\r\n\r\n"
    )
    assert taking.keyed(sent) == taking.keyed(written)
