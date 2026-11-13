import zipfile

import pytest

from apps.imports import office
from apps.imports.reading import TooLarge, Unreadable
from apps.imports.tests.word_files import p, word_file

NAMESPACE = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


@pytest.fixture
def few(monkeypatch):
    monkeypatch.setattr(office, "MOST_NODES", 100)


def saved(tmp_path, data: bytes, **parts: bytes):
    path = tmp_path / "file.docx"
    path.write_bytes(data)
    with zipfile.ZipFile(path, "a") as archive:
        for name, part in parts.items():
            archive.writestr(f"word/{name}", part)
    return path


def test_an_ordinary_file_opens(tmp_path, few):
    assert office.opened(saved(tmp_path, word_file(p("Ugovor")))).main_document_part


def test_xml_denser_than_a_reader_takes_on_is_refused(tmp_path, few):
    with pytest.raises(TooLarge):
        office.opened(saved(tmp_path, word_file("<w:p/>" * 200)))


def test_attributes_count_as_well_as_elements(tmp_path, few):
    attributes = " ".join(f'w:a{number}="1"' for number in range(200))
    with pytest.raises(TooLarge):
        office.opened(saved(tmp_path, word_file(f"<w:p {attributes}/>")))


def test_namespaces_and_comments_count_too(tmp_path, few):
    declared = " ".join(f'xmlns:n{number}="urn:n"' for number in range(200))
    with pytest.raises(TooLarge):
        office.opened(saved(tmp_path, word_file(p("x")), a=f"<a {declared}/>".encode()))
    (tmp_path / "file.docx").unlink()
    with pytest.raises(TooLarge):
        office.opened(saved(tmp_path, word_file(p("x")), a=b"<a>" + b"<!---->" * 200 + b"</a>"))


def test_a_part_counts_whatever_it_is_called(tmp_path, few):
    dense = f"<w:b {NAMESPACE}>".encode() + b"<w:p/>" * 200 + b"</w:b>"
    with pytest.raises(TooLarge):
        office.opened(saved(tmp_path, word_file(p("x")), **{"picture.bin": dense}))


def test_a_part_that_is_not_xml_counts_for_nothing(tmp_path, few):
    picture = b"\x89PNG\r\n" + b"<a/>" * 1000
    assert office.opened(saved(tmp_path, word_file(p("x")), **{"p.png": picture}))


def test_a_damaged_part_is_unreadable(tmp_path):
    path = saved(tmp_path, word_file(p("Ugovor")))
    with zipfile.ZipFile(path) as archive:
        part = archive.getinfo("word/document.xml")
    data = bytearray(path.read_bytes())
    start = part.header_offset + 30 + len(part.filename)
    data[start : start + 16] = b"\xff" * 16
    path.write_bytes(data)
    with pytest.raises(Unreadable):
        office.opened(path)
