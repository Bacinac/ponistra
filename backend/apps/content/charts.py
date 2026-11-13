"""What a chart shows, read out of the values its table is calculated to (f3-5).

A chart is a block of the tab's text over a range of one of its tables, by the ids of the
range's first and last row and column, as a formula's range is kept. The room that computes
the tables writes what each chart shows under the tab's `charts`, by the chart's id: the
series' names, the categories, and each value as a number, where the cell holds one, and as
the cell shows it. The browser only draws it."""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from pycrdt import Doc, Map, XmlElement, XmlFragment

from . import blocks
from .grids import FORMAT, TEXT
from .models import Grid, GridRow

CHARTS = "charts"
TAG = "chart"
MISSING = {"missing": True}
FAILED = {"failed": True}
NUMERIC = ("number", "date", "empty")
# A number format's literal text, escaped characters and bracketed parts (colours, locales,
# conditions) say nothing about whether it writes a date.
LITERAL = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]')
DATED = re.compile(r"[dmyhs]", re.IGNORECASE)


@dataclass(frozen=True)
class Chart:
    """Where a chart's values are, read out of its attributes: its table, the ids of the
    range's first and last row and column, which way its series run, and whether the
    range's first line names the series and gives the categories (None: decided by what
    the cells hold)."""

    table: str
    top: str
    left: str
    bottom: str
    right: str
    by: str
    scatter: bool
    names: bool | None
    labels: bool | None


def chart_of(attrs: dict) -> Chart | None:
    range = attrs.get("range")
    if not isinstance(range, dict):
        return None
    start = range.get("from")
    end = range.get("to", start)
    if not isinstance(start, dict) or not isinstance(end, dict):
        return None
    ids = (range.get("table"), start.get("row"), start.get("col"), end.get("row"), end.get("col"))
    if not all(isinstance(id, str) for id in ids):
        return None
    table, top, left, bottom, right = ids
    names, labels = attrs.get("names"), attrs.get("labels")
    return Chart(
        table,
        top,
        left,
        bottom,
        right,
        "rows" if attrs.get("by") == "rows" else "cols",
        attrs.get("kind") == "scatter",
        names if isinstance(names, bool) else None,
        labels if isinstance(labels, bool) else None,
    )


def charts_in(body: XmlFragment) -> dict[str, Chart | None]:
    """The charts of the tab's text by id, each where its values are, None where its
    attributes say nowhere."""
    found = {}
    for element in body.children:
        if isinstance(element, XmlElement) and element.tag == TAG:
            attrs = dict(element.attributes)
            if isinstance(attrs.get("id"), str):
                found[attrs["id"]] = chart_of(attrs)
    return found


def charts_of(doc: Doc) -> Map:
    return doc.get(CHARTS, type=Map)


@dataclass(frozen=True)
class Point:
    number: float | None
    text: str
    kind: str


def dated(format: str) -> bool:
    return bool(DATED.search(LITERAL.sub("", format)))


def drawn(chart: Chart, rows: list[str], cols: list[str], read) -> dict:
    """What the chart shows of a computed sheet whose rows and columns are those given,
    each cell read by `read(row, col)`, both counted from 0."""
    places = {id: index for index, id in enumerate(rows)}
    columns = {id: index for index, id in enumerate(cols)}
    ends = (places.get(chart.top), columns.get(chart.left))
    ends += (places.get(chart.bottom), columns.get(chart.right))
    if None in ends:
        return MISSING
    top, left, bottom, right = ends
    top, bottom = sorted((top, bottom))
    left, right = sorted((left, right))
    grid = [[read(y, x) for x in range(left, right + 1)] for y in range(top, bottom + 1)]
    if chart.by == "rows":
        grid = [list(line) for line in zip(*grid, strict=True)]
    # Each column of the grid is now a series, its first row their names and its first
    # column the categories.
    height, width = len(grid), len(grid[0])
    corner = grid[0][0].kind == "empty"
    names, labels = chart.names, chart.labels
    if labels is None:
        below = [line[0] for line in grid[1:]] or [grid[0][0]]
        labels = width > 1 and (
            chart.scatter
            or (corner and height > 1)
            or any(point.kind in ("text", "date") for point in below)
        )
    if names is None:
        after = grid[0][1:] if width > 1 else grid[0][:1]
        names = height > 1 and (
            (corner and width > 1) or any(point.kind == "text" for point in after)
        )
    names = names and height > 1
    labels = labels and width > 1
    data = grid[1:] if names else grid
    series = [
        {
            "name": grid[0][x].text if names else None,
            "values": [line[x].number for line in data],
            "texts": [line[x].text for line in data],
        }
        for x in range(1 if labels else 0, width)
    ]
    shown = {"series": series, "labels": [line[0].text for line in data] if labels else None}
    # As in Excel, x values that are not all numbers number the points 1, 2, 3 instead.
    if chart.scatter and labels and all(line[0].kind in NUMERIC for line in data):
        shown["x"] = [line[0].number for line in data]
    return shown


def read(
    document, chart: Chart | None, standing: Collection[str], texts: Mapping[str, Mapping[str, str]]
) -> dict:
    """What the chart shows of its table as Postgres holds what its cells are calculated to,
    given the tables standing in the document's text and by table the text of the cells that
    have a node of their own."""
    if chart is None or chart.table not in standing:
        return MISSING
    grid = Grid.objects.filter(document=document, table=chart.table).values_list("pk", "cols")
    if not grid:
        return MISSING
    pk, cols = grid[0]
    ends = GridRow.objects.filter(grid=pk, row__in=[chart.top, chart.bottom])
    positions = list(ends.values_list("position", flat=True))
    if len(positions) < len({chart.top, chart.bottom}):
        return MISSING
    found = list(
        GridRow.objects.filter(grid=pk, position__range=(min(positions), max(positions)))
        .order_by("position")
        .values_list("row", "cells", "values", "shown")
    )
    ids = [col["id"] for col in cols]
    own = texts.get(chart.table, {})

    def point(y: int, x: int) -> Point:
        row, cells, values, shown = found[y]
        col = ids[x]
        cell = cells.get(col) or {}
        value = values.get(col)
        text = shown.get(col, own.get(blocks.key_of(row, col), cell.get(TEXT, "")))
        match value:
            case None:
                return Point(None, "", "empty")
            case bool() | dict():
                return Point(None, text, "other")
            case int() | float():
                return Point(
                    float(value), text, "date" if dated(cell.get(FORMAT) or "") else "number"
                )
        return Point(None, text, "text")

    return drawn(chart, [row for row, *_ in found], ids, point)


def store(doc: Doc, shown: dict[str, dict]) -> None:
    """Writes what each chart given shows where it changed, and takes away what charts no
    longer in the text showed."""
    held = charts_of(doc)
    now = held.to_py() or {}
    present = set(charts_in(blocks.body_of(doc)))
    changed = {id: each for id, each in shown.items() if id in present and now.get(id) != each}
    gone = now.keys() - present
    if not changed and not gone:
        return
    with doc.transaction():
        for id, each in changed.items():
            held[id] = each
        for id in gone:
            del held[id]
