import pytest

from apps.content import names
from apps.documents.models import Node

RATE = {"table": "t1", "from": {"row": "r1", "col": "a"}}


def test_a_patch_of_names_goes_and_its_inverse_takes_it_back():
    before = {"n1": names.entry("Tečaj", [RATE]), "n2": names.entry("Porez", ["0,25"], "t1")}
    after = {"n1": names.entry("Tečaj", ["7,5"]), "n3": names.entry("Rok", ["30"])}
    patch = names.diff(before, after)
    assert patch == {
        "names": {
            "n1": [before["n1"], after["n1"]],
            "n2": [before["n2"], None],
            "n3": [None, after["n3"]],
        }
    }
    assert names.diff(before, dict(before)) is None
    now, done = names.apply(before, patch)
    assert (now, done) == (after, patch)
    assert names.apply(now, names.inverse(patch))[0] == before
    assert names.apply(now, patch) == (now, None)


def test_a_patch_taken_back_with_a_guard_leaves_a_name_changed_since():
    before = {"n1": names.entry("Tečaj", ["7,5"]), "n2": names.entry("Rok", ["30"])}
    after = {"n1": names.entry("Tečaj", ["7,6"]), "n2": names.entry("Rok", ["45"])}
    patch = names.diff(before, after)
    since = {**after, "n2": names.entry("Rok", ["60"])}
    now, done = names.apply(since, names.inverse(patch), guard=True)
    assert now == {"n1": before["n1"], "n2": since["n2"]}
    assert done == {"names": {"n1": [after["n1"], before["n1"]]}}


@pytest.mark.django_db
def test_names_are_stored_as_patched_and_read_back_in_the_order_made():
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Cijene")
    other = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Plaće")
    held = {"n1": names.entry("Tečaj", [RATE]), "n2": names.entry("Porez", ["0,25"], "t1")}
    names.put(document, held)
    names.put(other, {"n1": names.entry("Bruto", ["1000"])})
    assert names.of_document(document) == held
    after = {"n1": names.entry("Tečaj", ["7,5"]), "n3": names.entry("Rok", ["30"], "t2")}
    names.store(document.pk, names.diff(held, after))
    assert names.of_document(document) == after
    assert names.of_document(other) == {"n1": names.entry("Bruto", ["1000"])}


def test_names_brought_take_new_ids_and_one_the_document_has_goes_to_the_tables_brought():
    held = {"n1": names.entry("Tečaj", ["7,5"]), "n2": names.entry("Rok", ["30"], "t9")}
    brought = {
        "a": names.entry("TEČAJ", ["7,6"]),
        "b": names.entry("tečaj", ["7,7"], "t2"),
        "c": names.entry("Rok", ["45"]),
        "d": names.entry("Porez", ["0,25"], "t1"),
    }
    found = names.joined(held, brought, ["t1", "t2"])
    assert not found.keys() & {*held, *brought}
    assert sorted((each["name"], each["pieces"], each.get("table")) for each in found.values()) == [
        ("Porez", ["0,25"], "t1"),
        ("Rok", ["45"], None),
        ("TEČAJ", ["7,6"], "t1"),
        ("tečaj", ["7,7"], "t2"),
    ]


def test_names_follow_the_tables_given_new_ids():
    entries = {"n1": names.entry("Tečaj", ["2*", RATE]), "n2": names.entry("Porez", ["1"], "t1")}
    assert names.rekeyed(entries, {"t1": "u1"}) == {
        "n1": names.entry("Tečaj", ["2*", {**RATE, "table": "u1"}]),
        "n2": names.entry("Porez", ["1"], "u1"),
    }
