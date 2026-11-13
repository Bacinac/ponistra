"""What in the mail happens at its own time, on the server, whatever the user's devices do (D40):
a message leaves at the moment chosen, one put away comes back, and so does one no one answered.
One that does not leave stays among those waiting, with its reason, and the user is told."""

from datetime import timedelta
from logging import getLogger

from django.db import transaction
from django.utils import timezone

from apps.core.api import Refused
from apps.core.asyncdb import database, drain
from apps.push import notices as push
from apps.push.models import Notice

from . import absence, awaiting, imap, sending, snoozing, views
from .models import Away, AwayAnswer, Unsent

log = getLogger(__name__)

# How long past its moment something may wait for the loop to come round.
SWEEP = timedelta(seconds=15)
ACCOUNT_GONE = "mail_account_gone"
INTERRUPTED = "mail_interrupted"


def _told(unsent: Unsent, event: str) -> None:
    push.tell(
        [unsent.owner_id],
        Notice.Kind.LATER,
        {"event": event, "subject": unsent.written.get("subject", "")},
        tag=push.topic("later", unsent.pk),
    )


def interrupted() -> None:
    """What a restart cut off while it was leaving may have left, so it is not tried again but
    put before the user."""
    with transaction.atomic():
        cut = list(Unsent.objects.select_for_update().filter(sending=True))
        Unsent.objects.filter(pk__in=[each.pk for each in cut]).update(
            sending=False, failed=INTERRUPTED
        )
        for each in cut:
            _told(each, "failed")


@database
def _claimed() -> Unsent | None:
    """The message whose moment came first, marked as leaving."""
    with transaction.atomic():
        found = (
            Unsent.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(send_at__lte=timezone.now(), sending=False, failed="")
            .select_related("owner")
            .order_by("send_at")
            .first()
        )
        if found is not None:
            Unsent.objects.filter(pk=found.pk).update(sending=True)
    return found


@database
def _failed(unsent: Unsent, code: str) -> None:
    with transaction.atomic():
        if Unsent.objects.filter(pk=unsent.pk).update(sending=False, failed=code):
            _told(unsent, "failed")


@database
def _refused(unsent: Unsent) -> None:
    with transaction.atomic():
        _told(unsent, "refused")


async def _leaving(unsent: Unsent) -> None:
    if unsent.account_id is None:
        await _failed(unsent, ACCOUNT_GONE)
        return
    data = {**unsent.written, "account": unsent.account_id, "unsent": unsent.pk}
    try:
        answer = await views.sent(unsent.owner, data)
    except Refused as refused:
        await _failed(unsent, refused.error)
    except Exception:
        log.exception("mail: message %s to leave later failed", unsent.pk)
        await _failed(unsent, "unexpected")
    else:
        if answer["refused"]:
            await _refused(unsent)


@database
def _answer_claimed() -> AwayAnswer | None:
    with transaction.atomic():
        found = (
            AwayAnswer.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(due=True)
            .select_related("away", "away__owner", "message", "message__account")
            .order_by("pk")
            .first()
        )
        if found is not None:
            AwayAnswer.objects.filter(pk=found.pk).update(due=False)
    return found


@database
def _away_failed(away: Away, code: str) -> None:
    """Told once, as a period can bring many failures while the user is not there to see them."""
    with transaction.atomic():
        if Away.objects.filter(pk=away.pk, failed="").update(failed=code):
            push.tell(
                [away.owner_id],
                Notice.Kind.LATER,
                {"event": "away_failed", "subject": ""},
                tag=push.topic("away", away.pk),
            )


async def _answering(answer: AwayAnswer) -> None:
    received = answer.message
    if received is None or received.account is None:
        return
    away, account = answer.away, received.account
    try:
        reply = absence.marked(
            sending.composed(
                account,
                [sending.address("", answer.address)],
                [],
                [],
                absence.titled(received.subject),
                absence.wording(away),
                received,
                [],
            )
        )
        await sending.delivered(account, reply)
    except sending.Invalid:
        log.warning("mail: away answer to an address mail cannot reach, message %s", received.pk)
        return
    except imap.Failed as failed:
        await _away_failed(away, failed.code)
        return
    except Exception:
        log.exception("mail: away answer to message %s failed", received.pk)
        await _away_failed(away, "unexpected")
        return
    await database(sending.recorded)(account, reply, None)
    if away.failed:
        await database(Away.objects.filter(pk=away.pk).update)(failed="")


async def _step() -> bool:
    if (unsent := await _claimed()) is not None:
        await _leaving(unsent)
        return True
    if (answer := await _answer_claimed()) is not None:
        await _answering(answer)
        return True
    if await database(snoozing.due, own_thread=True)():
        return True
    return await database(awaiting.due, own_thread=True)()


async def later() -> None:
    """Does what has come due, as soon as something is handed over and at each sweep."""
    await drain(sending.LATER, _step, SWEEP, log)
