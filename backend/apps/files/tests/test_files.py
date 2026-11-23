import pytest

from apps.access.tests.test_access import person
from apps.locations.tests.test_locations import added, post, put

pytestmark = pytest.mark.django_db


def test_a_bookmark_is_kept_for_its_user_alone_and_removed(api):
    given = {"source": "location:1b0f", "path": "Ponude/2026", "name": "Ponude"}
    made = post(api, "/api/files/bookmarks", given)
    assert made.status_code == 201
    assert api.get("/api/files/bookmarks").json() == {"bookmarks": [made.json()]}
    ana = person("ana@example.com")
    assert ana.get("/api/files/bookmarks").json() == {"bookmarks": []}
    assert ana.delete(f"/api/files/bookmarks/{made.json()['id']}").status_code == 404
    assert api.delete(f"/api/files/bookmarks/{made.json()['id']}").status_code == 204
    assert api.get("/api/files/bookmarks").json() == {"bookmarks": []}


@pytest.mark.parametrize(
    "changed, error",
    [
        ({"source": ""}, "invalid_source"),
        ({"name": " "}, "invalid_name"),
        ({"path": None}, "invalid_path"),
        ({"path": "a\0b"}, "invalid_path"),
    ],
)
def test_a_bookmark_is_checked_as_it_is_kept(api, changed, error):
    given = {"source": "ponistra:mine", "path": "", "name": "Moji"} | changed
    assert post(api, "/api/files/bookmarks", given).json() == {"error": error}


def test_a_user_keeps_so_many_bookmarks_at_most(api, monkeypatch):
    monkeypatch.setattr("apps.files.views.BOOKMARKS", 2)
    given = {"source": "ponistra:mine", "path": "", "name": "Moji"}
    for _ in range(2):
        assert post(api, "/api/files/bookmarks", given).status_code == 201
    assert post(api, "/api/files/bookmarks", given).json() == {"error": "too_many_bookmarks"}


def test_a_locations_folder_is_searched_sized_and_its_entries_described(api, spot):
    location = added(api, spot)
    files = f"/api/locations/{location['id']}"
    post(api, f"{files}/folder", {"path": "", "name": "Ponude"})
    put(api, location, "Ponude", "Čakovec.txt", b"prva")
    put(api, location, "", "cakovec-2.txt", b"druga!")

    found = api.get(f"{files}/search", {"path": "", "q": "CAKOVEC"}).json()
    assert sorted(each["path"] for each in found["entries"]) == [
        "Ponude/Čakovec.txt",
        "cakovec-2.txt",
    ]
    assert found["partial"] is False
    assert api.get(f"{files}/search", {"q": " "}).json() == {"error": "invalid_query"}
    assert api.get(f"{files}/size", {"path": ""}).json() == {
        "size": 10,
        "files": 2,
        "folders": 1,
        "partial": False,
    }

    stat = api.get(f"{files}/stat", {"path": "cakovec-2.txt"}).json()
    assert (stat["kind"], stat["size"], stat["path"]) == ("file", 6, "cakovec-2.txt")
    assert stat["mode"] & 0o777 and stat["owner"] == "sftp"
    changed = post(api, f"{files}/mode", {"path": "cakovec-2.txt", "mode": 0o600})
    assert changed.json()["mode"] == 0o600
    assert post(api, f"{files}/mode", {"path": "a", "mode": 0o10000}).json() == {
        "error": "invalid_mode"
    }
