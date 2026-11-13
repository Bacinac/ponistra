import logging
import mimetypes
import re
from collections.abc import Iterable
from datetime import datetime

from django.db import transaction
from django.db.models import Case, F, IntegerField, Value, When, prefetch_related_objects
from django.db.models.expressions import RawSQL
from django.db.models.functions import Collate
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from pycrdt import Doc

from apps.access import log as access_log
from apps.access import rights
from apps.access.models import Grant, Role
from apps.blobs import edits, previews, store, text
from apps.blobs.models import Blob
from apps.blobs.views import serve
from apps.collab import server
from apps.collab.models import Update
from apps.collab.server import recompute, revoke
from apps.content import operations, styles
from apps.core.api import Refused, api, body, optional_id
from apps.exports import macros
from apps.imports.formats import EXTENSIONS, read_as
from apps.retention import kept as retention
from apps.search import extraction, ocr
from apps.users.views import describe as describe_user
from apps.versions import history
from apps.versions.models import FileVersion

from . import board_data, boards, links
from .models import Favourite, Node, Tab
from .tabs import close, renumbered, tabs_changed

log = logging.getLogger(__name__)

FOLDERS_FIRST = Case(
    When(kind=Node.Kind.FOLDER, then=Value(0)), default=Value(1), output_field=IntegerField()
)
BY_TITLE = Collate("title", "hr-x-icu")
LAID_OUT = (F("position").asc(nulls_last=True), BY_TITLE)
MOST_COLUMNS = 6


def describe(node: Node) -> dict:
    return {
        "id": node.id,
        "parent": node.parent_id,
        "kind": node.kind,
        "title": node.title,
        "locale": node.locale,
        "updated_at": node.updated_at,
        "updated_by": node.updated_by and describe_user(node.updated_by),
        "size": node.blob.size if node.blob else node.content_size,
        "holds": node.holds or None,
        "media_type": node.blob and node.blob.media_type,
        "picture": picture_of(node),
        "extension": extension_of(node) if node.kind == Node.Kind.FILE else None,
        "href": node.href or None,
        "description": node.description,
        "trashed_at": node.trashed_at,
        "original": read_as(node.source.media_type) if node.source_id else None,
        "origin": node.source_id
        and {"extension": EXTENSIONS[node.source.media_type], "size": node.source.size},
        "macros": macros.KINDS.get(node.source.media_type) if node.source_id else None,
        "imported": node.imported,
        "company": node.company,
        "confined": node.confined,
        "notes": node.notes,
        "links": node.links,
        "boards": node.boards,
        "columns": node.columns,
        "agent_folder": node.agent_folder or None,
    }


def described(nodes: list[Node]) -> list[dict]:
    prefetch_related_objects(nodes, "updated_by", "blob__preview", "edited__preview", "source")
    return [describe(node) for node in nodes]


def picture_of(node: Node) -> str | None:
    """The id of the picture a glance at the file shows, of its edited copy where it has one,
    once it is drawn; a link's, its site's icon once its page is read."""
    if node.kind == Node.Kind.LINK:
        return node.icon_id
    shown = node.edited or node.blob
    preview = shown and getattr(shown, "preview", None)
    return preview and preview.picture_id


def describe_tab(tab: Tab) -> dict:
    return {
        "id": tab.id,
        "parent": tab.parent_id,
        "title": tab.title,
        "position": tab.position,
        "room": tab.room,
    }


def live(user, pk, needs: Role = Role.READ) -> tuple[Node, rights.Reach]:
    node = Node.objects.filter(pk=pk).first()
    ancestry = node.ancestry() if node else []
    if node is None or not node.is_live(ancestry):
        raise Refused(404, "not_found")
    return node, rights.require(user, ancestry, needs)


def folder(user, pk, needs: Role = Role.READ) -> tuple[Node | None, rights.Reach | None]:
    """A folder, or None for the top of the user's own documents, where anyone but a visitor
    creates."""
    if pk is None:
        if user.visitor:
            raise Refused(403, "visitors_not_allowed")
        return None, None
    node, reach = live(user, pk, needs)
    if node.kind != Node.Kind.FOLDER:
        raise Refused(400, "not_a_folder")
    return node, reach


def beside(user, node: Node) -> Node | None:
    """The node's folder where the user may add to it, else the top of their own documents."""
    parent = node.parent
    if parent is not None:
        above = rights.reach(user, node.ancestry()[:-1])
        if not rights.covers(above.role, Role.EDIT):
            parent = None
    if parent is None and user.visitor:
        raise Refused(403, "visitors_not_allowed")
    return parent


def kept_in(user, nodes: Iterable[Node], place: Node | None) -> Node | None:
    """The folder what is made from these nodes goes to, refused where it would take one of them
    out of every folder that keeps it in the browser."""
    into = place.ancestry() if place else []
    if any(rights.reach(user, node.ancestry()).escapes(into) for node in nodes):
        raise Refused(403, "confined")
    return place


def downloadable(reach: rights.Reach) -> None:
    if reach.confined:
        raise Refused(403, "confined")


def taken_out(user, node: Node, reach: rights.Reach, format: str) -> None:
    """Logs the node saved outside PONISTRA, refused where a folder keeps it in the browser."""
    downloadable(reach)
    access_log.downloaded(user, node, format)


def laid_out(node: Node) -> None:
    """Refuses a change to a company folder itself, which only the administrator lays out."""
    if node.company:
        raise Refused(403, "company_folder")


def trashed(user, pk, needs: Role) -> tuple[Node, rights.Reach]:
    node = Node.objects.filter(pk=pk, trashed_at__isnull=False).first()
    if node is None:
        raise Refused(404, "not_found")
    return node, rights.require(user, node.ancestry(), needs)


def live_document(user, pk, needs: Role = Role.READ) -> Node:
    node, _ = live(user, pk, needs)
    if node.kind != Node.Kind.DOCUMENT:
        raise Refused(400, "not_a_document")
    return node


def live_tab(user, pk, needs: Role) -> Tab:
    tab = Tab.objects.select_related("document").filter(pk=pk).first()
    if tab is None:
        raise Refused(404, "not_found")
    live(user, tab.document_id, needs)
    return tab


def placed(reach: rights.Reach) -> dict:
    """Where the user finds a node: the path they can see, from their own documents
    or from what is shared with them, and their role there."""
    return {
        "path": described(reach.path),
        "root": reach.root,
        "role": reach.role,
        "confined": reach.confined,
    }


def along(reach: rights.Reach) -> dict:
    """Where a listing beside other places shows a node: the folders above it on the
    user's path, a place of the user's own among them, and the root that path starts from."""
    return {
        "path": [
            {
                "id": above.pk,
                "kind": above.kind,
                "title": above.title,
                "notes": above.notes,
                "links": above.links,
                "boards": above.boards,
            }
            for above in reach.path[:-1]
        ],
        "root": reach.root,
    }


def listing(request, chains: list[list[Node]]) -> list[dict]:
    nodes = [chain[-1] for chain in chains]
    return [
        {**node, **access}
        for node, access in zip(described(nodes), rights.listed(request.user, chains), strict=True)
    ]


def title_of(data: dict, required: bool = True) -> str:
    title = str(data.get("title", "")).strip()
    if (required and not title) or len(title) > 200:
        raise Refused(400, "invalid_title")
    return title


EXTENSION = re.compile(r"[a-z0-9]{1,10}")
# As much of a text file as the browser is given to show; the rest is downloaded.
TEXT_SHOWN = 5 * 1024 * 1024


def extension_given(data: dict) -> str:
    extension = data.get("extension", "")
    if not isinstance(extension, str) or (extension and not EXTENSION.fullmatch(extension)):
        raise Refused(400, "invalid_extension")
    return extension


def modified_of(data: dict) -> datetime | None:
    """When the file a node is made from was last changed, as the client's disk tells."""
    given = data.get("modified")
    if given is None:
        return None
    try:
        modified = datetime.fromisoformat(given) if isinstance(given, str) else None
    except ValueError:
        modified = None
    if modified is None or modified.tzinfo is None:
        raise Refused(400, "invalid_modified")
    return modified


def dated(node: Node, modified: datetime | None) -> Node:
    """The node last changed when its file was; a clock ahead of the server's is read as now."""
    if modified is not None:
        modified = min(modified, timezone.now())
        Node.objects.filter(pk=node.pk).update(updated_at=modified)
        node.updated_at = modified
    return node


def file_of(data: dict) -> Blob | None:
    sha256 = data.get("blob")
    if data.get("kind") != Node.Kind.FILE:
        if sha256 is not None:
            raise Refused(400, "unexpected_file")
        return None
    blob = Blob.objects.filter(pk=sha256).first() if isinstance(sha256, str) else None
    if blob is None:
        raise Refused(400, "unknown_file")
    return blob


@api("GET", "POST", visitors=True)
def nodes(request):
    if request.method == "GET":
        parent, reach = folder(request.user, optional_id(request.GET.get("parent")))
        if parent is None:
            children = rights.mine(request.user)
            place = {"path": [], "root": "mine", "role": Role.OWN, "confined": False}
        else:
            children = Node.objects.filter(parent=parent, trashed_at=None)
            place = placed(reach)
        above = reach.ancestry if reach else []
        chains = [[*above, child] for child in children.order_by(FOLDERS_FIRST, BY_TITLE)]
        return JsonResponse(
            {"folder": parent and describe(parent), **place, "children": listing(request, chains)}
        )
    data = body(request)
    kind = data.get("kind")
    if kind not in Node.Kind.values:
        raise Refused(400, "invalid_kind")
    blob = file_of(data)
    near = optional_id(data.get("beside"))
    reach = None
    if near is not None:
        parent = beside(request.user, live(request.user, near)[0])
    else:
        parent, reach = folder(request.user, optional_id(data.get("parent")), Role.EDIT)
    extension = extension_given(data) if kind == Node.Kind.FILE else ""
    modified = modified_of(data) if kind == Node.Kind.FILE else None
    if kind == Node.Kind.LINK:
        address, title = links.address_of(data), title_of(data, required=False)
        node = new_link(parent, address, title, request.user)
        links.wake()
    else:
        node = dated(created(parent, kind, title_of(data), blob, request.user, extension), modified)
    if reach and reach.ancestry[0].links:
        arranged(parent, [node], None)
    if kind == Node.Kind.FILE:
        extraction.wake()
        previews.wake()
    return JsonResponse(describe(node), status=201)


def created(
    parent: Node | None,
    kind: str,
    title: str,
    blob: Blob | None,
    user,
    extension: str = "",
    href: str = "",
) -> Node:
    """A new node in the folder, or owned by the user at the top of their documents; a
    document with its styles and one empty tab."""
    with transaction.atomic():
        node = Node.objects.create(
            parent=parent,
            kind=kind,
            title=title,
            blob=blob,
            extension=extension,
            href=href,
            created_by=user,
            updated_by=user,
        )
        if parent is None:
            Grant.objects.create(node=node, user=user, role=Role.OWN, created_by=user)
        if kind == Node.Kind.DOCUMENT:
            Update.objects.create(document=node, room=node.room, data=styles.template())
            Tab.objects.create(document=node, position=0)
    return node


def new_link(parent: Node | None, href: str, title: str, user) -> Node:
    """A link in the folder, under the title given or else the page's own once it is read."""
    node = created(parent, Node.Kind.LINK, title or links.site_of(href), None, user, href=href)
    if not title:
        node.follows_text = True
        node.save(update_fields=["follows_text"])
    return node


def _folders_first(chains: list[list[Node]]) -> list[list[Node]]:
    return sorted(
        chains, key=lambda chain: (chain[-1].kind != Node.Kind.FOLDER, chain[-1].title.casefold())
    )


@api("GET", visitors=True)
def shared(request):
    """What others gave the user, or with `by=me` what the user gave others."""
    if request.GET.get("by") == "me":
        found = rights.shared_by(request.user)
    else:
        found = [chain for chain in rights.shared_with(request.user) if not chain[0].boards]
    return JsonResponse({"children": listing(request, _folders_first(found))})


@api("GET")
def company(request):
    chains = [[node] for node in rights.company(request.user).order_by(BY_TITLE)]
    return JsonResponse({"children": listing(request, chains)})


RECENT = 10


@api("GET", visitors=True)
def recent(request):
    """The documents and files the user can read, the latest changed first."""
    readable, params = rights.readable(request.user)
    found = list(
        Node.objects.filter(pk__in=RawSQL(readable, params))
        .exclude(kind__in=(Node.Kind.FOLDER, Node.Kind.LINK))
        .order_by("-updated_at")[:RECENT]
    )
    reaches = rights.reaches(request.user, [node.pk for node in found])
    return JsonResponse(
        {"items": [{**node, **along(reaches[node["id"]])} for node in described(found)]}
    )


@api("GET", "POST", visitors=True)
def favourites(request):
    """What the user keeps at hand of what they can read, folders first; what went to the trash or
    is no longer shared with them returns with it. A POST marks the nodes, or no longer."""
    if request.method == "POST":
        data = body(request)
        wanted = data.get("favourite")
        if not isinstance(wanted, bool):
            raise Refused(400, "invalid_favourite")
        nodes = [node for node, _ in live_nodes(request.user, data, Role.READ)]
        if wanted:
            Favourite.objects.bulk_create(
                [Favourite(user=request.user, node=node) for node in nodes],
                ignore_conflicts=True,
            )
        else:
            Favourite.objects.filter(user=request.user, node__in=nodes).delete()
        return HttpResponse(status=204)
    readable, params = rights.readable(request.user)
    found = Node.objects.filter(pk__in=RawSQL(readable, params), favourites__user=request.user)
    reaches = rights.reaches(request.user, found.values_list("pk", flat=True))
    chains = _folders_first([reach.ancestry for reach in reaches.values()])
    return JsonResponse(
        {
            "children": [
                {**node, "kept": reaches[node["id"]].confined, **along(reaches[node["id"]])}
                for node in listing(request, chains)
            ]
        }
    )


@api("GET", "PATCH", visitors=True)
def node(request, pk):
    needs = Role.EDIT if request.method == "PATCH" else Role.READ
    node, reach = live(request.user, pk, needs)
    if request.method == "PATCH":
        data = body(request)
        if "title" in data:
            laid_out(node)
            node.title = title_of(data)
            node.follows_text = False
        if "href" in data:
            if node.kind != Node.Kind.LINK:
                raise Refused(400, "invalid_href")
            href = links.address_of(data)
            if href != node.href:
                node.href, node.description, node.icon, node.read_at = href, "", None, None
                if node.follows_text:
                    node.title = links.site_of(href)
        if "icon" in data:
            if node.kind != Node.Kind.LINK:
                raise Refused(400, "invalid_icon")
            if data["icon"] is None:
                node.icon, node.read_at = None, None
            else:
                node.icon = links.given_icon(data["icon"])
        if "columns" in data:
            columns = data["columns"]
            if node.kind != Node.Kind.FOLDER or not (
                columns is None or (type(columns) is int and 1 <= columns <= MOST_COLUMNS)
            ):
                raise Refused(400, "invalid_columns")
            node.columns = columns
        if "confined" in data:
            if node.kind != Node.Kind.FOLDER or not isinstance(data["confined"], bool):
                raise Refused(400, "invalid_confined")
            if reach.role != Role.OWN:
                raise Refused(403, "forbidden")
            node.confined = data["confined"]
        if "agent_folder" in data:
            node.agent_folder = boards.agent_folder_of(request.user, node, data["agent_folder"])
        relocated = "locale" in data and data["locale"] != node.locale
        if relocated:
            if node.kind != Node.Kind.DOCUMENT or data["locale"] not in Node.Locale.values:
                raise Refused(400, "invalid_locale")
            node.locale = data["locale"]
        if data.keys() == {"agent_folder"}:
            node.save(update_fields=["agent_folder"])
        else:
            node.updated_by = request.user
            node.save()
        if node.kind == Node.Kind.LINK and node.read_at is None:
            links.wake()
        if relocated:
            transaction.on_commit(lambda: recompute(node.pk, node.locale))
        reach = rights.reach(request.user, node.ancestry())
    elif node.kind != Node.Kind.FOLDER:
        access_log.opened(request.user, node)
    return JsonResponse(
        {
            "node": describe(node),
            **placed(reach),
            "room": node.room,
            "tabs": [describe_tab(tab) for tab in node.tabs_in_order()],
            "pdf": ocr.described(node.blob) if node.is_pdf else None,
        }
    )


def shown(room) -> bytes:
    """The room's state as its clients have it, which a live room's store writes only after, without
    the content deleted from it, as history.state_of gives it."""
    doc = Doc()
    doc.apply_update(server.read(room, lambda live: live.get_update()))
    return doc.get_update()


@api("GET", visitors=True)
def node_state(request, pk):
    document = live_document(request.user, pk)
    return HttpResponse(shown(document.room), content_type="application/octet-stream")


@api("GET", visitors=True)
def tab_state(request, pk):
    tab = live_tab(request.user, pk, Role.READ)
    return HttpResponse(shown(tab.room), content_type="application/octet-stream")


def live_nodes(user, data: dict, needs: Role) -> list[tuple[Node, rights.Reach]]:
    ids = data.get("nodes")
    if not isinstance(ids, list) or not ids or not all(isinstance(pk, str) for pk in ids):
        raise Refused(400, "invalid_nodes")
    return [live(user, optional_id(pk), needs) for pk in dict.fromkeys(ids)]


def arranged(parent: Node | None, moving: list[Node], before: Node | None) -> None:
    """The nodes moved among the parent's children, before the one given or after them all,
    each child numbered where it now stands."""
    moved = {node.pk for node in moving}
    order = [
        child
        for child in Node.objects.filter(parent=parent, trashed_at=None).order_by(*LAID_OUT)
        if child.pk not in moved
    ]
    at = next((index for index, child in enumerate(order) if child == before), len(order))
    order[at:at] = moving
    for position, child in enumerate(order):
        child.position = position
    Node.objects.bulk_update(order, ["position"])


@api("POST", visitors=True)
def move(request):
    data = body(request)
    moving = live_nodes(request.user, data, Role.EDIT)
    parent, target = folder(request.user, optional_id(data.get("parent")), Role.EDIT)
    before = None
    if data.get("before") is not None:
        before = Node.objects.filter(
            pk=optional_id(data["before"]), parent=parent, trashed_at=None
        ).first()
        if before is None:
            raise Refused(400, "before_gone")
    moved_into(moving, parent, target, request.user, before, "before" in data)
    return JsonResponse({"nodes": described([node for node, _ in moving])})


def moved_into(
    moving: list[tuple[Node, rights.Reach]],
    parent: Node | None,
    target: rights.Reach | None,
    user,
    before: Node | None = None,
    laying: bool = False,
) -> None:
    """The nodes moved into the folder; laying them out, before the child given or else after
    them all, in the order given, else after what was laid out. In the folder of links, what is
    moved in without a place stands after them all."""
    into = target.ancestry if target else []
    above = {ancestor.pk for ancestor in into}
    for node, reach in moving:
        laid_out(node)
        if node.pk in above:
            raise Refused(400, "cycle")
        if node.notes and parent is not None:
            raise Refused(400, "notes_at_top")
        if node.links and parent is not None:
            raise Refused(400, "links_at_top")
        if node.boards and parent is not None:
            raise Refused(400, "boards_at_top")
        if into and into[0].boards and not boards.is_board(node):
            raise Refused(400, "not_a_board")
        if reach.escapes(into, moved=True):
            raise Refused(403, "confined")
        # Only an owner may change who sees a node; an editor moves it inside the
        # folder their editing comes from, where the audience can only grow.
        if reach.role != Role.OWN and reach.first(Role.EDIT).pk not in above:
            raise Refused(403, "move_out")
    with transaction.atomic():
        for node, reach in moving:
            if node.parent_id != (parent and parent.pk):
                node.position = None
            node.parent = parent
            node.updated_by = user
            node.save()
            if parent is None:
                rights.keep_owners(node, reach.ancestry, user)
        if laying or (into and into[0].links):
            arranged(parent, [node for node, _ in moving], before)
    revoke()


@api("POST", visitors=True)
def tabs(request, pk):
    document = live_document(request.user, pk, Role.EDIT)
    data = body(request)
    parent = None
    if (parent_id := optional_id(data.get("parent"))) is not None:
        parent = document.tabs.filter(pk=parent_id).first()
        if parent is None:
            raise Refused(400, "invalid_parent")
    tab = operations.open_tab(document, title_of(data, required=False), parent)
    history.contributed(document.pk, request.user.pk)
    tabs_changed(document)
    return JsonResponse(describe_tab(tab), status=201)


@api("PATCH", "DELETE", visitors=True)
def tab(request, pk):
    tab = live_tab(request.user, pk, Role.EDIT)
    if request.method == "DELETE":
        others = tab.document.tabs.filter(parent=None).exclude(pk=tab.pk)
        if tab.parent_id is None and not others.exists():
            raise Refused(400, "last_tab")
        close(tab, request.user)
        return HttpResponse(status=204)
    data = body(request)
    if "title" in data:
        tab.title = title_of(data, required=False)
        tab.save(update_fields=["title"])
    if "position" in data:
        place(tab, optional_id(data.get("parent")), data["position"])
    history.contributed(tab.document.pk, request.user.pk)
    tabs_changed(tab.document)
    return JsonResponse(describe_tab(tab))


def place(tab: Tab, parent_id, position) -> None:
    """Puts the tab at `position` among the other children of `parent_id`, numbering
    the row it leaves and the row it joins from 0."""
    if type(position) is not int or position < 0:
        raise Refused(400, "invalid_position")
    with transaction.atomic():
        tabs = {
            each.pk: each for each in tab.document.tabs.select_for_update().order_by("position")
        }
        if parent_id is not None and parent_id not in tabs:
            raise Refused(400, "invalid_parent")
        above = parent_id
        while above is not None:
            if above == tab.pk:
                raise Refused(400, "tab_cycle")
            above = tabs[above].parent_id
        moving = tabs[tab.pk]
        left = [each for each in tabs.values() if each.parent_id == moving.parent_id]
        joined = [each for each in tabs.values() if each.parent_id == parent_id]
        left.remove(moving)
        if moving in joined:
            joined.remove(moving)
        joined.insert(min(position, len(joined)), moving)
        moving.parent_id = parent_id
        for row in (left, joined):
            for index, each in enumerate(row):
                each.position = index
        Tab.objects.bulk_update(tabs.values(), ["parent", "position"])
        renumbered(tab.document)
    tab.parent_id, tab.position = moving.parent_id, moving.position


def live_file(user, pk) -> tuple[Node, rights.Reach]:
    node, reach = live(user, pk)
    if node.blob is None:
        raise Refused(404, "not_found")
    return node, reach


def live_pdf(user, pk, needs: Role = Role.READ) -> tuple[Node, rights.Reach]:
    """A file of a PDF, for what only a PDF has: pages, their text and notes on them."""
    node, reach = live(user, pk, needs)
    if node.kind != Node.Kind.FILE:
        raise Refused(400, "not_a_file")
    if not node.is_pdf:
        raise Refused(400, "not_a_pdf")
    return node, reach


def extension_of(node: Node) -> str | None:
    """The extension of a file's name: the one it was uploaded with, else the one its bytes'
    kind has."""
    if node.extension:
        return node.extension
    media_type = node.blob.media_type
    if media_type == store.PDF:
        return "pdf"
    return store.IMAGES.get(media_type) or EXTENSIONS.get(media_type)


def file_name(node: Node) -> str:
    extension = extension_of(node)
    return f"{node.title}.{extension}" if extension else node.title


@api("GET", visitors=True)
def node_file(request, pk):
    """The bytes the file is shown from; `v` names them, so that a reader who opened them
    keeps getting the same bytes after the text read in them replaces them."""
    node, reach = live_file(request.user, pk)
    name = file_name(node)
    if request.GET.get("download") == "1":
        taken_out(request.user, node, reach, extension_of(node) or "file")
    if not node.is_pdf:
        unknown = node.blob.media_type == store.UNKNOWN
        named = mimetypes.guess_type(name)[0] if unknown else None
        # Anything but a picture is saved, never shown: an HTML file would pass for a page of ours.
        shown = node.blob.media_type in store.IMAGES
        response = serve(request, node.blob, name, shown=shown, media_type=named)
        # An SVG is a document that can run script; sandboxed, it is only a picture.
        response["Content-Security-Policy"] = "sandbox"
        return response
    blob = ocr.readable(node.blob)
    asked = request.GET.get("v", blob.sha256)
    if asked == node.blob_id:
        blob = node.blob
    elif asked != blob.sha256:
        raise Refused(404, "not_found")
    return serve(request, blob, name)


def live_board(request, pk) -> tuple[Node, FileVersion | None, rights.Reach]:
    node, reach = live_file(request.user, pk)
    if not boards.is_board(node):
        raise Refused(404, "not_found")
    return node, boards.version_of(node, request.GET.get("version")), reach


def board_frame(request, title: str, page: str, data: str, reads: bool) -> HttpResponse:
    response = HttpResponse(
        boards.frame(title, page, data, reads), content_type="text/html; charset=utf-8"
    )
    response["Content-Security-Policy"] = boards.frame_policy(request)
    response["Cache-Control"] = "private, no-cache"
    for header, value in boards.HEADERS.items():
        response[header] = value
    return response


def board_page(request, blob, name: str) -> HttpResponse:
    response = serve(request, blob, name)
    # A page that names no charset of its own would be read as Windows-1252.
    response["Content-Type"] = f"{store.HTML}; charset={text.read(blob, boards.MOST).encoding}"
    response["Content-Security-Policy"] = boards.page_policy(request)
    for header, value in boards.HEADERS.items():
        response[header] = value
    return response


@api("GET", visitors=True)
def node_board(request, pk):
    """The page a board is shown in, as PONISTRA frames it and as it opens on its own; a version
    of it, and whoever may not edit the board, only reads what the board keeps."""
    node, version, reach = live_board(request, pk)
    page = f"{request.path}/page"
    return board_frame(
        request,
        node.title,
        f"{page}?version={version.pk}" if version else page,
        f"{request.path}/data",
        version is not None or not rights.covers(reach.role, Role.EDIT),
    )


@api("GET", visitors=True)
def node_board_page(request, pk):
    """A board's page, or the one a version of it kept, sandboxed whoever opens it."""
    node, version, _ = live_board(request, pk)
    return board_page(request, version.blob if version else node.blob, file_name(node))


@api("GET", "PUT", "PATCH", "DELETE", visitors=True)
def node_board_data(request, pk):
    """What a board keeps, for its page: read as the board is read, written as it is edited."""
    needs = Role.READ if request.method == "GET" else Role.EDIT
    node, _ = live(request.user, pk, needs)
    if not boards.is_board(node):
        raise Refused(404, "not_found")
    if request.method == "GET":
        return JsonResponse(board_data.read(request, node))
    data = body(request)
    op = {"PUT": "set", "PATCH": "update", "DELETE": "delete"}[request.method]
    write = {
        "op": op,
        "collection": request.GET.get("collection"),
        "key": request.GET.get("key"),
        "data": data.get("data"),
        "if_version": data.get("if_version"),
    }
    return JsonResponse(board_data.written(node, [write], request.user)[0])


@api("GET", signed_in=False, visitors=True)
def board_runtime(request):
    """The script a board loads to reach what it keeps; the same for everyone, and it holds
    nothing."""
    response = HttpResponse(boards.RUNTIME, content_type="text/javascript; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api("GET", visitors=True)
def node_picture(request, pk):
    """The file drawn small, or a link's site's icon, also in the trash for whom the trash lists
    it; `v` names the picture, so that the browser keeps it for good."""
    if Node.objects.filter(pk=pk, trashed_at__isnull=False).exists():
        node, _ = trashed(request.user, pk, Role.EDIT)
    else:
        node, _ = live(request.user, pk)
    if node.kind == Node.Kind.LINK:
        picture, name = node.icon, f"{node.title}.png"
    elif node.kind == Node.Kind.FILE:
        preview = previews.drawn(node.edited or node.blob)
        picture, name = preview and preview.picture, f"{node.title}.webp"
    else:
        raise Refused(404, "not_found")
    if picture is None or request.GET.get("v", picture.pk) != picture.pk:
        raise Refused(404, "not_found")
    response = serve(request, picture, name)
    if "v" in request.GET:
        response["Cache-Control"] = "private, max-age=31536000, immutable"
    return response


@api("GET", "POST", visitors=True)
def node_edited(request, pk):
    """The image with its edits drawn in, as it is opened or saved outside PONISTRA; without
    edits, the image as it came. Posted, the copy becomes a new image beside it, or among the
    user's own documents where they may not add to its folder."""
    node, reach = live_file(request.user, pk)
    if node.blob.media_type not in edits.FORMATS:
        raise Refused(404, "not_found")
    if request.method == "POST":
        title = title_of(body(request))
        place = kept_in(request.user, [node], beside(request.user, node))
    elif request.GET.get("download") == "1":
        taken_out(request.user, node, reach, extension_of(node) or "file")
    try:
        edited = edits.current(node.pk)
    except edits.FAILURES as error:
        log.error("The edits of %s cannot be drawn: %s", node.pk, error)
        raise Refused(422, "unreadable_edits") from None
    if request.method == "GET":
        return serve(request, edited or node.blob, file_name(node))
    if edited is None:
        raise Refused(409, "not_edited")
    copy = created(place, Node.Kind.FILE, title, edited, request.user, node.extension)
    extraction.wake()
    previews.wake()
    return JsonResponse(describe(copy), status=201)


@api("GET", visitors=True)
def node_text(request, pk):
    node, _ = live_file(request.user, pk)
    if not node.blob.media_type.startswith("text/"):
        raise Refused(404, "not_found")
    try:
        most = int(request.GET.get("most", TEXT_SHOWN))
    except ValueError:
        raise Refused(400, "invalid_most") from None
    if not 1 <= most <= TEXT_SHOWN:
        raise Refused(400, "invalid_most")
    try:
        found = text.read(node.blob, most)
    except text.NotText:
        raise Refused(422, "not_text") from None
    return JsonResponse(
        {"text": found.text, "encoding": found.encoding, "truncated": found.truncated}
    )


@api("GET", visitors=True)
def node_original(request, pk):
    node, reach = live_pdf(request.user, pk)
    taken_out(request.user, node, reach, "pdf")
    return serve(request, node.blob, file_name(node))


@api("POST")
def node_ocr(request, pk):
    """Reads the file's pages without text once more, after the reading failed."""
    node, _ = live_pdf(request.user, pk)
    if not ocr.retry(node.blob):
        raise Refused(409, "not_failed")
    return JsonResponse(ocr.described(node.blob))


@api("POST", visitors=True)
def trash(request):
    trashing = live_nodes(request.user, body(request), Role.EDIT)
    for node, _ in trashing:
        laid_out(node)
    Node.objects.filter(pk__in=[node.pk for node, _ in trashing]).update(trashed_at=timezone.now())
    revoke()
    return HttpResponse(status=204)


@api("GET")
def trash_list(request):
    items = list(Node.objects.filter(trashed_at__isnull=False).order_by("-trashed_at", "pk"))
    chains = Node.ancestries(node.pk for node in items)
    roles = rights.granted(request.user, {above for chain in chains.values() for above in chain})
    held = {node.pk: rights.strongest(roles.get(n.pk) for n in chains[node.pk]) for node in items}
    editable = [node for node in items if rights.covers(held[node.pk], Role.EDIT)]
    kept = retention.kept_nodes(node.pk for node in editable)
    return JsonResponse(
        {
            "items": [
                {**node, "role": held[node["id"]], "kept": kept.get(node["id"])}
                for node in described(editable)
            ]
        }
    )


def trashed_nodes(user, data: dict, needs: Role) -> list[tuple[Node, rights.Reach]]:
    ids = data.get("nodes")
    if not isinstance(ids, list) or not ids or not all(isinstance(pk, str) for pk in ids):
        raise Refused(400, "invalid_nodes")
    found = [trashed(user, optional_id(pk), needs) for pk in dict.fromkeys(ids)]
    return sorted(found, key=lambda each: len(each[1].ancestry))


@api("POST")
def restore(request):
    """Puts nodes back, a folder before what was trashed inside it, so that keeps its place."""
    with transaction.atomic():
        for node, reach in trashed_nodes(request.user, body(request), Role.EDIT):
            node.trashed_at = None
            if node.parent and not node.parent.is_live():
                node.parent = None
                rights.keep_owners(node, reach.ancestry, request.user)
            node.save(update_fields=["trashed_at", "parent"])
    return HttpResponse(status=204)


@api("POST")
def purge(request):
    purging = trashed_nodes(request.user, body(request), Role.OWN)
    retention.refuse_nodes(node for node, _ in purging)
    Node.objects.filter(pk__in=[node.pk for node, _ in purging]).delete()
    store.collect_later()
    return HttpResponse(status=204)
