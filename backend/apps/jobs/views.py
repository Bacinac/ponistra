from django.http import HttpResponse, JsonResponse

from apps.blobs.views import serve
from apps.core.api import Refused, api, body

from . import work
from .models import Job
from .registry import EXPORTS, KINDS


def describe(job: Job) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "state": job.state,
        "status": job.status,
        "error": job.error or None,
        "answer": job.answer,
        "file": job.file_id is not None,
        "cancellable": job.state == Job.State.WAITING
        or (job.state == Job.State.RUNNING and KINDS[job.kind].saves),
    }


def _own(request, pk) -> Job:
    job = Job.objects.filter(pk=pk, user=request.user).first()
    if job is None:
        raise Refused(404, "not_found")
    return job


@api("POST", visitors=True)
def jobs(request):
    data = body(request)
    if request.user.visitor and data.get("kind") not in EXPORTS:
        raise Refused(403, "visitors_not_allowed")
    return JsonResponse(describe(work.start(request, str(data.get("kind")), data)), status=202)


@api("GET", "DELETE", visitors=True)
def job(request, pk):
    found = _own(request, pk)
    if request.method == "DELETE":
        if not work.cancel(found):
            raise Refused(409, "not_cancellable")
        return HttpResponse(status=204)
    return JsonResponse(describe(found))


@api("GET", visitors=True)
def file(request, pk):
    found = _own(request, pk)
    if found.file is None:
        raise Refused(404, "not_found")
    return serve(request, found.file, found.name)
