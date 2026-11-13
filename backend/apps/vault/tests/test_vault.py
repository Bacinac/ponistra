import base64
import uuid

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from apps.access.tests.test_access import JSON, person
from apps.actions.models import ActionRun
from apps.ai import installation, model
from apps.ai.tests.recorded import Recorded, message, used
from apps.blobs.tests.test_blobs import content
from apps.users.models import Passkey
from apps.vault import sorting
from apps.vault.models import Escrow, Event, Holder, Key, Unlock

pytestmark = pytest.mark.django_db

KDF = {
    "salt": base64.b64encode(b"s" * 16).decode(),
    "memory": 65536,
    "iterations": 3,
    "parallelism": 4,
}


def sealed(tag: str, size: int = 48) -> str:
    return base64.b64encode(tag.encode().ljust(size, b".")).decode()


def made(client, tag: str = "ana") -> dict:
    answer = client.post(
        "/api/vault",
        {
            "public_key": sealed(f"{tag} public", 32),
            "private_key": sealed(f"{tag} private"),
            "kdf": KDF,
            "by_password": sealed(f"{tag} by password"),
            "by_code": sealed(f"{tag} by code"),
            "code": sealed(f"{tag} code"),
            "personal": sealed(f"{tag} personal"),
        },
        JSON,
    )
    assert answer.status_code == 201, answer.json()
    return answer.json()


def listed(client) -> dict:
    return {
        each["name"]: each for each in client.get("/api/vault/collections").json()["collections"]
    }


def shared(client, name: str) -> str:
    answer = client.post("/api/vault/collections", {"name": name, "key": sealed(name)}, JSON)
    assert answer.status_code == 201, answer.json()
    return answer.json()["id"]


def member(client, collection, kind, id, role, keys=()):
    return client.post(
        f"/api/vault/collections/{collection}/members",
        {"grantee": {"kind": kind, "id": id}, "role": role, "keys": list(keys)},
        JSON,
    )


def add(client, collection, data="secret") -> str:
    answer = client.post(
        f"/api/vault/collections/{collection}/items",
        {"items": [{"key": sealed("item key"), "data": sealed(data)}]},
        JSON,
    )
    assert answer.status_code == 201, answer.json()
    return answer.json()["items"][0]["id"]


@pytest.fixture
def admin():
    return person("ivo@example.com", is_staff=True)


@pytest.fixture
def it():
    return Group.objects.create(name="IT")


@pytest.fixture
def ana(it):
    client = person("ana@example.com", first_name="Ana")
    client.user.groups.add(it)
    return client


@pytest.fixture
def marko():
    return person("marko@example.com", first_name="Marko")


def test_a_vault_is_made_once_with_the_users_own_collection(ana):
    assert ana.get("/api/vault").json() is None
    assert ana.delete("/api/vault").status_code == 204
    vault = made(ana)
    assert vault["kdf"] == KDF and vault["handed"] is None and vault["recovery"] is None
    assert ana.get("/api/vault").json() == vault
    own = listed(ana)[""]
    assert own["kind"] == "personal" and own["role"] == "own"
    assert own["key"] == sealed("ana personal") and own["items"] == 0
    assert ana.post("/api/vault", {}, JSON).status_code == 400
    again = ana.post(
        "/api/vault",
        {
            **{
                k: vault[k]
                for k in ("public_key", "private_key", "kdf", "by_password", "by_code", "code")
            },
            "personal": sealed("x"),
        },
        JSON,
    )
    assert again.json() == {"error": "vault_exists"}


def test_argon2id_costs_below_the_floor_are_refused(ana):
    made(ana)
    for weak in ({"memory": 1024}, {"iterations": 1}, {"parallelism": 0}, {"salt": "c2hvcnQ="}):
        answer = ana.patch("/api/vault", {"kdf": {**KDF, **weak}, "by_password": sealed("p")}, JSON)
        assert answer.json() == {"error": "invalid_kdf"}
    answer = ana.patch(
        "/api/vault", {"kdf": {**KDF, "iterations": 4}, "by_password": sealed("p")}, JSON
    )
    assert answer.json()["kdf"]["iterations"] == 4


def test_a_shared_collection_reaches_a_member_only_once_an_owner_seals_its_key_to_them(
    ana, marko, it
):
    made(ana)
    made(marko, "marko")
    servers = shared(ana, "Poslužitelji")
    answer = member(
        ana,
        servers,
        "user",
        marko.user.pk,
        "read",
        [{"user": marko.user.pk, "sealed": sealed("for marko")}],
    )
    assert answer.status_code == 200, answer.json()
    assert answer.json()["waiting"] == [] and answer.json()["unset"] == []
    seen = listed(marko)["Poslužitelji"]
    assert seen["role"] == "read" and seen["key"] == sealed("for marko") and "waiting" not in seen
    item = add(ana, servers)
    assert [
        each["id"] for each in marko.get(f"/api/vault/collections/{servers}/items").json()["items"]
    ] == [item]
    assert (
        marko.post(
            f"/api/vault/collections/{servers}/items",
            {"key": sealed("k"), "data": sealed("d")},
            JSON,
        ).status_code
        == 403
    )
    assert (
        marko.patch(f"/api/vault/items/{item}", {"data": sealed("changed")}, JSON).status_code
        == 403
    )


def test_a_group_given_a_role_waits_for_an_owner_to_confirm_its_members(ana, marko, it):
    made(ana)
    made(marko, "marko")
    servers = shared(marko, "Poslužitelji")
    lena = person("lena@example.com")
    lena.user.groups.add(it)
    answer = member(marko, servers, "group", it.pk, "edit")
    assert [each["email"] for each in answer.json()["waiting"]] == ["ana@example.com"]
    assert [each["email"] for each in answer.json()["unset"]] == ["lena@example.com"]
    assert listed(marko)["Poslužitelji"]["waiting"] == 1
    assert listed(ana)["Poslužitelji"]["key"] is None
    confirmed = {"keys": [{"user": ana.user.pk, "sealed": sealed("for ana")}]}
    assert ana.post(f"/api/vault/collections/{servers}/keys", confirmed, JSON).status_code == 403
    stranger = {"keys": [{"user": person("x@example.com").user.pk, "sealed": sealed("x")}]}
    assert marko.post(f"/api/vault/collections/{servers}/keys", stranger, JSON).json() == {
        "error": "invalid_keys"
    }
    answer = marko.post(f"/api/vault/collections/{servers}/keys", confirmed, JSON)
    assert answer.json()["waiting"] == []
    assert listed(ana)["Poslužitelji"]["key"] == sealed("for ana")
    again = marko.post(f"/api/vault/collections/{servers}/keys", confirmed, JSON)
    assert again.json() == {"error": "invalid_keys"}
    assert Event.objects.filter(kind="confirmed", subject=ana.user).count() == 1


def test_whom_a_collection_no_longer_reaches_loses_its_key(admin, ana, marko, it):
    made(ana)
    made(marko, "marko")
    servers = shared(marko, "Poslužitelji")
    member(
        marko, servers, "group", it.pk, "read", [{"user": ana.user.pk, "sealed": sealed("for ana")}]
    )
    admin.patch(f"/api/users/{ana.user.pk}", {"groups": []}, JSON)
    assert ana.get(f"/api/vault/collections/{servers}/items").status_code == 404
    assert not Key.objects.filter(user=ana.user).exclude(collection__kind="personal").exists()
    ana.user.groups.add(it)
    assert listed(ana)["Poslužitelji"]["key"] is None


def test_a_shared_collection_keeps_a_living_owner_and_members_may_leave(ana, marko):
    made(ana)
    made(marko, "marko")
    servers = shared(ana, "Poslužitelji")
    member(
        ana,
        servers,
        "user",
        marko.user.pk,
        "read",
        [{"user": marko.user.pk, "sealed": sealed("m")}],
    )
    members = ana.get(f"/api/vault/collections/{servers}/members").json()["members"]
    own = next(each for each in members if each["grantee"]["id"] == ana.user.pk)
    theirs = next(each for each in members if each["grantee"]["id"] == marko.user.pk)
    assert ana.delete(f"/api/vault/members/{own['id']}").json() == {"error": "collection_owner"}
    assert (
        marko.patch(f"/api/vault/members/{theirs['id']}", {"role": "own"}, JSON).status_code == 403
    )
    assert marko.delete(f"/api/vault/members/{theirs['id']}").status_code == 204
    assert "Poslužitelji" not in listed(marko)
    assert not Key.objects.filter(user=marko.user, collection_id=servers).exists()


def test_an_administrator_lays_out_company_collections_without_a_key_to_them(admin, ana, marko, it):
    made(admin, "ivo")
    made(ana)
    answer = admin.post(
        "/api/vault/company", {"name": "IT", "grants": [{"group": it.pk, "role": "own"}]}, JSON
    )
    assert answer.status_code == 201, answer.json()
    company = answer.json()["id"]
    assert "IT" not in listed(admin)
    assert admin.get(f"/api/vault/collections/{company}/items").status_code == 404
    seen = listed(ana)["IT"]
    assert seen["kind"] == "company" and seen["key"] is None and seen["keyless"]
    assert seen["waiting"] == 1
    first = {"keys": [{"user": ana.user.pk, "sealed": sealed("first")}]}
    assert ana.post(f"/api/vault/collections/{company}/keys", first, JSON).status_code == 200
    assert listed(ana)["IT"]["key"] == sealed("first") and not listed(ana)["IT"]["keyless"]
    marko.user.groups.add(it)
    made(marko, "marko")
    assert listed(marko)["IT"]["key"] is None and not listed(marko)["IT"]["keyless"]
    assert member(ana, company, "user", admin.user.pk, "read").json() == {"error": "not_shared"}
    assert ana.patch(f"/api/vault/collections/{company}", {"name": "Drugo"}, JSON).json() == {
        "error": "not_shared"
    }
    add(ana, company)
    assert admin.delete(f"/api/vault/company/{company}").json() == {"error": "collection_not_empty"}
    assert admin.delete(f"/api/groups/{it.pk}").json() == {"error": "collection_owner"}


def test_items_move_between_collections_the_user_edits_and_pass_through_the_trash(ana, marko):
    made(ana)
    made(marko, "marko")
    own = listed(ana)[""]["id"]
    servers = shared(marko, "Poslužitelji")
    member(
        marko, servers, "user", ana.user.pk, "edit", [{"user": ana.user.pk, "sealed": sealed("a")}]
    )
    item = add(ana, own)
    empty = ana.post(f"/api/vault/collections/{own}/items", {"items": []}, JSON)
    assert empty.json() == {"error": "invalid_items"}
    moved = ana.patch(
        f"/api/vault/items/{item}", {"collection": servers, "key": sealed("rewrapped")}, JSON
    )
    assert moved.json()["collection"] == servers and moved.json()["key"] == sealed("rewrapped")
    assert ana.delete(f"/api/vault/items/{item}").status_code == 204
    assert ana.get(f"/api/vault/collections/{servers}/items").json()["items"] == []
    assert [each["id"] for each in ana.get("/api/vault/trash").json()["items"]] == [item]
    assert ana.post("/api/vault/trash/purge", {"items": [item]}, JSON).status_code == 403
    assert ana.post("/api/vault/trash/restore", {"items": [item]}, JSON).status_code == 204
    assert ana.get("/api/vault/trash").json()["items"] == []
    ana.delete(f"/api/vault/items/{item}")
    assert marko.post("/api/vault/trash/purge", {"items": [item]}, JSON).status_code == 204
    assert marko.get("/api/vault/trash").json()["items"] == []


def test_an_attachment_is_kept_sealed_and_served_only_to_the_collections_members(
    ana, marko, upload
):
    made(ana)
    own = listed(ana)[""]["id"]
    item = add(ana, own)
    blob = upload(b"sealed bytes")["sha256"]
    answer = ana.post(
        f"/api/vault/items/{item}/attachments", {"blob": blob, "meta": sealed("name")}, JSON
    )
    assert answer.status_code == 201
    attachment = answer.json()["id"]
    assert content(ana.get(f"/api/vault/attachments/{attachment}")) == b"sealed bytes"
    assert marko.get(f"/api/vault/attachments/{attachment}").status_code == 404
    listed_item = ana.get(f"/api/vault/collections/{own}/items").json()["items"][0]
    assert listed_item["attachments"] == [{"id": attachment, "meta": sealed("name"), "size": 12}]
    assert ana.delete(f"/api/vault/attachments/{attachment}").status_code == 204


def test_the_log_shows_owners_who_opened_and_saw_once_an_hour(ana, marko):
    made(ana)
    made(marko, "marko")
    servers = shared(ana, "Poslužitelji")
    member(
        ana,
        servers,
        "user",
        marko.user.pk,
        "read",
        [{"user": marko.user.pk, "sealed": sealed("m")}],
    )
    item = add(ana, servers)
    for _ in range(2):
        marko.get(f"/api/vault/collections/{servers}/items")
        marko.post(f"/api/vault/items/{item}/seen", {"field": "password"}, JSON)
    marko.post(f"/api/vault/items/{item}/seen", {"field": "totp"}, JSON)
    assert (
        marko.post(f"/api/vault/items/{item}/seen", {"field": "username"}, JSON).status_code == 400
    )
    assert marko.get(f"/api/vault/collections/{servers}/log").status_code == 403
    events = ana.get(f"/api/vault/collections/{servers}/log").json()["events"]
    kinds = [(event["kind"], event["user"]["email"], event["detail"]) for event in events]
    assert kinds == [
        ("seen", "marko@example.com", {"field": "totp"}),
        ("seen", "marko@example.com", {"field": "password"}),
        ("opened", "marko@example.com", {}),
        ("confirmed", "ana@example.com", {}),
        (
            "shared",
            "ana@example.com",
            {
                "grantee": {
                    "kind": "user",
                    "id": marko.user.pk,
                    "email": "marko@example.com",
                    "name": "Marko",
                    "outside": False,
                },
                "role": "read",
            },
        ),
    ]
    own = listed(ana)[""]["id"]
    ana.get(f"/api/vault/collections/{own}/items")
    assert ana.get(f"/api/vault/collections/{own}/log").json() == {"error": "not_shared"}


def test_recovery_through_the_company_hands_a_user_a_code_from_an_administrator_who_holds_its_key(
    admin, ana
):
    made(ana)
    assert admin.put("/api/vault/recovery", {}, JSON).json() == {"error": "no_vault"}
    made(admin, "ivo")
    on = admin.put(
        "/api/vault/recovery",
        {"public_key": sealed("company", 32), "sealed": sealed("for ivo")},
        JSON,
    ).json()
    assert (
        on["on"] and on["sealed"] == sealed("for ivo") and on["escrowed"] == 0 and on["vaults"] == 2
    )
    vault = ana.get("/api/vault").json()
    assert vault["recovery"] == {"public_key": sealed("company", 32)} and not vault["escrowed"]
    stale = {"public_key": sealed("older", 32), "sealed": sealed("escrow")}
    assert ana.put("/api/vault/escrow", stale, JSON).json() == {"error": "recovery_changed"}
    assert ana.put(
        "/api/vault/escrow", {**stale, "public_key": sealed("company", 32)}, JSON
    ).json()["escrowed"]
    assert admin.get(f"/api/users/{ana.user.pk}/vault").json() == {
        "vault": True,
        "escrow": sealed("escrow"),
    }
    assert ana.get(f"/api/users/{admin.user.pk}/vault").status_code == 403
    assert (
        admin.post(
            f"/api/users/{ana.user.pk}/vault", {"handed": sealed("handed")}, JSON
        ).status_code
        == 204
    )
    vault = ana.get("/api/vault").json()
    assert (
        vault["handed"] == sealed("handed")
        and vault["recovered"]["by"]["email"] == "ivo@example.com"
    )
    vault = ana.patch("/api/vault", {"kdf": KDF, "by_password": sealed("new")}, JSON).json()
    assert vault["handed"] is None and vault["by_password"] == sealed("new")
    assert admin.delete("/api/vault/recovery").json() == {"on": False}
    assert not Escrow.objects.exists()
    assert ana.get("/api/vault").json()["recovery"] is None


def test_the_recovery_key_reaches_another_administrator_only_through_one_who_holds_it(admin, ana):
    made(admin, "ivo")
    made(ana)
    admin.put(
        "/api/vault/recovery",
        {"public_key": sealed("company", 32), "sealed": sealed("for ivo")},
        JSON,
    )
    admin.patch(f"/api/users/{ana.user.pk}", {"is_admin": True}, JSON)
    ana.user.refresh_from_db()
    state = ana.get("/api/vault/recovery").json()
    assert state["sealed"] is None and [each["email"] for each in state["waiting"]] == [
        "ana@example.com"
    ]
    entries = {"holders": [{"user": ana.user.pk, "sealed": sealed("for ana")}]}
    assert ana.post("/api/vault/recovery/holders", entries, JSON).json() == {"error": "no_key"}
    assert admin.post("/api/vault/recovery/holders", entries, JSON).json()["waiting"] == []
    assert ana.get("/api/vault/recovery").json()["sealed"] == sealed("for ana")
    admin.patch(f"/api/users/{ana.user.pk}", {"is_admin": False}, JSON)
    assert not Holder.objects.filter(user=ana.user).exists()
    assert admin.delete("/api/vault").json() == {"error": "last_holder"}


def test_starting_over_gives_up_the_vault_its_own_items_and_every_key(ana, marko):
    made(ana)
    made(marko, "marko")
    own = listed(ana)[""]["id"]
    add(ana, own)
    servers = shared(marko, "Poslužitelji")
    member(
        marko, servers, "user", ana.user.pk, "read", [{"user": ana.user.pk, "sealed": sealed("a")}]
    )
    assert ana.delete("/api/vault").status_code == 204
    assert ana.get("/api/vault").json() is None
    assert not Key.objects.filter(user=ana.user).exists()
    made(ana)
    collections = listed(ana)
    assert collections[""]["items"] == 0 and collections["Poslužitelji"]["key"] is None


def test_a_passkey_unlocks_only_its_own_users_vault_and_goes_with_it(ana, marko):
    made(ana)
    Passkey.objects.create(user=marko.user, credential=b"m", public_key=b"k", name="Marko")
    mine = Passkey.objects.create(user=ana.user, credential=b"a", public_key=b"k", name="Laptop")
    unlock = {"salt": sealed("salt", 32), "wrapped": sealed("wrapped")}
    assert ana.post("/api/vault/unlocks", {**unlock, "credential": "bQ=="}, JSON).json() == {
        "error": "invalid_credential"
    }
    vault = ana.post("/api/vault/unlocks", {**unlock, "credential": "YQ=="}, JSON).json()
    assert vault["unlocks"] == [
        {"passkey": mine.pk, "name": "Laptop", "credential": "YQ==", **unlock}
    ]
    mine.delete()
    assert not Unlock.objects.exists()


def test_public_keys_name_every_active_user_with_a_vault_to_anyone_signed_in(admin, ana, marko):
    assert Client().get("/api/vault/public-keys").status_code == 401
    assert marko.post("/api/vault/public-keys", {}, JSON).status_code == 405
    assert marko.get("/api/vault/public-keys").json() == {"keys": []}
    made(ana)
    made(admin, "ivo")
    keys = marko.get("/api/vault/public-keys").json()["keys"]
    assert sorted(keys, key=lambda each: each["user"]) == sorted(
        [
            {"user": ana.user.pk, "public_key": sealed("ana public", 32)},
            {"user": admin.user.pk, "public_key": sealed("ivo public", 32)},
        ],
        key=lambda each: each["user"],
    )
    admin.user.is_active = False
    admin.user.save()
    assert marko.get("/api/vault/public-keys").json() == {
        "keys": [{"user": ana.user.pk, "public_key": sealed("ana public", 32)}]
    }


def folders(client, collection, *given):
    return client.post(
        f"/api/vault/collections/{collection}/folders",
        {
            "folders": [
                {"name": sealed(name), "id": str(pk), "parent": parent and str(parent)}
                for pk, name, parent in given
            ]
        },
        JSON,
    )


def test_folders_hold_a_collections_items_and_go_leaving_them_at_its_top(ana, marko):
    made(ana)
    made(marko, "marko")
    own = listed(ana)[""]["id"]
    servers = shared(marko, "Poslužitelji")
    member(
        marko, servers, "user", ana.user.pk, "edit", [{"user": ana.user.pk, "sealed": sealed("a")}]
    )
    banks, erste, racks = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    answer = folders(ana, own, (banks, "Banke", None), (erste, "Erste", banks))
    assert answer.status_code == 201, answer.json()
    assert folders(ana, own, (banks, "Opet", None)).json() == {"error": "folder_exists"}
    assert folders(marko, servers, (racks, "Ormari", erste)).json() == {"error": "invalid_folder"}
    assert folders(marko, own, (racks, "Ormari", None)).status_code == 404
    assert ana.get(f"/api/vault/collections/{own}/folders").json()["folders"] == [
        {"id": str(banks), "parent": None, "name": sealed("Banke")},
        {"id": str(erste), "parent": str(banks), "name": sealed("Erste")},
    ]

    item = ana.post(
        f"/api/vault/collections/{own}/items",
        {"items": [{"key": sealed("k"), "data": sealed("d"), "folder": str(erste)}]},
        JSON,
    ).json()["items"][0]
    assert item["folder"] == str(erste)
    other = add(ana, own)
    filed = ana.patch(
        f"/api/vault/collections/{own}/items",
        {"folders": {item["id"]: None, other: str(banks)}},
        JSON,
    )
    assert filed.status_code == 204
    shown = {
        each["id"]: each["folder"]
        for each in ana.get(f"/api/vault/collections/{own}/items").json()["items"]
    }
    assert shown == {item["id"]: None, other: str(banks)}
    stray = ana.patch(f"/api/vault/collections/{own}/items", {"folders": {other: str(racks)}}, JSON)
    assert stray.json() == {"error": "invalid_folder"}

    assert ana.patch(f"/api/vault/folders/{banks}", {"parent": str(erste)}, JSON).json() == {
        "error": "invalid_folder"
    }
    renamed = ana.patch(f"/api/vault/folders/{erste}", {"name": sealed("Erste banka")}, JSON)
    assert renamed.json()["name"] == sealed("Erste banka")
    assert marko.delete(f"/api/vault/folders/{banks}").status_code == 404
    assert ana.delete(f"/api/vault/folders/{banks}").status_code == 204
    assert ana.get(f"/api/vault/collections/{own}/folders").json() == {"folders": []}

    folders(marko, servers, (racks, "Ormari", None))
    moved = ana.patch(
        f"/api/vault/items/{other}",
        {"collection": servers, "key": sealed("rewrapped"), "folder": str(racks)},
        JSON,
    )
    assert moved.json()["folder"] == str(racks)
    back = ana.patch(f"/api/vault/items/{other}", {"collection": own, "key": sealed("back")}, JSON)
    assert back.json()["folder"] is None


def proposed(*folders):
    return message(
        "tool_use",
        used("u1", "folders", {"folders": list(folders)}),
        model=sorting.MODEL,
        usage={"input_tokens": 4000, "output_tokens": 300},
    )


def test_a_model_proposes_folders_from_names_and_hosts_once_the_user_lets_them_out(
    ana, monkeypatch
):
    made(ana)
    own = listed(ana)[""]["id"]
    recorded = Recorded(
        proposed(
            {"name": "Banke", "entries": [0, 2]},
            {"name": " banke ", "entries": [1, 2]},
            {"name": "Kupnja", "entries": [0, 3, 9]},
            {"name": "Prazno", "entries": [7]},
        )
    )
    monkeypatch.setattr(model, "answer", recorded)
    entries = [
        {"name": "Erste NetBanking", "host": "netbanking.erstebank.hr"},
        {"name": "PBZ", "host": "pbz.hr"},
        {"name": "Revolut", "host": ""},
        {"name": "Links", "host": "links.hr"},
    ]

    def sort(**fields):
        given = {"entries": entries, "existing": ["Posao"], "language": "hr", **fields}
        return ana.post(f"/api/vault/collections/{own}/sorting", given, JSON)

    assert sort(consent="once").json() == {"error": "ai_off"}
    monkeypatch.setattr(installation, "enabled", lambda: True)
    assert sort().json() == {"error": "consent_needed"}
    assert sort(entries=[{"name": "PBZ"}]).json() == {"error": "invalid_entries"}
    assert sort(language="de", consent="once").json() == {"error": "invalid_language"}
    assert recorded.asked == []

    answer = sort(consent="once")
    assert answer.status_code == 200, answer.json()
    assert answer.json() == {
        "folders": [
            {"name": "Banke", "entries": [0, 2, 1]},
            {"name": "Kupnja", "entries": [3]},
        ]
    }
    (request,) = recorded.asked
    assert request["model"] == sorting.MODEL
    content = request["messages"][0]["content"]
    assert content.startswith('Folders the collection has: ["Posao"]')
    assert '[0, "Erste NetBanking", "netbanking.erstebank.hr"]' in content
    assert "Croatian" in request["system"][0]["text"]
    run = ActionRun.objects.get()
    assert (run.action, run.state, run.user, run.consent) == (
        sorting.ACTION,
        "done",
        ana.user,
        "once",
    )
    assert (run.target, run.input_tokens) == ({"collection": own}, 4000)
