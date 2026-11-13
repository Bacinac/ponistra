"""A table's rows as Postgres holds them, read by where they stand (D22, E3). The order of a
table is its rows' positions; a row's place, counted from 0, is how many of its rows stand
before it, read through the index on the positions rather than by numbering every row."""

import json
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence

from django.db import connection

from .filtering import View
from .grids import FORMULA, LOOK, Formula, Look, Row, decoded, shared_of
from .models import Shared

# Places further apart than this are read as two windows rather than one.
GAP = 64
_AT_ONCE = 2000


def _jsonb(given):
    # Django's cursor reads jsonb as its text, leaving JSONField to decode it.
    return json.loads(given) if isinstance(given, str) else given


def _seen(view: View | None, r: str = "r") -> tuple[str, list]:
    if view is None:
        return "", []
    where, params = view.sql(r)
    return f" AND {where}", params


def count(grid: int, view: View | None = None) -> int:
    """How many rows the table has, or of them the view shows."""
    where, params = _seen(view)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT count(*) FROM content_gridrow r WHERE r.grid_id = %s{where}", [grid, *params]
        )
        return cursor.fetchone()[0]


def ids_in(grid: int, first: int, last: int, view: View | None = None) -> list[str]:
    """The ids of the rows from the first place to the last, both included, as far as the
    table reaches; places among the rows the view shows, where one is given."""
    first = max(first, 0)
    if last < first:
        return []
    where, params = _seen(view)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT r.row FROM content_gridrow r WHERE r.grid_id = %s{where} "
            "ORDER BY r.position OFFSET %s LIMIT %s",
            [grid, *params, first, last - first + 1],
        )
        return [id for (id,) in cursor.fetchall()]


def _runs(places: Iterable[int]) -> list[tuple[int, int]]:
    runs: list[list[int]] = []
    for place in sorted({place for place in places if place >= 0}):
        if runs and place - runs[-1][1] <= GAP:
            runs[-1][1] = place
        else:
            runs.append([place, place])
    return [(first, last) for first, last in runs]


def ids_at(grid: int, places: Iterable[int], view: View | None = None) -> dict[int, str]:
    """The id of the row at each place given, of those the table reaches."""
    found: dict[int, str] = {}
    wanted = set(places)
    for first, last in _runs(wanted):
        for offset, id in enumerate(ids_in(grid, first, last, view)):
            if first + offset in wanted:
                found[first + offset] = id
    return found


def places_of(grid: int, ids: Iterable[str], view: View | None = None) -> dict[str, int]:
    """The place of each row given, of those the table has, or the view shows among those it
    shows: counted for each through the index on the positions, or for many by numbering the
    table's rows once."""
    ids = list(set(ids))
    if not ids:
        return {}
    where, params = _seen(view)
    seen, _ = _seen(view, "b")
    with connection.cursor() as cursor:
        if len(ids) > GAP:
            cursor.execute(
                "SELECT row, place FROM (SELECT r.row, row_number() OVER (ORDER BY r.position) "
                f"- 1 AS place FROM content_gridrow r WHERE r.grid_id = %s{where}) n "
                "WHERE row = ANY(%s)",
                [grid, *params, ids],
            )
        else:
            cursor.execute(
                "SELECT r.row, (SELECT count(*) FROM content_gridrow b "
                f"WHERE b.grid_id = r.grid_id AND b.position < r.position{seen}) "
                f"FROM content_gridrow r WHERE r.grid_id = %s AND r.row = ANY(%s){where}",
                [*params, grid, ids, *params],
            )
        return dict(cursor.fetchall())


class Reach(Sequence[str]):
    """The ids of a table's rows by place as far as they were read, for `grids.decoded`,
    which asks only for the places a formula's distances reach from its own row."""

    def __init__(self, size: int, ids: Mapping[int, str]):
        self.size = size
        self.ids = ids

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, place):
        return self.ids.get(place)


_FIELDS = 'row, height, cells, "values", position, id, look, shown, hidden'
_COLUMNS = (
    f"{_FIELDS}, (SELECT count(*) FROM content_gridrow b WHERE b.grid_id = r.grid_id "
    "AND b.position < r.position)"
)


def _shared(document, keys: set[str]) -> dict[str, Formula | Look]:
    if not keys:
        return {}
    found = Shared.objects.filter(document=document, key__in=list(keys))
    return shared_of(dict(found.values_list("key", "value")))


def _keys(cells: Mapping[str, dict]) -> set[str]:
    return {
        key
        for cell in cells.values()
        for part in (FORMULA, LOOK)
        if isinstance(key := cell.get(part), str)
    }


def _distances(cells: Mapping[str, dict], shared: Mapping[str, Formula | Look]) -> set[int]:
    found = set()
    for cell in cells.values():
        formula = shared.get(cell.get(FORMULA)) if isinstance(cell.get(FORMULA), str) else None
        for piece in formula or ():
            if isinstance(piece, dict) and "table" not in piece:
                for end in ("from", "to"):
                    if isinstance(target := (piece.get(end) or {}).get("row"), int):
                        found.add(target)
    return found


def read(
    document,
    grid: int,
    ids: Iterable[str] | None = None,
    span: tuple[int, int] | None = None,
    lock: bool = False,
) -> dict[str, tuple[int, Row]]:
    """The rows given, by id or by the span of their places with both ends, each with its place,
    as the grid holds them in memory: each formula's distances the ids of the rows they reach,
    and what is shared in place of its key. Locked for a change where asked."""
    with connection.cursor() as cursor:
        if span is not None:
            first, last = max(span[0], 0), span[1]
            if last < first:
                return {}
            cursor.execute(
                f"SELECT {_COLUMNS} FROM content_gridrow r WHERE r.id IN ("
                "SELECT id FROM content_gridrow WHERE grid_id = %s ORDER BY position "
                f"OFFSET %s LIMIT %s){' FOR UPDATE' if lock else ''}",
                [grid, first, last - first + 1],
            )
        else:
            wanted = list(set(ids or ()))
            if not wanted:
                return {}
            cursor.execute(
                f"SELECT {_COLUMNS} FROM content_gridrow r WHERE r.grid_id = %s "
                f"AND r.row = ANY(%s){' FOR UPDATE' if lock else ''}",
                [grid, wanted],
            )
        stored = cursor.fetchall()
    keys = set()
    rows = []
    for id, height, cells, values, position, pk, look, shown, hidden, place in stored:
        cells = _jsonb(cells)
        keys |= _keys(cells)
        if look:
            keys.add(look)
        rows.append(
            (
                place,
                Row(id, height, cells, _jsonb(values), position, pk, look, _jsonb(shown), hidden),
            )
        )
    shared = _shared(document, keys)
    reached = {
        place + distance
        for place, row in rows
        for distance in _distances(row.cells, shared)
        if distance
    }
    known = {place: row.id for place, row in rows}
    known |= ids_at(grid, reached - known.keys())
    reach = Reach(count(grid) if reached else 0, known)
    found = {}
    for place, row in rows:
        row.cells = decoded(row.cells, shared, row.id, place, reach)
        row.look = shared.get(row.look) if row.look else None
        found[row.id] = (place, row)
    return found


def reach(document) -> int:
    """How far, in rows, any formula of the document reaches from its own row."""
    found = 0
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT value FROM content_shared WHERE document_id = %s "
            "AND jsonb_typeof(value) = 'array'",
            [getattr(document, "pk", document)],
        )
        for (value,) in cursor.fetchall():
            for distance in _distances({"": {FORMULA: "k"}}, {"k": _jsonb(value)}):
                found = max(found, abs(distance))
    return found


def mentioning(document, ids: Iterable[str], grid: int | None = None) -> dict[str, list[str]]:
    """The rows whose formulas name any of the rows or columns given by id, as kept, by table:
    of every grid of the document, or of the one given."""
    ids = list(set(ids))
    if not ids:
        return {}
    document = getattr(document, "pk", document)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key FROM content_shared WHERE document_id = %s "
            "AND jsonb_typeof(value) = 'array' AND EXISTS (SELECT 1 FROM "
            "jsonb_array_elements(value) p WHERE ARRAY[p->'from'->>'row', p->'to'->>'row', "
            "p->'from'->>'col', p->'to'->>'col'] && %s::text[])",
            [document, ids],
        )
        keys = [key for (key,) in cursor.fetchall()]
        if not keys:
            return {}
        cursor.execute(
            "SELECT g.table, r.row FROM content_gridrow r JOIN content_grid g ON g.id = r.grid_id "
            "WHERE g.document_id = %s AND (%s::bigint IS NULL OR g.id = %s) AND EXISTS "
            "(SELECT 1 FROM jsonb_each(r.cells) e WHERE e.value->>'formula' = ANY(%s))",
            [document, grid, grid, keys],
        )
        found: dict[str, list[str]] = {}
        for table, id in cursor.fetchall():
            found.setdefault(table, []).append(id)
        return found


def referring(document, table: str) -> bool:
    """Whether a formula of the document's tables, as Postgres keeps them, names the table."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM content_gridrow r JOIN content_grid g "
            "ON g.id = r.grid_id, jsonb_each(r.cells) e WHERE g.document_id = %s "
            "AND e.value->>'formula' IN (SELECT key FROM content_shared "
            "WHERE document_id = %s AND jsonb_typeof(value) = 'array' AND EXISTS (SELECT 1 "
            "FROM jsonb_array_elements(value) p WHERE p->>'table' = %s)))",
            [getattr(document, "pk", document)] * 2 + [table],
        )
        return cursor.fetchone()[0]


def parts(
    document, grid: int, wanted: Collection[str] | None = None
) -> Iterator[list[tuple[int, Row]]]:
    """The rows of the grid in their order, or those of them wanted, each with its place and as
    `read` gives it, a few thousand at a time."""
    document = getattr(document, "pk", document)
    every = ids_in(grid, 0, count(grid) - 1)
    chosen = [(at, id) for at, id in enumerate(every) if wanted is None or id in wanted]
    for first in range(0, len(chosen), _AT_ONCE):
        part = chosen[first : first + _AT_ONCE]
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_FIELDS} FROM content_gridrow WHERE grid_id = %s AND row = ANY(%s)",
                [grid, [id for _, id in part]],
            )
            read_rows = {each[0]: each for each in cursor.fetchall()}
        rows = []
        keys: set[str] = set()
        for at, id in part:
            if (found := read_rows.get(id)) is None:
                continue
            _, height, cells, values, position, pk, look, shown, hidden = found
            cells = _jsonb(cells)
            keys |= _keys(cells) | ({look} if look else set())
            rows.append(
                (
                    at,
                    Row(
                        id, height, cells, _jsonb(values), position, pk, look, _jsonb(shown), hidden
                    ),
                )
            )
        shared = _shared(document, keys)
        for at, row in rows:
            row.cells = decoded(row.cells, shared, row.id, at, every)
            row.look = shared.get(row.look) if row.look else None
        yield rows


def naming(document, grid: int, table: str, own: bool) -> Iterator[Row]:
    """The rows of the grid, as `read` gives them, whose formulas name the table: by name, or,
    where the grid is the table's own, without one. A few thousand at a time."""
    document = getattr(document, "pk", document)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key FROM content_shared WHERE document_id = %s "
            "AND jsonb_typeof(value) = 'array' AND EXISTS (SELECT 1 FROM "
            "jsonb_array_elements(value) p WHERE jsonb_typeof(p) = 'object' "
            "AND (p->>'table' = %s OR (%s AND p->>'table' IS NULL)))",
            [document, table, own],
        )
        keys = [key for (key,) in cursor.fetchall()]
        if not keys:
            return
        cursor.execute(
            "SELECT r.row FROM content_gridrow r WHERE r.grid_id = %s AND EXISTS "
            "(SELECT 1 FROM jsonb_each(r.cells) e WHERE e.value->>'formula' = ANY(%s)) "
            "ORDER BY r.position",
            [grid, keys],
        )
        ids = [id for (id,) in cursor.fetchall()]
    for part in parts(document, grid, set(ids)):
        for _, row in part:
            yield row


def kept_in(patches: Iterable[dict]) -> set[str]:
    """The keys of the rows the patches keep in Postgres."""
    found = set()
    for patch in patches:
        for edit in patch.get("rows", {}).get("edits", []):
            if edit[0] == "out":
                found.add(edit[2])
            elif edit[0] == "order":
                found.add(edit[3])
            elif isinstance(edit[3], dict):
                found.add(edit[3]["kept"])
    return found


def unshare(document, kept: Iterable[str]) -> None:
    """Forgets the rows kept for changes none can take back any more, all those that can given
    by their keys, then what no row of the document, kept or not, and no column shares."""
    document = getattr(document, "pk", document)
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM content_keptrow WHERE document_id = %s AND NOT key = ANY(%s)",
            [document, list(kept)],
        )
        cursor.execute(
            "WITH used AS ("
            "SELECT e.value->>'formula' AS key FROM content_gridrow r JOIN content_grid g "
            "ON g.id = r.grid_id, jsonb_each(r.cells) e WHERE g.document_id = %s "
            "UNION SELECT e.value->>'look' FROM content_gridrow r JOIN content_grid g "
            "ON g.id = r.grid_id, jsonb_each(r.cells) e WHERE g.document_id = %s "
            "UNION SELECT r.look FROM content_gridrow r JOIN content_grid g "
            "ON g.id = r.grid_id WHERE g.document_id = %s "
            "UNION SELECT c->>'look' FROM content_grid g, jsonb_array_elements(g.cols) c "
            "WHERE g.document_id = %s "
            "UNION SELECT e.value->>'formula' FROM content_keptrow k, jsonb_each(k.cells) e "
            "WHERE k.document_id = %s "
            "UNION SELECT e.value->>'look' FROM content_keptrow k, jsonb_each(k.cells) e "
            "WHERE k.document_id = %s "
            "UNION SELECT k.look FROM content_keptrow k WHERE k.document_id = %s) "
            "DELETE FROM content_shared WHERE document_id = %s "
            "AND key NOT IN (SELECT key FROM used WHERE key IS NOT NULL)",
            [document] * 8,
        )


def cells_of(grid: int, ids: Iterable[str]) -> dict[str, dict]:
    """The cells of the rows given as Postgres keeps them, formulas and looks by their keys."""
    wanted = list(set(ids))
    if not wanted:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT row, cells FROM content_gridrow WHERE grid_id = %s AND row = ANY(%s)",
            [grid, wanted],
        )
        return {id: _jsonb(cells) for id, cells in cursor.fetchall()}


def columns(grid: int, ids: Iterable[str], cols: Iterable[str]) -> dict[str, tuple]:
    """Of each row given, the values, the texts shown and the cells of the columns given, as
    Postgres keeps them."""
    wanted, cols = list(set(ids)), list(set(cols))
    if not wanted or not cols:
        return {}
    picked = "(SELECT jsonb_object_agg(k, v) FROM jsonb_each(r.{}) e(k, v) WHERE k = ANY(%s))"
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT r.row, {picked.format('"values"')}, {picked.format('shown')}, "
            f"{picked.format('cells')} FROM content_gridrow r "
            "JOIN unnest(%s::varchar[]) AS u(row) ON u.row = r.row WHERE r.grid_id = %s",
            [cols, cols, cols, wanted, grid],
        )
        return {
            id: (_jsonb(values) or {}, _jsonb(shown) or {}, _jsonb(cells) or {})
            for id, values, shown, cells in cursor.fetchall()
        }


def subtotalling(document, grid: int) -> list[str]:
    """The rows of the table with a formula that may subtotal: its text names SUBTOTAL."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT r.row FROM content_gridrow r WHERE r.grid_id = %s AND (r.cells::text "
            "ILIKE '%%subtotal(%%' OR EXISTS (SELECT 1 FROM jsonb_each(r.cells) e "
            "WHERE e.value->>'formula' IN (SELECT key FROM content_shared WHERE "
            "document_id = %s AND value::text ILIKE '%%subtotal(%%')))",
            [grid, getattr(document, "pk", document)],
        )
        return [id for (id,) in cursor.fetchall()]


SHOWN = (
    "(SELECT k.key, CASE WHEN t.text LIKE '''%%' AND NOT r.shown ? k.key "
    "THEN substr(t.text, 2) ELSE t.text END "
    "FROM (SELECT jsonb_object_keys(r.cells) UNION SELECT jsonb_object_keys(r.shown)) k(key), "
    "LATERAL (SELECT coalesce(r.shown ->> k.key, r.cells -> k.key ->> 'text')) t(text))"
)


def matching(
    grid: int, pattern: str, case: bool, limit: int | None, besides: Iterable[str] = ()
) -> list[tuple[str, int, str, str]]:
    """The cells of the table, but in the rows given besides and those hidden, whose text
    shown matches the regular expression, its case counting or not: each one's row, the row's
    position, its column and that text, in the table's order, at most `limit` of them."""
    operator = "~" if case else "~*"
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT r.row, r.position, c.key, c.text FROM content_gridrow r "
            f"CROSS JOIN LATERAL {SHOWN} c(key, text) "
            f"WHERE r.grid_id = %s AND NOT r.hidden AND r.row <> ALL(%s) "
            f"AND c.text {operator} %s ORDER BY r.position LIMIT %s",
            [grid, list(besides), pattern, limit],
        )
        return cursor.fetchall()


def positions(grid: int, ids: Iterable[str]) -> dict[str, int]:
    """The position of each row given, of those the table has."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT row, position FROM content_gridrow WHERE grid_id = %s AND row = ANY(%s)",
            [grid, list(set(ids))],
        )
        return dict(cursor.fetchall())
