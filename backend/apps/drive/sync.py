"""Google Drives copied into PONISTRA while their users leave Google (D44): each drive's My Drive
and the shared drives it reaches, read whole once and then by Google's changes every DRIVE_SWEEP,
and at once when its user asks."""

import logging
import threading
from collections.abc import Iterable
from time import monotonic

from anyio import CancelScope, CapacityLimiter, create_task_group
from django.conf import settings
from django.db import connection, transaction
from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.access.models import RANK, Grant, Role
from apps.blobs import previews, store
from apps.collab.server import revoke
from apps.core.asyncdb import database, drain, notify
from apps.documents.models import Node
from apps.documents.views import created, dated
from apps.imports import convert, placed
from apps.mail.imap import Failed
from apps.mail.models import Account
from apps.retention import kept as retention
from apps.search import extraction
from apps.shares.sync import Bell
from apps.users.models import User

from . import google
from .models import Drive, Item, Space

log = logging.getLogger(__name__)

CHANNEL = "drives"
# Codes after which a drive waits for its user to sign in to the account again.
STOPPED = {
    "oauth_login",
    "oauth_client",
    "oauth_refused",
    "mail_lost",
    "drive_scope",
    "drive_disabled",
}
ROLES = {
    "owner": Role.OWN,
    "organizer": Role.OWN,
    "fileOrganizer": Role.EDIT,
    "writer": Role.EDIT,
    "commenter": Role.READ,
    "reader": Role.READ,
}
# How much of what stays out a space lists.
LISTED = 500
# How often a pass writes how far it got.
PROGRESS = 5.0
# How far up a file's folders are looked for before it is taken as outside the space.
DEPTH = 100


class Gone(Exception):
    pass


def wake() -> None:
    """Has every drive looked at once the current transaction commits."""
    notify(CHANNEL)


def _held(drive_id: int) -> Drive:
    """The drive locked for the rest of the transaction, so that nothing is copied for a drive its
    user has just let go of."""
    found = Drive.objects.select_for_update().filter(pk=drive_id).first()
    if found is None:
        raise Gone
    return found


def _people() -> dict[str, str]:
    """The installation's users by each address Google may know them by: their own, and those of
    the Google accounts they connected."""
    found = {
        email: str(pk)
        for email, pk in User.objects.filter(is_active=True).values_list("email", "pk")
    }
    google_accounts = Account.objects.filter(
        login=Account.Login.GOOGLE, owner__is_active=True, owner__visitor=False
    )
    for address, owner in google_accounts.values_list("address", "owner"):
        found.setdefault(address.lower(), str(owner))
    return found


def _wanted(permissions: Iterable[dict], people: dict[str, str]) -> dict[str, str]:
    """Who of the installation's users Google lets open it, and as what."""
    wanted: dict[str, str] = {}
    for each in permissions:
        role = ROLES.get(each.get("role", ""))
        user = people.get(str(each.get("emailAddress", "")).lower())
        if each.get("type") != "user" or role is None or user is None:
            continue
        if user not in wanted or RANK[role] > RANK[wanted[user]]:
            wanted[user] = role
    return wanted


def _merged(inherited: dict[str, str], own: dict[str, str]) -> dict[str, str]:
    merged = dict(inherited)
    for user, role in own.items():
        if user not in merged or RANK[role] > RANK[merged[user]]:
            merged[user] = role
    return merged


def _beyond(wanted: dict[str, str], inherited: dict[str, str]) -> dict[str, str]:
    """What the node's own grants add to those it has through its folders."""
    return {
        user: role
        for user, role in wanted.items()
        if user not in inherited or RANK[role] > RANK[inherited[user]]
    }


def _granted(node: Node, before: dict[str, str], after: dict[str, str], by) -> None:
    """The node's grants made what Google shares it with, leaving those it did not give."""
    for user, role in before.items():
        if after.get(user) != role:
            Grant.objects.filter(node=node, user_id=user, group=None, role=role).delete()
    for user, role in after.items():
        if before.get(user) != role:
            Grant.objects.update_or_create(
                node=node, user_id=user, group=None, defaults={"role": role, "created_by": by}
            )


class Pass:
    """One pass over a space: what Google lists against what was copied, the copy made like it."""

    def __init__(self, space: Space, drive: Drive, client: google.Google, stop: threading.Event):
        self.space, self.drive, self.client, self.stop = space, drive, client, stop
        self.user = drive.account.owner
        self.people = _people()
        self.known: dict[str, Item | None] = {}
        self.rights: dict[str, dict[str, str]] = {}
        self.left: list[dict] = []
        self.waiting = 0

    @property
    def drive_id(self) -> str:
        return self.space.google_id if self.space.shared else ""

    def item(self, google_id: str) -> Item | None:
        if google_id not in self.known:
            self.known[google_id] = (
                Item.objects.filter(google_id=google_id).select_related("node").first()
            )
        return self.known[google_id]

    def node(self, google_id: str) -> Node | None:
        if google_id == self.space.google_id:
            return self.space.folder
        found = self.item(google_id)
        return found.node if found is not None and found.folder else None

    def inherited(self, google_id: str) -> dict[str, str]:
        """Who reaches the folder through it and the folders above, as Google shares them."""
        if google_id in self.rights:
            return self.rights[google_id]
        if google_id == self.space.google_id:
            found = _merged({str(self.user.pk): Role.OWN}, self.space.granted)
        else:
            item = self.item(google_id)
            found = _merged(self.inherited(item.parent), item.granted) if item is not None else {}
        self.rights[google_id] = found
        return found

    def ids(self, google_id: str) -> set[str]:
        if google_id == self.space.google_id:
            return set(self.space.found.get("permissions", []))
        item = self.item(google_id)
        return set(item.permissions) if item is not None else set()

    def wanted(self, found: dict, parent: str) -> dict[str, str]:
        """Who Google lets open the file beyond what its folder gives: listed with it in a My
        Drive, asked for in a shared drive where its permissions are not all its folder's."""
        permissions = found.get("permissions")
        if permissions is None:
            if set(found.get("permissionIds", [])) <= self.ids(parent):
                return {}
            try:
                permissions = self.client.permissions(found["id"])
            except Failed as refused:
                # Whoever may only read a file is not told who else may.
                if refused.code != "drive_refused":
                    raise
                permissions = []
        return _beyond(_wanted(permissions, self.people), self.inherited(parent))

    def left_out(self, found: dict, why: str) -> None:
        self.left.append({"id": found["id"], "name": found.get("name", ""), "why": why})

    def removed(self, google_ids: Iterable[str]) -> None:
        """What Google no longer has here taken away from the copy, but for what a hold keeps."""
        found = list(
            Item.objects.filter(space=self.space, google_id__in=list(google_ids)).values_list(
                "node", flat=True
            )
        )
        if not found:
            return
        with transaction.atomic():
            _held(self.drive.pk)
            kept = retention.kept_nodes(found)
            Item.objects.filter(space=self.space, node_id__in=kept).delete()
            Node.objects.filter(pk__in=found).exclude(pk__in=kept).delete()
        self.known.clear()
        self.rights.clear()

    def ordered(self, files: dict[str, dict]) -> list[dict]:
        """Folders before what they hold, each before the files."""

        def depth(found: dict) -> int:
            steps, parent = 0, _parent(found)
            while parent in files and steps < DEPTH:
                steps, parent = steps + 1, _parent(files[parent])
            return steps

        return sorted(
            files.values(), key=lambda found: (found["mimeType"] != google.FOLDER, depth(found))
        )

    def applied(self, files: dict[str, dict], removed: set[str]) -> None:
        self.removed(removed)
        copied, written = 0, monotonic()
        for found in self.ordered(files):
            if self.stop.is_set():
                return
            parent = self.node(_parent(found))
            if parent is None:
                continue
            if found["mimeType"] == google.FOLDER:
                self.folder(found, parent)
            elif self.file(found, parent):
                copied += 1
            if monotonic() - written > PROGRESS:
                found_now = {**self.space.found, "copying": copied}
                Space.objects.filter(pk=self.space.pk).update(found=found_now)
                written = monotonic()

    def folder(self, found: dict, parent: Node) -> None:
        old = self.item(found["id"])
        wanted = self.wanted(found, _parent(found))
        title = found["name"][:200]
        with transaction.atomic():
            _held(self.drive.pk)
            if old is None or not old.folder:
                if old is not None:
                    old.node.delete()
                node = created(parent, Node.Kind.FOLDER, title, None, self.user)
                before = {}
            else:
                node, before = old.node, old.granted
                _moved(node, parent, title)
            _granted(node, before, wanted, self.user)
            self.known[found["id"]] = Item.objects.update_or_create(
                google_id=found["id"],
                defaults={
                    "space": self.space,
                    "parent": _parent(found),
                    "node": node,
                    "folder": True,
                    "stamp": "",
                    "permissions": found.get("permissionIds", []),
                    "granted": wanted,
                    "kept": "",
                },
            )[0]
        self.rights.pop(found["id"], None)

    def file(self, found: dict, parent: Node) -> bool:
        """The file copied where it changed, else moved and shared as Google has it now; False
        where it stays out."""
        why = _out(found)
        if why:
            self.left_out(found, why)
            self.removed([found["id"]])
            return False
        old = self.item(found["id"])
        wanted = self.wanted(found, _parent(found))
        title, extension = _named(found)
        stamp = _stamp(found)
        if old is not None and not old.folder and old.stamp == stamp:
            with transaction.atomic():
                _held(self.drive.pk)
                _moved(old.node, parent, title)
                _granted(old.node, old.granted, wanted, self.user)
                Item.objects.filter(pk=old.pk).update(
                    space=self.space,
                    parent=_parent(found),
                    permissions=found.get("permissionIds", []),
                    granted=wanted,
                )
            self.known.pop(found["id"], None)
            return True
        try:
            with self.client.content(found) as stream:
                blob = store.put(stream)
        except store.TooLarge:
            self.left_out(found, "too_large")
            return False
        except google.Missing:
            return False
        previous = old.node if old is not None and not old.folder else None
        if previous is not None and blob.pk in (previous.source_id, previous.blob_id):
            node, kept = previous, old.kept
        else:
            try:
                node, kept = placed.placed(blob, parent, title, extension, self.user, previous)
            except convert.Unavailable:
                raise Failed("converter_unavailable") from None
            if old is not None and old.folder:
                old.node.delete()
            dated(node, parse_datetime(found.get("modifiedTime", "")))
        try:
            with transaction.atomic():
                _held(self.drive.pk)
                _moved(node, parent, title)
                _granted(node, old.granted if old is not None else {}, wanted, self.user)
                Item.objects.update_or_create(
                    google_id=found["id"],
                    defaults={
                        "space": self.space,
                        "parent": _parent(found),
                        "node": node,
                        "folder": False,
                        "stamp": stamp,
                        "permissions": found.get("permissionIds", []),
                        "granted": wanted,
                        "kept": kept,
                    },
                )
        except Gone:
            node.delete()
            raise
        self.known.pop(found["id"], None)
        extraction.wake()
        previews.wake()
        return True


def _parent(found: dict) -> str:
    parents = found.get("parents") or [""]
    return parents[0]


def _stamp(found: dict) -> str:
    return found.get("md5Checksum") or found.get("modifiedTime", "")


def _named(found: dict) -> tuple[str, str]:
    """A file's title and extension: a Google format's by what it is taken as."""
    exported = google.EXPORTS.get(found["mimeType"])
    if exported is not None:
        return found["name"].strip()[:200] or found["id"], exported[1]
    return placed.named(found["name"])


def _out(found: dict) -> str:
    """Why the file stays out of the copy, or nothing."""
    kind = found["mimeType"]
    if kind == google.SHORTCUT:
        return "shortcut"
    if kind.startswith(google.NATIVE) and kind not in google.EXPORTS:
        return "google_only"
    if not (found.get("capabilities") or {}).get("canDownload", True):
        return "no_download"
    if int(found.get("size") or 0) > settings.BLOB_MAX_BYTES:
        return "too_large"
    return ""


def _moved(node: Node, parent: Node, title: str) -> None:
    if node.parent_id != parent.pk or node.title != title:
        Node.objects.filter(pk=node.pk).update(parent=parent, title=title)
        node.parent, node.title = parent, title


def _summary(space: Space) -> dict:
    items = Item.objects.filter(space=space)
    files = items.filter(folder=False)
    return {
        "files": files.count(),
        "folders": items.filter(folder=True).count(),
        "bytes": files.aggregate(
            bytes=Sum(Coalesce(F("node__blob__size"), F("node__source__size"), 0))
        )["bytes"]
        or 0,
        "kept": list(files.exclude(kept="").values_list("node__title", "kept")[:LISTED]),
    }


def _whole(run: Pass) -> tuple[dict[str, dict], set[str], str]:
    """Every file and folder of the space, by a listing that begins after the token the changes
    will be followed from."""
    space, client = run.space, run.client
    token = client.start(run.drive_id)
    listed = {found["id"]: found for found in client.listed(run.drive_id)}
    if not space.shared:

        def below(found: dict) -> bool:
            for _ in range(DEPTH):
                parent = _parent(found)
                if parent == space.google_id:
                    return True
                if parent not in listed:
                    return False
                found = listed[parent]
            return False

        listed = {key: found for key, found in listed.items() if below(found)}
    present = set(listed)
    copied = Item.objects.filter(space=space).values_list("google_id", flat=True)
    return listed, {each for each in copied if each not in present}, token


def _changed(run: Pass) -> tuple[dict[str, dict], set[str], str]:
    """What changed in the space since the last pass, with the folders above a file that arrived
    before them."""
    space, client = run.space, run.client
    changes, token = client.changes(space.changes, run.drive_id)
    files: dict[str, dict] = {}
    removed: set[str] = set()
    for change in changes:
        found = change.get("file")
        outside = found is not None and (
            found.get("driveId", "") != (space.google_id if space.shared else "")
        )
        if change.get("removed") or found is None or found.get("trashed") or outside:
            removed.add(change["fileId"])
        else:
            files[found["id"]] = found
    for key in list(files):
        found, chain = files[key], []
        for _ in range(DEPTH):
            parent = _parent(found)
            if parent == space.google_id or parent in files or run.node(parent) is not None:
                break
            try:
                found = client.file(parent)
            except google.Missing:
                parent = ""
            if not parent or found.get("trashed"):
                chain = None
                break
            chain.append(found)
        else:
            chain = None
        if chain is None:
            files.pop(key)
            removed.add(key)
        else:
            files |= {each["id"]: each for each in chain}
    return files, removed, token


def _space(run: Pass) -> None:
    space = run.space
    try:
        files, removed, token = _changed(run) if space.changes else _whole(run)
    except google.Expired:
        Space.objects.filter(pk=space.pk).update(changes="")
        space.changes = ""
        files, removed, token = _whole(run)
    run.applied(files, removed)
    if run.stop.is_set():
        return
    touched = set(files) | removed
    before = space.found.get("left", []) if space.changes else []
    left = [each for each in before if each.get("id") not in touched] + run.left
    Space.objects.filter(pk=space.pk).update(
        changes=token,
        found={
            **_summary(space),
            "permissions": space.found.get("permissions", []),
            "left": left[:LISTED],
            "left_count": len(left),
        },
        read_at=timezone.now(),
    )


def _top(drive: Drive, title: str, google_id: str, shared: bool) -> Space:
    with transaction.atomic():
        _held(drive.pk)
        folder = created(None, Node.Kind.FOLDER, title[:200], None, drive.account.owner)
        Node.objects.filter(pk=folder.pk).update(copied=True)
        return Space.objects.create(google_id=google_id, shared=shared, drive=drive, folder=folder)


def _spaces(drive: Drive, client: google.Google) -> list[Space]:
    """The spaces the drive follows: its user's My Drive, and the shared drives they see that no
    other drive follows yet. A shared drive they no longer see is let go for another to take."""
    root = client.root()
    Space.objects.filter(google_id=root, drive=None).update(drive=drive)
    if not Space.objects.filter(google_id=root).exists():
        others = Drive.objects.filter(user=drive.user_id).exclude(pk=drive.pk)
        title = "Google Drive" + (f" ({drive.account.address})" if others.exists() else "")
        _top(drive, title, root, False)
    seen = {each["id"]: each["name"] for each in client.drives()}
    Space.objects.filter(drive=drive, shared=True).exclude(google_id__in=seen).update(drive=None)
    taken = Space.objects.filter(google_id__in=seen)
    taken.filter(drive=None).update(drive=drive)
    for google_id in set(seen) - set(taken.values_list("google_id", flat=True)):
        _top(drive, seen[google_id], google_id, True)
    return list(Space.objects.filter(drive=drive).select_related("folder").order_by("shared", "pk"))


def _members(run: Pass) -> None:
    """The shared drive's members granted on its folder, as Google has them now, and its name."""
    space, client = run.space, run.client
    try:
        named = client.drive(space.google_id)["name"]
        permissions = client.permissions(space.google_id)
    except google.Missing:
        Space.objects.filter(pk=space.pk).update(drive=None)
        raise
    wanted = _wanted(permissions, run.people)
    wanted.pop(str(run.user.pk), None)
    with transaction.atomic():
        _held(run.drive.pk)
        _granted(space.folder, space.granted, wanted, run.user)
        if space.folder.title != named[:200]:
            Node.objects.filter(pk=space.folder_id).update(title=named[:200])
        space.found = {
            **space.found,
            "permissions": client.file(space.google_id).get("permissionIds", []),
        }
        Space.objects.filter(pk=space.pk).update(granted=wanted, found=space.found)
    space.granted = wanted


def _finished(drive: Drive) -> None:
    """The copies left PONISTRA's: their folders no longer only read, Google no longer followed."""
    with transaction.atomic():
        _held(drive.pk)
        spaces = Space.objects.filter(drive=drive)
        Node.objects.filter(pk__in=spaces.values("folder")).update(copied=False)
        spaces.delete()
        Drive.objects.filter(pk=drive.pk).delete()
    revoke()


def passed(drive_id: int, stop: threading.Event) -> None:
    """One pass over every space the drive follows."""
    drive = Drive.objects.select_related("account__owner").filter(pk=drive_id).first()
    if drive is None:
        raise Gone
    client = google.Google(drive.account)
    for space in _spaces(drive, client):
        if stop.is_set():
            return
        run = Pass(space, drive, client, stop)
        if space.shared:
            try:
                _members(run)
            except google.Missing:
                continue
        _space(run)
    if stop.is_set():
        return
    if drive.finishing:
        _finished(drive)
        return
    Drive.objects.filter(pk=drive.pk).update(
        state=Drive.State.READY, error="", read_at=timezone.now()
    )


def keep(drive_id: int, stop: threading.Event) -> None:
    try:
        passed(drive_id, stop)
    finally:
        connection.close()


def failed(drive_id: int, code: str) -> None:
    Drive.objects.filter(pk=drive_id).update(error=code)


def followed() -> dict[int, object]:
    """The drives to follow: all but those waiting for their user to sign in again."""
    found = Drive.objects.exclude(error__in=STOPPED).values_list("pk", flat=True)
    return dict.fromkeys(found, settings.DRIVE_SWEEP)


async def follow(drive_id: int, every, bell: Bell, lines: CapacityLimiter) -> None:
    """Passes over the drive every so often and when woken, until it is gone or Google refuses
    its sign-in."""
    while True:
        stop = threading.Event()
        try:
            async with lines:
                await database(keep, own_thread=True)(drive_id, stop)
        except Gone:
            return
        except Exception as error:
            code = error.code if isinstance(error, Failed) else None
            if code is None:
                log.exception("drive: drive %s failed", drive_id)
                code = "unexpected"
            else:
                log.warning("drive: drive %s: %s", drive_id, code)
            # Raised here it would end every drive's loop, and the backend's other loops with it.
            try:
                await database(failed)(drive_id, code)
            except Exception:
                log.exception("drive: drive %s could not be marked %s", drive_id, code)
            if code in STOPPED:
                return
        finally:
            stop.set()
        await bell.wait(every.total_seconds())


async def drives() -> None:
    """Follows each drive, wakes them all when a user asks for something, and stops following
    one as its user lets it go or finishes."""
    # Copying imports documents, which take memory and the processor: two drives at a time.
    lines = CapacityLimiter(2)
    following: dict[int, tuple[CancelScope, Bell]] = {}

    async with create_task_group() as group:

        async def run(drive_id: int, every, bell: Bell, scope: CancelScope) -> None:
            with scope:
                await follow(drive_id, every, bell, lines)
            following.pop(drive_id, None)

        async def step() -> bool:
            wanted = await database(followed)()
            for drive_id in set(following) - set(wanted):
                following.pop(drive_id)[0].cancel()
            for _, bell in following.values():
                bell.ring()
            for drive_id in set(wanted) - set(following):
                scope, bell = CancelScope(), Bell()
                following[drive_id] = (scope, bell)
                group.start_soon(run, drive_id, wanted[drive_id], bell, scope)
            return False

        await drain(CHANNEL, step, settings.DRIVE_SWEEP, log)
