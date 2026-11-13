"""The pages of the PDF files a document shows, put in the printed document as they are: the
print page leaves a link of its own where each page goes, which is taken out for the page."""

import io
import re
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Pdf, Rectangle

from apps.blobs import store
from apps.content.models import DocumentBlob
from apps.documents.models import Node
from apps.imports import reading
from apps.reader import client

MARKER = re.compile(r"ponistra-pdf:([0-9a-f]{64})/([1-9][0-9]{0,5})")


class Unreadable(Exception):
    """A PDF the document shows cannot be read."""


def _marked(annot) -> tuple[str, int] | None:
    action = annot.get("/A") if isinstance(annot, Dictionary) else None
    uri = action.get("/URI") if isinstance(action, Dictionary) else None
    found = MARKER.fullmatch(str(uri)) if isinstance(uri, pikepdf.String) else None
    return (found[1], int(found[2])) if found else None


def _wanted(printed: bytes, shown: set[str]) -> list[str] | None:
    """The files of those the document shows whose pages the printed document marks, None where
    it marks none; the printer made it, so the backend reads it itself."""
    found: set[str] = set()
    marked = False
    with pikepdf.open(io.BytesIO(printed)) as out:
        for page in out.pages:
            annots = page.obj.get("/Annots")
            for annot in annots if isinstance(annots, Array) else []:
                if (place := _marked(annot)) is not None:
                    marked = True
                    if place[0] in shown:
                        found.add(place[0])
    return sorted(found) if marked else None


def placed(document: Node, printed: bytes) -> bytes:
    """The printed document with each marked place holding its page, scaled to fit it."""
    shown = set(
        DocumentBlob.objects.filter(document=document, blob__media_type=store.PDF).values_list(
            "blob_id", flat=True
        )
    )
    wanted = _wanted(printed, shown) if shown else None
    if wanted is None:
        return printed
    try:
        with client.answered(
            "embed", printed, *(store.path_of(sha256) for sha256 in wanted), files=wanted
        ) as answer:
            answer.finish()
            return answer.files[0].read_bytes()
    except (reading.Unreadable, reading.TooLarge) as error:
        raise Unreadable(str(error)) from error


def embedded(printed: Path, sources: dict[str, Path], out) -> None:
    """`placed`, in the reader: the file it makes sent."""
    opened: dict[str, Pdf] = {}
    try:
        with pikepdf.open(printed) as made:
            for page in made.pages:
                annots = page.obj.get("/Annots")
                if not isinstance(annots, Array):
                    continue
                kept = Array()
                for annot in annots:
                    found = _marked(annot)
                    if found is None:
                        kept.append(annot)
                        continue
                    sha256, number = found
                    if sha256 not in sources:
                        continue
                    if sha256 not in opened:
                        try:
                            opened[sha256] = pikepdf.open(sources[sha256])
                        except pikepdf.PdfError as error:
                            raise Unreadable(sha256) from error
                    source = opened[sha256]
                    if number <= len(source.pages):
                        rect = Rectangle(*(float(side) for side in annot.Rect))
                        page.add_overlay(source.pages[number - 1], rect)
                if len(kept):
                    page.obj.Annots = kept
                else:
                    del page.obj.Annots
            buffer = io.BytesIO()
            made.save(buffer)
        out.data(buffer.getvalue())
    finally:
        for source in opened.values():
            source.close()
