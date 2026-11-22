"""An archive's entries listed, and one of them unpacked, by libarchive; a 7z with a password,
which libarchive refuses, by 7-Zip. A compressed file that holds no archive is one entry, named
as the file without its compression's extension."""

import os
import re
import subprocess
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import libarchive
from libarchive.exception import ArchiveError

# Entries a listing shows; the rest are counted.
MOST = 10_000
# What one entry may unpack to: past it, a bomb.
UNPACKED = 1024 * 1024 * 1024
TIMEOUT = 120
COMPRESSED = {".gz", ".bz2", ".xz", ".zst", ".lz4", ".z", ".lzma"}
SEVEN = b"7z\xbc\xaf\x27\x1c"
LOCKED = re.compile(r"passphrase|encrypt|password", re.IGNORECASE)
# Formats libarchive finds in plain text, which a compressed text file is not.
TEXTUAL = (b"mtree",)


class Locked(Exception):
    """The archive asks for a password: none was given, or the one given is wrong."""


class Unreadable(Exception):
    pass


class Overflow(Exception):
    """The entry unpacks to more than UNPACKED."""


class Raw(Exception):
    """What libarchive took for an archive is one compressed file."""


def _seven(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(6) == SEVEN


def _stem(name: str) -> str:
    named = PurePosixPath(name)
    return named.stem if named.suffix.lower() in COMPRESSED else f"{named.name}.out"


def _moment(entry, local: bool) -> str | None:
    """When the entry changed; a zip's time is the wall clock it was packed on, of no zone, which
    libarchive reads as this service's, UTC."""
    if not entry.mtime:
        return None
    moment = datetime.fromtimestamp(entry.mtime, UTC)
    return (moment.replace(tzinfo=None) if local else moment).isoformat()


def _reader(path: Path, password: str | None, raw: bool):
    if raw:
        return libarchive.file_reader(str(path), "raw", passphrase=password or None)
    return libarchive.file_reader(str(path), passphrase=password or None)


def listed(path: Path, name: str, password: str | None) -> dict:
    """The archive's entries in the order it holds them, each numbered by that order."""
    if password and _seven(path):
        return _seven_listed(path, password)
    try:
        return _listed(path, name, password, raw=False)
    except Raw:
        pass
    except ArchiveError as error:
        if LOCKED.search(str(error)):
            raise Locked(str(error)) from None
        if "unrecognized archive format" not in str(error).lower():
            raise Unreadable(str(error)) from None
    try:
        return _listed(path, name, password, raw=True)
    except ArchiveError as error:
        raise Unreadable(str(error)) from None


def _listed(path: Path, name: str, password: str | None, raw: bool) -> dict:
    entries, count = [], 0
    with _reader(path, password, raw) as archive:
        for entry in archive:
            if not raw and archive.format_name.startswith(TEXTUAL):
                raise Raw
            if count < MOST:
                entries.append(
                    {
                        "n": count,
                        "path": _stem(name) if raw else entry.pathname,
                        "size": None if raw or entry.isdir else entry.size,
                        "modified": _moment(entry, archive.format_name.startswith(b"ZIP")),
                        "folder": entry.isdir,
                    }
                )
            count += 1
    return {"entries": entries, "count": count}


def unpacked(path: Path, name: str, number: int, password: str | None):
    """The entry's name, its size when the archive tells it, and its bytes as they unpack."""
    if password and _seven(path):
        return _seven_unpacked(path, number, password)
    try:
        return _unpacked(path, name, number, password, raw=False)
    except Raw:
        pass
    except ArchiveError as error:
        if LOCKED.search(str(error)):
            raise Locked(str(error)) from None
        if "unrecognized archive format" not in str(error).lower():
            raise Unreadable(str(error)) from None
    return _unpacked(path, name, number, password, raw=True)


def _unpacked(path: Path, name: str, number: int, password: str | None, raw: bool):
    # The reader stays open while the bytes are sent, and closes with the last of them.
    held = ExitStack()
    try:
        archive = held.enter_context(_reader(path, password, raw))
        for at, entry in enumerate(archive):
            if not raw and archive.format_name.startswith(TEXTUAL):
                raise Raw
            if at < number:
                continue
            if at > number or entry.isdir:
                break
            blocks = entry.get_blocks()
            # The first block is read here, where a wrong password still raises.
            first = next(blocks, b"")
            size = None if raw else entry.size
            if size is not None and size > UNPACKED:
                raise Overflow(f"{size} bytes")
            named = _stem(name) if raw else PurePosixPath(entry.pathname).name

            return named, size, _sent(held, first, blocks)
    except BaseException:
        held.close()
        raise
    held.close()
    return None


def _sent(held: ExitStack, first: bytes, blocks):
    with held:
        told = len(first)
        if first:
            yield first
        for block in blocks:
            told += len(block)
            if told > UNPACKED:
                raise Overflow(f"more than {UNPACKED} bytes")
            yield block


def _seven_run(switches: list[str], files: list[str], password: str, **kwargs):
    return subprocess.Popen(
        ["7z", *switches, f"-p{password}", "-bsp0", "--", *files],
        stdin=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
        **kwargs,
    )


def _seven_entries(path: Path, password: str) -> list[dict]:
    process = _seven_run(["l", "-slt", "-ba"], [str(path)], password, stdout=subprocess.PIPE)
    try:
        said, failed = process.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, 9)
        process.communicate()
        raise Unreadable(f"listing overran {TIMEOUT} s") from None
    if process.returncode != 0:
        text = failed.decode(errors="replace")
        raise (Locked if LOCKED.search(text) else Unreadable)(text.strip()[-300:])
    entries, current = [], {}
    for line in [*said.decode("utf-8", "replace").splitlines(), ""]:
        if not line.strip():
            if "Path" in current:
                entries.append(current)
            current = {}
            continue
        key, _, value = line.partition(" = ")
        current[key.strip()] = value
    return entries


def _folder(entry: dict) -> bool:
    return entry.get("Folder") == "+" or entry.get("Attributes", "").startswith("D")


def _seven_listed(path: Path, password: str) -> dict:
    found = _seven_entries(path, password)
    entries = []
    for at, each in enumerate(found[:MOST]):
        folder = _folder(each)
        modified = each.get("Modified") or None
        entries.append(
            {
                "n": at,
                "path": each["Path"],
                "size": None if folder else int(each.get("Size") or 0),
                "modified": f"{modified.split('.')[0].replace(' ', 'T')}+00:00"
                if modified
                else None,
                "folder": folder,
            }
        )
    return {"entries": entries, "count": len(found)}


def _seven_unpacked(path: Path, number: int, password: str):
    found = _seven_entries(path, password)
    if not 0 <= number < len(found) or _folder(found[number]):
        return None
    entry = found[number]
    size = int(entry.get("Size") or 0)
    if size > UNPACKED:
        raise Overflow(f"{size} bytes")
    # -spd: the name is matched as it is, never as a wildcard.
    process = _seven_run(
        ["e", "-so", "-spd"], [str(path), entry["Path"]], password, stdout=subprocess.PIPE
    )

    def chunks():
        told = 0
        try:
            while block := process.stdout.read(1 << 20):
                told += len(block)
                if told > UNPACKED:
                    raise Overflow(f"more than {UNPACKED} bytes")
                yield block
            if process.wait(timeout=TIMEOUT) != 0:
                raise Unreadable(process.stderr.read().decode(errors="replace")[-300:])
        finally:
            if process.poll() is None:
                os.killpg(process.pid, 9)
            process.wait()

    return PurePosixPath(entry["Path"]).name, size, chunks()
