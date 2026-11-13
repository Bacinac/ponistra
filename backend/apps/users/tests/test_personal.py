import io
import json
import zipfile

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.contacts.models import Contact
from apps.core.api import Refused
from apps.documents.models import Node
from apps.documents.views import created
from apps.jobs.tests import handed
from apps.mail.models import Folder, Message
from apps.tasks.models import Task
from apps.users import personal, sessions
from apps.users.models import AppPassword, Session, User

pytestmark = pytest.mark.django_db

PASSWORD = "Kamen-Most-Rijeka-71"
MAIL = b"Message-ID: <1@x>\r\nFrom: marko@example.com\r\nSubject: Ponuda\r\n\r\nU prilogu.\r\n"


@pytest.fixture
def ana():
    return User.objects.create_user(
        "ana@example.com", PASSWORD, first_name="Ana", last_name="Horvat"
    )


@pytest.fixture
def ivo():
    return User.objects.create_superuser("ivo@example.com", PASSWORD)


def unpacked(user) -> zipfile.ZipFile:
    with personal.packed(user) as found:
        return zipfile.ZipFile(io.BytesIO(found.read()))


def rows(archive: zipfile.ZipFile, part: str) -> list[dict]:
    return json.loads(archive.read(f"data/{part}.json"))


def test_every_field_naming_a_user_is_exported_or_left_out_for_a_reason():
    assert not set(personal.PARTS) & set(personal.LEFT)
    assert personal.relations() == set(personal.PARTS) | set(personal.LEFT)


def test_the_export_holds_what_names_the_person_and_none_of_their_secrets(ana, ivo):
    Task.objects.create(owner=ana, text="Nazvati Marka")
    Task.objects.create(owner=ivo, text="Tuđe")
    AppPassword.objects.create(user=ana, name="Mobitel", digest="d" * 64)
    Session.objects.create(
        session_key="k" * 32, session_data="s", expire_date=timezone.now(), user=ana
    )
    photo = store.put(io.BytesIO(b"\x89PNG\r\n\x1a\nphoto"))
    Contact.objects.create(owner=ana, name="Marko", photo=photo)
    inbox = Folder.objects.create(owner=ana, name="Inbox", role="inbox")
    raw = store.put(io.BytesIO(MAIL))
    message = Message.objects.create(
        owner=ana, folder=inbox, key="1", raw=raw, subject="Ponuda", date=timezone.now()
    )
    projects = created(None, Node.Kind.FOLDER, "Projekti", None, ana)
    created(projects, Node.Kind.DOCUMENT, "Plan", None, ana)
    pdf = store.put(io.BytesIO(b"%PDF-1.7\n%%EOF\n"))
    created(projects, Node.Kind.FILE, "Ugovor", pdf, ana, "pdf")
    created(None, Node.Kind.DOCUMENT, "Ivino", None, ivo)
    ana.backdrop = store.put(io.BytesIO(b"\xff\xd8\xff\xe0backdrop"))
    ana.call = {"background": "own"}
    ana.save()

    archive = unpacked(ana)
    manifest = json.loads(archive.read("manifest.json"))
    assert (manifest["format"], manifest["user"]) == ("ponistra-personal", ana.pk)
    assert {part["name"] for part in manifest["parts"]} <= set(archive.namelist())
    person = json.loads(archive.read("person.json"))
    assert (person["email"], person["name"]) == ("ana@example.com", "Ana Horvat")
    assert person["call"] == {"background": "own"}
    assert archive.read(person["backdrop"]).endswith(b"backdrop")
    assert [row["text"] for row in rows(archive, "tasks.Task.owner")] == ["Nazvati Marka"]
    assert rows(archive, "users.AppPassword.user")[0]["name"] == "Mobitel"
    assert "digest" not in rows(archive, "users.AppPassword.user")[0]
    assert "session_key" not in rows(archive, "users.Session.user")[0]
    assert rows(archive, "mail.Message.owner")[0]["subject"] == "Ponuda"
    assert archive.read(f"mail/{message.pk}.eml") == MAIL
    assert archive.read(f"files/{photo.sha256}.png").endswith(b"photo")
    assert archive.read("documents/Projekti/Ugovor.pdf") == b"%PDF-1.7\n%%EOF\n"
    with zipfile.ZipFile(io.BytesIO(archive.read("documents/Projekti/Plan.ponx"))) as plan:
        assert json.loads(plan.read("manifest.json"))["format"] == "ponistra"
    assert not any("Ivino" in name for name in archive.namelist())
    assert b"d" * 64 not in b"".join(archive.read(name) for name in archive.namelist())


def test_only_an_administrator_asks_for_the_export_and_after_confirming(ana, ivo):
    request = RequestFactory().post("/api/jobs")
    request.user, request.session = ivo, {}
    with pytest.raises(Refused) as refused:
        personal.asked(request, {"user": ana.pk})
    assert refused.value.error == "confirm_required"
    sessions.confirm(request.session)
    assert personal.asked(request, {"user": ana.pk}) == {"user": ana.pk}
    with pytest.raises(Refused) as missing:
        personal.asked(request, {"user": "ana"})
    assert missing.value.error == "not_found"
    request.user = ana
    with pytest.raises(Refused) as refused:
        personal.asked(request, {"user": ana.pk})
    assert refused.value.error == "forbidden"
    with pytest.raises(Refused):
        personal.done(ana, {"user": ana.pk})
    assert personal.done(ivo, {"user": ana.pk}).name == "ana@example.com.zip"


def test_the_export_is_a_job_whose_file_the_administrator_saves(ana, ivo, client):
    Task.objects.create(owner=ana, text="Nazvati Marka")
    client.force_login(ana)
    assert handed.refused(client, "personal", user=ana.pk) == (403, "forbidden")
    client.force_login(ivo)
    archive = zipfile.ZipFile(io.BytesIO(content(handed.saved(client, "personal", user=ana.pk))))
    assert [row["text"] for row in rows(archive, "tasks.Task.owner")] == ["Nazvati Marka"]
