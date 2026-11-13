"""The door of a meeting (S2-2): a guest who came by the meeting's link waits there, on a socket
of its own (/api/lobby), until anyone of the installation in the meeting's conversation lets them
in or turns them away; those see who waits through the live channel.

    browser → {"key": <the guest's key>}
    server → {"type": "state", "state": "waiting" | "admitted" | "refused"}

A guest let in keeps it open in the call, where it also tells when the meeting's conversation
moved and how much of it they have not read: {…, "changed": <ISO time>, "unread": <count>}."""

import json

from anyio import CancelScope

from apps.chat.models import Member
from apps.collab import live
from apps.collab.server import same_origin
from apps.core.asyncdb import database

from . import talk
from .models import Guest, Meeting

PATH = "/api/lobby"


def waiting(user: int) -> list[dict]:
    """The guests at the door of the user's meetings."""
    found = Guest.objects.filter(
        state=Guest.State.WAITING, at_door=True, meeting__conversation__members__user_id=user
    )
    return [
        {"id": each.pk, "meeting": str(each.meeting_id), "name": each.name}
        for each in found.order_by("came_at")
    ]


def told(meeting: Meeting) -> None:
    """Wakes the pages of everyone who may let the meeting's guests in."""
    people = Member.objects.filter(conversation_id=meeting.conversation_id)
    live.tell(*people.values_list("user_id", flat=True))


def answered(guest: Guest, by, state: str) -> None:
    guest.state, guest.by = state, by
    guest.save(update_fields=["state", "by"])
    live.tell_guests(guest.pk)
    told(guest.meeting)


@database
def _door(key: str, at_door: bool) -> Guest | None:
    guest = Guest.objects.select_related("meeting").filter(key=key).first()
    if guest is not None and guest.at_door != at_door:
        guest.at_door = at_door
        guest.save(update_fields=["at_door"])
        told(guest.meeting)
    return guest


@database
def _state(guest: int) -> dict:
    found = Guest.objects.select_related("meeting__conversation").get(pk=guest)
    if found.state != Guest.State.ADMITTED:
        return {"state": found.state}
    return {
        "state": found.state,
        "changed": found.meeting.conversation.changed_at.isoformat(),
        "unread": talk.unread(found),
    }


async def socket(scope, receive, send) -> None:
    if (await receive())["type"] != "websocket.connect":
        return
    if not same_origin(scope):
        await send({"type": "websocket.close"})
        return
    await send({"type": "websocket.accept"})
    first = await receive()
    try:
        key = json.loads(first.get("text") or "")["key"]
    except ValueError, TypeError, KeyError:
        key = None
    guest = await _door(key, True) if isinstance(key, str) else None
    if guest is None:
        await send({"type": "websocket.close", "code": 4404})
        return
    listener = live.guest(guest.pk)
    try:
        await live.held(receive, send, listener, lambda: _state(guest.pk))
    finally:
        if not live.listening(listener):
            with CancelScope(shield=True):
                await _door(key, False)
