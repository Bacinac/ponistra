import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client

from apps.access import outside
from apps.access.models import Access, Code, Grant, OutsideLink, Role
from apps.documents.tests.test_views import create
from apps.mail import sending
from apps.mail.models import Account
from apps.users.models import User

pytestmark = pytest.mark.django_db

JSON = "application/json"


@pytest.fixture
def delivered(api, monkeypatch):
    """The mail that leaves from the user's own account, kept instead of sent."""
    kept = []

    async def deliver(account, message):
        kept.append(message)
        return [], True

    monkeypatch.setattr(sending, "delivered", deliver)
    Account.objects.create(
        owner=api.user,
        address="ivo@example.com",
        username="ivo@example.com",
        secret=b"",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        default=True,
    )
    return kept


def text_of(message) -> str:
    return message.get_body(("plain",)).get_content()


def shared(api, node, **fields):
    given = {"address": "Marko@Drugi.test", "name": "Marko", "role": "edit", "language": "hr"}
    return api.post(f"/api/nodes/{node}/visitors", given | fields, JSON)


def test_someone_outside_is_given_a_document_by_address_and_edits_it_by_name(api, delivered):
    document = create(api, "document", "Ugovor")
    made = shared(api, document)
    assert made.status_code == 201, made.json()
    marko = User.everyone.get(email="marko@drugi.test")
    assert (marko.visitor, marko.first_name, marko.has_usable_password()) == (True, "Marko", False)
    grant = Grant.objects.get(node_id=document, user=marko)
    assert (grant.role, grant.download) == (Role.EDIT, True)
    (message,) = delivered
    assert message["To"] == "marko@drugi.test"
    assert message["Subject"].endswith("dijeli s vama: Ugovor")
    assert f"/v/{grant.key}" in text_of(message)

    marko_browser = Client()
    came = marko_browser.post(f"/api/visit/{grant.key}", {}, JSON)
    assert came.json()["node"]["id"] == document
    assert marko_browser.get(f"/api/nodes/{document}").json()["role"] == "edit"
    session = marko_browser.get("/api/auth/session").json()
    assert session["user"]["visitor"] is True
    refused = marko_browser.get("/api/mail/accounts")
    assert (refused.status_code, refused.json()["error"]) == (403, "visitors_not_allowed")

    access = api.get(f"/api/nodes/{document}/access").json()
    outsider = next(each for each in access["grants"] if each["grantee"].get("outside"))
    assert outsider["grantee"]["name"] == "Marko"


def test_a_visitor_is_no_colleague(api, delivered):
    document = create(api, "document", "Ugovor")
    shared(api, document)
    people = api.get("/api/people").json()["users"]
    assert [each["email"] for each in people] == ["ivo@example.com"]
    signed_in = Client().post(
        "/api/auth/login", {"email": "marko@drugi.test", "password": ""}, JSON
    )
    assert signed_in.status_code == 400


def test_a_colleague_is_shared_with_inside(api, delivered):
    document = create(api, "document", "Ugovor")
    User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    refused = shared(api, document, address="ana@example.com")
    assert (refused.status_code, refused.json()["error"]) == (400, "colleague")
    assert delivered == []


def test_a_grant_without_download_keeps_the_document_in_the_browser(api, delivered):
    document = create(api, "document", "Ugovor")
    shared(api, document, role="read", download=False)
    grant = Grant.objects.get(node_id=document, user__email="marko@drugi.test")
    visitor = Client()
    visitor.post(f"/api/visit/{grant.key}", {}, JSON)
    assert visitor.get(f"/api/nodes/{document}").json()["confined"] is True
    changed = api.patch(f"/api/grants/{grant.pk}", {"download": True}, JSON)
    assert changed.json()["download"] is True
    assert visitor.get(f"/api/nodes/{document}").json()["confined"] is False


def test_a_visitor_never_reaches_what_everyone_is_given(api, delivered):
    document = create(api, "document", "Ugovor")
    common = create(api, "document", "Svima")
    Grant.objects.create(node_id=common, role=Role.READ)
    shared(api, document)
    grant = Grant.objects.get(node_id=document, user__email="marko@drugi.test")
    visitor = Client()
    visitor.post(f"/api/visit/{grant.key}", {}, JSON)
    assert visitor.get(f"/api/nodes/{common}").status_code == 404
    listed = visitor.get("/api/nodes/shared").json()
    assert [each["id"] for each in listed["children"]] == [document]


def test_taking_the_grant_back_ends_the_visit(api, delivered):
    document = create(api, "document", "Ugovor")
    shared(api, document)
    grant = Grant.objects.get(node_id=document, user__email="marko@drugi.test")
    visitor = Client()
    visitor.post(f"/api/visit/{grant.key}", {}, JSON)
    api.delete(f"/api/grants/{grant.pk}")
    assert visitor.get(f"/api/nodes/{document}").status_code == 404
    gone = Client().post(f"/api/visit/{grant.key}", {}, JSON)
    assert gone.status_code == 404


def test_a_mail_that_does_not_leave_takes_the_sharing_back(api, monkeypatch, delivered):
    from apps.mail import imap

    async def fail(account, message):
        raise imap.Failed("mail_refused")

    monkeypatch.setattr(sending, "delivered", fail)
    document = create(api, "document", "Ugovor")
    assert shared(api, document).status_code == 502
    assert not Grant.objects.filter(node_id=document, user__visitor=True).exists()


def mailed(api, document, *to, **fields):
    data = {
        "account": Account.objects.get(owner=api.user).pk,
        "to": [{"name": "", "address": address} for address in to],
        "subject": "Ugovor",
        "html": "<p>U privitku.</p>",
        "shared": [{"node": document, "role": "read"} | fields],
    }
    return api.post("/api/mail/send", data, JSON)


def test_a_mail_carries_a_document_as_a_link_each_recipient_opens_by_a_code(api, delivered):
    document = create(api, "document", "Ugovor")
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    sent = mailed(api, document, "marko@drugi.test", "ana@example.com")
    assert sent.status_code == 200, sent.json()
    link = OutsideLink.objects.get(node_id=document)
    assert (link.kind, link.addresses) == (OutsideLink.Kind.PEOPLE, ["marko@drugi.test"])
    assert Grant.objects.get(node_id=document, user=ana).role == Role.READ
    message = delivered[-1]
    assert outside.url_of(link) in message.get_body(("html",)).get_content()
    token = link.token

    stranger = Client()
    door = stranger.get(f"/api/outside/{token}").json()
    assert (door["kind"], door["title"]) == ("people", None)
    asked = stranger.post(f"/api/outside/{token}/code", {"address": "netko@drugi.test"}, JSON)
    assert asked.status_code == 204
    assert len(delivered) == 1
    asked = stranger.post(
        f"/api/outside/{token}/code", {"address": "Marko@drugi.test", "language": "hr"}, JSON
    )
    assert asked.status_code == 204
    code_mail = delivered[-1]
    assert code_mail["To"] == "marko@drugi.test"
    wrong = stranger.post(
        f"/api/outside/{token}/enter", {"address": "marko@drugi.test", "code": "000000x"}, JSON
    )
    assert (wrong.status_code, wrong.json()["error"]) == (403, "wrong_code")
    Code.objects.filter(link=link).update(digest=make_password("123456"))
    came = stranger.post(
        f"/api/outside/{token}/enter", {"address": "marko@drugi.test", "code": "123456"}, JSON
    )
    assert came.json()["node"]["id"] == document
    assert stranger.get(f"/api/nodes/{document}").json()["role"] == "read"
    opened = Access.objects.get(node_id=document, kind="opened", detail__link=str(link.pk))
    assert opened.user.email == "marko@drugi.test"

    api.delete(f"/api/outside-links/{link.pk}")
    assert stranger.get(f"/api/nodes/{document}").status_code == 404


def test_a_colleague_opens_a_mailed_link_as_themselves(api, delivered):
    document = create(api, "document", "Ugovor")
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    mailed(api, document, "ana@example.com")
    token = OutsideLink.objects.get(node_id=document).token
    colleague = Client()
    colleague.force_login(ana)
    assert colleague.get(f"/api/outside/{token}").json()["node"]["id"] == document


def test_a_mail_that_does_not_leave_takes_its_links_back(api, monkeypatch, delivered):
    from apps.mail import imap

    async def fail(account, message):
        raise imap.Failed("mail_refused")

    monkeypatch.setattr(sending, "delivered", fail)
    document = create(api, "document", "Ugovor")
    assert mailed(api, document, "marko@drugi.test").status_code == 502
    assert not OutsideLink.objects.exists()


def test_a_mail_to_leave_later_shares_only_when_it_leaves(api, delivered):
    from datetime import timedelta

    from django.utils import timezone

    document = create(api, "document", "Ugovor")
    data = {
        "account": Account.objects.get(owner=api.user).pk,
        "to": [{"name": "", "address": "marko@drugi.test"}],
        "subject": "Ugovor",
        "html": "<p>U privitku.</p>",
        "shared": [{"node": document, "title": "Ugovor", "role": "read"}],
        "at": (timezone.now() + timedelta(hours=1)).isoformat(),
    }
    assert api.post("/api/mail/later", data, JSON).status_code == 201
    assert not OutsideLink.objects.exists()


def test_a_visitor_exports_but_starts_no_other_job(api, delivered):
    document = create(api, "document", "Ugovor")
    shared(api, document)
    grant = Grant.objects.get(node_id=document, user__email="marko@drugi.test")
    visitor = Client()
    visitor.post(f"/api/visit/{grant.key}", {}, JSON)
    refused = visitor.post("/api/jobs", {"kind": "import", "blob": "0" * 64}, JSON)
    assert (refused.status_code, refused.json()["error"]) == (403, "visitors_not_allowed")
    started = visitor.post("/api/jobs", {"kind": "docx", "document": document}, JSON)
    assert started.status_code == 202, started.json()
