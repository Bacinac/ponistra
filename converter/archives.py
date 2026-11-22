"""An archive's entries listed, one of them unpacked or all its files packed as a tar, by
libarchive; a 7z with a password, which libarchive refuses, by 7-Zip. A compressed file that holds
no archive is one entry, named as the file without its compression's extension."""

import os
import re
import shutil
import subprocess
import tarfile
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import libarchive
from libarchive.exception import ArchiveError

# Entries a listing shows and a tar holds; the rest are counted.
MOST = 10_000
# What one entry, or all of them in a tar, may unpack to: past it, a bomb. The installation's
# largest file, as the backend keeps no larger.
UNPACKED = int(os.environ["PONISTRA_FILE_MAX_GB"]) * 1024**3
TIMEOUT = 120
# 7-Zip writing every file of an archive as large as UNPACKED.
TIMEOUT_ALL = 3600
COMPRESSED = {".gz", ".bz2", ".xz", ".zst", ".lz4", ".z", ".lzma"}
SEVEN = b"7z\xbc\xaf\x27\x1c"
DANGEROUS = "Dangerous link path was ignored"
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


def _formats(read, path: Path, name: str, password: str | None, *args):
    """`read` over the archive, or over the one compressed file libarchive finds no archive in."""
    try:
        return read(path, name, password, *args, raw=False)
    except Raw:
        pass
    except ArchiveError as error:
        if LOCKED.search(str(error)):
            raise Locked(str(error)) from None
        if "unrecognized archive format" not in str(error).lower():
            raise Unreadable(str(error)) from None
    try:
        return read(path, name, password, *args, raw=True)
    except ArchiveError as error:
        raise Unreadable(str(error)) from None


def listed(path: Path, name: str, password: str | None) -> dict:
    """The archive's entries in the order it holds them, each numbered by that order; `raw` when
    the file is one compressed file rather than an archive."""
    if password and _seven(path):
        return _seven_listed(path, password)
    return _formats(_listed, path, name, password)


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
    return {"entries": entries, "count": count, "raw": raw}


def unpacked(path: Path, name: str, number: int, password: str | None):
    """The entry's name, its size when the archive tells it, and its bytes as they unpack."""
    if password and _seven(path):
        return _seven_unpacked(path, number, password)
    return _formats(_unpacked, path, name, password, number)


def _unpacked(path: Path, name: str, password: str | None, number: int, raw: bool):
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


def packed(path: Path, name: str, password: str | None, into: Path) -> None:
    """Every file among the archive's first MOST entries written to `into` as an uncompressed tar
    of the pax format, each under its path in the archive and with its time; `into`'s folder holds
    each file while it unpacks."""
    if password and _seven(path):
        return _seven_packed(path, password, into)
    return _formats(_packed, path, name, password, into)


def _packed(path: Path, name: str, password: str | None, into: Path, raw: bool) -> None:
    spooled, told = into.with_name(f"{into.name}.entry"), 0
    with (
        _reader(path, password, raw) as archive,
        tarfile.open(into, "w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for at, entry in enumerate(archive):
            if not raw and archive.format_name.startswith(TEXTUAL):
                raise Raw
            if at >= MOST:
                break
            if not raw and not (entry.isreg and entry.pathname):
                continue
            with spooled.open("wb") as file:
                for block in entry.get_blocks():
                    told += len(block)
                    if told > UNPACKED:
                        raise Overflow(f"more than {UNPACKED} bytes")
                    file.write(block)
            _added(tar, spooled, _stem(name) if raw else entry.pathname, entry.mtime)
    spooled.unlink(missing_ok=True)


def _added(tar: tarfile.TarFile, path: Path, name: str, mtime: float | None) -> None:
    held = tarfile.TarInfo(name)
    held.size, held.mtime = path.stat().st_size, int(mtime or 0)
    with path.open("rb") as file:
        tar.addfile(held, file)


def _seven_packed(path: Path, password: str, into: Path) -> None:
    found = _seven_entries(path, password)[:MOST]
    files = [each for each in found if not _folder(each) and not _linked(each)]
    if sum(int(each.get("Size") or 0) for each in files) > UNPACKED:
        raise Overflow(f"more than {UNPACKED} bytes")
    out = into.with_name(f"{into.name}.out")
    process = _seven_run(["x", "-y", f"-o{out}"], [str(path)], password, stdout=subprocess.DEVNULL)
    try:
        _, failed = process.communicate(timeout=TIMEOUT_ALL)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, 9)
        process.communicate()
        raise Unreadable(f"unpacking overran {TIMEOUT_ALL} s") from None
    text = failed.decode(errors="replace")
    # 7-Zip fails the whole archive over a link pointing out of its folder, which it leaves out.
    errors = [line for line in text.splitlines() if line.startswith("ERROR")]
    if process.returncode != 0 and not (errors and all(DANGEROUS in line for line in errors)):
        raise (Locked if LOCKED.search(text) else Unreadable)(text.strip()[-300:])
    told = 0
    with tarfile.open(into, "w", format=tarfile.PAX_FORMAT) as tar:
        for each in files:
            unpacked = out / each["Path"]
            if unpacked.is_symlink() or not unpacked.is_file():
                continue
            if not unpacked.resolve().is_relative_to(out.resolve()):
                continue
            told += unpacked.stat().st_size
            if told > UNPACKED:
                raise Overflow(f"more than {UNPACKED} bytes")
            _added(tar, unpacked, each["Path"], unpacked.stat().st_mtime)
    shutil.rmtree(out, ignore_errors=True)


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


def _linked(entry: dict) -> bool:
    return " l" in entry.get("Attributes", "")


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
    return {"entries": entries, "count": len(found), "raw": False}


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
