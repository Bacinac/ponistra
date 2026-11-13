"""The registry's `mail.gather`: messages the user chooses taken into one of their collections,
kept whatever the model would say of them."""

from django.db import transaction
from django.db.models import QuerySet

from apps.core.api import Refused
from apps.core.asyncdb import notify
from apps.mail import sending
from apps.mail.acting import Acting
from apps.mail.models import Message

from . import taking
from .models import Collection, Item


def gather(acting: Acting, found: QuerySet[Message], parameters: dict) -> int:
    collection = Collection.objects.filter(owner=acting.owner, pk=parameters["collection"]).first()
    if collection is None or acting.person.pk != acting.owner.pk:
        raise Refused(404, "not_found")
    with transaction.atomic():
        again = Item.objects.filter(collection=collection, message__in=found).exclude(
            state=Item.State.KEPT
        )
        changed = again.update(chosen=True, state=Item.State.WAITING, error="", tried_at=None)
        held = Item.objects.filter(collection=collection).values("message")
        changed += taking.taken(collection, list(found.exclude(pk__in=held)), chosen=True)
        notify(sending.LATER)
    return changed
