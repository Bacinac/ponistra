"""The words search finds in the rows of tables, read again in the background for each row a
trigger queued as it was written (models.GridRowWords), so that a write of a column of values
does not wait on the search index."""

from logging import getLogger

from django.conf import settings
from django.db import connection

from apps.core.asyncdb import database, drain
from apps.search.text import CONFIG

log = getLogger(__name__)

CHANNEL = "grid_words"
STEP = 2000

READ = f"""
WITH taken AS (
    DELETE FROM content_stalegridrow WHERE grid_row_id IN (
        SELECT grid_row_id FROM content_stalegridrow LIMIT %s FOR UPDATE SKIP LOCKED
    )
    RETURNING grid_row_id
), written AS (
    INSERT INTO content_gridrowwords (grid_row_id, words)
    SELECT line.id, to_tsvector('{CONFIG}'::regconfig, grid_row_text(line.cells, line.shown))
    FROM content_gridrow line JOIN taken ON taken.grid_row_id = line.id
    ON CONFLICT (grid_row_id) DO UPDATE SET words = EXCLUDED.words
    WHERE content_gridrowwords.words IS DISTINCT FROM EXCLUDED.words
)
SELECT count(*) FROM taken
"""


def read_next() -> bool:
    """Reads the words of the next rows queued; whether there may be more."""
    with connection.cursor() as cursor:
        cursor.execute(READ, [STEP])
        return cursor.fetchone()[0] == STEP


def read() -> None:
    """Reads the words of every row queued."""
    while read_next():
        pass


async def follow() -> None:
    """Keeps the words following the rows while the server runs: on each notification the
    trigger sends, and in a sweep every SEARCH_SWEEP for whatever a lost one left."""
    await drain(CHANNEL, database(read_next, own_thread=True), settings.SEARCH_SWEEP, log)
