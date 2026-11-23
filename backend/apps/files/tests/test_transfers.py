import hashlib
from datetime import UTC, datetime

import pytest

from apps.access.tests.test_access import person
from apps.documents.models import Node
from apps.documents.tests.test_views import create
from apps.files.transfer import KINDS
from apps.jobs.tests.handed import done, refused
from apps.locations.tests.test_locations import added, names, on_server, post, put

pytestmark = pytest.mark.django_db


def source(location: dict) -> str:
    return f"location:{location['id']}"


def transferred(client, origin: str, paths: list[str], to: str, path: str = "", **given) -> dict:
    return done(
        client, "transfer", **{"from": origin, "paths": paths, "to": to, "path": path} | given
    )


def read(spot: str, path: str) -> bytes:
    return on_server(lambda server: server.whole(path, 1 << 20), spot)


def test_files_and_folders_are_copied_into_ponistra_dated_as_on_the_server(api, spot):
    location = added(api, spot)
    post(api, f"/api/locations/{location['id']}/folder", {"path": "", "name": "Ponude"})
    put(api, location, "Ponude", "prva.txt", b"Prva ponuda")
    put(api, location, "", "bilješka.txt", b"Samo redak")

    answer = transferred(api, source(location), ["Ponude", "bilješka.txt"], "ponistra:mine")
    assert (answer["files"], answer["of_files"], answer["skipped"]) == (2, 2, 0)
    assert answer["bytes"] == answer["of_bytes"] == len(b"Prva ponuda") + len("Samo redak")
    top = {node.title: node for node in Node.objects.filter(parent=None, trashed_at=None)}
    assert set(top) == {"Ponude", "bilješka"}
    assert top["Ponude"].kind == Node.Kind.FOLDER
    inside = Node.objects.get(parent=top["Ponude"])
    assert inside.title == "prva"
    assert (datetime.now(UTC) - inside.updated_at).total_seconds() < 120
    assert names(api, location) == ["Ponude", "bilješka.txt"]


def test_a_copy_between_locations_asks_once_what_a_name_already_taken_becomes(api, spot):
    location = added(api, spot)
    files = f"/api/locations/{location['id']}"
    for each in ("A", "B"):
        post(api, f"{files}/folder", {"path": "", "name": each})
    put(api, location, "A", "plan.txt", b"novi")
    put(api, location, "A", "samo.txt", b"samo")
    put(api, location, "B", "plan.txt", b"stari")
    here = source(location)

    skipped = transferred(api, here, ["A/plan.txt", "A/samo.txt"], here, "B", conflict="skip")
    assert skipped["skipped"] == 1
    assert read(spot, "B/plan.txt") == b"stari"
    kept = transferred(api, here, ["A/plan.txt"], here, "B", conflict="keep")
    assert kept["skipped"] == 0
    assert names(api, location, "B") == ["plan (2).txt", "plan.txt", "samo.txt"]
    transferred(api, here, ["A/plan.txt"], here, "B", conflict="replace")
    assert read(spot, "B/plan.txt") == b"novi"
    assert names(api, location, "A") == ["plan.txt", "samo.txt"]


def test_a_folder_replaced_merges_into_the_one_of_its_name(api, spot):
    location = added(api, spot)
    files = f"/api/locations/{location['id']}"
    for path, name in (("", "A"), ("", "B"), ("A", "Ponude"), ("B", "Ponude")):
        post(api, f"{files}/folder", {"path": path, "name": name})
    put(api, location, "A/Ponude", "nova.txt", b"nova")
    put(api, location, "B/Ponude", "stara.txt", b"stara")
    here = source(location)

    transferred(api, here, ["A/Ponude"], here, "B", conflict="replace")
    assert names(api, location, "B/Ponude") == ["nova.txt", "stara.txt"]


def test_a_move_within_a_location_renames_and_never_into_itself(api, spot):
    location = added(api, spot)
    files = f"/api/locations/{location['id']}"
    for path, name in (("", "A"), ("", "B"), ("A", "C")):
        post(api, f"{files}/folder", {"path": path, "name": name})
    put(api, location, "", "plan.txt", b"plan")
    here = source(location)

    moved = transferred(api, here, ["plan.txt", "A"], here, "B", move=True)
    assert (moved["files"], moved["of_files"]) == (2, 2)
    assert names(api, location) == ["B"]
    assert names(api, location, "B") == ["A", "plan.txt"]
    assert refused(
        api,
        "transfer",
        **{"from": here, "paths": ["B/A"], "to": here, "path": "B/A/C"} | {"move": True},
    ) == (400, "invalid_path")


def test_a_move_out_of_ponistra_trashes_what_it_wrote_and_a_document_goes_as_office(api, spot):
    location = added(api, spot)
    folder = create(api, "folder", "Ugovori")
    document = create(api, "document", "Ugovor", parent=folder)
    put_into = transferred(api, "ponistra:mine", [folder], source(location), move=True)
    assert put_into["files"] == 1
    assert names(api, location, "Ugovori") == ["Ugovor.docx"]
    assert read(spot, "Ugovori/Ugovor.docx")[:2] == b"PK"
    assert Node.objects.get(pk=folder).trashed_at is not None
    assert Node.objects.filter(pk=document).exists()


def test_a_name_ponistra_already_holds_is_matched_by_its_title(api, spot):
    location = added(api, spot)
    put(api, location, "", "Ugovor.txt", b"s posluzitelja")
    create(api, "document", "ugovor")

    skipped = transferred(api, source(location), ["Ugovor.txt"], "ponistra:mine", conflict="skip")
    assert skipped["skipped"] == 1
    transferred(api, source(location), ["Ugovor.txt"], "ponistra:mine", conflict="keep")
    titles = sorted(
        Node.objects.filter(parent=None, trashed_at=None).values_list("title", flat=True)
    )
    assert titles == ["Ugovor (2)", "ugovor"]


@pytest.mark.parametrize(
    "given, error",
    [
        ({"from": "ponistra:mine", "paths": ["Ponude"]}, "invalid_id"),
        ({"to": "ponistra:company"}, "invalid_folder"),
        ({"to": "elsewhere:x"}, "invalid_source"),
        ({"paths": []}, "invalid_paths"),
        ({"paths": ["../etc"]}, "invalid_path"),
        ({"conflict": "merge"}, "invalid_conflict"),
        ({"move": "yes"}, "invalid_move"),
    ],
)
def test_a_transfer_is_checked_as_it_is_handed_over(api, spot, given, error):
    location = added(api, spot)
    asked = {"from": source(location), "paths": ["a.txt"], "to": "ponistra:mine", "path": ""}
    assert refused(api, "transfer", **(asked | given)) == (400, error)


def test_a_colleague_without_the_location_transfers_nothing_from_it(api, spot):
    location = added(api, spot)
    asked = {"from": source(location), "paths": ["a.txt"], "to": "ponistra:mine"}
    assert refused(person("ana@example.com"), "transfer", **asked)[0] == 404


def test_the_transfers_of_the_user_are_listed_the_latest_first(api, spot):
    location = added(api, spot)
    put(api, location, "", "a.txt", b"a")
    transferred(api, source(location), ["a.txt"], "ponistra:mine")
    transferred(api, source(location), ["a.txt"], "ponistra:mine", conflict="keep", move=True)

    listed = api.get("/api/files/transfers").json()["transfers"]
    assert [(each["move"], each["paths"], each["state"]) for each in listed] == [
        (True, 1, "done"),
        (False, 1, "done"),
    ]
    assert listed[0]["from_name"] == location["name"]
    assert listed[0]["to"] == "ponistra:mine"
    assert listed[0]["answer"]["files"] == 1


def test_a_files_checksum_is_summed_as_the_server_sends_it(api, spot):
    location = added(api, spot)
    put(api, location, "", "a.txt", b"zbroj")
    asked = {"source": source(location), "path": "a.txt"}
    assert done(api, "checksum", **asked) == {
        "algorithm": "sha256",
        "digest": hashlib.sha256(b"zbroj").hexdigest(),
    }
    assert (
        done(api, "checksum", **asked, algorithm="md5")["digest"]
        == hashlib.md5(b"zbroj", usedforsecurity=False).hexdigest()
    )
    assert refused(api, "checksum", **asked, algorithm="crc") == (400, "invalid_algorithm")
    assert refused(api, "checksum", source="ponistra:mine", path="a") == (400, "invalid_source")


def test_transfers_save_what_they_wrote_and_checksums_end_at_once():
    assert KINDS["transfer"].saves
    assert not KINDS["checksum"].saves


def titles(parent) -> list[str]:
    return sorted(
        Node.objects.filter(parent=parent, trashed_at=None).values_list("title", flat=True)
    )


def test_a_folder_is_copied_within_ponistra_each_node_made_again(api):
    ponude = create(api, "folder", "Ponude")
    document = create(api, "document", "Ponuda", parent=ponude)
    create(api, "link", "Ponistra", parent=ponude, href="https://ponistra.example.com")
    arhiva = create(api, "folder", "Arhiva")

    answer = transferred(api, "ponistra:mine", [ponude], "ponistra:mine", arhiva)
    assert (answer["files"], answer["of_files"]) == (2, 2)
    copy = Node.objects.get(parent=arhiva, trashed_at=None)
    assert copy.title == "Ponude" and copy.pk != ponude
    assert titles(copy) == ["Ponistra", "Ponuda"]
    made = Node.objects.get(parent=copy, kind=Node.Kind.DOCUMENT)
    assert made.pk != document and made.created_by == api.user
    assert Node.objects.get(parent=copy, kind=Node.Kind.LINK).href == "https://ponistra.example.com"
    assert titles(ponude) == ["Ponistra", "Ponuda"]

    transferred(api, "ponistra:mine", [ponude], "ponistra:mine", arhiva, conflict="keep")
    assert titles(arhiva) == ["Ponude", "Ponude (2)"]
    assert refused(
        api,
        "transfer",
        **{"from": "ponistra:mine", "paths": [arhiva], "to": "ponistra:mine"}
        | {"path": f"{arhiva}/{copy.pk}"},
    ) == (400, "cycle")


def test_a_move_within_ponistra_is_left_to_documents(api):
    ugovor = create(api, "document", "Ugovor")
    arhiva = create(api, "folder", "Arhiva")
    asked = {"from": "ponistra:mine", "paths": [ugovor], "to": "ponistra:mine", "path": arhiva}
    assert refused(api, "transfer", **asked, move=True) == (400, "invalid_move")
