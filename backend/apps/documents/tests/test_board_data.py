from unittest.mock import patch

import pytest
from django.test import Client

from apps.access.models import Grant, Role
from apps.documents import board_data, boards
from apps.documents.models import BoardEntry, Node
from apps.users.models import User

from .test_boards import PAGE, board

pytestmark = pytest.mark.django_db

JSON = "application/json"


def data_of(node: str, **asked) -> str:
    query = "&".join(f"{name}={value}" for name, value in asked.items())
    return f"/api/nodes/{node}/board/data?{query}"


def test_a_board_keeps_documents_by_collection_and_key(api, upload):
    made = board(api, upload)
    written = api.put(data_of(made, collection="koraci", key="a"), {"data": {"n": 1}}, JSON)
    assert written.status_code == 200
    assert written.json()["version"] == 1
    api.put(data_of(made, collection="koraci", key="b"), {"data": {"n": 2}}, JSON)
    api.put(data_of(made, collection="dnevnik", key="a"), {"data": {"t": "x"}}, JSON)

    assert api.get(data_of(made, collection="koraci", key="a")).json()["data"] == {"n": 1}
    listed = api.get(data_of(made, collection="koraci")).json()["entries"]
    assert [each["key"] for each in listed] == ["a", "b"]
    assert api.get(data_of(made)).json()["collections"] == [
        {"collection": "dnevnik", "count": 1},
        {"collection": "koraci", "count": 2},
    ]
    gone = api.get(data_of(made, collection="koraci", key="c"))
    assert (gone.status_code, gone.json()["error"]) == (404, "not_found")


def test_an_update_merges_at_any_depth_and_a_field_leaves_on_asking(api, upload):
    made = board(api, upload)
    place = data_of(made, collection="c", key="k")
    api.put(place, {"data": {"a": 1, "b": {"x": 1, "y": 2}, "c": 3}}, JSON)
    merged = api.patch(place, {"data": {"b": {"x": 9}, "c": {"__delete__": True}}}, JSON)
    assert merged.json()["data"] == {"a": 1, "b": {"x": 9, "y": 2}}
    assert merged.json()["version"] == 2
    assert api.put(place, {"data": {"z": 1}}, JSON).json()["data"] == {"z": 1}
    assert api.delete(place, {}, JSON).json()["version"] == 0
    assert api.get(place).status_code == 404


def test_a_write_refuses_a_document_that_moved_on(api, upload):
    made = board(api, upload)
    place = data_of(made, collection="c", key="k")
    assert api.put(place, {"data": {}, "if_version": 0}, JSON).status_code == 200
    late = api.put(place, {"data": {"a": 1}, "if_version": 0}, JSON)
    assert (late.status_code, late.json()["error"]) == (409, "version_conflict")
    assert api.get(place).json()["data"] == {}


def test_writes_land_all_or_none(api, upload):
    node = Node.objects.get(pk=board(api, upload))
    fine = {"op": "set", "collection": "c", "key": "a", "data": {}}
    with pytest.raises(board_data.Refused):
        board_data.written(node, [fine, {"op": "set", "collection": "c/d", "key": "b"}], api.user)
    assert not BoardEntry.objects.filter(node=node).exists()


def test_a_document_has_a_limit(api, upload):
    made = board(api, upload)
    big = api.put(
        data_of(made, collection="c", key="k"),
        {"data": {"a": "x" * (board_data.MOST_BYTES + 1)}},
        JSON,
    )
    assert (big.status_code, big.json()["error"]) == (413, "board_data_too_large")


def test_a_collection_that_is_full_takes_no_more_but_changes_what_it_holds(api, upload):
    node = Node.objects.get(pk=board(api, upload))
    fill = [{"op": "set", "collection": "c", "key": f"k{at}", "data": {}} for at in range(3)]
    board_data.written(node, fill, api.user)
    with patch.object(board_data, "MOST_ROWS", 3):
        with pytest.raises(board_data.Refused) as refused:
            board_data.written(
                node, [{"op": "set", "collection": "c", "key": "x", "data": {}}], api.user
            )
        assert refused.value.error == "board_data_too_large"
        board_data.written(
            node, [{"op": "set", "collection": "c", "key": "k0", "data": {"a": 1}}], api.user
        )
        board_data.written(
            node, [{"op": "set", "collection": "d", "key": "x", "data": {}}], api.user
        )
    assert BoardEntry.objects.filter(node=node, collection="c").count() == 3


def test_who_reads_the_board_reads_what_it_keeps_and_who_edits_it_writes(api, upload):
    made = board(api, upload)
    place = data_of(made, collection="c", key="k")
    api.put(place, {"data": {"a": 1}}, JSON)
    other = Client()
    colleague = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    other.force_login(colleague)
    assert other.get(place).status_code == 404

    grant = Grant.objects.create(node_id=made, user=colleague, role=Role.READ)
    assert other.get(place).json()["data"] == {"a": 1}
    assert b" data-reads" in other.get(f"/api/nodes/{made}/board").content
    assert other.put(place, {"data": {}}, JSON).status_code == 403
    assert other.delete(place, {}, JSON).status_code == 403

    grant.role = Role.EDIT
    grant.save()
    assert b" data-reads" not in other.get(f"/api/nodes/{made}/board").content
    assert other.put(place, {"data": {"a": 2}}, JSON).json()["version"] == 2
    assert BoardEntry.objects.get(node_id=made).updated_by == colleague


def test_only_a_board_keeps_anything(api, upload):
    sha256 = upload(b"obican tekst")["sha256"]
    from .test_views import create

    made = create(api, "file", "Tekst", blob=sha256, extension="txt")
    assert api.get(data_of(made)).status_code == 404


def test_a_board_page_may_load_only_its_own_runtime_beside_the_libraries(api, upload):
    made = board(api, upload, PAGE)
    policy = api.get(f"/api/nodes/{made}/board/page")["Content-Security-Policy"]
    assert f"http://testserver{boards.RUNTIME_PATH}" in policy
    assert "connect-src https://cdnjs.cloudflare.com" in policy
    assert "'self'" not in policy.split("frame-ancestors")[0]
    runtime = Client().get(boards.RUNTIME_PATH)
    assert runtime.status_code == 200
    assert runtime["Content-Type"].startswith("text/javascript")
    assert b"window.ponistra" in runtime.content


def test_the_version_of_a_board_only_reads_what_it_keeps(api, upload):
    made = board(api, upload)
    assert b" data-reads" not in api.get(f"/api/nodes/{made}/board").content
    api.patch(f"/api/nodes/{made}", {"title": "Nova"}, JSON)
    node = Node.objects.get(pk=made)
    boards.rewritten(node, PAGE.replace("12", "13"), api.user, "")
    version = node.file_versions.first()
    held = api.get(f"/api/nodes/{made}/board?version={version.pk}").content
    assert b" data-reads" in held
