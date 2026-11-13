"""Events and tasks found by the search box (D21): each ranked within its own group, a series
once by its best occurrence, the nearest to today first among equals."""

from django.db import connection, transaction

from apps.calendar.models import Event
from apps.calendar.recurrence import shown
from apps.calendar.views import describe_calendar
from apps.tasks.models import Task
from apps.tasks.views import describe

from .query import Asked
from .text import (
    CONFIG,
    HEADLINE,
    LIKENESS,
    OPERATORS,
    PEOPLE,
    TAIL,
    WHOLE,
    matching,
    period_of,
)

# What an event says beyond its summary, as the snippet shows it.
ABOUT = "concat_ws(' · ', nullif(event.location, ''), nullif(left(event.description, 131072), ''))"
SNIPPET = (
    f"CASE WHEN to_tsvector('{CONFIG}'::regconfig, {ABOUT}) @@ q.query THEN regexp_replace("
    f"ts_headline('{CONFIG}'::regconfig, {ABOUT} || ' {TAIL}', q.query, %s), ' {TAIL}$', '')"
    " ELSE '' END"
)
NEAREST = "abs(extract(epoch FROM event.starts - now()))"

EVENTS = f"""
WITH q AS (
    SELECT {{query}} AS query, search_fold(%s) AS folded
),
hits AS (
    SELECT event.id, coalesce(event.master_id, event.id) AS series,
        1 + GREATEST(
            ts_rank_cd(event.words, q.query, 32),
            word_similarity(q.folded, search_fold(event.summary))
        ) AS rank
    FROM calendar_event event
    JOIN calendar_calendar calendar ON calendar.id = event.calendar_id
    CROSS JOIN q
    WHERE calendar.owner_id = %s AND event.status <> 'cancelled'{{filters}}
        AND (event.words @@ q.query OR q.folded <%% search_fold(event.summary))
),
best AS (
    SELECT DISTINCT ON (series) *, count(*) OVER (PARTITION BY series) AS hits
    FROM hits ORDER BY series, rank DESC, id
)
SELECT best.id, best.hits,
    ts_headline('{CONFIG}'::regconfig, event.summary, q.query, %s),
    {SNIPPET}
FROM best JOIN calendar_event event ON event.id = best.id CROSS JOIN q
ORDER BY best.rank DESC, {NEAREST}, event.id
LIMIT %s
"""

EVENTS_LISTED = """
SELECT event.id, 1, event.summary, ''
FROM calendar_event event
JOIN calendar_calendar calendar ON calendar.id = event.calendar_id
WHERE calendar.owner_id = %s AND event.status <> 'cancelled' AND event.master_id IS NULL{filters}
ORDER BY {order}, event.id
LIMIT %s
"""

TASKS = f"""
WITH q AS (
    SELECT {{query}} AS query, search_fold(%s) AS folded
)
SELECT task.id, ts_headline('{CONFIG}'::regconfig, task.text, q.query, %s),
    1 + GREATEST(
        ts_rank_cd(task.words, q.query, 32),
        word_similarity(q.folded, search_fold(task.text))
    ) AS rank
FROM tasks_task task CROSS JOIN q
WHERE task.owner_id = %s{{filters}}
    AND (task.words @@ q.query OR q.folded <%% search_fold(task.text))
ORDER BY task.done_at IS NOT NULL, rank DESC, task.due NULLS LAST, task.id DESC
LIMIT %s
"""

TASKS_LISTED = """
SELECT task.id, task.text
FROM tasks_task task
WHERE task.owner_id = %s{filters}
ORDER BY task.done_at IS NOT NULL, task.due NULLS LAST, task.id DESC
LIMIT %s
"""


def _events(wanted: Asked) -> tuple[str, list]:
    """The conditions on `event` the filters ask for: a date is when it takes place, a series
    from its first day on; a sender is its organiser or one of its guests."""
    conditions, params = [], []
    for value in wanted.sender:
        organiser = PEOPLE.format(
            name="event.organizer ->> 'name'", address="event.organizer ->> 'email'"
        )
        guest = PEOPLE.format(name="guest ->> 'name'", address="guest ->> 'email'")
        conditions.append(
            f"({organiser} OR EXISTS"
            f" (SELECT 1 FROM jsonb_array_elements(event.attendees) AS guest WHERE {guest}))"
        )
        params.extend([value, value])
    if wanted.period and wanted.period.changed:
        conditions.extend(period_of("event.changed_at", wanted, params))
    elif wanted.period:
        if wanted.period.end:
            conditions.append("event.starts < %s")
            params.append(wanted.period.end)
        if wanted.period.start:
            conditions.append("(event.ends > %s OR event.rrule <> '')")
            params.append(wanted.period.start)
    return "".join(f" AND {condition}" for condition in conditions), params


def _tasks(wanted: Asked) -> tuple[str, list]:
    """The conditions on `task` the filters ask for: a date is when it is due."""
    conditions, params = [], []
    if wanted.period and wanted.period.changed:
        conditions.extend(period_of("task.changed_at", wanted, params))
    elif wanted.period:
        if wanted.period.start:
            conditions.append("task.due >= %s")
            params.append(wanted.period.start.date())
        if wanted.period.end:
            conditions.append("task.due < %s")
            params.append(wanted.period.end.date())
    return "".join(f" AND {condition}" for condition in conditions), params


def fuzzy(wanted: Asked) -> str:
    """The text trigrams compare with a summary, none where it carries search operators."""
    return "" if OPERATORS.search(wanted.text) else wanted.text


def _event(event: Event, zone: str, hits: int, marked: str, snippet: str) -> dict:
    return {
        "id": event.pk,
        "master": event.master_id,
        "calendar": describe_calendar(event.calendar),
        "summary": event.summary,
        "marked": marked,
        "snippet": snippet,
        "location": event.location,
        "all_day": event.all_day,
        "start": shown(event.starts, event.all_day, zone),
        "end": shown(event.ends, event.all_day, zone, end=True),
        "recurring": bool(event.rrule) or event.master_id is not None,
        "hits": hits,
    }


def found_events(user, wanted: Asked, zone: str, limit: int) -> list[dict]:
    filters, params = _events(wanted)
    with transaction.atomic(), connection.cursor() as cursor:
        if not wanted.text:
            order = "event.starts" if wanted.period else NEAREST
            sql = EVENTS_LISTED.format(filters=filters, order=order)
            cursor.execute(sql, [user.pk, *params, limit])
        else:
            query, query_params = matching(wanted.text)
            cursor.execute(
                "SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)",
                [str(LIKENESS)],
            )
            cursor.execute(
                EVENTS.format(query=query, filters=filters),
                [*query_params, fuzzy(wanted), user.pk, *params, WHOLE, HEADLINE, limit],
            )
        rows = cursor.fetchall()
    events = (
        Event.objects.filter(pk__in=[row[0] for row in rows])
        .select_related("calendar__account")
        .prefetch_related("calendar__feeds__account")
        .in_bulk()
    )
    return [
        _event(events[pk], zone, hits, marked, snippet)
        for pk, hits, marked, snippet in rows
        if pk in events
    ]


def found_tasks(user, wanted: Asked, limit: int) -> list[dict]:
    filters, params = _tasks(wanted)
    with transaction.atomic(), connection.cursor() as cursor:
        if not wanted.text:
            cursor.execute(TASKS_LISTED.format(filters=filters), [user.pk, *params, limit])
        else:
            query, query_params = matching(wanted.text)
            cursor.execute(
                "SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)",
                [str(LIKENESS)],
            )
            cursor.execute(
                TASKS.format(query=query, filters=filters),
                [*query_params, fuzzy(wanted), WHOLE, user.pk, *params, limit],
            )
        rows = cursor.fetchall()
    tasks = Task.objects.in_bulk([row[0] for row in rows])
    return [{**describe(tasks[pk]), "marked": marked} for pk, marked, *_ in rows if pk in tasks]
