"""A file with its notes written in."""

import logging

from django.http import StreamingHttpResponse
from django.utils.http import content_disposition_header

from apps.blobs import store
from apps.blobs.views import serve
from apps.core.api import Refused, api
from apps.documents.views import file_name, live_pdf, taken_out
from apps.search import ocr

from . import annotated

log = logging.getLogger(__name__)


@api("GET", visitors=True)
def noted(request, pk):
    """The file with its notes written in, as it is opened or saved outside PONISTRA; without
    notes, or locked by a password they cannot be written under, the file as it is shown."""
    node, reach = live_pdf(request.user, pk)
    taken_out(request.user, node, reach, "pdf")
    try:
        written = annotated.written(node)
    except annotated.Locked:
        written = None
    except annotated.Unreadable as error:
        log.error("The notes of %s cannot be read: %s", node.pk, error)
        raise Refused(422, "unreadable_notes") from None
    name = file_name(node)
    if written is None:
        return serve(request, ocr.readable(node.blob), name)
    disposition = content_disposition_header(request.GET.get("download") == "1", name)
    return StreamingHttpResponse(
        store.streamed(written),
        content_type=store.PDF,
        headers={"Content-Disposition": disposition, "Cache-Control": "private, no-cache"},
    )
