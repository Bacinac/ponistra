"""A document's first table as a CSV file, what each cell shows, its rows read from Postgres a
batch at a time."""

import csv
import io
import tempfile
from typing import IO

from apps.content import placing
from apps.content.grids import TEXT
from apps.content.models import Grid, GridRow
from apps.engine import formats

from .xlsx import Empty

BATCH = 2_000
BOM = "﻿"


def _shown(row: GridRow, col: str, nodes: dict[str, str]) -> str:
    if col in row.shown:
        return row.shown[col]
    text = nodes.get(f"{row.row}:{col}") or (row.cells.get(col) or {}).get(TEXT) or ""
    return text[1:] if text.startswith("'") else text


def table(document) -> IO[bytes]:
    grid = (
        Grid.objects.filter(document=document, tab__isnull=False)
        .order_by("tab__position", "pk")
        .first()
    )
    if grid is None:
        raise Empty
    nodes = placing.nodes_of(placing.of_document(document)).get(grid.table, {})
    cols = [col["id"] for col in grid.cols]
    mark, _ = formats.marks(document.locale)
    out = tempfile.TemporaryFile()
    text = io.TextIOWrapper(out, encoding="utf-8", newline="", write_through=True)
    text.write(BOM)
    writer = csv.writer(text, delimiter=";" if mark == "," else ",")
    rows = GridRow.objects.filter(grid=grid).order_by("position")
    for row in rows.iterator(chunk_size=BATCH):
        writer.writerow([_shown(row, col, nodes) for col in cols])
    text.detach()
    out.seek(0)
    return out
