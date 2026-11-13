"""A copy of a PDF file without what its redaction marks cover: the text, images and drawings under
each box taken out of the file and the box drawn black over the place, the links, notes and form
fields the boxes touch removed, and the whole copy cleared of what a reader does not see: metadata,
attachments, scripts, thumbnails, private application data and earlier revisions. pdfium, which
did not write it, reads the copy before it is kept; any character still under a box and no file is
made. The file in PONISTRA stays as it came, its marks with it. The copy is made in the reader
(D51); the backend gives it the boxes and keeps what comes back."""

import ctypes
import tempfile
import uuid
from collections import defaultdict
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from django.db import transaction
from pikepdf import Array, Dictionary, Name, NumberTree, Pdf, Stream
from pycrdt import Doc, Map

from apps.access.models import Grant, Role
from apps.blobs import previews, store
from apps.collab.models import Update
from apps.documents.models import Node
from apps.exports import annotated
from apps.reader import client
from apps.search import extraction, ocr

from .composed import names_of
from .redaction.content import ALTERNATES, redact_page
from .redaction.fonts import number
from .redaction.paths import Box, Point, covered, overlap

# A character this much under a box was left in the copy.
LEFT = 0.8
ATTACHED = {Name.FileAttachment, Name.Sound, Name.Movie, Name.Screen, Name.RichMedia, Name("/3D")}
SCRIPTED = {Name.JavaScript, Name.Launch, Name.GoToE, Name.Rendition, Name.ImportData}
PRIVATE = ("/Metadata", "/PieceInfo", "/AA", "/Thumb", "/AF", "/JS")


class Forbidden(Exception):
    """The file's own permissions forbid changing its content."""


class Unmarked(Exception):
    """Nothing is marked to be blacked out."""


class Left(Exception):
    """Characters the boxes cover that the copy still holds."""


def _boxes(file: Node) -> dict[int, list[Box]]:
    found: dict[int, list[Box]] = defaultdict(list)
    for mark in annotated.redactions_of(file):
        found[mark.page] += [tuple(rect) for rect in mark.rects]
    if not found:
        raise Unmarked
    return dict(found)


def _rect(annotation: Dictionary) -> Box | None:
    values = [number(each) for each in annotation.get("/Rect", Array())]
    if len(values) != 4:
        return None
    return (
        min(values[0], values[2]),
        min(values[1], values[3]),
        max(values[0], values[2]),
        max(values[1], values[3]),
    )


def _key(annotation: object) -> object:
    return annotation.objgen if annotation.is_indirect else id(annotation)


def _unfield(pdf: Pdf, widget: Dictionary) -> None:
    """The widget out of its form field, and each field left without widgets out of the form."""
    node = widget
    for _ in range(64):
        parent = node.get("/Parent")
        if isinstance(parent, Dictionary):
            kids = [kid for kid in parent.get("/Kids") or [] if _key(kid) != _key(node)]
            parent.Kids = Array(kids)
            if kids:
                return
            node = parent
            continue
        form = pdf.Root.get("/AcroForm")
        if isinstance(form, Dictionary):
            for key in ("/Fields", "/CO"):
                if isinstance(form.get(key), Array):
                    form[key] = Array([each for each in form[key] if _key(each) != _key(node)])
        return


def _annotations(pdf: Pdf, boxes: dict[int, list[Box]]) -> None:
    """The annotations a box touches gone, with their pop-ups and replies, and every attachment."""
    for index, page in enumerate(pdf.pages):
        annotations = page.obj.get("/Annots")
        if not isinstance(annotations, Array):
            continue
        here = boxes.get(index + 1, [])
        listed = [each for each in annotations if isinstance(each, Dictionary)]
        gone = set()
        for each in listed:
            rect = _rect(each)
            if each.get("/Subtype") in ATTACHED or (
                rect is not None and any(overlap(rect, box) for box in here)
            ):
                gone.add(_key(each))
        while True:
            more = {
                _key(each)
                for each in listed
                if _key(each) not in gone
                and any(
                    isinstance(each.get(key), Dictionary) and _key(each[key]) in gone
                    for key in ("/IRT", "/Parent")
                )
            }
            more |= {
                _key(each["/Popup"])
                for each in listed
                if _key(each) in gone and isinstance(each.get("/Popup"), Dictionary)
            }
            if more <= gone:
                break
            gone |= more
        for each in listed:
            if _key(each) in gone and each.get("/Subtype") == Name.Widget:
                _unfield(pdf, each)
        page.obj.Annots = Array(
            [
                each
                for each in annotations
                if not isinstance(each, Dictionary) or _key(each) not in gone
            ]
        )


def _field_type(widget: Dictionary) -> object:
    node = widget
    for _ in range(64):
        if not isinstance(node, Dictionary):
            return None
        if "/FT" in node:
            return node["/FT"]
        node = node.get("/Parent")
    return None


def _unsigned(pdf: Pdf) -> None:
    """Signatures, which sign the file as it was, taken off with what they show."""
    for page in pdf.pages:
        for widget in page.obj.get("/Annots") or []:
            if not isinstance(widget, Dictionary) or _field_type(widget) != Name.Sig:
                continue
            if "/AP" in widget:
                del widget["/AP"]
            node = widget
            for _ in range(64):
                if not isinstance(node, Dictionary):
                    break
                if "/V" in node:
                    del node["/V"]
                node = node.get("/Parent")
    form = pdf.Root.get("/AcroForm")
    if isinstance(form, Dictionary):
        for key in ("/SigFlags", "/XFA"):
            if key in form:
                del form[key]
    for key in ("/Perms", "/DSS"):
        if key in pdf.Root:
            del pdf.Root[key]


def _safe(action: object) -> bool:
    return not isinstance(action, Dictionary) or action.get("/S") not in SCRIPTED


def _scrubbed(pdf: Pdf) -> None:
    """What a reader does not see: the document's metadata, attachments, scripts, thumbnails
    and private application data."""
    if "/Info" in pdf.trailer:
        del pdf.trailer["/Info"]
    for key in ("/Collection", "/SpiderInfo"):
        if key in pdf.Root:
            del pdf.Root[key]
    names = pdf.Root.get("/Names")
    if isinstance(names, Dictionary):
        for key in ("/JavaScript", "/EmbeddedFiles", "/AlternatePresentations"):
            if key in names:
                del names[key]
    for each in pdf.objects:
        if not isinstance(each, Dictionary | Stream):
            continue
        for key in PRIVATE:
            if key in each:
                del each[key]
        for key in ("/A", "/OpenAction"):
            if key in each and not _safe(each[key]):
                del each[key]
        following = each.get("/Next") if "/S" in each else None
        if isinstance(following, Array):
            each.Next = Array([action for action in following if _safe(action)])
        elif following is not None and not _safe(following):
            del each["/Next"]


def _unexplained(pdf: Pdf, marked: set[tuple[int, int | None]]) -> None:
    """The structure's alternate and actual texts of what was taken out, and of what holds it."""
    root = pdf.Root.get("/StructTreeRoot")
    tree = root.get("/ParentTree") if isinstance(root, Dictionary) else None
    if not marked or not isinstance(tree, Dictionary):
        return
    parents = NumberTree(tree)
    for key, mcid in marked:
        entry = parents.get(key)
        element = entry
        if mcid is not None:
            element = entry[mcid] if isinstance(entry, Array) and 0 <= mcid < len(entry) else None
        for _ in range(256):
            if not isinstance(element, Dictionary) or element.get("/Type") == Name.StructTreeRoot:
                break
            for alternate in ALTERNATES:
                if alternate in element:
                    del element[alternate]
            element = element.get("/P")


def _read(path: str, boxes: dict[int, list[Box]]) -> dict[int, list[tuple[Point, Box, int]]]:
    """Each character pdfium reads on a page with boxes, near one of them: where it is drawn from
    and the box of what it draws."""
    document = pdfium.PdfDocument(path)
    found: dict[int, list[tuple[Point, Box, int]]] = {}
    x, y = ctypes.c_double(), ctypes.c_double()
    try:
        for number_of, here in boxes.items():
            page = document[number_of - 1]
            text = page.get_textpage()
            held = found.setdefault(number_of, [])
            try:
                for index in range(text.count_chars()):
                    if pdfium_c.FPDFText_IsGenerated(text.raw, index) == 1:
                        continue
                    if not any(overlap(text.get_charbox(index, loose=True), box) for box in here):
                        continue
                    pdfium_c.FPDFText_GetCharOrigin(text.raw, index, x, y)
                    code = pdfium_c.FPDFText_GetUnicode(text.raw, index)
                    held.append(((x.value, y.value), text.get_charbox(index), code))
            finally:
                text.close()
                page.close()
    finally:
        document.close()
    return found


def _left(path: str, boxes: dict[int, list[Box]]) -> int:
    """How many characters pdfium still reads under the boxes."""
    return sum(
        1
        for number_of, chars in _read(path, boxes).items()
        for _, ink, code in chars
        if code and not chr(code).isspace() and covered(ink, boxes[number_of]) >= LEFT
    )


def _touches(mark: dict, boxes: list[Box]) -> bool:
    if mark["kind"] == "highlight":
        rects = [tuple(rect) for rect in mark["rects"]]
    else:
        xs, ys, reach = mark["points"][0::2], mark["points"][1::2], mark["width"] / 2
        rects = [(min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach)]
    return any(overlap(rect, box) for rect in rects for box in boxes)


def _room(file: Node, names: set[str], boxes: dict[int, list[Box]]) -> bytes | None:
    """The copy's own room: the notes and filled-in values the boxes do not touch."""
    marks = {
        str(uuid.uuid4()): mark
        for mark in annotated.marks_in(file).values()
        if not _touches(mark, boxes.get(mark["page"], []))
    }
    filled = {name: entry for name, entry in annotated.fields_in(file).items() if name in names}
    if not marks and not filled:
        return None
    doc = Doc()
    held, values = doc.get("marks", type=Map), doc.get("fields", type=Map)
    with doc.transaction():
        for key, mark in marks.items():
            held[key] = mark
        for name, entry in filled.items():
            values[name] = entry
    return doc.get_update()


def blacked(path: Path, boxes: dict[int, list[Box]], out) -> list[str]:
    """Sends the copy of the file at `path` without what the boxes cover, in the reader, and ends
    with the names of the copy's fields that hold values."""
    try:
        pdf = pikepdf.open(path)
    except pikepdf.PasswordError:
        raise annotated.Locked from None
    with pdf, tempfile.NamedTemporaryFile(suffix=".pdf") as written:
        if not pdf.allow.modify_other:
            raise Forbidden
        if max(boxes) > len(pdf.pages):
            raise annotated.Unreadable(f"a redaction on page {max(boxes)} of {len(pdf.pages)}")
        inks = _read(pdf.filename, boxes)
        _annotations(pdf, boxes)
        _unsigned(pdf)
        marked = set()
        for number_of, here in sorted(boxes.items()):
            drawn = [(origin, ink) for origin, ink, _ in inks[number_of]]
            marked |= redact_page(pdf, pdf.pages[number_of - 1], here, drawn).marked
        _unexplained(pdf, marked)
        _scrubbed(pdf)
        form = pdf.Root.get("/AcroForm")
        names = names_of(form.Fields) if isinstance(form, Dictionary) and "/Fields" in form else ()
        pdf.remove_unreferenced_resources()
        pdf.save(written, linearize=True, encryption=pdf.is_encrypted)
        written.flush()
        left = _left(written.name, boxes)
        if left:
            raise Left(f"{left} characters under the boxes")
        out.file(Path(written.name))
    return sorted(names)


def redact(file: Node, parent: Node | None, title: str, user) -> Node:
    """The blacked-out copy, in the folder given or at the top of the user's own documents."""
    boxes = _boxes(file)
    path = store.path_of(ocr.readable(file.blob).sha256)
    with client.answered("redact", path, boxes=boxes) as answer:
        room = _room(file, set(answer.finish()), boxes)
        with answer.files[0].open("rb") as written:
            blob = store.put(written)
    with transaction.atomic():
        node = Node.objects.create(
            parent=parent,
            kind=Node.Kind.FILE,
            title=title,
            blob=blob,
            created_by=user,
            updated_by=user,
        )
        if parent is None:
            Grant.objects.create(node=node, user=user, role=Role.OWN, created_by=user)
        if room is not None:
            Update.objects.create(document=node, room=node.room, data=room)
        extraction.wake()
        previews.wake()
    return node
