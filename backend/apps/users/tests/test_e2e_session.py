import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from apps.documents.models import Node
from apps.meetings.models import Meeting
from apps.users.models import User

pytestmark = pytest.mark.django_db

JSON = "application/json"


def e2e(action: str, *args: str) -> str:
    out = StringIO()
    call_command("e2e_session", action, *args, stdout=out)
    return out.getvalue().strip()


def test_start_signs_in_an_account_a_colleague_and_an_administrator_a_try_that_stop_removes():
    kept = User.objects.create_user("ivo@example.com")
    Node.objects.create(kind=Node.Kind.DOCUMENT, title="Ivin", created_by=kept)
    Meeting.objects.made("Ivin", kept)
    started = json.loads(e2e("start", "--workers=2", "--retries=1"))
    password = started["password"]
    assert [[account["name"] for account in tries] for tries in started["workers"]] == [
        ["Ana Kolegić", "Bruno Kolegić"],
        ["Cvita Kolegić", "Dino Kolegić"],
    ]
    signed = []
    for account in [account for tries in started["workers"] for account in tries]:
        browser, beside, administrator = Client(), Client(), Client()
        browser.cookies["sessionid"] = account["own"]
        beside.cookies["sessionid"] = account["colleague"]
        administrator.cookies["sessionid"] = account["administrator"]
        for each in (browser, beside, administrator):
            signed.append(each.get("/api/auth/session").json()["user"])
            confirmed = each.post("/api/auth/confirm", {"password": password}, content_type=JSON)
            assert confirmed.status_code == 204
        assert signed[-2]["name"] == account["name"]
        assert [user["is_admin"] for user in signed[-3:]] == [False, False, True]
    assert len({user["email"] for user in signed}) == 12
    made = browser.post(
        "/api/nodes", {"kind": "document", "title": "Proba", "parent": None}, content_type=JSON
    )
    assert made.status_code == 201
    met = browser.post("/api/meetings", {"title": "Proba"}, content_type=JSON)
    assert met.status_code == 201

    e2e("stop")

    assert list(User.objects.all()) == [kept]
    assert list(Node.objects.values_list("title", flat=True)) == ["Ivin"]
    assert list(Meeting.objects.values_list("conversation__title", flat=True)) == ["Ivin"]
    assert browser.get("/api/nodes").status_code == 401


def test_start_clears_what_an_interrupted_run_left():
    e2e("start", "--workers=3")
    e2e("start")
    assert User.objects.filter(email__endswith="@e2e.invalid").count() == 3


def test_start_refuses_more_accounts_than_it_has_colleagues_for():
    with pytest.raises(CommandError):
        e2e("start", "--workers=5", "--retries=1")
