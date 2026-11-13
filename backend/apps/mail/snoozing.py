"""A message put away until a moment (D40): it waits in a folder of PONISTRA's own and comes back
to the top of the inbox, unread, with a notification. The state is in Postgres alone; the
provider's copy stays where it is."""

from datetime import datetime

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from . import sorting, taking
from .models import Folder, Message, Role

BATCH = 100


def of_role(owner_id: int, role: Role) -> Folder:
    return Folder.objects.get_or_create(owner_id=owner_id, role=role, defaults={"name": role})[0]


def put_away(owner_id: int, found: QuerySet[Message], at: datetime) -> int:
    """Puts the messages away until the moment, but those in the folders of what the user sends
    and what is put away for good; how many went."""
    allowed = found.exclude(folder__role__in=[r for r in sorting.KEPT if r != Role.SNOOZED])
    return allowed.update(folder=of_role(owner_id, Role.SNOOZED), snoozed_until=at)


def returned(owner_id: int, found: QuerySet[Message]) -> int:
    """Brings the messages back to the top of the inbox now, unread; how many came."""
    inbox = of_role(owner_id, Role.INBOX)
    return found.update(folder=inbox, snoozed_until=None, returned_at=timezone.now(), seen=False)


def due() -> bool:
    """Brings back those whose moment has come and tells their owners; whether there were any."""
    now = timezone.now()
    with transaction.atomic():
        come = list(
            Message.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(snoozed_until__lte=now)
            .order_by("snoozed_until")[:BATCH]
        )
        for message in come:
            message.folder = of_role(message.owner_id, Role.INBOX)
            message.snoozed_until, message.returned_at, message.seen = None, now, False
            message.save(update_fields=["folder", "snoozed_until", "returned_at", "seen"])
            taking.announced(message)
    return bool(come)
