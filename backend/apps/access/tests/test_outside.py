from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.access.models import Access, Grant, OutsideLink, Role
from apps.access.outside import MOST_FAILURES
from apps.documents.models import Node
from apps.documents.tests.test_boards import board
from apps.documents.tests.test_views import create
from apps.push import notices
from apps.push.models import Notice, Subscription
from apps.users.models import Policy, User

pytestmark = pytest.mark.django_db

JSON = "application/json"


def link_of(api, node: str, **fields) -> dict:
    made = api.post(f"/api/nodes/{node}/outside-links", fields, JSON)
    assert made.status_code == 201, made.json()
    return made.json()


def token_of(made: dict) -> str:
    return made["url"].rsplit("/", 1)[1]


def entered(token: str, **given) -> Client:
    stranger = Client()
    came = stranger.post(f"/api/outside/{token}/enter", given, JSON)
    assert came.status_code == 200, came.json()
    return stranger


def test_whoever_holds_a_link_reads_the_document_and_nothing_else(api):
    document = create(api, "document", "Ugovor")
    elsewhere = create(api, "document", "Drugo")
    token = token_of(link_of(api, document))
    door = Client().get(f"/api/outside/{token}").json()
    assert door == {"kind": "open", "title": "Ugovor", "password": False, "node": None}

    stranger = entered(token)
    assert stranger.get(f"/api/nodes/{document}").json()["role"] == "read"
    assert stranger.get(f"/api/nodes/{document}/state").status_code == 200
    assert stranger.patch(f"/api/nodes/{document}", {"title": "X"}, JSON).status_code == 403
    assert stranger.get(f"/api/nodes/{elsewhere}").status_code == 404
    again = stranger.get(f"/api/outside/{token}").json()
    assert again["node"]["id"] == document


def test_a_link_to_a_board_reads_it_inside(api, upload):
    node = board(api, upload)
    stranger = entered(token_of(link_of(api, node)))
    framed = stranger.get(f"/api/nodes/{node}/board")
    assert framed.status_code == 200
    assert b" data-reads" in framed.content


def test_whoever_holds_a_link_reaches_nothing_but_documents(api):
    document = create(api, "document", "Ugovor")
    stranger = entered(token_of(link_of(api, document)))
    for address in ("/api/mail/accounts", "/api/contacts", "/api/users", "/api/agents/clients"):
        refused = stranger.get(address)
        assert (refused.status_code, refused.json()["error"]) == (403, "visitors_not_allowed")
    made = stranger.post("/api/nodes", {"kind": "document", "title": "Moje"}, JSON)
    assert (made.status_code, made.json()["error"]) == (403, "visitors_not_allowed")


def test_a_link_with_a_password_opens_only_with_it(api):
    document = create(api, "document", "Ugovor")
    token = token_of(link_of(api, document, password="tajna-rijec"))
    stranger = Client()
    assert stranger.get(f"/api/outside/{token}").json()["title"] is None
    wrong = stranger.post(f"/api/outside/{token}/enter", {"password": "krivo"}, JSON)
    assert (wrong.status_code, wrong.json()["error"]) == (403, "wrong_link_password")
    assert stranger.get(f"/api/nodes/{document}").status_code == 401
    entered(token, password="tajna-rijec")


def test_guessing_a_password_stops(api):
    document = create(api, "document", "Ugovor")
    token = token_of(link_of(api, document, password="tajna-rijec"))
    stranger = Client()
    for _ in range(MOST_FAILURES):
        stranger.post(f"/api/outside/{token}/enter", {"password": "krivo"}, JSON)
    late = stranger.post(f"/api/outside/{token}/enter", {"password": "tajna-rijec"}, JSON)
    assert (late.status_code, late.json()["error"]) == (429, "too_many_link_tries")
    link = OutsideLink.objects.get(token=token)
    link.failed_at = timezone.now() - timedelta(hours=1)
    link.save()
    entered(token, password="tajna-rijec")


def test_a_link_ends_with_everyone_it_let_in(api):
    document = create(api, "document", "Ugovor")
    made = link_of(api, document)
    token = token_of(made)
    stranger = entered(token)
    assert api.delete(f"/api/outside-links/{made['id']}").status_code == 204
    gone = Client().get(f"/api/outside/{token}")
    assert (gone.status_code, gone.json()["error"]) == (404, "no_link")
    assert stranger.get(f"/api/nodes/{document}").status_code == 401
    assert not User.everyone.filter(visitor=True).exists()


def test_a_link_ends_on_its_date_and_with_the_node(api):
    document = create(api, "document", "Ugovor")
    today = timezone.localdate().isoformat()
    token = token_of(link_of(api, document, expires_on=today))
    stranger = entered(token)
    link = OutsideLink.objects.get(token=token)
    link.expires_at = timezone.now() - timedelta(seconds=1)
    link.save()
    assert Client().get(f"/api/outside/{token}").status_code == 404
    assert stranger.get(f"/api/nodes/{document}").status_code == 404

    link.expires_at = None
    link.save()
    assert stranger.get(f"/api/nodes/{document}").status_code == 200
    Node.objects.filter(pk=document).update(trashed_at=timezone.now())
    assert Client().get(f"/api/outside/{token}").status_code == 404


def test_a_date_in_the_past_is_refused(api):
    document = create(api, "document", "Ugovor")
    past = (timezone.localdate() - timedelta(days=1)).isoformat()
    refused = api.post(f"/api/nodes/{document}/outside-links", {"expires_on": past}, JSON)
    assert (refused.status_code, refused.json()["error"]) == (400, "invalid_link_date")


def test_only_the_owner_makes_a_link(api):
    document = create(api, "document", "Ugovor")
    colleague = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    Grant.objects.create(node_id=document, user=colleague, role=Role.EDIT)
    other = Client()
    other.force_login(colleague)
    assert other.get(f"/api/nodes/{document}/outside-links").status_code == 403
    assert other.post(f"/api/nodes/{document}/outside-links", {}, JSON).status_code == 403
    made = link_of(api, document)
    assert other.delete(f"/api/outside-links/{made['id']}").status_code == 403


def test_a_colleague_who_reads_the_node_opens_it_as_themselves(api):
    document = create(api, "document", "Ugovor")
    token = token_of(link_of(api, document, password="tajna-rijec"))
    assert api.get(f"/api/outside/{token}").json()["node"]["id"] == document
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    other = Client()
    other.force_login(stranger)
    refused = other.post(f"/api/outside/{token}/enter", {"password": "tajna-rijec"}, JSON)
    assert (refused.status_code, refused.json()["error"]) == (409, "signed_in_inside")


def test_without_download_a_link_reads_but_takes_nothing_out(api):
    document = create(api, "document", "Ugovor")
    stranger = entered(token_of(link_of(api, document, download=False)))
    assert stranger.get(f"/api/nodes/{document}").json()["confined"] is True
    stranger = entered(token_of(link_of(api, document)))
    assert stranger.get(f"/api/nodes/{document}").json()["confined"] is False


def test_a_folder_that_keeps_things_in_the_browser_lets_no_link_out(api):
    place = create(api, "folder", "Povjerljivo")
    document = create(api, "document", "Ugovor")
    token = token_of(link_of(api, document))
    api.post("/api/nodes/move", {"nodes": [document], "parent": place}, JSON)
    Node.objects.filter(pk=place).update(confined=True)
    assert Client().get(f"/api/outside/{token}").status_code == 404
    listed = api.get(f"/api/nodes/{document}/outside-links").json()
    assert listed["allowed"] is False
    refused = api.post(f"/api/nodes/{document}/outside-links", {}, JSON)
    assert (refused.status_code, refused.json()["error"]) == (403, "links_not_allowed")


@pytest.mark.parametrize(
    ("outside", "staff", "allowed", "opens"),
    [
        ("everyone", False, True, True),
        ("administrators", False, False, True),
        ("administrators", True, True, True),
        ("nobody", True, False, False),
    ],
)
def test_the_policy_says_who_makes_a_link(api, outside, staff, allowed, opens):
    document = create(api, "document", "Ugovor")
    token = token_of(link_of(api, document))
    stranger = entered(token)
    User.objects.filter(pk=api.user.pk).update(is_staff=staff)
    Policy.objects.update_or_create(pk=1, defaults={"outside": outside})
    assert api.get(f"/api/nodes/{document}/outside-links").json()["allowed"] is allowed
    made = api.post(f"/api/nodes/{document}/outside-links", {}, JSON)
    assert made.status_code == (201 if allowed else 403)
    assert Client().get(f"/api/outside/{token}").status_code == (200 if opens else 404)
    assert stranger.get(f"/api/nodes/{document}").status_code == (200 if opens else 404)


def test_the_log_says_a_link_was_made_used_and_ended(api):
    document = create(api, "document", "Ugovor")
    made = link_of(api, document)
    token = token_of(made)
    entered(token)
    entered(token)
    api.delete(f"/api/outside-links/{made['id']}")
    logged = Access.objects.filter(node_id=document, detail__link=made["id"]).order_by("at")
    assert [(each.kind, each.detail.get("role")) for each in logged] == [
        ("shared", "read"),
        ("opened", None),
        ("shared", None),
    ]
    entries = api.get(f"/api/nodes/{document}/log").json()["entries"]
    assert [entry["user"] for entry in entries if entry["kind"] == "opened"] == [None]


def test_a_folder_asks_for_files_without_an_account(api, settings):
    place = create(api, "folder", "Ponude")
    document = create(api, "document", "Ugovor")
    refused = api.post(f"/api/nodes/{document}/outside-links", {"kind": "upload"}, JSON)
    assert (refused.status_code, refused.json()["error"]) == (400, "not_a_folder")
    token = token_of(link_of(api, place, kind="upload"))
    Subscription.objects.create(
        user=api.user, endpoint="https://push.example/1", p256dh=b"k", auth=b"a"
    )
    stranger = Client()
    assert stranger.get(f"/api/outside/{token}").json()["title"] == "Ponude"
    data = b"%PDF-1.4 ponuda"
    begun = stranger.post(f"/api/outside/{token}/uploads", {"size": len(data)}, JSON).json()
    put = stranger.generic(
        "PUT",
        f"/api/outside/{token}/uploads/{begun['id']}",
        data,
        "application/octet-stream",
        headers={"Upload-Offset": "0"},
    )
    assert put.json()["blob"] is not None
    filed = stranger.post(
        f"/api/outside/{token}/files",
        {"upload": begun["id"], "title": "Ponuda", "extension": "pdf", "sender": "Marko"},
        JSON,
    )
    assert filed.status_code == 201
    arrived = Node.objects.get(parent_id=place, title="Ponuda")
    assert arrived.created_by == api.user
    logged = Access.objects.get(node=arrived)
    assert (logged.kind, logged.detail["sender"]) == ("uploaded", "Marko")
    notice = Notice.objects.get(user=api.user, kind=Notice.Kind.UPLOADED)
    worded = notices.worded(notice, "hr", 0)
    assert (worded["title"], worded["body"], worded["url"]) == (
        "Nova datoteka u mapi Ponude",
        "Marko: Ponuda",
        f"/p/{arrived.pk}",
    )
    assert stranger.get(f"/api/nodes/{arrived.pk}").status_code == 401
    entering = stranger.post(f"/api/outside/{token}/enter", {}, JSON)
    assert entering.status_code == 400
