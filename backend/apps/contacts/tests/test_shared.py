import base64
import json

import pytest
from django.test import Client

from apps.contacts import cards
from apps.contacts.models import Contact
from apps.mail import sharing
from apps.mail.models import Grant
from apps.users.app_passwords import digest, made
from apps.users.models import AppPassword, User

from .test_views import person

pytestmark = pytest.mark.django_db


def test_the_contacts_of_a_mailbox_are_shared_by_its_grants(client):
    ivo, ana, marko = (
        User.objects.create_user(f"{name}@example.com", "Kamen-Most-Rijeka-71")
        for name in ("ivo", "ana", "marko")
    )
    box = sharing.made(ivo, "Prodaja")
    buyer = cards.made(box.pk, person("Kupac d.o.o.", email="kupac@example.com"))
    Grant.objects.create(mailbox=box, user=ana, role="read")
    client.force_login(ana)

    assert client.get("/api/contacts").json()["contacts"] == []
    found = client.get(f"/api/contacts?box={box.pk}").json()
    assert [each["id"] for each in found["contacts"]] == [buyer.pk]
    assert found["role"] == "read"
    assert client.get(f"/api/contacts/{buyer.pk}").json()["name"] == "Kupac d.o.o."
    starred = {"contacts": [buyer.pk], "starred": True}
    assert (
        client.post(f"/api/contacts/star?box={box.pk}", starred, "application/json").status_code
        == 403
    )

    Grant.objects.filter(mailbox=box, user=ana).update(role="edit")
    assert (
        client.post(f"/api/contacts/star?box={box.pk}", starred, "application/json").status_code
        == 204
    )
    assert sharing.concerned(str(box.pk)) == {box.pk, ivo.pk, ana.pk}

    client.force_login(marko)
    assert client.get(f"/api/contacts?box={box.pk}").status_code == 404
    assert client.get(f"/api/contacts/{buyer.pk}").status_code == 404


PROPS = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/>'
    "<d:current-user-privilege-set/></d:prop></d:propfind>"
)
CARD = "BEGIN:VCARD\r\nVERSION:3.0\r\nUID:dobavljac-1\r\nFN:Dobavljač d.o.o.\r\nEND:VCARD\r\n"


def phone_of(person, *, dav: bool) -> Client:
    secret = made()
    AppPassword.objects.create(user=person, name="Samsung SM-S926B", digest=digest(secret))
    if dav:
        token = base64.b64encode(f"{person.email}:{secret}".encode()).decode()
        return Client(HTTP_AUTHORIZATION=f"Basic {token}")
    return Client(enforce_csrf_checks=True, headers={"Authorization": f"Bearer {secret}"})


@pytest.fixture
def people():
    return [
        User.objects.create_user(f"{name}@example.com", "Kamen-Most-Rijeka-71")
        for name in ("ivo", "ana", "marko")
    ]


def test_a_phone_holds_the_mailboxs_book_over_carddav_by_the_role(people):
    ivo, ana, marko = people
    box = sharing.made(ivo, "Prodaja")
    buyer = cards.made(box.pk, person("Kupac d.o.o.", email="kupac@example.com"))
    Grant.objects.create(mailbox=box, user=ana, role="read")
    phone = phone_of(ana, dav=True)
    where = f"/dav/contacts/{ana.pk}/box-{box.pk}/"
    home = phone.generic("PROPFIND", f"/dav/contacts/{ana.pk}/", PROPS, HTTP_DEPTH="1")
    text = home.content.decode()
    assert f"<d:href>/dav/contacts/{ana.pk}/book/</d:href>" in text
    assert f"<d:href>{where}</d:href>" in text and "<d:displayname>Prodaja</d:displayname>" in text
    shown = phone.generic("PROPFIND", where, PROPS, HTTP_DEPTH="1").content.decode()
    assert "<d:read />" in shown and "<d:write />" not in shown
    assert f"<d:href>{where}{buyer.href}</d:href>" in shown
    assert "Kupac d.o.o." in phone.get(where + buyer.href).content.decode()
    made_at = where + "dobavljac.vcf"
    assert phone.put(made_at, CARD, content_type="text/vcard").status_code == 403
    assert phone.generic("DELETE", where + buyer.href).status_code == 403

    Grant.objects.filter(mailbox=box, user=ana).update(role="edit")
    assert "<d:write />" in phone.generic("PROPFIND", where, PROPS).content.decode()
    assert phone.put(made_at, CARD, content_type="text/vcard").status_code == 201
    assert Contact.objects.get(href="dobavljac.vcf").owner_id == box.pk

    stranger = phone_of(marko, dav=True)
    path = f"/dav/contacts/{marko.pk}/box-{box.pk}/"
    assert stranger.generic("PROPFIND", path, PROPS).status_code == 404


def test_the_phones_app_holds_the_mailboxs_book_by_the_role(people):
    ivo, ana, marko = people
    box = sharing.made(ivo, "Prodaja")
    buyer = cards.made(box.pk, person("Kupac d.o.o.", email="kupac@example.com"))
    Grant.objects.create(mailbox=box, user=ana, role="read")
    phone = phone_of(ana, dav=False)
    own = phone.get("/api/device/contacts").json()
    assert own["contacts"] == []
    assert own["mailboxes"] == [{"id": box.pk, "name": "Prodaja", "read_only": True}]
    boxed = phone.get(f"/api/device/contacts?box={box.pk}").json()
    assert [each["href"] for each in boxed["contacts"]] == [buyer.href]
    assert "mailboxes" not in boxed
    assert phone.get(f"/api/contacts/{buyer.pk}/photo").status_code == 404
    card = {"fields": {"given": "Dobavljač"}, "points": [], "revision": None}
    where = f"/api/device/contacts/dobavljac.vcf?box={box.pk}"
    assert phone.put(where, json.dumps(card), content_type="application/json").status_code == 403

    Grant.objects.filter(mailbox=box, user=ana).update(role="edit")
    listed = phone.get("/api/device/contacts").json()["mailboxes"]
    assert listed[0]["read_only"] is False
    made_here = phone.put(where, json.dumps(card), content_type="application/json")
    assert made_here.status_code == 201, made_here.content
    assert Contact.objects.get(href="dobavljac.vcf").owner_id == box.pk
    gone = f"/api/device/contacts/{buyer.href}?box={box.pk}&revision={buyer.revision}"
    assert phone.delete(gone).status_code == 204

    stranger = phone_of(marko, dav=False)
    assert stranger.get(f"/api/device/contacts?box={box.pk}").status_code == 404
    assert stranger.get("/api/device/contacts").json()["mailboxes"] == []
