from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from django.db import connection


@contextmanager
def held(*keys: int) -> Iterator[bool]:
    """A session's advisory lock on a connection of its own outside the pool, True while it is held
    and False when another has it. A pooled connection would not do: the work hands its connection
    back to the pool and goes on with another, while the lock stays with the first."""
    with psycopg.connect(**connection.get_connection_params(), autocommit=True) as own:
        placed = ", ".join(["%s"] * len(keys))
        yield own.execute(f"SELECT pg_try_advisory_lock({placed})", keys).fetchone()[0]
