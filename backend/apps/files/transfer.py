"""Files and folders copied or moved from one source of Files into another (D55, DT2): a job
that reads from one source and writes into the other in the backend, never through the browser.
What is chosen is walked first, so that the job tells how far it has come of how much; a name
the target already holds is settled by the one answer the user gave for the whole transfer
(skip, replace, keep both), a folder that meets a folder merging into it on replace. A move
removes from the source what reached the target, a folder once all it held did; within one
source it is a rename. Within Ponistra's tree a copy makes each node again rather than read out
and imported back; a move there is Documents' own."""

import hashlib
import posixpath
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime

from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.access import rights
from apps.access.models import Role
from apps.blobs import previews, store
from apps.blobs.views import chunks
from apps.collab.server import revoke
from apps.core.api import Refused, optional_id
from apps.core.asyncdb import database
from apps.documents import copies
from apps.documents.models import Node
from apps.documents.views import (
    created,
    dated,
    file_name,
    folder,
    kept_in,
    laid_out,
)
from apps.exports import jobs as exports
from apps.exports import tree
from apps.imports import convert, placed
from apps.jobs.kinds import Kind, answered, running
from apps.jobs.models import Job
from apps.locations.remote import Failed, Remote, asked, joined
from apps.search import extraction

from .sources import Source, confirmed, opened, source

CONFLICTS = {"skip", "replace", "keep"}
MOST_PATHS = 1000
# How often, at most, the job tells how far it has come, in seconds.
TOLD_EVERY = 0.5
KEPT_BOTH = 1000


Read = Callable[[], AsyncIterator[bytes]]


class _GivenUp(Exception):
    """The user gave the transfer up while it ran."""


@dataclass
class Item:
    name: str
    kind: str  # folder, file
    size: int | None
    modified: datetime | None
    # Where it lies in its source: a path, or a node's id in Ponistra's tree.
    at: str
    below: list[Item] = field(default_factory=list)

    def files(self) -> int:
        return 1 if self.kind == "file" else sum(each.files() for each in self.below)

    def bytes(self) -> int:
        return (self.size or 0) if self.kind == "file" else sum(each.bytes() for each in self.below)


def _safe(name: str) -> str:
    """A name of Ponistra's tree as one segment of a path elsewhere."""
    cleaned = "".join("-" if each in "/\\\0" else each for each in name).strip() or "-"
    return cleaned if cleaned not in (".", "..") else "-"


def _node_of(path: str) -> uuid.UUID | None:
    last = path.rstrip("/").rsplit("/", 1)[-1]
    return optional_id(last) if last else None


class _RemoteReader:
    def __init__(self, remote: Remote):
        self.remote = remote
        self.left = 0

    async def _walked(self, path: str, name: str) -> Item | None:
        entry = await self.remote.stat(path)
        return await self._item(path, name, entry.kind, entry.size, entry.modified, None)

    async def _item(self, path, name, kind, size, modified, link) -> Item | None:
        if kind == "file":
            return Item(name, kind, size, modified, path)
        if kind != "folder" or link is not None:
            self.left += 1
            return None
        item = Item(name, kind, None, modified, path)
        for entry in await self.remote.listed(path):
            inner = await self._item(
                joined(path, entry.name),
                entry.name,
                entry.kind,
                entry.size,
                entry.modified,
                entry.link,
            )
            if inner is not None:
                item.below.append(inner)
        return item

    async def planned(self, paths: list[str]) -> list[Item]:
        found = []
        for path in paths:
            item = await self._walked(path, posixpath.basename(path))
            if item is not None:
                found.append(item)
        return found

    def parts(self, item: Item) -> AsyncIterator[bytes]:
        return self.remote.chunks(item.at, 0, item.size or 0)

    async def removed(self, item: Item) -> None:
        await self.remote.remove(item.at)


class _TreeReader:
    """Ponistra's tree read as a download reads it: a document saved in its Office format, a
    file as it is, a link as a shortcut, each logged as taken out."""

    def __init__(self, user, site: str, move: bool, leaving: bool = True):
        self.user = user
        self.site = site
        self.move = move
        self.leaving = leaving
        self.left = 0
        self.nodes: dict[str, tuple[Node, rights.Reach]] = {}

    def _walk(self, ids: list[uuid.UUID]) -> list[Item]:
        _, walked = tree.walked(self.user, ids, self.leaving)
        items: dict = {}
        top = []
        for node, reach in walked:
            if self.move and not rights.covers(reach.role, Role.EDIT):
                raise Refused(403, "forbidden")
            self.nodes[str(node.pk)] = (node, reach)
            title = _safe(node.title)
            if node.kind == Node.Kind.FOLDER:
                item = Item(title, "folder", None, node.updated_at, str(node.pk))
            elif node.kind == Node.Kind.LINK:
                item = Item(f"{title}.url", "file", None, node.updated_at, str(node.pk))
            elif node.kind == Node.Kind.DOCUMENT:
                item = Item(
                    f"{title}.{tree.office_format(node)}",
                    "file",
                    None,
                    node.updated_at,
                    str(node.pk),
                )
            else:
                size = node.blob.size if node.blob_id else None
                item = Item(_safe(file_name(node)), "file", size, node.updated_at, str(node.pk))
            items[node.pk] = item
            (items[node.parent_id].below if node.parent_id in items else top).append(item)
        return top

    async def planned(self, paths: list[str]) -> list[Item]:
        ids = [_node_of(path) for path in paths]
        if None in ids:
            raise Refused(400, "invalid_paths")
        return await database(self._walk)(ids)

    async def parts(self, item: Item) -> AsyncIterator[bytes]:
        node, reach = self.nodes[item.at]
        if node.kind == Node.Kind.LINK:
            yield f"[InternetShortcut]\r\nURL={node.href}\r\n".encode()
            return
        if node.kind == Node.Kind.DOCUMENT:
            parameters = {"document": str(node.pk), "site": self.site, "versions": False}
            saved = await database(exports.KINDS[tree.office_format(node)].done)(
                self.user, parameters
            )
            if isinstance(saved.data, bytes):
                yield saved.data
            else:
                async for part in store.streamed(saved.data):
                    yield part
            return
        blob = await database(tree.blob_of)(self.user, node, reach)
        if blob is None:
            _, sent = await database(tree.with_notes)(node)
        else:
            sent = chunks(store.path_of(blob.sha256), 0, blob.size)
        async for part in sent:
            yield part

    def _trashed(self, item: Item) -> None:
        node, _ = self.nodes[item.at]
        laid_out(node)
        Node.objects.filter(pk=node.pk).update(trashed_at=timezone.now())
        revoke()

    async def removed(self, item: Item) -> None:
        await database(self._trashed)(item)


class _RemoteWriter:
    def __init__(self, remote: Remote):
        self.remote = remote

    def root(self, path: str) -> str:
        return path

    def key_of(self, name: str) -> str:
        return name

    async def names(self, into: str) -> dict[str, tuple[str, str]]:
        return {
            entry.name: (entry.kind, joined(into, entry.name))
            for entry in await self.remote.listed(into)
        }

    async def folder(self, into: str, name: str) -> str:
        made = joined(into, name)
        await self.remote.mkdir(made)
        return made

    async def file(self, into: str, item: Item, name: str, read: Read) -> None:
        await self.remote.put(joined(into, name), read())

    async def dropped(self, ref: str) -> None:
        await self.remote.remove(ref)


class _TreeWriter:
    """Into Ponistra's tree as an upload places a file: a document where Ponistra imports its
    kind, else the file it is; what a replace takes the place of goes to the trash."""

    def __init__(self, user, tree: str):
        self.user = user
        self.tree = tree

    def _root(self, path: str) -> Node | None:
        pk = _node_of(path)
        if pk is None and self.tree != "mine":
            raise Refused(400, "invalid_folder")
        into, _ = folder(self.user, pk, Role.EDIT)
        return into

    async def root(self, path: str) -> Node | None:
        return await database(self._root)(path)

    def key_of(self, name: str) -> str:
        return placed.named(name)[0].casefold()

    def _names(self, into: Node | None) -> dict[str, tuple[str, Node]]:
        children = (
            rights.mine(self.user).filter(unplaced=False)
            if into is None
            else Node.objects.filter(parent=into, trashed_at=None)
        )
        return {
            child.title.casefold(): ("folder" if child.kind == Node.Kind.FOLDER else "file", child)
            for child in children
        }

    async def names(self, into: Node | None) -> dict[str, tuple[str, Node]]:
        return await database(self._names)(into)

    async def folder(self, into: Node | None, name: str) -> Node:
        return await database(created)(into, Node.Kind.FOLDER, name[:200], None, self.user)

    def _placed(self, kept, name: str, modified, into: Node | None) -> None:
        kept.seek(0)
        blob = store.put(kept)
        title, extension = placed.named(name)
        try:
            node, _ = placed.placed(blob, into, title, extension, self.user, None)
        except convert.Unavailable:
            raise Refused(503, "converter_unavailable") from None
        dated(node, modified)

    async def file(self, into, item: Item, name: str, read: Read) -> None:
        with tempfile.TemporaryFile() as kept:
            async for part in read():
                kept.write(part)
            await database(self._placed)(kept, name, item.modified, into)

    def _trashed(self, node: Node) -> None:
        _, reach = folder(self.user, node.parent_id, Role.EDIT)
        if node.parent_id is None and not rights.mine(self.user).filter(pk=node.pk).exists():
            raise Refused(403, "forbidden")
        laid_out(node)
        Node.objects.filter(pk=node.pk).update(trashed_at=timezone.now())
        revoke()

    async def dropped(self, ref: Node) -> None:
        await database(self._trashed)(ref)


class _TreeCopier(_TreeWriter):
    """Within Ponistra's tree: each node made again where it stays in the folders that keep it
    in the browser."""

    def __init__(self, user, tree: str, nodes: dict[str, tuple[Node, rights.Reach]]):
        super().__init__(user, tree)
        self.nodes = nodes

    def _copied(self, into: Node | None, item: Item, name: str) -> None:
        node, _ = self.nodes[item.at]
        title = node.title if name == item.name else placed.named(name)[0]
        kept_in(self.user, [node], into)
        copies.copied(node, into, title[:200], self.user)

    async def file(self, into, item: Item, name: str, read: Read) -> None:
        await database(self._copied)(into, item, name)


def _both(name: str, taken: set[str], key_of) -> str:
    """The name with the first number after it the target does not hold: „plan (2).docx”."""
    stem, extension = posixpath.splitext(name)
    if not stem:
        stem, extension = name, ""
    for number in range(2, KEPT_BOTH):
        candidate = f"{stem} ({number}){extension}"
        if key_of(candidate) not in taken:
            return candidate
    raise Failed("file_exists")


class _Transfer:
    def __init__(self, reader, writer, conflict: str | None, move: bool):
        self.reader = reader
        self.writer = writer
        self.conflict = conflict
        self.move = move
        self.files = self.bytes = self.skipped = 0
        self.of_files = self.of_bytes = 0
        self.at = ""
        self.told_at = 0.0
        self.job = running.get(None)

    def _shown(self) -> dict:
        return {
            "files": self.files,
            "bytes": self.bytes,
            "of_files": self.of_files,
            "of_bytes": self.of_bytes,
            "skipped": self.skipped,
            "at": self.at,
        }

    def _tell(self) -> None:
        if self.job is None:
            return
        if Job.objects.filter(pk=self.job.pk, state=Job.State.CANCELLED).exists():
            raise _GivenUp
        answered({**self._shown(), "running": True})

    async def told(self, now: bool = False) -> None:
        if now or time.monotonic() - self.told_at >= TOLD_EVERY:
            self.told_at = time.monotonic()
            await database(self._tell)()

    async def counted(self, parts: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        async for part in parts:
            self.bytes += len(part)
            await self.told()
            yield part

    async def _settled(self, into, item: Item) -> tuple[str | None, object]:
        """The name the item takes in the folder and the folder it merges into, or no name where
        it is skipped."""
        names = await self.writer.names(into)
        key = self.writer.key_of(item.name)
        if key not in names:
            return item.name, None
        kind, ref = names[key]
        if self.conflict == "skip":
            return None, None
        if self.conflict == "replace":
            if item.kind == "folder" and kind == "folder":
                return item.name, ref
            await self.writer.dropped(ref)
            return item.name, None
        return _both(item.name, set(names), self.writer.key_of), None

    async def item(self, into, item: Item) -> bool:
        """The item written into the folder, removed from its source on a move once it all was;
        whether it all was."""
        self.at = item.name
        name, merged = await self._settled(into, item)
        if name is None:
            self.skipped += item.files()
            self.files += item.files()
            self.bytes += item.bytes()
            return False
        if item.kind == "folder":
            made = merged if merged is not None else await self.writer.folder(into, name)
            whole = True
            for inner in item.below:
                whole = await self.item(made, inner) and whole
        else:
            await self.writer.file(into, item, name, lambda: self.counted(self.reader.parts(item)))
            self.files += 1
            whole = True
        if self.move and whole:
            await self.reader.removed(item)
        await self.told()
        return whole

    async def renamed(self, remote: Remote, into: str, paths: list[str]) -> None:
        """A move within one source, each entry renamed into the folder."""
        for path in paths:
            if into == path or into.startswith(f"{path}/"):
                raise Refused(400, "invalid_path")
            name = posixpath.basename(path)
            self.at = name
            if posixpath.dirname(path) == into:
                continue
            entry = await remote.stat(path)
            item = Item(name, entry.kind, entry.size, entry.modified, path)
            settled, merged = await self._settled(into, item)
            if settled is None:
                self.skipped += 1
            elif merged is not None:
                for inner in await remote.listed(path):
                    await self.renamed(remote, merged, [joined(path, inner.name)])
                if not await remote.listed(path):
                    await remote.remove(path)
            else:
                await remote.rename(path, joined(into, settled))
            self.files += 1
            await self.told()


def _asked(request, data: dict) -> dict:
    user = request.user
    move = data.get("move", False)
    if not isinstance(move, bool):
        raise Refused(400, "invalid_move")
    conflict = data.get("conflict")
    if conflict is not None and conflict not in CONFLICTS:
        raise Refused(400, "invalid_conflict")
    given = data.get("paths")
    if not isinstance(given, list) or not 0 < len(given) <= MOST_PATHS:
        raise Refused(400, "invalid_paths")
    paths = list(dict.fromkeys(asked(path, root=False) for path in given))
    into = asked(data.get("path", ""))
    origin = source(user, data.get("from"), Role.EDIT if move else Role.READ)
    target = source(user, data.get("to"), Role.EDIT)
    if origin.kind == "ponistra" and None in (_node_of(path) for path in paths):
        raise Refused(400, "invalid_paths")
    if move and origin.kind == target.kind == "ponistra":
        raise Refused(400, "invalid_move")
    if target.kind == "ponistra":
        _TreeWriter(user, target.of)._root(into)
    confirmed(request, [target, *([origin] if move else [])])
    return {
        "from": origin.key,
        "from_name": origin.name,
        "paths": paths,
        "to": target.key,
        "to_name": target.name,
        "path": into,
        "move": move,
        "conflict": conflict,
        "site": request.build_absolute_uri("/"),
    }


def _ends(user, parameters: dict) -> tuple[Source, Source]:
    move = parameters["move"]
    return (
        source(user, parameters["from"], Role.EDIT if move else Role.READ),
        source(user, parameters["to"], Role.EDIT),
    )


async def _transferred(user, parameters: dict) -> dict:
    origin, target = await database(_ends)(user, parameters)
    move, into, paths = parameters["move"], parameters["path"], parameters["paths"]
    opened_here: list[Remote] = []

    async def remote_of(found: Source) -> Remote:
        remote = await opened(found)
        opened_here.append(remote)
        return remote

    try:
        same = origin.key == target.key
        within = origin.kind == target.kind == "ponistra"
        if origin.kind == "ponistra":
            reader = _TreeReader(user, parameters["site"], move, leaving=not within)
        else:
            reader = _RemoteReader(await remote_of(origin))
        if within:
            writer = _TreeCopier(user, target.of, reader.nodes)
            root = await writer.root(into)
        elif target.kind == "ponistra":
            writer = _TreeWriter(user, target.of)
            root = await writer.root(into)
        else:
            remote = reader.remote if same else await remote_of(target)
            writer = _RemoteWriter(remote)
            root = writer.root(into)
        transfer = _Transfer(reader, writer, parameters["conflict"], move)
        if same and move:
            transfer.of_files = len(paths)
            await transfer.told(now=True)
            await transfer.renamed(reader.remote, into, paths)
        else:
            planned = await reader.planned(paths)
            transfer.of_files = sum(item.files() for item in planned)
            transfer.of_bytes = sum(item.bytes() for item in planned)
            transfer.skipped = reader.left
            if within:
                transfer.of_bytes = 0
                above = await database(_ancestry)(root)
                if any(item.at in above for item in planned):
                    raise Refused(400, "cycle")
            await transfer.told(now=True)
            for item in planned:
                if same and item.kind == "folder" and (into + "/").startswith(item.at + "/"):
                    raise Refused(400, "invalid_path")
                await transfer.item(root, item)
        return {**transfer._shown(), "running": False}
    finally:
        for remote in opened_here:
            await remote.close()


def _ancestry(node: Node | None) -> set[str]:
    return {str(each.pk) for each in node.ancestry()} if node else set()


def _transfer_done(user, parameters: dict) -> dict:
    """What was chosen copied or moved; what was done before a server's refusal stays done."""
    try:
        return async_to_sync(_transferred)(user, parameters)
    except _GivenUp:
        return {}
    finally:
        extraction.wake()
        previews.wake()


ALGORITHMS = {"sha256", "sha1", "md5"}


def _checksum_asked(request, data: dict) -> dict:
    algorithm = data.get("algorithm", "sha256")
    if algorithm not in ALGORITHMS:
        raise Refused(400, "invalid_algorithm")
    found = source(request.user, data.get("source"))
    if found.kind == "ponistra":
        raise Refused(400, "invalid_source")
    return {
        "source": found.key,
        "path": asked(data.get("path"), root=False),
        "algorithm": algorithm,
    }


async def _summed(user, parameters: dict) -> dict:
    found = await database(source)(user, parameters["source"])
    remote = await opened(found)
    try:
        entry = await remote.stat(parameters["path"])
        if entry.kind != "file":
            raise Refused(400, "not_a_file")
        summed = hashlib.new(parameters["algorithm"], usedforsecurity=False)
        async for part in remote.chunks(parameters["path"], 0, entry.size or 0):
            summed.update(part)
    finally:
        await remote.close()
    return {"algorithm": parameters["algorithm"], "digest": summed.hexdigest()}


def _checksum_done(user, parameters: dict) -> dict:
    return async_to_sync(_summed)(user, parameters)


# A transfer may be given up while it runs, as what makes a file may: what it wrote stays.
KINDS = {
    "transfer": Kind(_asked, _transfer_done, saves=True),
    "checksum": Kind(_checksum_asked, _checksum_done, saves=False),
}
