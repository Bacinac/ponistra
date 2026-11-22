"""A location over SMB, through D37's connector: a session of its own for each request, its
blocking calls on a worker thread."""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from functools import partial

import smbclient
import smbclient.shutil
from smbprotocol import exceptions
from smbprotocol.file_info import FileAttributes

from apps.shares import smb

from .remote import CHUNK, Entry, Failed

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


async def _off[R](work: Callable[[], R]) -> R:
    try:
        return await asyncio.to_thread(work)
    except Failed:
        raise
    except Exception as error:
        if (known := refused(error)) is None:
            raise
        raise known from None


def _entry(name: str, info) -> Entry:
    folder = bool(info.file_attributes & FileAttributes.FILE_ATTRIBUTE_DIRECTORY)
    return Entry(
        name,
        "folder" if folder else "file",
        None if folder else info.end_of_file,
        info.last_write_time.replace(tzinfo=UTC),
    )


async def reached(host: str, port: int, share: str, username: str, password: str) -> Smb:
    server = smb.Server(smb.Address(host, share), username, password, port)
    await _off(server.__enter__)
    return Smb(server)


class Smb:
    """A location over SMB; its paths below the share's folder."""

    def __init__(self, server: smb.Server):
        self.server = server

    def _full(self, path: str) -> str:
        return self.server.full(path)

    async def listed(self, path: str) -> list[Entry]:
        def scanned() -> list[Entry]:
            found = []
            for entry in smbclient.scandir(self._full(path), connection_cache=self.server.cache):
                info = entry.smb_info
                if info.file_attributes & smb.HIDDEN:
                    continue
                found.append(_entry(entry.name, info))
            return found

        if not await _off(
            lambda: smbclient.path.isdir(self._full(path), connection_cache=self.server.cache)
        ):
            raise Failed("not_a_folder", 400)
        return await _off(scanned)

    async def stat(self, path: str) -> Entry:
        def stated() -> Entry:
            found = smbclient.stat(self._full(path), connection_cache=self.server.cache)
            folder = bool(found.st_file_attributes & FileAttributes.FILE_ATTRIBUTE_DIRECTORY)
            return Entry(
                path.rsplit("/", 1)[-1],
                "folder" if folder else "file",
                None if folder else found.st_size,
                datetime.fromtimestamp(found.st_mtime, UTC),
            )

        return await _off(stated)

    async def chunks(self, path: str, start: int, length: int) -> AsyncIterator[bytes]:
        file = await _off(lambda: self.server.read(path))
        try:
            await _off(lambda: file.seek(start))
            while length > 0:
                part = await _off(partial(file.read, min(CHUNK * 8, length)))
                if not part:
                    raise Failed("file_changed")
                length -= len(part)
                yield part
        finally:
            await asyncio.to_thread(file.close)

    async def whole(self, path: str, most: int) -> bytes | None:
        def read() -> bytes | None:
            with self.server.read(path) as file:
                data = file.read(most + 1)
            return None if len(data) > most else data

        return await _off(read)

    async def write(self, path: str, data: bytes) -> None:
        def written() -> None:
            with smbclient.open_file(
                self._full(path), mode="wb", connection_cache=self.server.cache
            ) as file:
                file.write(data)

        await _off(written)

    async def put(self, path: str, parts: AsyncIterator[bytes]) -> None:
        file = await _off(
            lambda: smbclient.open_file(
                self._full(path), mode="xb", connection_cache=self.server.cache
            )
        )
        done = False
        try:
            async for part in parts:
                await _off(partial(file.write, part))
            done = True
        finally:
            await asyncio.to_thread(file.close)
            if not done:
                await asyncio.to_thread(
                    smbclient.remove, self._full(path), connection_cache=self.server.cache
                )

    async def mkdir(self, path: str) -> None:
        await _off(lambda: smbclient.mkdir(self._full(path), connection_cache=self.server.cache))

    async def rename(self, path: str, to: str) -> None:
        await _off(
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

        await _off(removed)

    async def close(self) -> None:
        await asyncio.to_thread(self.server.close)
