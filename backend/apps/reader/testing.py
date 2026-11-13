"""The reader of a pytest worker: its server in a thread of the worker, so that what a test
changes in its process before a file is read holds in the reading forked from it."""

import threading

import pytest

from . import serve


@pytest.fixture(scope="session")
def reader_server():
    server = serve.serve(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(autouse=True)
def reader(settings, reader_server):
    settings.READER_URL = reader_server


def pytest_configure(config):
    # The server forks from a thread of the test's process: the readings it forks use none of
    # the locks the other threads hold, the database's refused, and end by os._exit.
    config.addinivalue_line(
        "filterwarnings", "ignore:This process .* is multi-threaded, use of fork:DeprecationWarning"
    )
