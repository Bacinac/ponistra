"""A version's grids read by windows (D22, E3): what a browser lays a table out by, from what the
version noted when it was taken, and the rows it shows, from the pieces holding them. A version
never changes, so what is read to open one is kept for the next window."""

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Iterator, Mapping
from functools import lru_cache
from itertools import accumulate

from pycrdt import Doc

from apps.collab.books import outline, shown
from apps.content import grids, placing
from apps.content import rows as stored
from apps.content.grids import Col, Look, Row, decoded, line_parts, shared_of
from apps.content.sheets import Places
from apps.content.table import Table

from .history import lines_of
from .models import Piece, Version, VersionGrid


class KeptTable:
    """A grid of a version, read by place: `place` counts all its rows, `shown` those not
    hidden."""

    def __init__(self, part: VersionGrid, document_id, shared: Mapping, sizes: Mapping):
        self.document_id = document_id
        self.shared = shared
        self.table = part.table
        self.tab = None if part.tab is None else str(part.tab)
        self.name = part.name
        self.frozen = part.frozen or None
        self.size = part.size
        self.outlined = part.outline
        self.at: dict[str, int] = part.at
        self.pieces: list[str] = part.pieces
        self.cols = [self._col(line) for line in part.cols]
        self.hidden_at = sorted(self.at[id] for id in part.outline["hidden"])
        self.hidden = set(self.hidden_at)
        self.starts = [0, *accumulate(sizes[sha256][0] for sha256 in self.pieces)]
        self.starts_shown = [0, *accumulate(sizes[sha256][1] for sha256 in self.pieces)]

    def _col(self, line: list) -> Col:
        id, width, *rest = line
        key = rest[0] if rest else None
        return Col(id, width, self.shared[key] if key else None, len(rest) > 1 and rest[1] is True)

    def col_ids(self) -> list[str]:
        return [col.id for col in self.cols]

    def place(self, id: str) -> int | None:
        return self.at.get(id)

    def places(self, ids: Iterable[str]) -> dict[str, int]:
        return {id: self.at[id] for id in ids if id in self.at}

    @property
    def shown_size(self) -> int:
        return self.size - len(self.hidden_at)

    def shown_place(self, place: int) -> int:
        return place - bisect_left(self.hidden_at, place)

    def told(self, looks: dict) -> dict:
        """The table without its rows, as a browser lays it out."""
        looked: dict[str, Look] = {
            id: self.shared[key] for id, key in self.outlined["looks"].items()
        }
        table = Table(
            self.table,
            0,
            self.tab,
            self.name,
            self.cols,
            self.frozen,
            self.shown_size,
            dict(self.outlined["heights"]),
            looked,
            set(),
            dict(self.outlined["merges"]),
        )
        seen = {id: place for id, place in self.at.items() if place not in self.hidden}
        at = {id: self.shown_place(place) for id, place in seen.items()}
        found = outline(table, looks, at=at)
        if self.hidden_at:
            found["numbers"] = seen
        return found

    def _lines(self, first: int, last: int) -> Iterator[tuple[int, int, list]]:
        """The rows from the shown place `first` to `last`, each with its shown place, its own
        place and as the version keeps it."""
        first, last = max(first, 0), min(last, self.shown_size - 1)
        if last < first:
            return
        low = bisect_right(self.starts_shown, first) - 1
        high = bisect_right(self.starts_shown, last)
        place, at = self.starts[low], self.starts_shown[low]
        for line in lines_of(self.document_id, self.pieces[low:high]):
            hidden = line_parts(line)[4]
            if not hidden:
                if first <= at <= last:
                    yield at, place, line
                at += 1
            place += 1

    def _ids_at(self, places: set[int]) -> dict[int, str]:
        """The ids of the rows at their own places given, reading only the pieces holding them."""
        found: dict[int, str] = {}
        wanted = sorted(place for place in places if 0 <= place < self.size)
        seen = {bisect_right(self.starts, place) - 1 for place in wanted}
        for index in sorted(seen):
            place = self.starts[index]
            for line in lines_of(self.document_id, [self.pieces[index]]):
                if place in places:
                    found[place] = line[0]
                place += 1
        return found

    def rows(self, book: KeptBook, spans: Iterable[tuple[int, int]], looks: dict) -> dict:
        """The rows of the spans of shown places, as a browser holds them."""
        read = [each for first, last in spans for each in self._lines(first, last)]
        known: dict[int, str] = {place: line[0] for _, place, line in read}
        reached = set()
        parts = []
        for at, place, line in read:
            id, height, cells, look, hidden, figures = line_parts(line)
            parts.append((at, place, id, height, cells, figures))
            reached |= {
                place + distance for distance in stored._distances(cells, self.shared) if distance
            }
        known |= self._ids_at(reached - known.keys())
        reach = stored.Reach(self.size, known)
        decoded_rows = [
            (at, place, id, height, decoded(cells, self.shared, id, place, reach), figures)
            for at, place, id, height, cells, figures in parts
        ]
        places = Places(book)
        places.of(self.table)[0].found.update({id: place + 1 for place, id in known.items()})
        places.learn((self.table, cell) for *_, cells, _ in decoded_rows for cell in cells.values())
        nodes = book.placing.get(self.table)
        sent: dict[str, dict] = {}
        standing: dict[str, int] = {}
        numbers: dict[str, int] = {}
        for at, place, id, height, cells, figures in decoded_rows:
            standing[id], numbers[id] = at, place
            row = Row(
                id,
                height,
                cells,
                figures.get("values", {}),
                shown=figures.get("shown", {}),
            )
            sent[id] = {
                "cells": {
                    col: shown(cell, places, self.table, id, col, looks)
                    for col, cell in cells.items()
                },
                "values": grids.told(row, nodes),
            }
        found = {"table": self.table, "at": standing, "rows": sent}
        if self.hidden_at:
            found["numbers"] = numbers
        return found

    def standing(self, places: Iterable[int], ids: Iterable[str], numbers: Iterable[int]) -> dict:
        """The ids of the rows at the shown places, the places of the ids, -1 for one gone, and
        where the rows of the numbers stand among those shown, -1 for one hidden or past the
        last."""
        asked = sorted(set(places))
        at_place = {at: line[0] for each in asked for at, _, line in self._lines(each, each)}
        wanted = set(ids)
        found = {id: self.shown_place(self.at[id]) for id in wanted if id in self.at}
        if missing := wanted - found.keys():
            place = 0
            for line in lines_of(self.document_id, self.pieces):
                if line[0] in missing:
                    found[line[0]] = -1 if place in self.hidden else self.shown_place(place)
                    missing.discard(line[0])
                    if not missing:
                        break
                place += 1
        numbered = {
            number: (
                -1
                if number in self.hidden or not 0 <= number < self.size
                else self.shown_place(number)
            )
            for number in numbers
        }
        return {"places": at_place, "rows": found, "numbered": numbered}


class KeptBook:
    """A version's grids as `Places` reads a document's."""

    def __init__(self, version: Version):
        placings = {}
        for part in version.tabs.select_related("state"):
            doc = Doc()
            doc.apply_update(bytes(part.state.data))
            placings[str(part.tab)] = placing.of(doc)
        self.placing = placing.nodes_of(placings)
        self.shared = shared_of(version.shared)
        parts = list(version.grids.all())
        wanted = {sha256 for part in parts for sha256 in part.pieces}
        sizes = {
            sha256: (size, shown)
            for sha256, size, shown in Piece.objects.filter(
                document=version.document_id, sha256__in=wanted
            ).values_list("sha256", "size", "shown")
        }
        self.found = {
            part.table: KeptTable(part, version.document_id, self.shared, sizes) for part in parts
        }

    def stands(self, table: str) -> bool:
        return table in self.placing

    def peek(self, table: str) -> KeptTable | None:
        return self.found.get(table)

    def tables(self) -> Iterator[tuple[str, KeptTable]]:
        yield from self.found.items()

    def of(self, tab: str | None) -> list[KeptTable]:
        return [table for table in self.found.values() if table.tab == tab]


@lru_cache(maxsize=8)
def _opened(pk) -> KeptBook:
    return KeptBook(Version.objects.get(pk=pk))


def opened(version: Version) -> KeptBook:
    return _opened(version.pk)
