"""A table's rows written into Postgres as its file is read, a batch at a time: the reader lays
them out (`Laying`), the backend writes each batch as it comes (`written`), so that a file of any
size takes the memory of one batch and the first rows can be read while the last are still in
it."""

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from django.db import connection, transaction

from apps.collab import server
from apps.content import grids
from apps.content.blocks import new_id
from apps.content.grids import STEP, Formula, Look
from apps.content.models import Grid, GridRow, Shared

from .reading import TooManyFormulas

# Excel's own width of a column none is given for, in characters.
DEFAULT_WIDTH = 9.140625
BATCH = 5_000
TOLD_EVERY = 3.0
COMPARED = 2_000
# A calculation holds each different formula of a document, some 3.4 kB, 170 MB at this many
# (measured 10.11.2026); cells one below the other holding the same one cost next to nothing.
MOST_FORMULAS = 50_000


class Ids(Sequence):
    """The ids of a sheet's rows or columns, each made from where it stands, so that none is
    kept and a formula read early can name a line that is written later."""

    def __init__(self, count: int = 0):
        self.prefix = new_id()
        self.count = count

    def __len__(self) -> int:
        return self.count

    def __getitem__(self, at: int) -> str:
        return f"{self.prefix}{at + 1:x}"

    def __iter__(self) -> Iterator[str]:
        return (self[at] for at in range(self.count))


class Standing(Mapping):
    """Where each of the ids stands, read off the id."""

    def __init__(self, ids: Ids):
        self.ids = ids

    def __contains__(self, id: object) -> bool:
        return isinstance(id, str) and id.startswith(self.ids.prefix)

    def __getitem__(self, id: str) -> int:
        if id not in self:
            raise KeyError(id)
        return int(id[len(self.ids.prefix) :], 16) - 1

    def __iter__(self) -> Iterator[str]:
        return iter(self.ids)

    def __len__(self) -> int:
        return len(self.ids)


@dataclass
class Line:
    number: int
    cells: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    shown: dict = field(default_factory=dict)
    height: float | None = None
    look: dict | None = None
    hidden: bool = False


def begin() -> None:
    """Makes the place of the values the file saved with its formulas until they are compared,
    on this connection's own disk, as there can be more of them than fit in memory."""
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS import_saved")
        cursor.execute(
            "CREATE TEMP TABLE import_saved "
            "(grid bigint, line int, row_id text, col_id text, value jsonb, address text)"
        )
        cursor.execute("CREATE INDEX ON import_saved (grid, line)")


def saved() -> Iterator[tuple[int, dict[str, list[tuple[str, object, str | None]]]]]:
    """By table's grid, a batch of rows at a time, the column, value and address of each
    formula's value the file saved."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT grid, max(line) FROM import_saved GROUP BY grid")
        for grid, last in cursor.fetchall():
            for low in range(0, last, COMPARED):
                cursor.execute(
                    "SELECT row_id, col_id, value::text, address FROM import_saved "
                    "WHERE grid = %s AND line > %s AND line <= %s",
                    [grid, low, low + COMPARED],
                )
                rows: dict[str, list[tuple[str, object, str | None]]] = {}
                for row, col, value, address in cursor.fetchall():
                    rows.setdefault(row, []).append((col, json.loads(value), address))
                if rows:
                    yield grid, rows


def bounded(document) -> None:
    """Refuses a document holding more different formulas than an import takes on."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM content_shared WHERE document_id = %s "
            "AND jsonb_typeof(value) = 'array'",
            [document.pk],
        )
        (count,) = cursor.fetchone()
    if count > MOST_FORMULAS:
        raise TooManyFormulas


def end() -> None:
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS import_saved")


class Laying:
    """The rows of one table on their way into Postgres, read in the reader: each batch sent as
    Postgres keeps it, its formulas and looks by key and those new to the table beside them, for
    the backend to write (`written`). `cols` is how many columns the table holds already."""

    def __init__(self, out, table: str, rows: Ids, cols: int):
        self.out = out
        self.table = table
        self.rows = rows
        self.standing = Standing(rows)
        self.cols = cols
        self.made: list[dict] = []
        self.next = rows.count + 1
        self.pending: list[Line] = []
        self.compared: list[list] = []
        self.found: dict[str, Formula | Look] = {}
        self.shared: set[str] = set()

    def add(self, line: Line) -> None:
        while self.next < line.number:
            self._put(Line(self.next))
        self._put(line)

    def _put(self, line: Line) -> None:
        self.next = line.number + 1
        self.pending.append(line)
        if len(self.pending) >= BATCH:
            self.flush()

    def col(self, at: int, line) -> None:
        """Has the table's columns reach the one given, each new one as `line` says."""
        while self.cols < at:
            self.cols += 1
            self.made.append(line(self.cols, self))

    def key_of(self, look: dict | None) -> str | None:
        return grids.keyed(look, self.found)

    def compare(self, number: int, col: str, value, address: str | None) -> None:
        self.compared.append([number, self.rows[number - 1], col, value, address])

    def flush(self, frozen: str | None = None) -> None:
        lines = []
        for line in self.pending:
            id = self.rows[line.number - 1]
            cells = grids.encoded(line.cells, id, self.standing, self.found)
            look = grids.keyed(line.look, self.found) or ""
            lines.append(
                [line.number, id, line.height, look, line.hidden, cells, line.values, line.shown]
            )
        fresh = {key: value for key, value in self.found.items() if key not in self.shared}
        self.out.send(
            {
                "rows": {
                    "table": self.table,
                    "lines": lines,
                    "shared": fresh,
                    "cols": self.made,
                    "compared": self.compared,
                    **({"frozen": frozen} if frozen is not None else {}),
                }
            }
        )
        self.shared |= fresh.keys()
        self.found.clear()
        if self.pending:
            self.rows.count = max(self.rows.count, self.pending[-1].number)
        self.pending, self.compared, self.made = [], [], []

    def finish(self, last: int, frozen: str = "") -> None:
        """Sends what is left and the empty rows up to the last row reached."""
        if self.next <= last:
            self.add(Line(last))
        self.flush(frozen)

    def merge(self, merges: list[tuple[str, str, str]]) -> None:
        """Merges cells of rows written: each by its row, its column and the slot it reaches."""
        for at in range(0, len(merges), COMPARED):
            self.out.send({"merge": {"table": self.table, "merges": merges[at : at + COMPARED]}})


class _Writer:
    """Writes into Postgres the rows a reader's Laying sends for one table."""

    def __init__(self, document, table: str):
        self.document = document
        self.grid = Grid.objects.get(document=document, table=table)
        self.cols = list(self.grid.cols)
        self.told = 0.0

    def rows(self, sent: dict) -> None:
        with transaction.atomic():
            if sent["lines"]:
                top = (
                    GridRow.objects.filter(grid=self.grid)
                    .order_by("-position")
                    .values_list("position", flat=True)
                    .first()
                    or 0
                )
                position = max(top, (sent["lines"][0][0] - 1) * STEP)
                made = []
                for _, id, height, look, hidden, cells, values, shown in sent["lines"]:
                    position += STEP
                    made.append(
                        GridRow(
                            grid=self.grid,
                            row=id,
                            position=position,
                            height=height,
                            look=look,
                            hidden=hidden,
                            cells=cells,
                            values=values,
                            shown=shown,
                        )
                    )
            shared = sent["shared"]
            if shared:
                Shared.objects.bulk_create(
                    [
                        Shared(document_id=self.document.pk, key=key, value=value)
                        for key, value in shared.items()
                    ],
                    ignore_conflicts=True,
                )
                if any(isinstance(value, Formula) for value in shared.values()):
                    bounded(self.document)
            if sent["lines"]:
                GridRow.objects.bulk_create(made, batch_size=1_000)
            changed = []
            if sent["cols"]:
                self.cols += sent["cols"]
                self.grid.cols = self.cols
                changed.append("cols")
            if sent.get("frozen"):
                self.grid.frozen = sent["frozen"]
                changed.append("frozen")
            if changed:
                Grid.objects.filter(pk=self.grid.pk).update(
                    **{name: getattr(self.grid, name) for name in changed}
                )
            if sent["compared"]:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO import_saved VALUES (%s, %s, %s, %s, %s::jsonb, %s)",
                        [
                            (self.grid.pk, number, row, col, json.dumps(value), address)
                            for number, row, col, value, address in sent["compared"]
                        ],
                    )
        if "frozen" not in sent and time.monotonic() - self.told >= TOLD_EVERY:
            server.grew(self.document.pk)
            self.told = time.monotonic()

    def merge(self, merges: list[list[str]]) -> None:
        by_row: dict[str, list[tuple[str, str]]] = {}
        for row, col, to in merges:
            by_row.setdefault(row, []).append((col, to))
        changed = list(GridRow.objects.filter(grid=self.grid, row__in=list(by_row)))
        for row in changed:
            for col, to in by_row[row.row]:
                row.cells.setdefault(col, {})[grids.TO] = to
        GridRow.objects.bulk_update(changed, ["cells"], batch_size=500)


def written(document, sent: Iterator[dict]) -> None:
    """Writes the rows the reader sends for the document's tables, each batch as it comes."""
    writers: dict[str, _Writer] = {}
    for found in sent:
        kind, value = next(iter(found.items()))
        if kind not in ("rows", "merge"):
            raise ValueError(f"the reader sent {kind!r} among a table's rows")
        writer = writers.get(value["table"])
        if writer is None:
            writer = writers[value["table"]] = _Writer(document, value["table"])
        if kind == "rows":
            writer.rows(value)
        else:
            writer.merge(value["merges"])
