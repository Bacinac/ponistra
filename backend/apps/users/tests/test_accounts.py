from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import Client

from apps.access.models import Grant, Role
from apps.documents.models import Node
from apps.users.models import Passkey, Policy, User

pytestmark = pytest.mark.django_db

JSON = "application/json"
PASSWORD = "Kamen-Most-Rijeka-71"


@pytest.fixture
def admin(client):
    client.user = User.objects.create_superuser("ivo@example.com", PASSWORD)
    client.force_login(client.user)
    return client


def passkey_of(user):
    return Passkey.objects.create(user=user, credential=b"made", public_key=b"key", name="Mobitel")


def signing_in(email, password):
    return Client().post(
        "/api/auth/login", {"email": email, "password": password}, content_type=JSON
    )


def test_a_lost_device_comes_back_through_a_password_an_administrator_sets(admin):
    Policy.objects.create(passkeys=Policy.Passkeys.EVERYONE)
    ana = User.objects.create_user("ana@example.com", PASSWORD)
    passkey_of(ana)
    assert signing_in(ana.email, PASSWORD).json() == {"error": "passkey_required"}

    given = "Novi-Most-Rijeka-72"
    admin.patch(f"/api/users/{ana.pk}", {"password": given}, content_type=JSON)
    assert not ana.passkeys.exists()
    assert signing_in(ana.email, given).json()["passkey_due"] is True


def test_a_password_set_keeps_the_passkeys_where_the_policy_holds_nobody_to_them(admin):
    Policy.objects.create(passkeys=Policy.Passkeys.NOBODY)
    ana = User.objects.create_user("ana@example.com", PASSWORD)
    passkey_of(ana)
    admin.patch(f"/api/users/{ana.pk}", {"password": "Novi-Most-Rijeka-72"}, content_type=JSON)
    assert ana.passkeys.exists()


def test_an_administrator_setting_their_own_password_keeps_their_passkeys(admin):
    Policy.objects.create(passkeys=Policy.Passkeys.EVERYONE)
    passkey_of(admin.user)
    admin.patch(
        f"/api/users/{admin.user.pk}", {"password": "Novi-Most-Rijeka-72"}, content_type=JSON
    )
    assert admin.user.passkeys.exists()


def test_the_access_command_lets_a_lone_administrator_back_in(admin):
    Policy.objects.create(passkeys=Policy.Passkeys.EVERYONE)
    passkey_of(admin.user)
    printed = StringIO()
    call_command("access", " IVO@example.com", stdout=printed)
    assert not admin.user.passkeys.exists()
    assert admin.get("/api/auth/session").json()["user"] is None
    assert signing_in(admin.user.email, printed.getvalue().strip()).json()["passkey_due"] is True


@pytest.mark.parametrize(
    ("email", "why"),
    [("nitko@example.com", "no account"), ("ana@example.com", "deactivated")],
)
def test_the_access_command_says_why_it_cannot(email, why):
    User.objects.create_user("ana@example.com", PASSWORD, is_active=False)
    with pytest.raises(CommandError, match=why):
        call_command("access", email)


def test_only_an_administrator_manages_accounts(api):
    assert api.get("/api/users").status_code == 403
    assert api.post("/api/groups", {"name": "Ured"}, content_type=JSON).status_code == 403


def test_an_administrator_creates_an_account_that_signs_in(admin):
    office = admin.post("/api/groups", {"name": "Ured"}, content_type=JSON).json()
    fields = {
        "email": " Ana@Example.com",
        "first_name": "Ana",
        "last_name": "Kovač",
        "password": PASSWORD,
        "is_admin": False,
        "groups": [office["id"]],
    }
    created = admin.post("/api/users", fields, content_type=JSON).json()
    assert (created["email"], created["name"], created["groups"]) == (
        "ana@example.com",
        "Ana Kovač",
        [office["id"]],
    )
    signed_in = Client().post(
        "/api/auth/login", {"email": "ana@example.com", "password": PASSWORD}, content_type=JSON
    )
    assert signed_in.status_code == 200
    listed = admin.get("/api/users").json()
    assert [user["email"] for user in listed["users"]] == ["ivo@example.com", "ana@example.com"]
    assert listed["groups"] == [office]


@pytest.mark.parametrize(
    "fields, error",
    [
        ({"email": "ivo@example.com", "password": PASSWORD}, "email_taken"),
        ({"email": "ana", "password": PASSWORD}, "invalid_email"),
        ({"email": "ana@example.com", "password": "kratka"}, "password_too_short"),
        ({"email": "ana@example.com", "password": PASSWORD, "groups": [999]}, "invalid_groups"),
        ({"email": "ana@example.com"}, "invalid_password"),
    ],
)
def test_an_account_needs_a_free_address_and_a_good_password(admin, fields, error):
    assert admin.post("/api/users", fields, content_type=JSON).json() == {"error": error}


def test_an_administrator_neither_deactivates_nor_demotes_themselves(admin):
    me = f"/api/users/{admin.user.pk}"
    for fields in ({"is_active": False}, {"is_admin": False}):
        assert admin.patch(me, fields, content_type=JSON).json() == {"error": "self"}
    ana = User.objects.create_user("ana@example.com", PASSWORD)
    changed = admin.patch(f"/api/users/{ana.pk}", {"is_active": False, "is_admin": True}, JSON)
    assert (changed.json()["is_active"], changed.json()["is_admin"]) == (False, True)


def test_a_group_that_alone_owns_a_top_level_node_stays(admin):
    office = Group.objects.create(name="Ured")
    folder = Node.objects.create(kind=Node.Kind.FOLDER, title="Ured")
    grant = Grant.objects.create(node=folder, group=office, role=Role.OWN)
    assert admin.delete(f"/api/groups/{office.pk}").json() == {"error": "last_owner"}
    Grant.objects.create(node=folder, user=admin.user, role=Role.OWN)
    assert admin.delete(f"/api/groups/{office.pk}").status_code == 204
    assert not Grant.objects.filter(pk=grant.pk).exists()


def test_a_leaving_user_keeps_their_own_documents_and_is_signed_out_everywhere(admin):
    ana = User.objects.create_user("ana@example.com", PASSWORD)
    marko = User.objects.create_user("marko@example.com", PASSWORD)
    own = Node.objects.create(kind=Node.Kind.FOLDER, title="Moje")
    Grant.objects.create(node=own, user=ana, role=Role.OWN)
    Grant.objects.create(node=own, user=marko, role=Role.READ)
    browser = Client()
    browser.force_login(ana)
    assert browser.get("/api/nodes").json()["children"][0]["title"] == "Moje"

    assert admin.patch(f"/api/users/{ana.pk}", {"is_active": False}, JSON).status_code == 200
    assert browser.get("/api/nodes").status_code == 401
    assert not ana.sessions.exists()
    assert set(Grant.objects.filter(node=own).values_list("user", "role")) == {
        (ana.pk, Role.OWN),
        (marko.pk, Role.READ),
    }
    assert admin.patch(f"/api/users/{ana.pk}", {"is_active": True}, JSON).status_code == 200
    back = browser.post("/api/auth/login", {"email": ana.email, "password": PASSWORD}, JSON)
    assert back.json()["user"]["email"] == ana.email


def test_group_names_are_unique(admin):
    admin.post("/api/groups", {"name": "Ured"}, content_type=JSON)
    again = admin.post("/api/groups", {"name": "Ured"}, content_type=JSON)
    assert again.json() == {"error": "name_taken"}


def test_a_user_changes_their_own_password(api):
    changed = api.post("/api/auth/password", {"password": "Novi-Kamen-Most-82"}, JSON)
    assert changed.status_code == 200
    assert api.get("/api/auth/session").json()["user"]["email"] == "ivo@example.com"
    assert User.objects.get().check_password("Novi-Kamen-Most-82")
