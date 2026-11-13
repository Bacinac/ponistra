import json
from collections import defaultdict, deque
from logging import getLogger
from threading import Lock
from time import monotonic

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from .api import Refused, api, body

log = getLogger(__name__)


@require_GET
def ping(request):
    connection.ensure_connection()
    return JsonResponse({"ok": True})


@require_GET
def version(request):
    try:
        release = json.loads(settings.REVISION_FILE.read_text())["version"]
    except FileNotFoundError:
        return JsonResponse(
            {"error": f"{settings.REVISION_FILE} is missing; run scripts/install-hooks.sh"},
            status=503,
        )
    return JsonResponse({"version": release})


def shipped() -> str:
    """The release this server runs, empty on a tree that has no revision file yet."""
    try:
        return json.loads(settings.REVISION_FILE.read_text())["version"]
    except FileNotFoundError:
        return ""


# A page's own report, kept to a size a log reads; a stack's frames past this tell nothing more.
CRASH_FIELD = 8000
# The log keeps a few tens of megabytes: anyone may report, so nobody may fill it.
CRASHES_A_USER = (5, 60.0)
CRASHES_OF_GUESTS = (10, 3600.0)
_reported: dict[str, deque[float]] = defaultdict(deque)
_reporting = Lock()


def _admitted(reporter: str, most: int, within: float) -> bool:
    now = monotonic()
    with _reporting:
        times = _reported[reporter]
        while times and now - times[0] > within:
            times.popleft()
        if len(times) >= most:
            return False
        times.append(now)
        return True


@api("POST", signed_in=False, visitors=True)
def crash(request):
    """What broke a page in the browser, which only the server's log keeps. Nothing the page sends
    begins a line of the log: a single line stays one, each line of a longer one is indented."""
    user = request.user.pk if request.user.is_authenticated else None
    if not _admitted(
        f"user{user}" if user else "guests", *(CRASHES_A_USER if user else CRASHES_OF_GUESTS)
    ):
        raise Refused(429, "too_many_crashes")
    data = body(request)

    def given(name: str) -> str:
        return str(data.get(name, ""))[:CRASH_FIELD]

    def line(text: str) -> str:
        return " ".join(text.splitlines())

    def lines(text: str) -> str:
        return "".join(f"\n    {each.strip()}" for each in text.splitlines() if each.strip())

    log.error(
        "page crashed at %s for user %s on %s (server %s): %s%s\ncomponents:%s\nqueries:%s",
        line(given("path")),
        user or "guest",
        line(request.headers.get("User-Agent", "")[:CRASH_FIELD]),
        shipped() or "without revision file",
        line(given("message")),
        lines(given("stack")),
        lines(given("components")),
        lines(given("queries")),
    )
    return HttpResponse(status=204)


@api("POST", signed_in=False, visitors=True)
def crossed(request):
    """An answer the page received for another of its requests, which a proxy between the browser
    and this server sent in place of the one asked."""
    user = request.user.pk if request.user.is_authenticated else None
    if not _admitted(
        f"user{user}" if user else "guests", *(CRASHES_A_USER if user else CRASHES_OF_GUESTS)
    ):
        raise Refused(429, "too_many_crashes")
    data = body(request)

    def given(name: str) -> str:
        return " ".join(str(data.get(name, ""))[:CRASH_FIELD].splitlines())

    log.error(
        "answer crossed for user %s on %s: asked %s, answered %s",
        user or "guest",
        " ".join(request.headers.get("User-Agent", "")[:CRASH_FIELD].splitlines()),
        given("asked"),
        given("answered"),
    )
    return HttpResponse(status=204)
