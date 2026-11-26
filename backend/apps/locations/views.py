"""Folders on the network's servers a user set up with their own account there, browsed from
Documents and shared as a folder is (D54). Every view that waits on a server is a coroutine."""

import asyncio
import hashlib
import tempfile
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils.http import content_disposition_header

from apps.access.models import Role
from apps.blobs import store
from apps.blobs.models import Upload
from apps.blobs.previews import DRAWN
from apps.blobs.views import Unsatisfiable, byte_range
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.core.sealed import opened, seal
from apps.exports import zipped
from apps.files import walk
from apps.imports.reading import TooLarge, Unreadable
from apps.network.models import Tunnel
from apps.reader import client
from apps.shares import smb
from apps.users.models import policy

from . import guests, held, reach, sftp
from .models import Grant, Location
from .remote import EDITED, Entry, Failed, Remote, asked, joined, name_of, ordered

User = get_user_model()
# A file drawn small is read whole first; a larger one is shown without its picture.
PICTURED = 64 * 1024 * 1024
SNIFFED = 1024
# Shown in place, as what a browser cannot run: a picture, sound, video, a PDF.
SHOWN = DRAWN | {"audio/mp4", "audio/mpeg", "audio/ogg", "audio/wav", "audio/flac"}
SHOWN |= {"video/mp4", "video/webm", "video/quicktime", "video/ogg"}
CHANGES = ("POST",)
# What one zip takes at once: the rows chosen in one folder.
ZIPPED = 1000


def _address(found: Location) -> str:
    if found.kind == Location.Kind.SMB:
        return str(smb.Address(found.host, found.path).unc)
    port = "" if found.port == 22 else f":{found.port}"
    return f"{found.host}{port}:{found.path}" if found.path else f"{found.host}{port}"


def describe(found: Location, role: Role) -> dict:
    owner = found.owner
    shown = {
        "id": str(found.pk),
        "name": found.name,
        "kind": found.kind,
        "address": _address(found),
        "role": role,
        "owner": {"id": owner.pk, "name": owner.get_full_name() or owner.email},
        "tunnel": found.tunnel and {"id": found.tunnel.pk, "name": found.tunnel.name},
    }
    if role != Role.OWN:
        return shown
    return shown | {
        "host": found.host,
        "port": found.port,
        "path": found.path,
        "username": found.username,
        "auth": found.auth,
        "public_key": found.public_key,
        "jump": found.jump,
    }


def describe_grant(grant: Grant) -> dict:
    if grant.user_id:
        name = grant.user.get_full_name() or grant.user.email
        grantee = {"kind": "user", "id": grant.user_id, "name": name}
    elif grant.group_id:
        grantee = {"kind": "group", "id": grant.group_id, "name": grant.group.name}
    else:
        grantee = {"kind": "everyone", "id": None, "name": ""}
    return {"id": grant.pk, "role": grant.role, "grantee": grantee}


def _text(
    data: dict, key: str, most: int, *, required: bool = True, error: str | None = None
) -> str:
    error = error or f"invalid_{key}"
    given = data.get(key, "" if not required else None)
    if not isinstance(given, str) or len(given) > most or any(each in given for each in "\0\r\n"):
        raise Refused(400, error)
    given = given.strip()
    if required and not given:
        raise Refused(400, error)
    return given


def _port(data: dict, default: int) -> int:
    port = data.get("port", default)
    if type(port) is not int or not 0 < port < 65536:
        raise Refused(400, "invalid_port")
    return port


def _made_key() -> tuple[str, str]:
    installation = urlsplit(settings.PUBLIC_URL).hostname or "ponistra"
    return sftp.made_key(f"ponistra@{installation}")


def _given(data: dict, found: Location) -> str | None:
    """The fields the request sets on the location, checked; the secret it brings, None where it
    keeps the one it has. A key PONISTRA makes is the secret of a location set to sign in with
    one."""
    adding = found._state.adding
    if "name" in data or adding:
        found.name = _text(data, "name", 100, error="invalid_location_name")
    secret = None
    switched = False
    if found.kind == Location.Kind.SMB:
        if "address" in data or adding:
            given = data.get("address")
            address = (
                smb.address_of(given) if isinstance(given, str) and len(given) <= 1000 else None
            )
            if address is None:
                raise Refused(400, "invalid_address")
            found.host, found.path = address.host, address.path
        found.port = _port(data, found.port or 445)
        found.auth = Location.Auth.PASSWORD
    else:
        if "host" in data or adding:
            host = _text(data, "host", 253)
            if not sftp.HOST.fullmatch(host):
                raise Refused(400, "invalid_host")
            found.host = host
        found.port = _port(data, found.port or 22)
        if "path" in data:
            found.path = _text(data, "path", 1000, required=False)
        if "jump" in data:
            jump = _text(data, "jump", 600, required=False)
            if jump and sftp.jump_of(jump) is None:
                raise Refused(400, "invalid_jump")
            found.jump = jump
        if "auth" in data or adding:
            auth = data.get("auth")
            if auth not in Location.Auth.values:
                raise Refused(400, "invalid_auth")
            if auth == Location.Auth.KEY and found.auth != Location.Auth.KEY:
                secret, found.public_key = _made_key()
            switched = auth == Location.Auth.PASSWORD and found.auth != auth
            found.auth = auth
    if "tunnel" in data:
        tunnel = data["tunnel"]
        if tunnel is not None and type(tunnel) is not int:
            raise Refused(400, "invalid_tunnel")
        found.tunnel_id = tunnel
    if "username" in data or adding:
        username = _text(data, "username", 320)
        if found.kind == Location.Kind.SFTP and not sftp.USER.fullmatch(username):
            raise Refused(400, "invalid_username")
        found.username = username
    if found.auth == Location.Auth.PASSWORD:
        found.public_key = ""
        if "password" in data or adding or switched:
            password = data.get("password")
            if not isinstance(password, str) or not password or len(password) > 1000:
                raise Refused(400, "invalid_password")
            secret = password
    return secret


def _may_add(user) -> None:
    if not policy().adds_locations(user):
        raise Refused(403, "locations_off")


def _chosen(found: Location, data: dict) -> None:
    """A tunnel the request chooses is one of the installation's switched on."""
    if "tunnel" not in data or found.tunnel_id is None:
        return
    found.tunnel = Tunnel.objects.filter(pk=found.tunnel_id, enabled=True).first()
    if found.tunnel is None:
        raise Refused(400, "invalid_tunnel")


def _tunnels() -> list[dict]:
    """The tunnels a location may go through."""
    found = Tunnel.objects.filter(enabled=True).order_by("name", "pk")
    return [{"id": each.pk, "name": each.name} for each in found]


def _listed(user) -> list[dict]:
    roles = reach.roles(user)
    found = Location.objects.select_related("owner", "tunnel").filter(pk__in=roles).order_by("name")
    return [describe(each, roles[each.pk]) for each in found]


def _saved(user, found: Location, secret: str | None, known_hosts: str | None) -> dict:
    if secret is not None:
        found.secret = seal(reach.SEALED, secret)
    if known_hosts is not None:
        found.known_hosts = known_hosts
    found.save()
    return describe(found, reach.role_on(user, found))


MOVED = {"host", "port", "address", "jump", "tunnel"}
REACHING = MOVED | {"path", "username", "auth", "password"}


async def _tried(found: Location, secret: str | None, data: dict) -> str | None:
    """The account signed in to where the request changes how the location is reached, the host
    keys the server showed; a key PONISTRA just made signs in only once its public half is on
    the server, and a location moved to another server learns that server's keys anew."""
    if not found._state.adding and not REACHING & data.keys():
        return None
    if MOVED & data.keys():
        found.known_hosts = ""
    if found.auth == Location.Auth.KEY:
        return found.known_hosts
    if secret is None:
        secret = opened(reach.SEALED, found.secret)
        if secret is None:
            raise Failed("location_secret_lost")
    return await reach.tried(found, secret)


@api("GET", "POST", confirmed=CHANGES)
async def locations(request):
    user = request.user
    if request.method == "GET":
        listed = await database(_listed)(user)
        adds = await database(lambda: policy().adds_locations(user))()
        tunnels = await database(_tunnels)() if adds else []
        return JsonResponse({"locations": listed, "adds": adds, "tunnels": tunnels})
    await database(_may_add)(user)
    data = body(request)
    if data.get("kind") not in Location.Kind.values:
        raise Refused(400, "invalid_kind")
    found = Location(owner=user, kind=data["kind"], port=0)
    secret = await asyncio.to_thread(_given, data, found)
    await database(_chosen)(found, data)
    known = await _tried(found, secret, data)
    return JsonResponse(await database(_saved)(user, found, secret, known), status=201)


@api("GET", "PATCH", "DELETE", confirmed=("PATCH", "DELETE"))
async def location(request, pk):
    user = request.user
    if request.method == "GET":
        found, role = await database(reach.location)(user, pk)
        return JsonResponse(describe(found, role))
    found, _ = await database(reach.location)(user, pk, Role.OWN)
    if request.method == "DELETE":
        await database(found.delete)()
        sftp.ended(f"{found.pk}:")
        return HttpResponse(status=204)
    data = body(request)
    secret = await asyncio.to_thread(_given, data, found)
    await database(_chosen)(found, data)
    known = await _tried(found, secret, data)
    described = await database(_saved)(user, found, secret, known)
    sftp.ended(f"{found.pk}:")
    return JsonResponse(described)


def _grants(found: Location) -> list[dict]:
    held = found.grants.select_related("user", "group").order_by("created_at")
    return [describe_grant(grant) for grant in held]


def _granted(found: Location, data: dict) -> None:
    kind, given, role = data.get("kind"), data.get("id"), data.get("role")
    if role not in Role.values:
        raise Refused(400, "invalid_role")
    where = {"user": None, "group": None}
    if kind == "user":
        where["user"] = (
            User.objects.filter(pk=given, visitor=False).first() if type(given) is int else None
        )
        if where["user"] is None or where["user"].pk == found.owner_id:
            raise Refused(400, "invalid_grantee")
    elif kind == "group":
        where["group"] = Group.objects.filter(pk=given).first() if type(given) is int else None
        if where["group"] is None:
            raise Refused(400, "invalid_grantee")
    elif kind != "everyone":
        raise Refused(400, "invalid_grantee")
    with transaction.atomic():
        Grant.objects.update_or_create(location=found, **where, defaults={"role": role})


@api("GET", "POST")
def grants(request, pk):
    """Whom the location is shared with, as a folder is; a grant given again changes its role."""
    found, _ = reach.location(request.user, pk, Role.OWN)
    if request.method == "POST":
        _granted(found, body(request))
    return JsonResponse({"grants": _grants(found)})


@api("DELETE")
def grant(request, pk, grant_pk):
    found, _ = reach.location(request.user, pk, Role.OWN)
    if not Grant.objects.filter(location=found, pk=grant_pk).delete()[0]:
        raise Refused(404, "not_found")
    return HttpResponse(status=204)


async def _remote(request, where: dict, needs: Role = Role.READ) -> tuple[str, Remote]:
    """The location the request names, or the guest of a machine the user manages, whose
    session is root in it and so covers every role (DT7)."""
    if "pk" in where:
        found, _ = await database(reach.location)(request.user, where["pk"], needs)
        return found.name, await reach.reached(found)
    computer = await database(guests.managed)(request.user, where["computer"])
    guest = guests.named(where["guest"])
    return guest, await guests.reached(computer, guest, request.user)


@api("GET")
async def guests_of(request):
    """The guests of the machines the user manages, as a source of Files each."""
    return JsonResponse({"computers": await guests.listed(request.user)})


@api("GET")
async def files(request, **where):
    """What a folder of the location holds, as its server lists it now."""
    path = asked(request.GET.get("path", ""))
    _, remote = await _remote(request, where)
    try:
        entries = ordered(await remote.listed(path))
    finally:
        await remote.close()
    return JsonResponse({"path": path, "entries": [entry.described() for entry in entries]})


def _media(head: bytes) -> str:
    media = store.sniff(head)
    return media if media in SHOWN else "application/octet-stream"


@api("GET")
async def raw(request, **where):
    """A file's bytes as its server has them, or the one range a player asks for; shown in place
    only where it is a picture, sound, video or PDF, which runs nothing."""
    path = asked(request.GET.get("path"), root=False)
    _, remote = await _remote(request, where)
    try:
        entry = await remote.stat(path)
        if entry.kind != "file":
            raise Refused(400, "not_a_file")
        size = entry.size or 0
        span = None
        if "Range" in request.headers:
            try:
                span = byte_range(request.headers["Range"], size)
            except Unsatisfiable:
                await remote.close()
                return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        head = await remote.whole(path, SNIFFED) if size <= SNIFFED else None
        if head is None:
            head = b"".join([part async for part in remote.chunks(path, 0, min(size, SNIFFED))])
    except BaseException:
        await remote.close()
        raise
    start, end = span or (0, size - 1)
    length = end - start + 1 if size else 0

    async def sent():
        try:
            if length:
                async for part in remote.chunks(path, start, length):
                    yield part
        finally:
            await remote.close()

    media = _media(head)
    download = request.GET.get("download") == "1" or media == "application/octet-stream"
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "Content-Disposition": content_disposition_header(download, entry.name),
        "Content-Length": str(length),
    }
    if span:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingHttpResponse(
        sent(), status=206 if span else 200, content_type=media, headers=headers
    )


@api("GET")
async def picture(request, **where):
    """An image or a PDF's first page drawn small by the reader (D51), which alone reads what
    someone else made."""
    path = asked(request.GET.get("path"), root=False)
    _, remote = await _remote(request, where)
    try:
        data = await remote.whole(path, PICTURED)
    finally:
        await remote.close()
    media = data and store.sniff(data[:SNIFFED])
    if media not in DRAWN:
        raise Refused(404, "not_found")
    with tempfile.NamedTemporaryFile() as file:
        file.write(data)
        file.flush()
        try:
            drawn = await asyncio.to_thread(
                client.ask, "preview", Path(file.name), pdf=media == store.PDF
            )
        except Unreadable, TooLarge:
            raise Refused(404, "not_found") from None
    return HttpResponse(drawn, content_type="image/webp", headers={"Cache-Control": "private"})


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _textual(data: bytes) -> str | None:
    if b"\0" in data:
        return None
    try:
        return data.decode()
    except UnicodeDecodeError:
        return None


@api("GET", "POST", confirmed=CHANGES)
async def text(request, **where):
    """A text file to read and edit; written back only while it still is what was read."""
    if request.method == "GET":
        path = asked(request.GET.get("path"), root=False)
        _, remote = await _remote(request, where)
        try:
            entry = await remote.stat(path)
            data = await remote.whole(path, EDITED) if entry.kind == "file" else None
        finally:
            await remote.close()
        if entry.kind != "file":
            raise Refused(400, "not_a_file")
        shown = {"path": path, "size": entry.size, "modified": entry.modified}
        if data is None:
            return JsonResponse(shown | {"kind": "large", "text": None, "hash": None})
        written = _textual(data)
        kind = "text" if written is not None else "binary"
        return JsonResponse(shown | {"kind": kind, "text": written, "hash": _hash(data)})
    data = body(request)
    path = asked(data.get("path"), root=False)
    given, was = data.get("text"), data.get("hash")
    if not isinstance(given, str) or not isinstance(was, str):
        raise Refused(400, "invalid_text")
    written = given.encode()
    if len(written) > EDITED:
        raise Refused(413, "too_large")
    _, remote = await _remote(request, where, Role.EDIT)
    try:
        now = await remote.whole(path, EDITED)
        if now is None or _hash(now) != was:
            raise Refused(409, "changed")
        await remote.write(path, written)
        entry = await remote.stat(path)
    finally:
        await remote.close()
    return JsonResponse(
        {"path": path, "size": entry.size, "modified": entry.modified, "hash": _hash(written)}
    )


@api("POST", confirmed=CHANGES)
async def folder(request, **where):
    data = body(request)
    path = joined(asked(data.get("path", "")), name_of(data.get("name")))
    _, remote = await _remote(request, where, Role.EDIT)
    try:
        await remote.mkdir(path)
    finally:
        await remote.close()
    return JsonResponse({"path": path}, status=201)


@api("POST", confirmed=CHANGES)
async def rename(request, **where):
    """A file or folder renamed, or moved to another folder of the location."""
    data = body(request)
    path, to = asked(data.get("path"), root=False), asked(data.get("to"), root=False)
    if to == path or to.startswith(f"{path}/"):
        raise Refused(400, "invalid_path")
    _, remote = await _remote(request, where, Role.EDIT)
    try:
        await remote.rename(path, to)
    finally:
        await remote.close()
    return JsonResponse({"path": to})


@api("POST", confirmed=CHANGES)
async def remove(request, **where):
    """Files and folders deleted on the server, folders with all they hold; nothing keeps them."""
    given = body(request).get("paths")
    if not isinstance(given, list) or not 0 < len(given) <= 1000:
        raise Refused(400, "invalid_paths")
    paths = [asked(path, root=False) for path in given]
    _, remote = await _remote(request, where, Role.EDIT)
    try:
        for path in paths:
            await remote.remove(path)
    finally:
        await remote.close()
    return HttpResponse(status=204)


@api("GET")
async def stat(request, **where):
    """An entry itself, a link and not what it points at, with its owner and mode where the
    server has them."""
    path = asked(request.GET.get("path", ""))
    _, remote = await _remote(request, where)
    try:
        return JsonResponse((await remote.described(path)).described(path))
    finally:
        await remote.close()


@api("POST", confirmed=CHANGES)
async def mode(request, **where):
    data = body(request)
    path, given = asked(data.get("path", "")), walk.mode_of(data.get("mode"))
    _, remote = await _remote(request, where, Role.EDIT)
    try:
        await remote.chmod(path, given)
        return JsonResponse((await remote.described(path)).described(path))
    finally:
        await remote.close()


@api("POST", confirmed=CHANGES)
async def owner(request, **where):
    data = body(request)
    path = asked(data.get("path"), root=False)
    uid, gid = walk.id_of(data.get("uid")), walk.id_of(data.get("gid"))
    _, remote = await _remote(request, where, Role.EDIT)
    try:
        await remote.chown(path, uid, gid)
        return JsonResponse((await remote.described(path)).described(path))
    finally:
        await remote.close()


@api("GET")
async def search(request, **where):
    """The entries below a folder whose names hold what was asked."""
    path, query = asked(request.GET.get("path", "")), walk.query_of(request.GET.get("q"))
    _, remote = await _remote(request, where)
    try:
        return JsonResponse(await walk.searched(remote, path, query))
    finally:
        await remote.close()


@api("GET")
async def size(request, **where):
    """A folder's size with all it holds."""
    path = asked(request.GET.get("path", ""))
    _, remote = await _remote(request, where)
    try:
        return JsonResponse(await walk.sized(remote, path))
    finally:
        await remote.close()


def _uploaded(user, sha256: object) -> Path:
    if not isinstance(sha256, str) or not Upload.objects.filter(user=user, blob=sha256).exists():
        raise Refused(400, "invalid_blob")
    return store.path_of(sha256)


@api("POST", confirmed=CHANGES)
async def put(request, **where):
    """A file the user uploaded to PONISTRA written into a folder of the location; one by its
    name already there is refused."""
    data = body(request)
    path = joined(asked(data.get("path", "")), name_of(data.get("name")))
    source = await database(_uploaded)(request.user, data.get("blob"))
    _, remote = await _remote(request, where, Role.EDIT)

    async def parts():
        with source.open("rb") as file:
            while part := await asyncio.to_thread(file.read, store.CHUNK):
                yield part

    try:
        await remote.put(path, parts())
    finally:
        await remote.close()
    return JsonResponse({"path": path}, status=201)


def _fetch(remote: Remote, path: str):
    async def fetch(kept) -> None:
        entry = await remote.stat(path)
        if entry.kind != "file":
            raise Refused(400, "not_a_file")
        held.too_large(entry.size)
        await held.written(kept, remote.chunks(path, 0, entry.size or 0))

    return fetch


@api("GET", "POST")
async def held_shown(request, token, **where):
    """What a file of the location shows of what it holds, as a file of Documents shows it."""
    path = asked(held.path_of(token), root=False)
    _, remote = await _remote(request, where)
    try:
        return await held.of(request, path.rsplit("/", 1)[-1], _fetch(remote, path))
    finally:
        await remote.close()


@api("GET", "POST")
async def held_part(request, token, part, **where):
    path = asked(held.path_of(token), root=False)
    _, remote = await _remote(request, where)
    try:
        return await held.part(request, path.rsplit("/", 1)[-1], part, _fetch(remote, path))
    finally:
        await remote.close()


@api("GET")
async def held_text(request, token, **where):
    path = asked(held.path_of(token), root=False)
    _, remote = await _remote(request, where)
    try:
        return await held.text_of(request, _fetch(remote, path))
    finally:
        await remote.close()


async def _zipped(remote: Remote, chosen: list[tuple[str, Entry]]):
    """The entries chosen, a folder with all it holds, each written as the server sends it; a
    link or anything but a folder or a file is left out, as the browser shows it and no more."""
    archive = zipped.Zipped()
    try:
        waiting = [(path, entry, "") for path, entry in reversed(chosen)]
        while waiting:
            path, entry, folder = waiting.pop()
            if entry.kind == "folder":
                named = archive.named(folder, entry.name)
                archive.folder(named, entry.modified)
                below = ordered(await remote.listed(path))
                waiting.extend((joined(path, each.name), each, named) for each in reversed(below))
            elif entry.kind == "file":
                named = archive.named(folder, entry.name)
                parts = remote.chunks(path, 0, entry.size or 0)
                async for sent in zipped.written(archive, named, entry.modified, entry.size, parts):
                    yield sent
        yield archive.closed()
    finally:
        await remote.close()


@api("GET")
async def zip_of(request, **where):
    """The files and folders chosen as one zip, sent as it is written, a folder with all it
    holds."""
    given = request.GET.getlist("path")
    if not 0 < len(given) <= ZIPPED:
        raise Refused(400, "invalid_paths")
    paths = list(dict.fromkeys(asked(path) for path in given))
    name, remote = await _remote(request, where)
    try:
        chosen = [(path, await remote.stat(path)) for path in paths]
    except BaseException:
        await remote.close()
        raise
    chosen = [(path, entry if path else replace(entry, name=name)) for path, entry in chosen]
    folders = {path.rpartition("/")[0] for path in paths}
    if len(chosen) == 1:
        title = chosen[0][1].name
    elif len(folders) == 1 and (folder := folders.pop()):
        title = folder.rsplit("/", 1)[-1]
    else:
        title = name
    return StreamingHttpResponse(
        _zipped(remote, chosen), content_type="application/zip", headers=zipped.zip_headers(title)
    )


# The views of a location's files, by the route below its address, that a guest's take too.
GUESTS = {
    "files": files,
    "raw": raw,
    "picture": picture,
    "text": text,
    "folder": folder,
    "rename": rename,
    "remove": remove,
    "put": put,
    "zip": zip_of,
    "stat": stat,
    "mode": mode,
    "owner": owner,
    "search": search,
    "size": size,
    "held/<str:token>/shown": held_shown,
    "held/<str:token>/text": held_text,
    "held/<str:token>/shown/<str:part>": held_part,
}
