"""A location over SMB, through D37's connector: a session of its own for each request, its
blocking calls on a worker thread. A location behind a tunnel opens its connections through the
tunnel service: smbprotocol makes its own socket, so its transport is one that asks the worker
thread which tunnel it reaches through, set around every call the location makes."""

import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from functools import partial

import smbclient
import smbclient.shutil
import smbprotocol.connection
from smbprotocol import exceptions
from smbprotocol.file_info import FileAttributes
from smbprotocol.transport import Tcp

from apps.network import socks
from apps.shares import smb

from .remote import CHUNK, Entry, Failed, Stat

SIGNED_IN = {
    "share_login": "location_login",
    "share_not_found": "location_not_found",
    "share_denied": "location_denied",
    "share_unreachable": "location_unreachable",
}
MISSING = {
    exceptions.NtStatus.STATUS_OBJECT_NAME_NOT_FOUND,
    exceptions.NtStatus.STATUS_OBJECT_PATH_NOT_FOUND,
    exceptions.NtStatus.STATUS_NO_SUCH_FILE,
}
TAKEN = {exceptions.NtStatus.STATUS_OBJECT_NAME_COLLISION}
BUSY = {exceptions.NtStatus.STATUS_SHARING_VIOLATION}


def refused(error: BaseException) -> Failed | None:
    """What went wrong as the location's error, None for anything not the server's answer."""
    if isinstance(error, exceptions.SMBOSError):
        if error.ntstatus in MISSING:
            return Failed("file_missing", 404)
        if error.ntstatus == exceptions.NtStatus.STATUS_ACCESS_DENIED:
            return Failed("location_denied", 403)
        if error.ntstatus in TAKEN:
            return Failed("file_exists")
        if error.ntstatus in BUSY:
            return Failed("file_busy")
    code = smb.failure(error)
    return Failed(SIGNED_IN.get(code, "location_failed")) if code else None


_route = threading.local()


class Routed(Tcp):
    """smbprotocol's transport, through the tunnel the calling thread reaches through, if any."""

    def connect(self):
        tunnel = getattr(_route, "tunnel", None)
        if tunnel is None:
            return super().connect()
        with self._sock_lock:
            if not self.connected:
                try:
                    self._sock = socks.opened(tunnel, self.server, self.port, self.timeout or 20)
                except OSError as err:
                    raise ValueError(
                        f"Failed to connect to '{self.server}:{self.port}': {err}"
                    ) from err
                self.connected = True


smbprotocol.connection.Tcp = Routed


def _through[R](tunnel: int | None, work: Callable[[], R]) -> R:
    _route.tunnel = tunnel
    try:
        return work()
    finally:
        _route.tunnel = None


async def _off[R](tunnel: int | None, work: Callable[[], R]) -> R:
    try:
        return await asyncio.to_thread(_through, tunnel, work)
    except Failed:
        raise
    except Exception as error:
        if (known := refused(error)) is None:
            raise
        raise known from None


ATTRIBUTES = {
    "readonly": FileAttributes.FILE_ATTRIBUTE_READONLY,
    "hidden": FileAttributes.FILE_ATTRIBUTE_HIDDEN,
    "system": FileAttributes.FILE_ATTRIBUTE_SYSTEM,
    "archive": FileAttributes.FILE_ATTRIBUTE_ARCHIVE,
}


def _entry(name: str, info) -> Entry:
    folder = bool(info.file_attributes & FileAttributes.FILE_ATTRIBUTE_DIRECTORY)
    return Entry(
        name,
        "folder" if folder else "file",
        None if folder else info.end_of_file,
        info.last_write_time.replace(tzinfo=UTC),
        hidden=bool(info.file_attributes & smb.HIDDEN),
    )


async def reached(
    host: str, port: int, share: str, username: str, password: str, tunnel: int | None = None
) -> Smb:
    server = smb.Server(smb.Address(host, share), username, password, port)
    await _off(tunnel, server.__enter__)
    return Smb(server, tunnel)


class Smb:
    """A location over SMB; its paths below the share's folder."""

    def __init__(self, server: smb.Server, tunnel: int | None = None):
        self.server = server
        self.tunnel = tunnel

    async def _off[R](self, work: Callable[[], R]) -> R:
        return await _off(self.tunnel, work)

    async def _closed(self, work: Callable[[], object]) -> None:
        await asyncio.to_thread(_through, self.tunnel, work)

    def _full(self, path: str) -> str:
        return self.server.full(path)

    async def listed(self, path: str) -> list[Entry]:
        def scanned() -> list[Entry]:
            found = []
            for entry in smbclient.scandir(self._full(path), connection_cache=self.server.cache):
                found.append(_entry(entry.name, entry.smb_info))
            return found

        if not await self._off(
            lambda: smbclient.path.isdir(self._full(path), connection_cache=self.server.cache)
        ):
            raise Failed("not_a_folder", 400)
        return await self._off(scanned)

    async def stat(self, path: str) -> Entry:
        return (await self.described(path)).entry

    async def described(self, path: str) -> Stat:
        def stated() -> Stat:
            found = smbclient.stat(self._full(path), connection_cache=self.server.cache)
            attributes = found.st_file_attributes
            folder = bool(attributes & FileAttributes.FILE_ATTRIBUTE_DIRECTORY)
            entry = Entry(
                path.rsplit("/", 1)[-1],
                "folder" if folder else "file",
                None if folder else found.st_size,
                datetime.fromtimestamp(found.st_mtime, UTC),
                hidden=bool(attributes & smb.HIDDEN),
            )
            marked = tuple(name for name, bit in ATTRIBUTES.items() if attributes & bit)
            return Stat(entry, attributes=marked)

        return await self._off(stated)

    async def chmod(self, path: str, mode: int) -> None:
        raise Failed("not_supported", 400)

    async def chown(self, path: str, uid: int, gid: int) -> None:
        raise Failed("not_supported", 400)

    async def chunks(self, path: str, start: int, length: int) -> AsyncIterator[bytes]:
        file = await self._off(lambda: self.server.read(path))
        try:
            await self._off(lambda: file.seek(start))
            while length > 0:
                part = await self._off(partial(file.read, min(CHUNK * 8, length)))
                if not part:
                    raise Failed("file_changed")
                length -= len(part)
                yield part
        finally:
            await self._closed(file.close)

    async def whole(self, path: str, most: int) -> bytes | None:
        def read() -> bytes | None:
            with self.server.read(path) as file:
                data = file.read(most + 1)
            return None if len(data) > most else data

        return await self._off(read)

    async def write(self, path: str, data: bytes) -> None:
        def written() -> None:
            with smbclient.open_file(
                self._full(path), mode="wb", connection_cache=self.server.cache
            ) as file:
                file.write(data)

        await self._off(written)

    async def put(self, path: str, parts: AsyncIterator[bytes]) -> None:
        file = await self._off(
            lambda: smbclient.open_file(
                self._full(path), mode="xb", connection_cache=self.server.cache
            )
        )
        done = False
        try:
            async for part in parts:
                await self._off(partial(file.write, part))
            done = True
        finally:
            await self._closed(file.close)
            if not done:
                await self._closed(
                    partial(smbclient.remove, self._full(path), connection_cache=self.server.cache)
                )

    async def mkdir(self, path: str) -> None:
        await self._off(
            lambda: smbclient.mkdir(self._full(path), connection_cache=self.server.cache)
        )

    async def rename(self, path: str, to: str) -> None:
        await self._off(
            lambda: smbclient.rename(
                self._full(path), self._full(to), connection_cache=self.server.cache
            )
        )

    async def remove(self, path: str) -> None:
        def removed() -> None:
            full = self._full(path)
            if smbclient.path.isdir(full, connection_cache=self.server.cache):
                smbclient.shutil.rmtree(full, connection_cache=self.server.cache)
            else:
                smbclient.remove(full, connection_cache=self.server.cache)

        await self._off(removed)

    async def close(self) -> None:
        await self._closed(self.server.close)
