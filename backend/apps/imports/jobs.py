"""A file made into a document or into a document's tabs, a document copied, and pages of PDF
files composed or redacted into a new file, in the queue of jobs: a large one takes longer than
a request is given."""

import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import PurePosixPath

from apps.access.models import Role
from apps.blobs import store
from apps.blobs.models import Blob
from apps.blobs.views import describe as describe_blob
from apps.core.api import Refused, optional_id
from apps.documents.models import Node
from apps.documents.views import (
    beside,
    dated,
    describe,
    describe_tab,
    folder,
    kept_in,
    live,
    live_document,
    live_pdf,
    modified_of,
    title_of,
)
from apps.exports import annotated
from apps.jobs.kinds import Kind, answered, answered_before

from . import bookmarks, composed, convert, create, ponx, reading, redacted, scanned
from .formats import EXTENSIONS
from .redaction.content import Unredactable
from .views import photo

log = logging.getLogger(__name__)

MOST_PAGES = 10_000
MOST_FILES = 500
MOST_SCANNED = 100


def _source(data: dict, also: frozenset[str] = frozenset()) -> Blob:
    """The uploaded file the import reads: an Office file, a PONISTRA file, or a kind only a new
    import makes something of."""
    sha256 = data.get("blob")
    source = Blob.objects.filter(pk=sha256).first() if isinstance(sha256, str) else None
    if source is None:
        raise Refused(400, "unknown_file")
    if source.media_type not in EXTENSIONS and source.media_type not in {store.PONX} | also:
        raise Refused(415, "not_importable")
    return source


@contextmanager
def _reading(source: Blob):
    try:
        yield
    except reading.TooManyCells:
        raise Refused(413, "too_many_cells") from None
    except reading.TooManyFormulas:
        raise Refused(413, "too_many_formulas") from None
    except reading.TooLarge:
        raise Refused(413, "too_large") from None
    except ponx.Newer:
        raise Refused(422, "newer_file") from None
    except reading.Unreadable:
        log.warning("File %s could not be read", source.sha256, exc_info=True)
        raise Refused(422, "unreadable") from None
    except convert.Unavailable:
        log.error("The converter did not answer for %s", source.sha256, exc_info=True)
        raise Refused(503, "converter_unavailable") from None


def _new(user, data: dict) -> tuple[Blob, Node | None, str, datetime | None]:
    source = _source(data, also=frozenset({store.BOOKMARKS}))
    parent, _ = folder(user, optional_id(data.get("parent")), Role.EDIT)
    return source, parent, title_of(data), modified_of(data)


def _new_asked(request, data: dict) -> dict:
    source, parent, title, modified = _new(request.user, data)
    return {
        "blob": source.sha256,
        "parent": parent and str(parent.pk),
        "title": title,
        "modified": modified and modified.isoformat(),
    }


def _new_done(user, parameters: dict) -> dict:
    """A new document from an uploaded text document, spreadsheet, presentation or PONISTRA
    file, or a folder of links from a browser's bookmarks, last changed when the file was."""
    source, parent, title, modified = _new(user, parameters)
    with _reading(source):
        if source.media_type == store.PONX:
            made = ponx.document(source, parent, title, user)
        elif source.media_type == store.BOOKMARKS:
            made = bookmarks.folder(source, parent, title, user)
        else:
            if (cut_off := answered_before()) is not None:
                Node.objects.filter(pk=cut_off["id"]).delete()
            made = create.document(
                source, parent, title, user, lambda node: answered(describe(node))
            )
        return describe(dated(made, modified))


def _into(user, data: dict) -> tuple[Node, Blob, str]:
    document = live_document(user, optional_id(data.get("document")), Role.EDIT)
    return document, _source(data), title_of(data)


def _into_asked(request, data: dict) -> dict:
    document, source, title = _into(request.user, data)
    return {"document": str(document.pk), "blob": source.sha256, "title": title}


def _into_done(user, parameters: dict) -> dict:
    """The file's tabs after the document's own, and what the import could not carry."""
    document, source, title = _into(user, parameters)
    joined = ponx.into if source.media_type == store.PONX else create.into
    with _reading(source):
        tab, report = joined(document, source, title, user)
    return {"tab": describe_tab(tab), "report": report}


def _reimported(user, data: dict) -> Node:
    document = live_document(user, optional_id(data.get("document")), Role.EDIT)
    if document.source is None:
        raise Refused(409, "not_imported")
    return document


def _reimport_asked(request, data: dict) -> dict:
    return {"document": str(_reimported(request.user, data).pk)}


def _reimport_done(user, parameters: dict) -> dict:
    """The document read from its file once more."""
    document = _reimported(user, parameters)
    with _reading(document.source):
        return describe(create.reimport(document, user))


def _copied(user, data: dict) -> tuple[Node, str]:
    return live_document(user, optional_id(data.get("document"))), title_of(data)


def _copy_asked(request, data: dict) -> dict:
    document, title = _copied(request.user, data)
    return {"document": str(document.pk), "title": title}


def _copy_done(user, parameters: dict) -> dict:
    """The document made again beside it, or among the user's own documents where they may not
    add to its folder."""
    document, title = _copied(user, parameters)
    return describe(
        ponx.copy(document, kept_in(user, [document], beside(user, document)), title, user)
    )


def _taken(user, entries: object) -> list[composed.Taken]:
    if not isinstance(entries, list) or not 0 < len(entries) <= MOST_PAGES:
        raise Refused(400, "invalid_pages")
    files: dict = {}
    taken = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.keys() <= {"file", "page", "turn"}:
            raise Refused(400, "invalid_pages")
        pk, page, turn = optional_id(entry.get("file")), entry.get("page"), entry.get("turn", 0)
        whole = page is None or (type(page) is int and page > 0)
        if pk is None or not whole or type(turn) is not int or not 0 <= turn < 4:
            raise Refused(400, "invalid_pages")
        if pk not in files:
            files[pk], _ = live_pdf(user, pk)
        taken.append(composed.Taken(files[pk], page, turn))
    return taken


def _composing(user, data: dict) -> tuple[str, Node, list[composed.Taken]]:
    title = title_of(data)
    near = optional_id(data.get("beside"))
    if near is None:
        raise Refused(400, "invalid_id")
    return title, live(user, near)[0], _taken(user, data.get("pages"))


def _compose_asked(request, data: dict) -> dict:
    title, near, taken = _composing(request.user, data)
    pages = [{"file": str(each.file.pk), "page": each.page, "turn": each.turn} for each in taken]
    return {"title": title, "beside": str(near.pk), "pages": pages}


def _compose_done(user, parameters: dict) -> dict:
    """A new PDF file from pages of files the user may read, turned and in the order given,
    beside the file named, or among the user's own documents where they may not add to its
    folder."""
    title, near, taken = _composing(user, parameters)
    try:
        place = kept_in(user, {each.file for each in taken}, beside(user, near))
        node = composed.compose(taken, place, title, user)
    except annotated.Locked:
        raise Refused(409, "locked") from None
    except composed.Forbidden:
        raise Refused(409, "assembly_forbidden") from None
    except composed.Outside:
        raise Refused(400, "invalid_pages") from None
    except store.TooLarge, reading.TooLarge:
        raise Refused(413, "too_large") from None
    except annotated.Unreadable as error:
        log.error("The notes of a file composed from cannot be read: %s", error)
        raise Refused(422, "unreadable_notes") from None
    except reading.Unreadable:
        log.warning(
            "Pages could not be composed from %s", [t.file.pk for t in taken], exc_info=True
        )
        raise Refused(422, "unreadable") from None
    return describe(node)


def _redacting(user, data: dict) -> tuple[Node, str]:
    file, _ = live_pdf(user, optional_id(data.get("file")), Role.EDIT)
    return file, title_of(data)


def _redact_asked(request, data: dict) -> dict:
    file, title = _redacting(request.user, data)
    return {"file": str(file.pk), "title": title}


def _redact_done(user, parameters: dict) -> dict:
    """A copy of the file without what its redaction marks cover, beside it, or among the user's
    own documents where they may not add to its folder."""
    file, title = _redacting(user, parameters)
    try:
        node = redacted.redact(file, kept_in(user, [file], beside(user, file)), title, user)
    except redacted.Unmarked:
        raise Refused(400, "nothing_marked") from None
    except annotated.Locked:
        raise Refused(409, "locked") from None
    except redacted.Forbidden:
        raise Refused(409, "modify_forbidden") from None
    except store.TooLarge, reading.TooLarge:
        raise Refused(413, "too_large") from None
    except annotated.Unreadable as error:
        log.error("The redactions of file %s cannot be read: %s", file.pk, error)
        raise Refused(422, "unreadable_notes") from None
    except Unredactable as error:
        log.warning("File %s cannot be redacted: %s", file.pk, error)
        raise Refused(422, "unredactable") from None
    except redacted.Left as error:
        log.error("A redacted copy of %s still holds text: %s", file.pk, error)
        raise Refused(422, "not_removed") from None
    except reading.Unreadable:
        log.warning("File %s could not be redacted", file.pk, exc_info=True)
        raise Refused(422, "unreadable") from None
    return describe(node)


def _linking(user, data: dict) -> tuple[Node, list[tuple[Blob, str]]]:
    parent, _ = folder(user, optional_id(data.get("parent")), Role.EDIT)
    if parent is None:
        raise Refused(400, "invalid_id")
    files = data.get("files")
    if not isinstance(files, list) or not 0 < len(files) <= MOST_FILES:
        raise Refused(400, "invalid_files")
    for each in files:
        if not isinstance(each, dict) or not all(
            isinstance(each.get(key), str) for key in ("blob", "name")
        ):
            raise Refused(400, "invalid_files")
    blobs = Blob.objects.in_bulk([each["blob"] for each in files])
    if len(blobs) < len({each["blob"] for each in files}):
        raise Refused(400, "unknown_file")
    return parent, [(blobs[each["blob"]], PurePosixPath(each["name"]).name) for each in files]


def _links_asked(request, data: dict) -> dict:
    parent, files = _linking(request.user, data)
    return {
        "parent": str(parent.pk),
        "files": [{"blob": blob.sha256, "name": name} for blob, name in files],
    }


def _links_done(user, parameters: dict) -> dict:
    """The groups and links of a browser's bookmarks and of a Homepage dashboard's services and
    bookmarks in the folder, beside what it holds, with the icons among the files given."""
    parent, files = _linking(user, parameters)
    trees, icons = [], {}
    for blob, name in files:
        with _reading(blob):
            if blob.media_type == store.BOOKMARKS:
                trees.append(bookmarks.bookmarks(bookmarks.text_of(blob)))
            elif PurePosixPath(name).suffix.lower() in (".yaml", ".yml"):
                trees.append(bookmarks.homepage(bookmarks.text_of(blob)))
            elif blob.media_type in store.IMAGES:
                icons[name] = blob
    if not trees:
        raise Refused(415, "not_importable")
    made = bookmarks.kept(bookmarks.planned(trees, parent, icons), user)
    return {"folder": describe(parent), "links": made}


def _scanned_pages(entries: object) -> list[scanned.Page]:
    if not isinstance(entries, list) or not 0 < len(entries) <= MOST_SCANNED:
        raise Refused(400, "invalid_pages")
    pages = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.keys() != {"blob", "corners"}:
            raise Refused(400, "invalid_pages")
        quad = scanned.quad_of(entry["corners"])
        if quad is None:
            raise Refused(400, "invalid_corners")
        pages.append(scanned.Page(photo(entry["blob"]), quad))
    return pages


def _scanning(user, data: dict) -> tuple[list[scanned.Page], Node | None, str, bool]:
    attached = data.get("attached", False)
    if type(attached) is not bool:
        raise Refused(400, "invalid_attached")
    parent = None if attached else folder(user, optional_id(data.get("parent")), Role.EDIT)[0]
    return _scanned_pages(data.get("pages")), parent, title_of(data), attached


def _scan_asked(request, data: dict) -> dict:
    pages, parent, title, attached = _scanning(request.user, data)
    return {
        "pages": [{"blob": page.blob.sha256, "corners": page.corners} for page in pages],
        "parent": parent and str(parent.pk),
        "title": title,
        "attached": attached,
    }


def _scan_done(user, parameters: dict) -> dict:
    """A PDF file of the pages photographed, straightened and with their text read, in the
    folder given, or as a file to attach to a mail, named by its title."""
    pages, parent, title, attached = _scanning(user, parameters)
    try:
        if attached:
            return {**describe_blob(scanned.scanned(pages)), "name": f"{title}.pdf"}
        return describe(scanned.scan(pages, parent, title, user))
    except store.TooLarge, reading.TooLarge:
        raise Refused(413, "too_large") from None
    except reading.Unreadable:
        log.warning("Pages could not be scanned", exc_info=True)
        raise Refused(422, "unreadable") from None


KINDS = {
    "import": Kind(_new_asked, _new_done, saves=False),
    "into": Kind(_into_asked, _into_done, saves=False),
    "reimport": Kind(_reimport_asked, _reimport_done, saves=False),
    "copy": Kind(_copy_asked, _copy_done, saves=False),
    "compose": Kind(_compose_asked, _compose_done, saves=False),
    "redact": Kind(_redact_asked, _redact_done, saves=False),
    "scan": Kind(_scan_asked, _scan_done, saves=False),
    "links": Kind(_links_asked, _links_done, saves=False),
}
