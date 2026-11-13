"""The nightly pass over the memory (MEM5), only once its owner turned it on: the mechanical reading
and an analysis of what changed since the last, after the night's checks."""

from datetime import timedelta
from logging import getLogger

from anyio import sleep
from django.conf import settings
from django.utils import timezone

from apps.core.api import Refused
from apps.core.asyncdb import database

from . import ledger
from .models import Nightly

log = getLogger(__name__)

HOUR = 4
EVERY = timedelta(minutes=15)


def passed() -> None:
    if not settings.WORKSPACE or not settings.WORKSPACE_TOKEN or not ledger.owners():
        return
    found = Nightly.objects.get_or_create(pk=1)[0]
    now = timezone.localtime()
    if not found.on or now.hour != HOUR or found.last == now.date():
        return
    Nightly.objects.filter(pk=1).update(last=now.date())
    ledger.heard()
    try:
        ledger.analyse(None)
    except Refused as refused:
        if refused.error != "memory_analysed":
            log.warning("memory: the night's analysis was not asked: %s", refused.error)


async def nightly() -> None:
    while True:
        try:
            await database(passed, own_thread=True)()
        except Exception:
            log.exception("memory: the night's pass failed")
        await sleep(EVERY.total_seconds())
