import pytest
from django.contrib.auth.models import Group

from apps.mail import sharing, taking
from apps.mail.models import Grant, Message, Opening, Unsent
from apps.users.models import User

from .mox import letter
from .test_opened import inbox
from .test_views import kept

pytestmark = pytest.mark.django_db


@pytest.fixture
def people():
    return {
        name: User.objects.create_user(
            f"{name}@example.com", "Kamen-Most-Rijeka-71", first_name=name
        )
        for name in ("Ivo", "Ana", "Marko")
    }


@pytest.fixture
def box(client, people):
    client.force_login(people["Ivo"])
    made = client.post("/api/mail/mailboxes", {"name": "Prodaja"}, "application/json")
    assert made.status_code == 201
    return User.everyone.get(pk=made.json()["id"])


def arrived(box, subject="Upit"):
    message = letter(subject)
    message.replace_header("From", "Kupac <kupac@example.com>")
    message.replace_header("To", "prodaja@firma.test")
    return taking.took(inbox(kept(box, "prodaja@firma.test")), message.as_bytes(), {})


def share(client, box, kind, pk, role):
    given = {"kind": kind, "id": pk, "role": role}
    return client.post(f"/api/mail/mailboxes/{box.pk}/grants", given, "application/json")


def test_a_mailbox_is_owned_by_its_maker_and_is_no_one_among_the_people(client, people, box):
    assert box.mailbox and not box.has_usable_password()
    assert not User.objects.filter(pk=box.pk).exists()
    listed = client.get("/api/mail/accounts").json()
    assert listed["mailboxes"] == [{"id": box.pk, "name": "Prodaja", "role": "own", "unseen": 0}]
    assert listed["role"] is None
    assert client.get(f"/api/mail/accounts?box={box.pk}").json()["role"] == "own"


def test_a_colleague_reads_what_the_mailbox_is_shared_with_them_as(client, people, box):
    message = arrived(box)
    assert share(client, box, "user", people["Ana"].pk, "read").status_code == 201
    client.force_login(people["Ana"])
    page = client.get(f"/api/mail/folders/{message.folder_id}/messages?box={box.pk}").json()
    assert [each["subject"] for each in page["messages"]] == ["Upit"]
    by_folder = client.get(f"/api/mail/folders/{message.folder_id}/messages").json()
    assert by_folder["messages"] == page["messages"]
    acted = {"where": {"messages": [message.pk]}, "action": "seen"}
    chosen = f"/api/mail/folders/{message.folder_id}/chosen?box={box.pk}"
    assert client.post(chosen, acted, "application/json").status_code == 403
    client.force_login(people["Ivo"])
    share(client, box, "user", people["Ana"].pk, "edit")
    client.force_login(people["Ana"])
    assert client.post(chosen, acted, "application/json").json() == {"changed": 1}
    assert (
        client.post(f"/api/mail/accounts?box={box.pk}", {}, "application/json").status_code == 403
    )
    client.force_login(people["Marko"])
    assert client.get(f"/api/mail/messages/{message.pk}?box={box.pk}").status_code == 404
    assert client.get(f"/api/mail/messages/{message.pk}").status_code == 404


def test_a_group_reaches_the_mailbox_and_its_changes_reach_them(client, people, box):
    sellers = Group.objects.create(name="Prodaja")
    people["Marko"].groups.add(sellers)
    share(client, box, "group", sellers.pk, "edit")
    assert sharing.roles(people["Marko"]) == {box.pk: "edit"}
    assert sharing.concerned(str(box.pk)) == {box.pk, people["Ivo"].pk, people["Marko"].pk}
    share(client, box, "everyone", None, "read")
    assert sharing.concerned(str(box.pk)) is None
    assert sharing.concerned(str(people["Ana"].pk)) == {people["Ana"].pk}


def test_the_mailbox_keeps_someone_who_owns_it(client, people, box):
    [own] = client.get(f"/api/mail/mailboxes/{box.pk}/grants").json()["grants"]
    taken = client.delete(f"/api/mail/mailboxes/{box.pk}/grants/{own['id']}")
    assert taken.json() == {"error": "last_owner"}
    assert share(client, box, "user", people["Ivo"].pk, "read").json() == {"error": "last_owner"}
    assert Grant.objects.get(pk=own["id"]).role == "own"


def test_each_colleague_opening_a_message_of_the_mailbox_is_noted(client, people, box):
    message = arrived(box)
    share(client, box, "user", people["Ana"].pk, "read")
    client.get(f"/api/mail/messages/{message.pk}?box={box.pk}")
    client.force_login(people["Ana"])
    client.get(f"/api/mail/messages/{message.pk}?box={box.pk}")
    message.refresh_from_db()
    assert message.opened_at is not None
    assert {each.user_id for each in Opening.objects.all()} == {people["Ivo"].pk, people["Ana"].pk}


def test_removing_the_mailbox_takes_its_accounts_and_its_mail(client, people, box):
    message = arrived(box)
    share(client, box, "user", people["Ana"].pk, "edit")
    client.force_login(people["Ana"])
    assert client.delete(f"/api/mail/mailboxes/{box.pk}").status_code == 403
    client.force_login(people["Ivo"])
    assert client.delete(f"/api/mail/mailboxes/{box.pk}").status_code == 204
    assert not Message.objects.filter(pk=message.pk).exists()
    assert not User.everyone.filter(pk=box.pk).exists()


def test_a_colleague_writes_from_the_mailbox_where_they_act_on_its_mail(client, people, box):
    account = kept(box, "prodaja@firma.test")
    share(client, box, "user", people["Ana"].pk, "read")
    client.force_login(people["Ana"])
    written = {"account": account.pk, "subject": "Ponuda", "html": "<p>Cijena</p>"}
    assert client.post("/api/mail/unsent", written, "application/json").status_code == 403
    client.force_login(people["Ivo"])
    share(client, box, "user", people["Ana"].pk, "edit")
    client.force_login(people["Ana"])
    begun = client.post("/api/mail/unsent", written, "application/json")
    assert begun.status_code == 201
    assert Unsent.objects.get(pk=begun.json()["id"]).owner == box
    assert client.get("/api/mail/unsent").json() == {"unsent": []}
    assert len(client.get(f"/api/mail/unsent?box={box.pk}").json()["unsent"]) == 1
