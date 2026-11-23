"""Docker on the servers of the network an administrator set up as locations (D55): the host's
containers, images, volumes and networks, and the stacks among a location's folders. Each view
waits on the host, so each is a coroutine; each that changes something asks a fresh confirmation."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse

from apps.access.models import Role
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.core.sealed import seal
from apps.locations import reach as locations
from apps.locations import sftp
from apps.locations.models import Location
from apps.locations.remote import Failed, asked

from . import compose, live, reach
from .engine import Refusal, frames, part, path_of
from .models import Host

CHANGES = ("POST", "DELETE")
KINDS = ("containers", "images", "volumes", "networks")
PRUNED = {
    "containers": ("/containers/prune", None),
    "images": ("/images/prune", {"dangling": ["false"]}),
    "volumes": ("/volumes/prune", {"all": ["true"]}),
    "networks": ("/networks/prune", None),
    "builder": ("/build/prune", None),
}
ACTIONS = ("start", "stop", "restart")
TAIL = 500
MOST_TAIL = 10_000
# Docker's own networks, which are never removed.
BUILT_IN = {"bridge", "host", "none"}


def _refused(refused: Failed) -> JsonResponse:
    shown = {"error": refused.error}
    if message := getattr(refused, "message", ""):
        shown["detail"] = message
    return JsonResponse(shown, status=refused.status)


def answered(view):
    """What the daemon or compose said as it refused is shown to the administrator."""

    async def answering(request, *args, **kwargs):
        try:
            return await view(request, *args, **kwargs)
        except (Refusal, compose.StackFailed) as refused:
            return _refused(refused)

    answering.__name__ = view.__name__
    answering.__doc__ = view.__doc__
    return answering


def _described(held: Host) -> dict:
    found = held.location
    return {
        "location": str(found.pk),
        "name": found.name,
        "address": f"{found.username}@{found.host}"
        + (f":{found.port}" if found.port != 22 else ""),
        "public_key": held.public_key,
        "authorized": reach.authorized(held.public_key),
    }


def _listed(user) -> dict:
    if not user.is_staff:
        raise Refused(403, "forbidden")
    roles = locations.roles(user)
    held = Host.objects.select_related("location").filter(location__in=roles)
    hosts = sorted((_described(each) for each in held), key=lambda each: each["name"].lower())
    taken = {each["location"] for each in hosts}
    candidates = Location.objects.filter(
        pk__in=[pk for pk, role in roles.items() if role == Role.OWN],
        kind=Location.Kind.SFTP,
    ).order_by("name")
    return {
        "hosts": hosts,
        "candidates": [
            {"id": str(each.pk), "name": each.name}
            for each in candidates
            if str(each.pk) not in taken
        ],
    }


def _made(user, pk) -> dict:
    if not user.is_staff:
        raise Refused(403, "forbidden")
    found, _ = locations.location(user, pk, Role.OWN)
    if found.kind != Location.Kind.SFTP:
        raise Refused(400, "docker_needs_sftp")
    if Host.objects.filter(location=found).exists():
        raise Refused(409, "docker_host_exists")
    installation = urlsplit(settings.PUBLIC_URL).hostname or "ponistra"
    secret, public = sftp.made_key(f"ponistra-docker@{installation}")
    held = Host.objects.create(
        location=found, secret=seal(reach.SEALED, secret), public_key=public, created_by=user
    )
    held.location = found
    return _described(held)


@api("GET", "POST", confirmed=CHANGES)
async def hosts(request):
    """The Docker hosts the administrator reaches, and the SFTP locations of theirs that may become
    one; a new one gets a key of its own, whose line the server's `authorized_keys` takes."""
    user = request.user
    if request.method == "GET":
        return JsonResponse(await database(_listed)(user))
    given = body(request).get("location")
    if not isinstance(given, str):
        raise Refused(400, "invalid_location")
    made = await database(_made)(user, given)
    live.followed()
    return JsonResponse(made, status=201)


def _forgotten(user, pk) -> None:
    reach.host(user, pk, Role.OWN).delete()


@api("GET", "DELETE", confirmed=CHANGES)
@answered
async def host(request, pk):
    """The host and its daemon's version, which tries the key; DELETE forgets the key, the
    location staying as it was."""
    if request.method == "DELETE":
        await database(_forgotten)(request.user, pk)
        live.followed()
        return HttpResponse(status=204)
    held, engine = await reach.reached(request.user, pk)
    version = await engine.get("/version")
    info = await engine.get("/info")
    return JsonResponse(
        _described(held)
        | {
            "version": version.get("Version", ""),
            "api": version.get("ApiVersion", ""),
            "os": info.get("OperatingSystem", ""),
            "arch": version.get("Arch", ""),
            "cpus": info.get("NCPU"),
            "memory": info.get("MemTotal"),
            "containers": {
                "running": info.get("ContainersRunning", 0),
                "stopped": info.get("ContainersStopped", 0),
                "paused": info.get("ContainersPaused", 0),
            },
            "images": info.get("Images", 0),
        }
    )


def _when(stamp) -> str | None:
    if isinstance(stamp, int | float) and stamp > 0:
        return datetime.fromtimestamp(stamp, UTC).isoformat()
    if isinstance(stamp, str) and stamp and not stamp.startswith("0001"):
        return stamp
    return None


def _ports(found: dict) -> list[str]:
    shown = set()
    for each in found.get("Ports") or []:
        if each.get("PublicPort"):
            address = each.get("IP") or "0.0.0.0"
            shown.add(f"{address}:{each['PublicPort']}->{each['PrivatePort']}/{each['Type']}")
    return sorted(shown)


def _container(found: dict) -> dict:
    labels = found.get("Labels") or {}
    names = found.get("Names") or [""]
    return {
        "id": found.get("Id", ""),
        "name": names[0].lstrip("/"),
        "image": found.get("Image", ""),
        "state": found.get("State", ""),
        "status": found.get("Status", ""),
        "created": _when(found.get("Created")),
        "project": labels.get("com.docker.compose.project", ""),
        "service": labels.get("com.docker.compose.service", ""),
        "folder": labels.get("com.docker.compose.project.working_dir", ""),
        "ports": _ports(found),
    }


def _image(found: dict, used: set[str]) -> dict:
    tags = [each for each in found.get("RepoTags") or [] if each != "<none>:<none>"]
    return {
        "id": found.get("Id", ""),
        "tags": tags,
        "size": found.get("Size"),
        "created": _when(found.get("Created")),
        "used": found.get("Id", "") in used,
    }


def _volume(found: dict, used: set[str]) -> dict:
    labels = found.get("Labels") or {}
    return {
        "id": found.get("Name", ""),
        "name": found.get("Name", ""),
        "driver": found.get("Driver", ""),
        "created": _when(found.get("CreatedAt")),
        "project": labels.get("com.docker.compose.project", ""),
        "used": found.get("Name", "") in used,
    }


def _network(found: dict, used: set[str]) -> dict:
    labels = found.get("Labels") or {}
    name = found.get("Name", "")
    return {
        "id": found.get("Id", ""),
        "name": name,
        "driver": found.get("Driver", ""),
        "scope": found.get("Scope", ""),
        "created": _when(found.get("Created")),
        "project": labels.get("com.docker.compose.project", ""),
        "used": found.get("Id", "") in used or name in BUILT_IN,
        "built_in": name in BUILT_IN,
    }


@api("GET")
@answered
async def listed(request, pk, kind):
    """What the host holds of one kind, each image, volume and network with whether a container
    uses it."""
    if kind not in KINDS:
        raise Refused(404, "not_found")
    _, engine = await reach.reached(request.user, pk)
    containers = await engine.get("/containers/json", all="true")
    if kind == "containers":
        shown = [_container(each) for each in containers]
        return JsonResponse({"containers": sorted(shown, key=lambda each: each["name"])})
    if kind == "images":
        used = {each.get("ImageID", "") for each in containers}
        found = await engine.get("/images/json")
        shown = [_image(each, used) for each in found]
        return JsonResponse({"images": sorted(shown, key=lambda each: each["tags"] or ["~"])})
    details = await asyncio.gather(
        *(engine.get(f"/containers/{part(each['Id'])}/json") for each in containers)
    )
    if kind == "volumes":
        used = {
            mount.get("Name", "")
            for each in details
            for mount in each.get("Mounts") or []
            if mount.get("Type") == "volume"
        }
        found = (await engine.get("/volumes")).get("Volumes") or []
        shown = [_volume(each, used) for each in found]
    else:
        used = {
            network.get("NetworkID", "")
            for each in details
            for network in ((each.get("NetworkSettings") or {}).get("Networks") or {}).values()
        }
        shown = [_network(each, used) for each in await engine.get("/networks")]
    return JsonResponse({kind: sorted(shown, key=lambda each: each["name"])})


@api("DELETE", confirmed=CHANGES)
@answered
async def removed(request, pk, kind, ref):
    """One container (stopped), image, volume or network removed, as the daemon allows."""
    if kind not in KINDS:
        raise Refused(404, "not_found")
    _, engine = await reach.reached(request.user, pk, Role.EDIT)
    await engine.delete(f"/{kind}/{part(ref)}")
    return HttpResponse(status=204)


@api("POST", confirmed=CHANGES)
@answered
async def pruned(request, pk):
    """What nothing uses of one kind removed from the host, the same the lists mark unused: stopped
    containers, images and volumes (named ones too) no container holds, networks without one,
    the build cache."""
    kind = body(request).get("kind")
    if kind not in PRUNED:
        raise Refused(400, "invalid_kind")
    _, engine = await reach.reached(request.user, pk, Role.EDIT)
    path, filters = PRUNED[kind]
    found = await engine.post(path, filters=filters and json.dumps(filters)) or {}
    removed = next(
        (
            found.get(key) or []
            for key in (
                "ContainersDeleted",
                "ImagesDeleted",
                "VolumesDeleted",
                "NetworksDeleted",
                "CachesDeleted",
            )
            if key in found
        ),
        [],
    )
    return JsonResponse({"removed": len(removed), "reclaimed": found.get("SpaceReclaimed", 0)})


@api("POST", confirmed=CHANGES)
@answered
async def acted(request, pk, ref, action):
    """A container started, stopped or restarted."""
    if action not in ACTIONS:
        raise Refused(404, "not_found")
    _, engine = await reach.reached(request.user, pk, Role.EDIT)
    await engine.post(f"/containers/{part(ref)}/{action}")
    return HttpResponse(status=204)


async def _logged(engine, ref: str, tail: int, tty: bool) -> AsyncIterator[bytes]:
    query = {
        "follow": "true",
        "stdout": "true",
        "stderr": "true",
        "tail": tail,
        "timestamps": "true",
    }
    async with engine.answer("GET", path_of(f"/containers/{part(ref)}/logs", query)) as (
        answer,
        _,
    ):
        left = b""
        try:
            async for data in answer.body():
                if tty:
                    yield data
                    continue
                found, left = frames(left + data)
                for _, text in found:
                    yield text
        except asyncio.IncompleteReadError, OSError:
            return


@api("GET")
@answered
async def logs(request, pk, ref):
    """The container's log as it is written, its last lines first, each after its time."""
    try:
        tail = min(int(request.GET.get("tail", TAIL)), MOST_TAIL)
    except ValueError:
        raise Refused(400, "invalid_tail") from None
    _, engine = await reach.reached(request.user, pk)
    found = await engine.get(f"/containers/{part(ref)}/json")
    tty = bool((found.get("Config") or {}).get("Tty"))
    return StreamingHttpResponse(
        _logged(engine, ref, max(tail, 0), tty),
        content_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _folder(request, pk) -> tuple:
    path = asked(request.GET.get("path"))
    held, engine = await reach.reached(
        request.user, pk, Role.EDIT if request.method == "POST" else Role.READ
    )
    return held, engine, path


@api("GET", "POST", confirmed=("POST",))
@answered
async def stack(request, pk):
    """The folder as a stack: its compose file and its containers as compose finds them; POST
    runs compose there with one verb, its output streamed line by line as JSON."""
    verb = body(request).get("verb") if request.method == "POST" else None
    if request.method == "POST" and verb not in compose.VERBS:
        raise Refused(400, "invalid_verb")
    held, engine, path = await _folder(request, pk)
    target = engine.target
    folder = compose.folder_of(held.location.path, path)
    if verb is not None:

        async def sent():
            async for each in compose.ran(target, folder, verb):
                yield json.dumps(each).encode() + b"\n"

        return StreamingHttpResponse(
            sent(),
            content_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
    remote = await locations.reached(held.location)
    names = {each.name for each in await remote.listed(path) if each.kind == "file"}
    file = next((each for each in compose.FILES if each in names), None)
    if file is None:
        return JsonResponse({"file": None, "containers": [], "said": []})
    containers, said = await compose.listed(target, folder)
    return JsonResponse({"file": file, "containers": containers, "said": said})
