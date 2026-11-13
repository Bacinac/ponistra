import io
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings as django_settings
from django.db import connection
from django.utils import timezone

from apps.backups import backups
from apps.blobs import store
from apps.blobs.models import Blob
from apps.users.models import User

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def into(tmp_path):
    return tmp_path / "restoring"


@pytest.fixture
def emails(monkeypatch):
    """The users each database a restore brings back holds."""
    seen = []
    read = backups.read

    def reading(restored):
        seen.append(
            [row[0] for row in restored.execute("SELECT email FROM users_user ORDER BY id")]
        )
        return read(restored)

    monkeypatch.setattr(backups, "read", reading)
    return seen


def listed(snapshot: str) -> set[str]:
    lines = backups.restic("ls", "--json", snapshot).splitlines()
    return {entry["path"] for entry in map(json.loads, lines[1:])}


def test_a_snapshot_holds_the_database_the_files_and_env():
    blob = store.put(io.BytesIO(b"kept bytes"))
    snapshot = backups.backup("before-0.2.0")
    paths = listed(snapshot)
    assert str(backups.BASE / "PG_VERSION") in paths
    assert str(store.path_of(blob.sha256)) in paths
    assert str(django_settings.BACKUP_ENV) in paths
    [described] = backups.snapshots(snapshot)
    assert (described["id"], described["version"], described["tags"]) == (
        snapshot,
        "0.1.99",
        ["before-0.2.0"],
    )
    assert backups.place(described["starts"])
    assert described["time"].tzinfo is not None


def test_a_lock_a_killed_restic_left_does_not_stop_the_next_snapshot(tmp_path):
    backups.backup()
    held = tmp_path / "large"
    held.write_bytes(os.urandom(64 << 20))
    locks = tmp_path / "repository" / "locks"

    def left() -> list[str]:
        return [path.name for path in locks.iterdir() if re.fullmatch(r"[0-9a-f]{64}", path.name)]

    killed = subprocess.Popen(["restic", "backup", "--quiet", str(held)])
    while not left():
        time.sleep(0.05)
    killed.send_signal(signal.SIGKILL)
    killed.wait()
    assert left()
    backups.backup()
    assert not left()


def test_a_slot_a_killed_snapshot_left_does_not_stop_the_next_and_none_stays():
    name = "base_" + django_settings.DATABASES["default"]["NAME"].lower()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_create_physical_replication_slot(%s, true)", [name])
    backups.backup()
    with connection.cursor() as cursor:
        cursor.execute("SELECT slot_name FROM pg_replication_slots WHERE slot_name LIKE 'base_%'")
        assert name not in [row[0] for row in cursor.fetchall()]


def test_without_env_no_snapshot_is_taken(settings, tmp_path):
    settings.BACKUP_ENV = tmp_path / "missing"
    with pytest.raises(backups.Failed, match="missing"):
        backups.backup()


def test_a_restore_builds_the_database_as_the_snapshot_left_it_and_puts_back_its_files(
    into, emails
):
    User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    blob = store.put(io.BytesIO(b"bytes the snapshot keeps"))
    snapshot = backups.backup()
    User.objects.create_user("bruno@example.com", "Kamen-Most-Rijeka-71")
    store.path_of(blob.sha256).unlink()
    assert backups.restore(snapshot, into) == "0.1.99"
    assert store.path_of(blob.sha256).read_bytes() == b"bytes the snapshot keeps"
    assert emails == [["ana@example.com"]]
    assert (into / "data" / "PG_VERSION").read_text().strip() == "18"
    assert not (into / "data" / "recovery.signal").exists()


def test_a_restore_to_a_moment_replays_the_wal_and_brings_back_the_files_collected_since(
    into, emails, archived, repository
):
    User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    backups.backup()
    User.objects.create_user("bruno@example.com", "Kamen-Most-Rijeka-71")
    blob = store.put(io.BytesIO(b"bytes written after the snapshot"))
    time.sleep(0.05)
    moment = timezone.localtime().replace(tzinfo=None)
    time.sleep(0.05)
    User.objects.create_user("cvita@example.com", "Kamen-Most-Rijeka-71")
    Blob.objects.filter(pk=blob.pk).delete()
    store.collect()
    archived()
    backups.between()
    for path in repository.iterdir():
        path.unlink()
    assert not store.path_of(blob.sha256).exists()
    assert backups.restore(moment.isoformat(), into) == "0.1.99"
    assert emails == [["ana@example.com", "bruno@example.com"]]
    assert store.path_of(blob.sha256).read_bytes() == b"bytes written after the snapshot"
    assert list(repository.glob("*.history.gz"))


def test_the_latest_restore_replays_all_the_wal_there_is(into, emails, archived):
    backups.backup()
    User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    archived()
    backups.restore("latest", into)
    assert emails == [["ana@example.com"]]


def test_a_moment_the_wal_does_not_reach_fails_loudly(into, archived):
    backups.backup()
    archived()
    later = timezone.localtime().replace(tzinfo=None) + timedelta(hours=1)
    with pytest.raises(backups.Failed, match="the WAL reaches only"):
        backups.restore(later.isoformat(), into)
    with pytest.raises(backups.Failed, match="no snapshot holds the database before"):
        backups.restore("2020-01-01 12:00", into)


def test_a_snapshot_with_a_dump_of_the_database_is_not_restored_here(into, tmp_path):
    dump = tmp_path / "database.dump"
    dump.write_bytes(b"PGDMP")
    backups.repository()
    backups.restic("backup", "--quiet", f"--host={backups.HOST}", str(dump))
    [snapshot] = backups.snapshots()
    with pytest.raises(backups.Failed, match="holds a dump of the database"):
        backups.restore(snapshot["id"], into)


def test_the_archived_segments_stay_until_the_snapshot_before_the_newest_needs_none(repository):
    old = repository / "000000010000000000000001.gz"
    history = repository / "00000002.history.gz"
    for path in (old, history):
        path.write_bytes(b"")
    backups.backup()
    assert old.exists()
    backups.backup()
    assert not old.exists() and history.exists()


def test_between_snapshots_the_newest_holding_each_oldest_segment_is_kept(repository):
    (repository / "000000010000000000000001.gz").write_bytes(b"one")
    backups.between()
    backups.between()
    assert len(backups.found(backups.BETWEEN)) == 1
    (repository / "000000010000000000000002.gz").write_bytes(b"two")
    backups.between()
    [kept] = backups.found(backups.BETWEEN)
    assert backups.tagged(kept, backups.HOLDS) == "000000010000000000000001.gz"
    (repository / "000000010000000000000001.gz").unlink()
    backups.between()
    assert len(backups.found(backups.BETWEEN)) == 2


def test_a_segment_waiting_to_be_taken_makes_the_archive_late(repository):
    segment = repository / "000000010000000000000001.gz"
    segment.write_bytes(b"")
    assert backups.archive()["late"]
    backups.between()
    assert backups.archive() == {
        "at": backups.when(backups.found(backups.BETWEEN)[-1]),
        "error": "",
        "late": False,
    }
    taken = (timezone.now() + 3 * backups.TAKEN).timestamp()
    os.utime(segment, (taken, taken))
    assert backups.archive()["late"]


def test_the_code_workspace_kept_here_is_in_the_snapshot_and_comes_back_with_a_restore(
    settings, tmp_path, into
):
    settings.WORKSPACE_ROOT = tmp_path / "workspace"
    kept = settings.WORKSPACE_ROOT / "projekt" / "main.py"
    kept.parent.mkdir(parents=True)
    kept.write_text("print(1)\n")
    settings.WORKSPACE = ""
    assert str(kept) not in listed(backups.backup())
    settings.WORKSPACE = "ivo@example.com"
    settings.WORKSPACE_URL = "https://code.example.com"
    assert str(kept) not in listed(backups.backup())
    settings.WORKSPACE_URL = ""
    snapshot = backups.backup()
    assert str(kept) in listed(snapshot)
    kept.unlink()
    backups.restore(snapshot, into)
    assert kept.read_text() == "print(1)\n"


def test_an_unknown_snapshot_fails_loudly(into):
    backups.backup()
    with pytest.raises(backups.Failed, match="no snapshot deadbeef"):
        backups.restore("deadbeef", into)


def test_without_a_repository_there_are_no_snapshots():
    assert backups.snapshots() == []


ZAGREB = ZoneInfo("Europe/Zagreb")


@pytest.mark.parametrize(
    ("newest", "due"),
    [
        (datetime(2026, 10, 23, 15, 30), datetime(2026, 10, 24, 3, 0)),
        (datetime(2026, 10, 24, 2, 0), datetime(2026, 10, 24, 3, 0)),
        (datetime(2026, 10, 24, 3, 0, 5), datetime(2026, 10, 25, 3, 0)),
        (datetime(2026, 10, 24, 23, 0), datetime(2026, 10, 25, 3, 0)),
    ],
)
def test_the_next_snapshot_is_due_the_night_after_the_newest(newest, due):
    older = datetime(2026, 10, 1, 3, 0, tzinfo=ZAGREB)
    found = [
        {"time": older, "starts": "x"},
        {"time": newest.replace(tzinfo=ZAGREB), "starts": "x"},
        {"time": newest.replace(tzinfo=ZAGREB) + timedelta(hours=1), "starts": None},
    ]
    assert backups.due(found) == due.replace(tzinfo=ZAGREB)


def test_without_snapshots_one_is_due_at_once_and_late():
    assert (timezone.now() - backups.due([])).total_seconds() < 1
    assert backups.late([])


def test_a_night_missed_is_late():
    yesterday = timezone.localtime() - timedelta(days=1, hours=2)
    assert backups.late([{"time": yesterday, "starts": "x"}])
    assert not backups.late([{"time": timezone.localtime(), "starts": "x"}])
    assert backups.late([{"time": timezone.localtime(), "starts": None}])
