"""Files' own: the folders a user keeps at hand of any source, and the transfers under way
between sources and lately ended."""

from django.http import HttpResponse, JsonResponse

from apps.core.api import Refused, api, body
from apps.jobs.models import Job
from apps.jobs.views import describe as described_job

from .models import Bookmark
from .sources import KEY

BOOKMARKS = 200
NAME = 200
PATH = 4096
SHOWN = 50


def _described(bookmark: Bookmark) -> dict:
    return {
        "id": bookmark.pk,
        "source": bookmark.source,
        "path": bookmark.path,
        "name": bookmark.name,
    }


def _text(given: object, most: int, error: str, empty: bool = False) -> str:
    if not isinstance(given, str) or len(given) > most or "\0" in given:
        raise Refused(400, error)
    if not empty and not given.strip():
        raise Refused(400, error)
    return given.strip() if not empty else given


@api("GET", "POST")
def bookmarks(request):
    kept = Bookmark.objects.filter(user=request.user)
    if request.method == "GET":
        return JsonResponse({"bookmarks": [_described(each) for each in kept]})
    data = body(request)
    if kept.count() >= BOOKMARKS:
        raise Refused(409, "too_many_bookmarks")
    made = Bookmark.objects.create(
        user=request.user,
        source=_text(data.get("source"), KEY, "invalid_source"),
        path=_text(data.get("path", ""), PATH, "invalid_path", empty=True),
        name=_text(data.get("name"), NAME, "invalid_name"),
    )
    return JsonResponse(_described(made), status=201)


@api("DELETE")
def bookmark(request, pk):
    if not Bookmark.objects.filter(user=request.user, pk=pk).delete()[0]:
        raise Refused(404, "not_found")
    return HttpResponse(status=204)


def _transfer(job: Job) -> dict:
    given = job.parameters
    return {
        **described_job(job),
        "from": given.get("from"),
        "from_name": given.get("from_name"),
        "to": given.get("to"),
        "to_name": given.get("to_name"),
        "path": given.get("path"),
        "paths": len(given.get("paths", [])),
        "move": given.get("move", False),
        "queued_at": job.queued_at,
    }


@api("GET")
def transfers(request):
    """The user's transfers, the latest first, until the queue forgets them."""
    found = Job.objects.filter(user=request.user, kind="transfer").order_by("-queued_at")
    return JsonResponse({"transfers": [_transfer(job) for job in found[:SHOWN]]})
