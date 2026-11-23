"""What changes on a Docker host reaches the pages as it happens (D55): one stream of the daemon's
events per host, each event telling `/api/live` that the area `containers` changed. A host that
cannot be reached is tried again later, waiting longer each time it fails."""

import asyncio
import json
import logging
from contextlib import suppress

from django.db import connection

from apps.core.asyncdb import database
from apps.locations.remote import Failed

from . import reach
from .engine import path_of
from .models import Host

log = logging.getLogger(__name__)

AREA = "containers"
FIRST_RETRY = 5
LAST_RETRY = 300
# Events come in bursts (a stack going up is dozens); the pages are told once per burst.
GATHERED = 0.5
EVENTS = {"type": ["container", "image", "volume", "network"]}

_hosts_changed: asyncio.Event | None = None


def _told() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('changed', %s)", [f"{AREA} *"])


def followed() -> None:
    """The hosts changed: the watcher reads them again."""
    if _hosts_changed is not None:
        _hosts_changed.set()


def _hosts() -> set:
    return set(Host.objects.values_list("pk", flat=True))


def _host(pk) -> Host | None:
    return Host.objects.select_related("location", "location__tunnel").filter(pk=pk).first()


async def _watched(held: Host) -> None:
    """The host's events as long as its daemon sends them."""
    engine = await database(reach.engine)(held)
    query = {"filters": json.dumps(EVENTS)}
    async with engine.answer("GET", path_of("/events", query)) as (answer, _):
        await database(_told)()
        pending: asyncio.TimerHandle | None = None
        loop = asyncio.get_running_loop()

        def tell() -> None:
            nonlocal pending
            pending = None
            loop.create_task(database(_told)())

        async for _ in answer.body():
            if pending is None:
                pending = loop.call_later(GATHERED, tell)


async def _kept(pk) -> None:
    retry = FIRST_RETRY
    while True:
        try:
            # Read again each time, as the location may have moved or changed its key since.
            if (held := await database(_host)(pk)) is None:
                return
            await _watched(held)
            retry = FIRST_RETRY
        except (Failed, OSError, asyncio.IncompleteReadError, RuntimeError) as error:
            log.info("docker events of %s: %s", pk, error)
        await asyncio.sleep(retry)
        retry = min(retry * 2, LAST_RETRY)


async def follow() -> None:
    """Watches every host's events, the set of hosts read again whenever it changes."""
    global _hosts_changed
    _hosts_changed = asyncio.Event()
    watching: dict = {}
    try:
        while True:
            _hosts_changed.clear()
            hosts = await database(_hosts)()
            for pk in watching.keys() - hosts:
                watching.pop(pk).cancel()
            for pk in hosts - watching.keys():
                watching[pk] = asyncio.create_task(_kept(pk))
            await _hosts_changed.wait()
    finally:
        for task in watching.values():
            task.cancel()
        for task in watching.values():
            with suppress(asyncio.CancelledError):
                await task
