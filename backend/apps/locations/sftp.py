"""A location over SFTP, spoken by the backend itself to the `sftp` subsystem of OpenSSH's client
(`ssh -s`): the libraries that speak it are not permissive (asyncssh is EPL, paramiko LGPL), and
OpenSSH brings the jump through another host and the host keys with it. SFTP version 3
(draft-ietf-secsh-filexfer-02), as OpenSSH's sftp-server speaks it."""

import asyncio
import logging
import os
import posixpath
import re
import shutil
import struct
import subprocess
import tempfile
import weakref
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from apps.network import socks

from .remote import CHUNK, Entry, Failed, Stat

log = logging.getLogger(__name__)

# A connection unused this long ends; the next request opens another.
IDLE = 120
OPENING = 20
ANSWERING = 30
AHEAD = 16
# Larger than any packet OpenSSH sends; a larger length is a shell's greeting in the stream.
PACKET = 1024 * 1024
SAID = 16 * 1024

INIT, VERSION, OPEN, CLOSE, READ, WRITE, LSTAT, FSTAT = 1, 2, 3, 4, 5, 6, 7, 8
SETSTAT = 9
OPENDIR, READDIR, REMOVE, MKDIR, RMDIR, REALPATH, STAT, RENAME = 11, 12, 13, 14, 15, 16, 17, 18
READLINK = 19
EXTENDED = 200
STATUS, HANDLE, DATA, NAME, ATTRS = 101, 102, 103, 104, 105
OK, EOF, NO_SUCH_FILE, PERMISSION_DENIED, FAILURE = 0, 1, 2, 3, 4
A_SIZE, A_UIDGID, A_PERMISSIONS, A_ACMODTIME, A_EXTENDED = 0x1, 0x2, 0x4, 0x8, 0x80000000
O_READ, O_WRITE, O_CREAT, O_TRUNC, O_EXCL = 0x1, 0x2, 0x8, 0x10, 0x20

# What goes into the ssh config this connection writes, so nothing a user typed can add an option.
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}")
USER = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._@-]{0,127}")
# A jump's port follows a colon, so an IPv6 address there stands in brackets.
JUMP = re.compile(
    rf"(?:({USER.pattern})@)?([A-Za-z0-9][A-Za-z0-9.-]{{0,252}}|\[[0-9A-Fa-f:.]{{2,45}}\])"
    r"(?::(\d{1,5}))?"
)

# What ssh says when it cannot sign in, as the location's error; the first that matches wins.
FAILURES = [
    (re.compile(r"^tunnel down: ", re.M), "location_tunnel_down"),
    (re.compile(r"^tunnel: ", re.M), "location_unreachable"),
    (re.compile(r"REMOTE HOST IDENTIFICATION HAS CHANGED"), "location_host_key_changed"),
    (re.compile(r"Host key verification failed"), "location_host_key_changed"),
    (re.compile(r"Load key .*: (invalid format|bad permissions)"), "location_key_unreadable"),
    (re.compile(r"Permission denied \(|Too many authentication failures"), "location_login"),
    (re.compile(r"Could not resolve hostname"), "location_host_unknown"),
    (re.compile(r"subsystem request failed"), "location_sftp_missing"),
    (
        re.compile(
            r"Connection refused|timed out|No route to host|Network is unreachable"
            r"|Connection reset|Connection closed|banner exchange"
        ),
        "location_unreachable",
    ),
]


@dataclass(frozen=True)
class Target:
    """Where the location stands and how it signs in, its secret opened."""

    host: str
    port: int
    user: str
    path: str
    password: str | None
    key: str | None
    jump: str
    known_hosts: str
    tunnel: int | None = None


def jump_of(given: str) -> tuple[str | None, str, int] | None:
    """`user@host:port`, its user and port optional, as the jump's parts."""
    found = JUMP.fullmatch(given)
    if found is None:
        return None
    user, host, port = found.groups()
    port = int(port) if port else 22
    return (user, host.strip("[]"), port) if 0 < port < 65536 else None


def _config(target: Target, folder: Path) -> str:
    def entry(name: str, host: str, port: int, user: str | None) -> list[str]:
        return [f"Host {name}", f"  HostName {host}", f"  Port {port}"] + (
            [f"  User {user}"] if user else []
        )

    # The first hop reaches its host through the tunnel, the one after it through the first.
    through = (
        [f"  ProxyCommand {socks.proxy_command(target.tunnel)}", "  ProxyUseFdpass yes"]
        if target.tunnel is not None
        else []
    )
    lines = entry("location", target.host, target.port, target.user)
    if target.jump:
        jump_user, jump_host, jump_port = jump_of(target.jump)
        lines += ["  ProxyJump jump", *entry("jump", jump_host, jump_port, jump_user), *through]
    else:
        lines += through
    lines += [
        "Host *",
        f"  UserKnownHostsFile {folder}/known_hosts",
        "  GlobalKnownHostsFile /dev/null",
        "  StrictHostKeyChecking accept-new",
        "  UpdateHostKeys no",
        "  HashKnownHosts no",
        "  ConnectTimeout 10",
        "  ServerAliveInterval 15",
        "  ServerAliveCountMax 3",
        "  IdentitiesOnly yes",
        "  IdentityAgent none",
        "  ControlMaster no",
        "  ControlPath none",
    ]
    if target.key is not None:
        lines += [
            f"  IdentityFile {folder}/key",
            "  PubkeyAuthentication yes",
            "  PasswordAuthentication no",
            "  KbdInteractiveAuthentication no",
            "  BatchMode yes",
        ]
    else:
        lines += [
            "  IdentityFile none",
            "  PubkeyAuthentication no",
            "  PasswordAuthentication yes",
            "  KbdInteractiveAuthentication yes",
            "  NumberOfPasswordPrompts 1",
            "  BatchMode no",
        ]
    return "\n".join(lines) + "\n"


def _private(path: Path, text: str, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "w") as file:
        file.write(text)


def _named(folder: Path) -> dict[str, str]:
    """The environment OpenSSH runs in: nss_wrapper names the user it runs as, whom no passwd
    lists and without whom it refuses to start."""
    uid, gid = os.getuid(), os.getgid()
    _private(folder / "passwd", f"ponistra:x:{uid}:{gid}::{folder}:/bin/false\n", 0o644)
    _private(folder / "group", f"ponistra:x:{gid}:\n", 0o644)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(folder),
        "LD_PRELOAD": "libnss_wrapper.so",
        "NSS_WRAPPER_PASSWD": str(folder / "passwd"),
        "NSS_WRAPPER_GROUP": str(folder / "group"),
    }


def placed(target: Target) -> tuple[Path, dict[str, str]]:
    """A folder of the connection's own with its config, known hosts and secret, and the
    environment ssh runs in, the password told by askpass."""
    folder = Path(tempfile.mkdtemp(prefix="location-"))
    _private(folder / "config", _config(target, folder))
    _private(folder / "known_hosts", target.known_hosts)
    environment = _named(folder)
    if target.key is not None:
        _private(folder / "key", target.key if target.key.endswith("\n") else f"{target.key}\n")
    else:
        _private(folder / "password", target.password or "")
        _private(folder / "askpass", f'#!/bin/sh\nexec cat "{folder}/password"\n', 0o700)
        environment |= {"SSH_ASKPASS": str(folder / "askpass"), "SSH_ASKPASS_REQUIRE": "force"}
    return folder, environment


def failure(said: str, host: str) -> Failed:
    """Why ssh to the host ended, by what it said."""
    for pattern, code in FAILURES:
        if pattern.search(said):
            return Failed(code)
    log.warning("ssh to %s ended: %s", host, said or "without a word")
    return Failed("location_failed")


def made_key(comment: str) -> tuple[str, str]:
    """A key made for one location alone: its private half and the public one."""
    with tempfile.TemporaryDirectory(prefix="location-") as made:
        folder = Path(made)
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", folder / "key"],
            check=True,
            capture_output=True,
            timeout=30,
            env=_named(folder),
        )
        return (folder / "key").read_text(), (folder / "key.pub").read_text().strip()


def _u32(value: int) -> bytes:
    return struct.pack(">I", value)


def _u64(value: int) -> bytes:
    return struct.pack(">Q", value)


def _string(value: str | bytes) -> bytes:
    data = value.encode() if isinstance(value, str) else value
    return _u32(len(data)) + data


def _attrs(permissions: int | None = None) -> bytes:
    return _u32(0) if permissions is None else _u32(A_PERMISSIONS) + _u32(permissions)


def _owned(uid: int, gid: int) -> bytes:
    return _u32(A_UIDGID) + _u32(uid) + _u32(gid)


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.at = 0

    def u32(self) -> int:
        (value,) = struct.unpack_from(">I", self.data, self.at)
        self.at += 4
        return value

    def u64(self) -> int:
        (value,) = struct.unpack_from(">Q", self.data, self.at)
        self.at += 8
        return value

    def raw(self) -> bytes:
        length = self.u32()
        value = self.data[self.at : self.at + length]
        self.at += length
        return value

    def string(self) -> str:
        return self.raw().decode(errors="surrogateescape")

    def attrs(self) -> dict:
        flags = self.u32()
        found: dict = {}
        if flags & A_SIZE:
            found["size"] = self.u64()
        if flags & A_UIDGID:
            found["uid"], found["gid"] = self.u32(), self.u32()
        if flags & A_PERMISSIONS:
            found["permissions"] = self.u32()
        if flags & A_ACMODTIME:
            found["atime"], found["mtime"] = self.u32(), self.u32()
        if flags & A_EXTENDED:
            for _ in range(self.u32()):
                self.raw()
                self.raw()
        return found


def _kind(attrs: dict) -> str:
    kind = attrs.get("permissions", 0) & 0o170000
    return {0o040000: "folder", 0o100000: "file", 0o120000: "link"}.get(kind, "other")


def _entry(name: str, attrs: dict, link: str | None = None) -> Entry:
    kind = _kind(attrs)
    mtime = attrs.get("mtime")
    return Entry(
        name,
        kind,
        attrs.get("size") if kind == "file" else None,
        datetime.fromtimestamp(mtime, UTC) if mtime is not None else None,
        link,
    )


def _owners(longname: str) -> tuple[str | None, str | None]:
    """The owner and group a server's `ls -l` line names, as OpenSSH writes it."""
    parts = longname.split(None, 4)
    return (parts[2], parts[3]) if len(parts) == 5 else (None, None)


class Connection:
    """One connection to the server's `sftp` subsystem, requests answered by their ids."""

    def __init__(self, target: Target):
        self.target = target
        self.waiting: dict[int, asyncio.Future] = {}
        self.next = 1
        self.said = b""
        self.failure: Failed | None = None
        self.extensions: set[str] = set()
        self.start = ""
        self.process: asyncio.subprocess.Process | None = None
        self.idle: asyncio.TimerHandle | None = None
        self.folder: Path | None = None
        self.version: asyncio.Future = asyncio.get_running_loop().create_future()

    @property
    def gone(self) -> bool:
        return self.failure is not None

    async def open(self) -> None:
        self.folder, environment = placed(self.target)
        try:
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
                stderr=asyncio.subprocess.PIPE,
                env=environment,
            )
        except OSError as error:
            self.end(Failed("location_failed", 500))
            raise RuntimeError(f"ssh could not start: {error}") from error
        self.heard = asyncio.create_task(self._heard())
        self.receiving = asyncio.create_task(self._received())
        self.send(bytes([INIT]) + _u32(3))
        try:
            await asyncio.wait_for(asyncio.shield(self.version), OPENING)
        except TimeoutError:
            self.end(Failed("location_unreachable"))
        if self.failure:
            raise self.failure
        # SFTP takes a relative path from the user's home, where a shell would expand `~`.
        given = re.sub(r"^~(/|$)", "./", self.target.path) or "."
        self.start = await self.realpath(given)
        self.touch()

    def known_hosts(self) -> str:
        try:
            return (self.folder / "known_hosts").read_text()
        except OSError:
            return self.target.known_hosts

    def _failed(self) -> Failed:
        return failure(self.said.decode(errors="replace").strip(), self.target.host)

    def end(self, failure: Failed | None = None) -> None:
        if self.gone:
            return
        self.failure = failure or self._failed()
        if self.idle:
            self.idle.cancel()
        if self.process and self.process.returncode is None:
            self.process.kill()
        if not self.version.done():
            self.version.set_exception(self.failure)
            self.version.exception()
        for waiting in self.waiting.values():
            if not waiting.done():
                waiting.set_exception(self.failure)
                waiting.exception()
        self.waiting.clear()
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)

    def touch(self) -> None:
        if self.idle:
            self.idle.cancel()
        self.idle = asyncio.get_running_loop().call_later(IDLE, self._idled)

    def _idled(self) -> None:
        if self.waiting:
            self.touch()
        else:
            self.end(Failed("location_closed"))

    async def _heard(self) -> None:
        while part := await self.process.stderr.read(4096):
            if len(self.said) < SAID:
                self.said += part

    async def _received(self) -> None:
        stream = self.process.stdout
        try:
            while True:
                length = struct.unpack(">I", await stream.readexactly(4))[0]
                if not 0 < length <= PACKET:
                    log.warning("sftp on %s sent what is no packet", self.target.host)
                    return self.end(Failed("location_garbled"))
                packet = await stream.readexactly(length)
                self._answered(packet[0], _Reader(packet[1:]))
        except asyncio.IncompleteReadError:
            await self.process.wait()
            await self.heard
            self.end()

    def _answered(self, kind: int, reader: _Reader) -> None:
        if kind == VERSION:
            reader.u32()
            while reader.at < len(reader.data):
                self.extensions.add(reader.string())
                reader.string()
            if not self.version.done():
                self.version.set_result(None)
            return
        asked = self.waiting.pop(reader.u32(), None)
        if asked is None or asked.done():
            return
        if kind != STATUS:
            asked.set_result((kind, reader))
            return
        code, message = reader.u32(), reader.string()
        if code in (OK, EOF):
            asked.set_result((kind, code))
        elif code == NO_SUCH_FILE:
            asked.set_exception(Failed("file_missing", 404))
        elif code == PERMISSION_DENIED:
            asked.set_exception(Failed("location_denied", 403))
        elif code == FAILURE:
            asked.set_exception(Failed("location_refused"))
        else:
            log.warning("sftp on %s refused a request: %s %s", self.target.host, code, message)
            asked.set_exception(Failed("location_refused"))

    def send(self, body: bytes) -> None:
        self.process.stdin.write(_u32(len(body)) + body)

    async def request(self, kind: int, *parts: bytes):
        if self.failure:
            raise self.failure
        number = self.next
        self.next += 1
        answer = asyncio.get_running_loop().create_future()
        self.waiting[number] = answer
        self.touch()
        self.send(bytes([kind]) + _u32(number) + b"".join(parts))
        try:
            return await asyncio.wait_for(asyncio.shield(answer), ANSWERING)
        except TimeoutError:
            self.end(Failed("location_unreachable"))
            raise self.failure from None

    async def _expected(self, answer: int, kind: int, *parts: bytes) -> _Reader:
        answered, reader = await self.request(kind, *parts)
        if answered != answer:
            raise Failed("location_garbled")
        return reader

    async def realpath(self, path: str) -> str:
        reader = await self._expected(NAME, REALPATH, _string(path))
        reader.u32()
        return reader.string()

    async def stat(self, path: str, follow: bool = True) -> dict:
        return (await self._expected(ATTRS, STAT if follow else LSTAT, _string(path))).attrs()

    async def open_file(self, path: str, flags: int, permissions: int | None = None) -> bytes:
        given = _attrs(permissions)
        return (await self._expected(HANDLE, OPEN, _string(path), _u32(flags), given)).raw()

    async def close(self, handle: bytes) -> None:
        await self.request(CLOSE, _string(handle))

    async def read(self, handle: bytes, offset: int, length: int) -> bytes | None:
        """Up to `length` bytes from `offset`, None at the end of the file."""
        kind, reader = await self.request(READ, _string(handle), _u64(offset), _u32(length))
        if kind == STATUS:
            return None
        if kind != DATA:
            raise Failed("location_garbled")
        return reader.raw()

    async def write(self, handle: bytes, offset: int, data: bytes) -> None:
        await self.request(WRITE, _string(handle), _u64(offset), _string(data))

    async def readlink(self, path: str) -> str:
        reader = await self._expected(NAME, READLINK, _string(path))
        reader.u32()
        return reader.string()

    async def setstat(self, path: str, attrs: bytes) -> None:
        await self.request(SETSTAT, _string(path), attrs)

    async def entries(self, path: str) -> list[tuple[str, dict]]:
        return [(name, attrs) for name, _, attrs in await self.lines(path)]

    async def lines(self, path: str) -> list[tuple[str, str, dict]]:
        """A folder's entries, each with the `ls -l` line the server writes of it."""
        handle = (await self._expected(HANDLE, OPENDIR, _string(path))).raw()
        found = []
        try:
            while True:
                kind, reader = await self.request(READDIR, _string(handle))
                if kind == STATUS:
                    break
                if kind != NAME:
                    raise Failed("location_garbled")
                for _ in range(reader.u32()):
                    name = reader.string()
                    longname = reader.string()
                    attrs = reader.attrs()
                    if name not in (".", ".."):
                        found.append((name, longname, attrs))
        finally:
            if not self.gone:
                await self.close(handle)
        return found


_connections: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


async def connection(key: str, target: Target) -> Connection:
    """The location's open connection or a new one, once it is signed in; a location changed
    since comes by another key, and its old connection ends unused."""
    loop = asyncio.get_running_loop()
    kept: dict[str, asyncio.Task] = _connections.setdefault(loop, {})
    opening = kept.get(key)
    if opening is not None and opening.done() and (opening.exception() or opening.result().gone):
        opening = None
    if opening is None:
        made = Connection(target)
        opening = asyncio.ensure_future(_opened(made))
        kept[key] = opening
    try:
        return await asyncio.shield(opening)
    except Failed:
        if kept.get(key) is opening:
            del kept[key]
        raise


async def _opened(made: Connection) -> Connection:
    try:
        await made.open()
    except BaseException:
        made.end(made.failure or Failed("location_failed"))
        raise
    return made


def ended(prefix: str) -> None:
    """Ends every connection of the location, whose secret or address has changed or gone."""
    for kept in _connections.values():
        for key in [key for key in kept if key.startswith(prefix)]:
            task = kept.pop(key)
            if task.done() and not task.exception():
                task.result().end(Failed("location_closed"))


class Sftp:
    """A location over SFTP; its paths from the folder it opens at."""

    def __init__(self, link: Connection):
        self.link = link

    def _real(self, path: str) -> str:
        return posixpath.join(self.link.start, path) if path else self.link.start

    async def listed(self, path: str) -> list[Entry]:
        folder = self._real(path)
        if _kind(await self.link.stat(folder)) != "folder":
            raise Failed("not_a_folder", 400)
        found = []
        for name, attrs in await self.link.entries(folder):
            if _kind(attrs) == "link":
                found.append(await self._followed(posixpath.join(folder, name), name))
            else:
                found.append(_entry(name, attrs))
        return found

    async def _followed(self, real: str, name: str) -> Entry:
        """A symbolic link as what it points at, a link to nowhere where that is gone."""
        try:
            target = await self.link.readlink(real)
        except Failed:
            if self.link.gone:
                raise
            target = None
        try:
            return _entry(name, await self.link.stat(real), target)
        except Failed:
            if self.link.gone:
                raise
            return Entry(name, "link", None, None, target)

    async def stat(self, path: str) -> Entry:
        return _entry(posixpath.basename(path), await self.link.stat(self._real(path)))

    async def described(self, path: str) -> Stat:
        real = self._real(path)
        name = posixpath.basename(real)
        attrs = await self.link.stat(real, follow=False)
        entry = await self._followed(real, name) if _kind(attrs) == "link" else _entry(name, attrs)
        owner = group = None
        if path:
            above = posixpath.dirname(real)
            for each, longname, _ in await self.link.lines(above):
                if each == name:
                    owner, group = _owners(longname)
                    break
        permissions = attrs.get("permissions")
        return Stat(
            entry,
            mode=None if permissions is None else permissions & 0o7777,
            uid=attrs.get("uid"),
            gid=attrs.get("gid"),
            owner=owner,
            group=group,
        )

    async def chmod(self, path: str, mode: int) -> None:
        await self.link.setstat(self._real(path), _attrs(mode))

    async def chown(self, path: str, uid: int, gid: int) -> None:
        await self.link.setstat(self._real(path), _owned(uid, gid))

    async def chunks(self, path: str, start: int, length: int) -> AsyncIterator[bytes]:
        """The bytes from `start` on, several reads ahead of what is sent on."""
        handle = await self.link.open_file(self._real(path), O_READ)
        offset, end = start, start + length
        ahead: list[tuple[int, int, asyncio.Task]] = []

        def more() -> None:
            nonlocal offset
            while len(ahead) < AHEAD and offset < end:
                size = min(CHUNK, end - offset)
                ahead.append(
                    (offset, size, asyncio.ensure_future(self.link.read(handle, offset, size)))
                )
                offset += size

        try:
            more()
            while ahead:
                at, size, part = ahead.pop(0)
                data = await part
                if data is None:
                    raise Failed("file_changed")
                if len(data) < size:
                    rest = asyncio.ensure_future(
                        self.link.read(handle, at + len(data), size - len(data))
                    )
                    ahead.insert(0, (at + len(data), size - len(data), rest))
                yield data
                more()
        finally:
            for _, _, part in ahead:
                part.cancel()
            if not self.link.gone:
                await self.link.close(handle)

    async def whole(self, path: str, most: int) -> bytes | None:
        handle = await self.link.open_file(self._real(path), O_READ)
        parts, size = [], 0
        try:
            while (part := await self.link.read(handle, size, CHUNK)) is not None:
                size += len(part)
                if size > most:
                    return None
                parts.append(part)
        finally:
            if not self.link.gone:
                await self.link.close(handle)
        return b"".join(parts)

    async def _written(self, handle: bytes, parts: AsyncIterator[bytes]) -> None:
        offset = 0
        try:
            async for part in parts:
                for at in range(0, len(part), CHUNK):
                    piece = part[at : at + CHUNK]
                    await self.link.write(handle, offset, piece)
                    offset += len(piece)
        finally:
            if not self.link.gone:
                await self.link.close(handle)

    async def write(self, path: str, data: bytes) -> None:
        """The text written over the file in place, which keeps who owns it and its rights: a
        server's file is often writable by a group in a folder that is not."""

        async def once() -> AsyncIterator[bytes]:
            yield data

        handle = await self.link.open_file(self._real(path), O_WRITE | O_TRUNC)
        await self._written(handle, once())

    async def put(self, path: str, parts: AsyncIterator[bytes]) -> None:
        """A new file; one by that name already there is refused."""
        real = self._real(path)
        try:
            await self.link.stat(real, follow=False)
        except Failed as missing:
            if missing.status != 404:
                raise
        else:
            raise Failed("file_exists")
        handle = await self.link.open_file(real, O_WRITE | O_CREAT | O_EXCL, 0o644)
        try:
            await self._written(handle, parts)
        except BaseException:
            if not self.link.gone:
                await self.link.request(REMOVE, _string(real))
            raise

    async def mkdir(self, path: str) -> None:
        real = self._real(path)
        try:
            await self.link.stat(real, follow=False)
        except Failed as missing:
            if missing.status != 404:
                raise
        else:
            raise Failed("file_exists")
        await self.link.request(MKDIR, _string(real), _attrs(0o755))

    async def rename(self, path: str, to: str) -> None:
        real, target = self._real(path), self._real(to)
        try:
            await self.link.stat(target, follow=False)
        except Failed as missing:
            if missing.status != 404:
                raise
        else:
            raise Failed("file_exists")
        await self.link.request(RENAME, _string(real), _string(target))

    async def remove(self, path: str) -> None:
        """The file, or the folder with all it holds; a link goes, never what it points at."""
        real = self._real(path)
        if _kind(await self.link.stat(real, follow=False)) != "folder":
            await self.link.request(REMOVE, _string(real))
            return
        for name, attrs in await self.link.entries(real):
            inner = posixpath.join(path, name)
            if _kind(attrs) == "folder":
                await self.remove(inner)
            else:
                await self.link.request(REMOVE, _string(self._real(inner)))
        await self.link.request(RMDIR, _string(real))

    async def close(self) -> None:
        """The connection stays for the next request, until it idles."""
