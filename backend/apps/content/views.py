import logging
import tempfile
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
from django.db.models.expressions import RawSQL
from django.http import JsonResponse, StreamingHttpResponse

from apps.access import rights
from apps.access.models import Role
from apps.blobs import edits, store
from apps.blobs.models import Blob
from apps.blobs.views import serve
from apps.collab import server
from apps.collab.books import wrote_whole
from apps.core import fetch
from apps.core.api import Refused, api, body, optional_id
from apps.documents.models import Node
from apps.documents.views import live, live_document, live_pdf, live_tab
from apps.exports import annotated
from apps.imports.reading import TooLarge, Unreadable
from apps.reader import client
from apps.search import extraction, ocr

from . import blocks, finding, pages
from .models import DocumentBlob, Element, Grid, GridRow

log = logging.getLogger(__name__)

PDFS = {store.PDF}
# What a glance at a document shows of its first tab.
GLANCED_BLOCKS = 12
GLANCED_ROWS = 8
GLANCED_COLS = 6


def seen_by(user, sha256) -> bool:
    """Whether the image or PDF is in a document the user can read."""
    readable, params = rights.readable(user)
    return DocumentBlob.objects.filter(
        blob_id=sha256, document_id__in=RawSQL(readable, params)
    ).exists()


def shown(user, sha256, types) -> Blob:
    """The image or PDF of one of the types, when a document the user can read shows it."""
    blob = Blob.objects.filter(pk=sha256, media_type__in=types).first()
    if blob is None or not seen_by(user, sha256):
        raise Refused(404, "not_found")
    return blob


def stored(stream, types, refusal: str) -> Blob:
    try:
        blob = store.put(stream)
    except store.TooLarge:
        raise Refused(413, "too_large") from None
    if blob.media_type not in types:
        raise Refused(415, refusal)
    return blob


def redrawn(blob: Blob, data: dict) -> Blob:
    """The image with the edits and marks the request brings drawn into it, a blob of its own."""
    kept, marks = data.get("edits", {}), data.get("marks", {})
    if not isinstance(kept, dict) or not isinstance(marks, dict):
        raise Refused(400, "invalid_edits")
    if blob.media_type not in edits.FORMATS:
        raise Refused(415, "not_editable")
    try:
        wanted = edits.read(kept, marks)
        return blob if wanted == edits.Edits() else edits.drawn(blob, wanted)
    except edits.Unreadable:
        raise Refused(400, "invalid_edits") from None
    except edits.FAILURES as error:
        log.error("The edits of image %s cannot be drawn: %s", blob.sha256, error)
        raise Refused(422, "unreadable") from None


def received(request) -> Blob:
    """The image the request brings: its bytes, an image file or an image of another document
    the user can read, edited where the request says how, or the address of one on the web."""
    if request.content_type != "application/json":
        return stored(request, store.IMAGES, "not_an_image")
    data = body(request)
    if (id := optional_id(data.get("file"))) is not None:
        file, _ = live(request.user, id)
        if file.kind != Node.Kind.FILE:
            raise Refused(400, "not_a_file")
        if file.blob.media_type not in store.IMAGES:
            raise Refused(415, "not_an_image")
        return file.blob
    if isinstance(sha256 := data.get("blob"), str):
        blob = shown(request.user, sha256, store.IMAGES)
        return redrawn(blob, data) if "edits" in data or "marks" in data else blob
    if isinstance(url := data.get("url"), str):
        try:
            with fetch.fetched(url) as response:
                return stored(response, store.IMAGES, "not_an_image")
        except fetch.Unreachable:
            raise Refused(422, "unreachable") from None
    raise Refused(400, "no_image")


@api("POST", visitors=True)
def images(request, pk):
    document = live_document(request.user, pk, Role.EDIT)
    blob = received(request)
    DocumentBlob.objects.get_or_create(document=document, blob=blob)
    return JsonResponse({"blob": blob.sha256, "media_type": blob.media_type}, status=201)


@api("GET", visitors=True)
def image(request, sha256):
    blob = shown(request.user, sha256, store.IMAGES)
    response = serve(request, blob, f"{sha256[:12]}.{store.IMAGES[blob.media_type]}")
    # An SVG is a document that can run script; sandboxed, it is only a picture.
    response["Content-Security-Policy"] = "sandbox"
    return response


def brought(request) -> Blob:
    """The PDF the request brings: its bytes, a file the user can read, as its text was read in
    it, or a PDF of another document they can read."""
    if request.content_type != "application/json":
        return stored(request, PDFS, "not_a_pdf")
    data = body(request)
    if (id := optional_id(data.get("file"))) is not None:
        file, _ = live_pdf(request.user, id)
        return ocr.readable(file.blob)
    if isinstance(sha256 := data.get("blob"), str):
        return shown(request.user, sha256, PDFS)
    raise Refused(400, "no_pdf")


def embeddable(blob: Blob) -> None:
    """Refuses a PDF that only opens with its password, which a reader of the document is never
    asked for, or whose own permissions keep its pages out of another."""
    try:
        assembled = client.ask("pdf_assembly", store.path_of(blob.sha256))
    except annotated.Locked:
        raise Refused(409, "locked") from None
    except Unreadable, TooLarge:
        raise Refused(422, "unreadable") from None
    if not assembled:
        raise Refused(409, "assembly_forbidden")


def assembly(path: Path) -> bool:
    """Whether the PDF's own permissions let its pages into another; in the reader."""
    with pikepdf.open(path) as pdf:
        return pdf.allow.modify_assembly


@api("POST", visitors=True)
def pdfs(request, pk):
    document = live_document(request.user, pk, Role.EDIT)
    blob = brought(request)
    embeddable(blob)
    DocumentBlob.objects.get_or_create(document=document, blob=blob)
    extraction.wake()
    return JsonResponse({"blob": blob.sha256}, status=201)


@api("GET", visitors=True)
def pdf(request, sha256):
    return serve(request, shown(request.user, sha256, PDFS), f"{sha256[:12]}.pdf")


def _sizes(path: Path) -> list[tuple[float, float]]:
    try:
        return client.ask("pdf_sizes", path)
    except Unreadable, TooLarge:
        raise Refused(422, "unreadable") from None


def sizes(path: Path) -> list[tuple[float, float]]:
    """The size of each of the PDF's pages; in the reader."""
    opened = pdfium.PdfDocument(path)
    try:
        return [opened.get_page_size(index) for index in range(len(opened))]
    finally:
        opened.close()


@api("GET", visitors=True)
def pdf_pages(request, sha256):
    """The size of each of the PDF's pages in points, as it shows: turned where it is."""
    sizes = _sizes(store.path_of(shown(request.user, sha256, PDFS).sha256))
    return JsonResponse({"pages": [[round(width, 2), round(height, 2)] for width, height in sizes]})


def _whole(room, fragments) -> StreamingHttpResponse:
    def reading(doc, held):
        present = {table for each in fragments(doc) for table in blocks.table_ids(each)}
        kept = {table: found for table, found in held.tables() if table in present}
        file = tempfile.TemporaryFile()
        try:
            wrote_whole(file, kept, held)
        except BaseException:
            file.close()
            raise
        file.seek(0)
        return file

    return StreamingHttpResponse(
        store.streamed(server.read_grids(room, reading, settled=True)),
        content_type="application/json",
    )


@api("GET", visitors=True)
def tab_grids(request, pk):
    """The grids of the tab's tables whole, every row with what its cells show: what its
    pages print."""
    tab = live_tab(request.user, pk, Role.READ)
    return _whole(tab.room, lambda doc: [blocks.body_of(doc)])


@api("GET", visitors=True)
def tab_found(request, pk):
    """The hits of the text sought in the tab, its text and its tables, in their order: at most
    finding.LIMIT, and whether there are more."""
    tab = live_tab(request.user, pk, Role.READ)
    text = request.GET.get("text", "")
    if not text:
        raise Refused(400, "invalid")
    sought = finding.Sought(text, request.GET.get("case") == "1", request.GET.get("words") == "1")

    def reading(doc, held):
        body = blocks.body_of(doc)
        grids = {table: held.peek(table) for table in blocks.table_ids(body) if table in held}
        return finding.found_in(body, grids, sought)

    hits, more = server.read_grids(tab.room, reading, settled=True)
    return JsonResponse({"hits": [hit.json() for hit in hits], "more": more})


def _shown(row: GridRow, col: str) -> str:
    """What the cell shows: the text the server computed for it, else what was typed, without
    the apostrophe that keeps it text."""
    if col in row.shown:
        return row.shown[col]
    return row.cells.get(col, {}).get("text", "").removeprefix("'")


@api("GET", visitors=True)
def node_beginning(request, pk):
    """The first blocks of the document's first tab as its content was last read: their text,
    a heading's level, the first rows of a table as they show and an image."""
    document = live_document(request.user, pk)
    tab = document.tabs.filter(parent=None).order_by("position").first()
    found = list(
        Element.objects.filter(tab=tab, row="")
        .exclude(type__in=("footnote", "endnote", "pdf", "chart"))
        .order_by("position")[: GLANCED_BLOCKS + 1]
    )
    tables = [each.block for each in found if each.type == "table"]
    grids = {grid.table: grid for grid in Grid.objects.filter(document=document, table__in=tables)}
    shown = []
    for element in found[:GLANCED_BLOCKS]:
        attrs = element.content.get("attrs", {})
        if element.type == "image":
            shown.append({"type": "image", "blob": attrs["blob"], "alt": attrs.get("alt", "")})
        elif element.type == "table":
            grid = grids.get(element.block)
            cols = [col["id"] for col in grid.cols[:GLANCED_COLS]] if grid else []
            rows = grid.rows.order_by("position")[:GLANCED_ROWS] if grid else []
            shown.append(
                {"type": "table", "rows": [[_shown(row, col) for col in cols] for row in rows]}
            )
        else:
            shown.append({"type": element.type, "text": element.text, "level": attrs.get("level")})
    return JsonResponse({"blocks": shown, "more": len(found) > GLANCED_BLOCKS})


@api("GET", visitors=True)
def node_grids(request, pk):
    """The grids of the tables in the document's headers and footers whole."""
    return _whole(live_document(request.user, pk).room, pages.fragments)
