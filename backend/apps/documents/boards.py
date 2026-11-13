"""Boards (D36): pages of HTML an agent writes or a user brings, shown as they are. A board
runs in a sandbox of its own origin, so it reaches nothing of PONISTRA, and its frame lets it
load nothing but the libraries of a few public CDNs and navigate nowhere. What it keeps it asks
the page that frames it for (D36-2, `board_data`), which answers for that board alone."""

import base64
import hashlib
import io
from pathlib import Path

from django.db import transaction
from django.db.models import Max, QuerySet
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.html import escape

from apps.blobs import store
from apps.blobs.models import Blob
from apps.core.api import Refused, optional_id
from apps.search import extraction
from apps.versions.models import FileVersion
from apps.workspace.views import owns

from .models import Node

MOST = 1024 * 1024
NAMES = {"html", "htm", ""}
LIBRARIES = " ".join(
    (
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
        "https://unpkg.com",
        "https://cdn.tailwindcss.com",
        "https://code.jquery.com",
    )
)
# Without allow-popups and with a frame that admits only the board's own address, what it shows
# leaves by no window or link; what a library fetches comes from where the library came from.
SANDBOX = "allow-scripts"
RUNTIME_PATH = "/api/boards/runtime.js"
RUNTIME = (Path(__file__).parent / "board" / "runtime.js").read_text()
BRIDGE = (Path(__file__).parent / "board" / "bridge.js").read_text()
BRIDGE_HASH = base64.b64encode(hashlib.sha256(BRIDGE.encode()).digest()).decode()
HEADERS = {
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-DNS-Prefetch-Control": "off",
}


def is_board(node: Node) -> bool:
    """A page of HTML by its bytes, named one or not named at all: an error page saved as JSON
    stays the text it was saved as."""
    return (
        node.kind == Node.Kind.FILE
        and node.blob.media_type == store.HTML
        and node.extension.lower() in NAMES
    )


def among(nodes: QuerySet[Node]) -> QuerySet[Node]:
    """The boards among these nodes, told as `is_board` tells one."""
    return nodes.annotate(named=Lower("extension")).filter(
        kind=Node.Kind.FILE, blob__media_type=store.HTML, named__in=NAMES
    )


def frame(title: str, page: str, data: str, reads: bool = False) -> str:
    """The page PONISTRA shows a board in: the board in a sandboxed frame that may hold nothing
    but the board, so that the board cannot take itself elsewhere, and the one script that answers
    what the board asks of its own data, so that a page in a sandbox can keep anything."""
    read_only = " data-reads" if reads else ""
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{escape(title)} – Ponistra</title>"
        "<style>html,body,iframe{margin:0;border:0;width:100%;height:100%;display:block}</style>"
        f'</head><body><iframe src="{escape(page)}" sandbox="{SANDBOX}" title="{escape(title)}" '
        f'data-data="{escape(data)}"{read_only}></iframe>'
        f"<script>{BRIDGE}</script></body></html>"
    )


def frame_policy(request) -> str:
    page = f"{request.get_host()}{request.path}/page"
    return (
        f"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{BRIDGE_HASH}'; "
        f"connect-src 'self'; frame-src {page}; frame-ancestors 'self'"
    )


def page_policy(request) -> str:
    runtime = f"{request.scheme}://{request.get_host()}{RUNTIME_PATH}"
    return "; ".join(
        (
            f"sandbox {SANDBOX}",
            "default-src 'none'",
            f"script-src 'unsafe-inline' 'unsafe-eval' blob: {LIBRARIES} {runtime}",
            f"style-src 'unsafe-inline' {LIBRARIES} https://fonts.googleapis.com",
            f"font-src data: {LIBRARIES} https://fonts.gstatic.com",
            f"img-src data: blob: {LIBRARIES}",
            "media-src data: blob:",
            "worker-src blob:",
            f"connect-src {LIBRARIES}",
            "form-action 'none'",
            "base-uri 'none'",
            "frame-ancestors 'self'",
        )
    )


def agent_folder_of(user, node: Node, given) -> str:
    """The folder of the owner's code workspace that the board's agent starts in, or none."""
    if not is_board(node):
        raise Refused(400, "not_a_board")
    if not owns(user):
        raise Refused(403, "not_the_owner")
    if (
        not isinstance(given, str)
        or len(given) > Node._meta.get_field("agent_folder").max_length
        or (given and not given.startswith("/"))
        or any(character in given for character in "\r\n\0")
    ):
        raise Refused(400, "invalid_agent_folder")
    return given


def version_of(node: Node, asked: str | None) -> FileVersion | None:
    if asked is None:
        return None
    version = node.file_versions.filter(pk=optional_id(asked)).first()
    if version is None:
        raise Refused(404, "not_found")
    return version


def page(html: str) -> Blob:
    """The bytes of a board's page, refused unless whole: a fragment would be shown as text."""
    data = html.encode()
    if len(data) > MOST:
        raise Refused(413, "board_too_large")
    if not store.PAGE.match(data.lstrip()):
        raise Refused(400, "not_a_page")
    blob = store.put(io.BytesIO(data))
    if blob.media_type != store.HTML:
        raise RuntimeError(f"{blob.sha256} is kept as {blob.media_type}, not as a page")
    return blob


def _next(node: Node, blob: Blob, user, agent: str = "", restored_from=None) -> FileVersion:
    last = node.file_versions.aggregate(last=Max("number"))["last"] or 0
    return FileVersion.objects.create(
        node=node,
        number=last + 1,
        blob=blob,
        created_at=timezone.now(),
        created_by=user,
        agent=agent,
        restored_from=restored_from,
    )


def _replaced(node: Node, blob: Blob, user) -> None:
    """The file before its first replacement becomes its first version, as it was made."""
    if not node.file_versions.exists():
        FileVersion.objects.create(
            node=node,
            number=1,
            blob=node.blob,
            created_at=node.created_at,
            created_by=node.created_by,
        )
    node.blob = blob
    node.updated_by = user
    node.save(update_fields=["blob", "updated_by", "updated_at"])


def begun(node: Node, user, agent: str) -> FileVersion:
    return _next(node, node.blob, user, agent)


def rewritten(node: Node, html: str, user, agent: str, title: str | None = None) -> Node:
    if not is_board(node):
        raise Refused(400, "not_a_board")
    blob = page(html)
    with transaction.atomic():
        node = Node.objects.select_for_update(of=("self",)).select_related("blob").get(pk=node.pk)
        if title:
            node.title = title
            node.save(update_fields=["title", "updated_at"])
        if blob.pk != node.blob_id:
            _replaced(node, blob, user)
            _next(node, blob, user, agent)
    extraction.wake()
    return node


def restored(version: FileVersion, user) -> FileVersion:
    with transaction.atomic():
        node = Node.objects.select_for_update(of=("self",)).get(pk=version.node_id)
        _replaced(node, version.blob, user)
        return _next(node, version.blob, user, restored_from=version.number)
