import base64
import time

import pytest
from django.test import Client

from apps.journal.models import Entry
from apps.users import factors
from apps.users.models import Authenticator, Policy, User
from apps.users.tests.test_passkeys import Device, add, post, sign_in

pytestmark = pytest.mark.django_db

JSON = "application/json"
PASSWORD = "Kamen-Most-Rijeka-71"


@pytest.fixture(autouse=True)
def passwords():
    Policy.objects.create(passkeys=Policy.Passkeys.NOBODY)


@pytest.fixture
def ana():
    return User.objects.create_user("ana@example.com", PASSWORD)


def login(browser, email="ana@example.com"):
    return browser.post("/api/auth/login", {"email": email, "password": PASSWORD}, JSON)


def signed_in(email="ana@example.com"):
    browser = Client()
    assert login(browser, email).json()["user"]["email"] == email
    return browser


def code(secret: str, ahead: int = 0) -> str:
    return factors.code_at(base64.b32decode(secret), int(time.time()) // factors.STEP + ahead)


def enrolled(browser) -> str:
    made = browser.post("/api/authenticator", {}, JSON)
    assert made.status_code == 201
    secret = made.json()["secret"]
    assert made.json()["uri"].startswith("otpauth://totp/Ponistra%3Aana%40example.com?secret=")
    confirmed = browser.post("/api/authenticator/confirm", {"code": code(secret)}, JSON)
    assert confirmed.json()["authenticator"] is True
    return secret


def test_the_sign_in_page_offers_passkeys_only_while_the_policy_does(api):
    device = Device()
    assert add(api, device).status_code == 201
    api.logout()
    assert api.get("/api/auth/session").json()["passkeys"] is True
    Policy.objects.update(passkeys=Policy.Passkeys.OFF)
    assert api.get("/api/auth/session").json()["passkeys"] is False
    refused = post(api, "/api/auth/passkey/options")
    assert (refused.status_code, refused.json()) == (403, {"error": "passkeys_off"})
    Policy.objects.update(passkeys=Policy.Passkeys.NOBODY)
    assert sign_in(api, device).status_code == 200


def test_a_passkey_answers_whichever_of_the_pages_options_the_person_used(api):
    device = Device()
    assert add(api, device).status_code == 201
    api.logout()
    listed = post(api, "/api/auth/passkey/options").json()
    post(api, "/api/auth/passkey/options")
    answered = post(api, "/api/auth/passkey", {"credential": device.get(listed)})
    assert answered.json()["user"]["email"] == "ivo@example.com"


def test_an_authenticator_app_asks_for_its_code_after_the_password(ana):
    secret = enrolled(signed_in())
    assert Entry.objects.filter(kind=Entry.Kind.AUTHENTICATOR_ADDED).count() == 1
    browser = Client()
    waiting = login(browser).json()
    assert (waiting["user"], waiting["second_factor"]) == (None, {"code": True, "passkey": False})
    assert browser.get("/api/nodes").status_code == 401
    wrong = browser.post("/api/auth/second", {"code": "000000"}, JSON)
    assert (wrong.status_code, wrong.json()) == (400, {"error": "invalid_code"})
    signed = browser.post("/api/auth/second", {"code": code(secret, 1)}, JSON).json()
    assert (signed["user"]["email"], signed["second_factor"], signed["due"]) == (
        "ana@example.com",
        None,
        None,
    )
    again = Client()
    login(again)
    replayed = again.post("/api/auth/second", {"code": code(secret, 1)}, JSON)
    assert replayed.json() == {"error": "invalid_code"}


def test_a_few_wrong_codes_ask_for_the_password_again(ana):
    enrolled(signed_in())
    browser = Client()
    login(browser)
    for _ in range(factors.TRIES):
        browser.post("/api/auth/second", {"code": "000000"}, JSON)
    assert browser.get("/api/auth/session").json()["second_factor"] is None
    gone = browser.post("/api/auth/second", {"code": "000000"}, JSON)
    assert gone.json() == {"error": "no_pending_sign_in"}
    assert Entry.objects.filter(kind=Entry.Kind.SIGN_IN_FAILED).count() == factors.TRIES


def test_the_policy_holds_everyone_to_a_second_factor(ana):
    Policy.objects.update(second_factor=True)
    owing = signed_in()
    assert owing.get("/api/auth/session").json()["due"] == "factor"
    assert owing.get("/api/nodes").json() == {"error": "factor_required"}
    enrolled(owing)
    assert owing.get("/api/auth/session").json()["due"] is None
    assert owing.get("/api/nodes").status_code == 200
    kept = owing.delete("/api/authenticator")
    assert (kept.status_code, kept.json()) == (400, {"error": "last_factor"})


def test_a_passkey_is_the_second_factor_while_passkeys_are_offered(api):
    device = Device()
    assert add(api, device).status_code == 201
    Policy.objects.update(second_factor=True)
    browser = Client()
    waiting = login(browser, "ivo@example.com").json()
    assert waiting["second_factor"] == {"code": False, "passkey": True}
    options = post(browser, "/api/auth/second/options").json()
    assert [each["id"] for each in options["allowCredentials"]] == [device.answer({})["id"]]
    signed = post(browser, "/api/auth/second", {"credential": device.get(options)}).json()
    assert signed["user"]["email"] == "ivo@example.com"
    only = browser.get("/api/passkeys").json()["passkeys"][0]["id"]
    assert browser.delete(f"/api/passkeys/{only}").json() == {"error": "last_passkey"}
    Policy.objects.update(passkeys=Policy.Passkeys.OFF)
    assert signed_in("ivo@example.com").get("/api/auth/session").json()["due"] == "factor"


def test_the_password_confirms_with_the_code_beside_it(ana):
    browser = signed_in()
    secret = enrolled(browser)
    session = browser.session
    session.pop("confirmed_at")
    session.save()
    assert browser.get("/api/auth/confirm").json()["code"] is True
    alone = browser.post("/api/auth/confirm", {"password": PASSWORD}, JSON)
    assert alone.json() == {"error": "invalid_code"}
    both = {"password": PASSWORD, "code": code(secret, 1)}
    assert browser.post("/api/auth/confirm", both, JSON).status_code == 204


def test_a_password_an_administrator_hands_out_drops_the_lost_phones_app(ana):
    enrolled(signed_in())
    User.objects.create_superuser("ivo@example.com", PASSWORD)
    admin = signed_in("ivo@example.com")
    handed = admin.patch(f"/api/users/{ana.pk}", {"password": "Novi-Kamen-Most-72"}, JSON)
    assert handed.status_code == 200
    assert not Authenticator.objects.exists()


def test_where_the_second_step_is_held_a_handed_password_drops_the_lost_passkeys(ana):
    browser = signed_in()
    assert add(browser, Device()).status_code == 201
    User.objects.create_superuser("ivo@example.com", PASSWORD)
    admin = signed_in("ivo@example.com")
    Policy.objects.update(second_factor=True)
    handed = admin.patch(f"/api/users/{ana.pk}", {"password": "Novi-Kamen-Most-72"}, JSON)
    assert handed.status_code == 200
    assert not ana.passkeys.exists()
