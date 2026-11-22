"""Files opened from the computer while nobody is signed in (D53): the browser becomes a visitor of
its own, each file is placed as an upload is, in no folder, and the visitor only reads it. The
visitor and its files go when its window closes, OPENED_FOR after it came at the latest, or pass to
whoever signs in from that browser and takes them."""

import hashlib
import secrets
from datetime import timedelta
from logging import getLogger

from anyio import sleep
from django.contrib.auth import logout as end_session
from django.db import transaction
from django.db.models import F, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.access import visitors
from apps.access.models import Grant, Role
from apps.blobs import store
from apps.blobs.models import Blob
from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database, notify
from apps.imports import convert, placed
from apps.jobs.kinds import Kind
from apps.jobs.models import Job
from apps.users.models import User, policy
from apps.users.sessions import client_ip

from .models import Node, Opening
from .views import describe, described

log = getLogger(__name__)

OPENED_FOR = timedelta(hours=1)
EVERY = timedelta(minutes=5)
MOST_BYTES = 100 * 1024**2
# Files one address may open within OPENED_FOR, across the visitors it became.
MOST_FILES = 30
JOBS = "jobs"


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _opening(user) -> Opening | None:
    if not user.is_authenticated or not user.visitor:
        return None
    return Opening.objects.filter(visitor=user).first()


def _admitted(request) -> str | None:
    """The address the file comes from, refused where it opened too many of late."""
    address = client_ip(request)
    since = timezone.now() - OPENED_FOR
    opened = Opening.objects.filter(address=address, created_at__gte=since).aggregate(
        files=Sum("files")
    )["files"]
    if (opened or 0) >= MOST_FILES:
        raise Refused(429, "too_many_openings")
    return address


def _received(request) -> JsonResponse:
    if not policy().opening:
        raise Refused(403, "opening_off")
    user = request.user
    opening = _opening(user)
    if user.is_authenticated and opening is None:
        raise Refused(400, "signed_in")
    try:
        size = int(request.headers.get("Content-Length", ""))
    except ValueError:
        raise Refused(411, "length_required") from None
    if size > MOST_BYTES:
        raise Refused(413, "too_large")
    address = _admitted(request)
    key = None
    if opening is None:
        key = secrets.token_urlsafe(32)
        with transaction.atomic():
            visitor = User.everyone.create_user(
                f"opened-{secrets.token_hex(8)}@outside.invalid", None, visitor=True
            )
            opening = Opening.objects.create(visitor=visitor, key=_digest(key), address=address)
        visitors.signed_in_as(request, visitor, "opened")
    try:
        blob = store.put(request)
    except store.TooLarge:
        raise Refused(413, "too_large") from None
    Opening.objects.filter(pk=opening.pk).update(files=F("files") + 1, bytes=F("bytes") + blob.size)
    title, extension = placed.named(request.GET.get("name", ""))
    job = Job.objects.create(
        user=opening.visitor,
        kind="opened",
        parameters={"blob": blob.sha256, "title": title, "extension": extension},
        source_id=blob.sha256,
    )
    notify(JOBS)
    return JsonResponse({"job": job.pk, **({"key": key} if key else {})}, status=202)


@api("POST", signed_in=False, visitors=True)
async def opened(request):
    """Takes a file opened from the computer by someone not signed in, its name in `name`; answers
    the job that places it and, the first time, the key that lets whoever signs in take it."""
    return await database(_received)(request)


def _asked(request, data: dict) -> dict:
    raise Refused(400, "unknown_job")


def _done(user, parameters: dict) -> dict:
    """The file in no folder, as an upload is placed, for its visitor to read only."""
    blob = Blob.objects.get(pk=parameters["blob"])
    try:
        node, _ = placed.placed(
            blob, None, parameters["title"], parameters["extension"], user, None, unplaced=True
        )
    except convert.Unavailable:
        raise Refused(503, "converter_unavailable") from None
    Grant.objects.filter(node=node, user=user).update(role=Role.READ, download=True)
    revoke()
    return describe(node)


KINDS = {"opened": Kind(_asked, _done, saves=False)}


def _forget(opening: Opening) -> None:
    with transaction.atomic():
        Node.objects.filter(created_by_id=opening.visitor_id).delete()
        User.everyone.filter(pk=opening.visitor_id).delete()
    revoke()
    store.collect_later()


@api("POST", visitors=True)
def closed(request):
    """The window that showed the files closed: they and their visitor go, and the browser is
    signed out."""
    opening = _opening(request.user)
    if opening is None:
        raise Refused(400, "not_opened")
    end_session(request)
    _forget(opening)
    return HttpResponse(status=204)


@api("POST")
def taken(request):
    """Gives whoever signed in the files their browser opened before, by the key it kept: each
    stays in no folder, theirs, for them to place."""
    if request.user.visitor:
        raise Refused(403, "visitors_not_allowed")
    key = body(request).get("key")
    since = timezone.now() - OPENED_FOR
    found = (
        Opening.objects.filter(key=_digest(key), created_at__gte=since).first()
        if isinstance(key, str)
        else None
    )
    if found is None:
        raise Refused(404, "opening_gone")
    user = request.user
    with transaction.atomic():
        nodes = list(Node.objects.filter(created_by_id=found.visitor_id, unplaced=True))
        Node.objects.filter(pk__in=[node.pk for node in nodes]).update(
            created_by=user, updated_by=user
        )
        Grant.objects.filter(node__in=nodes, user=found.visitor_id).update(
            user=user, role=Role.OWN, download=True
        )
        User.everyone.filter(pk=found.visitor_id).delete()
    revoke()
    return JsonResponse({"nodes": described(nodes)})


def forgotten() -> int:
    """Removes the visitors that came longer than OPENED_FOR ago, and their files."""
    gone = list(Opening.objects.filter(created_at__lt=timezone.now() - OPENED_FOR))
    for opening in gone:
        _forget(opening)
    if gone:
        log.info("removed %d openings of files by someone not signed in", len(gone))
    return len(gone)


async def forgetting() -> None:
    while True:
        try:
            await database(forgotten, own_thread=True)()
        except Exception:
            log.exception("forgetting files opened by someone not signed in failed")
        await sleep(EVERY.total_seconds())
