"""The Docker Engine API (Apache 2.0) as the backend speaks it itself: HTTP/1.1 over the stdin and
stdout of `ssh … docker system dial-stdio`, which is how `docker -H ssh://` reaches the daemon,
through the location's own ssh config, tunnel, jump and host keys (D55). Each request is an ssh of
its own, closed with its answer; a stream (logs, events) or a shell holds its ssh until it ends."""

import asyncio
import json
import re
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import quote, urlencode

from apps.locations import sftp
from apps.locations.remote import Failed

# The oldest Engine API Docker 29 still answers, and all this module asks for.
VERSION = "/v1.44"
CHUNK = 64 * 1024
OPENING = 30
ANSWERING = 60
SAID = 16 * 1024
# A JSON answer is no larger: a host's whole list of images or containers fits many times over.
ANSWER = 64 * 1024 * 1024

DIAL = "docker system dial-stdio"

# What ssh, the forced command or docker on the host said as it ended, before the location's own.
FAILURES = [
    (re.compile(r"^ponistra: refused", re.M), "docker_command_refused"),
    (
        re.compile(r"permission denied while trying to connect to the Docker daemon", re.I),
        "docker_denied",
    ),
    (
        re.compile(r"Cannot connect to the Docker daemon|Is the docker daemon running"),
        "docker_down",
    ),
    (
        re.compile(r"can't cd to|cd: .*(No such file|can't cd|Not a directory)"),
        "docker_stack_missing",
    ),
    (re.compile(r"docker: (command )?not found|docker: No such file"), "docker_missing"),
    (
        re.compile(r"unknown (shorthand flag|command).*compose|'compose' is not a docker command"),
        "docker_compose_missing",
    ),
]


class Refusal(Failed):
    """The daemon answered with an error, its message shown to the administrator as it said it."""

    def __init__(self, status: int, message: str):
        code = {404: "docker_not_found", 409: "docker_conflict"}.get(status, "docker_refused")
        super().__init__(code, 404 if status == 404 else 409)
        self.message = message


class Process:
    """ssh running one command on the host, its stdin and stdout the stream to it."""

    def __init__(self, target: sftp.Target, command: str):
        self.target = target
        self.command = command
        self.said = b""
        self.folder: Path | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.hearing: asyncio.Task | None = None

    async def open(self) -> Process:
        self.folder, environment = sftp.placed(self.target)
        try:
            self.process = await asyncio.create_subprocess_exec(
                "ssh",
                "-F",
                str(self.folder / "config"),
                "-T",
                "--",
                "location",
                self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=environment,
                limit=1024 * 1024,
            )
        except OSError as error:
            self.close()
            raise RuntimeError(f"ssh could not start: {error}") from error
        self.hearing = asyncio.create_task(self._heard())
        return self

    @property
    def reader(self) -> asyncio.StreamReader:
        return self.process.stdout

    @property
    def writer(self) -> asyncio.StreamWriter:
        return self.process.stdin

    async def _heard(self) -> None:
        while part := await self.process.stderr.read(4096):
            if len(self.said) < SAID:
                self.said += part

    def known_hosts(self) -> str:
        try:
            return (self.folder / "known_hosts").read_text()
        except OSError, TypeError:
            return self.target.known_hosts

    async def failure(self) -> Failed:
        """Why the command ended without the answer it was to give."""
        if self.process and self.process.returncode is None:
            with suppress(TimeoutError):
                await asyncio.wait_for(self.process.wait(), 5)
        if self.hearing:
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(self.hearing), 5)
        said = self.said.decode(errors="replace").strip()
        for pattern, code in FAILURES:
            if pattern.search(said):
                return Failed(code)
        return sftp.failure(said, self.target.host)

    async def ended(self) -> int | None:
        """Waits for the command to exit by itself, its status."""
        status = await self.process.wait()
        if self.hearing:
            await self.hearing
        return status

    def close(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.kill()
        if self.hearing and not self.hearing.done():
            self.hearing.cancel()
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None


class Answer:
    def __init__(self, status: int, headers: dict[str, str], reader: asyncio.StreamReader):
        self.status = status
        self.headers = headers
        self.reader = reader

    async def body(self) -> AsyncIterator[bytes]:
        reader = self.reader
        if self.status < 200 or self.status in (204, 304):
            return
        if self.headers.get("transfer-encoding", "").lower() == "chunked":
            while True:
                size = int((await reader.readline()).split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while (await reader.readline()).strip():
                        pass
                    return
                yield await reader.readexactly(size)
                await reader.readexactly(2)
        elif "content-length" in self.headers:
            left = int(self.headers["content-length"])
            while left:
                part = await reader.read(min(left, CHUNK))
                if not part:
                    raise asyncio.IncompleteReadError(b"", left)
                left -= len(part)
                yield part
        else:
            while part := await reader.read(CHUNK):
                yield part

    async def whole(self, most: int = ANSWER) -> bytes:
        data = bytearray()
        async for part in self.body():
            data += part
            if len(data) > most:
                raise Failed("docker_answer_too_large", 502)
        return bytes(data)

    async def json(self):
        data = await self.whole()
        return json.loads(data) if data else None

    async def refusal(self) -> Refusal:
        try:
            data = await self.whole(SAID)
            message = json.loads(data).get("message", "") if data else ""
        except ValueError, AttributeError, asyncio.IncompleteReadError:
            message = ""
        return Refusal(self.status, str(message))


def path_of(path: str, query: dict | None = None) -> str:
    given = {key: value for key, value in (query or {}).items() if value is not None}
    return VERSION + path + (f"?{urlencode(given)}" if given else "")


def part(value: str) -> str:
    """An id or a name as one segment of the API's path."""
    return quote(value, safe="")


async def _head(reader: asyncio.StreamReader) -> tuple[int, dict[str, str]]:
    line = await reader.readline()
    found = re.match(rb"HTTP/1\.[01] (\d{3})", line)
    if found is None:
        raise asyncio.IncompleteReadError(line, None)
    headers: dict[str, str] = {}
    while (line := await reader.readline()).strip():
        name, _, value = line.decode("latin-1").partition(":")
        headers[name.strip().lower()] = value.strip()
    return int(found[1]), headers


class Engine:
    """The daemon of one Docker host."""

    def __init__(self, target: sftp.Target, learned=None):
        self.target = target
        # Called with the host keys a first connection found, to keep with the location.
        self.learned = learned

    async def _sent(
        self, method: str, path: str, body: object, upgrade: bool
    ) -> tuple[Process, Answer]:
        process = await Process(self.target, DIAL).open()
        data = b"" if body is None else json.dumps(body).encode()
        lines = [f"{method} {path} HTTP/1.1", "Host: docker"]
        if upgrade:
            lines += ["Connection: Upgrade", "Upgrade: tcp"]
        else:
            lines += ["Connection: close"]
        if body is not None:
            lines += ["Content-Type: application/json", f"Content-Length: {len(data)}"]
        try:
            process.writer.write(("\r\n".join(lines) + "\r\n\r\n").encode() + data)
            await process.writer.drain()
            status, headers = await asyncio.wait_for(_head(process.reader), OPENING)
        except OSError, TimeoutError, asyncio.IncompleteReadError, ValueError:
            failure = await process.failure()
            process.close()
            raise failure from None
        if self.learned and (known := process.known_hosts()) != self.target.known_hosts:
            await self.learned(known)
        return process, Answer(status, headers, process.reader)

    @asynccontextmanager
    async def answer(self, method: str, path: str, body: object = None, upgrade: bool = False):
        """The daemon's answer, its body read while it lasts; an error answer raises Refusal."""
        process, answer = await self._sent(method, path, body, upgrade)
        try:
            if answer.status >= 400:
                raise await answer.refusal()
            yield answer, process
        finally:
            process.close()

    async def call(self, method: str, path: str, query: dict | None = None, body: object = None):
        async with self.answer(method, path_of(path, query), body) as (answer, process):
            try:
                return await asyncio.wait_for(answer.json(), ANSWERING)
            except TimeoutError, asyncio.IncompleteReadError, OSError:
                raise await process.failure() from None
            except ValueError:
                raise Failed("docker_garbled", 502) from None

    async def get(self, path: str, **query):
        return await self.call("GET", path, query)

    async def post(self, path: str, body: object = None, **query):
        return await self.call("POST", path, query, body)

    async def delete(self, path: str, **query):
        return await self.call("DELETE", path, query)


def frames(data: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """The frames a container's stream without a terminal sends whole (stream 1 stdout, 2
    stderr, each after a header of eight bytes), and what is left of the next."""
    found = []
    while len(data) >= 8:
        size = int.from_bytes(data[4:8])
        if len(data) < 8 + size:
            break
        found.append((data[0], data[8 : 8 + size]))
        data = data[8 + size :]
    return found, data
