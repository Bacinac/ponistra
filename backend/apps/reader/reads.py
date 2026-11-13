"""What the reader reads, by the kind a request names: each reading given the request's files,
its head and where to send its lines, and the processor time it may take; and the failures a
reading reports by name, raised in the backend as the exceptions it knows them by."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from django.utils.module_loading import import_string


@dataclass(frozen=True)
class Read:
    run: Callable[[list[Path], dict, object], object]
    seconds: int


def _read(path: Path, head: dict):
    from apps.imports import delimited, docx, pptx, xlsx

    target, locale = head["target"], head["locale"]
    if target == "csv":
        return delimited.read(path, locale)
    if target == "xlsx":
        return xlsx.read(path, locale)
    return (pptx if target == "pptx" else docx).read(path, locale, head.get("formats"))


def _imported(paths: list[Path], head: dict, out):
    imported = _read(paths[0], head)
    rest, imported.rest = imported.rest, None
    out.send({"imported": imported, "streams": rest is not None})
    return None if rest is None else rest(out)


def _import_pages(paths: list[Path], head: dict, out):
    from apps.search import extraction

    return extraction.paged(_read(paths[0], head).tabs)


def _pdf_text(paths: list[Path], head: dict, out):
    from apps.search import pdf

    return pdf.read(paths[0])


def _pdf_hits(paths: list[Path], head: dict, out):
    from apps.search import pdf

    return pdf.hits(paths[0], head["query"], head["most"])


def _preview(paths: list[Path], head: dict, out):
    from apps.blobs import previews

    return previews.picture(paths[0], head["pdf"])


def _avatar(paths: list[Path], head: dict, out):
    from apps.contacts import cards

    return cards.avatar(paths[0])


def _icon(paths: list[Path], head: dict, out):
    from apps.documents import links

    return links.icon(paths[0].read_bytes(), head["given"])


def _tint(paths: list[Path], head: dict, out):
    from apps.documents import links

    return links.painted(paths[0].read_bytes(), head["colour"])


def _edit(paths: list[Path], head: dict, out):
    from apps.blobs import edits

    out.data(edits.edited(paths[0], head["edits"], head["media_type"]))


def _pdf_assembly(paths: list[Path], head: dict, out):
    from apps.content import views

    return views.assembly(paths[0])


def _pdf_sizes(paths: list[Path], head: dict, out):
    from apps.content import views

    return views.sizes(paths[0])


def _svg_size(paths: list[Path], head: dict, out):
    from apps.exports import pictures

    return pictures.svg_size(paths[0])


def _upright(paths: list[Path], head: dict, out):
    from apps.exports import pictures

    return pictures.upright(paths[0], head["media_type"], out)


def _pdf_page(paths: list[Path], head: dict, out):
    from apps.exports import pictures

    return pictures.drawn_page(paths[0], head["number"], head["inches"], out)


def _annotate(paths: list[Path], head: dict, out):
    from apps.exports import annotated

    annotated.annotate(paths[0], **head, out=out)


def _embed(paths: list[Path], head: dict, out):
    from apps.exports import embedded

    printed, *sources = paths
    embedded.embedded(printed, dict(zip(head["files"], sources, strict=True)), out)


def _content_type(paths: list[Path], head: dict, out):
    from apps.blobs import store

    return store.typed(paths[0], head["part"])


def _macros(paths: list[Path], head: dict, out):
    from apps.exports import macros

    macros.restored(paths[0], paths[1], out)


def _compose(paths: list[Path], head: dict, out):
    from apps.imports import composed

    return composed.made(paths, head["taken"], head["titles"], out)


def _redact(paths: list[Path], head: dict, out):
    from apps.imports import redacted

    return redacted.blacked(paths[0], head["boxes"], out)


def _scan_corners(paths: list[Path], head: dict, out):
    from apps.imports import scanned

    return scanned.corners(paths[0])


def _scan(paths: list[Path], head: dict, out):
    from apps.imports import scanned

    return scanned.made(paths, head["corners"], out)


READS: dict[str, Read] = {
    "import": Read(_imported, 3600),
    "import_pages": Read(_import_pages, 600),
    "pdf_text": Read(_pdf_text, 300),
    "pdf_hits": Read(_pdf_hits, 120),
    "pdf_assembly": Read(_pdf_assembly, 60),
    "pdf_sizes": Read(_pdf_sizes, 60),
    "pdf_page": Read(_pdf_page, 120),
    "preview": Read(_preview, 60),
    "svg_size": Read(_svg_size, 30),
    "upright": Read(_upright, 120),
    "avatar": Read(_avatar, 60),
    "icon": Read(_icon, 30),
    "tint": Read(_tint, 30),
    "edit": Read(_edit, 120),
    "annotate": Read(_annotate, 300),
    "embed": Read(_embed, 600),
    "content_type": Read(_content_type, 10),
    "macros": Read(_macros, 120),
    "compose": Read(_compose, 600),
    "redact": Read(_redact, 600),
    "scan_corners": Read(_scan_corners, 30),
    "scan": Read(_scan, 600),
}

# The first that a failure is an instance of names it; the backend raises the class named.
FAILURES: list[tuple[str, str]] = [
    ("edits_unreadable", "apps.blobs.edits.Unreadable"),
    ("locked", "apps.exports.annotated.Locked"),
    ("annotated_unreadable", "apps.exports.annotated.Unreadable"),
    ("embedded_unreadable", "apps.exports.embedded.Unreadable"),
    ("no_macros", "apps.exports.macros.Missing"),
    ("compose_forbidden", "apps.imports.composed.Forbidden"),
    ("outside", "apps.imports.composed.Outside"),
    ("redact_forbidden", "apps.imports.redacted.Forbidden"),
    ("left", "apps.imports.redacted.Left"),
    ("unredactable", "apps.imports.redaction.content.Unredactable"),
    ("too_many_cells", "apps.imports.reading.TooManyCells"),
    ("too_many_formulas", "apps.imports.reading.TooManyFormulas"),
    ("too_large", "apps.imports.reading.TooLarge"),
    ("unreadable", "apps.imports.reading.Unreadable"),
]
# What the libraries raise over a file they cannot read, by the name the backend knows it.
NATIVE: list[tuple[str, str]] = [
    ("locked", "pikepdf.PasswordError"),
    ("unreadable", "pikepdf.PdfError"),
    ("unreadable", "pikepdf.OutlineStructureError"),
    ("unreadable", "pypdfium2.PdfiumError"),
    ("unreadable", "PIL.Image.DecompressionBombError"),
    ("unreadable", "lxml.etree.XMLSyntaxError"),
    ("unreadable", "OSError"),
]


def failure(error: Exception) -> str | None:
    """The name of a failure the backend knows, or None for one it does not, a fault of ours."""
    for name, path in (*FAILURES, *NATIVE):
        if isinstance(error, OSError if path == "OSError" else import_string(path)):
            return name
    return None


def raised(name: str, detail: str) -> Exception:
    for each, path in FAILURES:
        if each == name:
            return import_string(path)(detail)
    return RuntimeError(f"the reader failed as {name!r}: {detail}")
