"""A document from PONISTRA's own file (D10), as it was saved. Its tabs keep their exact
states under ids of their own here, so a file can come in beside the document it was saved
from, and the own room's state moves what it keeps by tab to those ids. A user the file names
is the one with the same email here; one without an account here keeps their name on their
comments and proposed changes. Every state and grid is checked against the schema first, as
anything an importer writes is; brought into another document, its tables take ids of their own
there as its tabs do."""

import hashlib
import json
import uuid
import zipfile
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime

from django.db import transaction
from django.db.models import Max
from pycrdt import Doc, Map

from apps.access.models import Grant, Role
from apps.blobs import store
from apps.blobs.models import Blob
from apps.collab import server
from apps.collab.models import Update
from apps.comments.models import Comment, Thread
from apps.content import (
    blocks,
    by_tab,
    grids,
    lists,
    names,
    numbering,
    operations,
    pages,
    people,
    schema,
    slides,
    styles,
    tallies,
)
from apps.content.grids import Laid
from apps.content.models import DocumentBlob, Grid
from apps.content.sheets import Sheets, apart
from apps.documents.models import Node, Tab
from apps.exports import ponx as saved
from apps.search import extraction
from apps.users.models import User
from apps.versions import history
from apps.versions.models import Piece, State, Version, VersionEditor, VersionGrid, VersionTab

from . import create
from .office import bounded
from .reading import Unreadable


class Newer(Unreadable):
    """A file a later PONISTRA saved, in a version of the format this one cannot read."""


Held = dict[str, Laid]


def _read(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError:
        raise Unreadable(f"the file has no {name}") from None


def _json(archive: zipfile.ZipFile, name: str) -> dict:
    try:
        found = json.loads(_read(archive, name))
    except ValueError:
        raise Unreadable(f"{name} is not JSON") from None
    if not isinstance(found, dict):
        raise Unreadable(f"{name} holds no object")
    return found


def _list(value) -> list:
    if not isinstance(value, list):
        raise Unreadable("a list was expected")
    return value


def _moment(value) -> datetime | None:
    try:
        return None if value is None else datetime.fromisoformat(value)
    except TypeError, ValueError:
        raise Unreadable(f"{value!r} is not a time") from None


def _dated(model, pk, value) -> None:
    """When the row was made, as the file says, which its own creation would take."""
    if (moment := _moment(value)) is not None:
        model.objects.filter(pk=pk).update(created_at=moment)


def _id(value) -> str:
    try:
        return str(uuid.UUID(value))
    except AttributeError, TypeError, ValueError:
        raise Unreadable(f"{value!r} is not an id") from None


def _size(value) -> bool:
    return value is None or isinstance(value, int | float) and not isinstance(value, bool)


def _decoded(lines: list, shared: Mapping[str, object], name: str, rows: bool = True) -> list:
    """A version's rows, or its grid's columns, with what they share in place of its keys; as
    they are where one is not a row or column, which reading them then says."""
    try:
        if not rows:
            return [
                grids.unkept_col(line, shared)
                if isinstance(line, list) and len(line) in (2, 3, 4)
                else line
                for line in lines
            ]
        if all(
            isinstance(line, list) and len(line) in (3, 4, 5, 6) and isinstance(line[2], dict)
            for line in lines
        ):
            return grids.unkept_rows(lines, shared)
        return lines
    except AttributeError, KeyError, TypeError:
        raise Unreadable(f"{name} names what no version shares") from None


def _shared(found) -> dict[str, object]:
    """What a version's cells share, by key, each its digest."""
    if not isinstance(found, dict) or any(
        not isinstance(value, list | dict) or grids.digest(value) != key
        for key, value in found.items()
    ):
        raise Unreadable("what a version's cells share is not as it should be")
    return grids.shared_of(found)


def _lines(found, table: str, rows: bool) -> list:
    """A grid's columns, each [id, width], or its rows, each [id, height, cells], and the
    line's look where it has one, once each and as they should be; a row's cells by column id
    and the looks, each checked against the schema."""
    lines = _list(found)
    seen = set()
    for line in lines:
        given = 3 if rows else 2
        if (
            not isinstance(line, list)
            or len(line) not in (given, given + 1, given + 2)
            or not schema.holds("id", line[0])
            or line[0] in seen
            or not _size(line[1])
            or rows
            and not isinstance(line[2], dict)
        ):
            raise Unreadable(f"a line of the grid of {table} is not as it should be")
        seen.add(line[0])
        try:
            if len(line) > given and line[given] is not None:
                if not isinstance(line[given], dict):
                    raise operations.Refused("schema", f"{table} {line[0]}: no look")
                operations.Editing.check_look(table, line[0], line[given])
            if len(line) > given + 1 and line[given + 1] is not True:
                raise operations.Refused("schema", f"{table} {line[0]}: not hidden")
            for col, cell in line[2].items() if rows else []:
                if not schema.holds("id", col):
                    raise Unreadable(f"a cell of the grid of {table} is in no column")
                operations.Editing.check_cell(table, blocks.key_of(line[0], col), cell)
        except operations.Refused as refused:
            raise Unreadable(f"the grid of {table} cannot be taken in: {refused}") from None
    return lines


def _grid(table, found) -> Laid:
    if not schema.holds("id", table) or not isinstance(found, dict):
        raise Unreadable(f"the grid of {table!r} is not as it should be")
    name = found.get("name", "")
    if not isinstance(name, str) or name and not schema.holds("tableName", name):
        raise Unreadable(f"the grid of {table} cannot be named {name!r}")
    cols = _lines(found.get("cols"), table, rows=False)
    rows = _lines(found.get("rows"), table, rows=True)
    laid = grids.from_whole(table, {"name": name, "cols": cols, "rows": rows})
    return _frozen(laid, found.get("frozen"))


def _names(found) -> dict[str, dict]:
    """Defined names by id, each checked against the schema and none twice in one scope."""
    if not isinstance(found, dict) or not all(
        schema.holds("id", key) and schema.holds("definedName", each) for key, each in found.items()
    ):
        raise Unreadable("the defined names are not as they should be")
    scopes = {(each["name"].casefold(), each.get("table")) for each in found.values()}
    if len(scopes) != len(found):
        raise Unreadable("two defined names share a name")
    return {
        key: names.entry(each["name"], each["pieces"], each.get("table"))
        for key, each in found.items()
    }


def _named_once(*held: Held) -> None:
    """Fails where two of the document's tables share a name, ignoring case."""
    found = [laid.name.casefold() for each in held for laid in each.values() if laid.name]
    if len(set(found)) != len(found):
        raise Unreadable("two tables share a name")


def _frozen(laid: Laid, frozen) -> Laid:
    if frozen is not None and (not isinstance(frozen, str) or laid.row(frozen) is None):
        raise Unreadable(f"the grid of {laid.table} freezes no row of its own")
    laid.frozen = frozen
    return laid


class _Reader:
    def __init__(self, archive: zipfile.ZipFile):
        self.archive = archive
        self.described = _json(archive, saved.DOCUMENT)
        found = self.described.get("people")
        if not isinstance(found, dict) or not all(
            isinstance(each, dict) and isinstance(each.get("email"), str) for each in found.values()
        ):
            raise Unreadable("the people are not as they should be")
        emails = {id: each["email"].strip().lower() for id, each in found.items()}
        here = dict(User.objects.filter(email__in=emails.values()).values_list("email", "pk"))
        self.users = {int(id): here.get(email) for id, email in emails.items()}
        self.names = {int(id): each.get("name") or each["email"] for id, each in found.items()}
        self.renaming = any(user != id for id, user in self.users.items())
        self.tabs = [self._tab(each) for each in _list(self.described.get("tabs"))]
        if not self.tabs:
            raise Unreadable("the document has no tab")
        self.versions = _list(self.described.get("versions", []))
        self.defined = _names(_json(archive, saved.NAMES))
        known = [each["id"] for each in self.tabs] + [
            _id(part.get("tab")) for version in self.versions for part in _list(version.get("tabs"))
        ]
        self.ids = {old: str(uuid.uuid4()) for old in known}
        self.tables: dict[str, str] = {}
        self.read: dict[tuple[str, bool], bytes] = {}
        self.pieces: dict[str, list] = {}

    @staticmethod
    def _tab(found) -> dict:
        if not isinstance(found, dict) or not isinstance(found.get("title"), str):
            raise Unreadable("a tab is not as it should be")
        parent = found.get("parent")
        return {
            "id": _id(found.get("id")),
            "parent": None if parent is None else _id(parent),
            "position": found.get("position") if isinstance(found.get("position"), int) else 0,
            "title": found["title"][: Tab._meta.get_field("title").max_length],
        }

    def state(self, name: str, own: bool, held: Held) -> bytes:
        """The state the file keeps under the name, its schema checked with the grids it
        holds, made this installation's: an own room's by the tabs' ids here, each by the
        users here and, apart from the document it was saved from, by its tables' ids."""
        data = _read(self.archive, name)
        doc = Doc()
        try:
            doc.apply_update(data)
            fragments = pages.fragments(doc) if own else [blocks.body_of(doc)]
            sheets = Sheets(held)
            for fragment in fragments:
                if len(fragment.children):
                    operations.Editing(doc, sheets, None, fragment).check_whole()
            if (name, own) in self.read:
                return self.read[name, own]
            if self.tables:
                blocks.rekey_tables(fragments, self.tables)
            if own:
                by_tab.rekeyed(doc, self.ids)
            if self.renaming:
                people.renamed(people.own_roots(doc) if own else people.tab_roots(doc), self.users)
        except (ValueError, TypeError, operations.Refused) as error:
            raise Unreadable(f"{name} cannot be taken in: {error}") from None
        changed = own or self.renaming or self.tables
        self.read[name, own] = doc.get_update() if changed else data
        return self.read[name, own]

    def grids(self, name: str) -> Held:
        """The grids the file keeps under the name, by table, each checked."""
        return {table: _grid(table, found) for table, found in _json(self.archive, name).items()}

    def apart(self, *held: Held) -> None:
        """Gives the tables of the grids ids of their own, the file being taken into another
        document than the one it was saved from."""
        self.tables = {table: blocks.new_id() for each in held for table in each}

    def here(self, held: Held) -> Held:
        """The grids by the ids their tables have here."""
        return {
            self.tables.get(table, table): grids.rekeyed(laid, self.tables)
            for table, laid in held.items()
        }

    def contents(self) -> dict[str, tuple[bytes, Held]]:
        """Each tab's state and grids, by its id in the file."""
        held = {each["id"]: self.grids(saved.tab_grids(each["id"])) for each in self.tabs}
        return {
            id: (self.state(saved.tab_state(id), False, found), self.here(found))
            for id, found in held.items()
        }

    def piece(self, sha256, shared: Mapping[str, object]) -> list:
        """The rows of a version's grid the file keeps under the digest, checked with what
        their cells share, by key, in place of the keys; they stay by key."""
        if not isinstance(sha256, str):
            raise Unreadable("a piece of a version's grid is named by no hash")
        if sha256 not in self.pieces:
            name = saved.kept_piece(sha256)
            try:
                rows = _list(json.loads(_read(self.archive, name)))
            except ValueError:
                raise Unreadable(f"{name} is not JSON") from None
            _lines(_decoded(rows, shared, name), name, rows=True)
            if history.digest(rows) != sha256:
                raise Unreadable(f"{name} holds other rows")
            self.pieces[sha256] = rows
        return self.pieces[sha256]

    def blob(self, sha256) -> Blob:
        if not isinstance(sha256, str):
            raise Unreadable("a file is named by no hash")
        try:
            stream = self.archive.open(saved.file_of(sha256))
        except KeyError:
            raise Unreadable(f"the file has no {saved.file_of(sha256)}") from None
        with stream:
            blob = store.put(stream)
        if blob.sha256 != sha256:
            raise Unreadable(f"{saved.file_of(sha256)} holds other bytes")
        return blob

    def user(self, id) -> int | None:
        return self.users.get(id) if isinstance(id, int) else None

    def name(self, id) -> str:
        return self.names.get(id, "") if isinstance(id, int) else ""


def _checked(archive: zipfile.ZipFile) -> _Reader:
    bounded(archive)
    manifest = _json(archive, saved.MANIFEST)
    if manifest.get("format") != saved.FORMAT or not isinstance(manifest.get("version"), int):
        raise Unreadable("the file is not PONISTRA's")
    if manifest["version"] > saved.VERSION:
        raise Newer
    if manifest["version"] < saved.VERSION:
        raise Unreadable("the file was saved in a form no PONISTRA now reads")
    return _Reader(archive)


@contextmanager
def _opened(source: Blob):
    try:
        archive = zipfile.ZipFile(store.path_of(source.sha256))
    except zipfile.BadZipFile:
        raise Unreadable from None
    with archive:
        yield _checked(archive)


def document(source: Blob, parent: Node | None, title: str, user) -> Node:
    with _opened(source) as reader:
        return _made(reader, parent, title, user)


def copy(document: Node, parent: Node | None, title: str, user) -> Node:
    """The document made again from its own file, its versions left with it."""
    with saved.packed(document) as file, zipfile.ZipFile(file) as archive:
        return _made(_checked(archive), parent, title, user)


def _made(reader: _Reader, parent: Node | None, title: str, user) -> Node:
    described = reader.described
    headed = reader.grids(saved.GRIDS)
    own = reader.state(saved.OWN, True, headed)
    contents = reader.contents()
    _named_once(headed, *(found for _, found in contents.values()))
    locale = described.get("locale")
    original = described.get("original")
    numbers = [version.get("number") for version in reader.versions]
    if len(set(numbers)) != len(numbers):
        raise Unreadable("two versions have one number")
    with transaction.atomic():
        node = Node.objects.create(
            parent=parent,
            kind=Node.Kind.DOCUMENT,
            title=title,
            locale=locale if locale in Node.Locale.values else Node.Locale.HR,
            source=None if original is None else reader.blob(original),
            created_by=user,
            updated_by=user,
        )
        if parent is None:
            Grant.objects.create(node=node, user=user, role=Role.OWN, created_by=user)
        Update.objects.create(document=node, room=node.room, data=own)
        for laid in headed.values():
            grids.put(node, None, laid)
        _tabs(reader, node, contents, 0)
        names.put(node, reader.defined)
        for version in reader.versions:
            _kept(reader, node, version)
    return node


def into(node: Node, source: Blob, title: str, user) -> tuple[Tab, dict]:
    """The file's tabs after the document's last, as any file's are, the first named after the
    file where it has no name. The document keeps its theme, and a style, list format or slide
    layout it has keeps its look; a tab laid out unlike the document's pages keeps pages of its
    own. A table named as one of the document's is named as its copy would be, and the file's
    names join the document's. The file's versions stay with the document it was saved from."""
    with _opened(source) as reader:
        headed = reader.grids(saved.GRIDS)
        held = [reader.grids(saved.tab_grids(each["id"])) for each in reader.tabs]
        reader.apart(headed, *held)
        theirs = _doc(reader.state(saved.OWN, True, headed))
        headed = reader.here(headed)
        contents = reader.contents()
        brought = [
            *headed.values(),
            *(laid for _, found in contents.values() for laid in found.values()),
        ]
        defined = names.rekeyed(reader.defined, reader.tables)

        def write() -> dict[str, Tab]:
            with transaction.atomic():
                apart(brought, Grid.objects.filter(document=node).values_list("name", flat=True))
                last = node.tabs.filter(parent=None).aggregate(Max("position"))["position__max"]
                tabs = _tabs(reader, node, contents, 0 if last is None else last + 1, title)
                tables = [laid.table for laid in brought]
                names.put(node, names.joined(names.of_document(node), defined, tables))
                history.contributed(node.pk, user.pk)
            return tabs

        tabs = server.rewrite(node.pk, write)
    read = {
        str(tab.pk): blocks.read(_doc(contents[old][0]), contents[old][1])
        for old, tab in tabs.items()
    }
    server.change(node.room, lambda own, sheets: _joined(own, sheets, theirs, headed, read))
    server.announce(node.room, "tabs")
    lost = {"versions": len(reader.versions)} if reader.versions else {}
    first = next(tab for tab in tabs.values() if tab.parent_id is None)
    return first, {"fonts": [], "lost": lost, "accepted": 0}


def _doc(state: bytes) -> Doc:
    doc = Doc()
    doc.apply_update(state)
    return doc


def _tabs(
    reader: _Reader,
    node: Node,
    contents: dict[str, tuple[bytes, Held]],
    start: int,
    named: str = "",
) -> dict[str, Tab]:
    """The file's tabs in the document, the top ones from the position on, with their grids,
    the images and PDFs they show and their comments."""
    made: dict[str, Tab] = {}
    for each in reader.tabs:
        if each["parent"] is not None and each["parent"] not in made:
            raise Unreadable("a tab comes before its parent")
        top = each["parent"] is None
        tab = Tab.objects.create(
            id=reader.ids[each["id"]],
            document=node,
            parent=made.get(each["parent"]),
            position=start + each["position"] if top else each["position"],
            title=each["title"] or (named if top and not made else ""),
        )
        state, held = contents[each["id"]]
        Update.objects.create(document=node, tab=tab, room=tab.room, data=state)
        for laid in held.values():
            grids.put(node, str(tab.pk), laid)
        made[each["id"]] = tab
    for sha256 in _list(reader.described.get("shown", [])):
        DocumentBlob.objects.get_or_create(document=node, blob=reader.blob(sha256))
        extraction.wake()
    for thread in _list(reader.described.get("threads", [])):
        _discussed(reader, made, thread)
    return made


def _joined(
    own: Doc, sheets: Sheets, theirs: Doc, headed: Held, contents: dict[str, list[blocks.Block]]
) -> None:
    found = own.get(styles.STYLES, type=Map)
    for id, style in theirs.get(styles.STYLES, type=Map).items():
        if id not in found and isinstance(style, Map):
            found[id] = Map(style.to_py())
    had = lists.read(own)
    lists.write(own, {id: each for id, each in lists.read(theirs).items() if id not in had})
    template = slides.template_of(theirs)
    known = {layout["id"] for layout in slides.template_of(own).layouts}
    added = [layout for layout in template.layouts if layout["id"] not in known]
    if added and not template.built_in:
        size = {"width": template.width, "height": template.height}
        slides.join(own, {**size, "layouts": added})
    by_tab.carried(theirs, own, list(contents), (pages.TABS, pages.COUNTS))
    for fragment in pages.fragments(own):
        for table in blocks.table_ids(fragment):
            if table in headed and table not in sheets:
                sheets.make(headed[table])
    shared = create.laid_out(*pages.read(own, sheets.grids()))
    counted = numbering.styles_of(own)
    for tab, content in contents.items():
        page, parts = pages.read(theirs, headed, tab)
        if not pages.owns(theirs, tab) and create.laid_out(page, parts) != shared:
            pages.write(own, sheets, page, parts, tab=tab)
        tallies.keep(own, tab, content, counted)


def _discussed(reader: _Reader, tabs: dict[str, Tab], found) -> None:
    if not isinstance(found, dict) or _id(found.get("tab")) not in tabs:
        raise Unreadable("a comment is on no tab")
    if not isinstance(found.get("anchor"), dict):
        raise Unreadable("a comment has no place")
    thread = Thread.objects.create(
        tab=tabs[_id(found["tab"])],
        anchor=found["anchor"],
        quote=str(found.get("quote") or ""),
        resolved_at=_moment(found.get("resolved_at")),
        resolved_by_id=reader.user(found.get("resolved_by")),
    )
    _dated(Thread, thread.pk, found.get("created_at"))
    for each in _list(found.get("comments")):
        if not isinstance(each, dict) or not isinstance(each.get("body"), str):
            raise Unreadable("a comment is not as it should be")
        author = reader.user(each.get("author"))
        outside = each.get("outside_author") or ("" if author else reader.name(each.get("author")))
        comment = Comment.objects.create(
            thread=thread,
            author_id=author,
            outside_author=str(outside)[: Comment._meta.get_field("outside_author").max_length],
            body=each["body"],
            edited_at=_moment(each.get("edited_at")),
        )
        _dated(Comment, comment.pk, each.get("created_at"))


def _kept(reader: _Reader, node: Node, found) -> None:
    if not isinstance(found, dict) or not isinstance(found.get("number"), int):
        raise Unreadable("a version is not as it should be")
    created, checked = _moment(found.get("created_at")), _moment(found.get("checked_at"))
    if created is None or checked is None:
        raise Unreadable("a version has no time")
    restored = found.get("restored_from")
    shared = _shared(found.get("shared"))
    held = _version_grids(reader, found.get("grids"), shared)

    def state(sha256, own: bool, tab: str | None) -> State:
        if not isinstance(sha256, str):
            raise Unreadable("a version's state is named by no hash")
        laids = {table: laid for (at, table), (laid, _) in held.items() if at == tab}
        data = reader.state(saved.kept_state(sha256), own, laids)
        digest = hashlib.sha256(data).hexdigest()
        return State.objects.get_or_create(document=node, sha256=digest, defaults={"data": data})[0]

    version = Version.objects.create(
        document=node,
        number=found["number"],
        title=str(found.get("title") or ""),
        created_at=created,
        checked_at=checked,
        restored_from=restored if isinstance(restored, int) else None,
        state=state(found.get("state"), own=True, tab=None),
        names=_names(found.get("names")),
        shared=shared,
    )
    editors = {reader.user(id) for id in _list(found.get("editors", []))}
    VersionEditor.objects.bulk_create(
        [VersionEditor(version=version, user_id=user) for user in sorted(editors - {None})]
    )
    for part in _list(found.get("tabs")):
        if not isinstance(part, dict):
            raise Unreadable("a version's tab is not as it should be")
        parent = part.get("parent")
        VersionTab.objects.create(
            version=version,
            tab=reader.ids[_id(part.get("tab"))],
            parent=None if parent is None else reader.ids.get(_id(parent)),
            position=part.get("position") if isinstance(part.get("position"), int) else 0,
            title=str(part.get("title") or ""),
            state=state(part.get("state"), own=False, tab=_id(part.get("tab"))),
        )
    pieces = {sha256 for _, digests in held.values() for sha256 in digests}
    stored = set(
        Piece.objects.filter(document=node, sha256__in=pieces).values_list("sha256", flat=True)
    )
    Piece.objects.bulk_create(
        [
            Piece(document=node, sha256=sha256, rows=reader.piece(sha256, shared))
            for sha256 in sorted(pieces - stored)
        ]
    )
    VersionGrid.objects.bulk_create(
        [
            VersionGrid(
                version=version,
                tab=None if tab is None else reader.ids[tab],
                table=table,
                name=laid.name,
                cols=grids.kept_cols(laid, {}),
                frozen=laid.frozen or "",
                pieces=digests,
            )
            for (tab, table), (laid, digests) in held.items()
        ]
    )
    history.settle(version)


def _version_grids(
    reader: _Reader, found, shared: Mapping[str, object]
) -> dict[tuple[str | None, str], tuple[Laid, list]]:
    """A version's grids by its tab in the file, or none for the headers' and footers', and
    table: each with the digests of its rows' pieces."""
    held = {}
    for part in _list(found):
        if not isinstance(part, dict):
            raise Unreadable("a version's grid is not as it should be")
        tab = part.get("tab")
        tab = None if tab is None else _id(tab)
        if tab is not None and tab not in reader.ids:
            raise Unreadable("a version's grid is in no tab")
        table, digests = part.get("table"), _list(part.get("pieces"))
        rows = grids.unkept_rows(
            [row for sha256 in digests for row in reader.piece(sha256, shared)], shared
        )
        if len({row[0] for row in rows}) != len(rows):
            raise Unreadable(f"a row of the grid of {table} comes twice")
        cols = _decoded(_list(part.get("cols")), shared, f"the grid of {table}", rows=False)
        whole = {"name": part.get("name", ""), "cols": cols, "rows": []}
        laid = _grid(table, whole)
        laid.rows = grids.from_whole(table, {"rows": rows}).rows
        _frozen(laid, part.get("frozen"))
        if (tab, table) in held:
            raise Unreadable(f"a version keeps the grid of {table} twice")
        held[tab, table] = (laid, digests)
    return held
