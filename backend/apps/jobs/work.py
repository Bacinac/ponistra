"""The queue of jobs, which the backend goes through in its own process, JOBS_AT_ONCE at a time,
in the order they were handed over. A job a restart cut off runs again, once; a second cut is
taken as the job's own doing, so that a job that brings the server down cannot do it forever."""

import io
from logging import getLogger

from anyio import create_task_group
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.blobs import store
from apps.core.api import Refused
from apps.core.asyncdb import database, drain, notify

from .kinds import Saved, running
from .models import Job
from .registry import KINDS

log = getLogger(__name__)

CHANNEL = "jobs"
TRIES = 2


def start(request, kind: str, data: dict) -> Job:
    """Checks what the user asks for and queues the job to do it."""
    if kind not in KINDS:
        raise Refused(400, "unknown_job")
    parameters = KINDS[kind].asked(request, data)
    job = Job.objects.create(
        user=request.user, kind=kind, parameters=parameters, source_id=parameters.get("blob")
    )
    notify(CHANNEL)
    return job


def cancel(job: Job) -> bool:
    """Gives the job up while it waits, or while it runs where what it makes is a file."""
    states = [Job.State.WAITING, *([Job.State.RUNNING] if KINDS[job.kind].saves else [])]
    return bool(
        Job.objects.filter(pk=job.pk, state__in=states).update(
            state=Job.State.CANCELLED, finished_at=timezone.now()
        )
    )


def claim() -> Job | None:
    with transaction.atomic():
        found = (
            Job.objects.filter(state=Job.State.WAITING)
            .order_by("queued_at")
            .select_related("user")
            .select_for_update(no_key=True, skip_locked=True, of=("self",))
            .first()
        )
        if found is not None:
            found.state = Job.State.RUNNING
            found.started_at = timezone.now()
            found.attempts += 1
            found.save(update_fields=["state", "started_at", "attempts"])
        return found


def _ended(job: Job, state: Job.State, **outcome) -> None:
    Job.objects.filter(pk=job.pk, state=Job.State.RUNNING).update(
        state=state, finished_at=timezone.now(), **outcome
    )


def run(job: Job) -> None:
    running.set(job)
    try:
        made = KINDS[job.kind].done(job.user, job.parameters)
        if isinstance(made, Saved):
            data = io.BytesIO(made.data) if isinstance(made.data, bytes) else made.data
            with data:
                file = store.put(data)
    except Refused as refused:
        _ended(job, Job.State.FAILED, status=refused.status, error=refused.error)
    except store.TooLarge:
        _ended(job, Job.State.FAILED, status=413, error="too_large")
    except Exception:
        log.exception("Job %s %s failed", job.kind, job.pk)
        _ended(job, Job.State.FAILED, status=500, error="unexpected")
    else:
        if isinstance(made, Saved):
            _ended(job, Job.State.DONE, file=file, name=made.name)
        else:
            _ended(job, Job.State.DONE, answer=made)


def swept() -> None:
    """Deletes the jobs ended longer than JOBS_KEPT ago, and the files nothing else holds."""
    ended = Job.objects.filter(finished_at__lt=timezone.now() - settings.JOBS_KEPT)
    if ended.delete()[0]:
        store.collect()


def interrupted() -> None:
    running = Job.objects.filter(state=Job.State.RUNNING)
    running.filter(attempts__gte=TRIES).update(
        state=Job.State.FAILED, status=500, error="interrupted", finished_at=timezone.now()
    )
    running.update(state=Job.State.WAITING, started_at=None)


async def run_next() -> bool:
    """Does one job waiting; False when none is."""
    claimed = await database(claim, own_thread=True)()
    if claimed is None:
        await database(swept, own_thread=True)()
        return False
    await database(run, own_thread=True)(claimed)
    return True


async def work() -> None:
    """Does jobs while the server runs, as soon as one is handed over."""
    async with create_task_group() as workers:
        for _ in range(settings.JOBS_AT_ONCE):
            workers.start_soon(drain, CHANNEL, run_next, settings.JOBS_SWEEP, log)
