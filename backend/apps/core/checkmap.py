"""The files each test runs, and in them the top-level functions and classes, for the gate
(scripts/check.sh, scripts/select.py): a full run notes them under PONISTRA_MAP, by pytest's tests
here and by the browser's tests in the server, which learns from a header which one runs, and the
tests that failed; a run over a change is given in PONISTRA_SELECT the tests it reaches."""

import json
import os
import sys
from pathlib import Path

import pytest
from asgiref.sync import iscoroutinefunction
from django.utils.decorators import sync_and_async_middleware

OUT = os.environ.get("PONISTRA_MAP")
SELECT = os.environ.get("PONISTRA_SELECT")
ROOT = f"{Path(__file__).resolve().parents[2]}/"
TOOL = 4

_test: str | None = None
_files: set[str] = set()
_tests: dict[str, list[str]] = {}
_failed: set[str] = set()


def _started(code, offset):
    if _test is not None and code.co_filename.startswith(ROOT):
        file = f"backend/{code.co_filename.removeprefix(ROOT)}"
        _files.add(file)
        if (top := code.co_qualname.split(".")[0]) != "<module>":
            _files.add(f"{file}#{top}")
    # Each function is noted once per test: switch() lets them all be seen again.
    return sys.monitoring.DISABLE


def trace() -> None:
    monitoring = sys.monitoring
    if monitoring.get_tool(TOOL) is None:
        monitoring.use_tool_id(TOOL, "ponistra-map")
        monitoring.register_callback(TOOL, monitoring.events.PY_START, _started)
        monitoring.set_events(TOOL, monitoring.events.PY_START)


def switch(test: str | None) -> tuple[str | None, list[str]]:
    """Notes what runs from now on under `test`, or under none; returns the test that ended and
    the files it ran."""
    global _test, _files
    ended, ran = _test, sorted(_files)
    _test, _files = test, set()
    sys.monitoring.restart_events()
    return ended, ran


def ran() -> list[str] | None:
    """What this process ran under its test, for a process forked from a test's to hand back."""
    return sorted(_files) if _test is not None else None


def noted(files: list[str]) -> None:
    """Notes what a process forked from this one ran under the current test."""
    if _test is not None:
        _files.update(files)


def pytest_configure(config):
    if OUT:
        trace()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    if not OUT:
        return (yield)
    switch(item.nodeid)
    try:
        return (yield)
    finally:
        _tests[item.nodeid] = switch(None)[1]


def pytest_collection_finish(session):
    if OUT and session.items:
        worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
        Path(OUT, f"pytest-{worker}.collected").write_text(
            "".join(f"{item.nodeid}\n" for item in session.items)
        )


def pytest_runtest_logreport(report):
    if OUT and report.failed:
        _failed.add(report.nodeid)


def pytest_sessionfinish(session):
    if not OUT:
        return
    if _tests:
        worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
        Path(OUT, f"pytest-{worker}.json").write_text(json.dumps(_tests))
    # The tests that failed are told by the process that hears every report, xdist's controller:
    # a worker that crashes tells nothing.
    if not hasattr(session.config, "workerinput"):
        Path(OUT, "pytest.failed").write_text("".join(f"{test}\n" for test in sorted(_failed)))
        Path(OUT, "pytest.status").write_text(f"{int(session.exitstatus)}\n")


def pytest_unconfigure(config):
    if sys.monitoring.get_tool(TOOL) is not None:
        sys.monitoring.set_events(TOOL, 0)
        sys.monitoring.free_tool_id(TOOL)


def pytest_collection_modifyitems(config, items):
    if not SELECT:
        return
    wanted = set(Path(SELECT).read_text().splitlines())

    def reached(item) -> bool:
        parts = item.nodeid.split("[")[0].split("::")
        return (
            item.nodeid in wanted
            or any("::".join(parts[:depth]) in wanted for depth in range(1, len(parts) + 1))
            or any(parts[0].startswith(folder) for folder in wanted if folder.endswith("/"))
        )

    kept = [item for item in items if reached(item)]
    config.hook.pytest_deselected(items=[item for item in items if not reached(item)])
    items[:] = kept


def _mark(request) -> None:
    test = request.headers.get("X-Ponistra-Test")
    if test is None:
        return
    ended, ran = switch(None if test == "-" else test)
    if ended is not None:
        with Path(OUT, "e2e-backend.jsonl").open("a") as out:
            out.write(json.dumps({"test": ended, "files": ran}) + "\n")


@sync_and_async_middleware
def marker(get_response):
    """Installed by the settings only in a full run of the gate."""
    trace()
    if iscoroutinefunction(get_response):

        async def middleware(request):
            _mark(request)
            return await get_response(request)

    else:

        def middleware(request):
            _mark(request)
            return get_response(request)

    return middleware
