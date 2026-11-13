"""A file's notes written into a copy of it as the annotations every PDF reader knows: a highlight
and the text a comment is about as Highlight, a stroke as Ink, a comment on a point as Text, and
a thread's replies and resolution as Text in reply to it; and its form filled in, its fields still
fields. The file in PONISTRA stays as it came."""

import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

import pikepdf
from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from django.utils import timezone
from pikepdf import AcroFormField, Array, Dictionary, FormFieldFlag, Name, Pdf, String
from pikepdf.form import DefaultAppearanceStreamGenerator
from pikepdf.models.metadata import encode_pdf_date
from pycrdt import Map

from apps.blobs import store
from apps.collab import server
from apps.collab.kept import finite, moment, whole
from apps.comments.models import Comment, Thread
from apps.content import palette
from apps.documents.models import Node
from apps.reader import client
from apps.search import ocr

PRINT = 4
NO_VIEW = 32
# The side of a point comment's icon, in points, its top left corner on the point.
ICON = 20
COMMENT = "yellow"


class Locked(Exception):
    """The file opens only with its password, which never reaches PONISTRA."""


class Unreadable(ValueError):
    """A note or a field's value in the file's room that is not as the viewer writes it."""


@dataclass(frozen=True)
class Highlight:
    id: str
    page: int
    color: str
    rects: list[list[float]]
    by: int | None
    at: datetime


@dataclass(frozen=True)
class Stroke:
    id: str
    page: int
    color: str
    width: float
    points: list[float]
    by: int | None
    at: datetime


SHAPES = {
    "highlight": {"kind", "page", "color", "rects", "by", "at"},
    "stroke": {"kind", "page", "color", "width", "points", "by", "at"},
}


def _read(key: str, mark: object) -> Highlight | Stroke:
    kind = mark.get("kind") if isinstance(mark, dict) else None
    if kind not in SHAPES or mark.keys() != SHAPES[kind]:
        raise Unreadable(f"note {key}: {mark!r}")
    page, by, when = whole(mark["page"]), whole(mark["by"]), moment(mark["at"])
    color = (palette.highlight if kind == "highlight" else palette.text)(mark["color"])
    if (
        page is None
        or page < 1
        or color is None
        or (by is None and mark["by"] is not None)
        or when is None
    ):
        raise Unreadable(f"note {key}: {mark!r}")
    if kind == "highlight":
        rects = mark["rects"]
        if not (isinstance(rects, list) and rects and all(finite(rect, 4) for rect in rects)):
            raise Unreadable(f"note {key}: {mark!r}")
        return Highlight(key, page, color, rects, by, when)
    width, points = mark["width"], mark["points"]
    if not (finite([width], 1) and width > 0 and finite(points)):
        raise Unreadable(f"note {key}: {mark!r}")
    return Stroke(key, page, color, width, points, by, when)


def _kept(file: Node, name: str) -> dict:
    return server.read(file.room, lambda doc: dict(doc.get(name, type=Map).to_py() or {}))


def marks_of(file: Node) -> list[Highlight | Stroke]:
    """The file's highlights and strokes in the order they were made."""
    marks = [_read(key, mark) for key, mark in _kept(file, "marks").items()]
    return sorted(marks, key=lambda mark: (mark.at, mark.id))


def marks_in(file: Node) -> dict[str, dict]:
    """The file's highlights and strokes as its room keeps them, each checked."""
    found = _kept(file, "marks")
    for key, mark in found.items():
        _read(key, mark)
    return found


@dataclass(frozen=True)
class Redaction:
    id: str
    page: int
    rects: list[list[float]]
    by: int | None
    at: datetime


REDACTION = {"kind", "page", "rects", "by", "at"}


def _redaction(key: str, mark: object) -> Redaction:
    if not isinstance(mark, dict) or mark.get("kind") != "redaction" or mark.keys() != REDACTION:
        raise Unreadable(f"redaction {key}: {mark!r}")
    page, by, when, rects = (
        whole(mark["page"]),
        whole(mark["by"]),
        moment(mark["at"]),
        mark["rects"],
    )
    if (
        page is None
        or page < 1
        or (by is None and mark["by"] is not None)
        or when is None
        or not isinstance(rects, list)
        or not rects
        or not all(finite(rect, 4) and rect[0] < rect[2] and rect[1] < rect[3] for rect in rects)
    ):
        raise Unreadable(f"redaction {key}: {mark!r}")
    return Redaction(key, page, rects, by, when)


def redactions_of(file: Node) -> list[Redaction]:
    """What the file's readers marked to be blacked out of a copy of it."""
    marks = [_redaction(key, mark) for key, mark in _kept(file, "redactions").items()]
    return sorted(marks, key=lambda mark: (mark.at, mark.id))


@dataclass(frozen=True)
class Filled:
    name: str
    value: str | list[str]
    shown: str | None


@dataclass(frozen=True)
class Discussed:
    """A comment thread as the file keeps it: where it is, each comment's author, time, text and
    name, and who resolved it and when."""

    id: str
    anchor: dict
    comments: list[tuple[str, datetime, str, str]]
    resolved: tuple[str, datetime] | None


def _discussed(thread: Thread) -> Discussed:
    return Discussed(
        str(thread.id),
        thread.anchor,
        [
            (_name(each.author) or each.outside_author, each.created_at, each.body, str(each.id))
            for each in thread.comments.all()
        ],
        None if thread.resolved_at is None else (_name(thread.resolved_by), thread.resolved_at),
    )


def _filled(name: str, entry: object) -> Filled:
    keys = entry.keys() if isinstance(entry, dict) else None
    if keys not in ({"value"}, {"value", "shown"}):
        raise Unreadable(f"field {name}: {entry!r}")
    value, shown = entry["value"], entry.get("shown")
    texts = isinstance(value, list) and all(isinstance(each, str) for each in value)
    if not (isinstance(value, str) or texts) or not (shown is None or isinstance(shown, str)):
        raise Unreadable(f"field {name}: {entry!r}")
    return Filled(name, value, shown)


def filled_of(file: Node) -> list[Filled]:
    """The values the file's form was filled with, by its fields' full names."""
    return [_filled(name, entry) for name, entry in sorted(_kept(file, "fields").items())]


def fields_in(file: Node) -> dict[str, dict]:
    """The values the file's form was filled with as its room keeps them, each checked."""
    found = _kept(file, "fields")
    for name, entry in found.items():
        _filled(name, entry)
    return found


def _number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _rgb(color: str) -> list[float]:
    return [round(int(color[at : at + 2], 16) / 255, 4) for at in (0, 2, 4)]


def _drawn(pdf: Pdf, box: list[float], content: str, resources: dict | None = None):
    return pdf.make_stream(
        content.encode("ascii"),
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=box,
        Resources=Dictionary(resources or {}),
    )


def _highlight(pdf: Pdf, rects: list[list[float]], color: str, **said) -> Dictionary:
    box = [
        min(rect[0] for rect in rects),
        min(rect[1] for rect in rects),
        max(rect[2] for rect in rects),
        max(rect[3] for rect in rects),
    ]
    red, green, blue = (_number(part) for part in _rgb(color))
    areas = " ".join(
        f"{_number(left)} {_number(bottom)} {_number(right - left)} {_number(top - bottom)} re"
        for left, bottom, right, top in rects
    )
    multiply = {"/ExtGState": Dictionary(M=Dictionary(Type=Name.ExtGState, BM=Name.Multiply))}
    return Dictionary(
        Type=Name.Annot,
        Subtype=Name.Highlight,
        Rect=box,
        QuadPoints=[
            corner
            for left, bottom, right, top in rects
            for corner in (left, top, right, top, left, bottom, right, bottom)
        ],
        C=_rgb(color),
        F=PRINT,
        AP=Dictionary(N=_drawn(pdf, box, f"/M gs {red} {green} {blue} rg {areas} f", multiply)),
        **said,
    )


def _stroke(pdf: Pdf, stroke: Stroke, **said) -> Dictionary:
    xs, ys = stroke.points[0::2], stroke.points[1::2]
    reach = stroke.width / 2 + 1
    box = [min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach]
    red, green, blue = (_number(part) for part in _rgb(stroke.color))
    path = " ".join(
        f"{_number(x)} {_number(y)} {'m' if index == 0 else 'l'}"
        for index, (x, y) in enumerate(zip(xs, ys, strict=True))
    )
    if len(xs) == 1:
        path += f" {_number(xs[0])} {_number(ys[0])} l"
    return Dictionary(
        Type=Name.Annot,
        Subtype=Name.Ink,
        Rect=box,
        InkList=[stroke.points],
        BS=Dictionary(W=stroke.width),
        C=_rgb(stroke.color),
        F=PRINT,
        AP=Dictionary(
            N=_drawn(
                pdf,
                box,
                f"{_number(stroke.width)} w 1 J 1 j {red} {green} {blue} RG {path} S",
            )
        ),
        **said,
    )


def _said(author: str, when: datetime, name: str) -> dict:
    """Who wrote a note, when, and its name, unique on its page."""
    return {
        "T": String(author),
        "M": encode_pdf_date(timezone.localtime(when)),
        "NM": String(name),
    }


def _name(user) -> str:
    return (user.get_full_name() or user.email) if user else ""


def _reply(rect: list[float], opening: Dictionary, **said) -> Dictionary:
    return Dictionary(Type=Name.Annot, Subtype=Name.Text, Rect=rect, IRT=opening, F=NO_VIEW, **said)


def _thread(pdf: Pdf, thread: Discussed) -> list[Dictionary]:
    """The thread's first comment on its text or point, and each later one and its resolution in
    reply to it; only the first shows on the page, as readers list the replies under it."""
    (author, at, body, _), *later = thread.comments
    yellow = palette.highlight(COMMENT)
    said = {**_said(author, at, thread.id), "Contents": String(body)}
    if "rects" in thread.anchor:
        opening = _highlight(pdf, thread.anchor["rects"], yellow, **said)
    else:
        left, top = thread.anchor["at"]
        opening = Dictionary(
            Type=Name.Annot,
            Subtype=Name.Text,
            Name=Name.Comment,
            Rect=[left, top - ICON, left + ICON, top],
            C=_rgb(yellow),
            F=PRINT,
            **said,
        )
    rect = [float(edge) for edge in opening.Rect]
    opening = pdf.make_indirect(opening)
    replies = [
        _reply(rect, opening, Contents=String(body), **_said(author, at, name))
        for author, at, body, name in later
    ]
    if thread.resolved is not None:
        replies.append(
            _reply(
                rect,
                opening,
                StateModel=String("Review"),
                State=String("Completed"),
                **_said(*thread.resolved, f"{thread.id}-resolved"),
            )
        )
    return [opening, *(pdf.make_indirect(reply) for reply in replies)]


def _holders(fields: list[AcroFormField]) -> list[Dictionary]:
    """The dictionaries that keep the fields' values; QPDF gives each button of a radio group as a
    field of its own."""
    found: dict[tuple[int, int], Dictionary] = {}
    for field in fields:
        holder = field.obj if Name.T in field.obj else field.obj.Parent
        found.setdefault(holder.objgen, holder)
    return list(found.values())


def _widgets(holder: Dictionary) -> list[Dictionary]:
    return list(holder.Kids) if Name.Kids in holder else [holder]


def _states(widget: Dictionary) -> list[str]:
    drawn = widget.get(Name.AP, Dictionary()).get(Name.N)
    return list(drawn.keys()) if isinstance(drawn, Dictionary) else []


def _undrawn(holder: Dictionary) -> None:
    """Leaves the reader to draw what QPDF draws wrong: wrapped or combed text, and lists."""
    for widget in _widgets(holder):
        if Name.AP in widget:
            del widget.AP


def _fill_text(pdf: Pdf, fields: list[AcroFormField], filled: Filled) -> None:
    if not isinstance(filled.value, str):
        raise Unreadable(f"field {filled.name}: {filled.value!r}")
    draw = DefaultAppearanceStreamGenerator(pdf, pdf.acroform)
    for field in fields:
        if field.flags & (FormFieldFlag.tx_multiline | FormFieldFlag.tx_comb):
            field.set_value(filled.value, False)
            _undrawn(field.obj)
            continue
        # Drawn as the field's own script shows it, kept as typed, as Acrobat does.
        field.set_value(filled.shown if filled.shown is not None else filled.value, False)
        draw.generate_text(field)
        field.obj.V = String(filled.value)


def _fill_button(fields: list[AcroFormField], filled: Filled) -> None:
    holders = _holders(fields)
    state = f"/{filled.value}"
    known = {each for holder in holders for widget in _widgets(holder) for each in _states(widget)}
    if not isinstance(filled.value, str) or (filled.value != "Off" and state not in known):
        raise Unreadable(f"field {filled.name}: {filled.value!r}")
    for holder in holders:
        holder.V = Name(state)
        for widget in _widgets(holder):
            if _states(widget):
                widget.AS = Name(state) if state in _states(widget) else Name.Off


def _fill_choice(pdf: Pdf, fields: list[AcroFormField], filled: Filled) -> None:
    field = fields[0]
    many = bool(field.flags & FormFieldFlag.ch_multi_select)
    chosen = (
        filled.value if isinstance(filled.value, list) else [filled.value] if filled.value else []
    )
    options = [
        str(option[0] if isinstance(option, Array) else option)
        for option in field.obj.get(Name.Opt, Array())
    ]
    typed = field.flags & FormFieldFlag.ch_edit and isinstance(filled.value, str)
    if isinstance(filled.value, list) != many or not (typed or set(chosen) <= set(options)):
        raise Unreadable(f"field {filled.name}: {filled.value!r}")
    for holder in _holders(fields):
        for key in (Name.V, Name.I):
            if key in holder:
                del holder[key]
        if chosen:
            holder.V = Array([String(each) for each in chosen]) if many else String(chosen[0])
        if many and chosen:
            holder.I = Array(sorted(options.index(each) for each in chosen))
    if field.flags & FormFieldFlag.ch_combo:
        draw = DefaultAppearanceStreamGenerator(pdf, pdf.acroform)
        for each in fields:
            draw.generate_choice(each)
    else:
        for holder in _holders(fields):
            _undrawn(holder)


def _fill(pdf: Pdf, filled: list[Filled]) -> None:
    """Each field's value where the PDF keeps it, which readers draw the field from again."""
    if not filled:
        return
    named: dict[str, list[AcroFormField]] = {}
    for field in pdf.acroform.fields:
        named.setdefault(field.fully_qualified_name, []).append(field)
    for each in filled:
        fields = named.get(each.name)
        if not fields:
            raise Unreadable(f"field {each.name} is not in the file")
        if fields[0].is_text:
            _fill_text(pdf, fields, each)
        elif fields[0].is_checkbox or fields[0].is_radio_button:
            _fill_button(fields, each)
        elif fields[0].is_choice:
            _fill_choice(pdf, fields, each)
        else:
            raise Unreadable(f"field {each.name} takes no value")
    form = pdf.Root.AcroForm
    form.NeedAppearances = True
    # Readers that know XFA prefer it to the fields, so a form with both would show them empty.
    if Name.XFA in form:
        del form.XFA


def written(file: Node) -> IO[bytes] | None:
    """The file with its notes and its form filled in, or None while it has neither."""
    marks = marks_of(file)
    filled = filled_of(file)
    in_order = Comment.objects.select_related("author").order_by("created_at", "id")
    threads = list(
        Thread.objects.filter(file=file)
        .select_related("resolved_by")
        .prefetch_related(Prefetch("comments", queryset=in_order))
        .order_by("created_at", "id")
    )
    if not marks and not threads and not filled:
        return None
    names = {
        user.pk: _name(user)
        for user in get_user_model().everyone.filter(pk__in={mark.by for mark in marks})
    }
    with client.answered(
        "annotate",
        store.path_of(ocr.readable(file.blob).sha256),
        marks=marks,
        filled=filled,
        threads=[_discussed(thread) for thread in threads],
        names=names,
    ) as answer:
        answer.finish()
        result = tempfile.TemporaryFile()
        with answer.files[0].open("rb") as made:
            shutil.copyfileobj(made, result)
    result.seek(0)
    return result


def annotate(
    path: Path,
    marks: list[Highlight | Stroke],
    filled: list[Filled],
    threads: list[Discussed],
    names: dict[int, str],
    out,
) -> None:
    """`written`, in the reader: the file it makes sent."""
    try:
        pdf = pikepdf.open(path)
    except pikepdf.PasswordError:
        raise Locked from None
    with pdf, tempfile.NamedTemporaryFile(suffix=".pdf") as result:
        _fill(pdf, filled)
        annotations: list[tuple[int, list[Dictionary]]] = []
        for mark in marks:
            said = _said(names.get(mark.by, ""), mark.at, mark.id)
            drawn = (
                _highlight(pdf, mark.rects, mark.color, **said)
                if isinstance(mark, Highlight)
                else _stroke(pdf, mark, **said)
            )
            annotations.append((mark.page, [pdf.make_indirect(drawn)]))
        for thread in threads:
            annotations.append((thread.anchor["page"], _thread(pdf, thread)))
        for number, made in annotations:
            if number > len(pdf.pages):
                raise Unreadable(f"a note on page {number} of {len(pdf.pages)}")
            page = pdf.pages[number - 1]
            if "/Annots" not in page.obj:
                page.obj.Annots = pdf.make_indirect(Array())
            for annotation in made:
                annotation.P = page.obj
                page.obj.Annots.append(annotation)
        pdf.save(result, encryption=pdf.is_encrypted)
        result.flush()
        out.file(Path(result.name))
