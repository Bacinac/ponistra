from apps.blobs.tests.office import MACRO, ole, vba_project
from apps.imports import vba


def test_a_container_unpacks_as_the_specification_shows():
    normal = bytes.fromhex(
        "01 2F B0 00 23 61 61 61 62 63 64 65 82 66 00 70 61 67 68 69 6A 01 38 08 61 6B 6C 00 30"
        "6D 6E 6F 70 06 71 02 70 04 10 72 73 74 75 76 10 77 78 79 7A 00 3C"
    )
    plain = bytes.fromhex(
        "01 19 B0 00 61 62 63 64 65 66 67 68 00 69 6A 6B 6C 6D 6E 6F 70 00 71 72 73 74 75 76 2E"
    )
    assert vba.decompressed(normal) == b"#aaabcdefaaaaghijaaaaaklaaamnopqaaaaaaaaaaaarstuvwxyzaaa"
    assert vba.decompressed(plain) == b"abcdefghijklmnopqrstuv."
    assert vba.decompressed(bytes.fromhex("0103B002614500")) == b"a" * 73


def test_the_modules_that_hold_code_come_by_name_without_the_hidden_attribute_lines():
    project = vba_project({"Module1": MACRO, "ThisWorkbook": 'Attribute VB_Name = "X"\r\n'})
    assert vba.source(project) == [
        {"name": "Module1", "code": 'Sub Zbroji()\n    Range("A1") = "Šećer"\nEnd Sub'}
    ]


def test_code_past_the_longest_is_cut(monkeypatch):
    monkeypatch.setattr(vba, "LONGEST", 10)
    project = vba_project({"First": "Sub A()\r\nEnd Sub\r\n", "Second": "Sub B()\r\nEnd Sub\r\n"})
    assert vba.source(project) == [
        {"name": "First", "code": "Sub A()\nEn\n…"},
        {"name": "Second", "code": "\n…"},
    ]


def test_a_project_that_cannot_be_read_shows_no_source():
    assert vba.source(ole({"VBA": b"\0" * 4096})) == []
    assert vba.source(b"not a project") == []
