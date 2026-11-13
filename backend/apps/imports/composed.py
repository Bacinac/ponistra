"""A new PDF file from pages of others: joined, split, turned and put in a new order. The files
it takes from never change. The new one carries the notes and filled-in values of the pages it
holds in its own room; comment threads stay with the file they were made on. The pages are put
together in the reader (D51); the backend sends the files and keeps what comes back."""

import tempfile
import uuid
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import pikepdf
from django.db import transaction
from pikepdf import Array, Dictionary, Name, NameTree, Object, OutlineItem, Pdf, String
from pycrdt import Doc, Map

from apps.access.models import Grant, Role
from apps.blobs import previews, store
from apps.collab.models import Update
from apps.documents.models import Node
from apps.exports import annotated
from apps.reader import client
from apps.search import extraction, ocr


class Forbidden(Exception):
    """The file's own permissions forbid putting its pages together anew."""


class Outside(ValueError):
    """A page the file does not have."""


@dataclass(frozen=True)
class Taken:
    """A page of a file, counted from 1, or every page where None, turned clockwise by quarters."""

    file: Node
    page: int | None
    turn: int = 0


@dataclass(frozen=True)
class _Source:
    """A file the reader takes pages from, by its place among the files sent."""

    at: int
    title: str
    path: Path


@dataclass(frozen=True)
class _Placed:
    file: _Source
    source: Pdf
    index: int


def _opened(file: _Source) -> Pdf:
    try:
        pdf = pikepdf.open(file.path)
    except pikepdf.PasswordError:
        raise annotated.Locked from None
    if not pdf.allow.modify_assembly:
        pdf.close()
        raise Forbidden
    return pdf


def _brought(out: Pdf, source: Pdf, obj: Object) -> Object:
    return out.copy_foreign(obj if obj.is_indirect else source.make_indirect(obj))


def _named(source: Pdf, name: Object) -> Object | None:
    if isinstance(name, Name):
        dests = source.Root.get("/Dests")
        found = dests.get(name) if isinstance(dests, Dictionary) else None
    else:
        names = source.Root.get("/Names")
        tree = names.get("/Dests") if isinstance(names, Dictionary) else None
        found = NameTree(tree).get(str(name)) if isinstance(tree, Dictionary) else None
    return found.get("/D") if isinstance(found, Dictionary) else found


def _aim(source: Pdf, dest: Object | None, action: Object | None) -> Array | None:
    """The explicit destination of a link or bookmark within its own file."""
    if dest is None and isinstance(action, Dictionary) and action.get("/S") == Name.GoTo:
        dest = action.get("/D")
    if isinstance(dest, (Name, String)):
        dest = _named(source, dest)
    if isinstance(dest, Array) and len(dest) > 0 and isinstance(dest[0], Dictionary):
        return dest
    return None


class _Composer:
    def __init__(self, stack: ExitStack):
        self.stack = stack
        self.out = Pdf.new()
        self.sources: dict[int, list[Pdf]] = {}
        self.indices: dict[int, dict[tuple[int, int], int]] = {}
        self.placed: list[_Placed] = []
        self.first: dict[tuple[int, int], int] = {}

    def source(self, file: _Source, copy: int) -> Pdf:
        """The file opened once more for each time a page of it is taken again, so a page taken
        twice is two pages with fields of their own."""
        held = self.sources.setdefault(file.at, [])
        while len(held) <= copy:
            held.append(self.stack.enter_context(_opened(file)))
        return held[copy]

    def index_of(self, source: Pdf, page: Object) -> int | None:
        if id(source) not in self.indices:
            self.indices[id(source)] = {
                each.obj.objgen: index for index, each in enumerate(source.pages)
            }
        return self.indices[id(source)].get(page.objgen)

    def at(self, file: _Source, source: Pdf, dest: Array) -> Array | None:
        """The destination on the new file's page that first shows the page aimed at."""
        index = self.index_of(source, dest[0])
        at = self.first.get((file.at, index)) if index is not None else None
        return None if at is None else Array([self.out.pages[at].obj, *list(dest)[1:]])

    def take(self, taken: list[tuple[_Source, int | None, int]]) -> None:
        copies: Counter[tuple[int, int]] = Counter()
        for file, page, turn in taken:
            count = len(self.source(file, 0).pages)
            indices = range(count) if page is None else [page - 1]
            for index in indices:
                if not 0 <= index < count:
                    raise Outside(f"page {index + 1} of file {file.at}")
                source = self.source(file, copies[(file.at, index)])
                copies[(file.at, index)] += 1
                self.out.pages.append(source.pages[index])
                if turn:
                    self.out.pages[-1].rotate(90 * turn, relative=True)
                self.first.setdefault((file.at, index), len(self.placed))
                self.placed.append(_Placed(file, source, index))

    def annotations(self) -> dict[int, list[tuple[Object, Object]]]:
        """Links aimed again at the new pages, or dropped where their page was left behind, and
        each source's form widgets beside their copies."""
        widgets: dict[int, list[tuple[Object, Object]]] = {}
        for at, placed in enumerate(self.placed):
            page = self.out.pages[at].obj
            ours = page.get("/Annots")
            if ours is None:
                continue
            theirs = list(placed.source.pages[placed.index].obj.get("/Annots") or [])
            kept = Array()
            for their, our in zip(theirs, list(ours), strict=True):
                if not isinstance(their, Dictionary):
                    continue
                subtype = their.get("/Subtype")
                action = their.get("/A")
                goes = "/Dest" in their or (
                    isinstance(action, Dictionary) and action.get("/S") == Name.GoTo
                )
                if subtype == Name.Link and goes:
                    aim = _aim(placed.source, their.get("/Dest"), action)
                    dest = aim and self.at(placed.file, placed.source, aim)
                    if dest is None:
                        continue
                    our.Dest = dest
                    if "/A" in our:
                        del our["/A"]
                if subtype == Name.Widget:
                    widgets.setdefault(id(placed.source), []).append((their, our))
                kept.append(our)
            page.Annots = kept
        return widgets

    def form(self, widgets: dict[int, list[tuple[Object, Object]]]) -> dict[int, dict[str, str]]:
        """The fields of the widgets taken, without the widgets left behind, and each source's
        top field names as renamed where an earlier source already had them."""
        on_page = {our.objgen for pairs in widgets.values() for _, our in pairs}
        fields, names, renamed = Array(), set[str](), {}
        mapped: dict[int, dict[tuple[int, int], Object]] = {}
        co, needs, da = Array(), False, None
        dr: dict[str, dict[str, Object]] = {}
        for _, source in self.opened():
            pairs = widgets.get(id(source), [])
            if not pairs:
                continue
            ours = mapped.setdefault(id(source), {})
            tops: dict[tuple[int, int], Object] = {}
            for their, our in pairs:
                while True:
                    ours[their.objgen] = our
                    if "/Parent" not in their:
                        if "/T" in their:
                            tops.setdefault(their.objgen, our)
                        break
                    their, our = their.Parent, our.Parent
            renamed[id(source)] = {}
            for top in tops.values():
                if not _pruned(top, on_page):
                    continue
                name = str(top.T)
                if name in names:
                    count = 1
                    while f"{name}+{count}" in names:
                        count += 1
                    top.T = String(f"{name}+{count}")
                    renamed[id(source)][name] = f"{name}+{count}"
                else:
                    renamed[id(source)][name] = name
                names.add(str(top.T))
                fields.append(top)
            theirs = source.Root.get("/AcroForm")
            if not isinstance(theirs, Dictionary):
                continue
            kept = _members(fields)
            for field in theirs.get("/CO") or []:
                our = ours.get(field.objgen)
                if our is not None and our.objgen in kept:
                    co.append(our)
            needs = needs or bool(theirs.get("/NeedAppearances"))
            if da is None and "/DA" in theirs:
                da = String(bytes(theirs.DA))
            if isinstance(theirs.get("/DR"), Dictionary):
                for kind, entries in _brought(self.out, source, theirs.DR).items():
                    if isinstance(entries, Dictionary):
                        held = dr.setdefault(kind, {})
                        for key, value in entries.items():
                            held.setdefault(key, value)
        if len(fields):
            form = Dictionary(Fields=fields)
            if len(co):
                form.CO = co
            if needs:
                form.NeedAppearances = True
            if da is not None:
                form.DA = da
            if dr:
                form.DR = Dictionary({kind: Dictionary(held) for kind, held in dr.items()})
            self.out.Root.AcroForm = form
            self.out.acroform.disable_digital_signatures()
        return renamed

    def opened(self) -> list[tuple[_Source, Pdf]]:
        """Every source opened, with its file, in the order its pages were first taken."""
        seen: dict[int, tuple[_Source, Pdf]] = {}
        for placed in self.placed:
            seen.setdefault(id(placed.source), (placed.file, placed.source))
        return list(seen.values())

    def outline(self) -> None:
        """Each file's bookmarks to the pages kept, under the file's name where several give
        pages."""
        files: dict[int, _Source] = {}
        for placed in self.placed:
            files.setdefault(placed.file.at, placed.file)
        made = []
        for file in files.values():
            source = self.sources[file.at][0]
            with source.open_outline() as theirs:
                items = self.items(file, source, theirs.root)
            if len(files) == 1:
                made.extend(items)
                continue
            at = next(at for at, placed in enumerate(self.placed) if placed.file.at == file.at)
            item = OutlineItem(file.title, Array([self.out.pages[at].obj, Name.Fit]))
            item.children.extend(items)
            made.append(item)
        if made:
            with self.out.open_outline() as outline:
                outline.root.extend(made)

    def items(self, file: _Source, source: Pdf, theirs: list[OutlineItem]) -> list[OutlineItem]:
        made = []
        for their in theirs:
            children = self.items(file, source, their.children)
            aim = _aim(source, their.destination, their.action)
            dest = aim and self.at(file, source, aim)
            if dest is None and not children:
                continue
            item = OutlineItem(their.title, dest if dest is not None else children[0].destination)
            item.is_closed = their.is_closed
            item.children.extend(children)
            made.append(item)
        return made

    def layers(self) -> None:
        """The optional content of every source, hidden where it was hidden."""
        groups, off, order, radio, locked = Array(), Array(), Array(), Array(), Array()
        seen = set()
        for _, source in self.opened():
            theirs = source.Root.get("/OCProperties")
            if not isinstance(theirs, Dictionary) or "/OCGs" not in theirs:
                continue
            shown = theirs.get("/D")
            shown = shown if isinstance(shown, Dictionary) else Dictionary()
            all_of = list(theirs.OCGs)
            if shown.get("/BaseState") == Name.OFF:
                lit = {group.objgen for group in shown.get("/ON") or []}
                hidden = [group for group in all_of if group.objgen not in lit]
            else:
                hidden = list(shown.get("/OFF") or [])
            for group in all_of:
                ours = _brought(self.out, source, group)
                if ours.objgen not in seen:
                    seen.add(ours.objgen)
                    groups.append(ours)
            for group in hidden:
                off.append(_brought(self.out, source, group))
            for key, held in (("/Order", order), ("/RBGroups", radio), ("/Locked", locked)):
                if isinstance(shown.get(key), Array):
                    held.extend(_brought(self.out, source, shown[key]))
            if "/Order" not in shown:
                order.extend(_brought(self.out, source, group) for group in all_of)
        if len(groups):
            shown = Dictionary(Order=order, OFF=off)
            if len(radio):
                shown.RBGroups = radio
            if len(locked):
                shown.Locked = locked
            self.out.Root.OCProperties = Dictionary(OCGs=groups, D=shown)


def _pruned(field: Object, on_page: set[tuple[int, int]]) -> bool:
    """Whether the field keeps a widget on a page taken, its kids cut to those that do."""
    kids = field.get("/Kids")
    if kids is None:
        return field.objgen in on_page
    kept = [kid for kid in kids if isinstance(kid, Dictionary) and _pruned(kid, on_page)]
    field.Kids = Array(kept)
    return bool(kept)


def _members(fields: Array) -> set[tuple[int, int]]:
    found = set()
    stack = list(fields)
    while stack:
        field = stack.pop()
        found.add(field.objgen)
        stack.extend(field.get("/Kids") or [])
    return found


def names_of(fields: Array) -> set[str]:
    """The full names of the form's fields that hold values."""
    found = set()

    def walk(field: Object, above: str) -> None:
        name = f"{above}.{field.T}" if above else str(field.T)
        kids = [kid for kid in field.get("/Kids") or [] if "/T" in kid]
        if not kids:
            found.add(name)
        for kid in kids:
            walk(kid, name)

    for field in fields:
        walk(field, "")
    return found


def _room(files: list[Node], made: dict) -> bytes | None:
    """The new file's own room: the notes on each page taken and the values its fields held."""
    held_marks = [annotated.marks_in(file) for file in files]
    held_fields = [annotated.fields_in(file) for file in files]
    marks, filled = {}, {}
    for at, (source, index) in enumerate(made["placed"]):
        for mark in held_marks[source].values():
            if mark["page"] == index + 1:
                marks[str(uuid.uuid4())] = {**mark, "page": at + 1}
    names = set(made["names"])
    for source, tops in made["opened"]:
        for name, entry in held_fields[source].items():
            top, dot, rest = name.partition(".")
            ours = f"{tops[top]}{dot}{rest}" if top in tops else None
            if ours in names:
                filled[ours] = entry
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


def made(paths: list[Path], taken: list, titles: list[str], out) -> dict:
    """Sends the new file of the pages taken, each (file, page, turn) by the file's place among
    `paths`, in the reader; it ends with where each page came from, each source's top field
    names as renamed and the new file's field names that hold values."""
    sources = [_Source(at, *each) for at, each in enumerate(zip(titles, paths, strict=True))]
    with ExitStack() as stack:
        composer = _Composer(stack)
        composer.take([(sources[at], page, turn) for at, page, turn in taken])
        renamed = composer.form(composer.annotations())
        composer.outline()
        composer.layers()
        form = composer.out.Root.get("/AcroForm")
        names = names_of(form.Fields) if isinstance(form, Dictionary) else set()
        composer.out.remove_unreferenced_resources()
        with tempfile.NamedTemporaryFile(suffix=".pdf") as written:
            composer.out.save(written, linearize=True)
            written.flush()
            out.file(Path(written.name))
        return {
            "placed": [(placed.file.at, placed.index) for placed in composer.placed],
            "opened": [(file.at, renamed.get(id(pdf), {})) for file, pdf in composer.opened()],
            "names": sorted(names),
        }


def compose(taken: list[Taken], parent: Node | None, title: str, user) -> Node:
    """The new file, in the folder given or at the top of the user's own documents."""
    files: dict[uuid.UUID, Node] = {}
    for each in taken:
        files.setdefault(each.file.pk, each.file)
    order = list(files)
    pages = [(order.index(each.file.pk), each.page, each.turn) for each in taken]
    paths = [store.path_of(ocr.readable(file.blob).sha256) for file in files.values()]
    titles = [file.title for file in files.values()]
    with client.answered("compose", *paths, taken=pages, titles=titles) as answer:
        room = _room(list(files.values()), answer.finish())
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
