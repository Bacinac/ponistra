"""A message sent that waits for an answer (D40): if no one has answered it by the date, it comes
back to the top of the inbox, as a snoozed one does."""

from django.db import transaction
from django.utils import timezone

from apps.push import notices as push
from apps.push.models import Notice

from . import correspondents, sending, snoozing, taking
from .models import Message, Role

BATCH = 100
LEFT_ALONE = (Role.TRASH, Role.JUNK)
# More than a thread can hold, so that a subject everyone uses cannot keep the loop reading.
CANDIDATES = 500


def _bare(subject: str) -> str:
    while found := sending.ANSWERED.match(subject):
        subject = subject[found.end() :]
    return subject.strip().casefold()


def answered(message: Message) -> bool:
    """Whether someone else answered in its thread. A server that writes Message-IDs anew, as
    Traveler does, leaves no thread to follow, so a message under its subject from one of those it
    went to, after it, is an answer too."""
    mine = set(correspondents.own(message.owner_id))
    theirs = Message.objects.filter(
        owner_id=message.owner_id, automatic=False, reaction=""
    ).exclude(pk=message.pk)
    if taking.real(mid := message.message_id.strip()):
        following = theirs.filter(in_reply_to__contains=mid) | theirs.filter(
            references__contains=mid
        )
        senders = following.values_list("sender__address", flat=True)[:CANDIDATES]
        if any((sender or "").lower() not in mine for sender in senders):
            return True
    bare = _bare(message.subject)
    went_to = {(each.get("address") or "").lower() for each in [*message.to, *message.cc]} - mine
    if not bare or not went_to:
        return False
    after = theirs.filter(date__gt=message.date, subject__icontains=bare)
    return any(
        (sender or "").lower() in went_to and _bare(subject) == bare
        for sender, subject in after.values_list("sender__address", "subject")[:CANDIDATES]
    )


def _told(message: Message) -> None:
    push.tell(
        [message.owner_id],
        Notice.Kind.LATER,
        {
            "event": "unanswered",
            "subject": message.subject,
            "folder": message.folder_id,
            "message": message.pk,
        },
        tag=push.topic("awaited", message.pk),
    )


def due() -> bool:
    """Settles those whose date has come: what no one answered comes back and its owner is told;
    whether there were any."""
    now = timezone.now()
    with transaction.atomic():
        come = list(
            Message.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(awaited_until__lte=now)
            .select_related("folder")
            .order_by("awaited_until")[:BATCH]
        )
        for message in come:
            back = message.folder.role not in LEFT_ALONE and not answered(message)
            message.awaited_until = None
            if back:
                message.folder = snoozing.of_role(message.owner_id, Role.INBOX)
                message.snoozed_until, message.returned_at = None, now
                message.seen, message.unanswered = False, True
            message.save(
                update_fields=[
                    "awaited_until",
                    "folder",
                    "snoozed_until",
                    "returned_at",
                    "seen",
                    "unanswered",
                ]
            )
            if back:
                _told(message)
    return bool(come)
