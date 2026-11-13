import os
import signal
from datetime import UTC, datetime

import pytest

from apps.documents.models import Node
from apps.imports.reading import Remark, Thread, TooLarge, Unreadable
from apps.reader import client, reads, serve, wire


def _probe(monkeypatch, run, seconds=10):
    monkeypatch.setitem(reads.READS, "probe", reads.Read(run, seconds))


def test_a_value_passes_as_it_was():
    value = {
        "thread": Thread([Remark("Ana", datetime(2026, 11, 10, 14, tzinfo=UTC), "x")], False),
        "pages": {1: [(0.5, 1.0, 2.0, 3.0)]},
        "names": {"a", "b"},
        "raw": b"\x00\xff",
        "kind": Node.Kind.FILE,
    }
    passed = wire.parsed(wire.line(value))
    assert passed == {**value, "kind": "file"}
    assert type(passed["pages"][1][0]) is tuple


def test_a_type_outside_the_set_is_refused_both_ways():
    with pytest.raises(TypeError):
        wire.line(object())
    with pytest.raises(TypeError):
        wire.line({wire.TAG: "x"})
    with pytest.raises(ValueError, match="'Popen'"):
        wire.parsed(b'{"\\u0000":"Popen","v":{}}')


def test_a_reading_sends_lines_and_files_before_its_end(monkeypatch):
    def run(paths, head, out):
        out.send({"got": paths[0].read_bytes(), "head": head["given"]})
        out.data(b"made")
        return paths[1].stat().st_size

    _probe(monkeypatch, run)
    with client.answered("probe", b"one", b"three", given=(1, 2)) as answer:
        assert answer.next() == {"got": b"one", "head": (1, 2)}
        assert answer.next() is None
        assert answer.value == 5
        assert answer.files[0].read_bytes() == b"made"
        kept = answer.files[0]
    assert not kept.exists()


def test_the_reading_reaches_no_database(monkeypatch):
    _probe(monkeypatch, lambda paths, head, out: Node.objects.count())
    with pytest.raises(Unreadable, match="reaches no database"):
        client.ask("probe", b"x")


def test_a_reading_past_its_memory_is_too_large(monkeypatch):
    _probe(monkeypatch, lambda paths, head, out: len(bytearray(serve.MEMORY)))
    with pytest.raises(TooLarge):
        client.ask("probe", b"x")


@pytest.mark.parametrize(
    ("ended", "raised"), [(signal.SIGKILL, TooLarge), (signal.SIGTERM, Unreadable)]
)
def test_a_reading_that_dies_is_answered_by_how(monkeypatch, ended, raised):
    _probe(monkeypatch, lambda paths, head, out: os.kill(os.getpid(), ended))
    with pytest.raises(raised, match=f"signal {ended.value}"):
        client.ask("probe", b"x")


def test_a_failure_the_backend_knows_is_raised_as_it(monkeypatch):
    def run(paths, head, out):
        raise Unreadable("broken")

    _probe(monkeypatch, run)
    with pytest.raises(Unreadable, match="broken"):
        client.ask("probe", b"x")


def test_a_file_larger_than_the_reader_takes_is_refused_whole(monkeypatch):
    _probe(monkeypatch, lambda paths, head, out: None)
    monkeypatch.setattr(serve, "LARGEST", 1024)
    with pytest.raises(TooLarge):
        client.ask("probe", bytes(4096))
    assert client.ask("probe", b"x") is None


def test_a_kind_the_reader_lacks_is_refused():
    with pytest.raises(RuntimeError, match="400"):
        client.ask("nothing", b"x")


def test_a_reader_that_does_not_answer_is_unavailable(settings):
    settings.READER_URL = "http://127.0.0.1:9"
    with pytest.raises(client.Unavailable):
        client.ask("probe", b"x")
