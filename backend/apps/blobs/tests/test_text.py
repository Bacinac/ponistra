import codecs

import pytest

from apps.blobs import text
from apps.blobs.models import Blob

pytestmark = pytest.mark.django_db


@pytest.fixture
def stored(upload):
    return lambda data: Blob.objects.get(pk=upload(data)["sha256"])


@pytest.mark.parametrize(
    ("data", "encoding"),
    [
        (b"plain ASCII\n", "UTF-8"),
        ("Čestitka\n".encode(), "UTF-8"),
        (codecs.BOM_UTF8 + "Čestitka\n".encode(), "UTF-8"),
        ("Čestitka\n".encode("utf-16"), "UTF-16"),
        ("Čestitka\n".encode("utf-32"), "UTF-32"),
    ],
)
def test_the_code_page_is_the_one_the_bytes_name_or_read_in(stored, data, encoding):
    found = text.read(stored(data), 1024)
    assert (found.text, found.encoding, found.truncated) == (
        "plain ASCII\n" if data.startswith(b"plain") else "Čestitka\n",
        encoding,
        False,
    )


def test_a_text_cut_short_ends_on_a_whole_line_and_says_so(stored):
    found = text.read(stored("prvi redak\ndrugi ččč\ntreći\n".encode()), 18)
    assert (found.text, found.truncated) == ("prvi redak\n", True)
    found = text.read(stored("prvi\r\ndrugi\r\n".encode("utf-16")), 15)
    assert (found.text, found.truncated) == ("prvi\n", True)


def test_pages_end_on_whole_lines_and_a_line_longer_than_one_is_cut():
    assert text.pages("aaaa\nbbbb\ncc\n", 9) == ["aaaa\n", "bbbb\ncc\n"]
    assert text.pages("x" * 10, 4) == ["xxxx", "xxxx", "xx"]
    assert text.pages("", 4) == []
