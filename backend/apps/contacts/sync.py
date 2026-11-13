"""The contacts taken while the backend runs (D15, S4): each Microsoft and Google account's new
ones every LOOK, and each ActiveSync account's directory gone through once a night. An ActiveSync
account's own contacts come on its mail's connection (`apps.mail.activesync.sync`)."""

from datetime import timedelta
from functools import partial
from logging import getLogger

from anyio import sleep
from django.db.models import Q
from django.utils import timezone

from apps.core.asyncdb import database, waited
from apps.mail.imap import Failed
from apps.mail.models import Account

from . import directory, google, graph
from .models import Book, Directory

log = getLogger(__name__)

LOOK = timedelta(minutes=10)


def _followed() -> list[Account]:
    signed = Q(login__in=[Account.Login.MICROSOFT, Account.Login.GOOGLE])
    gmail = Q(protocol=Account.Protocol.IMAP, imap_host=google.IMAP)
    return list(Account.objects.exclude(state=Account.State.FAILED).filter(signed | gmail))


def _due() -> list[int]:
    accounts = Account.objects.exclude(state=Account.State.FAILED).filter(
        protocol=Account.Protocol.ACTIVESYNC
    )
    passed = dict(Directory.objects.values_list("account_id", "passed_at"))
    now = timezone.now()
    return [each.pk for each in accounts if directory.due(passed.get(each.pk)) <= now]


def _taken(account: Account) -> None:
    try:
        (graph if account.login == Account.Login.MICROSOFT else google).taken(account)
    except Failed as failed:
        Book.objects.update_or_create(
            account=account, server_id="", defaults={"error": failed.code}
        )


async def contacts() -> None:
    while True:
        try:
            for account in await database(_followed)():
                await waited(partial(_taken, account))
            for account_id in await database(_due)():
                await waited(partial(directory.passed, account_id))
        except Exception:
            log.exception("contacts: taking them failed")
        await sleep(LOOK.total_seconds())
