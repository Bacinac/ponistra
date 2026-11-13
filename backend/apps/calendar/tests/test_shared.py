import base64
import json

import pytest
from django.test import Client

from apps.calendar import taking, views
from apps.mail import sharing
from apps.mail.models import Account, Grant
from apps.users.app_passwords import digest, made
from apps.users.models import AppPassword, User

from .test_views import sent

pytestmark = pytest.mark.django_db


@pytest.fixture
def people():
    return {
        name: User.objects.create_user(
            f"{name}@example.com", "Kamen-Most-Rijeka-71", first_name=name
        )
        for name in ("Ivo", "Ana", "Marko")
    }


def test_the_calendars_of_a_mailbox_are_shared_by_its_grants(client, people):
    box = sharing.made(people["Ivo"], "Prodaja")
    held = taking.own(box.pk, "Prodaja")
    Grant.objects.create(mailbox=box, user=people["Ana"], role="read")
    client.force_login(people["Ana"])

    assert client.get("/api/calendar").json()["calendars"] == []
    shown = client.get(f"/api/calendar?box={box.pk}").json()
    assert [(each["id"], each["read_only"]) for each in shown["calendars"]] == [(held.pk, True)]
    assert shown["role"] == "read"
    meeting = {"summary": "Sajam", "start": "2026-11-20T09:00", "end": "2026-11-20T17:00"}
    made = sent(client, "post", "/api/calendar/events", calendar=held.pk, **meeting)
    assert made.status_code == 403

    Grant.objects.filter(mailbox=box, user=people["Ana"]).update(role="edit")
    made = sent(client, "post", "/api/calendar/events", calendar=held.pk, **meeting)
    assert made.status_code == 201
    event = made.json()["id"]
    assert client.get(f"/api/calendar/events/{event}").json()["read_only"] is False
    listed = client.get(f"/api/calendar/events?box={box.pk}&from=2026-11-20&to=2026-11-20")
    assert [each["event"] for each in listed.json()["events"]] == [event]
    assert views.concerned(str(held.pk)) == {box.pk, people["Ivo"].pk, people["Ana"].pk}

    client.force_login(people["Marko"])
    assert client.get(f"/api/calendar?box={box.pk}").status_code == 404
    assert client.get(f"/api/calendar/events/{event}").status_code == 404


PROPS = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/>'
    "<d:current-user-privilege-set/></d:prop></d:propfind>"
)
ADDRESSES = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    "<d:prop><c:calendar-user-address-set/></d:prop></d:propfind>"
)
ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//phone//EN\r\nBEGIN:VEVENT\r\nUID:sajam-1\r\n"
    "DTSTAMP:20261112T100000Z\r\nDTSTART:20261120T080000Z\r\nDTEND:20261120T160000Z\r\n"
    "SUMMARY:Sajam\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)


def phone_of(person, *, dav: bool) -> Client:
    secret = made()
    AppPassword.objects.create(user=person, name="Samsung SM-S926B", digest=digest(secret))
    if dav:
        token = base64.b64encode(f"{person.email}:{secret}".encode()).decode()
        return Client(HTTP_AUTHORIZATION=f"Basic {token}")
    return Client(enforce_csrf_checks=True, headers={"Authorization": f"Bearer {secret}"})


@pytest.fixture
def fairs(people):
    box = sharing.made(people["Ivo"], "Prodaja")
    Account.objects.create(owner=box, address="prodaja@example.com", username="prodaja@example.com")
    Grant.objects.create(mailbox=box, user=people["Ana"], role="read")
    return box, taking.own(box.pk, "Sajmovi")


def test_a_phone_holds_the_mailboxs_calendars_over_caldav_by_the_role(people, fairs):
    box, held = fairs
    ana = people["Ana"]
    phone = phone_of(ana, dav=True)
    where = f"/dav/calendars/{ana.pk}/{held.pk}/"
    home = phone.generic("PROPFIND", f"/dav/calendars/{ana.pk}/", PROPS, HTTP_DEPTH="1")
    text = home.content.decode()
    assert f"<d:href>{where}</d:href>" in text
    assert "<d:displayname>Sajmovi (Prodaja)</d:displayname>" in text
    shown = phone.generic("PROPFIND", where, PROPS, HTTP_DEPTH="0").content.decode()
    assert "<d:read />" in shown and "<d:write />" not in shown
    assert phone.put(where + "sajam.ics", ICS, content_type="text/calendar").status_code == 403
    principal = phone.generic("PROPFIND", f"/dav/principals/{ana.pk}/", ADDRESSES)
    assert "prodaja@example.com" not in principal.content.decode()

    Grant.objects.filter(mailbox=box, user=ana).update(role="edit")
    shown = phone.generic("PROPFIND", where, PROPS, HTTP_DEPTH="0").content.decode()
    assert "<d:write />" in shown
    assert phone.put(where + "sajam.ics", ICS, content_type="text/calendar").status_code == 201
    assert held.events.get().summary == "Sajam"
    principal = phone.generic("PROPFIND", f"/dav/principals/{ana.pk}/", ADDRESSES)
    assert "mailto:prodaja@example.com" in principal.content.decode()

    marko = phone_of(people["Marko"], dav=True)
    stranger = f"/dav/calendars/{people['Marko'].pk}/{held.pk}/"
    assert marko.generic("PROPFIND", stranger, PROPS, HTTP_DEPTH="0").status_code == 404


def test_the_phones_app_holds_the_mailboxs_calendars_by_the_role(people, fairs):
    box, held = fairs
    ana = people["Ana"]
    phone = phone_of(ana, dav=False)
    own = taking.own(ana.pk, "Moj")
    listed = phone.get("/api/device/calendars").json()["calendars"]
    assert [(each["id"], each["name"], each["read_only"]) for each in listed] == [
        (held.pk, "Sajmovi (Prodaja)", True),
        (own.pk, "Moj", False),
    ]
    assert listed[0]["owner"] == box.email
    sajam = {
        "summary": "Sajam",
        "starts": 1795161600000,
        "ends": 1795190400000,
        "zone": "Europe/Zagreb",
    }
    where = f"/api/device/calendars/{held.pk}/sajam.ics"
    written = json.dumps({"revision": None, "language": "hr", "parts": [sajam]})
    assert phone.put(where, written, content_type="application/json").status_code == 403

    Grant.objects.filter(mailbox=box, user=ana).update(role="edit")
    assert phone.get("/api/device/calendars").json()["calendars"][0]["read_only"] is False
    made_here = phone.put(where, written, content_type="application/json")
    assert made_here.status_code == 201, made_here.content
    assert held.events.get().summary == "Sajam"
    read = phone.get(f"/api/device/calendars/{held.pk}").json()
    assert [each["href"] for each in read["events"]] == ["sajam.ics"]
    revision = made_here.json()["revision"]
    assert phone.delete(f"{where}?revision={revision}").status_code == 204
    assert not held.events.exists()

    marko = phone_of(people["Marko"], dav=False)
    assert marko.get(f"/api/device/calendars/{held.pk}").status_code == 404
