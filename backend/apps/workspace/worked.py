"""The time worked on each project of the workspace (VT1). The workspace reads its chats'
transcripts as they grow and says what stretches of work it found in each, and how far it read;
here they are kept, joined into blocks and counted by project, day and month.

A pause longer than `IDLE` ends a block, and a block lasts at least `LEAST`. The chats of one
project are one piece of work, their stretches joined into the same blocks, while projects worked
on at once each count in full. A block counts on the installation's day it began. Time brought
from Clockify for the days before the transcripts begin stands for its project's day as Clockify
had it."""

from collections import defaultdict
from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import Stretch, Transcript

IDLE = timedelta(minutes=15)
LEAST = timedelta(minutes=2)
CLOCKIFY = "clockify"

Span = tuple[datetime, datetime]


def joined(spans: list[Span], apart: timedelta = IDLE) -> list[Span]:
    """The spans joined wherever one begins no later than `apart` after those before it end."""
    out: list[list[datetime]] = []
    for began, ended in sorted(spans):
        if out and began - out[-1][1] <= apart:
            out[-1][1] = max(out[-1][1], ended)
        else:
            out.append([began, ended])
    return [(began, ended) for began, ended in out]


@transaction.atomic
def kept(namespace: str, session: str, project: str, read: int | None, spans: list[Span]) -> None:
    """Adds what the workspace found in a transcript to what it found there before, and moves
    the mark of how far it was read, unless it was read from a copy elsewhere (`read` None)."""
    transcript, _ = Transcript.objects.select_for_update().get_or_create(
        namespace=namespace, session=session, defaults={"project": project}
    )
    transcript.project = project
    if read is not None:
        transcript.read = read
    transcript.save()
    held = list(transcript.stretches.values_list("pk", "began", "ended"))
    wanted = set(joined([(began, ended) for _, began, ended in held] + spans))
    had = {(began, ended) for _, began, ended in held}
    Stretch.objects.filter(
        pk__in=[pk for pk, began, ended in held if (began, ended) not in wanted]
    ).delete()
    Stretch.objects.bulk_create(
        [
            Stretch(transcript=transcript, began=began, ended=ended)
            for began, ended in sorted(wanted - had)
        ]
    )


def marks() -> dict[str, int]:
    """How far the workspace read each of its transcripts, by `namespace/session`."""
    return {
        f"{namespace}/{session}": read
        for namespace, session, read in Transcript.objects.exclude(namespace=CLOCKIFY).values_list(
            "namespace", "session", "read"
        )
    }


def day_of(moment: datetime) -> date:
    return timezone.localtime(moment).date()


def blocks() -> dict[str, list[Span]]:
    """Each project's blocks of work, the days Clockify gave a project its blocks there."""
    found: dict[str, list[Span]] = defaultdict(list)
    brought: dict[str, list[Span]] = defaultdict(list)
    for project, namespace, began, ended in Stretch.objects.values_list(
        "transcript__project", "transcript__namespace", "began", "ended"
    ):
        (brought if namespace == CLOCKIFY else found)[project].append((began, ended))
    counted: dict[str, list[Span]] = {}
    for project in found.keys() | brought.keys():
        given = joined(brought.get(project, []), timedelta(0))
        days = {day_of(began) for began, _ in given}
        own = [
            (began, max(ended, began + LEAST))
            for began, ended in joined(found.get(project, []))
            if day_of(began) not in days
        ]
        counted[project] = sorted(own + given)
    return counted


def seconds(spans: list[Span]) -> int:
    return round(
        sum((ended - began).total_seconds() for began, ended in joined(spans, timedelta(0)))
    )


def hours(month: str | None = None) -> dict:
    """The time worked in each month by project, and in one month, the latest unless named, by
    day: each project's time, their sum and the time on the clock any of them was worked."""
    by_day: dict[date, dict[str, list[Span]]] = defaultdict(lambda: defaultdict(list))
    for project, spans in blocks().items():
        for span in spans:
            by_day[day_of(span[0])][project].append(span)
    days = []
    for day, projects in by_day.items():
        each = {project: seconds(spans) for project, spans in projects.items()}
        days.append(
            {
                "day": day.isoformat(),
                "projects": each,
                "total": sum(each.values()),
                "wall": seconds([span for spans in projects.values() for span in spans]),
            }
        )
    days.sort(key=lambda each: each["day"], reverse=True)
    months: dict[str, dict] = {}
    for day in days:
        held = months.setdefault(
            day["day"][:7], {"month": day["day"][:7], "projects": {}, "total": 0, "wall": 0}
        )
        for project, worked in day["projects"].items():
            held["projects"][project] = held["projects"].get(project, 0) + worked
        held["total"] += day["total"]
        held["wall"] += day["wall"]
    shown = month if month in months else next(iter(months), None)
    return {
        "months": list(months.values()),
        "month": shown,
        "days": [day for day in days if shown and day["day"].startswith(shown)],
    }
