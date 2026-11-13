"""What a message carries, as it is given and as each reader sees it: its files, and the items of
PONISTRA its text links to, shown as those files are."""

import re
import uuid
from urllib.parse import urlsplit

from django.conf import settings

from apps.access import rights
from apps.access.models import Role
from apps.blobs import previews, store
from apps.blobs.models import Blob
from apps.core.api import Refused
from apps.documents import views as documents
from apps.documents.models import Node

from .models import Attachment, Message

# Files a message carries at most, and items of its text shown as cards.
MOST = 20
MOST_ITEMS = 5
NAME = 255
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ITEM = re.compile(r"https?://([^/\s]+)/(?:d|p|f)/(?:[a-z0-9-]*-)?([0-9A-Za-z]{22})(?![0-9A-Za-z])")
# Bytes a browser may show as they are: anything else, HTML above all, is saved instead.
SHOWN_MEDIA = ("video/", "audio/")

NOTHING: dict = {"files": [], "items": []}


def _node_of(user, given: object) -> Attachment:
    try:
        pk = uuid.UUID(str(given))
    except ValueError:
        raise Refused(400, "invalid_attachments") from None
    node, reach = documents.live(user, pk, Role.OWN)
    if node.kind == Node.Kind.FOLDER:
        raise Refused(400, "invalid_attachments")
    if any(each.confined for each in reach.ancestry):
        raise Refused(403, "confined")
    return Attachment(node=node, name=node.title[:NAME])


def _blob_of(each: dict) -> Attachment:
    name = str(each.get("name") or "").strip()[:NAME]
    sha256 = each.get("blob")
    blob = Blob.objects.filter(pk=sha256).first() if isinstance(sha256, str) else None
    if blob is None or not name:
        raise Refused(400, "unknown_file")
    return Attachment(blob=blob, name=name)


def given(user, data: dict) -> list[Attachment]:
    """The files the request attaches, not yet saved: bytes uploaded, or files of the tree the
    user may share, which a folder that keeps its documents inside never lets go."""
    listed = data.get("attachments") or []
    if not isinstance(listed, list) or len(listed) > MOST:
        raise Refused(400, "invalid_attachments")
    if not all(isinstance(each, dict) for each in listed):
        raise Refused(400, "invalid_attachments")
    return [_node_of(user, each["node"]) if each.get("node") else _blob_of(each) for each in listed]


def number_of(digits: str) -> uuid.UUID | None:
    value = 0
    for digit in digits:
        value = value * 62 + DIGITS.index(digit)
    return uuid.UUID(int=value) if value >> 128 == 0 else None


def hosts_of(request) -> set[str]:
    """The names this installation is reached by, whose links are its own items."""
    return {urlsplit(settings.PUBLIC_URL).netloc, request.get_host()}


def _linked(text: str, hosts: set[str]) -> list[uuid.UUID]:
    found = []
    for host, digits in ITEM.findall(text):
        pk = number_of(digits) if host in hosts else None
        if pk is not None and pk not in found:
            found.append(pk)
    return found[:MOST_ITEMS]


def _readable(user, ids: set[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if user is None or not ids:
        return {}
    nodes = [
        reach.ancestry[-1]
        for reach in rights.reaches(user, ids).values()
        if reach.role is not None and reach.ancestry[-1].is_live(reach.ancestry)
    ]
    return {each["id"]: each for each in documents.described(nodes)}


def _file(each: Attachment, node: dict | None, at: str) -> dict:
    blob = each.blob
    return {
        "id": each.pk,
        "name": each.name,
        "blob": blob and blob.pk,
        "size": blob and blob.size,
        "media_type": blob and blob.media_type,
        "href": f"{at}/attachments/{each.pk}" if blob else None,
        "picture": bool(blob and blob.media_type in previews.DRAWN),
        "node": node,
    }


def carried(messages: list[Message], user, at: str, hosts: set[str]) -> dict[int, dict]:
    """For each message what it carries as this reader may see it: nothing of the tree for
    someone without a right to it, as for a guest in a meeting's call."""
    links = {each.pk: _linked(each.body, hosts) for each in messages}
    wanted = {pk for found in links.values() for pk in found}
    for message in messages:
        wanted |= {each.node_id for each in message.attachments.all() if each.node_id}
    readable = _readable(user, wanted)
    found = {}
    for message in messages:
        files = list(message.attachments.all())
        attached = {each.node_id for each in files}
        found[message.pk] = {
            "files": [_file(each, readable.get(each.node_id), at) for each in files],
            "items": [
                readable[pk] for pk in links[message.pk] if pk in readable and pk not in attached
            ],
        }
    return found


def shown_inline(blob: Blob) -> bool:
    return (
        blob.media_type in store.IMAGES
        or blob.media_type == store.PDF
        or blob.media_type.startswith(SHOWN_MEDIA)
    )
