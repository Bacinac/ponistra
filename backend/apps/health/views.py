"""The installation's health as an administrator reads it (D15, S1): the version, the services
the backend reaches, the snapshots, the room left and what waits in the queues."""

import json
import os
import secrets
import shutil
import socket
import ssl
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.models import Sum
from django.http import JsonResponse

from apps.actions.models import RunItem
from apps.backups import backups, offsite
from apps.blobs import store
from apps.blobs.models import Blob
from apps.core.api import api
from apps.jobs.models import Job
from apps.meetings import relay
from apps.meetings.models import Relay
from apps.search import extraction, ocr
from apps.search.models import BlobText
from apps.users.accounts import administrator

from .models import Problem

# Each service the backend reaches, and its page that answers while it works.
SERVICES = {
    "converter": ("CONVERTER_URL", "/health"),
    "printer": ("PRINTER_URL", "/health"),
    "ocr": ("OCR_URL", "/health"),
    "meetings": ("LIVEKIT_URL", "/"),
}
TIMEOUT = 3
RELAY_PORT = 443
TLS = ssl.create_default_context()
STUN_COOKIE = 0x2112A442


def answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT):
            return True
    except OSError:
        return False


def relays(name: str) -> bool:
    """Whether the relay answers a STUN binding under its name and certificate, the way a browser
    outside reaches it, so a stale address or a certificate that did not renew shows."""
    transaction = secrets.token_bytes(12)
    try:
        with (
            socket.create_connection((name, RELAY_PORT), timeout=TIMEOUT) as raw,
            TLS.wrap_socket(raw, server_hostname=name) as tls,
        ):
            tls.sendall(struct.pack("!HHI", 0x0001, 0, STUN_COOKIE) + transaction)
            answer = tls.makefile("rb").read(20)
    except OSError:
        return False
    return answer[:2] == b"\x01\x01" and answer[8:] == transaction


def reached(outside: Relay) -> bool:
    """Whether the external relay gives those joining a meeting what they go through it with."""
    try:
        relay.servers(outside)
    except relay.Unavailable:
        return False
    return True


def services() -> dict:
    checks = {
        name: partial(answers, getattr(settings, setting) + page)
        for name, (setting, page) in SERVICES.items()
    }
    if settings.TURN:
        checks["relay"] = partial(relays, settings.TURN)
    if (outside := relay.setting()).provider:
        checks["outside"] = partial(reached, outside)
    with ThreadPoolExecutor(len(checks)) as pool:
        found = {name: pool.submit(check) for name, check in checks.items()}
        return {"database": True, **{name: each.result() for name, each in found.items()}}


def snapshots() -> dict:
    try:
        found = backups.snapshots()
    except backups.Failed as failed:
        return {"error": str(failed), "late": True}
    return {
        "count": len(found),
        "newest": max((snapshot["time"] for snapshot in found), default=None),
        "due": backups.due(found),
        "late": backups.late(found),
    }


def archive() -> dict:
    try:
        return backups.archive()
    except backups.Failed as failed:
        return {"at": None, "error": str(failed), "late": True}


def disks() -> list[dict]:
    """Each disk the files and the snapshots are kept on, with what it holds."""
    places = [("files", store.root())]
    repository = os.environ.get("RESTIC_REPOSITORY", "")
    if repository.startswith("/"):
        places.append(("snapshots", Path(repository)))
    found: dict[int, dict] = {}
    for holds, path in places:
        usage = shutil.disk_usage(path)
        disk = found.setdefault(
            path.stat().st_dev, {"holds": [], "free": usage.free, "total": usage.total}
        )
        disk["holds"].append(holds)
    return list(found.values())


def stored() -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        [database] = cursor.fetchone()
    return {
        "database": database,
        "files": Blob.objects.aggregate(size=Sum("size"))["size"] or 0,
        "dead": store.dead_bytes(),
    }


def queues() -> dict:
    return {
        "jobs": Job.objects.filter(state__in=[Job.State.WAITING, Job.State.RUNNING]).count(),
        "ocr": ocr.waiting().count(),
        "text": extraction.waiting().count(),
        "unread": BlobText.objects.exclude(failed="").count(),
        "batches": RunItem.objects.filter(state=RunItem.State.WAITING).count(),
    }


@api("GET")
def health(request):
    administrator(request)
    local = snapshots()
    return JsonResponse(
        {
            "version": json.loads(settings.REVISION_FILE.read_text())["version"],
            "services": services(),
            "snapshots": local,
            "archive": archive(),
            "offsite": {
                "locked": offsite.LOCKED,
                "setting": offsite.describe(offsite.offsite(), local.get("newest")),
            },
            "disks": disks(),
            "stored": stored(),
            "queues": queues(),
            "problems": [
                {"key": problem.key, "since": problem.since, "detail": problem.detail}
                for problem in Problem.objects.exclude(raised_at=None).order_by("since")
            ],
        }
    )
