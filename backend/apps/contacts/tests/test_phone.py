import base64
import io

import pytest
from django.test import Client
from PIL import Image

from apps.contacts import cards
from apps.contacts.models import Contact
from apps.contacts.vcard import Card
from apps.users.app_passwords import digest, made
from apps.users.models import AppPassword

pytestmark = pytest.mark.django_db

JSON = "application/json"


@pytest.fixture
def phone(owner):
    secret = made()
    AppPassword.objects.create(user=owner, name="Samsung SM-S921B", digest=digest(secret))
    return Client(enforce_csrf_checks=True, headers={"Authorization": f"Bearer {secret}"})


def ana(owner) -> Contact:
    card = Card(points=[{"kind": "phone", "label": "mobile", "value": "091 234 5678"}])
    card.fields.update(given="Ana", family="Horvat", organisation="Firma d.o.o.")
    return cards.made(owner.pk, card, href="ana.vcf")


def picture() -> str:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode()


def test_the_phone_reads_the_whole_book_then_what_changed_since(owner, phone):
    first = ana(owner)
    cards.made(owner.pk, Card(fields={**Card().fields, "name": "Grupa"}, group=True))
    whole = phone.get("/api/device/contacts").json()
    assert whole["gone"] == [] and [each["href"] for each in whole["contacts"]] == ["ana.vcf"]
    assert whole["contacts"][0]["fields"]["name"] == "Ana Horvat"
    assert whole["contacts"][0]["points"] == [
        {"kind": "phone", "label": "mobile", "value": "+385 91 234 5678", "parts": []}
    ]
    assert whole["contacts"][0]["revision"] == first.revision
    since = whole["revision"]
    assert phone.get(f"/api/device/contacts?since={since}").json()["contacts"] == []

    first.note = "Zove poslijepodne"
    cards.saved(first, cards.card(first, photo=False), photo=False)
    cards.deleted(cards.made(owner.pk, Card(fields={**Card().fields, "name": "Ivan"})))
    changed = phone.get(f"/api/device/contacts?since={since}").json()
    assert [each["fields"]["note"] for each in changed["contacts"]] == ["Zove poslijepodne"]
    assert len(changed["gone"]) == 1 and changed["revision"] > since


def test_a_name_made_of_nothing_but_a_firm_stays_empty(owner, phone):
    cards.made(owner.pk, Card(fields={**Card().fields, "organisation": "Firma d.o.o."}))
    served = phone.get("/api/device/contacts").json()["contacts"][0]
    assert served["fields"]["name"] == "" and served["fields"]["organisation"] == "Firma d.o.o."


def test_a_revision_the_book_never_reached_is_refused(owner, phone):
    ana(owner)
    answer = phone.get("/api/device/contacts?since=999999999")
    assert answer.status_code == 410 and answer.json() == {"error": "since_unknown"}
    assert phone.get("/api/device/contacts?since=x").status_code == 400


def test_only_the_phones_own_app_reads_the_book_this_way(owner, client):
    client.force_login(owner)
    assert client.get("/api/device/contacts").json() == {"error": "app_password_required"}


def test_the_phone_makes_a_contact_under_its_own_href_once(owner, phone):
    data = {
        "fields": {"given": "Marko", "family": "Kovač"},
        "points": [{"kind": "email", "label": "work", "value": "Marko@Firma.test"}],
    }
    made_ = phone.put("/api/device/contacts/9f2c.vcf", data, JSON)
    assert made_.status_code == 201
    assert made_.json()["href"] == "9f2c.vcf"
    assert made_.json()["points"][0]["value"] == "marko@firma.test"
    again = phone.put("/api/device/contacts/9f2c.vcf", data, JSON)
    assert again.status_code == 412 and Contact.objects.filter(owner=owner).count() == 1


def test_the_phone_writes_over_only_the_revision_it_read(owner, phone):
    found = ana(owner)
    data = {"fields": {"given": "Ana", "family": "Horvat-Kos"}, "points": []}
    stale = phone.put(
        "/api/device/contacts/ana.vcf", {**data, "revision": found.revision - 1}, JSON
    )
    assert stale.status_code == 412 and stale.json() == {"error": "changed"}
    kept = phone.put("/api/device/contacts/ana.vcf", {**data, "revision": found.revision}, JSON)
    assert kept.status_code == 200
    assert kept.json()["fields"]["family"] == "Horvat-Kos" and kept.json()["points"] == []
    assert kept.json()["revision"] > found.revision
    missing = phone.put("/api/device/contacts/nema.vcf", {**data, "revision": 1}, JSON)
    assert missing.status_code == 404


def test_a_favourite_goes_both_ways_and_stays_where_the_phone_does_not_tell(owner, phone):
    found = ana(owner)
    cards.saved(found, cards.card(found, photo=False), photo=False, starred=True)
    served = phone.get("/api/device/contacts").json()["contacts"][0]
    assert served["starred"] is True
    data = {"fields": served["fields"], "points": served["points"]}
    kept = phone.put("/api/device/contacts/ana.vcf", {**data, "revision": served["revision"]}, JSON)
    assert kept.json()["starred"] is True
    unstarred = phone.put(
        "/api/device/contacts/ana.vcf",
        {**data, "revision": kept.json()["revision"], "starred": False},
        JSON,
    )
    assert unstarred.json()["starred"] is False
    refused = phone.put(
        "/api/device/contacts/ana.vcf",
        {**data, "revision": unstarred.json()["revision"], "starred": "da"},
        JSON,
    )
    assert refused.status_code == 400 and refused.json() == {"error": "invalid_starred"}
    made_ = phone.put("/api/device/contacts/novi.vcf", {**data, "starred": True}, JSON)
    assert made_.status_code == 201 and made_.json()["starred"] is True


def test_the_photo_changes_only_where_the_phone_gives_one(owner, phone):
    found = ana(owner)
    data = {"fields": {"given": "Ana", "family": "Horvat"}, "points": []}
    pictured = phone.put(
        "/api/device/contacts/ana.vcf",
        {**data, "revision": found.revision, "photo": picture()},
        JSON,
    ).json()
    assert pictured["photo"] is not None
    assert Contact.objects.get(pk=found.pk).avatar is not None
    kept = phone.put(
        "/api/device/contacts/ana.vcf", {**data, "revision": pictured["revision"]}, JSON
    )
    assert kept.json()["photo"] == pictured["photo"]
    assert phone.get(f"/api/contacts/{found.pk}/photo").status_code == 200
    removed = phone.put(
        "/api/device/contacts/ana.vcf",
        {**data, "revision": kept.json()["revision"], "photo": None},
        JSON,
    )
    assert removed.json()["photo"] is None
    broken = phone.put(
        "/api/device/contacts/ana.vcf",
        {**data, "revision": removed.json()["revision"], "photo": "nije slika!"},
        JSON,
    )
    assert broken.status_code == 400 and broken.json() == {"error": "invalid_photo"}


def test_the_phone_deletes_only_the_revision_it_read(owner, phone):
    found = ana(owner)
    since = phone.get("/api/device/contacts").json()["revision"]
    stale = phone.delete(f"/api/device/contacts/ana.vcf?revision={found.revision - 1}")
    assert stale.status_code == 412
    assert (
        phone.delete(f"/api/device/contacts/ana.vcf?revision={found.revision}").status_code == 204
    )
    assert phone.delete("/api/device/contacts/ana.vcf?revision=1").status_code == 404
    assert phone.get(f"/api/device/contacts?since={since}").json()["gone"] == ["ana.vcf"]
