"""A file with its notes written in; the folders and files chosen in Documents as one zip."""

import logging
import uuid

from django.http import StreamingHttpResponse
from django.utils.http import content_disposition_header

from apps.access import rights
from apps.blobs import store
from apps.blobs.views import chunks, serve
from apps.core.api import Refused, api
from apps.core.asyncdb import database
from apps.documents.models import Node
from apps.documents.views import file_name, live_pdf, taken_out
from apps.search import ocr

from . import annotated, jobs, tree, zipped

log = logging.getLogger(__name__)
# What a zip of Documents takes at once: the rows chosen in one folder.
CHOSEN = 1000


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


def _picked(given: list[str]) -> list[uuid.UUID]:
    if not 0 < len(given) <= CHOSEN:
        raise Refused(400, "invalid_nodes")
    try:
        return list(dict.fromkeys(uuid.UUID(each) for each in given))
    except ValueError:
        raise Refused(400, "invalid_nodes") from None


async def _once(data: bytes):
    yield data


async def _documents(user, walked: list[tuple[Node, rights.Reach]], site: str):
    archive = zipped.Zipped()
    places: dict = {}
    for node, reach in walked:
        folder = places.get(node.parent_id, "")
        if node.kind == Node.Kind.FOLDER:
            places[node.pk] = archive.named(folder, node.title)
            archive.folder(places[node.pk], node.updated_at)
            continue
        if node.kind == Node.Kind.LINK:
            path = archive.named(folder, f"{node.title}.url")
            shortcut = f"[InternetShortcut]\r\nURL={node.href}\r\n".encode()
            size, parts = len(shortcut), _once(shortcut)
        elif node.kind == Node.Kind.DOCUMENT:
            format = tree.office_format(node)
            parameters = {"document": str(node.pk), "site": site, "versions": False}
            saved = await database(jobs.KINDS[format].done)(user, parameters)
            path = archive.named(folder, saved.name)
            if isinstance(saved.data, bytes):
                size, parts = len(saved.data), _once(saved.data)
            else:
                size, parts = None, store.streamed(saved.data)
        else:
            path = archive.named(folder, file_name(node))
            blob = await database(tree.blob_of)(user, node, reach)
            if blob is None:
                size, parts = await database(tree.with_notes)(node)
            else:
                size, parts = blob.size, chunks(store.path_of(blob.sha256), 0, blob.size)
        async for sent in zipped.written(archive, path, node.updated_at, size, parts):
            yield sent
    yield archive.closed()


async def _logged(stream, title: str):
    try:
        async for sent in stream:
            yield sent
    except Exception:
        log.exception("The zip %s stopped while it was sent", title)
        raise


@api("GET", visitors=True)
def nodes_zip(request):
    """The folders, documents and files chosen as one zip, sent as it is written: each
    document saved in its Office format and each file as it is downloaded alone, every one of
    them logged as taken out."""
    ids = _picked(request.GET.getlist("node"))
    title, walked = tree.walked(request.user, ids)
    stream = _documents(request.user, walked, request.build_absolute_uri("/"))
    return StreamingHttpResponse(
        _logged(stream, title), content_type="application/zip", headers=zipped.zip_headers(title)
    )
