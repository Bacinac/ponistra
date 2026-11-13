import pytest
from asgiref.sync import async_to_sync
from django.conf import settings
from django.test import Client

from apps.users.models import Policy, User

pytestmark = pytest.mark.django_db

PASSWORD = "Kamen-Most-Rijeka-71"


@pytest.fixture
def user():
    return User.objects.create_user("ivo@example.com", PASSWORD, first_name="Ivo")


def login(client, email, password):
    return client.post(
        "/api/auth/login", {"email": email, "password": password}, content_type="application/json"
    )


def test_anonymous_session_has_no_user_and_gets_a_csrf_cookie(client, user):
    response = client.get("/api/auth/session")
    assert response.json() == {
        "user": None,
        "passkey_due": False,
        "setup": False,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }
    assert "csrftoken" in response.cookies


JSON = "application/json"


def content(response) -> bytes:
    async def read():
        return b"".join([part async for part in response.streaming_content])

    return async_to_sync(read)()


def test_the_account_keeps_a_language_and_a_theme_for_every_device(client, user):
    assert client.patch("/api/auth/preferences", {}, content_type=JSON).status_code == 401
    client.force_login(user)
    me = client.get("/api/auth/session").json()["user"]
    assert (me["language"], me["theme"]) == ("", "")
    sent = {"language": "en", "theme": "dark"}
    changed = client.patch("/api/auth/preferences", sent, content_type=JSON)
    assert changed.json()["user"]["language"] == "en"
    other = Client()
    other.force_login(user)
    me = other.get("/api/auth/session").json()["user"]
    assert (me["language"], me["theme"]) == ("en", "dark")
    other.patch("/api/auth/preferences", {"theme": "light"}, content_type=JSON)
    me = client.get("/api/auth/session").json()["user"]
    assert (me["language"], me["theme"]) == ("en", "light")


def test_the_account_keeps_the_themes_of_projects_and_meetings_for_every_device(client, user):
    client.force_login(user)
    me = client.get("/api/auth/session").json()["user"]
    assert (me["projects_theme"], me["meetings_theme"]) == ("", "")
    sent = {"projects_theme": "dark", "meetings_theme": "light"}
    client.patch("/api/auth/preferences", sent, content_type=JSON)
    other = Client()
    other.force_login(user)
    me = other.get("/api/auth/session").json()["user"]
    assert (me["theme"], me["projects_theme"], me["meetings_theme"]) == ("", "dark", "light")
    other.patch("/api/auth/preferences", {"projects_theme": "ponistra"}, content_type=JSON)
    assert client.get("/api/auth/session").json()["user"]["projects_theme"] == "ponistra"


def test_the_account_keeps_how_it_signs_in_for_every_device(client, user):
    client.force_login(user)
    assert client.get("/api/auth/session").json()["user"]["sign_in"] == ""
    changed = client.patch("/api/auth/preferences", {"sign_in": "password"}, content_type=JSON)
    assert changed.json()["user"]["sign_in"] == "password"


def test_the_account_keeps_what_a_call_does_with_the_camera_and_sound(client, user):
    client.force_login(user)
    assert client.get("/api/auth/session").json()["user"]["call"] == {}
    sent = {"call": {"background": "soft", "framing": True}}
    client.patch("/api/auth/preferences", sent, content_type=JSON)
    other = Client()
    other.force_login(user)
    assert other.get("/api/auth/session").json()["user"]["call"] == sent["call"]
    other.patch("/api/auth/preferences", {"call": {"noise": False}}, content_type=JSON)
    assert client.get("/api/auth/session").json()["user"]["call"] == {"noise": False}


def test_the_account_keeps_a_picture_of_its_own_behind_the_user(client, user):
    assert client.get("/api/auth/backdrop").status_code == 401
    client.force_login(user)
    assert client.get("/api/auth/backdrop").status_code == 404
    picture = b"\xff\xd8\xff\xe0" + b"j" * 64
    put = client.put("/api/auth/backdrop", picture, content_type="image/jpeg")
    assert put.status_code == 200
    assert put.json()["user"]["backdrop"] is not None
    client.patch("/api/auth/preferences", {"call": {"background": "own"}}, content_type=JSON)
    shown = client.get("/api/auth/backdrop")
    assert (shown["Content-Type"], content(shown)) == ("image/jpeg", picture)
    gone = client.delete("/api/auth/backdrop").json()["user"]
    assert (gone["backdrop"], gone["call"]["background"]) == (None, "none")
    assert client.get("/api/auth/backdrop").status_code == 404


def test_a_backdrop_is_a_picture(client, user):
    client.force_login(user)
    refused = client.put("/api/auth/backdrop", b"%PDF-1.7\n%%EOF\n", content_type="image/jpeg")
    assert (refused.status_code, refused.json()["error"]) == (415, "not_a_photo")
    assert User.objects.get().backdrop is None


def test_a_choice_of_how_to_sign_in_refuses_nothing(client, user):
    user.sign_in = "passkey"
    user.save()
    Policy.objects.create(passkeys=Policy.Passkeys.NOBODY)
    assert login(client, user.email, PASSWORD).status_code == 200


@pytest.mark.parametrize(
    "given",
    [
        {"language": "de"},
        {"theme": "blue"},
        {"theme": 1},
        {"theme": "ponistra"},
        {"projects_theme": "system"},
        {"meetings_theme": "blue"},
        {"sign_in": "sms"},
        {"call": {"background": "beach"}},
        {"call": {"framing": 1}},
        {"call": {"noise": "yes"}},
        {"call": {"zoom": True}},
        {"call": ["background"]},
    ],
)
def test_a_preference_outside_what_the_interface_offers_is_refused(client, user, given):
    client.force_login(user)
    assert client.patch("/api/auth/preferences", given, content_type=JSON).status_code == 400


def test_login_starts_a_session_that_adds_a_passkey_first(client, user):
    response = login(client, "Ivo@Example.com ", PASSWORD)
    me = {
        "id": user.pk,
        "email": "ivo@example.com",
        "name": "Ivo",
        "is_admin": False,
        "visitor": False,
        "workspace": None,
        "language": "",
        "theme": "",
        "projects_theme": "",
        "meetings_theme": "",
        "sign_in": "",
        "call": {},
        "backdrop": None,
    }
    assert response.json() == {
        "user": me,
        "passkey_due": True,
        "setup": False,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }
    assert client.get("/api/auth/session").json()["user"]["email"] == "ivo@example.com"


def test_wrong_password_is_refused(client, user):
    response = login(client, "ivo@example.com", "wrong")
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_credentials"}
    assert client.get("/api/auth/session").json() == {
        "user": None,
        "passkey_due": False,
        "setup": False,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }


def test_malformed_body_is_refused(client):
    response = client.post("/api/auth/login", "{", content_type="application/json")
    assert response.status_code == 400


def test_login_requires_the_csrf_token(user):
    client = Client(enforce_csrf_checks=True)
    assert login(client, "ivo@example.com", PASSWORD).status_code == 403
    client.get("/api/auth/session")
    response = client.post(
        "/api/auth/login",
        {"email": "ivo@example.com", "password": PASSWORD},
        content_type="application/json",
        headers={"X-CSRFToken": client.cookies["csrftoken"].value},
    )
    assert response.status_code == 200


def test_five_failures_lock_the_account_out_for_that_address(client, user):
    for _ in range(5):
        login(client, "ivo@example.com", "wrong")
    response = login(client, "ivo@example.com", PASSWORD)
    assert response.status_code == 429
    assert response.json() == {"error": "locked_out"}
    elsewhere = login(Client(REMOTE_ADDR="192.0.2.7"), "ivo@example.com", PASSWORD)
    assert elsewhere.status_code == 200


def test_the_tunnel_client_address_counts_not_the_proxy(user):
    def attempt(address, password):
        return login(Client(HTTP_CF_CONNECTING_IP=address), "ivo@example.com", password)

    for n in range(5):
        attempt("198.51.100.9", f"wrong{n}")
    assert attempt("198.51.100.9", PASSWORD).status_code == 429
    assert attempt("198.51.100.10", PASSWORD).status_code == 200


def test_logout_ends_the_session(client, user):
    login(client, "ivo@example.com", PASSWORD)
    assert client.post("/api/auth/logout").json() == {
        "user": None,
        "passkey_due": False,
        "setup": False,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }
    assert client.get("/api/auth/session").json() == {
        "user": None,
        "passkey_due": False,
        "setup": False,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }


def test_email_is_stored_lowercase():
    assert User.objects.create_user(" Ana@Example.COM", PASSWORD).email == "ana@example.com"
