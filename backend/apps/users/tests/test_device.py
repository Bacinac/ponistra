from datetime import timedelta

import pytest
from django.test import Client

from apps.users import app_passwords
from apps.users.app_passwords import digest, made
from apps.users.models import AppPassword, User

pytestmark = pytest.mark.django_db

JSON = "application/json"


@pytest.fixture
def phone():
    owner = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    owner.first_name, owner.last_name = "Ana", "Horvat"
    owner.save()
    secret = made()
    AppPassword.objects.create(user=owner, name="Android", digest=digest(secret))
    return Client(enforce_csrf_checks=True, headers={"Authorization": f"Bearer {secret}"})


def test_the_phones_app_signs_in_with_its_app_password_and_names_the_phone(phone):
    assert phone.get("/api/device").json() == {
        "email": "ana@example.com",
        "name": "Ana Horvat",
        "device": "Android",
    }
    renamed = phone.patch("/api/device", {"name": "Samsung SM-S921B"}, JSON)
    assert renamed.status_code == 200 and renamed.json()["device"] == "Samsung SM-S921B"
    assert AppPassword.objects.get().used_at is not None
    assert phone.patch("/api/device", {"name": " "}, JSON).status_code == 400


def test_signing_out_ends_the_password_and_nothing_else_takes_it(phone):
    assert phone.get("/api/app-passwords").status_code == 401
    assert phone.delete("/api/device").status_code == 204
    assert not AppPassword.objects.exists()
    assert phone.get("/api/device").json() == {"error": "not_signed_in"}
    stranger = Client(headers={"Authorization": "Bearer abcd-efgh-jkmn-pqrs"})
    assert stranger.get("/api/device").status_code == 401


def test_an_inactive_user_s_phone_is_signed_out(phone):
    User.objects.update(is_active=False)
    assert phone.get("/api/device").status_code == 401


def test_a_browser_keeps_its_csrf_check_and_has_no_device():
    browser = Client(enforce_csrf_checks=True)
    browser.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71"))
    assert browser.patch("/api/device", {"name": "Laptop"}, JSON).status_code == 403
    assert browser.get("/api/device").json() == {"error": "app_password_required"}


@pytest.fixture
def browser():
    browser = Client()
    browser.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71"))
    return browser


def claimed(code):
    return Client(enforce_csrf_checks=True).post("/api/device/claim", {"code": code}, JSON)


def test_a_pairing_code_tells_the_phone_its_password_once(browser):
    made = browser.post("/api/device/pairing")
    assert made.status_code == 201 and made.json()["name"] == "Android"
    code = made.json()["code"]
    assert Client(headers={"Authorization": f"Bearer {code}"}).get("/api/device").status_code == 401
    given = claimed(code)
    assert given.status_code == 201
    phone = Client(headers={"Authorization": f"Bearer {given.json()['password']}"})
    assert phone.get("/api/device").json()["email"] == "ana@example.com"
    assert browser.get("/api/app-passwords").json()["app_passwords"][0]["used_at"]
    assert claimed(code).json() == {"error": "invalid_code"}


def test_a_pairing_code_lapses_and_cannot_be_forged(browser, monkeypatch):
    code = browser.post("/api/device/pairing").json()["code"]
    pk = code.split(":")[0]
    assert claimed(f"{int(pk) + 1}:{code.split(':', 1)[1]}").json() == {"error": "invalid_code"}
    monkeypatch.setattr(app_passwords, "PAIRING_AGE", timedelta(seconds=-1))
    assert claimed(code).json() == {"error": "invalid_code"}
    monkeypatch.undo()
    User.objects.update(is_active=False)
    assert claimed(code).json() == {"error": "invalid_code"}
    assert Client().post("/api/device/pairing").status_code == 401
