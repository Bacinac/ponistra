"""What a folder holds all the way down, as any source lists it: the entries whose names match,
and its size. A walk ends early, `partial`, rather than outlast the proxies in front of the
request; a folder a symbolic link leads to is not entered, as it may lead back up."""

import time
import unicodedata

from apps.core.api import Refused
from apps.locations.remote import PATH, Failed, Remote, joined

WALKED_FOR = 25
FOUND = 500
QUERY = 200


def _folded(text: str) -> str:
    return "".join(
        each
        for each in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(each)
    )


class _Walk:
    def __init__(self, remote: Remote):
        self.remote = remote
        self.until = time.monotonic() + WALKED_FOR
        self.partial = False

    async def entries(self, path: str):
        """Each entry below the folder with its path, a folder before what it holds."""
        waiting = [path]
        while waiting:
            if time.monotonic() > self.until:
                self.partial = True
                return
            folder = waiting.pop()
            try:
                listed = await self.remote.listed(folder)
            except Failed as failed:
                if failed.status not in (403, 404) or folder == path:
                    raise
                self.partial = True
                continue
            for entry in listed:
                inner = joined(folder, entry.name)
                yield inner, entry
                if entry.kind == "folder" and entry.link is None and len(inner) < PATH:
                    waiting.append(inner)


def query_of(given: object) -> str:
    if not isinstance(given, str) or not given.strip() or len(given) > QUERY:
        raise Refused(400, "invalid_query")
    return _folded(given.strip())


async def searched(remote: Remote, path: str, query: str) -> dict:
    """The entries below the folder whose names hold the query, as a name is matched without
    regard to case or accents."""
    walk = _Walk(remote)
    found: list[dict] = []
    async for inner, entry in walk.entries(path):
        if query in _folded(entry.name):
            found.append({**entry.described(), "path": inner})
            if len(found) >= FOUND:
                walk.partial = True
                break
    return {"entries": found, "partial": walk.partial}


async def sized(remote: Remote, path: str) -> dict:
    walk = _Walk(remote)
    size = files = folders = 0
    async for _, entry in walk.entries(path):
        if entry.kind == "folder":
            folders += 1
        elif entry.kind == "file" and entry.link is None:
            files += 1
            size += entry.size or 0
    return {"size": size, "files": files, "folders": folders, "partial": walk.partial}


def mode_of(given: object) -> int:
    if not isinstance(given, int) or isinstance(given, bool) or not 0 <= given <= 0o7777:
        raise Refused(400, "invalid_mode")
    return given


def id_of(given: object) -> int:
    if not isinstance(given, int) or isinstance(given, bool) or not 0 <= given < 2**32:
        raise Refused(400, "invalid_owner")
    return given
