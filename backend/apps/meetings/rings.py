"""Ringing colleagues into a meeting made on its own (S2): the ring sounds in every PONISTRA of
theirs that is open, through the live channel, until they join, decline or it has rung for as long
as a call rings. Whoever rang sees how each ring stands beside the meeting."""

from datetime import timedelta
from math import ceil

from django.utils import timezone

from apps.collab import live
from apps.push import notices as push
from apps.push.models import Notice

from .models import Meeting, Ring

RINGING = timedelta(seconds=45)
# How long the rings a user made stay in sight of their meeting.
KEPT = timedelta(hours=1)


def _name(user) -> str:
    return (user.get_full_name() or user.email) if user else ""


def _left(ring: Ring, now) -> int:
    return max(0, ceil((ring.rung_at + RINGING - now).total_seconds()))


def ringing(user: int) -> list[dict]:
    """The rings sounding for the user, with the seconds each has left."""
    now = timezone.now()
    found = Ring.objects.filter(user_id=user, answer="", rung_at__gt=now - RINGING)
    return [
        {
            "id": each.pk,
            "meeting": str(each.meeting_id),
            "title": each.meeting.title,
            "by": _name(each.by),
            "left": _left(each, now),
        }
        for each in found.select_related("meeting", "by").order_by("rung_at")
    ]


def rung(user: int) -> list[dict]:
    """The rings the user made lately: unanswered with no seconds left is a ring that stopped."""
    now = timezone.now()
    found = Ring.objects.filter(by_id=user, rung_at__gt=now - KEPT)
    return [
        {
            "id": each.pk,
            "meeting": str(each.meeting_id),
            "name": _name(each.user),
            "address": each.user.email,
            "answer": each.answer,
            "left": _left(each, now),
        }
        for each in found.select_related("user").order_by("rung_at")
    ]


def ring(by, meeting: Meeting, users) -> None:
    """Rings the users, once more those whose ring stopped unanswered."""
    now = timezone.now()
    for user in users:
        Ring.objects.update_or_create(
            meeting=meeting, user=user, answer="", defaults={"by": by, "rung_at": now}
        )
    live.tell(by.pk, *(each.pk for each in users))
    push.tell(
        [each.pk for each in users],
        Notice.Kind.RING,
        {"by": _name(by), "title": meeting.title, "meeting": str(meeting.id)},
        tag=push.topic("ring", meeting.id),
        urgency=Notice.Urgency.HIGH,
        ttl=int(RINGING.total_seconds()),
    )


def answered(user, meeting: Meeting, answer: str) -> None:
    unanswered = Ring.objects.filter(meeting=meeting, user=user, answer="")
    by = {each for each in unanswered.values_list("by_id", flat=True) if each}
    if unanswered.update(answer=answer):
        live.tell(user.pk, *by)
