"""A file taken from somewhere else placed in a folder as an upload places it (D37, D44)."""

import re

from apps.blobs import store
from apps.blobs.models import Blob
from apps.documents.models import Node
from apps.documents.views import created

from . import create, ponx, reading
from .formats import EXTENSIONS

EXTENSION = re.compile(r"\.([a-z0-9]*[a-z][a-z0-9]*)$", re.IGNORECASE)
KEPT = {
    reading.TooManyCells: "too_many_cells",
    reading.TooManyFormulas: "too_many_formulas",
    reading.TooLarge: "too_large",
    ponx.Newer: "newer_file",
    reading.Unreadable: "unreadable",
}


def named(name: str) -> tuple[str, str]:
    """A file's title and the extension that names its kind, as an upload names them."""
    found = EXTENSION.search(name)
    extension = found.group(1) if found and found.start() > 0 and len(found.group(1)) <= 10 else ""
    title = name[: found.start()].strip() if found and extension else name.strip()
    return (title or name)[:200], extension.lower()


def placed(blob: Blob, parent: Node, title: str, extension: str, user, old: Node | None):
    """The file in the folder: a document where PONISTRA imports its kind and can read it, else
    the file it is, with why the import could not. A document read again keeps its place, its
    links and its versions. A converter that cannot be reached raises `convert.Unavailable`."""
    kept = ""
    if blob.media_type in EXTENSIONS or blob.media_type == store.PONX:
        try:
            if old is not None and old.kind == Node.Kind.DOCUMENT and blob.media_type != store.PONX:
                old.source = blob
                node = create.reimport(old, user)
                Node.objects.filter(pk=node.pk).update(source=blob)
                return node, ""
            made = ponx.document if blob.media_type == store.PONX else create.document
            node = made(blob, parent, title, user)
        except tuple(KEPT) as refused:
            kept = KEPT[type(refused)]
        else:
            if old is not None:
                old.delete()
            return node, ""
    if old is not None and old.kind == Node.Kind.FILE:
        old.blob, old.extension = blob, extension
        old.save(update_fields=["blob", "extension", "updated_at"])
        return old, kept
    node = created(parent, Node.Kind.FILE, title, blob, user, extension)
    if old is not None:
        old.delete()
    return node, kept
