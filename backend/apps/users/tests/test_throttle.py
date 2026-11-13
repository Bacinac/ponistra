import pytest
from django.test import Client

from apps.users.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "Kamen-Most-Rijeka-71"


def login(address, email, password):
    return Client(REMOTE_ADDR=address).post(
        "/api/auth/login", {"email": email, "password": password}, content_type="application/json"
    )


@pytest.fixture
def ivo():
    return User.objects.create_user("ivo@example.com", PASSWORD)


def test_one_address_guessing_across_many_accounts_is_held(ivo):
    for n in range(29):
        assert login("198.51.100.9", f"someone{n}@example.com", "wrong").status_code == 400
    login("198.51.100.9", "someone29@example.com", "wrong")
    held = login("198.51.100.9", "ivo@example.com", PASSWORD)
    assert (held.status_code, held.json()) == (429, {"error": "locked_out"})
    assert login("198.51.100.10", "ivo@example.com", PASSWORD).status_code == 200


def test_many_people_signing_in_from_one_address_are_never_held():
    for n in range(40):
        User.objects.create_user(f"colleague{n}@example.com", PASSWORD)
        assert login("198.51.100.9", f"colleague{n}@example.com", PASSWORD).status_code == 200


def test_one_account_guessed_from_many_addresses_is_held_only_where_it_never_signed_in(ivo):
    assert login("203.0.113.1", "ivo@example.com", PASSWORD).status_code == 200
    for n in range(29):
        assert login(f"198.51.100.{n + 1}", "ivo@example.com", "wrong").status_code == 400
    login("198.51.100.30", "ivo@example.com", "wrong")
    held = login("198.51.100.200", "ivo@example.com", PASSWORD)
    assert (held.status_code, held.json()) == (429, {"error": "locked_out"})
    assert login("203.0.113.1", "ivo@example.com", PASSWORD).status_code == 200


def test_signing_in_to_an_own_account_does_not_forgive_the_guessing_at_others(ivo):
    for n in range(29):
        login("198.51.100.9", f"someone{n}@example.com", "wrong")
    assert login("198.51.100.9", "ivo@example.com", PASSWORD).status_code == 200
    login("198.51.100.9", "someone-else@example.com", "wrong")
    assert login("198.51.100.9", "ivo@example.com", PASSWORD).status_code == 429
