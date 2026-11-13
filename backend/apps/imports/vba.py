"""The source of an Office file's macros, read from its VBA project as [MS-OVBA] lays it out:
shown to whoever imported the file, never run."""

import io
import re
import struct
from logging import getLogger

import olefile

log = getLogger(__name__)

LONGEST = 100_000
CHUNK = 4096
TERMINATOR, VERSION, CODE_PAGE = 0x0010, 0x0009, 0x0003
MODULE_NAME, MODULE_NAME_UNICODE = 0x0019, 0x0047
STREAM_NAME, STREAM_NAME_UNICODE = 0x001A, 0x0032
MODULE_OFFSET, MODULE_END = 0x0031, 0x002B
ATTRIBUTE = re.compile(r"^Attribute\s+[\w.]+\s*=.*(?:\n|$)", re.MULTILINE | re.IGNORECASE)


class Unreadable(Exception):
    pass


def decompressed(data: bytes) -> bytes:
    """A compressed container unpacked chunk by chunk: a chunk's tokens copy either a byte
    or a run of what the chunk has already given."""
    if not data or data[0] != 1:
        raise Unreadable("not a compressed container")
    found = bytearray()
    at = 1
    while at < len(data):
        if at + 2 > len(data):
            raise Unreadable("a cut chunk header")
        (header,) = struct.unpack_from("<H", data, at)
        if header >> 12 & 0b111 != 0b011:
            raise Unreadable("a chunk without its signature")
        end = min(at + (header & 0x0FFF) + 3, len(data))
        at += 2
        if not header & 0x8000:
            found += data[at : at + CHUNK]
            at += CHUNK
            continue
        start = len(found)
        while at < end:
            flags = data[at]
            at += 1
            for bit in range(8):
                if at >= end:
                    break
                if not flags >> bit & 1:
                    found.append(data[at])
                    at += 1
                    continue
                if at + 2 > end:
                    raise Unreadable("a cut copy token")
                (token,) = struct.unpack_from("<H", data, at)
                at += 2
                count = max((len(found) - start - 1).bit_length(), 4)
                offset = (token >> (16 - count)) + 1
                if offset > len(found) - start:
                    raise Unreadable("a copy from before its chunk")
                for _ in range((token & 0xFFFF >> count) + 3):
                    found.append(found[-offset])
    return bytes(found)


def _records(data: bytes):
    at = 0
    while at + 6 <= len(data):
        kind, size = struct.unpack_from("<HI", data, at)
        # PROJECTVERSION gives 4 as its size, yet two more bytes follow.
        size = 6 if kind == VERSION else size
        at += 6
        yield kind, data[at : at + size]
        at += size
        if kind == TERMINATOR:
            return
    raise Unreadable("a dir stream without its end")


def _modules(project: olefile.OleFileIO) -> list[dict]:
    path = next((each for each in project.listdir() if each[-2:] == ["VBA", "dir"]), None)
    if path is None:
        raise Unreadable("no dir stream")
    storage = path[:-1]
    page, modules, module = 1252, [], {}
    for kind, data in _records(decompressed(project.openstream(path).read())):
        if kind == CODE_PAGE:
            (page,) = struct.unpack("<H", data[:2])
        elif kind == MODULE_NAME:
            module = {"name": data.decode(f"cp{page}", "replace")}
        elif kind == MODULE_NAME_UNICODE:
            module["name"] = data.decode("utf-16-le", "replace")
        elif kind == STREAM_NAME:
            module["stream"] = data.decode(f"cp{page}", "replace")
        elif kind == STREAM_NAME_UNICODE:
            module["stream"] = data.decode("utf-16-le", "replace")
        elif kind == MODULE_OFFSET:
            (module["offset"],) = struct.unpack("<I", data[:4])
        elif kind == MODULE_END:
            modules.append(module)
    found = []
    for each in modules:
        stream = project.openstream([*storage, each["stream"]]).read()
        text = decompressed(stream[each["offset"] :]).decode(f"cp{page}", "replace")
        code = ATTRIBUTE.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).strip("\n")
        if code.strip():
            found.append({"name": each["name"], "code": code})
    return found


def source(data: bytes) -> list[dict]:
    """The project's modules that hold code, by name, without the attribute lines the VBA
    editor hides too; what goes past `LONGEST` characters together is cut."""
    try:
        with olefile.OleFileIO(io.BytesIO(data)) as project:
            modules = _modules(project)
    except (OSError, KeyError, LookupError, struct.error, Unreadable) as error:
        log.warning("The VBA project's source is unreadable: %s", error)
        return []
    left = LONGEST
    for module in modules:
        if len(module["code"]) > left:
            module["code"] = module["code"][:left] + "\n…"
        left = max(left - len(module["code"]), 0)
    return modules
