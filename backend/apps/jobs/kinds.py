from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import IO

from django.http import HttpRequest

from .models import Job

running: ContextVar[Job] = ContextVar("running")


def answered(answer: dict) -> None:
    """Gives the running job's answer early, for what it made to be opened while the rest of
    the work goes on."""
    job = running.get(None)
    if job is not None:
        Job.objects.filter(pk=job.pk).update(answer=answer)


def answered_before() -> dict | None:
    """The answer a run of the job that a restart cut off gave early."""
    job = running.get(None)
    return None if job is None else job.answer


@dataclass(frozen=True)
class Saved:
    """A file a job made, for the browser to save under its name."""

    data: bytes | IO[bytes]
    name: str


@dataclass(frozen=True)
class Kind:
    """What a job checks when it is handed over, as the request would have, giving what it
    keeps to do it with (the file it reads under "blob"), and what it does when its turn comes,
    checking again what may have changed while it waited. One that saves a file can be given up
    while it runs, its file thrown away; one that makes a document cannot be unmade."""

    asked: Callable[[HttpRequest, dict], dict]
    done: Callable[..., Saved | dict]
    saves: bool
