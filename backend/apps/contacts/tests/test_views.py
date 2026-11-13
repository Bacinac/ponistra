import base64

import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.contacts import cards
from apps.contacts.models import Book, Contact, Gone
from apps.contacts.vcard import Card
from apps.mail.models import Correspondent
from apps.mail.tests import eas
from apps.users.app_passwords import digest
from apps.users.models import AppPassword

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def content(response) -> bytes:
    async def read():
        return b"".join([part async for part in response.streaming_content])

    return async_to_sync(read)()


def person(name="", organisation="", **points) -> Card:
    made = Card(
        points=[{"kind": k, "label": "", "value": v, "parts": []} for k, v in points.items()]
    )
    made.fields.update(name=name, organisation=organisation)
    return made


@pytest.fixture
def signed(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_the_book_lists_by_name_and_finds_by_any_word_of_a_person(signed, owner):
    cards.made(owner.pk, person("Željko Šimić", "Brodogradilište", email="zeljko@brod.test"))
    cards.made(owner.pk, person("Ana Horvat", phone="091 234 5678"))
    group = person("Prijatelji")
    group.group = True
    cards.made(owner.pk, group)
    listed = signed.get("/api/contacts").json()
    assert [each["name"] for each in listed["contacts"]] == ["Ana Horvat", "Željko Šimić"]
    assert (listed["failed"], listed["directories"]) == ([], [])
    for typed in ("simic", "brodo", "zeljko@", "091"):
        assert [
            e["name"] for e in signed.get("/api/contacts", {"q": typed}).json()["contacts"]
        ] in (
            ["Željko Šimić"],
            ["Ana Horvat"],
        )
    assert signed.get("/api/contacts", {"q": "horvat simic"}).json()["contacts"] == []


@pytest.mark.django_db
def test_the_book_is_in_the_order_of_the_croatian_alphabet(signed, owner):
    for name in ("Antonia", "Čedo", "Anđela", "cvita", "Andro", "Ćiro", "Zora", "Šime"):
        cards.made(owner.pk, person(name))
    listed = [each["name"] for each in signed.get("/api/contacts").json()["contacts"]]
    assert listed == ["Andro", "Anđela", "Antonia", "cvita", "Čedo", "Ćiro", "Šime", "Zora"]


@pytest.mark.django_db
def test_favourites_come_first_and_stay_through_a_change_of_the_card(signed, owner):
    ana = cards.made(owner.pk, person("Ana Horvat"))
    zora = cards.made(owner.pk, person("Zora Kos"))

    def star(chosen, starred=True):
        return signed.post(
            "/api/contacts/star", {"contacts": chosen, "starred": starred}, "application/json"
        )

    assert star([zora.pk]).status_code == 204
    listed = signed.get("/api/contacts").json()["contacts"]
    assert [(each["name"], each["starred"]) for each in listed] == [
        ("Zora Kos", True),
        ("Ana Horvat", False),
    ]
    revision = Contact.objects.get(pk=zora.pk).revision
    assert revision > zora.revision
    star([zora.pk])
    assert Contact.objects.get(pk=zora.pk).revision == revision

    changed = signed.patch(
        f"/api/contacts/{zora.pk}",
        {"fields": {"name": "Zora Kos-Car"}, "points": []},
        "application/json",
    )
    assert changed.json()["starred"] is True
    star([zora.pk, ana.pk], starred=False)
    assert [each["name"] for each in signed.get("/api/contacts").json()["contacts"]] == [
        "Ana Horvat",
        "Zora Kos-Car",
    ]
    assert star([ana.pk, zora.pk]).status_code == 204
    assert Contact.objects.filter(owner=owner, starred=True).count() == 2
    assert star([ana.pk], starred="da").json() == {"error": "invalid_starred"}
    assert star([]).json() == {"error": "invalid_contacts"}
    assert star([ana.pk, ana.pk + zora.pk], starred=False).status_code == 404
    assert Contact.objects.filter(owner=owner, starred=True).count() == 2


@pytest.mark.django_db
def test_a_contact_is_made_changed_and_removed_with_its_photo(signed, owner):
    given = {
        "fields": {"given": "Ana", "family": "Horvat", "birthday": "--03-15"},
        "points": [
            {"kind": "phone", "label": "mobile", "value": " 091 234 5678 "},
            {
                "kind": "address",
                "label": "work",
                "parts": ["", "", "Ilica 1", "Zagreb", "", "10000"],
            },
            {"kind": "email", "label": "", "value": ""},
        ],
    }
    made = signed.post("/api/contacts", given, content_type="application/json")
    assert made.status_code == 201
    ana = made.json()
    ana_uid = Contact.objects.get().uid
    assert (ana["name"], ana["phone"], ana["fields"]["birthday"]) == (
        "Ana Horvat",
        "+385 91 234 5678",
        "--03-15",
    )
    assert ana["points"][1]["value"] == "Ilica 1\n10000 Zagreb"
    path = f"/api/contacts/{ana['id']}"
    for wrong, error in (
        ({"fields": {}}, "empty_contact"),
        ({"fields": {"birthday": "15.3."}}, "invalid_birthday"),
        ({"fields": {"given": "A"}, "points": [{"kind": "fax", "value": "1"}]}, "invalid_points"),
    ):
        answered = signed.patch(path, wrong, content_type="application/json")
        assert (answered.status_code, answered.json()["error"]) == (400, error)
    changed = signed.patch(
        path, {"fields": {"given": "Ana", "note": "Kći Lana"}}, content_type="application/json"
    )
    assert (changed.json()["fields"]["note"], changed.json()["points"]) == ("Kći Lana", [])
    revision = Contact.objects.get().revision
    shown = signed.put(f"{path}/photo", PNG, content_type="image/png").json()
    assert shown["photo"] and Contact.objects.get().revision > revision
    assert content(signed.get(f"{path}/photo")) == PNG
    avatar = signed.get("/api/contacts").json()["contacts"][0]["avatar"]
    assert avatar.startswith("data:image/webp;base64,")
    assert signed.put(f"{path}/photo", b"<svg/>", content_type="image/svg+xml").status_code == 415
    assert signed.delete(f"{path}/photo").json()["photo"] is None
    assert signed.get("/api/contacts").json()["contacts"][0]["avatar"] is None
    assert signed.delete(path).status_code == 204
    assert Gone.objects.get().href == f"{ana_uid}.vcf"
    assert not Contact.objects.exists()


@pytest.mark.django_db
def test_another_users_contact_is_not_found(signed, owner, django_user_model):
    other = django_user_model.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    theirs = cards.made(other.pk, person("Marko"))
    assert signed.get(f"/api/contacts/{theirs.pk}").status_code == 404
    assert signed.delete(f"/api/contacts/{theirs.pk}").status_code == 404


@pytest.mark.django_db
def test_chosen_contacts_go_together_or_none_when_one_is_not_mine(signed, owner, django_user_model):
    other = django_user_model.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    theirs = cards.made(other.pk, person("Marko"))
    mine = [cards.made(owner.pk, person(name)).pk for name in ("Ivan", "Mia", "Dino")]
    deleting = {"contacts": [mine[0], theirs.pk]}
    assert signed.post("/api/contacts/delete", deleting, "application/json").status_code == 404
    assert Contact.objects.filter(owner=owner).count() == 3
    deleting = {"contacts": mine[:2]}
    assert signed.post("/api/contacts/delete", deleting, "application/json").status_code == 204
    assert list(Contact.objects.filter(owner=owner).values_list("pk", flat=True)) == [mine[2]]
    assert Gone.objects.count() == 2


@pytest.mark.django_db
def test_an_account_whose_contacts_failed_says_why(signed, account):
    Book.objects.create(account=account, server_id="5", name="Contacts", error="activesync_login")
    assert signed.get("/api/contacts").json()["failed"] == [
        {"account": eas.USER, "error": "activesync_login"}
    ]


@pytest.mark.django_db(transaction=True)
def test_a_colleague_found_in_the_directory_is_added_with_one_click(signed, account, box):
    box.people = [("Ana Horvat", "ana.horvat@example.com", {"Title": "Direktorica"})]
    found = signed.get("/api/contacts/colleagues", {"q": "ana"}).json()
    assert found["unanswered"] == []
    assert [(each["address"], each["title"], each["contact"]) for each in found["people"]] == [
        ("ana.horvat@example.com", "Direktorica", None)
    ]
    chosen = {"account": account.pk, "address": "ana.horvat@example.com", "name": "Ana Horvat"}
    made = signed.post("/api/contacts/colleagues", chosen, content_type="application/json")
    assert made.status_code == 201
    assert (made.json()["colleague"], made.json()["title"]) == (True, "Direktorica")
    assert made.json()["directory"]["fields"]["title"] == "Direktorica"
    again = signed.get("/api/contacts/colleagues", {"q": "ana"}).json()["people"]
    assert again[0]["contact"] == made.json()["id"]
    missing = {**chosen, "address": "nema@example.com", "name": "Nema"}
    assert (
        signed.post(
            "/api/contacts/colleagues", missing, content_type="application/json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_writing_a_message_offers_the_contacts_first(signed, owner):
    cards.made(owner.pk, person("Ana Horvat", email="ana@firma.test"))
    cards.made(owner.pk, person("Ana Kovač", email="ana.kovac@firma.test"))
    now = timezone.now()
    Correspondent.objects.create(owner=owner, address="ana.kovac@firma.test", written=5, last=now)
    Correspondent.objects.create(owner=owner, address="anamarija@drugo.test", written=9, last=now)
    assert [
        each["address"] for each in signed.get("/api/mail/people", {"q": "ana"}).json()["people"]
    ] == [
        "ana.kovac@firma.test",
        "ana@firma.test",
        "anamarija@drugo.test",
    ]


@pytest.mark.django_db
def test_an_app_password_is_shown_once_and_signs_out_its_device_when_removed(signed, owner):
    made = signed.post("/api/app-passwords", {"name": "iPhone"}, content_type="application/json")
    assert made.status_code == 201
    secret = made.json()["password"]
    assert len(secret) == 19 and secret.count("-") == 3
    assert AppPassword.objects.get().digest == digest(secret.replace("-", "").upper())
    listed = signed.get("/api/app-passwords").json()["app_passwords"]
    assert [(each["name"], "password" in each) for each in listed] == [("iPhone", False)]
    assert (
        signed.post("/api/app-passwords", {"name": ""}, content_type="application/json").status_code
        == 400
    )
    assert signed.delete(f"/api/app-passwords/{made.json()['id']}").status_code == 204
    assert signed.delete(f"/api/app-passwords/{made.json()['id']}").status_code == 404


@pytest.mark.django_db
def test_a_photo_that_is_no_picture_is_kept_without_an_avatar(owner):
    contact = cards.made(owner.pk, Card(photo=b"no picture"))
    assert contact.photo_id is not None and contact.avatar is None
