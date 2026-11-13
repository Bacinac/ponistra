"""A Word, Excel or PowerPoint file given back the macros of the file its document came from. Office
keeps a VBA project as a part beside the main one, with parts of its own (Word's vbaData.xml,
a signature), so they go over unchanged and the main part is typed macro-enabled. The original
is the user's file, so it is read in the reader (D51)."""

import io
import posixpath
import zipfile
from pathlib import Path

from lxml import etree

from apps.blobs import store
from apps.reader import client

from .package import CONTENT_TYPES, PACKAGE, TYPES, main_of, relationships, rels_of, type_of

VBA = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"
ENABLED = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": (
        "application/vnd.ms-word.document.macroEnabled.main+xml"
    ),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml": (
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
    ),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml": (
        "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml"
    ),
}
# The format a document saves its original's macros in, by the original's media type.
KINDS = {
    store.DOCM: "docm",
    store.DOTM: "docm",
    store.XLSM: "xlsm",
    store.XLTM: "xlsm",
    store.PPTM: "pptm",
    store.POTM: "pptm",
    store.PPSM: "pptm",
}


class Missing(Exception):
    """The original holds no VBA project."""


def _carried(archive: zipfile.ZipFile, project: str) -> list[str]:
    """The VBA project and every part it leads to, with their relationships."""
    found, waiting = [], [project]
    while waiting:
        part = waiting.pop()
        if part in found or part not in archive.namelist():
            continue
        found.append(part)
        if rels_of(part) in archive.namelist():
            found.append(rels_of(part))
        waiting += [name for _, _, name in relationships(archive, part)]
    return found


def with_macros(made: bytes, original: Path) -> bytes:
    with client.answered("macros", made, original) as answer:
        answer.finish()
        return answer.files[0].read_bytes()


def restored(made: Path, original: Path, out) -> None:
    """Sends the file made with the original's macros, in the reader."""
    with zipfile.ZipFile(original) as source:
        main = main_of(source)
        project = next((name for _, type, name in relationships(source, main) if type == VBA), None)
        if project is None or project not in source.namelist():
            raise Missing
        source_types = etree.fromstring(source.read(CONTENT_TYPES))
        carried = {
            part: (source.read(part), type_of(source_types, part))
            for part in _carried(source, project)
        }
    if any(type is None for _, type in carried.values()):
        raise Missing
    found = io.BytesIO()
    with (
        zipfile.ZipFile(made) as ours,
        zipfile.ZipFile(found, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        our_main = main_of(ours)
        types = etree.fromstring(ours.read(CONTENT_TYPES))
        for override in types.iterfind(f"{{{TYPES}}}Override"):
            if override.get("PartName", "").lstrip("/") == our_main:
                override.set("ContentType", ENABLED[override.get("ContentType")])
        for part, (_, type) in carried.items():
            if not part.endswith(".rels"):
                etree.SubElement(
                    types, f"{{{TYPES}}}Override", PartName=f"/{part}", ContentType=type
                )
        rels = etree.fromstring(ours.read(rels_of(our_main)))
        taken = {each.get("Id") for each in rels}
        etree.SubElement(
            rels,
            f"{{{PACKAGE}}}Relationship",
            Id=next(f"rIdVba{n}" for n in range(1, len(taken) + 2) if f"rIdVba{n}" not in taken),
            Type=VBA,
            Target=posixpath.relpath(project, posixpath.dirname(our_main)),
        )
        for name in ours.namelist():
            if name in carried:
                continue
            if name == CONTENT_TYPES:
                data = etree.tostring(types, xml_declaration=True, encoding="UTF-8")
            elif name == rels_of(our_main):
                data = etree.tostring(rels, xml_declaration=True, encoding="UTF-8")
            else:
                data = ours.read(name)
            target.writestr(name, data)
        for part, (data, _) in carried.items():
            target.writestr(part, data)
    out.data(found.getvalue())
