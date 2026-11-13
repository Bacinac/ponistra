"""A table's patch applied as SQL over its rows (D22, E3), the one way a grid a book holds is
changed: by a change to a draft of the table, by a change taken back, with a guard, each part
only where nobody changed it since.

A row's formulas are held by the ids of the rows they name and kept by how far those rows
stand (grids.stored_formula), so lines put in, taken out or reordered change what is kept of
the formulas that reach across them, never what they hold: each such edit reads the rows within
the reach of any formula of the document from where it happens as they are held, makes it, and
writes again those whose kept form changed. What a range covers once its lines change is the
change's to say (sheets), in the cells it writes.

Rows taken out, the places of rows reordered and the cells of columns taken out go to `KeptRow`
under a key of the edit, which the patch names in their place; taking the edit back reads them
from there. A row taken out is kept as it stood among those taken out with it: its formulas by
how far the rows they name stood within that run, by id beyond it."""

import json
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.utils import timezone

from apps.documents.models import Node
from apps.engine.values import loaded

from . import grids
from . import rows as stored
from .grids import COLS, FORMULA, OWN, ROWS, STEP, TEXT, TO, Col, Formula, Look, Row, cleaned
from .models import Grid, GridRow, KeptRow, Shared
from .table import Table

# More lines than this put in, taken out or reordered at once have a browser read the table
# again rather than be told each of them.
TOLD = 1000
READ = 2000

_TYPES = {
    "cells": "jsonb",
    "height": "double precision",
    "look": "varchar",
    "hidden": "boolean",
    "position": "bigint",
}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _jsonb(given):
    return json.loads(given) if isinstance(given, str) else given


def _merged(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    found: list[list[int]] = []
    for first, last in sorted((max(first, 0), last) for first, last in spans):
        if last < first:
            continue
        if found and first <= found[-1][1] + 1:
            found[-1][1] = max(found[-1][1], last)
        else:
            found.append([first, last])
    return [(first, last) for first, last in found]


def _runs(places: Iterable[int]) -> list[tuple[int, int]]:
    """The places as runs of consecutive ones, each (first, count)."""
    found: list[list[int]] = []
    for place in sorted(set(places)):
        if found and place == found[-1][0] + found[-1][1]:
            found[-1][1] += 1
        else:
            found.append([place, 1])
    return [(first, count) for first, count in found]


def _targets(cells: Mapping[str, dict]) -> set[str]:
    """The rows of its own table the cells' formulas name by id."""
    found = set()
    for cell in cells.values():
        for piece in cell.get(FORMULA) or ():
            if isinstance(piece, dict) and "table" not in piece:
                for end in ("from", "to"):
                    target = (piece.get(end) or {}).get("row")
                    if isinstance(target, str) and target != OWN:
                        found.add(target)
    return found


@dataclass
class Done:
    """A patch as it went: what it did, each part with what it found as its before, the table
    as it left it, by column the keys of the formulas it wrote, the rows whose formulas it kept
    again at other distances, the rows it put in, those it took out and those that stood
    beside them, and how
    its lines moved as a browser is told, none where too many did."""

    patch: dict | None
    table: Table | None
    keys: dict[str, set[str]] = field(default_factory=dict)
    restated: set[str] = field(default_factory=set)
    put: set[str] = field(default_factory=set)
    out: set[str] = field(default_factory=set)
    beside: set[str] = field(default_factory=set)
    told: list[dict] | None = field(default_factory=list)


class _Run:
    """One patch of a table being applied: the table's outline as it goes, the shared values
    written, the rows touched and the reach of the document's formulas."""

    def __init__(self, document, table: Table, guard: bool):
        self.document = document
        self.table = table
        self.grid = table.grid
        self.guard = guard
        self.written: dict[str, Formula | Look] = {}
        self.keys: dict[str, set[str]] = {}
        self.restated: set[str] = set()
        self.arrived: set[str] = set()
        self.gone: set[str] = set()
        self.beside: set[str] = set()
        self.told: list[dict] | None = []
        self._reach: int | None = None

    @property
    def reach(self) -> int:
        if self._reach is None:
            self._reach = stored.reach(self.document)
        return self._reach

    def tell(self, lines: dict | None) -> None:
        """Notes how the lines moved, as a browser is told; none, too many to tell."""
        if self.told is not None:
            if lines is None:
                self.told = None
            else:
                self.told.append(lines)

    def refused(self, why: str) -> bool:
        """False where a guard lets a part that no longer applies go; raises without one."""
        if self.guard:
            return False
        raise ValueError(why)

    # Reading and writing rows

    def held(self, spans: Iterable[tuple[int, int]]) -> dict[str, tuple[int, Row]]:
        found: dict[str, tuple[int, Row]] = {}
        for first, last in _merged(spans):
            found |= stored.read(self.document, self.grid, span=(first, last), lock=True)
        return found

    def encode(self, held: Iterable[Row], cells: Mapping[str, Mapping[str, dict]] | None = None):
        """The cells of the rows, theirs or those given by row, as Postgres keeps them by where
        the rows now stand."""
        held = list(held)
        given = cells or {row.id: row.cells for row in held}
        ids = {row.id for row in held} | {
            target for row in held for target in _targets(given[row.id])
        }
        at = stored.places_of(self.grid, ids)
        found = {}
        for row in held:
            found[row.id] = grids.encoded(given[row.id], row.id, at, self.written)
            for col, cell in found[row.id].items():
                if isinstance(key := cell.get(FORMULA), str):
                    self.keys.setdefault(col, set()).add(key)
        return found

    def share(self) -> None:
        if self.written:
            Shared.objects.bulk_create(
                [
                    Shared(document_id=self.document, key=key, value=value)
                    for key, value in self.written.items()
                ],
                batch_size=2000,
                ignore_conflicts=True,
            )
            self.written = {}

    def write(self, values: list[dict], *fields: str) -> None:
        """Writes the fields given of the rows, each value by its row's primary key as `id`."""
        self.share()
        if not values:
            return
        sets = ", ".join(f"{name} = u.{name}" for name in fields)
        kinds = ", ".join(["id bigint", *(f"{name} {_TYPES[name]}" for name in fields)])
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE content_gridrow r SET {sets} FROM jsonb_to_recordset(%s::jsonb) "
                f"AS u({kinds}) WHERE r.id = u.id",
                [_json(values)],
            )

    def restate(self, held: Iterable[Row]) -> None:
        """Writes again those of the rows, as they were held, still there whose kept form the
        edit just made changed."""
        held = list(held)
        present = stored.places_of(self.grid, [row.id for row in held])
        held = [row for row in held if row.id in present]
        if not held:
            return
        kept = dict(
            GridRow.objects.filter(pk__in=[row.pk for row in held]).values_list("pk", "cells")
        )
        now = self.encode(held)
        changed = [
            {"id": row.pk, "cells": now[row.id]} for row in held if now[row.id] != kept[row.pk]
        ]
        self.restated |= {row.id for row in held if now[row.id] != kept[row.pk]}
        self.write(changed, "cells")

    def named_by(self, ids: Iterable[str]) -> list[Row]:
        """The rows of the table whose formulas name any of the rows given by id."""
        found = stored.mentioning(self.document, ids, self.grid).get(self.table.table, [])
        held = stored.read(self.document, self.grid, found, lock=True)
        return [row for _, row in held.values()]

    def forget(self, ids: set[str]) -> None:
        """Takes the rows given out of the table's outline."""
        table = self.table
        for id in ids & table.heights.keys():
            del table.heights[id]
        for id in ids & table.looks.keys():
            del table.looks[id]
        table.hidden -= ids
        table.merges = {
            key: to
            for key, to in table.merges.items()
            if key.partition(":")[0] not in ids and to.partition(":")[0] not in ids
        }

    def note(self, row: Row) -> None:
        """Puts the row's layout in the table's outline."""
        table = self.table
        self.forget({row.id})
        if row.height is not None:
            table.heights[row.id] = row.height
        if row.look is not None:
            table.looks[row.id] = row.look
        if row.hidden:
            table.hidden.add(row.id)
        for col, cell in row.cells.items():
            if isinstance(to := cell.get(TO), str) and to:
                table.merges[f"{row.id}:{col}"] = to

    def noted(self, ids: list[str]) -> None:
        """Puts the layout of the rows given, as stored, in the table's outline."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT row, height, look, hidden, (SELECT jsonb_object_agg(k, v->'to') FROM "
                "jsonb_each(cells) AS e(k, v) WHERE v ? 'to') FROM content_gridrow "
                "WHERE grid_id = %s AND row = ANY(%s) AND (height IS NOT NULL OR look <> '' "
                "OR hidden OR jsonb_path_exists(cells, '$.*.to'))",
                [self.grid, ids],
            )
            found = cursor.fetchall()
        shared = stored._shared(self.document, {look for _, _, look, _, _ in found if look})
        for id, height, look, hidden, merges in found:
            cells = {col: {TO: to} for col, to in (_jsonb(merges) or {}).items()}
            self.note(Row(id, height, cells, look=shared.get(look), hidden=hidden))

    # Rows put in

    def room(self, at: int, count: int) -> list[int]:
        """Positions for rows put in at the place given, between their neighbours', the rows
        from there spaced out where there is no room left."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT position FROM content_gridrow WHERE grid_id = %s ORDER BY position "
                "OFFSET %s LIMIT %s",
                [self.grid, max(at - 1, 0), 2 if at else 1],
            )
            around = [position for (position,) in cursor.fetchall()]
            low = around.pop(0) if at else 0
            high = around[0] if around else None
            if high is None:
                return [low + (offset + 1) * STEP for offset in range(count)]
            if high - low > count:
                step = (high - low) // (count + 1)
                return [low + (offset + 1) * step for offset in range(count)]
            cursor.execute(
                "UPDATE content_gridrow g SET position = (s.n + CASE WHEN s.n > %s THEN %s "
                "ELSE 0 END) * %s FROM (SELECT id, row_number() OVER (ORDER BY position) AS n "
                "FROM content_gridrow WHERE grid_id = %s) s WHERE g.id = s.id",
                [at, count, STEP, self.grid],
            )
        return [(at + 1 + offset) * STEP for offset in range(count)]

    def put(self, edit: list) -> list | None:
        at, prev, what = (edit[1], None, edit[2]) if len(edit) == 3 else edit[1:]
        size = self.table.size
        if prev is not None and (found := stored.places_of(self.grid, [prev])):
            at = found[prev] + 1
        at = min(max(at, 0), size)
        prev = stored.ids_at(self.grid, [at - 1]).get(at - 1) if at else None
        reach = self.reach
        near = self.held([(at - reach, at + reach - 1)]) if reach else {}
        if isinstance(what, dict):
            done = self.put_kept(at, what)
        else:
            done = self.put_lines(at, what)
        if done is None:
            return None
        self.restate(row for _, row in near.values())
        return ["put", at, prev, done]

    def put_lines(self, at: int, lines: list) -> list | None:
        taken = set(stored.places_of(self.grid, [id for id, _ in lines]))
        if taken:
            self.refused(f"rows {sorted(taken)[0]} exists")
            lines = [[id, line] for id, line in lines if id not in taken]
        if not lines:
            return None
        made = [
            Row(
                id,
                line.get("size"),
                {col: cell for col, cell in line.get("cells", {}).items() if cleaned(cell)},
                look=grids.look(line["look"]) if line.get("look") is not None else None,
                hidden=line.get("hidden", False),
            )
            for id, line in lines
        ]
        created = GridRow.objects.bulk_create(
            [
                GridRow(
                    grid_id=self.grid,
                    row=row.id,
                    position=position,
                    height=row.height,
                    look=grids.keyed(row.look, self.written) or "",
                    hidden=row.hidden,
                )
                for row, position in zip(made, self.room(at, len(made)), strict=True)
            ],
            batch_size=2000,
        )
        for row, each in zip(made, created, strict=True):
            row.pk = each.pk
            self.note(row)
        cells = self.encode(made)
        self.write([{"id": row.pk, "cells": cells[row.id]} for row in made], "cells")
        self.table.size += len(made)
        self.arrived |= {row.id for row in made}
        self.restate(self.named_by([row.id for row in made]))
        self.tell(
            {
                "put": [
                    [row.id, at + offset, row.height, row.look, row.hidden]
                    for offset, row in enumerate(made)
                ]
            }
            if len(made) <= TOLD
            else None
        )
        return [[row.id, _line(row)] for row in made]

    def put_kept(self, at: int, what: dict) -> dict | None:
        key, first, count = what["kept"], what.get("from", 0), what["count"]
        kept = KeptRow.objects.filter(
            document=self.document, key=key, ordinal__gte=first, ordinal__lt=first + count
        )
        ids = list(kept.order_by("ordinal").values_list("row", flat=True))
        if len(ids) != count:
            self.refused(f"kept rows {key} gone")
            return None
        if taken := stored.places_of(self.grid, ids):
            self.refused(f"rows {sorted(taken)[0]} exists")
            return None
        reach = self.reach
        edges = [*range(min(reach, count)), *range(max(count - reach, reach), count)]
        reached = {*range(min(2 * reach, count)), *range(max(count - 2 * reach, 0), count)}
        local = {
            each.ordinal - first: each
            for each in kept.filter(ordinal__in=[first + at for at in reached])
        }
        positions = self.room(at, count)
        step = positions[1] - positions[0] if count > 1 else 0
        middle = (min(reach, count), max(count - reach, min(reach, count)))
        with connection.cursor() as cursor:
            if middle[1] > middle[0]:
                cursor.execute(
                    "INSERT INTO content_gridrow (grid_id, row, position, height, look, hidden, "
                    'cells, "values", shown) SELECT %s, row, %s + (ordinal - %s) * %s, height, '
                    "look, hidden, cells, '{}', '{}' FROM content_keptrow WHERE document_id = %s "
                    "AND key = %s AND ordinal >= %s AND ordinal < %s",
                    [
                        self.grid,
                        positions[0],
                        first,
                        step,
                        self.document,
                        key,
                        first + middle[0],
                        first + middle[1],
                    ],
                )
                cursor.execute(
                    "SELECT DISTINCT e.key, e.value->>'formula' FROM content_keptrow k, "
                    "jsonb_each(k.cells) e WHERE k.document_id = %s AND k.key = %s "
                    "AND k.ordinal >= %s AND k.ordinal < %s AND e.value ? 'formula'",
                    [self.document, key, first + middle[0], first + middle[1]],
                )
                for col, formula in cursor.fetchall():
                    self.keys.setdefault(col, set()).add(formula)
        shared = stored._shared(
            self.document,
            {part for each in local.values() for part in stored._keys(each.cells)}
            | {each.look for each in local.values() if each.look},
        )
        reach_of = stored.Reach(count, {at: each.row for at, each in local.items()})
        made = []
        for offset in edges:
            each = local[offset]
            made.append(
                Row(
                    each.row,
                    each.height,
                    grids.decoded(each.cells, shared, each.row, offset, reach_of),
                    position=positions[offset],
                    look=shared.get(each.look) if each.look else None,
                    hidden=each.hidden,
                )
            )
        created = GridRow.objects.bulk_create(
            [
                GridRow(
                    grid_id=self.grid,
                    row=row.id,
                    position=row.position,
                    height=row.height,
                    look=grids.keyed(row.look, self.written) or "",
                    hidden=row.hidden,
                )
                for row in made
            ],
            batch_size=2000,
        )
        for row, each in zip(made, created, strict=True):
            row.pk = each.pk
        cells = self.encode(made)
        self.write([{"id": row.pk, "cells": cells[row.id]} for row in made], "cells")
        self.table.size += count
        self.arrived |= set(ids)
        self.noted(ids)
        self.restate(self.named_by(ids))
        self.tell(self.told_kept(at, kept) if count <= TOLD else None)
        return {"kept": key, "from": first, "count": count}

    def told_kept(self, at: int, kept) -> dict:
        lines = list(kept.order_by("ordinal").values_list("row", "height", "look", "hidden"))
        shared = stored._shared(self.document, {look for _, _, look, _ in lines if look})
        return {
            "put": [
                [id, at + offset, height, shared.get(look) if look else None, hidden]
                for offset, (id, height, look, hidden) in enumerate(lines)
            ]
        }

    # Rows taken out

    def out(self, edit: list) -> list | None:
        given = edit[1]
        if isinstance(given, dict):
            if "kept" in given:
                first, count = given.get("from", 0), given["count"]
                ids = KeptRow.objects.filter(
                    document=self.document,
                    key=given["kept"],
                    ordinal__gte=first,
                    ordinal__lt=first + count,
                ).values_list("row", flat=True)
            else:
                ids = given["rows"]
            places = sorted(stored.places_of(self.grid, ids).values())
        else:
            places = sorted({place for place in given if 0 <= place < self.table.size})
        if not places:
            return None
        if len(places) >= self.table.size:
            self.refused("a table keeps a row")
            return None
        runs = _runs(places)
        reach = self.reach
        spans = []
        for first, count in runs:
            last = first + count - 1
            spans += [(first - reach, first + reach - 1), (last - reach + 1, last + reach)]
        near = self.held(spans) if reach else {}
        gone = set(places)
        around = stored.ids_at(
            self.grid, {first - 1 for first, _ in runs} | {first + count for first, count in runs}
        )
        self.beside |= {id for place, id in around.items() if place not in gone}
        frozen = self.table.frozen
        if frozen and (stood := stored.places_of(self.grid, [frozen]).get(frozen)) in gone:
            above = next((place for place in range(stood, -1, -1) if place not in gone), None)
            self.table.frozen = None if above is None else stored.ids_at(self.grid, [above])[above]
        key = secrets.token_hex(16)
        ordinals, ordinal = [], 0
        for _, count in runs:
            ordinals.append(ordinal)
            ordinal += count
        taken: set[str] = set()
        for (first, count), ordinal in reversed(list(zip(runs, ordinals, strict=True))):
            taken |= self.take(key, first, count, ordinal, near)
        self.gone |= taken
        self.forget(taken)
        self.table.size -= len(places)
        self.restate(row for place, row in near.values() if place not in gone)
        self.tell({"out": places} if len(places) <= TOLD else None)
        return [
            "out",
            [[first, count, around.get(first - 1)] for first, count in runs],
            key,
        ]

    def take(
        self, key: str, first: int, count: int, ordinal: int, near: Mapping[str, tuple[int, Row]]
    ) -> set[str]:
        """Takes the run of rows out to the key, the rows near its ends kept as they stood
        within it and those between moved as they are."""
        reach = self.reach
        edges = [
            (place, row)
            for place, row in near.values()
            if first <= place < first + count
            and (place - first < reach or first + count - place <= reach)
        ]
        targets = {target for _, row in edges for target in _targets(row.cells)}
        local = {
            id: place - first
            for id, place in stored.places_of(
                self.grid, targets | {row.id for _, row in edges}
            ).items()
            if first <= place < first + count
        }
        KeptRow.objects.bulk_create(
            [
                KeptRow(
                    document_id=self.document,
                    key=key,
                    ordinal=ordinal + place - first,
                    row=row.id,
                    position=row.position,
                    height=row.height,
                    look=grids.keyed(row.look, self.written) or "",
                    hidden=row.hidden,
                    cells=grids.encoded(row.cells, row.id, local, self.written),
                )
                for place, row in edges
            ],
            batch_size=2000,
        )
        self.share()
        taken = {row.id for _, row in edges}
        low = first + min(reach, count)
        high = max(first + count - reach, low)
        with connection.cursor() as cursor:
            if high > low:
                cursor.execute(
                    "WITH gone AS (DELETE FROM content_gridrow WHERE id IN (SELECT id FROM "
                    "content_gridrow WHERE grid_id = %s ORDER BY position OFFSET %s LIMIT %s) "
                    "RETURNING row, position, height, look, hidden, cells) "
                    "INSERT INTO content_keptrow (document_id, key, ordinal, row, position, "
                    "height, look, hidden, cells) SELECT %s, %s, %s + row_number() OVER "
                    "(ORDER BY position) - 1, row, position, height, look, hidden, cells "
                    "FROM gone RETURNING row",
                    [self.grid, low, high - low, self.document, key, ordinal + low - first],
                )
                taken |= {id for (id,) in cursor.fetchall()}
            cursor.execute(
                "DELETE FROM content_gridrow WHERE id = ANY(%s)", [[row.pk for _, row in edges]]
            )
        return taken

    # Rows reordered

    def order(self, edit: list) -> list | None:
        given = edit[2]
        if isinstance(given, dict):
            kept = KeptRow.objects.filter(document=self.document, key=given["kept"])
            ids = list(kept.order_by("position").values_list("row", flat=True))
        else:
            ids = list(given)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, row, position FROM content_gridrow WHERE grid_id = %s "
                "AND row = ANY(%s) ORDER BY position",
                [self.grid, ids],
            )
            now = cursor.fetchall()
        if len(now) != len(set(ids)) or len(now) != len(ids):
            self.refused("rows to order are not the table's")
            return None
        if [id for _, id, _ in now] == ids:
            return None
        pks = {id: pk for pk, id, _ in now}
        places = stored.places_of(self.grid, ids)
        first, last = min(places.values()), max(places.values())
        reach = self.reach
        near = self.held([(first - reach, last + reach)])
        key = secrets.token_hex(16)
        KeptRow.objects.bulk_create(
            [
                KeptRow(document_id=self.document, key=key, ordinal=at, row=id, position=position)
                for at, (_, id, position) in enumerate(now)
            ],
            batch_size=2000,
        )
        self.write(
            [
                {"id": pks[id], "position": position}
                for id, (_, _, position) in zip(ids, now, strict=True)
            ],
            "position",
        )
        self.restate(row for _, row in near.values())
        self.tell({"order": [first, ids]} if len(ids) <= TOLD else None)
        return ["order", first, len(ids), key]

    # Columns

    def cols(self, lines: dict) -> dict:
        table = self.table
        found: dict = {}
        ids = table.col_ids()
        if gone := {id for id, *_ in lines.get("out", [])} & set(ids):
            key = self.keep_cols(gone)
            found["out"] = [
                [id, ids[at - 1] if at else None, at, _col_line(table.cols[at], key)]
                for at, id in enumerate(ids)
                if id in gone
            ]
            table.cols = [col for col in table.cols if col.id not in gone]
            table.merges = {
                spot: to for spot, to in table.merges.items() if spot.partition(":")[2] not in gone
            }
            ids = table.col_ids()
        if "order" in lines:
            before, after = lines["order"]
            moving = set(before)
            if set(after) == moving and moving <= set(ids):
                slots = [at for at, id in enumerate(ids) if id in moving]
                current = [ids[at] for at in slots]
                if (not self.guard or current == before) and current != after:
                    found["order"] = [current, list(after)]
                    by_id = {col.id: col for col in table.cols}
                    for at, id in zip(slots, after, strict=True):
                        table.cols[at] = by_id[id]
                    ids = table.col_ids()
        brought: dict[str, list] = {}
        for entry in lines.get("put", []):
            if entry[0] in brought or entry[0] in set(ids):
                self.refused(f"cols {entry[0]} exists")
                continue
            brought[entry[0]] = entry
        if brought:
            order = grids._with_put(ids, brought)
            at_of = {id: at for at, id in enumerate(order)}
            found["put"] = [
                [id, order[at_of[id] - 1] if at_of[id] else None, at_of[id], line]
                for id, (_, _, _, line) in sorted(brought.items(), key=lambda kv: at_of[kv[0]])
            ]
            by_id = {col.id: col for col in table.cols}
            for id, (_, _, _, line) in brought.items():
                by_id[id] = Col(
                    id,
                    line.get("size"),
                    grids.look(line["look"]) if line.get("look") is not None else None,
                    line.get("hidden", False),
                )
            table.cols = [by_id[id] for id in order]
            self.put_cols(brought)
        return found

    def keep_cols(self, gone: set[str]) -> str | None:
        """Takes the cells of the columns out to a key, as their rows held them."""
        cols = sorted(gone)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT row FROM content_gridrow WHERE grid_id = %s AND cells ?| %s",
                [self.grid, cols],
            )
            ids = [id for (id,) in cursor.fetchall()]
        if not ids:
            return None
        key = secrets.token_hex(16)
        held = stored.read(self.document, self.grid, ids, lock=True)
        KeptRow.objects.bulk_create(
            [
                KeptRow(
                    document_id=self.document,
                    key=key,
                    ordinal=at,
                    row=row.id,
                    position=0,
                    cells={col: row.cells[col] for col in cols if col in row.cells},
                )
                for at, (_, row) in enumerate(sorted(held.values(), key=lambda each: each[0]))
            ],
            batch_size=2000,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE content_gridrow SET cells = cells - %s::text[] WHERE grid_id = %s "
                "AND cells ?| %s",
                [cols, self.grid, cols],
            )
        return key

    def put_cols(self, brought: Mapping[str, list]) -> None:
        """Writes the cells of the columns put in, given or kept."""
        given: dict[str, dict[str, dict]] = {}
        for id, (_, _, _, line) in brought.items():
            if key := line.get("kept"):
                for row, cells in KeptRow.objects.filter(
                    document=self.document, key=key
                ).values_list("row", "cells"):
                    if id in cells:
                        given.setdefault(row, {})[id] = cells[id]
            for row, cell in line.get("cells", {}).items():
                if cell := cleaned(cell):
                    given.setdefault(row, {})[id] = cell
        if not given:
            return
        held = stored.read(self.document, self.grid, given, lock=True)
        rows = [row for _, row in held.values()]
        cells = self.encode(rows, {row.id: given[row.id] for row in rows})
        kept = dict(
            GridRow.objects.filter(pk__in=[row.pk for row in rows]).values_list("pk", "cells")
        )
        for row in rows:
            row.cells |= given[row.id]
            self.note(row)
        self.write([{"id": row.pk, "cells": kept[row.pk] | cells[row.id]} for row in rows], "cells")

    # What changes of rows that stay

    def lines(self, patch: dict, done: dict) -> None:
        ids = set(patch.get("heights", {})) | set(patch.get("cells", {}))
        for part in ("looks", "hidden"):
            ids |= set(patch.get(part, {}).get(ROWS, {}))
        if not ids:
            return
        read = stored.read(self.document, self.grid, ids, lock=True)
        held = {id: row for id, (_, row) in read.items()}
        cols = set(self.table.col_ids())
        changed: dict[str, Row] = {}
        heights = {}
        for id, (before, after) in patch.get("heights", {}).items():
            row = held.get(id)
            if row is None or (self.guard and row.height != before) or row.height == after:
                continue
            heights[id] = [row.height, after]
            row.height = after
            changed[id] = row
        if heights:
            done["heights"] = heights
        for part in ("looks", "hidden"):
            for id, (before, after) in patch.get(part, {}).get(ROWS, {}).items():
                if (row := held.get(id)) is None:
                    continue
                now = row.look if part == "looks" else row.hidden
                if (self.guard and now != before) or now == after:
                    continue
                done.setdefault(part, {}).setdefault(ROWS, {})[id] = [now, after]
                if part == "looks":
                    row.look = grids.look(after) if after is not None else None
                else:
                    row.hidden = after
                changed[id] = row
        written = set()
        cells: dict = {}
        for id, by_col in patch.get("cells", {}).items():
            row = held.get(id)
            if row is None:
                continue
            for col, (before, after) in by_col.items():
                if col not in cols:
                    continue
                now, after = cleaned(row.cells.get(col)), cleaned(after)
                if (self.guard and now != cleaned(before)) or now == after:
                    continue
                cells.setdefault(id, {})[col] = [now, after]
                if after is None:
                    row.cells.pop(col, None)
                else:
                    row.cells[col] = after
                changed[id] = row
                written.add(id)
        if cells:
            done["cells"] = cells
        if not changed:
            return
        encoded = self.encode([changed[id] for id in written])
        self.write(
            [
                {
                    "id": row.pk,
                    "height": row.height,
                    "look": grids.keyed(row.look, self.written) or "",
                    "hidden": row.hidden,
                }
                for row in changed.values()
            ],
            "height",
            "look",
            "hidden",
        )
        self.write([{"id": changed[id].pk, "cells": encoded[id]} for id in written], "cells")
        for row in changed.values():
            self.note(row)

    def lines_of_cols(self, patch: dict, done: dict) -> bool:
        cols = {col.id: col for col in self.table.cols}
        meta = False
        widths = {}
        for id, (before, after) in patch.get("widths", {}).items():
            col = cols.get(id)
            if col is None or (self.guard and col.width != before) or col.width == after:
                continue
            widths[id] = [col.width, after]
            col.width = after
        if widths:
            done["widths"] = widths
            meta = True
        for part in ("looks", "hidden"):
            for id, (before, after) in patch.get(part, {}).get(COLS, {}).items():
                if (col := cols.get(id)) is None:
                    continue
                now = col.look if part == "looks" else col.hidden
                if (self.guard and now != before) or now == after:
                    continue
                done.setdefault(part, {}).setdefault(COLS, {})[id] = [now, after]
                if part == "looks":
                    col.look = grids.look(after) if after is not None else None
                else:
                    col.hidden = after
                meta = True
        return meta


def _line(row: Row) -> dict:
    return (
        {"size": row.height, "cells": row.cells}
        | ({"look": row.look} if row.look is not None else {})
        | ({"hidden": True} if row.hidden else {})
    )


def _col_line(col: Col, key: str | None) -> dict:
    return (
        {"size": col.width}
        | ({"look": col.look} if col.look is not None else {})
        | ({"hidden": True} if col.hidden else {})
        | ({"kept": key} if key else {})
    )


def _copy(table: Table) -> Table:
    return Table(
        table.table,
        table.grid,
        table.tab,
        table.name,
        [Col(col.id, col.width, col.look, col.hidden) for col in table.cols],
        table.frozen,
        table.size,
        dict(table.heights),
        dict(table.looks),
        set(table.hidden),
        dict(table.merges),
    )


@transaction.atomic
def apply(document, table: Table | None, patch: dict, guard: bool = False) -> Done:
    """Applies the patch to the table, none where it makes one, and gives what it did. With a
    guard, as a patch is taken back, each part applies only where the table still has what the
    patch takes for its before: a cell somebody wrote since stays as they left it."""
    document = getattr(document, "pk", document)
    # `unshare` forgets what no row names under the same lock, so never a key named here.
    Node.objects.select_for_update().only("pk").get(pk=document)
    if "from" in patch.get("made", ()):
        return _copied(document, table, patch, guard)
    if "from" in patch.get("gone", ()):
        Grid.objects.filter(document=document, table=patch["table"]).delete()
        return Done(patch if table is not None else None, None)
    if "made" in patch or "gone" in patch:
        return _whole(document, table, patch, guard)
    if table is None:
        if guard:
            return Done(None, None)
        raise ValueError(f"no grid {patch['table']}")
    run = _Run(document, _copy(table), guard)
    outline = run.table
    done: dict = {"table": table.table}
    meta = False
    if "name" in patch:
        before, after = patch["name"]
        if (not guard or outline.name == before) and outline.name != after:
            done["name"] = [outline.name, after]
            outline.name = after
            meta = True
    frozen = outline.frozen
    if lines := patch.get(COLS):
        if found := run.cols(lines):
            done[COLS] = found
            meta = True
    edits = []
    for edit in patch.get(ROWS, {}).get("edits", []):
        kind = edit[0]
        if kind == "put":
            made = run.put(edit)
        elif kind == "out":
            made = run.out(edit)
        else:
            made = run.order(edit)
        if made is not None:
            edits.append(made)
    if edits:
        done[ROWS] = {"edits": edits}
    if "frozen" in patch:
        before, after = patch["frozen"]
        if after is not None and not stored.places_of(table.grid, [after]):
            run.refused(f"no row {after}")
        elif not guard or frozen == before:
            outline.frozen = after
    if outline.frozen != frozen:
        done["frozen"] = [frozen, outline.frozen]
        meta = True
    meta = run.lines_of_cols(patch, done) or meta
    run.lines(patch, done)
    run.share()
    grid = Grid.objects.get(pk=table.grid)
    grid.edited_at = timezone.now()
    fields = ["edited_at"]
    if meta:
        grid.name, grid.frozen = outline.name, outline.frozen or ""
        grid.cols = [
            {"id": col.id}
            | ({"width": col.width} if col.width is not None else {})
            | ({"look": grids.keyed(col.look, run.written)} if col.look is not None else {})
            | ({"hidden": True} if col.hidden else {})
            for col in outline.cols
        ]
        run.share()
        fields += ["name", "cols", "frozen"]
    if len(done) == 1:
        return Done(None, table)
    grid.save(update_fields=fields)
    return Done(done, outline, run.keys, run.restated, run.arrived, run.gone, run.beside, run.told)


def _whole(document, table: Table | None, patch: dict, guard: bool) -> Done:
    """A table made or taken away whole, by the grid read and stored whole."""
    from .table import tables_of

    laid = grids.of_document(document, [patch["table"]]).get(patch["table"]) if table else None
    applied = grids.apply(laid, patch, guard)
    keys = grids.store(document, applied)
    after = tables_of(document, [patch["table"]]).get(patch["table"])
    return Done(applied.patch, after, keys, told=None)


def _copied(document, table: Table | None, patch: dict, guard: bool) -> Done:
    """A table made as a copy of another of the document, by Postgres: its rows as they stand
    with their ids, so what its formulas name of their own table is the copy's. Each formula is
    the value it shows, written in the locale, where the patch gives one."""
    from .calculation import language, written
    from .table import tables_of

    if table is not None:
        if guard:
            return Done(None, table)
        raise ValueError(f"grid {patch['table']} exists")
    made = patch["made"]
    source = Grid.objects.filter(document=document, table=made["from"]).first()
    if source is None:
        if guard:
            return Done(None, None)
        raise ValueError(f"no grid {made['from']}")
    grid = Grid.objects.create(
        document_id=document,
        tab_id=made["tab"],
        table=patch["table"],
        name=made["name"],
        cols=source.cols,
        frozen=source.frozen,
    )
    if "values" not in made:
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO content_gridrow (grid_id, "row", position, height, look, hidden, '
                'cells, "values", shown) SELECT %s, "row", position, height, look, hidden, '
                'cells, "values", shown FROM content_gridrow WHERE grid_id = %s',
                [grid.pk, source.pk],
            )
            cursor.execute(
                "SELECT DISTINCT e.key, e.value->>'formula' FROM content_gridrow r, "
                "jsonb_each(r.cells) e WHERE r.grid_id = %s AND e.value ? 'formula'",
                [grid.pk],
            )
            keys: dict[str, set[str]] = {}
            for col, key in cursor.fetchall():
                keys.setdefault(col, set()).add(key)
    else:
        keys = {}
        tongue = language(made["values"])
        batch: list[GridRow] = []
        for row in GridRow.objects.filter(grid=source).order_by("position").iterator(READ):
            row.pk, row.grid = None, grid
            for col, cell in row.cells.items():
                if FORMULA in cell:
                    del cell[FORMULA]
                    cell[TEXT] = written(loaded(row.values.get(col)), tongue)
            batch.append(row)
            if len(batch) == READ:
                GridRow.objects.bulk_create(batch)
                batch = []
        GridRow.objects.bulk_create(batch)
    return Done(patch, tables_of(document, [patch["table"]]).get(patch["table"]), keys, told=None)


def _flipped(pair: list) -> list:
    return [pair[1], pair[0]]


def inverse(patch: dict) -> dict:
    """The patch that takes the one given back."""
    if "made" in patch or "gone" in patch or "edits" not in patch.get(ROWS, {"edits": []}):
        return grids.inverse(patch)
    back = grids.inverse({part: value for part, value in patch.items() if part != ROWS})
    edits = []
    for edit in reversed(patch.get(ROWS, {}).get("edits", [])):
        match edit:
            case ["put", _, _, dict() as kept]:
                edits.append(["out", dict(kept)])
            case ["put", _, _, lines]:
                edits.append(["out", {"rows": [id for id, _ in lines]}])
            case ["out", runs, key]:
                ordinal = 0
                for first, count, prev in runs:
                    edits.append(
                        ["put", first, prev, {"kept": key, "from": ordinal, "count": count}]
                    )
                    ordinal += count
            case ["order", first, _, key]:
                edits.append(["order", first, {"kept": key}])
    if edits:
        back[ROWS] = {"edits": edits}
    return back
