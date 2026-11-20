"""What everyone in a meeting sees beside the people, guests too: whether it is being recorded,
and a board one of its members shows, drawn in each browser from the board itself."""

from django.db.models import Count, Max

from apps.core.api import Refused
from apps.core.asyncdb import released
from apps.documents import boards
from apps.documents.models import Node
from apps.documents.views import live

from . import livekit
from .models import Meeting, Recording


def _live(meeting: Meeting) -> Node | None:
    node = meeting.board
    return node if node is not None and node.is_live(node.ancestry()) else None


def _board(meeting: Meeting) -> dict | None:
    node = _live(meeting)
    if node is None:
        return None
    kept = node.board_entries.aggregate(count=Count("pk"), last=Max("updated_at"))
    by = meeting.board_by
    return {
        "id": str(node.pk),
        "title": node.title,
        "by": by and (by.get_full_name() or by.email),
        "user": meeting.board_by_id,
        "page": node.blob_id,
        "data": f"{kept['count']}:{kept['last'] and kept['last'].isoformat()}",
    }


def state(meeting: Meeting) -> dict:
    return {
        "recording": meeting.recordings.filter(state=Recording.State.RECORDING).exists(),
        "board": _board(meeting),
    }


def told(meeting: Meeting) -> None:
    """Raises livekit.Unavailable where LiveKit did not take it."""
    now = state(meeting)
    released()
    livekit.staged(str(meeting.pk), now)


def shown(meeting: Meeting) -> Node:
    """The board on the stage, for whoever is let into the meeting."""
    node = _live(meeting)
    if node is None:
        raise Refused(404, "no_board")
    return node


def show(user, meeting: Meeting, pk) -> None:
    node, _ = live(user, pk)
    if not boards.is_board(node):
        raise Refused(404, "not_found")
    Meeting.objects.filter(pk=meeting.pk).update(board=node, board_by=user)
    meeting.refresh_from_db()
    announce(meeting)


def hide(meeting: Meeting) -> None:
    Meeting.objects.filter(pk=meeting.pk).update(board=None, board_by=None)
    meeting.refresh_from_db()
    announce(meeting)


def announce(meeting: Meeting) -> None:
    try:
        told(meeting)
    except livekit.Unavailable as unavailable:
        raise Refused(503, "meetings_unavailable") from unavailable
