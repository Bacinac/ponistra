"""The installation's off-site copy (D15, S1): the local repository mirrored file by file into an
S3 bucket whose own rule refuses deleting or overwriting an object for LOCKED days, so a server
taken over cannot wipe it. restic's files are written once and never changed, so the mirror only
adds; its lock files stay home, since a locked bucket could never remove them, and the copy is
read without one. A restic snapshot leans on files as old as the repository, so the mirror
starts a new generation with every file once PERIOD has passed: the newest generation is whole
and still locked, and the ones before go as their locks run out."""

import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from logging import getLogger
from pathlib import Path

import psycopg
from anyio import sleep
from django.utils import timezone

from apps.blobs import store
from apps.core import sealed
from apps.core.asyncdb import database

from . import backups
from .bucket import Bucket, Refused, Unreachable
from .models import Offsite

log = getLogger(__name__)

PERIOD = timedelta(days=28)
LOCKED = 30
ORDER = ("config", "keys", "data", "index", "snapshots")
NAMED = re.compile(r"[0-9a-f]{64}")
EMERGENCY = "emergency"
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CHECK_TIMEOUT = 15
PARTS = PERIOD.days
TRIAL = timedelta(days=30)
REMOTE = ("--no-lock", "--no-cache", "-o", "s3.region=auto")


class Unavailable(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def offsite() -> Offsite | None:
    return Offsite.objects.filter(pk=1).first()


def opened(found: Offsite) -> str | None:
    return sealed.opened("offsite secret", found.secret)


def unsealed(found: Offsite) -> str:
    if (secret := opened(found)) is None:
        raise backups.Failed("the installation's secret key no longer opens the off-site secret")
    return secret


def bucket(found: Offsite) -> Bucket:
    return Bucket(found.endpoint, found.bucket, found.access_key, unsealed(found))


def describe(found: Offsite | None, newest: datetime | None) -> dict | None:
    if found is None:
        return None
    behind = newest is not None and (found.mirrored_at is None or found.mirrored_at < newest)
    return {
        "endpoint": found.endpoint,
        "bucket": found.bucket,
        "access_key": found.access_key,
        "hint": found.hint,
        "lost": opened(found) is None,
        "generation": found.generation,
        "mirrored_at": found.mirrored_at,
        "protected": found.protected,
        "error": found.error,
        "checked_at": found.checked_at,
        "check_error": found.check_error,
        "tried_at": found.tried_at,
        "trial": found.trial,
        "trial_error": found.trial_error,
        "late": bool(found.error) or (behind and timezone.now() - newest > backups.AGAIN),
    }


def checked(endpoint: str, name: str, access_key: str, secret: str) -> None:
    """Whether the bucket answers to the key pair."""
    try:
        Bucket(endpoint, name, access_key, secret, timeout=CHECK_TIMEOUT).listed("", "/")
    except Unreachable:
        raise Unavailable("offsite_unreachable") from None
    except Refused as refused:
        raise Unavailable(
            "offsite_no_bucket" if refused.code == "NoSuchBucket" else "offsite_refused"
        ) from None


def change(user, endpoint: str, name: str, access_key: str, secret: str | None) -> Offsite:
    """The bucket the snapshots go to, checked first; the secret may stay only with the same
    bucket and key."""
    found = offsite()
    if secret is None:
        same = found and (found.endpoint, found.bucket, found.access_key) == (
            endpoint,
            name,
            access_key,
        )
        if not same or (secret := opened(found)) is None:
            raise Unavailable("offsite_secret_needed")
    checked(endpoint, name, access_key, secret)
    found, _ = Offsite.objects.update_or_create(
        pk=1,
        defaults={
            "endpoint": endpoint,
            "bucket": name,
            "access_key": access_key,
            "secret": sealed.seal("offsite secret", secret),
            "hint": secret[-4:],
            "changed_by": user,
            "changed_at": timezone.now(),
            "generation": "",
            "mirrored_at": None,
            "protected": None,
            "error": "",
            "checked_at": None,
            "check_error": "",
            "tried_at": None,
            "trial": None,
            "trial_error": "",
        },
    )
    return found


def configured(user, endpoint: str, name: str, access_key: str, secret: str | None):
    """Changes the bucket and returns it with a new emergency key, since the kit printed before
    names the old one."""
    with busy():
        found = change(user, endpoint, name, access_key, secret)
        return found, emergency()


def reissued() -> str:
    with busy():
        return emergency()


@contextmanager
def busy():
    try:
        with backups.alone(wait=False):
            yield
    except backups.Busy:
        raise Unavailable("offsite_busy") from None


def emergency() -> str:
    """A new emergency key in place of the one before. Printed in the recovery kit and kept
    nowhere else, it opens the snapshots once this server and its .env are gone."""
    key = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(6))
    with backups.alone():
        backups.repository()
        added = backups.run(
            "restic",
            *("key", "add", "--new-password-file=/dev/stdin", f"--host={backups.HOST}"),
            f"--user={EMERGENCY}",
            input=key,
        )
        kept = re.search(r"ID ([0-9a-f]{64})", added).group(1)
        for found in json.loads(backups.restic("key", "list", "--json")):
            if found["userName"] == EMERGENCY and found["id"] != kept:
                backups.restic("key", "remove", found["id"])
    return key


def kit(found: Offsite, key: str) -> dict:
    return {
        "endpoint": found.endpoint,
        "bucket": found.bucket,
        "access_key": found.access_key,
        "secret": opened(found),
        "emergency": key,
    }


def contents(path: Path) -> bytes:
    data = path.read_bytes()
    if NAMED.fullmatch(path.name) and hashlib.sha256(data).hexdigest() != path.name:
        raise backups.Failed(f"{path} does not match its name: the local repository is damaged")
    return data


def files(root: Path, part: str) -> list[Path]:
    path = root / part
    if path.is_file():
        return [path]
    return sorted(found for found in path.rglob("*") if found.is_file())


def current(target: Bucket) -> str:
    """The generation the mirror adds to, a new one once the newest is PERIOD old. Its canary is
    the first object written to it, which the lock must still hold when the generation ends."""
    generations = target.generations()
    today = timezone.localdate()
    if generations and date.fromisoformat(generations[-1]) > today - PERIOD:
        return generations[-1]
    generation = today.isoformat()
    target.put(f"{generation}.canary")
    return generation


def expire(target: Bucket, kept: str) -> None:
    """Takes away the generations before the one kept, oldest objects first, as far as their
    locks let it."""
    for generation in target.generations():
        if generation >= kept:
            continue
        items, _ = target.listed(generation)
        for item in sorted(items, key=lambda item: item.modified):
            if not target.delete(item.key):
                break


def mirror(found: Offsite) -> tuple[str, bool]:
    """Copies what the bucket lacks of the repository, the snapshots last so each arrives after
    what it needs; returns the generation and whether the bucket refused to delete its canary."""
    target = bucket(found)
    root = Path(os.environ["RESTIC_REPOSITORY"])
    with backups.alone():
        backups.repository()
        generation = current(target)
        held = target.read(f"{generation}/config")
        if held is not None and held != (root / "config").read_bytes():
            raise backups.Failed(
                f"generation {generation} in the bucket holds another installation's repository"
            )
        there = {item.key for item in target.listed(f"{generation}/")[0]}
        for part in ORDER:
            for path in files(root, part):
                key = f"{generation}/{path.relative_to(root).as_posix()}"
                if key not in there:
                    target.put(key, contents(path))
    canary = f"{generation}.canary"
    protected = not target.delete(canary)
    if not protected:
        target.put(canary)
    expire(target, generation)
    return generation, protected


def mirrored() -> None:
    """Mirrors and records how it went, against the setting it began with."""
    found = offsite()
    same = Offsite.objects.filter(pk=1, changed_at=found.changed_at)
    try:
        generation, protected = mirror(found)
    except (backups.Failed, Unreachable, Refused, OSError) as failed:
        same.update(error=str(failed))
        raise
    same.update(generation=generation, protected=protected, mirrored_at=timezone.now(), error="")


def remote(found: Offsite) -> dict:
    """restic's environment for the generation last mirrored, straight from the bucket."""
    return {
        **os.environ,
        "RESTIC_REPOSITORY": f"s3:{found.endpoint}/{found.bucket}/{found.generation}",
        "AWS_ACCESS_KEY_ID": found.access_key,
        "AWS_SECRET_ACCESS_KEY": unsealed(found),
    }


def remotely(found: Offsite, command: str, *arguments: str) -> str:
    # Without a lock: the bucket would never let restic remove one.
    return backups.run("restic", command, *REMOTE, *arguments, env=remote(found))


def verify(found: Offsite) -> None:
    """Checks the generation as restic checks a repository, reading one PARTS-th of its packs a
    night in turn, so each pack is read before the generation gives way."""
    part = (timezone.localdate() - date.fromisoformat(found.generation)).days % PARTS + 1
    remotely(found, "check", f"--read-data-subset={part}/{PARTS}")


def attempt(found: Offsite) -> dict:
    """Restores the database of the bucket's newest snapshot with all the WAL after it into a
    cluster of its own, checks that the copy holds each file that database names, then removes
    the cluster."""
    into = Path(tempfile.mkdtemp(prefix="trial-"))
    try:
        restored = backups.recover("latest", into, None, remote(found), REMOTE)
    finally:
        shutil.rmtree(into)
    files = restored.between or restored.snapshot
    held = {
        Path(entry["path"]).name
        for entry in map(
            json.loads,
            remotely(
                found, "ls", "--json", "--recursive", files["id"], str(store.root())
            ).splitlines(),
        )
        if entry.get("type") == "file"
    }
    if missing := restored.named - held:
        raise backups.Failed(
            f"snapshot {files['short_id']} lacks {len(missing)} of the files its database names"
        )
    return {
        "snapshot": restored.snapshot["short_id"],
        "time": files["time"],
        "nodes": restored.nodes,
        "files": len(restored.named),
    }


def examined() -> None:
    """Once a day after a mirror, checks the copy in the bucket, and after a check restores it on
    trial when TRIAL has passed or the last trial failed."""
    found = offsite()
    if found is None or found.mirrored_at is None or found.error:
        return
    if found.checked_at and timezone.localdate(found.checked_at) >= timezone.localdate(
        found.mirrored_at
    ):
        return
    same = Offsite.objects.filter(pk=1, changed_at=found.changed_at)
    try:
        verify(found)
    except (backups.Failed, OSError) as failed:
        log.error("backups: the off-site copy failed its check: %s", failed)
        same.update(checked_at=timezone.now(), check_error=str(failed))
        return
    same.update(checked_at=timezone.now(), check_error="")
    if found.tried_at and not found.trial_error and timezone.now() - found.tried_at < TRIAL:
        return
    try:
        trial = attempt(found)
    except (backups.Failed, OSError, psycopg.Error) as failed:
        log.error("backups: the trial restore of the off-site copy failed: %s", failed)
        same.update(tried_at=timezone.now(), trial_error=str(failed))
        return
    same.update(tried_at=timezone.now(), trial=trial, trial_error="")


def state(found: Offsite) -> tuple:
    """What a mirror would change: the setting, and the snapshots and keys the repository holds,
    since a new recovery kit's key must reach the bucket before the next night."""
    root = Path(os.environ["RESTIC_REPOSITORY"])
    names = frozenset(
        f"{part}/{path.name}"
        for part in ("keys", "snapshots")
        if (root / part).is_dir()
        for path in (root / part).iterdir()
    )
    return found.changed_at, names


async def follow() -> None:
    """Mirrors each new snapshot while the server runs, and once at start, then examines the
    copy."""
    done = None
    while True:
        wait = backups.LOOK
        try:
            found = await database(offsite)()
            if found is not None:
                if (now := state(found)) != done:
                    await database(mirrored, own_thread=True)()
                    done = now
                await database(examined, own_thread=True)()
        except Exception:
            log.exception("backups: mirroring off-site failed")
            wait = backups.AGAIN
        await sleep(wait.total_seconds())
