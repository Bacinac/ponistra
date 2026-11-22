"""A file with its notes written in; the folders and files chosen in Documents as one zip."""

import logging
import uuid

from django.http import StreamingHttpResponse
from django.utils.http import content_disposition_header

from apps.access import rights
from apps.blobs import edits, store
from apps.blobs.models import Blob
from apps.blobs.views import chunks, serve
from apps.core.api import Refused, api
from apps.core.asyncdb import database
from apps.documents.models import Node
from apps.documents.views import extension_of, file_name, live_pdf, taken_out
from apps.imports.formats import read_as
from apps.search import ocr

from . import annotated, jobs, macros, zipped

log = logging.getLogger(__name__)
# What a zip of Documents takes at once: the rows chosen in one folder.
CHOSEN = 1000
BY_HOLDS = {Node.Holds.TABLE: "xlsx", Node.Holds.SLIDES: "pptx"}


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


def _walked(user, ids: list[uuid.UUID]) -> tuple[str, list[tuple[Node, rights.Reach]]]:
    """The nodes chosen with all their folders hold, each after its folder, and the zip's
    title; refused whole where one of them may not leave the browser."""
    chosen = sorted(
        Node.objects.filter(pk__in=ids, trashed_at=None), key=lambda node: node.title.lower()
    )
    reached = rights.reaches(user, [node.pk for node in chosen])
    if len(chosen) != len(ids) or any(
        not node.is_live(reached[node.pk].ancestry) or reached[node.pk].role is None
        for node in chosen
    ):
        raise Refused(404, "not_found")
    walked = []
    for node in chosen:
        walked.append(node)
        if node.kind == Node.Kind.FOLDER:
            walked.extend(node.descendants())
    loaded = Node.objects.select_related("blob", "source").in_bulk([node.pk for node in walked])
    walked = [loaded[node.pk] for node in walked]
    reached |= rights.reaches(user, [node.pk for node in walked if node.pk not in reached])
    if any(reached[node.pk].confined for node in walked):
        raise Refused(403, "confined")
    parents = {node.parent_id for node in chosen}
    if len(chosen) == 1:
        title = chosen[0].title
    elif len(parents) == 1 and None not in parents:
        title = reached[chosen[0].pk].ancestry[-2].title
    else:
        title = "Ponistra"
    return title, [(node, reached[node.pk]) for node in walked]


def _format(document: Node) -> str:
    """The Office format a document is saved in as the editor saves it: that of the file it came
    from, with its macros, else the one its content takes."""
    if document.source_id:
        media_type = document.source.media_type
        return macros.KINDS.get(media_type) or read_as(media_type)
    return BY_HOLDS.get(document.holds, "docx")


def _blob_of(user, node: Node, reach: rights.Reach) -> Blob | None:
    """The bytes a file is saved from, as when it is downloaded alone: a PDF's with its notes
    (None, written apart), an image's with its edits."""
    taken_out(user, node, reach, extension_of(node) or "file")
    if node.is_pdf:
        return None
    if node.blob.media_type in edits.FORMATS:
        return edits.current(node.pk) or node.blob
    return node.blob


def _noted(node: Node):
    written = annotated.written(node)
    if written is None:
        blob = ocr.readable(node.blob)
        return blob.size, chunks(store.path_of(blob.sha256), 0, blob.size)
    return None, store.streamed(written)


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
            format = _format(node)
            parameters = {"document": str(node.pk), "site": site, "versions": False}
            saved = await database(jobs.KINDS[format].done)(user, parameters)
            path = archive.named(folder, saved.name)
            if isinstance(saved.data, bytes):
                size, parts = len(saved.data), _once(saved.data)
            else:
                size, parts = None, store.streamed(saved.data)
        else:
            path = archive.named(folder, file_name(node))
            blob = await database(_blob_of)(user, node, reach)
            if blob is None:
                size, parts = await database(_noted)(node)
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
    title, walked = _walked(request.user, ids)
    stream = _documents(request.user, walked, request.build_absolute_uri("/"))
    return StreamingHttpResponse(
        _logged(stream, title), content_type="application/zip", headers=zipped.zip_headers(title)
    )
