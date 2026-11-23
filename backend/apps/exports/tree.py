"""What leaves Ponistra's tree as files: the nodes chosen with all their folders hold, each
document in its Office format, a file in the bytes it is saved from."""

import uuid

from apps.access import rights
from apps.blobs import edits, store
from apps.blobs.models import Blob
from apps.blobs.views import chunks
from apps.core.api import Refused
from apps.documents.models import Node
from apps.documents.views import extension_of, taken_out
from apps.imports.formats import read_as
from apps.search import ocr

from . import annotated, macros

BY_HOLDS = {Node.Holds.TABLE: "xlsx", Node.Holds.SLIDES: "pptx"}


def walked(
    user, ids: list[uuid.UUID], leaving: bool = True
) -> tuple[str, list[tuple[Node, rights.Reach]]]:
    """The nodes chosen with all their folders hold, each after its folder, and the zip's
    title; refused whole where one of them may not leave the browser, unless they stay in it."""
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
    if leaving and any(reached[node.pk].confined for node in walked):
        raise Refused(403, "confined")
    parents = {node.parent_id for node in chosen}
    if len(chosen) == 1:
        title = chosen[0].title
    elif len(parents) == 1 and None not in parents:
        title = reached[chosen[0].pk].ancestry[-2].title
    else:
        title = "Ponistra"
    return title, [(node, reached[node.pk]) for node in walked]


def office_format(document: Node) -> str:
    """The Office format a document is saved in as the editor saves it: that of the file it came
    from, with its macros, else the one its content takes."""
    if document.source_id:
        media_type = document.source.media_type
        return macros.KINDS.get(media_type) or read_as(media_type)
    return BY_HOLDS.get(document.holds, "docx")


def blob_of(user, node: Node, reach: rights.Reach) -> Blob | None:
    """The bytes a file is saved from, as when it is downloaded alone: a PDF's with its notes
    (None, written apart), an image's with its edits."""
    taken_out(user, node, reach, extension_of(node) or "file")
    if node.is_pdf:
        return None
    if node.blob.media_type in edits.FORMATS:
        return edits.current(node.pk) or node.blob
    return node.blob


def with_notes(node: Node):
    written = annotated.written(node)
    if written is None:
        blob = ocr.readable(node.blob)
        return blob.size, chunks(store.path_of(blob.sha256), 0, blob.size)
    return None, store.streamed(written)
