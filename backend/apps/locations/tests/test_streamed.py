import asyncio
import itertools
import uuid

import pytest
from asgiref.sync import async_to_sync

from apps.locations import sftp
from apps.locations.remote import Failed

from .test_locations import target

# Parts cut across the packets' bounds, as a link's messages carry them.
SIZES = (1, 3, 7, 4096, 5, 2, 65536, 11)


class Piped:
    """The test server's sftp-server behind a pipe, its bytes handed on in parts of every size."""

    def __init__(self, given: sftp.Target):
        self.given = given
        self.sizes = itertools.cycle(SIZES)
        self.held = b""
        self.ended: tuple[int, str] | None = None

    async def opened(self) -> Piped:
        self.folder, environment = sftp.placed(self.given)
        self.process = await asyncio.create_subprocess_exec(
            "ssh",
            "-F",
            str(self.folder / "config"),
            "-s",
            "--",
            "location",
            "sftp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
        )
        return self

    async def read(self) -> bytes:
        if not self.held:
            self.held = await self.process.stdout.read(sftp.RECEIVED)
            if not self.held:
                self.ended = (1000, "")
                return b""
        size = next(self.sizes)
        part, self.held = self.held[:size], self.held[size:]
        return part

    def write(self, data: bytes) -> None:
        for at in range(0, len(data), 5):
            self.process.stdin.write(data[at : at + 5])

    async def close(self) -> None:
        if self.process.returncode is None:
            self.process.kill()
        await self.process.wait()


def why(stream: Piped) -> Failed:
    return Failed("location_closed" if stream.ended == (1000, "") else "location_failed")


def streamed(path: str, opening=None) -> sftp.Connection:
    piped = Piped(target(path))
    return sftp.Connection(sftp.Streamed("guest", opening or piped.opened, why), path)


async def _over_stream(path: str, work):
    link = streamed(path)
    await link.open()
    try:
        return await work(sftp.Sftp(link))
    finally:
        link.end(Failed("location_closed"))


def over_stream(work, path: str = "files"):
    return async_to_sync(_over_stream)(path, work)


def test_a_session_over_a_stream_lists_reads_writes_and_renames_whatever_its_parts():
    folder = f"streamed-{uuid.uuid4().hex[:8]}"
    data = bytes(range(256)) * 700

    async def work(remote: sftp.Sftp):
        await remote.mkdir(folder)

        async def parts():
            yield data

        await remote.put(f"{folder}/a.bin", parts())
        await remote.rename(f"{folder}/a.bin", f"{folder}/b.bin")
        listed = [(each.name, each.kind, each.size) for each in await remote.listed(folder)]
        read = b"".join([part async for part in remote.chunks(f"{folder}/b.bin", 0, len(data))])
        await remote.remove(folder)
        return listed, read, remote.link.start

    listed, read, start = over_stream(work)
    assert listed == [("b.bin", "file", len(data))]
    assert read == data
    assert start == "/home/sftp/files"


def test_a_refusal_before_the_session_is_the_connections_failure():
    async def refused():
        raise Failed("guest_not_running")

    async def opened():
        link = streamed("files", refused)
        with pytest.raises(Failed) as failed:
            await link.open()
        return failed.value.error, link.gone

    assert async_to_sync(opened)() == ("guest_not_running", True)


def test_a_stream_that_ends_fails_what_waits_by_why_it_ended():
    async def work(remote: sftp.Sftp):
        await remote.link.carrier.stream.close()
        with pytest.raises(Failed) as failed:
            await remote.listed("")
        return failed.value.error

    assert over_stream(work) == "location_closed"


class Garbled:
    ended = None

    async def read(self) -> bytes:
        return b"SSH-2.0-OpenSSH\r\n"

    def write(self, data: bytes) -> None:
        pass

    async def close(self) -> None:
        pass


def test_what_is_no_packet_ends_the_session_as_garbled():
    async def garbled():
        return Garbled()

    async def opened():
        link = sftp.Connection(sftp.Streamed("guest", garbled, why), "")
        with pytest.raises(Failed) as failed:
            await link.open()
        return failed.value.error

    assert async_to_sync(opened)() == "location_garbled"


def test_a_session_ended_after_its_loop_is_gone_ends_without_it():
    async def opened():
        link = streamed("files")
        await link.open()
        return link

    link = async_to_sync(opened)()
    link.end(Failed("location_closed"))
    assert link.gone
