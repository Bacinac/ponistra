"""The workbooks Excel saved, held one language at a time: a module that holds the engine to them
reads what it needs for a language and lets it go before the next language and once its tests are
done. A worker of the suite is one process, which would otherwise keep both languages of every
module at once, more than the memory a check has. Each language is a group of its own, so that one
worker reads it for every module and the languages spread over the workers.

A push runs them in the languages named in PONISTRA_LANGUAGES (scripts/select.py), the night in
every one."""

import os
from pathlib import Path
from random import Random

import pytest

from apps.engine.book import Cells
from apps.engine.tests.cases import PATHS
from apps.engine.tests.saved import LANGUAGES, SAVED_ON, read, saved_at

CHOSEN = set(filter(None, os.environ.get("PONISTRA_LANGUAGES", "").split(",")))
HERE = Path(__file__).parent


def pytest_collection_modifyitems(config, items):
    if not CHOSEN:
        return

    def other(item) -> bool:
        params = getattr(getattr(item, "callspec", None), "params", {})
        return item.path.is_relative_to(HERE) and any(
            params.get(name) in LANGUAGES and params[name] not in CHOSEN
            for name in ("code", "language")
        )

    left = [item for item in items if other(item)]
    if left:
        config.hook.pytest_deselected(items=left)
        items[:] = [item for item in items if not other(item)]


@pytest.fixture(
    scope="module",
    params=[pytest.param(code, marks=pytest.mark.xdist_group(code)) for code in LANGUAGES],
)
def code(request) -> str:
    """The language Excel saved the workbooks in."""
    return request.param


@pytest.fixture(scope="module")
def etalon(code) -> dict[str, dict]:
    """The sheets of the cases Excel saved."""
    return read(PATHS[code])


@pytest.fixture(scope="module")
def book(code, etalon) -> Cells:
    """The engine's book of the cases Excel saved."""
    cells = Cells(code, saved_at(PATHS[code]), Random(0), SAVED_ON)
    for title, sheet in etalon.items():
        for (row, col), value in sheet["constants"].items():
            cells.put(title, row, col, value)
        for (row, col), text in sheet["formulas"].items():
            cells.write(title, row, col, text)
        for row in sheet["hidden"]:
            cells.hide(title, row)
    return cells
