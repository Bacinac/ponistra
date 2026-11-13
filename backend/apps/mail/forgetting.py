from itertools import batched

from django.db import transaction
from django.db.models import Q

from . import taking
from .models import Deleted, Message

# The messages deleted for good in one statement, below the bound a statement's parameters have.
FORGOTTEN = 1000


def forgotten(owner_id: int, found) -> int:
    """Deletes the messages for good and the reactions to them, each remembered as deleted so that
    no provider that gives a folder out again from nothing brings it back."""
    chosen = found.values("pk")
    taken = Message.objects.filter(Q(pk__in=chosen) | Q(reacts_to__in=chosen))
    gone = list(taken.values_list("pk", "key", "fingerprint", "date", "message_id"))
    counted = found.count()
    with transaction.atomic():
        for each in batched(gone, FORGOTTEN, strict=False):
            Deleted.objects.bulk_create(
                (
                    Deleted(
                        owner_id=owner_id,
                        key=key,
                        fingerprint=made,
                        date=date,
                        keyed=taking.real(message_id),
                    )
                    for _, key, made, date, message_id in each
                ),
                ignore_conflicts=True,
            )
            Message.objects.filter(pk__in=[pk for pk, *_ in each]).delete()
    return counted
