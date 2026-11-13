"""A document saved as a Word, Excel or PowerPoint file, with the macros of the file it came from,
as PONISTRA's own or as PDF, in the queue of jobs: a large one takes longer than a request is
given."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

from apps.access import log as access_log
from apps.blobs import store
from apps.content import calculation, grids
from apps.core.api import Refused, optional_id
from apps.documents import printing
from apps.documents.models import Node
from apps.documents.views import downloadable, live
from apps.jobs.kinds import Kind, Saved
from apps.users import sessions

from . import delimited, docx, embedded, macros, pictures, ponx, pptx, xlsx

log = logging.getLogger(__name__)


@contextmanager
def _signed_in(user) -> Iterator[str]:
    """A session of the user's own for the printer, which lays out what they may read."""
    session = sessions.opened(user, printing.TIMEOUT)
    try:
        yield session
    finally:
        sessions.closed(session)


def _word(document: Node, parameters: dict, user) -> bytes:
    return docx.word_file(document, parameters["site"])


def _excel(document: Node, parameters: dict, user) -> IO[bytes]:
    return xlsx.workbook(document)


def _delimited(document: Node, parameters: dict, user) -> IO[bytes]:
    return delimited.table(document)


def _slides(document: Node, parameters: dict, user) -> bytes:
    with _signed_in(user) as session:
        measured = printing.measured(document.pk, session)
    return pptx.presentation(document, parameters["site"], measured)


def _ponistra(document: Node, parameters: dict, user) -> IO[bytes]:
    return ponx.packed(document, versions=parameters["versions"])


def _pdf(document: Node, parameters: dict, user) -> bytes:
    with _signed_in(user) as session:
        printed = printing.printed(document.pk, session)
    return embedded.placed(document, printed)


# What holds a table's cells in one tree in memory, so stops at the ceiling on them.
UNWIELDY = {"docx", "docm", "pptx", "pptm"}
MADE = {
    "docx": _word,
    "docm": _word,
    "xlsx": _excel,
    "xlsm": _excel,
    "csv": _delimited,
    "pptx": _slides,
    "pptm": _slides,
    "ponx": _ponistra,
    "pdf": _pdf,
}


def _document(user, pk, format: str) -> Node:
    document, reach = live(user, pk)
    if document.kind != Node.Kind.DOCUMENT:
        raise Refused(400, "not_a_document")
    downloadable(reach)
    source = document.source
    if format in macros.KINDS.values() and (
        source is None or macros.KINDS.get(source.media_type) != format
    ):
        raise Refused(404, "no_macros")
    return document


def _asked(format: str):
    def asked(request, data: dict) -> dict:
        document = _document(request.user, optional_id(data.get("document")), format)
        return {
            "document": str(document.pk),
            "site": request.build_absolute_uri("/"),
            "versions": data.get("versions") is True,
        }

    return asked


def _done(format: str):
    def done(user, parameters: dict) -> Saved:
        document = _document(user, parameters["document"], format)
        calculation.refresh(document)
        if format in UNWIELDY and grids.oversized(document):
            raise Refused(413, "table_too_large")
        try:
            data = MADE[format](document, parameters, user)
            if format in macros.KINDS.values():
                data = macros.with_macros(
                    data if isinstance(data, bytes) else data.read(),
                    store.path_of(document.source.sha256),
                )
        except xlsx.Empty:
            raise Refused(409, "no_tables") from None
        except pptx.Unmeasured as error:
            log.warning("The slides of %s changed while they were measured: %s", document.pk, error)
            raise Refused(409, "slides_changed") from None
        except macros.Missing:
            raise Refused(404, "no_macros") from None
        except (pictures.UnreadablePdf, embedded.Unreadable) as error:
            log.error("A PDF of %s cannot be read: %s", document.pk, error)
            raise Refused(422, "unreadable_pdf") from None
        except pictures.Unreadable as error:
            log.error("An image of %s cannot be read: %s", document.pk, error)
            raise Refused(422, "unreadable_image") from None
        except printing.Unavailable:
            log.error("The printer did not lay out %s", document.pk, exc_info=True)
            raise Refused(503, "printer_unavailable") from None
        access_log.downloaded(user, document, format)
        return Saved(data, f"{document.title}.{format}")

    return done


KINDS = {format: Kind(_asked(format), _done(format), saves=True) for format in MADE}
