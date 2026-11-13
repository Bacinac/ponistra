import uuid

import pytest
from django.conf import settings
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.push.models import Notice
from apps.push.tests.test_push import subscribed
from apps.users import sessions
from apps.users.models import Policy, User
from apps.users.tests.test_passkeys import Device, add, post

pytestmark = pytest.mark.django_db

JSON = "application/json"
PASSWORD = "Kamen-Most-Rijeka-71"
GUARDED = [
    ("post", "/api/auth/password"),
    ("post", "/api/passkeys/options"),
    ("post", "/api/passkeys"),
    ("delete", "/api/passkeys/1"),
    ("post", "/api/app-passwords"),
    ("post", "/api/device/pairing"),
    ("post", "/api/agents/consent"),
    ("post", "/api/users"),
    ("patch", "/api/users/1"),
    ("patch", "/api/policy"),
    ("put", "/api/vault/recovery"),
    ("delete", "/api/vault/recovery"),
    ("post", "/api/users/1/vault"),
    ("patch", "/api/backups/offsite"),
    ("post", "/api/backups/offsite/kit"),
    ("patch", "/api/vault"),
    ("delete", "/api/vault"),
    ("post", "/api/vault/unlocks"),
    ("delete", "/api/vault/unlocks/1"),
    ("post", f"/api/vault/collections/{uuid.UUID(int=1)}/exported"),
]


def stale(client) -> None:
    session = client.session
    session[sessions.CONFIRMED] = (timezone.now() - sessions.CONFIRMED_FOR).isoformat()
    session.save()


def made(client):
    return client.post("/api/app-passwords", {"name": "Telefon"}, JSON)


def confirm(client, device):
    options = post(client, "/api/auth/confirm/options").json()
    return post(client, "/api/auth/confirm", {"credential": device.get(options)})


@pytest.mark.parametrize(("method", "path"), GUARDED)
def test_what_an_open_session_must_not_do_alone_waits_for_a_confirmation(api, method, path):
    stale(api)
    refused = getattr(api, method)(path, {}, JSON)
    assert (refused.status_code, refused.json()) == (403, {"error": "confirm_required"})


def test_a_sign_in_is_a_confirmation(api):
    assert made(api).status_code == 201


def test_the_rest_of_a_guarded_view_needs_none(api):
    stale(api)
    assert api.get("/api/app-passwords").status_code == 200


def test_the_password_confirms(api):
    stale(api)
    assert api.get("/api/auth/confirm").json() == {
        "passkey": False,
        "password": True,
        "providers": [],
    }
    wrong = api.post("/api/auth/confirm", {"password": "x"}, JSON)
    assert (wrong.status_code, wrong.json()) == (400, {"error": "invalid_credentials"})
    assert made(api).status_code == 403
    assert api.post("/api/auth/confirm", {"password": PASSWORD}, JSON).status_code == 204
    assert made(api).status_code == 201


def test_a_request_begun_before_the_confirmation_does_not_take_it_back(api):
    stale(api)
    request = RequestFactory().get("/api/workspace/limits")
    request.COOKIES[settings.SESSION_COOKIE_NAME] = api.session.session_key

    def slow(request):
        assert request.user.is_authenticated
        assert api.post("/api/auth/confirm", {"password": PASSWORD}, JSON).status_code == 204
        return HttpResponse()

    SessionMiddleware(AuthenticationMiddleware(sessions.seen(slow)))(request)
    assert made(api).status_code == 201


def test_a_session_saves_only_what_its_request_changed(api):
    key = api.session.session_key
    early, late = sessions.SessionStore(key), sessions.SessionStore(key)
    early["asked"], early["kept"] = "challenge", "a"
    early.save()
    late.pop("asked")
    late["kept"] = "b"
    early["seen"] = "now"
    early.save()
    late.save()
    found = sessions.SessionStore(key).load()
    assert (found.get("asked"), found["kept"], found["seen"]) == (None, "b", "now")


def test_a_passkey_of_the_users_own_confirms(api):
    device = Device()
    assert add(api, device).status_code == 201
    stale(api)
    assert api.get("/api/auth/confirm").json() == {
        "passkey": True,
        "password": False,
        "providers": [],
    }
    refused = api.post("/api/auth/confirm", {"password": PASSWORD}, JSON)
    assert (refused.status_code, refused.json()) == (403, {"error": "passkey_required"})
    options = post(api, "/api/auth/confirm/options").json()
    assert [each["id"] for each in options["allowCredentials"]] == [device.answer({})["id"]]
    assert confirm(api, device).status_code == 204
    assert made(api).status_code == 201


def test_a_colleagues_passkey_does_not(api):
    device = Device()
    assert add(api, device).status_code == 201
    other = Client()
    other.force_login(User.objects.create_user("ana@example.com", PASSWORD))
    stale(other)
    refused = confirm(other, device)
    assert (refused.status_code, refused.json()) == (400, {"error": "invalid_passkey"})
    assert made(other).status_code == 403


def test_the_password_confirms_beside_a_passkey_where_the_policy_allows_it(api):
    Policy.objects.create(passkeys=Policy.Passkeys.NOBODY)
    assert add(api, Device()).status_code == 201
    stale(api)
    assert api.get("/api/auth/confirm").json() == {
        "passkey": True,
        "password": True,
        "providers": [],
    }
    assert api.post("/api/auth/confirm", {"password": PASSWORD}, JSON).status_code == 204


def test_a_sign_in_a_passkey_and_an_app_password_are_told_to_the_users_browsers(api):
    subscribed(api.user)
    api.logout()
    api.post("/api/auth/login", {"email": "ivo@example.com", "password": PASSWORD}, JSON)
    add(api, Device(), name="Laptop")
    made(api)
    told = Notice.objects.filter(user=api.user, kind=Notice.Kind.SECURITY)
    assert [(each.data["event"], each.data.get("name")) for each in told] == [
        ("sign_in", None),
        ("passkey", "Laptop"),
        ("app_password", "Telefon"),
    ]
