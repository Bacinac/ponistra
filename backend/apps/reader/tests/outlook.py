"""An Outlook message written as a compound file (MS-CFB version 3), for the tests."""

import itertools
import struct
from datetime import UTC, datetime

SECTOR = 512
MINI = 64
CUTOFF = 4096
FREE, END, FAT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD


def compound(streams: dict[str, bytes]) -> bytes:
    nodes = [{"name": "Root Entry", "type": 5, "kids": [], "data": b""}]
    index = {"": 0}
    for path, data in streams.items():
        parts = path.split("/")
        for depth in range(1, len(parts)):
            key = "/".join(parts[:depth])
            if key not in index:
                index[key] = len(nodes)
                nodes.append({"name": parts[depth - 1], "type": 1, "kids": [], "data": b""})
                nodes[index["/".join(parts[: depth - 1])]]["kids"].append(index[key])
        index[path] = len(nodes)
        nodes.append({"name": parts[-1], "type": 2, "kids": [], "data": data})
        nodes[index["/".join(parts[:-1])]]["kids"].append(index[path])

    fat: list[int] = []
    body = bytearray()

    def placed(data: bytes) -> int:
        count = -(-len(data) // SECTOR)
        if not count:
            return END
        start = len(fat)
        fat.extend([*range(start + 1, start + count), END])
        body.extend(data.ljust(count * SECTOR, b"\0"))
        return start

    mini = bytearray()
    minifat: list[int] = []

    def tucked(data: bytes) -> int:
        count = -(-len(data) // MINI)
        if not count:
            return END
        start = len(minifat)
        minifat.extend([*range(start + 1, start + count), END])
        mini.extend(data.ljust(count * MINI, b"\0"))
        return start

    starts = [
        END
        if node["type"] != 2
        else tucked(node["data"])
        if len(node["data"]) < CUTOFF
        else placed(node["data"])
        for node in nodes
    ]
    nodes[0]["data"] = bytes(mini)
    starts[0] = placed(bytes(mini))
    minifat.extend([FREE] * (-len(minifat) % (SECTOR // 4)))
    minifat_start = placed(struct.pack(f"<{len(minifat)}I", *minifat)) if minifat else END
    right = {kid: after for node in nodes for kid, after in itertools.pairwise(node["kids"])}
    entries = bytearray()
    for number, node in enumerate(nodes):
        name = node["name"].encode("utf-16-le") + b"\0\0"
        entries += struct.pack(
            "<64sHBBIII16sIQQIII",
            name,
            len(name),
            node["type"],
            1,
            FREE,
            right.get(number, FREE),
            node["kids"][0] if node["kids"] else FREE,
            bytes(16),
            0,
            0,
            0,
            starts[number],
            len(node["data"]),
            0,
        )
    while len(entries) % SECTOR:
        entries += struct.pack(
            "<64sHBBIII16sIQQIII", b"", 0, 0, 0, FREE, FREE, FREE, bytes(16), *[0] * 6
        )
    first = placed(bytes(entries))
    sectors = 1
    while len(fat) + sectors > sectors * SECTOR // 4:
        sectors += 1
    held = list(range(len(fat), len(fat) + sectors))
    fat.extend([FAT] * sectors)
    fat.extend([FREE] * (sectors * SECTOR // 4 - len(fat)))
    header = struct.pack(
        "<8s16sHHHHH6sIIIIIIIII",
        bytes.fromhex("D0CF11E0A1B11AE1"),
        bytes(16),
        0x3E,
        3,
        0xFFFE,
        9,
        6,
        bytes(6),
        0,
        sectors,
        first,
        0,
        CUTOFF,
        minifat_start,
        len(minifat) * 4 // SECTOR,
        END,
        0,
    ) + struct.pack("<109I", *held, *[FREE] * (109 - sectors))
    return header + bytes(body) + struct.pack(f"<{len(fat)}I", *fat)


def text(value: str) -> bytes:
    return value.encode("utf-16-le")


def fixed(*properties: tuple[int, int, bytes]) -> bytes:
    return b"".join(
        struct.pack("<HHI", kind, prop, 6) + value.ljust(8, b"\0")
        for kind, prop, value in properties
    )


def filetime(moment: datetime) -> bytes:
    since = moment - datetime(1601, 1, 1, tzinfo=UTC)
    return struct.pack("<Q", (since.days * 86_400 + since.seconds) * 10_000_000)


def message(sent: datetime) -> bytes:
    recipient = "__recip_version1.0_#00000000/"
    attachment = "__attach_version1.0_#00000000/"
    return compound(
        {
            "__substg1.0_0037001F": text("Ponuda za održavanje"),
            "__substg1.0_0C1A001F": text("Ana Kovač"),
            "__substg1.0_5D01001F": text("ana@example.com"),
            "__substg1.0_1000001F": text("Pozdrav iz Outlooka"),
            "__properties_version1.0": bytes(32)
            + fixed((0x0040, 0x0039, filetime(sent)), (0x0003, 0x3FDE, struct.pack("<i", 65001))),
            f"{recipient}__substg1.0_3001001F": text("Ivo"),
            f"{recipient}__substg1.0_39FE001F": text("ivo@example.com"),
            f"{recipient}__properties_version1.0": bytes(8)
            + fixed((0x0003, 0x0C15, struct.pack("<i", 1))),
            f"{attachment}__substg1.0_37010102": b"%PDF-1.4 ponuda",
            f"{attachment}__substg1.0_3707001F": text("ponuda.pdf"),
            f"{attachment}__substg1.0_370E001F": text("application/pdf"),
            f"{attachment}__properties_version1.0": bytes(8),
        }
    )
