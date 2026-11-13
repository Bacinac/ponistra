import json

import pytest

from apps.tasks.models import Task
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")


@pytest.fixture
def signed_in(client, owner):
    client.force_login(owner)
    return client


def sent(client, method, path, **data):
    return getattr(client, method)(path, json.dumps(data), content_type="application/json")


def test_a_task_is_a_note_with_a_due_date_that_leads_back_to_where_it_came_from(signed_in):
    made = sent(
        signed_in,
        "post",
        "/api/tasks",
        text="  Nazvati   Anu ",
        due="2026-11-03",
        source={"kind": "mail", "label": "Ponuda", "link": "/mail/2/17"},
    )
    assert made.status_code == 201
    assert made.json() == {
        "id": made.json()["id"],
        "text": "Nazvati Anu",
        "due": "2026-11-03",
        "done": False,
        "done_at": None,
        "source": {"kind": "mail", "label": "Ponuda", "link": "/mail/2/17"},
        "changed_at": made.json()["changed_at"],
    }
    later = sent(signed_in, "post", "/api/tasks", text="Kupiti papir")
    sooner = sent(signed_in, "post", "/api/tasks", text="Poslati račun", due="2026-11-01")
    listed = signed_in.get("/api/tasks").json()["tasks"]
    assert [each["text"] for each in listed] == ["Poslati račun", "Nazvati Anu", "Kupiti papir"]
    done = sent(signed_in, "patch", f"/api/tasks/{sooner.json()['id']}", done=True)
    assert done.json()["done"] is True and done.json()["done_at"] is not None
    listed = signed_in.get("/api/tasks").json()["tasks"]
    assert [each["text"] for each in listed] == ["Nazvati Anu", "Kupiti papir", "Poslati račun"]
    undone = sent(signed_in, "patch", f"/api/tasks/{sooner.json()['id']}", done=False, due=None)
    assert undone.json() | {"done": False, "due": None, "done_at": None} == undone.json()
    gone = signed_in.delete(f"/api/tasks/{later.json()['id']}")
    assert gone.status_code == 204
    assert signed_in.get(f"/api/tasks/{later.json()['id']}").status_code == 404


def test_what_a_task_refuses(signed_in, owner):
    assert sent(signed_in, "post", "/api/tasks", text="   ").json()["error"] == "text_required"
    assert (
        sent(signed_in, "post", "/api/tasks", text="X", due="sutra").json()["error"]
        == "invalid_due"
    )
    for source in (
        {"kind": "web", "link": "/x"},
        {"kind": "mail", "link": "https://evil.example/x"},
        {"kind": "mail", "link": "//evil.example/x"},
        "mail",
    ):
        refused = sent(signed_in, "post", "/api/tasks", text="X", source=source)
        assert refused.json()["error"] == "invalid_source", source
    other = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    theirs = Task.objects.create(owner=other, text="Tuđe")
    assert signed_in.get(f"/api/tasks/{theirs.pk}").status_code == 404
    assert [each["text"] for each in signed_in.get("/api/tasks").json()["tasks"]] == []
