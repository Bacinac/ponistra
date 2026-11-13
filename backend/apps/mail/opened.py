"""Which colleagues opened a message the user sent, as WhatsApp shows it within the installation
(SCOPE, S3, read within the organisation): no receipt is asked for or sent, and only the sender
sees it. A colleague holds the message where a copy of theirs is the same message
(`taking.same`), and only opening it counts, never marking it read."""

from collections import defaultdict

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.users.views import describe as describe_user

from . import taking
from .models import Account, Message, Opening, Setting


def setting() -> Setting:
    return Setting.objects.get_or_create(pk=1)[0]


def describe_setting(found: Setting) -> dict:
    return {
        "opened": found.opened,
        "changed_by": found.changed_by and describe_user(found.changed_by),
        "changed_at": found.changed_at,
    }


def change(user, on: bool) -> Setting:
    """Turns it on or off for the whole installation; off, what was noted of openings goes."""
    with transaction.atomic():
        found = Setting.objects.select_for_update().get_or_create(pk=1)[0]
        found.opened, found.changed_by, found.changed_at = on, user, timezone.now()
        found.save()
        if not on:
            Message.objects.exclude(opened_at=None).update(opened_at=None)
            Opening.objects.all().delete()
    return found


def noted(message: Message, person) -> None:
    """Notes the first opening of the message, where the installation shows openings: the owner's,
    or a shared mailbox's by whichever colleague opened it first, and each colleague's own."""
    if not setting().opened:
        return
    now = timezone.now()
    if message.opened_at is None:
        message.opened_at = now
        Message.objects.filter(pk=message.pk, opened_at=None).update(opened_at=now)
    if person.pk != message.owner_id:
        Opening.objects.get_or_create(message=message, user=person, defaults={"at": now})


def _own(user) -> set[str]:
    return {each.casefold() for each in user.mail_accounts.values_list("address", flat=True)}


def _sender(message: Message) -> str:
    return (message.sender.get("address") or "").casefold()


def _copies(user, message: Message):
    same = taking.same(
        message.message_id, message.key, message.fingerprint, message.date, taking.UNKEYED
    )
    return Message.objects.filter(same).exclude(owner=user)


def counted(user, messages) -> dict[int, dict]:
    """Of the messages, each the user sent that colleagues hold: how many colleagues hold it and
    how many of them opened it."""
    own = _own(user)
    mine = [each for each in messages if _sender(each) in own]
    if not mine or not setting().opened:
        return {}
    found = {}
    for message in mine:
        held = _copies(user, message).aggregate(
            held=Count("owner", distinct=True),
            opened=Count("owner", distinct=True, filter=~Q(opened_at=None)),
        )
        if held["held"]:
            found[message.pk] = held
    return found


def opened_by(user, message: Message) -> dict | None:
    """Of the message the user sent, each colleague holding it and when they opened it, those
    who did first, and how many of the people it names are outside the installation."""
    if _sender(message) not in _own(user) or not setting().opened:
        return None
    colleagues = {}
    copies = _copies(user, message).select_related("owner")
    for copy in copies.order_by(F("opened_at").asc(nulls_last=True), "owner_id"):
        colleagues.setdefault(copy.owner_id, copy)
    if not colleagues:
        return None
    inside = {each.casefold() for each in Account.objects.values_list("address", flat=True)}
    named = {
        each["address"].casefold() for each in [*message.to, *message.cc] if each.get("address")
    }
    openings = Opening.objects.filter(message__in=colleagues.values()).select_related("user")
    within = defaultdict(list)
    for each in openings.order_by("at"):
        within[each.message_id].append({"user": describe_user(each.user), "opened_at": each.at})
    return {
        "colleagues": [
            {"user": describe_user(copy.owner), "opened_at": copy.opened_at}
            | ({"within": within[copy.pk]} if copy.owner.mailbox else {})
            for copy in colleagues.values()
        ],
        "outside": len(named - inside),
    }
