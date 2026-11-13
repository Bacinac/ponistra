"""A CSV file as a tab of one table, its rows written as the file is read and each cell typed
as the document's locale reads what is typed into it."""

import csv
from collections.abc import Iterator
from functools import partial
from pathlib import Path

from apps.content import calculation, styles
from apps.content.blocks import Block, Grid, new_id
from apps.content.grids import FORMAT, TEXT
from apps.engine.parse import Error
from apps.engine.values import stored

from . import laying
from .laying import DEFAULT_WIDTH, Ids
from .reading import Imported, Tab, Unreadable

SAMPLE = 1 << 16
DELIMITERS = ";,\t|"
LONGEST_FIELD = 1 << 24


def read(path: Path, locale: str) -> Imported:
    encoding = _encoding(path)
    delimiter = _delimiter(path, encoding)
    rows, cols, table = Ids(), Ids(1), new_id()
    grid = Grid([], list(cols))
    attrs = {"widths": {cols[0]: DEFAULT_WIDTH}, "sized": True}
    return Imported(
        [Tab("", [Block("table", table, attrs, grid=grid), Block("paragraph")])],
        None,
        {},
        dict(styles.TEMPLATE[styles.THEME]),
        styles.TEMPLATE[styles.STYLES],
        {},
        [],
        {"fonts": [], "lost": {}, "accepted": 0, "functions": [], "cells": []},
        {},
        rest=partial(_written, path, encoding, delimiter, table, rows, cols, locale),
    )


def _encoding(path: Path) -> str:
    with path.open("rb") as file:
        head = file.read(SAMPLE)
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        # A sample can end inside a character; only an error before its last bytes counts.
        head.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        if error.start < len(head) - 4:
            return "cp1250"
    return "utf-8-sig"


def _delimiter(path: Path, encoding: str) -> str:
    """The delimiter that stands the same number of times, at least once, in most lines."""
    with path.open(encoding=encoding, errors="replace", newline="") as file:
        lines = [line for line in file.read(SAMPLE).splitlines()[:50] if line]
    best, most = ";", 0
    for each in DELIMITERS:
        counts = [line.count(each) for line in lines]
        steady = max(((counts.count(count), count) for count in set(counts) if count), default=None)
        if steady is not None and steady[0] > most:
            best, most = each, steady[0]
    return best


def _lines(path: Path, encoding: str, delimiter: str) -> Iterator[list[str]]:
    csv.field_size_limit(LONGEST_FIELD)
    with path.open(encoding=encoding, errors="replace", newline="") as file:
        try:
            yield from csv.reader(file, delimiter=delimiter)
        except csv.Error as error:
            raise Unreadable from error


def _written(
    path: Path,
    encoding: str,
    delimiter: str,
    table: str,
    rows: Ids,
    cols: Ids,
    locale: str,
    out,
) -> dict:
    laid = laying.Laying(out, table, rows, cols.count)
    language = calculation.language(locale)

    def column(at: int, _) -> dict:
        return {"id": cols[at - 1], "width": DEFAULT_WIDTH}

    number = 0
    for number, fields in enumerate(_lines(path, encoding, delimiter), 1):
        cols.count = max(cols.count, len(fields))
        laid.col(len(fields), column)
        line = laying.Line(number)
        for at, field in enumerate(fields):
            if not field:
                continue
            id = cols[at]
            text = "'" + field if field[0] in "'=" else field
            given = {TEXT: text}
            value = calculation.typed(text, language)
            format = calculation.implied(text, language)
            if format:
                given[FORMAT] = format
            line.cells[id] = given
            line.values[id] = stored(value)
            shown = calculation.shown(value, format or None, locale)
            if shown != text or format or isinstance(value, Error):
                line.shown[id] = shown
        laid.add(line)
    laid.finish(number)
    return {"written": [table]}
