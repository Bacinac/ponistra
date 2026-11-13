from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.journal import entries
from apps.journal.models import Entry
from apps.users import erasure
from apps.users.models import Policy, User

pytestmark = pytest.mark.django_db

JSON = "application/json"
PASSWORD = "Kamen-Most-Rijeka-71"
Kind = Entry.Kind


@pytest.fixture
def admin(client):
    client.user = User.objects.create_superuser("ivo@example.com", PASSWORD)
    client.force_login(client.user)
    return client


@pytest.fixture
def ana():
    return User.objects.create_user("ana@example.com", PASSWORD)


def signing_in(email, password, address="198.51.100.7"):
    return Client(REMOTE_ADDR=address, HTTP_USER_AGENT="Firefox").post(
        "/api/auth/login", {"email": email, "password": password}, content_type=JSON
    )


def journal(client, **asked):
    answer = client.get("/api/journal", asked)
    assert answer.status_code == 200
    return answer.json()


def kinds() -> list[str]:
    return list(Entry.objects.order_by("pk").values_list("kind", flat=True))


def test_a_sign_in_is_written_with_its_way_address_and_browser(ana):
    assert signing_in(ana.email, PASSWORD).status_code == 200
    entry = Entry.objects.get(kind=Kind.SIGNED_IN)
    assert (entry.actor, entry.address, entry.detail) == (
        ana,
        "198.51.100.7",
        {"way": "password", "agent": "Firefox"},
    )


def test_a_failed_sign_in_names_the_account_it_tried(ana):
    signing_in(ana.email, "wrong")
    signing_in("nobody@example.com", "wrong")
    failed = Entry.objects.filter(kind=Kind.SIGN_IN_FAILED).order_by("pk")
    assert [(each.subject, each.detail["email"]) for each in failed] == [
        (ana, "ana@example.com"),
        (None, "nobody@example.com"),
    ]


def test_an_address_held_after_its_failures_is_written_as_locked_out_once_a_try(ana, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT + 2):
        signing_in(ana.email, "wrong")
    assert (
        kinds() == [Kind.SIGN_IN_FAILED] * (settings.AXES_FAILURE_LIMIT - 1) + [Kind.LOCKED_OUT] * 3
    )


def test_signing_out_and_ending_another_users_sessions_are_written(admin, ana):
    browser = Client()
    browser.force_login(ana)
    assert admin.delete(f"/api/users/{ana.pk}/sessions").status_code == 204
    browser.post("/api/auth/logout")
    admin.post("/api/auth/logout")
    ended = Entry.objects.get(kind=Kind.SESSIONS_ENDED)
    assert (ended.actor, ended.subject, ended.detail) == (admin.user, ana, {"count": 1})
    assert Entry.objects.get(kind=Kind.SIGNED_OUT).actor == admin.user


def test_an_administrator_adding_and_changing_an_account_is_written(admin):
    made = admin.post(
        "/api/users", {"email": "mia@example.com", "password": PASSWORD}, content_type=JSON
    ).json()
    admin.patch(
        f"/api/users/{made['id']}",
        {"is_admin": True, "first_name": "Mia", "last_name": "Horvat"},
        content_type=JSON,
    )
    admin.patch(f"/api/users/{made['id']}", {"first_name": "Mia"}, content_type=JSON)
    added, changed = Entry.objects.order_by("pk")
    assert (added.kind, added.subject_id, added.detail) == (
        Kind.USER_ADDED,
        made["id"],
        {"admin": False},
    )
    assert (changed.kind, changed.actor, changed.detail) == (
        Kind.USER_CHANGED,
        admin.user,
        {"changed": ["name", "admin"], "admin": True, "active": True},
    )


def test_the_policy_is_written_only_when_it_changes(admin):
    Policy.objects.create(passkeys=Policy.Passkeys.NOBODY, outside=Policy.Outside.NOBODY)
    for _ in range(2):
        admin.patch("/api/policy", {"passkeys": Policy.Passkeys.EVERYONE}, content_type=JSON)
    assert [entry.detail for entry in Entry.objects.filter(kind=Kind.POLICY_CHANGED)] == [
        {"passkeys": Policy.Passkeys.EVERYONE, "outside": Policy.Outside.NOBODY}
    ]


def test_groups_and_applications_are_written(admin):
    group = admin.post("/api/groups", {"name": "Prodaja"}, content_type=JSON).json()
    admin.patch(f"/api/groups/{group['id']}", {"name": "Nabava"}, content_type=JSON)
    admin.delete(f"/api/groups/{group['id']}")
    admin.post(
        "/api/identity/applications",
        {"name": "Kod", "redirect_uris": ["https://code.example.com/back"]},
        content_type=JSON,
    )
    assert [(entry.kind, entry.detail) for entry in Entry.objects.order_by("pk")] == [
        (Kind.GROUP_ADDED, {"name": "Prodaja"}),
        (Kind.GROUP_RENAMED, {"name": "Nabava", "was": "Prodaja"}),
        (Kind.GROUP_REMOVED, {"name": "Nabava"}),
        (Kind.APPLICATION_ADDED, {"name": "Kod"}),
    ]


def test_only_an_administrator_reads_the_journal(client, ana):
    client.force_login(ana)
    assert client.get("/api/journal").status_code == 403


def test_the_journal_is_read_newest_first_in_pages_narrowed_by_group_and_person(admin, ana):
    for _ in range(3):
        entries.wrote(Kind.SIGNED_IN, actor=ana)
    entries.wrote(Kind.GROUP_ADDED, actor=admin.user, name="Prodaja")
    entries.wrote(Kind.USER_CHANGED, actor=admin.user, subject=ana, changed=["name"])
    everything = journal(admin)
    assert [entry["kind"] for entry in everything["entries"]] == [
        Kind.USER_CHANGED,
        Kind.GROUP_ADDED,
        *[Kind.SIGNED_IN] * 3,
    ]
    assert everything["entries"][0]["subject"]["email"] == "ana@example.com"
    assert [entry["kind"] for entry in journal(admin, group="sign_ins")["entries"]] == [
        Kind.SIGNED_IN
    ] * 3
    assert len(journal(admin, user=ana.pk)["entries"]) == 4
    assert admin.get("/api/journal", {"group": "else"}).status_code == 400


def test_a_page_ends_where_the_next_begins(admin, monkeypatch):
    monkeypatch.setattr("apps.journal.views.PAGE", 2)
    for _ in range(5):
        entries.wrote(Kind.SIGNED_IN, actor=admin.user)
    first = journal(admin)
    second = journal(admin, before=first["next"])
    third = journal(admin, before=second["next"])
    ids = [entry["id"] for page in (first, second, third) for entry in page["entries"]]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == 5
    assert third["next"] is None


def test_an_erased_person_takes_their_own_trail_and_leaves_what_was_done_to_others(admin, ana):
    signing_in(ana.email, PASSWORD)
    signing_in(ana.email, "wrong", "203.0.113.4")
    entries.wrote(Kind.GROUP_ADDED, actor=ana, name="Prodaja")
    erasure.erase(ana, None, admin.user)
    assert [(entry.kind, entry.actor) for entry in Entry.objects.all()] == [
        (Kind.GROUP_ADDED, None)
    ]


def test_entries_older_than_a_year_go_at_a_sign_in(ana):
    old = entries.wrote(Kind.SIGNED_IN, actor=ana)
    Entry.objects.filter(pk=old.pk).update(at=timezone.now() - entries.KEPT - timedelta(days=1))
    signing_in(ana.email, PASSWORD)
    assert not Entry.objects.filter(pk=old.pk).exists()
