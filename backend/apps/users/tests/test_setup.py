import pytest
from django.conf import settings

from apps.users.models import User

pytestmark = pytest.mark.django_db

CODE = "K7QM-4XTR-9PWD-HB2C"
PASSWORD = "Kamen-Most-Rijeka-71"


@pytest.fixture(autouse=True)
def code(settings):
    settings.SETUP_CODE = CODE


def set_up(client, **data):
    data = {"code": CODE, "email": "ivo@example.com", "password": PASSWORD, **data}
    return client.post("/api/setup", data, content_type="application/json")


def test_an_installation_without_users_asks_for_its_first_administrator(client):
    assert client.get("/api/auth/session").json() == {
        "user": None,
        "passkey_due": False,
        "setup": True,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }


def test_the_code_makes_an_administrator_and_signs_them_in_to_add_a_passkey(client):
    response = set_up(client, first_name="Ivo", last_name="Bošković", code=" k7qm 4xtr 9pwd hb2c ")
    assert response.status_code == 201
    user = User.objects.get()
    me = {
        "id": user.pk,
        "email": "ivo@example.com",
        "name": "Ivo Bošković",
        "is_admin": True,
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
    assert user.is_superuser
    assert client.get("/api/auth/session").json() == {
        "user": me,
        "passkey_due": True,
        "setup": False,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }


def test_a_wrong_code_is_refused(client):
    response = set_up(client, code="K7QM-4XTR-9PWD-HB2D")
    assert (response.status_code, response.json()) == (400, {"error": "invalid_setup_code"})
    assert not User.objects.exists()


def test_a_code_outside_ascii_is_refused_like_any_wrong_code(client):
    response = set_up(client, code="Č7QM-4XTR-9PWD-HB2C")
    assert (response.status_code, response.json()) == (400, {"error": "invalid_setup_code"})
    assert not User.objects.exists()


def test_without_a_code_the_installation_is_set_up_from_the_shell(client, settings):
    settings.SETUP_CODE = ""
    response = set_up(client, code="")
    assert (response.status_code, response.json()) == (409, {"error": "no_setup_code"})


def test_once_someone_exists_the_code_opens_nothing(client):
    User.objects.create_user("ana@example.com", PASSWORD)
    response = set_up(client)
    assert (response.status_code, response.json()) == (409, {"error": "already_set_up"})
    assert client.get("/api/auth/session").json() == {
        "user": None,
        "passkey_due": False,
        "setup": False,
        "site": settings.PUBLIC_URL,
        "providers": [],
    }
    assert User.objects.count() == 1


def test_the_password_is_held_to_the_same_rules(client):
    response = set_up(client, password="kratka")
    assert (response.status_code, response.json()) == (400, {"error": "password_too_short"})
    assert not User.objects.exists()


def test_only_the_fields_of_a_person_are_taken(client):
    set_up(client, is_active=False, groups=[1])
    user = User.objects.get()
    assert user.is_active
    assert not user.groups.exists()
