"""The time worked on each project of the workspace (VT1). The workspace reads its chats'
transcripts as they grow and says what stretches of work it found in each, and how far it read;
here they are kept, joined into blocks and counted by project, day and month.

A pause longer than `IDLE` ends a block, and a block lasts at least `LEAST`. The chats of one
project are one piece of work, their stretches joined into the same blocks, while projects worked
on at once each count in full. A block counts on the installation's day it began. Time brought
from Clockify for the days before the transcripts begin stands for its project's day as Clockify
had it."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Spend, Stretch, Transcript

IDLE = timedelta(minutes=15)
LEAST = timedelta(minutes=2)
CLOCKIFY = "clockify"

Span = tuple[datetime, datetime]
TOKENS = ("turns", "input", "output", "cache_read", "cache_write")


@dataclass(frozen=True)
class Spent:
    """The tokens a transcript's answers took in one hour on one model (PJ3)."""

    hour: datetime
    model: str
    turns: int
    input: int
    output: int
    cache_read: int
    cache_write: int


@dataclass(frozen=True)
class Found:
    """What a reading of a transcript found besides its time: the chat it belongs to, the round
    that chat is in, where the reading began, the answer counted last, the chat's title and the
    tokens of each hour and model."""

    chat: str = ""
    round: str = ""
    origin: int = 0
    last: str = ""
    title: str = ""
    spent: list[Spent] = field(default_factory=list)


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
def kept(
    namespace: str,
    session: str,
    project: str,
    read: int | None,
    spans: list[Span],
    found: Found | None = None,
) -> None:
    """Adds what the workspace found in a transcript to what it found there before, and moves
    the mark of how far it was read, unless it was read from a copy elsewhere (`read` None). The
    tokens count only where the reading began at the mark, so that a reading told twice counts
    once; a copy's only for a transcript not known before."""
    found = found or Found()
    transcript, created = Transcript.objects.select_for_update().get_or_create(
        namespace=namespace, session=session, defaults={"project": project}
    )
    counts = created if read is None else found.origin == transcript.read
    transcript.project = project
    transcript.chat = found.chat or transcript.chat or session
    if found.title:
        transcript.title = found.title
    if read is not None:
        transcript.read = read
        if found.last:
            transcript.last = found.last
    transcript.save()
    if counts and found.spent:
        _spent(transcript, found.round, found.spent)
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


def _spent(transcript: Transcript, round: str, spent: list[Spent]) -> None:
    held = {
        (each.hour, each.model): each
        for each in Spend.objects.filter(
            transcript=transcript, round=round, hour__in={each.hour for each in spent}
        )
    }
    for each in spent:
        known = held.get((each.hour, each.model))
        if known is None:
            Spend.objects.create(
                transcript=transcript,
                hour=each.hour,
                model=each.model,
                round=round,
                **{name: getattr(each, name) for name in TOKENS},
            )
        else:
            Spend.objects.filter(pk=known.pk).update(
                **{name: F(name) + getattr(each, name) for name in TOKENS}
            )


def marks() -> dict[str, dict]:
    """How far the workspace read each of its transcripts and the answer it counted last, each
    by `namespace/session`."""
    read, last = {}, {}
    for namespace, session, at, answer in Transcript.objects.exclude(
        namespace=CLOCKIFY
    ).values_list("namespace", "session", "read", "last"):
        read[f"{namespace}/{session}"] = at
        if answer:
            last[f"{namespace}/{session}"] = answer
    return {"read": read, "last": last}


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
