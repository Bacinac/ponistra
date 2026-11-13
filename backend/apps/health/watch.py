"""The installation watched while it runs (U7): every few minutes the same checks an
administrator reads on the health page, and a problem that holds is written to the journal and
told to the administrators, rather than found later in the log."""

from collections.abc import Callable
from datetime import timedelta
from logging import getLogger

from anyio import sleep
from django.db import connection, transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.actions.models import ActionRun, RunItem
from apps.backups import offsite
from apps.core.asyncdb import database
from apps.identity.models import Provider
from apps.jobs.models import Job
from apps.journal import entries
from apps.journal.entries import Kind
from apps.push import notices
from apps.push.models import Notice
from apps.search import extraction, ocr
from apps.search.models import BlobText, PdfOcr
from apps.users.models import User

from . import views
from .models import Problem

log = getLogger(__name__)

EVERY = timedelta(minutes=5)
# A queue stalls when it has work waiting and none of it finished for this long.
STALL = timedelta(hours=1)
# How long a problem holds before the administrators hear of it: a service restarting or a
# queue between two long items is not one, nor snapshots waiting for the base an update takes.
GRACE = {
    "service": timedelta(minutes=10),
    "queue": STALL,
    "snapshots": timedelta(hours=1),
    "archive": timedelta(hours=1),
    "source": timedelta(hours=2),
}
# The least share of a disk left free.
FREE = 0.1
LOCK = 0x6E4C7A11

QUEUES: dict[str, tuple[Callable[[], QuerySet], Callable[[], QuerySet]]] = {
    "jobs": (
        lambda: Job.objects.filter(state=Job.State.WAITING),
        lambda: Job.objects.filter(finished_at__gte=timezone.now() - STALL),
    ),
    "ocr": (
        ocr.waiting,
        lambda: PdfOcr.objects.filter(finished_at__gte=timezone.now() - STALL),
    ),
    "text": (
        extraction.waiting,
        lambda: BlobText.objects.filter(extracted_at__gte=timezone.now() - STALL),
    ),
    "batches": (
        lambda: RunItem.objects.filter(
            state=RunItem.State.WAITING, run__state=ActionRun.State.RUNNING
        ),
        lambda: RunItem.objects.filter(finished_at__gte=timezone.now() - STALL),
    ),
}


def found() -> dict[str, dict]:
    """What is wrong now, by its key, with what the administrator is told of it."""
    problems: dict[str, dict] = {}
    for name, answers in views.services().items():
        if not answers:
            problems[f"service:{name}"] = {}
    local = views.snapshots()
    if local["late"]:
        problems["snapshots"] = {"error": local.get("error", "")}
    archived = views.archive()
    if archived["late"]:
        problems["archive"] = {"error": archived["error"]}
    setting = offsite.describe(offsite.offsite(), local.get("newest"))
    if setting is not None and (setting["late"] or setting["lost"]):
        problems["offsite"] = {"error": setting["error"]}
    for disk in views.disks():
        if disk["free"] < disk["total"] * FREE:
            problems[f"disk:{'+'.join(disk['holds'])}"] = {
                "free": disk["free"],
                "total": disk["total"],
            }
    for name, (waiting, finished) in QUEUES.items():
        if waiting().exists() and not finished().exists():
            problems[f"queue:{name}"] = {}
    for source in Provider.objects.filter(enabled=True).exclude(error=""):
        problems[f"source:{source.name}"] = {"error": source.error}
    return problems


def grace(key: str) -> timedelta:
    return GRACE.get(key.split(":")[0], timedelta(0))


def raised(problem: Problem) -> None:
    entries.wrote(Kind.PROBLEM, problem=problem.key, **problem.detail)
    administrators = User.objects.filter(is_staff=True, is_active=True).values_list("pk", flat=True)
    notices.tell(list(administrators), Notice.Kind.HEALTH, {"problem": problem.key})


def checked() -> None:
    current = found()
    now = timezone.now()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK])
        kept = {problem.key: problem for problem in Problem.objects.all()}
        for key, detail in current.items():
            problem = kept.get(key) or Problem.objects.create(key=key, since=now, detail=detail)
            if problem.raised_at is None and now - problem.since >= grace(key):
                problem.raised_at, problem.detail = now, detail
                problem.save(update_fields=["raised_at", "detail"])
                raised(problem)
        for key, problem in kept.items():
            if key not in current:
                if problem.raised_at is not None:
                    entries.wrote(Kind.RESOLVED, problem=key)
                problem.delete()


async def watch() -> None:
    while True:
        try:
            await database(checked, own_thread=True)()
        except Exception:
            log.exception("health: the watch failed")
        await sleep(EVERY.total_seconds())
