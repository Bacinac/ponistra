"""The installation's snapshots (D15, S1): a base backup of the database, the files, .env and the
owner's code workspace (D34) together in one restic snapshot, in the repository RESTIC_REPOSITORY
names and encrypted with RESTIC_PASSWORD. Between two snapshots, every TAKEN, the WAL Postgres
archived into SPOOL and the files go into a snapshot of their own, so the installation can be
restored to any moment of the last WINDOW (S8)."""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from logging import getLogger
from pathlib import Path
from string import hexdigits

import psycopg
from anyio import sleep
from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.blobs import store
from apps.core.asyncdb import database
from apps.workspace.views import kept_here

log = getLogger(__name__)

# restic records a snapshot under the host that took it, and each container has a name of its own.
# The product's old name, kept: the snapshots taken so far are listed, pruned and checked by it.
HOST = "scriptor"
# The snapshots between them, under a name of their own so that neither's forget sees the other.
BETWEEN = "ponistra-wal"
BASE = Path("/tmp/backup/database")
SPOOL = Path("/wal")
SERVER = Path("/usr/lib/postgresql/18/bin")
KEEP = ["--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "12"]
NO_REPOSITORY = 10
VERSION = "version:"
# The WAL segment a snapshot's database starts from, and the oldest one a snapshot between holds.
STARTS = "wal:"
HOLDS = "from:"
LOCK = 0x5C21B10C
LOOK = timedelta(minutes=10)
AGAIN = timedelta(hours=1)
TAKEN = timedelta(minutes=15)
WINDOW = store.KEPT
UNREACHED = "recovery ended before configured recovery target was reached"


class Failed(Exception):
    pass


class Busy(Exception):
    pass


@dataclass
class Recovered:
    snapshot: dict
    between: dict | None
    version: str
    named: set[str]
    nodes: int


def run(*command: str, **options) -> str:
    done = subprocess.run(command, capture_output=True, text=True, **options)
    if done.returncode:
        raise Failed(f"{command[0]} {command[1]}: {done.stderr.strip()}")
    return done.stdout


def restic(*arguments: str, env: dict | None = None) -> str:
    return run("restic", *arguments, env=env)


def postgres() -> dict:
    database = settings.DATABASES["default"]
    return {
        **os.environ,
        "PGHOST": database["HOST"],
        "PGPORT": str(database["PORT"]),
        "PGUSER": database["USER"],
        "PGPASSWORD": database["PASSWORD"],
    }


@contextmanager
def reserved():
    """A slot made before the base's checkpoint, so the WAL from where the base starts stays on
    the server until the base has streamed it: pg_basebackup's own slot is made only after
    that checkpoint, by when a busy server may have archived and removed the first segment."""
    name = "base_" + re.sub(r"[^a-z0-9_]", "_", settings.DATABASES["default"]["NAME"].lower())
    with connection.cursor() as cursor:
        dropped(cursor, name)
        cursor.execute("SELECT pg_create_physical_replication_slot(%s, true)", [name])
    try:
        yield name
    finally:
        with connection.cursor() as cursor:
            dropped(cursor, name)


def dropped(cursor, name: str) -> None:
    for _ in range(50):
        cursor.execute("SELECT active FROM pg_replication_slots WHERE slot_name = %s", [name])
        held = cursor.fetchone()
        if held is None:
            return
        if not held[0]:
            cursor.execute("SELECT pg_drop_replication_slot(%s)", [name])
            return
        time.sleep(0.2)
    raise Failed(f"replication slot {name} is still in use")


@contextmanager
def alone(wait: bool = True):
    """One snapshot or mirror at a time: they share the base's path and the repository's files.
    Without waiting it refuses while another runs."""
    with connection.cursor() as cursor:
        if wait:
            cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK])
        else:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK])
            if not cursor.fetchone()[0]:
                raise Busy
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK])


def repository() -> None:
    """The repository, made on first use and freed of the locks a killed restic left behind,
    which would refuse every exclusive command after it."""
    probe = subprocess.run(["restic", "--no-lock", "cat", "config"], capture_output=True, text=True)
    if probe.returncode == NO_REPOSITORY:
        restic("init")
    elif probe.returncode:
        raise Failed(f"restic cat: {probe.stderr.strip()}")
    else:
        restic("unlock")


def place(name: str) -> str | None:
    """Where a WAL file falls in the sequence, whatever its timeline; none for a timeline's
    history."""
    head = name[:24]
    if len(head) == 24 and all(character in hexdigits for character in head):
        return head[8:]
    return None


def first(base: Path) -> str:
    """The segment a base backup's recovery starts from, as its label names it."""
    for line in (base / "backup_label").read_text().splitlines():
        if line.startswith("START WAL LOCATION:"):
            return line.rsplit("file ", 1)[1].rstrip(")")
    raise Failed(f"{base}/backup_label names no first segment")


def tagged(snapshot: dict, prefix: str) -> str | None:
    return next(
        (tag.removeprefix(prefix) for tag in snapshot.get("tags", []) if tag.startswith(prefix)),
        None,
    )


def when(snapshot: dict) -> datetime:
    return timezone.localtime(datetime.fromisoformat(snapshot["time"]))


def found(host: str, *ids: str, env: dict | None = None, options: tuple = ()) -> list[dict]:
    """restic's own record of the snapshots a host took, oldest first."""
    # Read without a lock, so a listing does not wait for a prune.
    listed = subprocess.run(
        ["restic", "--no-lock", *options, "snapshots", "--json", f"--host={host}", *ids],
        capture_output=True,
        text=True,
        env=env,
    )
    if listed.returncode == NO_REPOSITORY and not ids:
        return []
    if listed.returncode:
        raise Failed(f"restic snapshots: {listed.stderr.strip()}")
    return sorted(json.loads(listed.stdout or "[]"), key=when)


def snapshots(*ids: str) -> list[dict]:
    return [
        {
            "id": snapshot["short_id"],
            "time": when(snapshot),
            "version": tagged(snapshot, VERSION),
            "starts": tagged(snapshot, STARTS),
            "tags": [
                tag for tag in snapshot.get("tags", []) if not tag.startswith((VERSION, STARTS))
            ],
        }
        for snapshot in found(HOST, *ids)
    ]


def backup(*tags: str) -> str:
    """Takes a snapshot and returns its id, then the WAL and the files since, and lets go of the
    archived segments no restore needs from the disk any more. Collection waits meanwhile, so
    every file the database refers to is still there when it is read."""
    if not settings.BACKUP_ENV.is_file():
        raise Failed(
            f"{settings.BACKUP_ENV} is missing, and a snapshot cannot be opened without it"
        )
    version = json.loads(settings.REVISION_FILE.read_text())["version"]
    with alone():
        repository()
        shutil.rmtree(BASE, ignore_errors=True)
        BASE.parent.mkdir(parents=True, exist_ok=True)
        with store.held():
            try:
                with reserved() as slot:
                    # File by file and uncompressed, so restic finds what has not changed since.
                    run(
                        *("pg_basebackup", f"--pgdata={BASE}", "--wal-method=stream"),
                        *(f"--slot={slot}", "--checkpoint=fast", "--no-sync"),
                        env=postgres(),
                    )
                report = restic(
                    *("backup", "--json", "--quiet", f"--host={HOST}", f"--tag={VERSION}{version}"),
                    f"--tag={STARTS}{first(BASE)}",
                    *(f"--tag={tag}" for tag in tags),
                    *(str(BASE), str(store.root()), str(settings.BACKUP_ENV)),
                    *([str(settings.WORKSPACE_ROOT)] if kept_here() else []),
                )
            finally:
                shutil.rmtree(BASE, ignore_errors=True)
        take()
        trim()
        restic("forget", f"--host={HOST}", "--group-by=host", *KEEP, "--prune")
    lines = map(json.loads, report.splitlines())
    summary = next(line for line in lines if line.get("message_type") == "summary")
    return summary["snapshot_id"][:8]


def take() -> None:
    """The WAL archived so far and the files, in a snapshot between snapshots unless nothing
    changed since the last; of those it keeps for WINDOW the newest holding each oldest segment,
    as it holds all the earlier ones did."""
    oldest = min(filter(place, spooled()), key=place, default=None)
    with store.held():
        restic(
            *("backup", "--json", "--quiet", "--skip-if-unchanged", f"--host={BETWEEN}"),
            *([f"--tag={HOLDS}{oldest}"] if oldest else []),
            f"--exclude={SPOOL}/.*",
            *(str(SPOOL), str(store.root())),
        )
    taken = found(BETWEEN)
    newest = {tagged(snapshot, HOLDS): snapshot for snapshot in taken}
    kept = {
        snapshot["id"] for snapshot in newest.values() if when(snapshot) >= timezone.now() - WINDOW
    }
    if gone := [snapshot["id"] for snapshot in taken if snapshot["id"] not in kept]:
        restic("forget", *gone)


def spooled() -> list[str]:
    return sorted(path.name for path in SPOOL.iterdir() if not path.name.startswith("."))


def trim() -> None:
    """Deletes from SPOOL, once taken, the segments before the one the snapshot before the newest
    starts from: a restore to any moment since it starts from one of the two, and finds them in
    every snapshot between taken after it."""
    bases = [snapshot for snapshot in found(HOST) if tagged(snapshot, STARTS)]
    if len(bases) < 2:
        return
    reached = place(tagged(bases[-2], STARTS))
    for name in spooled():
        if (at := place(name)) and at < reached:
            (SPOOL / name).unlink()


def between() -> None:
    with alone():
        repository()
        take()


def chosen(which: str, env: dict | None = None, options: tuple = ()):
    """The snapshot and the snapshot between to restore which from, and the moment to stop at:
    a snapshot as it was taken, latest as far as the WAL reaches, or a moment as YYYY-MM-DD HH:MM
    in local time."""
    bases = found(HOST, env=env, options=options)
    if which != "latest":
        named = [snapshot for snapshot in bases if snapshot["id"].startswith(which)]
        if named:
            if not tagged(named[0], STARTS):
                raise Failed(f"snapshot {which} holds a dump of the database, not a base")
            return named[0], None, None
    bases = [snapshot for snapshot in bases if tagged(snapshot, STARTS)]
    moment = None
    if which != "latest":
        try:
            moment = datetime.fromisoformat(which)
        except ValueError:
            raise Failed(f"no snapshot {which}") from None
        if timezone.is_naive(moment):
            moment = timezone.make_aware(moment)
        bases = [snapshot for snapshot in bases if when(snapshot) <= moment]
    if not bases:
        raise Failed(f"no snapshot holds the database before {which}")
    base = bases[-1]
    starts = place(tagged(base, STARTS))
    held = [
        snapshot
        for snapshot in found(BETWEEN, env=env, options=options)
        if (holds := tagged(snapshot, HOLDS)) and place(holds) <= starts
    ]
    after = [snapshot for snapshot in held if moment and when(snapshot) >= moment]
    return base, (after[:1] or held[-1:] or [None])[0], moment


def reach(sources: list[Path]) -> datetime | None:
    """When the newest archived segment was archived: the WAL holds what was written until then."""
    times = [
        path.stat().st_mtime
        for source in sources
        if source.is_dir()
        for path in source.iterdir()
        if place(path.name)
    ]
    return timezone.localtime(datetime.fromtimestamp(max(times), tz=UTC)) if times else None


def fetched(sources: list[Path]) -> str:
    """restore_command: a segment from the first source holding it."""
    tried = " ".join(str(source) for source in sources)
    return (
        f'for d in {tried}; do if [ -f "$d/%f.gz" ]; then gunzip -c "$d/%f.gz" > "%p"; exit $?; '
        "fi; done; exit 1"
    )


def replayed(data: Path, sources: list[Path], target: tuple[str, str] | None) -> dict:
    """Starts Postgres of its own on the restored data, replays the WAL to the target and promotes
    it, reads what a restore checks and stops it, the data left as a cluster Postgres opens."""
    socket = data.parent
    command = [
        str(SERVER / "postgres"),
        *("-D", str(data)),
        *("-c", "listen_addresses=", "-c", f"unix_socket_directories={socket}"),
        *("-c", "archive_mode=off", "-c", f"restore_command={fetched(sources)}"),
        *("-c", "recovery_target_action=promote"),
        *(("-c", "=".join(target)) if target else ()),
    ]
    log_path = socket / "recovery.log"
    with log_path.open("w") as written:
        server = subprocess.Popen(command, stdout=written, stderr=subprocess.STDOUT)
    try:
        while True:
            if server.poll() is not None:
                said = log_path.read_text()
                if UNREACHED in said and target and target[0] == "recovery_target_time":
                    # No transaction committed after the moment in all the WAL there is, which
                    # reaches past it: replayed to its end, the database is as it was then.
                    return replayed(data, sources, None)
                raise Failed("recovery stopped: " + " / ".join(said.strip().splitlines()[-3:]))
            try:
                with psycopg.connect(
                    host=str(socket),
                    dbname=settings.DATABASES["default"]["NAME"],
                    user=settings.DATABASES["default"]["USER"],
                    connect_timeout=2,
                ) as restored:
                    (recovering,) = restored.execute("SELECT pg_is_in_recovery()").fetchone()
                    if not recovering:
                        return read(restored)
            except psycopg.OperationalError:
                pass
            time.sleep(0.2)
    finally:
        if server.poll() is None:
            server.send_signal(signal.SIGINT)
            server.wait()


def read(restored) -> dict:
    migrated = restored.execute("SELECT version FROM backups_migrated").fetchone()
    if migrated is None:
        raise Failed("the restored database names no version that migrated it")
    (version,) = migrated
    (nodes,) = restored.execute("SELECT count(*) FROM documents_node").fetchone()
    named = {sha256 for (sha256,) in restored.execute("SELECT sha256 FROM blobs_blob")}
    return {"version": version, "nodes": nodes, "named": named}


def recover(
    which: str,
    into: Path,
    spool: Path | None,
    env: dict | None = None,
    options: tuple = (),
) -> Recovered:
    """The database as which left it, a cluster in into/data, from a snapshot, the WAL of the
    snapshot between after it and what spool holds yet."""
    base, held, moment = chosen(which, env, options)
    data, wal = into / "data", into / "wal"
    shutil.rmtree(data, ignore_errors=True)
    shutil.rmtree(wal, ignore_errors=True)
    wal.mkdir(parents=True)
    restic("restore", *options, f"{base['id']}:{BASE}", f"--target={data}", env=env)
    sources = [wal, *([spool] if spool else [])]
    if held:
        restic("restore", *options, f"{held['id']}:{SPOOL}", f"--target={wal}", env=env)
    if moment and ((reached := reach(sources)) is None or reached < moment):
        until = f"{reached:%d.%m.%Y. %H:%M}" if reached else "the snapshot itself"
        raise Failed(f"the WAL reaches only {until}")
    (data / "recovery.signal").touch()
    if which != "latest" and moment is None:
        target = ("recovery_target", "immediate")
    elif moment:
        target = ("recovery_target_time", moment.isoformat())
    else:
        target = None
    replay = replayed(data, sources, target)
    return Recovered(base, held, replay["version"], replay["named"], replay["nodes"])


def restore(which: str, into: Path) -> str:
    """Builds in into/data the database as which left it, puts back the files it names beside
    those in use, and returns the version it ran with; the installation's command then puts
    into/data in Postgres's place."""
    recovered = recover(which, into, SPOOL)
    files = recovered.between or recovered.snapshot
    # Files are only added: those the restored database no longer refers to are collected.
    restic("restore", f"{files['id']}:{store.root()}", f"--target={store.root()}")
    workspace = settings.WORKSPACE_ROOT
    if str(workspace) in recovered.snapshot["paths"]:
        restic("restore", f"{recovered.snapshot['id']}:{workspace}", f"--target={workspace}")
    if missing := {sha256 for sha256 in recovered.named if not store.revive(sha256)}:
        raise Failed(f"{len(missing)} of the files the restored database names are in no snapshot")
    # Promoted with archiving off, Postgres left its new timeline's history unarchived, and the
    # next restore must not choose that timeline again.
    for history in (into / "data" / "pg_wal").glob("*.history"):
        if not (SPOOL / f"{history.name}.gz").exists():
            with (SPOOL / f".{history.name}").open("wb") as kept:
                subprocess.run(["gzip", "-1nc", str(history)], stdout=kept, check=True)
            (SPOOL / f".{history.name}").rename(SPOOL / f"{history.name}.gz")
    shutil.rmtree(into / "wal")
    return recovered.version


def archive() -> dict:
    """How archiving the WAL goes: when the WAL and the files were last taken, what stops
    Postgres archiving, and whether a segment waits longer to be taken than it should."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT last_archived_time, last_failed_wal, last_failed_time FROM pg_stat_archiver"
        )
        archived, failed, failed_at = cursor.fetchone()
    error = ""
    if failed_at and (archived is None or failed_at > archived):
        since = timezone.localtime(failed_at)
        error = f"Postgres cannot archive {failed} since {since:%d.%m.%Y. %H:%M}"
    taken = found(BETWEEN)
    at = when(taken[-1]) if taken else None
    waiting = reach([SPOOL])
    late = bool(error) or (waiting is not None and (at is None or waiting - at > 2 * TAKEN))
    return {"at": at, "error": error, "late": late}


def due(found: list[dict]) -> datetime:
    """When the next snapshot is due: at BACKUP_AT after the newest found with a base of the
    database, at once without one."""
    bases = [snapshot for snapshot in found if snapshot["starts"]]
    if not bases:
        return timezone.now()
    newest = timezone.localtime(max(snapshot["time"] for snapshot in bases))
    at = newest.replace(
        hour=settings.BACKUP_AT.hour, minute=settings.BACKUP_AT.minute, second=0, microsecond=0
    )
    return at if at > newest else at + timedelta(days=1)


def late(found: list[dict]) -> bool:
    """Whether the night's snapshot is missing: the nightly retries within AGAIN of a failure."""
    return not any(snapshot["starts"] for snapshot in found) or due(found) < timezone.now() - AGAIN


async def nightly() -> None:
    """Takes a snapshot each night while the server runs, at start the one a night it was down
    for missed, and between them the WAL and the files every TAKEN."""
    taken = None
    while True:
        try:
            wait = due(await database(snapshots, own_thread=True)()) - timezone.now()
            if wait <= timedelta(0):
                await database(backup, own_thread=True)("nightly")
                taken = timezone.now()
                continue
        except Exception:
            log.exception("backups: the nightly snapshot failed")
            wait = AGAIN
        if taken is None or timezone.now() - taken >= TAKEN:
            try:
                await database(between, own_thread=True)()
            except Exception:
                log.exception("backups: taking the WAL and the files failed")
            taken = timezone.now()
        wait = min(wait, TAKEN - (timezone.now() - taken))
        await sleep(min(wait, LOOK).total_seconds())
