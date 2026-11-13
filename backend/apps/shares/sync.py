"""Company folders connected to a file server's folders (D37), followed while the server runs: a
copy read again every SHARE_SWEEP, an inbox every INBOX_SWEEP, and either as soon as the
administrator asks."""

import logging
import shutil
import threading
from datetime import timedelta
from pathlib import PurePosixPath
from time import monotonic

from anyio import CancelScope, CapacityLimiter, Event, create_task_group, move_on_after
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.blobs import previews, store
from apps.collab.server import revoke
from apps.core.asyncdb import database, drain, notify
from apps.core.sealed import opened
from apps.documents.models import Node
from apps.documents.views import created, dated
from apps.imports import convert, placed
from apps.retention import kept as retention
from apps.search import extraction

from . import smb
from .models import Entry, Share

log = logging.getLogger(__name__)

CHANNEL = "shares"
SEALED = "share"
# Codes after which the share waits for the administrator to give its sign-in again.
STOPPED = {"share_login", "share_secret"}
# A scanner writes its file over seconds; an inbox's file changed this recently waits a pass.
SETTLING = timedelta(seconds=30)
# Room the disk keeps beyond what a copy takes.
SPARE = 1024**3
# How much of what stays out, and of what was kept as a file, a share lists.
LISTED = 500
# How often a pass writes how far it got.
PROGRESS = 5.0


class Gone(Exception):
    pass


class Bell:
    """What wakes a share's loop before its next pass is due."""

    def __init__(self) -> None:
        self.event = Event()

    def ring(self) -> None:
        self.event.set()

    async def wait(self, seconds: float) -> None:
        with move_on_after(seconds):
            await self.event.wait()
        self.event = Event()


def wake() -> None:
    """Has every share looked at once the current transaction commits."""
    notify(CHANNEL)


def password(share: Share) -> str:
    found = opened(SEALED, share.secret)
    if found is None:
        raise smb.Failed("share_secret")
    return found


def free() -> int:
    return shutil.disk_usage(store.root()).free


def room_for(needed: int) -> bool:
    return needed + SPARE <= free()


def _parent(path: str) -> str:
    return str(PurePosixPath(path).parent).removeprefix(".")


def _sorted(walked) -> tuple[list[smb.Found], list[smb.Found], list[smb.Left]]:
    folders, files, left = [], [], []
    for each in walked:
        if isinstance(each, smb.Left):
            left.append(each)
        elif each.folder:
            folders.append(each)
        elif each.size > settings.BLOB_MAX_BYTES:
            left.append(smb.Left(each.path, "too_large"))
        else:
            files.append(each)
    return folders, files, left


def _summary(folders, files, left) -> dict:
    return {
        "files": len(files),
        "folders": len(folders),
        "bytes": sum(found.size for found in files),
        "left": [{"path": each.path, "why": each.why} for each in left[:LISTED]],
        "left_count": len(left),
    }


def _held(share: Share) -> None:
    """The share locked for the rest of the transaction, so that nothing is copied into a folder
    the administrator has just disconnected or moved."""
    if not Share.objects.select_for_update().filter(pk=share.pk).exists():
        raise Gone


def _taken(share: Share, server: smb.Server, found: smb.Found, parent: Node, old: Node | None):
    """The file copied into the folder and noted, False while someone holds it open."""
    try:
        with server.read(found.path, alone=share.mode == Share.Mode.INBOX) as stream:
            blob = store.put(stream)
    except store.TooLarge:
        return False
    except Exception as refused:
        if smb.busy(refused):
            return False
        raise
    title, extension = placed.named(PurePosixPath(found.path).name)
    if old is not None and blob.pk in (old.source_id, old.blob_id):
        node, kept = old, Entry.objects.get(share=share, path=found.path).kept
    else:
        try:
            node, kept = placed.placed(blob, parent, title, extension, share.created_by, old)
        except convert.Unavailable:
            raise smb.Failed("converter_unavailable") from None
        dated(node, found.modified)
    try:
        with transaction.atomic():
            _held(share)
            Entry.objects.update_or_create(
                share=share,
                path=found.path,
                defaults={
                    "node": node,
                    "size": found.size,
                    "modified": found.modified,
                    "kept": kept,
                },
            )
    except Gone:
        node.delete()
        raise
    extraction.wake()
    previews.wake()
    return True


def _read(share: Share, server: smb.Server) -> None:
    """The copy's folder read whole, and what it found, before anything is copied."""
    folders, files, left = _sorted(server.walk())
    Share.objects.filter(pk=share.pk, state=Share.State.READING).update(
        state=Share.State.READ,
        error="",
        found={**_summary(folders, files, left), "free": free()},
        read_at=timezone.now(),
    )


def _folders(share: Share, folders: list[smb.Found], nodes: dict[str, Node], entries) -> None:
    for found in folders:
        if found.path in nodes:
            continue
        with transaction.atomic():
            _held(share)
            node = created(
                nodes[_parent(found.path)],
                Node.Kind.FOLDER,
                PurePosixPath(found.path).name[:200],
                None,
                share.created_by,
            )
            entries[found.path] = Entry.objects.create(
                share=share, path=found.path, node=node, size=0, modified=found.modified
            )
        nodes[found.path] = node


def _copied(share: Share, server: smb.Server, stop: threading.Event) -> None:
    """The copy made like the server's folder: what is new or changed copied, what is gone or now
    stays out taken away; then, where the administrator asked, the folder left PONISTRA's."""
    folders, files, left = _sorted(server.walk())
    summary = _summary(folders, files, left)
    entries = {entry.path: entry for entry in share.entries.select_related("node")}
    present = {found.path: True for found in folders} | {found.path: False for found in files}
    kept_on = {
        path: entry
        for path, entry in entries.items()
        if present.get(path) == (entry.node.kind == Node.Kind.FOLDER)
    }
    gone = [entry.node_id for path, entry in entries.items() if path not in kept_on]
    if gone:
        with transaction.atomic():
            _held(share)
            kept = retention.kept_nodes(gone)
            Entry.objects.filter(share=share, node_id__in=kept).delete()
            Node.objects.filter(pk__in=gone).exclude(pk__in=kept).delete()
    entries = kept_on
    changed = [
        found
        for found in files
        if (entry := entries.get(found.path)) is None
        or (entry.size, entry.modified) != (found.size, found.modified)
    ]
    needed = sum(found.size for found in changed)
    if not room_for(needed):
        raise smb.Failed("no_space")
    nodes = {"": share.folder, **{path: entry.node for path, entry in entries.items()}}
    _folders(share, folders, nodes, entries)
    copied, waiting, written = len(files) - len(changed), 0, monotonic()
    for found in changed:
        if stop.is_set():
            return
        entry = entries.get(found.path)
        old = entry.node if entry is not None else None
        if _taken(share, server, found, nodes[_parent(found.path)], old):
            copied += 1
        else:
            waiting += 1
        if monotonic() - written > PROGRESS:
            Share.objects.filter(pk=share.pk).update(found={**summary, "copied": copied})
            written = monotonic()
    kept = list(share.entries.exclude(kept="").order_by("path").values("path", "kept")[:LISTED])
    with transaction.atomic():
        _held(share)
        Share.objects.filter(pk=share.pk).update(
            state=Share.State.READY if not waiting else Share.State.COPYING,
            error="",
            found={**summary, "copied": copied, "kept": kept},
            read_at=timezone.now(),
        )
        if share.moving and not waiting:
            Node.objects.filter(pk=share.folder_id).update(copied=False)
            Share.objects.filter(pk=share.pk).delete()
    if share.moving and not waiting:
        revoke()


def _emptied(share: Share, server: smb.Server, stop: threading.Event) -> None:
    """Each whole file that arrived in the inbox moved into the company folder: taken as
    PONISTRA's, then deleted on the server. A file the account may not delete is refused before
    it is taken, as taking it again on the next pass would make it twice."""
    _, files, left = _sorted(server.walk())
    files = [found for found in files if "/" not in found.path]
    settled = timezone.now() - SETTLING
    entries = {entry.path: entry for entry in share.entries.all()}
    taken = 0
    for found in files:
        if stop.is_set():
            return
        entry = entries.get(found.path)
        if entry is not None and (entry.size, entry.modified) == (found.size, found.modified):
            continue
        if found.modified > settled:
            continue
        if not server.deletable(found.path):
            raise smb.Failed("inbox_not_deletable")
        if not _taken(share, server, found, share.folder, None):
            continue
        server.remove(found.path)
        Entry.objects.filter(share=share, path=found.path).delete()
        taken += 1
    found = dict(share.found)
    found["taken"] = found.get("taken", 0) + taken
    found["left"] = [{"path": each.path, "why": each.why} for each in left[:LISTED]]
    found["left_count"] = len(left)
    Share.objects.filter(pk=share.pk).update(error="", found=found, read_at=timezone.now())


def passed(share_id: int, stop: threading.Event) -> None:
    """One pass over the share, by what it is and how far it has come."""
    try:
        share = Share.objects.select_related("folder", "created_by").get(pk=share_id)
    except Share.DoesNotExist:
        raise Gone from None
    address = smb.Address(share.host, share.path)
    with smb.Server(address, share.username, password(share)) as server:
        if share.mode == Share.Mode.INBOX:
            _emptied(share, server, stop)
        elif share.state == Share.State.READING:
            _read(share, server)
        elif share.state != Share.State.READ:
            _copied(share, server, stop)


def keep(share_id: int, stop: threading.Event) -> None:
    try:
        passed(share_id, stop)
    finally:
        connection.close()


def failed(share_id: int, code: str) -> None:
    Share.objects.filter(pk=share_id).update(error=code)


def followed() -> dict[int, timedelta]:
    """The shares to follow, each with how often: all but a copy read and waiting for the
    administrator, and those whose sign-in the server refused until it is given again."""
    found = (
        Share.objects.exclude(state=Share.State.READ)
        .exclude(error__in=STOPPED)
        .values_list("pk", "mode")
    )
    return {
        pk: settings.INBOX_SWEEP if mode == Share.Mode.INBOX else settings.SHARE_SWEEP
        for pk, mode in found
    }


async def follow(share_id: int, every: timedelta, bell: Bell, lines: CapacityLimiter) -> None:
    """Passes over the share every so often and when woken, until it is gone or its sign-in is
    refused."""
    while True:
        stop = threading.Event()
        try:
            async with lines:
                await database(keep, own_thread=True)(share_id, stop)
        except Gone:
            return
        except Exception as error:
            code = smb.failure(error)
            if code is None:
                log.exception("shares: share %s failed", share_id)
                code = "unexpected"
            else:
                log.warning("shares: share %s: %s (%s)", share_id, code, error)
            # Raised here it would end every share's loop, and the backend's other loops with it.
            try:
                await database(failed)(share_id, code)
            except Exception:
                log.exception("shares: share %s could not be marked %s", share_id, code)
            if code in STOPPED:
                return
        finally:
            stop.set()
        await bell.wait(every.total_seconds())


async def shares() -> None:
    """Follows each connected share, wakes them all when the administrator asks for something,
    and stops following one as it is disconnected or moved in."""
    # Copying imports documents, which take memory and the processor: two shares at a time.
    lines = CapacityLimiter(2)
    following: dict[int, tuple[CancelScope, Bell]] = {}

    async with create_task_group() as group:

        async def run(share_id: int, every: timedelta, bell: Bell, scope: CancelScope) -> None:
            with scope:
                await follow(share_id, every, bell, lines)
            following.pop(share_id, None)

        async def step() -> bool:
            wanted = await database(followed)()
            for share_id in set(following) - set(wanted):
                following.pop(share_id)[0].cancel()
            for _, bell in following.values():
                bell.ring()
            for share_id in set(wanted) - set(following):
                scope, bell = CancelScope(), Bell()
                following[share_id] = (scope, bell)
                group.start_soon(run, share_id, wanted[share_id], bell, scope)
            return False

        await drain(CHANNEL, step, settings.SHARE_SWEEP, log)
