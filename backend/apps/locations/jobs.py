"""Files and folders of a location copied into PONISTRA, as an upload places them (D54)."""

import tempfile
from pathlib import PurePosixPath

from asgiref.sync import async_to_sync

from apps.access.models import Role
from apps.blobs import previews, store
from apps.core.api import Refused, optional_id
from apps.core.asyncdb import database
from apps.documents.models import Node
from apps.documents.views import created, dated, folder
from apps.imports import convert, placed
from apps.jobs.kinds import Kind
from apps.search import extraction

from . import reach
from .remote import Remote, asked

MOST_PATHS = 1000


def _asked(user, data: dict) -> tuple:
    found, _ = reach.location(user, optional_id(data.get("location")))
    given = data.get("paths")
    if not isinstance(given, list) or not 0 < len(given) <= MOST_PATHS:
        raise Refused(400, "invalid_paths")
    paths = [asked(path, root=False) for path in given]
    into, _ = folder(user, optional_id(data.get("folder")), Role.EDIT)
    return found, paths, into


def _network_asked(request, data: dict) -> dict:
    found, paths, into = _asked(request.user, data)
    return {"location": str(found.pk), "paths": paths, "folder": into and str(into.pk)}


class _Copy:
    def __init__(self, user, remote: Remote):
        self.user = user
        self.remote = remote
        self.made: list[Node] = []

    def _placed(self, file, path: str, modified, into: Node | None) -> Node:
        file.seek(0)
        blob = store.put(file)
        title, extension = placed.named(PurePosixPath(path).name)
        try:
            node, _ = placed.placed(blob, into, title, extension, self.user, None)
        except convert.Unavailable:
            raise Refused(503, "converter_unavailable") from None
        return dated(node, modified)

    async def file(self, path: str, size: int, modified, into: Node | None) -> Node:
        with tempfile.TemporaryFile() as file:
            if size:
                async for part in self.remote.chunks(path, 0, size):
                    file.write(part)
            return await database(self._placed)(file, path, modified, into)

    async def folder(self, path: str, into: Node | None) -> Node:
        name = PurePosixPath(path).name[:200]
        node = await database(created)(into, Node.Kind.FOLDER, name, None, self.user)
        for entry in await self.remote.listed(path):
            inner = f"{path}/{entry.name}"
            if entry.kind == "folder":
                await self.folder(inner, node)
            elif entry.kind == "file":
                await self.file(inner, entry.size or 0, entry.modified, node)
        return node

    async def taken(self, path: str, into: Node | None) -> None:
        entry = await self.remote.stat(path)
        if entry.kind == "folder":
            self.made.append(await self.folder(path, into))
        elif entry.kind == "file":
            self.made.append(await self.file(path, entry.size or 0, entry.modified, into))
        else:
            raise Refused(400, "not_a_file")


async def _copied(user, found, paths: list[str], into: Node | None) -> list[Node]:
    remote = await reach.reached(found)
    copy = _Copy(user, remote)
    try:
        for path in paths:
            await copy.taken(path, into)
    finally:
        await remote.close()
    return copy.made


def _network_done(user, parameters: dict) -> dict:
    """What was chosen copied into the folder, a folder with all it holds; what was copied before
    a server's refusal stays."""
    found, paths, into = _asked(user, parameters)
    try:
        # One loop for the whole copy: a connection to the server lives on the loop that opened it.
        made = async_to_sync(_copied)(user, found, paths, into)
    finally:
        extraction.wake()
        previews.wake()
    return {"folder": into and str(into.pk), "nodes": [str(node.pk) for node in made]}


KINDS = {"network": Kind(_network_asked, _network_done, saves=False)}
