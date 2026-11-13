"""A company folder connected to a folder on a file server (D37), by the administrator alone."""

from django.db import transaction
from django.http import HttpResponse, JsonResponse

from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.core.sealed import seal
from apps.documents.models import Node
from apps.retention import kept as retention
from apps.users.accounts import administrator

from . import smb, sync
from .models import Share


def describe(share: Share) -> dict:
    return {
        "address": str(share),
        "mode": share.mode,
        "username": share.username,
        "state": share.state,
        "error": share.error,
        "found": share.found,
        "moving": share.moving,
        "read_at": share.read_at,
    }


def _signed_in(address: smb.Address, username: str, password: str) -> None:
    """The server answers the account and has the folder, or the request says why not."""
    try:
        with smb.Server(address, username, password):
            pass
    except Exception as error:
        code = smb.failure(error)
        if code is None:
            raise
        raise Refused(422, code) from None


def _credentials(data: dict) -> tuple[str, str]:
    username, password = data.get("username"), data.get("password")
    if not isinstance(username, str) or not username.strip() or len(username) > 320:
        raise Refused(400, "invalid_username")
    if not isinstance(password, str) or len(password) > 1000:
        raise Refused(400, "invalid_password")
    return username.strip(), password


def _folder(pk) -> Node:
    node = Node.objects.filter(pk=pk, company=True).first()
    if node is None:
        raise Refused(404, "not_found")
    return node


def _connected(node: Node) -> Share:
    share = Share.objects.filter(folder=node).first()
    if share is None:
        raise Refused(404, "not_connected")
    return share


@api("GET", "POST", "PATCH", "DELETE", confirmed=("POST", "DELETE"))
def share(request, pk):
    administrator(request)
    node = _folder(pk)
    if request.method == "POST":
        return _connect(request, node)
    found = _connected(node)
    if request.method == "GET":
        return JsonResponse(describe(found))
    if request.method == "DELETE":
        with transaction.atomic():
            locked = Share.objects.select_for_update().get(pk=found.pk)
            if locked.mode == Share.Mode.COPY:
                retention.refuse_nodes(Node.objects.filter(parent=node))
                Node.objects.filter(parent=node).delete()
                Node.objects.filter(pk=node.pk).update(copied=False)
            locked.delete()
            sync.wake()
        revoke()
        return HttpResponse(status=204)
    data = body(request)
    with transaction.atomic():
        found = Share.objects.select_for_update().get(pk=found.pk)
        if "password" in data:
            username, password = _credentials(data)
            _signed_in(smb.Address(found.host, found.path), username, password)
            found.username, found.secret = username, seal(sync.SEALED, password)
            found.error = ""
        if data.get("copy") is True:
            if found.state != Share.State.READ:
                raise Refused(409, "not_read")
            if not sync.room_for(found.found.get("bytes", 0)):
                raise Refused(507, "no_space")
            found.state = Share.State.COPYING
        elif found.state == Share.State.READ:
            found.state = Share.State.READING
        found.save()
        sync.wake()
    return JsonResponse(describe(found))


def _connect(request, node: Node) -> JsonResponse:
    data = body(request)
    mode = data.get("mode")
    if mode not in Share.Mode.values:
        raise Refused(400, "invalid_mode")
    given = data.get("address")
    address = smb.address_of(given) if isinstance(given, str) and len(given) <= 1000 else None
    if address is None:
        raise Refused(400, "invalid_address")
    username, password = _credentials(data)
    if Share.objects.filter(folder=node).exists():
        raise Refused(409, "connected")
    if mode == Share.Mode.COPY and Node.objects.filter(parent=node).exists():
        raise Refused(409, "not_empty")
    _signed_in(address, username, password)
    with transaction.atomic():
        found = Share.objects.create(
            folder=node,
            mode=mode,
            host=address.host,
            path=address.path,
            username=username,
            secret=seal(sync.SEALED, password),
            state=Share.State.READING if mode == Share.Mode.COPY else Share.State.READY,
            created_by=request.user,
        )
        if mode == Share.Mode.COPY:
            Node.objects.filter(pk=node.pk).update(copied=True)
        sync.wake()
    revoke()
    return JsonResponse(describe(found), status=201)


@api("POST")
def move(request, pk):
    """The copy's last changes taken and the folder left PONISTRA's."""
    administrator(request)
    with transaction.atomic():
        found = Share.objects.select_for_update().filter(folder=_folder(pk)).first()
        if found is None:
            raise Refused(404, "not_connected")
        if found.mode != Share.Mode.COPY or found.state in (Share.State.READING, Share.State.READ):
            raise Refused(409, "not_copied")
        found.moving = True
        found.save(update_fields=["moving"])
        sync.wake()
    return JsonResponse(describe(found))
