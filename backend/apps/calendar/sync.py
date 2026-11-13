"""The events taken while the backend runs (D15, S4): each Microsoft and Google account's new
ones every LOOK. An ActiveSync account's calendars come on its mail's connection
(`apps.mail.activesync.sync`)."""

from datetime import timedelta
from functools import partial
from logging import getLogger

from anyio import sleep
from django.db.models import Q

from apps.contacts.google import IMAP
from apps.core.asyncdb import database, waited
from apps.mail.imap import Failed
from apps.mail.models import Account

from . import google, graph
from .models import Feed

log = getLogger(__name__)

LOOK = timedelta(minutes=10)


def _followed() -> list[Account]:
    signed = Q(login__in=[Account.Login.MICROSOFT, Account.Login.GOOGLE])
    gmail = Q(protocol=Account.Protocol.IMAP, imap_host=IMAP)
    return list(Account.objects.exclude(state=Account.State.FAILED).filter(signed | gmail))


def _taken(account: Account) -> None:
    try:
        (graph if account.login == Account.Login.MICROSOFT else google).taken(account)
    except Failed as failed:
        Feed.objects.update_or_create(
            account=account, server_id="", defaults={"error": failed.code}
        )


async def calendars() -> None:
    while True:
        try:
            for account in await database(_followed)():
                await waited(partial(_taken, account))
        except Exception:
            log.exception("calendar: taking events failed")
        await sleep(LOOK.total_seconds())
