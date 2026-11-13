from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.test import Client
from django.utils import timezone

from apps.users.models import Policy, Session, User
from apps.users.tests.test_passkeys import Device, add, post, sign_in

pytestmark = pytest.mark.django_db

JSON = "application/json"
PASSWORD = "Kamen-Most-Rijeka-71"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0"


def signed_in(email: str = "ana@example.com", agent: str = FIREFOX, address: str = "203.0.113.7"):
    browser = Client(headers={"User-Agent": agent, "X-Forwarded-For": address})
    answer = browser.post("/api/auth/login", {"email": email, "password": PASSWORD}, JSON)
    assert answer.status_code == 200, answer.json()
    return browser


@pytest.fixture(autouse=True)
def passwords():
    Policy.objects.create(passkeys=Policy.Passkeys.NOBODY)


@pytest.fixture
def ana():
    return User.objects.create_user("ana@example.com", PASSWORD)


@pytest.fixture
def admin():
    User.objects.create_superuser("ivo@example.com", PASSWORD)
    return signed_in("ivo@example.com")


def test_a_user_sees_the_browsers_they_are_signed_in_on_and_signs_one_out(ana):
    laptop = signed_in()
    phone = signed_in(agent="Mozilla/5.0 (Linux; Android 16) Chrome/150.0 Mobile")
    listed = laptop.get("/api/sessions").json()["sessions"]
    assert [(each["agent"][:40], each["address"], each["current"]) for each in listed] == [
        ("Mozilla/5.0 (Linux; Android 16) Chrome/1", "203.0.113.7", False),
        (FIREFOX[:40], "203.0.113.7", True),
    ]
    assert all(len(each["id"]) == 16 and each["signed_in_at"] for each in listed)
    assert laptop.delete(f"/api/sessions/{listed[0]['id']}").status_code == 204
    assert phone.get("/api/nodes").status_code == 401
    assert [each["current"] for each in laptop.get("/api/sessions").json()["sessions"]] == [True]
    assert laptop.delete(f"/api/sessions/{listed[0]['id']}").status_code == 404


def test_a_sign_in_ends_when_it_has_lasted_however_busy_its_browser_kept_it(ana, monkeypatch):
    from apps.users import sessions

    laptop = signed_in()
    signed = Session.objects.get().signed_in_at
    start = timezone.now()
    for days in (13, 26):
        monkeypatch.setattr(timezone, "now", lambda days=days: start + timedelta(days=days))
        assert laptop.get("/api/nodes").status_code == 200
    ends = signed + sessions.LASTS
    assert ends - timedelta(seconds=1) < Session.objects.get().expire_date <= ends
    monkeypatch.setattr(timezone, "now", lambda: signed + sessions.LASTS + timedelta(seconds=1))
    assert laptop.get("/api/nodes").status_code == 401


def test_a_session_opened_for_the_printer_is_not_listed(ana):
    from apps.users import sessions

    laptop = signed_in()
    key = sessions.opened(ana, 60)
    assert Session.objects.get(session_key=key).user == ana
    assert len(laptop.get("/api/sessions").json()["sessions"]) == 1


def test_an_administrator_signs_a_user_out_of_one_browser_or_all(ana, admin):
    laptop, phone = signed_in(), signed_in()
    listed = admin.get(f"/api/users/{ana.pk}/sessions").json()["sessions"]
    assert len(listed) == 2
    assert admin.delete(f"/api/users/{ana.pk}/sessions/{listed[1]['id']}").status_code == 204
    assert laptop.get("/api/nodes").status_code == 401
    assert phone.get("/api/nodes").status_code == 200
    assert admin.delete(f"/api/users/{ana.pk}/sessions").status_code == 204
    assert phone.get("/api/nodes").status_code == 401
    assert signed_in().get(f"/api/users/{ana.pk}/sessions").json() == {"error": "forbidden"}


def test_a_policy_holds_administrators_to_passkeys_from_their_next_sign_in(ana, admin):
    assert admin.get("/api/policy").json() == {"passkeys": "nobody", "outside": "everyone"}
    assert admin.patch("/api/policy", {"passkeys": "sometimes"}, JSON).status_code == 400
    assert admin.patch("/api/policy", {"passkeys": "administrators"}, JSON).json() == {
        "passkeys": "administrators",
        "outside": "everyone",
    }
    assert admin.get("/api/nodes").status_code == 200
    assert signed_in().get("/api/auth/session").json()["passkey_due"] is False
    assert signed_in().patch("/api/policy", {"passkeys": "nobody"}, JSON).status_code == 403

    due = signed_in("ivo@example.com")
    assert due.get("/api/auth/session").json()["passkey_due"] is True
    assert due.get("/api/nodes").json() == {"error": "passkey_required"}
    device = Device()
    assert add(due, device).status_code == 201
    assert due.get("/api/auth/session").json()["passkey_due"] is False
    assert due.get("/api/nodes").status_code == 200

    refused = Client().post(
        "/api/auth/login", {"email": "ivo@example.com", "password": PASSWORD}, JSON
    )
    assert (refused.status_code, refused.json()) == (403, {"error": "passkey_required"})
    keyed = Client()
    assert sign_in(keyed, device).status_code == 200
    only = keyed.get("/api/passkeys").json()["passkeys"][0]["id"]
    assert keyed.delete(f"/api/passkeys/{only}").json() == {"error": "last_passkey"}


def test_a_user_who_owes_a_passkey_is_kept_out_of_live_documents_too(ana, admin):
    from apps.collab.server import signed_in as websocket_user

    admin.patch("/api/policy", {"passkeys": "everyone"}, JSON)
    due = signed_in()
    key = due.cookies["sessionid"].value
    scope = {"headers": [(b"cookie", f"sessionid={key}".encode())]}
    assert async_to_sync(websocket_user)(scope) is None
    add(due, Device())
    assert async_to_sync(websocket_user)(scope).user == ana.pk
    post(due, "/api/auth/logout")


def test_a_browser_marks_itself_to_work_without_the_network_and_its_list_shows_it(ana):
    laptop = signed_in()
    phone = signed_in(agent="Mozilla/5.0 (Linux; Android 16) Chrome/150.0 Mobile")
    assert phone.patch("/api/sessions", {"offline": True}, JSON).status_code == 204
    listed = laptop.get("/api/sessions").json()["sessions"]
    assert [(each["current"], each["offline"]) for each in listed] == [(False, True), (True, False)]
    assert phone.patch("/api/sessions", {"offline": "yes"}, JSON).status_code == 400
    assert phone.patch("/api/sessions", {"offline": False}, JSON).status_code == 204
    assert not Session.objects.filter(offline=True).exists()
