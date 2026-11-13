import io
import re
import struct
import zipfile

from apps.blobs import store

SECTOR = 512
FREE, END, FAT_SECTOR, NONE = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF
TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
MACRO_ENABLED = {
    "word/document.xml": "application/vnd.ms-word.document.macroEnabled.main+xml",
    "xl/workbook.xml": "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
    "ppt/presentation.xml": "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml",
}
VBA = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"
FILLER = b"\0" * 4096
MACRO = 'Attribute VB_Name = "Module1"\r\nSub Zbroji()\r\n    Range("A1") = "Šećer"\r\nEnd Sub\r\n'


def _entry(name: str, kind: int, child: int, right: int, start: int, size: int) -> bytes:
    encoded = (name + "\0").encode("utf-16-le") if name else b""
    return struct.pack(
        "<64sHBBIII16sIQQIQ",
        encoded,
        len(encoded),
        kind,
        1,
        NONE,
        right,
        child,
        b"",
        0,
        0,
        0,
        start,
        size,
    )


def ole(streams: dict[str, bytes]) -> bytes:
    """A compound file holding these streams, `VBA/dir` being one in a storage: the FAT in
    sector 0, the directory after it, then each stream in sectors of its own, none in the
    mini stream, which is why each must be at least 4096 bytes long."""
    names = ["Root Entry"]
    kinds, children, data = {0: 5}, {0: []}, {}
    for path, content in streams.items():
        assert len(content) >= 4096
        parent = 0
        parts = path.split("/")
        for depth in range(len(parts)):
            key = "/".join(parts[: depth + 1])
            if key not in names:
                names.append(key)
                index = len(names) - 1
                children[parent].append(index)
                kinds[index] = 2 if depth == len(parts) - 1 else 1
                children.setdefault(index, [])
            parent = names.index(key)
        data[parent] = content
    entries = -(-len(names) // 4) * 4
    first = 1 + entries // 4
    fat = [FAT_SECTOR, *range(2, first), END]
    starts = {}
    for index, content in data.items():
        starts[index] = len(fat)
        count = -(-len(content) // SECTOR)
        fat += [*range(len(fat) + 1, len(fat) + count), END]
    assert len(fat) <= SECTOR // 4
    fat += [FREE] * (SECTOR // 4 - len(fat))
    header = struct.pack(
        "<8s16sHHHHH6sIIIIIIIII",
        store.OLE,
        b"",
        0x3E,
        3,
        0xFFFE,
        9,
        6,
        b"",
        0,
        1,
        1,
        0,
        4096,
        END,
        0,
        END,
        0,
    )
    header += struct.pack("<109I", 0, *[FREE] * 108)
    siblings = {kids[i]: kids[i + 1] for kids in children.values() for i in range(len(kids) - 1)}
    directory = b"".join(
        _entry(
            name.rsplit("/", 1)[-1],
            kinds[index],
            children[index][0] if children[index] else NONE,
            siblings.get(index, NONE),
            starts.get(index, END if index == 0 else 0),
            len(data.get(index, b"")),
        )
        for index, name in enumerate(names)
    ) + _entry("", 0, NONE, NONE, 0, 0) * (entries - len(names))
    body = b"".join(content + b"\0" * (-len(content) % SECTOR) for content in data.values())
    return header + struct.pack(f"<{len(fat)}I", *fat) + directory + body


def compressed(data: bytes) -> bytes:
    """A compressed container as [MS-OVBA] allows it to be written: whole chunks stored as
    they are, the last one in literal tokens alone."""
    found = bytearray(b"\1")
    for at in range(0, len(data), 4096):
        chunk = data[at : at + 4096]
        if len(chunk) == 4096:
            found += struct.pack("<H", 0x3FFF) + chunk
            continue
        tokens = b"".join(b"\0" + chunk[i : i + 8] for i in range(0, len(chunk), 8))
        assert len(tokens) <= 4096
        found += struct.pack("<H", 0xB000 | len(tokens) - 1) + tokens
    return bytes(found)


def _record(kind: int, data: bytes) -> bytes:
    return struct.pack("<HI", kind, len(data)) + data


def vba_project(modules: dict[str, str]) -> bytes:
    """A VBA project of these modules in code page 1250, each module stream after a
    performance cache, as Office writes them; the dir stream is padded to a whole chunk."""
    records = _record(0x0003, struct.pack("<H", 1250))
    records += struct.pack("<HIIH", 0x0009, 4, 0x5E, 3)
    streams = {}
    for name, code in modules.items():
        records += _record(0x0019, name.encode("cp1250"))
        records += _record(0x001A, name.encode("cp1250"))
        records += _record(0x0032, name.encode("utf-16-le"))
        records += _record(0x0031, struct.pack("<I", len(FILLER)))
        records += _record(0x002B, b"")
        streams[f"VBA/{name}"] = FILLER + compressed(code.encode("cp1250"))
    records += _record(0x0010, b"")
    dir_stream = compressed(records + b"\0" * (4096 - len(records)))
    return ole({"PROJECT": FILLER, "VBA/dir": dir_stream, **streams})


def odf(mimetype: str) -> bytes:
    found = io.BytesIO()
    with zipfile.ZipFile(found, "w") as archive:
        archive.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_STORED)
        archive.writestr("content.xml", "<office:document-content/>")
    return found.getvalue()


def ooxml(part: str, content_type: str | None = None) -> bytes:
    found = io.BytesIO()
    typed = f'<Override PartName="/{part}" ContentType="{content_type}"/>' if content_type else ""
    with zipfile.ZipFile(found, "w") as archive:
        archive.writestr("[Content_Types].xml", f'<Types xmlns="{TYPES}">{typed}</Types>')
        archive.writestr(part, "<root/>")
    return found.getvalue()


def with_macros(data: bytes) -> bytes:
    """A Word, Excel or PowerPoint file made macro-enabled as Office saves one: its main part
    typed so, with a VBA project beside it."""
    found = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(found, "w") as target:
        main = next(part for part in MACRO_ENABLED if part in source.namelist())
        folder, name = main.split("/")
        for each in source.namelist():
            content = source.read(each)
            if each == "[Content_Types].xml":
                content = re.sub(
                    rf'(PartName="/{main}" ContentType=")[^"]+'.encode(),
                    rf"\g<1>{MACRO_ENABLED[main]}".encode(),
                    content,
                ).replace(
                    b"</Types>",
                    f'<Override PartName="/{folder}/vbaProject.bin" '
                    'ContentType="application/vnd.ms-office.vbaProject"/></Types>'.encode(),
                )
            if each == f"{folder}/_rels/{name}.rels":
                content = content.replace(
                    b"</Relationships>",
                    f'<Relationship Id="rIdVba" Type="{VBA}" Target="vbaProject.bin"/>'
                    "</Relationships>".encode(),
                )
            target.writestr(each, content)
        target.writestr(
            f"{folder}/vbaProject.bin", vba_project({"Module1": MACRO, "ThisWorkbook": ""})
        )
    return found.getvalue()
