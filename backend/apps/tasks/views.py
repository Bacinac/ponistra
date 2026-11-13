from datetime import date, timedelta

from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.core.api import Refused, api, body

from .models import Task

# How long a task done stays in the list before it is only in the database.
DONE_SHOWN = timedelta(days=30)


def describe(task: Task) -> dict:
    return {
        "id": task.pk,
        "text": task.text,
        "due": task.due.isoformat() if task.due else None,
        "done": task.done_at is not None,
        "done_at": task.done_at,
        "source": {"kind": task.source_kind, "label": task.source_label, "link": task.source_link}
        if task.source_kind
        else None,
        "changed_at": task.changed_at,
    }


def filled(task: Task, data: dict) -> None:
    if "text" in data:
        task.text = " ".join(str(data.get("text") or "").split())[:1000]
        if not task.text:
            raise Refused(400, "text_required")
    if "due" in data:
        given = data["due"]
        if given is None or given == "":
            task.due = None
        else:
            try:
                task.due = date.fromisoformat(str(given))
            except ValueError:
                raise Refused(400, "invalid_due") from None
    if "done" in data:
        done = bool(data["done"])
        if done and task.done_at is None:
            task.done_at = timezone.now()
        elif not done:
            task.done_at = None
    if "source" in data:
        given = data["source"]
        if given is None:
            task.source_kind = task.source_label = task.source_link = ""
        else:
            if (
                not isinstance(given, dict)
                or given.get("kind") not in Task.Source.values
                or not str(given.get("link", "")).startswith("/")
                or "//" in str(given.get("link", ""))[:2]
            ):
                raise Refused(400, "invalid_source")
            task.source_kind = given["kind"]
            task.source_label = str(given.get("label") or "").strip()[:300]
            task.source_link = str(given["link"])[:500]


def listed(user) -> list[Task]:
    found = Task.objects.filter(owner=user).filter(done_at__isnull=True) | Task.objects.filter(
        owner=user, done_at__gte=timezone.now() - DONE_SHOWN
    )
    return sorted(
        found.distinct(), key=lambda each: (each.done_at is not None, each.due or date.max, each.pk)
    )


@api("GET", "POST")
def tasks(request):
    """The user's one list: what is open, and what was done lately."""
    if request.method == "GET":
        return JsonResponse({"tasks": [describe(each) for each in listed(request.user)]})
    made = Task(owner=request.user)
    filled(made, {"text": "", **body(request)})
    made.save()
    return JsonResponse(describe(made), status=201)


@api("GET", "PATCH", "DELETE")
def task(request, pk):
    found = Task.objects.filter(owner=request.user, pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        found.delete()
        return HttpResponse(status=204)
    if request.method == "PATCH":
        filled(found, body(request))
        found.save()
    return JsonResponse(describe(found))
