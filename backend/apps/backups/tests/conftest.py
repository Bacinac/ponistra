import json
import shutil
import time
from pathlib import Path

import pytest
from django.db import connection
from django.utils import timezone

from apps.backups import backups
from apps.backups.models import Migrated

# Where the database the tests run on archives its WAL: read only, as the installation's own
# snapshots take it from there.
ARCHIVE = Path("/wal")


@pytest.fixture(autouse=True)
def repository(tmp_path, monkeypatch, settings):
    monkeypatch.setenv("RESTIC_REPOSITORY", str(tmp_path / "repository"))
    monkeypatch.setenv("RESTIC_PASSWORD", "test")
    monkeypatch.setenv("RESTIC_CACHE_DIR", str(tmp_path / "cache"))
    env = tmp_path / ".env"
    env.write_text("PONISTRA_SECRET_KEY=kept\n")
    settings.BACKUP_ENV = env
    revision = tmp_path / "revision.json"
    revision.write_text(json.dumps({"version": "0.1.99"}))
    settings.REVISION_FILE = revision
    spool = tmp_path / "wal"
    spool.mkdir()
    monkeypatch.setattr(backups, "SPOOL", spool)
    Migrated.objects.update_or_create(pk=1, defaults={"version": "0.1.99", "at": timezone.now()})
    return spool


@pytest.fixture
def archived(repository):
    """Has Postgres archive what it wrote so far and copies the archive into the test's spool."""

    def archive() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_walfile_name(pg_switch_wal())")
            (closed,) = cursor.fetchone()
            deadline = time.monotonic() + 30
            while not (ARCHIVE / f"{closed}.gz").exists():
                assert time.monotonic() < deadline, f"Postgres did not archive {closed}"
                time.sleep(0.1)
        for path in ARCHIVE.iterdir():
            if not path.name.startswith(".") and not (repository / path.name).exists():
                shutil.copy2(path, repository / path.name)

    return archive
