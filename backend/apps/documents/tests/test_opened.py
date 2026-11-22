from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.access.models import Grant, Role
from apps.documents import opened
from apps.documents.models import Node, Opening
from apps.imports.tests.test_views import WORD
from apps.jobs import work
from apps.users.models import User, policy

pytestmark = pytest.mark.django_db

RAW = "application/octet-stream"


def opens(client, data: bytes = WORD, name: str = "Ugovor.docx"):
    return client.post(f"/api/opened?name={name}", data, content_type=RAW)


def placed(client, data: bytes = WORD, name: str = "Ugovor.docx") -> tuple[dict, dict]:
    response = opens(client, data, name)
    assert response.status_code == 202, response.json()
    while (claimed := work.claim()) is not None:
        work.run(claimed)
    job = client.get(f"/api/jobs/{response.json()['job']}").json()
    assert job["state"] == "done", job
    return response.json(), job["answer"]


def test_a_file_opened_signed_out_is_read_by_a_visitor_of_its_own(client):
    sent, made = placed(client)
    assert sent["key"] and made["unplaced"] and made["parent"] is None
    node = Node.objects.get(pk=made["id"])
    visitor = User.everyone.get(opening__isnull=False)
    assert visitor.visitor and node.created_by == visitor
    assert Grant.objects.get(node=node, user=visitor).role == Role.READ
    assert client.get(f"/api/nodes/{node.pk}").status_code == 200
    assert client.get("/api/nodes").status_code == 403

    again, _ = placed(client, name="Drugi.docx")
    assert "key" not in again
    opening = Opening.objects.get()
    assert opening.files == 2 and opening.bytes == 2 * len(WORD)


def test_a_member_signed_in_opens_files_as_always(api):
    assert opens(api).status_code == 400


def test_opening_follows_the_policy(client):
    rules = policy()
    rules.opening = False
    rules.save()
    response = opens(client)
    assert (response.status_code, response.json()["error"]) == (403, "opening_off")
    assert not User.everyone.filter(visitor=True).exists()


def test_a_file_too_large_is_refused_before_anyone_is_made(client, monkeypatch):
    monkeypatch.setattr(opened, "MOST_BYTES", len(WORD) - 1)
    response = opens(client)
    assert (response.status_code, response.json()["error"]) == (413, "too_large")
    assert not Opening.objects.exists()


def test_one_address_opens_so_many_files_an_hour(client, monkeypatch):
    monkeypatch.setattr(opened, "MOST_FILES", 2)
    assert opens(client).status_code == 202
    assert opens(Client(), name="Drugi.docx").status_code == 202
    response = opens(Client())
    assert (response.status_code, response.json()["error"]) == (429, "too_many_openings")


def test_closing_the_window_removes_the_visitor_and_its_files(client):
    _, made = placed(client)
    assert client.post("/api/opened/closed").status_code == 204
    assert not Node.objects.filter(pk=made["id"]).exists()
    assert not User.everyone.filter(visitor=True).exists()
    assert client.get(f"/api/nodes/{made['id']}").status_code in (401, 403)


def test_whoever_signs_in_takes_the_files_by_the_key(api):
    sent, made = placed(Client())
    response = api.post("/api/opened/taken", {"key": sent["key"]}, content_type="application/json")
    assert response.status_code == 200
    [node] = response.json()["nodes"]
    assert node["id"] == made["id"] and node["unplaced"]
    owned = Node.objects.get(pk=made["id"])
    assert owned.created_by == api.user
    assert Grant.objects.get(node=owned).user == api.user
    assert Grant.objects.get(node=owned).role == Role.OWN
    assert not User.everyone.filter(visitor=True).exists()
    gone = api.post("/api/opened/taken", {"key": sent["key"]}, content_type="application/json")
    assert (gone.status_code, gone.json()["error"]) == (404, "opening_gone")


def test_files_opened_an_hour_ago_are_forgotten(client):
    _, made = placed(client)
    Opening.objects.update(created_at=timezone.now() - opened.OPENED_FOR - timedelta(seconds=1))
    assert opened.forgotten() == 1
    assert not Node.objects.filter(pk=made["id"]).exists()
    assert not User.everyone.filter(visitor=True).exists()
