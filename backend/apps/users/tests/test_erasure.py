import pytest
from axes.models import AccessLog
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from apps.access.models import Access, Grant, Role
from apps.documents.models import Node
from apps.documents.views import created
from apps.mail import sharing
from apps.mail.models import Grant as MailGrant
from apps.tasks.models import Task
from apps.users.models import Session, User
from apps.vault.models import Collection, Member

pytestmark = pytest.mark.django_db

PASSWORD = "Kamen-Most-Rijeka-71"


@pytest.fixture
def admin(client):
    client.user = User.objects.create_superuser("ivo@example.com", PASSWORD)
    client.force_login(client.user)
    return client


@pytest.fixture
def ana():
    return User.objects.create_user(
        "ana@example.com", PASSWORD, first_name="Ana", last_name="Horvat"
    )


def folder(title, user, **flags):
    node = created(None, Node.Kind.FOLDER, title, None, user)
    Node.objects.filter(pk=node.pk).update(**flags)
    return Node.objects.get(pk=node.pk)


def test_an_erased_user_leaves_the_documents_only_they_owned_to_the_heir(admin, ana):
    marko = User.objects.create_user("marko@example.com", PASSWORD)
    plan = created(None, Node.Kind.DOCUMENT, "Plan", None, ana)
    notes = folder("Bilješke", ana, notes=True)
    old = folder("Staro", ana, trashed_at=timezone.now())
    shared = folder("Zajedničko", ana)
    Grant.objects.create(node=shared, user=marko, role=Role.OWN)
    reader = Grant.objects.create(node=plan, user=marko, role=Role.READ)
    office = folder("Ured", ana, company=True)
    Task.objects.create(owner=ana, text="Nazvati")
    seen = Access.objects.create(node=plan, user=ana, kind=Access.Kind.OPENED)
    AccessLog.objects.create(username="ana@example.com", ip_address="203.0.113.7")

    assert admin.delete(f"/api/users/{ana.pk}").json() == {"error": "heir_required"}
    assert admin.delete(f"/api/users/{ana.pk}?heir={ana.pk}").json() == {"error": "invalid_heir"}
    assert admin.delete(f"/api/users/{admin.user.pk}?heir={marko.pk}").json() == {"error": "self"}
    assert admin.delete(f"/api/users/{ana.pk}?heir={marko.pk}").status_code == 204

    assert not User.objects.filter(pk=ana.pk).exists()
    assert not Task.objects.exists()
    assert not AccessLog.objects.filter(username="ana@example.com").exists()
    seen.refresh_from_db()
    assert seen.user is None
    taken = Node.objects.get(parent=None, title="Ana Horvat")
    assert Grant.objects.filter(node=taken, user=marko, role=Role.OWN).exists()
    assert set(Node.objects.filter(parent=taken).values_list("title", flat=True)) == {
        "Plan",
        "Bilješke",
        "Staro",
    }
    notes.refresh_from_db()
    old.refresh_from_db()
    assert (notes.notes, old.trashed_at is not None) == (False, True)
    assert Grant.objects.filter(pk=reader.pk).exists()
    shared.refresh_from_db()
    office.refresh_from_db()
    assert (shared.parent, office.parent) == (None, None)
    assert Grant.objects.filter(node=office, user=marko, role=Role.OWN).exists()


def test_an_erased_user_leaves_the_shared_mailboxes_only_they_owned_to_the_heir(admin, ana):
    marko = User.objects.create_user("marko@example.com", PASSWORD)
    gone = User.objects.create_user("bivsi@example.com", PASSWORD, is_active=False)
    office = sharing.made(ana, "Ured")
    MailGrant.objects.create(mailbox=office, user=gone, role=Role.OWN)
    MailGrant.objects.create(mailbox=office, user=marko, role=Role.READ)
    sales = sharing.made(ana, "Prodaja")
    MailGrant.objects.create(
        mailbox=sales, group=Group.objects.create(name="Prodaja"), role=Role.OWN
    )

    assert admin.delete(f"/api/users/{ana.pk}").json() == {"error": "heir_required"}
    assert admin.delete(f"/api/users/{ana.pk}?heir={marko.pk}").status_code == 204

    assert MailGrant.objects.get(mailbox=office, user=marko).role == Role.OWN
    assert not MailGrant.objects.filter(mailbox=sales, user=marko).exists()


def test_a_user_who_owns_nothing_alone_needs_no_heir_and_is_signed_out(admin, ana):
    Client().force_login(ana)
    assert Session.objects.filter(user=ana).exists()
    assert admin.delete(f"/api/users/{ana.pk}").status_code == 204
    assert not Session.objects.filter(user_id=ana.pk).exists()


def test_the_last_owner_of_a_shared_vault_collection_stays_until_it_has_another(admin, ana):
    shared = Collection.objects.create(kind=Collection.Kind.SHARED, name="Lozinke")
    Member.objects.create(collection=shared, user=ana, role=Role.OWN)
    assert admin.delete(f"/api/users/{ana.pk}").json() == {"error": "collection_owner"}
    assert User.objects.filter(pk=ana.pk).exists()
    Member.objects.create(collection=shared, user=admin.user, role=Role.OWN)
    assert admin.delete(f"/api/users/{ana.pk}").status_code == 204


def test_only_an_administrator_erases(ana, client):
    marko = User.objects.create_user("marko@example.com", PASSWORD)
    client.force_login(marko)
    assert client.delete(f"/api/users/{ana.pk}").json() == {"error": "forbidden"}
