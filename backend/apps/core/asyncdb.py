import functools
from collections.abc import Awaitable, Callable
from datetime import timedelta
from logging import Logger

import psycopg
from anyio import CancelScope, sleep, to_thread
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections, connection, connections


def database[**P, R](fn: Callable[P, R], *, own_thread: bool = False) -> Callable[P, Awaitable[R]]:
    # A WebSocket or a background loop outlives Django's request cycle, which is what
    # normally returns connections to the pool and drops broken ones. Called back into a
    # request's transaction, the connection is the request's, and stays open.
    @functools.wraps(fn)
    def call(*args: P.args, **kwargs: P.kwargs) -> R:
        if connection.in_atomic_block:
            return fn(*args, **kwargs)
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    # Outside a request every thread-sensitive call runs on one shared thread, so a
    # long one would stall the WebSocket writes queued behind it.
    return sync_to_async(call, thread_sensitive=not own_thread)


def released() -> None:
    """Gives the thread's connection back to the pool before it waits on work that takes
    connections of its own: a book's pass, a page the printer opens. Held meanwhile, a few such
    waits hold the whole pool, and what they wait for never starts until the pool's timeout.
    Within a transaction the connection is the transaction's, and stays."""
    if not connection.in_atomic_block:
        connection.close()


async def waited[R](run: Callable[[], R]) -> R:
    """What work on another server answers, waited for on a worker thread. A database
    connection it opened there goes back to the pool: no request cycle ends there to return it."""

    def closing() -> R:
        try:
            return run()
        finally:
            connections.close_all()

    return await to_thread.run_sync(closing, abandon_on_cancel=True)


def conninfo() -> str:
    db = settings.DATABASES["default"]
    return psycopg.conninfo.make_conninfo(
        host=db["HOST"],
        port=db["PORT"],
        dbname=db["NAME"],
        user=db["USER"],
        password=db["PASSWORD"],
    )


def notify(channel: str) -> None:
    """Wakes whoever listens on the channel once the current transaction commits."""
    with connection.cursor() as cursor:
        cursor.execute(f"NOTIFY {channel}")


async def drain(
    channel: str, step: Callable[[], Awaitable[bool]], sweep: timedelta, log: Logger
) -> None:
    """Takes steps until one finds nothing left to do, again on each notification on the
    channel, and in a sweep every `sweep` for whatever a lost notification left."""
    every = sweep.total_seconds()
    while True:
        try:
            listener = await psycopg.AsyncConnection.connect(conninfo(), autocommit=True)
            try:
                await listener.execute(f"LISTEN {channel}")
                while True:
                    while await step():
                        pass
                    async for _ in listener.notifies(timeout=every, stop_after=1):
                        pass
            finally:
                # Closed rather than left as a context manager: that rolls back first, which a
                # connection still waiting for notifications refuses, with a warning.
                with CancelScope(shield=True):
                    await listener.close()
        except Exception:
            log.exception("%s failed", channel)
            await sleep(every)
