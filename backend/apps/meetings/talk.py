"""A guest's part in the conversation of the meeting they were let into (S2-2): while they are in
its call with someone of the installation, they read what has been written since the meeting
began and write to it under their own name. A meeting held in a group's conversation shows its
guest nothing the group said before it, nor anything once the installation has left the call."""

import uuid
from logging import getLogger

from django.db import transaction
from django.db.models import QuerySet

from apps.chat import conversations
from apps.chat.models import Message
from apps.collab import live
from apps.core.api import Refused
from apps.core.asyncdb import database

from . import livekit
from .models import Guest

log = getLogger(__name__)


def window(guest: Guest) -> QuerySet[Message]:
    meeting = guest.meeting
    return Message.objects.filter(
        conversation_id=meeting.conversation_id, created_at__gte=meeting.created_at
    )


def unread(guest: Guest) -> int:
    return window(guest).filter(id__gt=guest.read).exclude(guest=guest).count()


@database
def _admitted(pk: uuid.UUID, key: str) -> Guest:
    found = Guest.objects.select_related("meeting__conversation").filter(meeting_id=pk, key=key)
    if (guest := found.first()) is None:
        raise Refused(404, "no_guest")
    if guest.state != Guest.State.ADMITTED:
        raise Refused(403, "not_admitted")
    return guest


async def in_call(pk: uuid.UUID, key: str) -> Guest:
    """The guest the key names, while they are in the meeting's call with someone of the
    installation."""
    guest = await _admitted(pk, key)
    try:
        identities = await livekit.inside(str(pk))
    except livekit.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
        raise Refused(503, "meetings_unavailable") from unavailable
    theirs = f"{livekit.guest_identity(guest.pk)}."
    if not any(each.startswith(theirs) for each in identities) or all(
        livekit.is_guest(each) for each in identities
    ):
        raise Refused(403, "not_in_call")
    return guest


@transaction.atomic
def written(guest: Guest, text: str) -> Message:
    message = Message.objects.create(
        conversation=guest.meeting.conversation, guest=guest, body=text
    )
    Guest.objects.filter(pk=guest.pk).update(read=message.pk)
    conversations.announced(message, guest.name)
    return message


def read(guest: Guest, upto: int) -> None:
    """Marks the conversation read by the guest up to the message, never past its last one nor
    back."""
    last = window(guest).filter(id__lte=upto).order_by("-id").values_list("id", flat=True).first()
    if last and Guest.objects.filter(pk=guest.pk, read__lt=last).update(read=last):
        live.tell_guests(guest.pk)
