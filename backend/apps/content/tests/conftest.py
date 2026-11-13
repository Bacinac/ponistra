import pytest

from .helpers import Room

# The modules whose rooms run twice: their grids whole in memory, as a document being written
# or imported holds them, and in Postgres, as a book does.
ROOMS = {
    "test_beginning",
    "test_compute",
    "test_elements",
    "test_fill",
    "test_finding",
    "test_measures",
    "test_names",
    "test_operations",
    "test_proposals",
    "test_sort",
    "test_values",
}


def pytest_generate_tests(metafunc):
    if metafunc.module.__name__.rpartition(".")[2] in ROOMS:
        metafunc.parametrize("rooms", ["memory", "stored"], indirect=True)


@pytest.fixture(autouse=True)
def rooms(request, monkeypatch):
    if getattr(request, "param", "memory") == "stored":
        request.getfixturevalue("db")
        monkeypatch.setattr(Room, "stored", True)
