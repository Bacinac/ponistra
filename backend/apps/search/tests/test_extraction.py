import errno
import urllib.error

import pytest

from apps.blobs import store
from apps.blobs.models import Blob
from apps.imports import convert
from apps.imports.tests import test_xlsx
from apps.imports.tests.word_files import p, word_file
from apps.search import extraction
from apps.search.models import BlobText

from .test_search import extract_all, search, titles, upload_file

pytestmark = pytest.mark.django_db

RTF = b"{\\rtf1\\ansi Ugovor\\par}"


def broken_workbook(tmp_path) -> bytes:
    def nameless(styles: str) -> str:
        return styles.replace(
            "</styleSheet>", '<numFmts count="1"><numFmt formatCode="0"/></numFmts></styleSheet>'
        )

    return test_xlsx.book(
        tmp_path, {"Sheet1": {"A1": "1"}}, parts={"xl/styles.xml": nameless}
    ).read_bytes()


def answering(monkeypatch, code: int) -> None:
    def refused(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "", {}, None)

    monkeypatch.setattr(convert.urllib.request, "urlopen", refused)


def test_a_broken_workbook_is_recorded_and_the_files_after_it_are_read(api, tmp_path):
    upload_file(api, "Pokvarena", broken_workbook(tmp_path))
    upload_file(api, "Uvjeti", word_file(p("Jamstveni rok")))
    upload_file(api, "Ponuda", word_file(p("Kalibracija osi")))
    extract_all()
    assert BlobText.objects.exclude(failed="").count() == 1
    assert titles(search(api, "jamstveni")) == ["Uvjeti"]
    assert titles(search(api, "kalibracija")) == ["Ponuda"]
    assert not extraction.waiting().exists()


def test_a_tab_too_long_for_one_search_vector_is_read_in_pages(api):
    words = " ".join(f"r{number}x" for number in range(200_000))
    upload_file(api, "Popis", word_file(p(words) + p("Kalibracija osi")))
    extract_all()
    found = BlobText.objects.get()
    assert not found.failed and found.page_count > 1
    assert titles(search(api, "kalibracija")) == ["Popis"]


@pytest.mark.parametrize(("code", "name"), [(413, "TooLarge"), (400, "Unreadable")])
def test_a_file_the_converter_refuses_is_recorded(api, monkeypatch, code, name):
    upload_file(api, "Velika", RTF)
    answering(monkeypatch, code)
    assert extraction.extract_next()
    assert BlobText.objects.get().failed.startswith(name)
    assert not extraction.extract_next()


def test_a_converter_in_trouble_leaves_the_file_waiting(api, monkeypatch):
    upload_file(api, "Velika", RTF)
    answering(monkeypatch, 500)
    assert not extraction.extract_next()
    assert not BlobText.objects.exists() and extraction.waiting().count() == 1


def test_a_full_disk_marks_no_file_failed(api, monkeypatch):
    upload_file(api, "Uvjeti", word_file(p("Jamstveni rok")))

    def full(blob):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(extraction, "_read", full)
    with pytest.raises(OSError, match="No space"):
        extraction.extract_next()
    assert not BlobText.objects.exists()


def test_a_store_not_mounted_marks_no_file_failed(api, monkeypatch, tmp_path):
    upload_file(api, "Uvjeti", word_file(p("Jamstveni rok")))
    (tmp_path / "unmounted").mkdir()
    monkeypatch.setattr(store, "root", lambda: tmp_path / "unmounted")
    with pytest.raises(FileNotFoundError):
        extraction.extract_next()
    assert not BlobText.objects.exists()


def test_one_file_gone_from_the_store_is_recorded(api):
    upload_file(api, "Uvjeti", word_file(p("Jamstveni rok")))
    upload_file(api, "Ponuda", word_file(p("Kalibracija osi")))
    gone = Blob.objects.order_by("sha256").first()
    store.path_of(gone.sha256).unlink()
    extract_all()
    assert BlobText.objects.get(blob=gone).failed
    assert BlobText.objects.count() == 2
