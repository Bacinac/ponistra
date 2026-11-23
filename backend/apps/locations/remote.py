"""What every kind of location answers alike: its paths, its entries and why a server refused."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from icu import Collator, Locale, UCollAttribute, UCollAttributeValue

from apps.core.api import Refused

# The longest path a request names below a location, as a path on Linux may be.
PATH = 4096
# A text read to be edited, and written back, is no larger.
EDITED = 1024 * 1024
CHUNK = 32 * 1024
BY_NAME = Collator.createInstance(Locale("hr"))
BY_NAME.setAttribute(UCollAttribute.NUMERIC_COLLATION, UCollAttributeValue.ON)


class Failed(Refused):
    """The server could not be reached, signed in to or asked, by the code the page names it by."""

    def __init__(self, code: str, status: int = 409):
        super().__init__(status, code)


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str  # folder, file, link (to nowhere it can follow), other
    size: int | None
    modified: datetime | None
    # Where a symbolic link points; the kind is then its target's.
    link: str | None = None
    # Hidden by the server's own mark rather than a leading dot, as SMB's.
    hidden: bool = False

    def described(self) -> dict:
        shown = {"name": self.name, "kind": self.kind, "size": self.size, "modified": self.modified}
        if self.link is not None:
            shown["link"] = self.link
        if self.hidden:
            shown["hidden"] = True
        return shown


@dataclass(frozen=True)
class Stat:
    """An entry itself, a link and not what it points at, with whom it belongs to and its mode
    where the server has them."""

    entry: Entry
    mode: int | None = None
    uid: int | None = None
    gid: int | None = None
    owner: str | None = None
    group: str | None = None
    attributes: tuple[str, ...] = ()

    def described(self, path: str) -> dict:
        shown = {
            **self.entry.described(),
            "path": path,
            "mode": self.mode,
            "uid": self.uid,
            "gid": self.gid,
            "owner": self.owner,
            "group": self.group,
        }
        if self.attributes:
            shown["attributes"] = list(self.attributes)
        return shown


def asked(path: object, *, root: bool = True) -> str:
    """A path below the location as slashes join it, never above it: a colleague it is shared
    with reaches through the owner's account no more than the owner set it up to open."""
    if not isinstance(path, str) or len(path) > PATH or "\0" in path or "\\" in path:
        raise Refused(400, "invalid_path")
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if ".." in parts or (not parts and not root):
        raise Refused(400, "invalid_path")
    return "/".join(parts)


def name_of(given: object) -> str:
    """A name a new file or folder takes, of one path segment."""
    if (
        not isinstance(given, str)
        or not given.strip()
        or len(given.encode()) > 255
        or given in (".", "..")
        or any(each in given for each in "/\\\0")
    ):
        raise Refused(400, "invalid_file_name")
    return given


def joined(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder else name


def ordered(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda each: (each.kind != "folder", BY_NAME.getSortKey(each.name)))


class Remote(Protocol):
    """A location reached: what it holds, read and changed by paths below it."""

    async def listed(self, path: str) -> list[Entry]: ...

    async def stat(self, path: str) -> Entry: ...

    async def described(self, path: str) -> Stat: ...

    async def chmod(self, path: str, mode: int) -> None: ...

    async def chown(self, path: str, uid: int, gid: int) -> None: ...

    def chunks(self, path: str, start: int, length: int) -> AsyncIterator[bytes]: ...

    async def whole(self, path: str, most: int) -> bytes | None: ...

    async def write(self, path: str, data: bytes) -> None: ...

    async def put(self, path: str, parts: AsyncIterator[bytes]) -> None: ...

    async def mkdir(self, path: str) -> None: ...

    async def rename(self, path: str, to: str) -> None: ...

    async def remove(self, path: str) -> None: ...

    async def close(self) -> None: ...
