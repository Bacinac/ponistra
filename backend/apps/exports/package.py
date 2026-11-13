"""The parts of an Office file (OPC) as its zip holds them: the relationships of a part, the
main part and the content type of each part."""

import posixpath
import zipfile

from lxml import etree

TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCUMENT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
CONTENT_TYPES = "[Content_Types].xml"


def rels_of(part: str) -> str:
    folder, name = posixpath.split(part)
    return posixpath.join(folder, "_rels", f"{name}.rels")


def relationships(archive: zipfile.ZipFile, part: str) -> list[tuple[str, str, str]]:
    """The part's internal relationships, as their ids, types and the names of the parts
    they lead to."""
    rels = rels_of(part)
    if rels not in archive.namelist():
        return []
    folder = posixpath.dirname(part)
    found = []
    for each in etree.fromstring(archive.read(rels)).iterfind(f"{{{PACKAGE}}}Relationship"):
        target = each.get("Target") or ""
        if each.get("TargetMode") == "External" or not target:
            continue
        name = target[1:] if target.startswith("/") else posixpath.join(folder, target)
        found.append((each.get("Id") or "", each.get("Type") or "", posixpath.normpath(name)))
    return found


def main_of(archive: zipfile.ZipFile) -> str:
    return next(name for _, type, name in relationships(archive, "") if type == DOCUMENT)


def type_of(types, part: str) -> str | None:
    for override in types.iterfind(f"{{{TYPES}}}Override"):
        if override.get("PartName", "").lstrip("/") == part:
            return override.get("ContentType")
    extension = posixpath.splitext(part)[1][1:].lower()
    for default in types.iterfind(f"{{{TYPES}}}Default"):
        if default.get("Extension", "").lower() == extension:
            return default.get("ContentType")
    return None
