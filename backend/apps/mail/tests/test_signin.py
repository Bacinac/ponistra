import base64
import io
import json
import time
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.core import sealed
from apps.mail import signin, sync, views
from apps.mail.imap import Failed, Login
from apps.mail.models import Account, Client, Folder, Source
from apps.mail.servers import provider_name
from apps.users.models import User

pytestmark = pytest.mark.django_db

RETURN = "http://testserver/api/oauth/{}"


def id_token(**claims) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


class TokenEndpoint:
    """The provider's token endpoint: gives its answers in turn, an error by its code, and keeps
    what it was asked."""

    def __init__(self, monkeypatch, *answers):
        self.answers = list(answers)
        self.asked: list[dict] = []
        monkeypatch.setattr(signin.urllib.request, "urlopen", self.urlopen)

    def urlopen(self, request, timeout):
        self.asked.append({key: value for key, (value,) in parse_qs(request.data.decode()).items()})
        answer = self.answers.pop(0)
        if isinstance(answer, str):
            body = io.BytesIO(json.dumps({"error": answer}).encode())
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", None, body)
        return io.BytesIO(json.dumps(answer).encode())


@pytest.fixture(autouse=True)
def fresh_tokens():
    signin._tokens.clear()
    yield
    signin._tokens.clear()


@pytest.fixture
def clients():
    for provider in ("google", "microsoft"):
        Client.objects.create(
            provider=provider,
            client_id=f"{provider}-id",
            secret=sealed.seal("oauth client", f"{provider}-secret"),
            hint="cret",
        )


@pytest.fixture
def ivo(client):
    user = User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )
    client.force_login(user)
    return user


@pytest.fixture
def checked(monkeypatch):
    """The servers' sign-in, which the test mail server cannot do through XOAUTH2. The code is
    traded on a worker thread, which sees only what is committed: the tests that come back from
    the provider run outside a transaction."""
    found = []

    async def signed_in(fields, login, device=""):
        found.append((fields["imap_host"], fields["smtp_host"], login))

    monkeypatch.setattr(views, "_checked", signed_in)
    return found


def started(client, provider: str) -> str:
    url = client.post(f"/api/mail/oauth/{provider}", content_type="application/json").json()["url"]
    return parse_qs(urlsplit(url).query)["state"][0]


def test_signing_in_starts_at_the_provider_with_a_challenge_and_returns_here(client, ivo, clients):
    response = client.post(
        "/api/mail/oauth/microsoft", {"address": "ime@outlook.com"}, content_type="application/json"
    )
    url = urlsplit(response.json()["url"])
    query = {key: value for key, (value,) in parse_qs(url.query).items()}
    assert url.netloc == "login.microsoftonline.com"
    assert query["client_id"] == "microsoft-id"
    assert query["redirect_uri"] == RETURN.format("microsoft")
    assert query["code_challenge_method"] == "S256"
    consented = query["scope"].split()
    assert "offline_access" in consented
    assert "https://graph.microsoft.com/Calendars.Read" in consented
    assert "https://graph.microsoft.com/Contacts.Read" in consented
    assert query["login_hint"] == "ime@outlook.com"
    kept = client.session["mail_oauth"]
    assert kept["state"] == query["state"]
    assert signin._challenge(kept["verifier"]) == query["code_challenge"]


def test_signing_in_needs_the_installations_client_at_the_provider(client, ivo):
    response = client.post("/api/mail/oauth/google", content_type="application/json")
    assert (response.status_code, response.json()) == (409, {"error": "oauth_client"})
    response = client.post("/api/mail/oauth/yahoo", content_type="application/json")
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_coming_back_connects_the_account_signed_in_with(
    client, ivo, clients, checked, monkeypatch
):
    state = started(client, "microsoft")
    claims = {"aud": "microsoft-id", "email": "ime@Outlook.com", "tid": signin.CONSUMERS}
    endpoint = TokenEndpoint(
        monkeypatch,
        {"access_token": "access", "refresh_token": "refresh", "id_token": id_token(**claims)},
    )
    response = client.get(f"/api/oauth/microsoft?code=given&state={state}")
    assert (response.status_code, response["Location"]) == (302, "/mail")
    login = Login("ime@outlook.com", token="access")
    assert checked == [("outlook.office365.com", "smtp-mail.outlook.com", login)]
    asked = endpoint.asked[0]
    assert (asked["grant_type"], asked["code"]) == ("authorization_code", "given")
    assert asked["redirect_uri"] == RETURN.format("microsoft")
    assert asked["code_verifier"]
    assert "graph.microsoft.com" not in asked["scope"]
    assert "https://outlook.office.com/IMAP.AccessAsUser.All" in asked["scope"].split()
    made = Account.objects.get()
    assert (made.address, made.username, made.login) == ("ime@outlook.com",) * 2 + ("microsoft",)
    assert (made.name, made.smtp_port, made.smtp_security) == ("Ivo Bošković", 587, "starttls")
    assert sealed.opened("mail", made.secret) == "refresh"
    again = client.get(f"/api/oauth/microsoft?code=given&state={state}")
    assert again["Location"] == "/mail?oauth=oauth_state"


@pytest.mark.django_db(transaction=True)
def test_a_work_account_at_microsoft_sends_through_microsoft_365(
    client, ivo, clients, checked, monkeypatch
):
    state = started(client, "microsoft")
    claims = {"aud": "microsoft-id", "preferred_username": "ana@firma.test", "tid": "firma"}
    TokenEndpoint(
        monkeypatch,
        {"access_token": "access", "refresh_token": "refresh", "id_token": id_token(**claims)},
    )
    client.get(f"/api/oauth/microsoft?code=given&state={state}")
    assert checked[0][:2] == ("outlook.office365.com", "smtp.office365.com")
    assert Account.objects.get().address == "ana@firma.test"


@pytest.mark.django_db(transaction=True)
def test_an_account_kept_with_a_password_signs_in_through_the_provider_from_then_on(
    client, ivo, clients, checked, monkeypatch
):
    found = Account.objects.create(
        owner=ivo,
        address="ime@gmail.com",
        name="Ivo",
        username="ime@gmail.com",
        secret=sealed.seal("mail", "app password"),
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_security="tls",
        smtp_host="smtp.gmail.com",
        smtp_port=465,
        smtp_security="tls",
        state=Account.State.FAILED,
        error="imap_login",
    )
    node = Folder.objects.create(owner=ivo, name="Inbox", role="inbox")
    Source.objects.create(account=found, name="INBOX", kind="inbox", folder=node, low=1, high=9)
    state = started(client, "google")
    claims = {"aud": "google-id", "email": "ime@gmail.com"}
    TokenEndpoint(
        monkeypatch,
        {"access_token": "access", "refresh_token": "refresh", "id_token": id_token(**claims)},
    )
    assert client.get(f"/api/oauth/google?code=given&state={state}")["Location"] == "/mail"
    found.refresh_from_db()
    assert (found.login, found.name, found.state, found.error) == ("google", "Ivo", "syncing", "")
    assert sealed.opened("mail", found.secret) == "refresh"
    assert list(found.sources.values_list("high", flat=True)) == [9]


@pytest.mark.django_db(transaction=True)
def test_a_sign_in_refused_or_not_started_here_connects_nothing(
    client, ivo, clients, checked, monkeypatch
):
    state = started(client, "google")
    response = client.get(f"/api/oauth/google?error=access_denied&state={state}")
    assert response["Location"] == "/mail?oauth=oauth_denied"
    assert (
        client.get("/api/oauth/google?code=x&state=forged")["Location"] == "/mail?oauth=oauth_state"
    )
    assert (
        client.get("/api/oauth/google?code=x&state=%C4%8Dvor")["Location"]
        == "/mail?oauth=oauth_state"
    )
    state = started(client, "google")
    response = client.get(f"/api/oauth/microsoft?code=x&state={state}")
    assert response["Location"] == "/mail?oauth=oauth_state"
    state = started(client, "google")
    claims = {"aud": "someone-else", "email": "ime@gmail.com"}
    TokenEndpoint(
        monkeypatch, {"access_token": "a", "refresh_token": "r", "id_token": id_token(**claims)}
    )
    response = client.get(f"/api/oauth/google?code=x&state={state}")
    assert response["Location"] == "/mail?oauth=oauth_refused"
    assert not checked and not Account.objects.exists()


def test_coming_back_signed_out_goes_to_the_sign_in(client):
    response = client.get("/api/oauth/google?code=x&state=y")
    assert (response.status_code, response["Location"]) == (302, "/")


def account_at(owner, provider: str, refresh: str, address: str = "ime@outlook.com") -> Account:
    return Account.objects.create(
        owner=owner,
        address=address,
        username=address,
        login=provider,
        secret=sealed.seal("mail", refresh),
        imap_host="outlook.office365.com",
        imap_port=993,
        imap_security="tls",
        smtp_host="smtp-mail.outlook.com",
        smtp_port=587,
        smtp_security="starttls",
    )


def test_microsoft_replaces_the_refresh_token_at_each_use_and_the_new_one_is_kept(
    ivo, clients, monkeypatch
):
    account = account_at(ivo, "microsoft", "first")
    endpoint = TokenEndpoint(
        monkeypatch, {"access_token": "a1", "refresh_token": "second", "expires_in": 3600}
    )
    login, ends = signin.login(account)
    assert login == Login("ime@outlook.com", token="a1")
    assert ends == pytest.approx(time.time() + 3600 - signin.EARLY, abs=5)
    assert (endpoint.asked[0]["grant_type"], endpoint.asked[0]["refresh_token"]) == (
        "refresh_token",
        "first",
    )
    assert endpoint.asked[0]["scope"] == signin.WAYS["microsoft"].scope
    assert sealed.opened("mail", Account.objects.get().secret) == "second"
    assert signin.login(account)[0].token == "a1"
    assert len(endpoint.asked) == 1


def test_graph_has_a_token_of_its_own_from_the_same_sign_in(ivo, clients, monkeypatch):
    account = account_at(ivo, "microsoft", "first")
    endpoint = TokenEndpoint(
        monkeypatch,
        {"access_token": "mail", "refresh_token": "second", "expires_in": 3600},
        {"access_token": "graph", "refresh_token": "third", "expires_in": 3600},
    )
    assert signin.login(account)[0].token == "mail"
    assert signin.graph(Account.objects.get()) == "graph"
    assert endpoint.asked[1]["refresh_token"] == "second"
    assert endpoint.asked[1]["scope"] == f"{signin.WAYS['microsoft'].beside} offline_access"
    assert (signin.login(account)[0].token, signin.graph(account)) == ("mail", "graph")
    assert len(endpoint.asked) == 2
    with pytest.raises(Failed):
        signin.graph(account_at(ivo, "google", "first", "ime@gmail.com"))


def test_a_token_about_to_end_is_renewed_and_google_keeps_its_refresh_token(
    ivo, clients, monkeypatch
):
    account = account_at(ivo, "google", "lasting")
    endpoint = TokenEndpoint(
        monkeypatch,
        {"access_token": "a1", "expires_in": signin.EARLY - 1},
        {"access_token": "a2", "expires_in": 3600},
    )
    assert signin.login(account)[0].token == "a1"
    assert signin.login(account)[0].token == "a2"
    assert [asked["refresh_token"] for asked in endpoint.asked] == ["lasting", "lasting"]
    assert "scope" not in endpoint.asked[0]
    assert sealed.opened("mail", Account.objects.get().secret) == "lasting"


@pytest.mark.parametrize(
    "answer, code",
    [
        ("invalid_grant", "oauth_login"),
        ("invalid_client", "oauth_client"),
        ("temporarily_unavailable", "oauth_refused"),
    ],
)
def test_a_renewal_the_provider_refuses_says_why(ivo, clients, monkeypatch, answer, code):
    TokenEndpoint(monkeypatch, answer)
    with pytest.raises(Failed) as refused:
        signin.login(account_at(ivo, "microsoft", "withdrawn"))
    assert refused.value.code == code


def test_a_withdrawn_sign_in_stops_the_account_until_the_user_signs_in_again(ivo):
    withdrawn = account_at(ivo, "google", "r")
    Account.objects.filter(pk=withdrawn.pk).update(state="failed", error="oauth_login")
    waiting = account_at(ivo, "microsoft", "r", "drugi@outlook.com")
    Account.objects.filter(pk=waiting.pk).update(state="failed", error="oauth_client")
    assert sync.followed() == {waiting.pk}


def test_a_client_the_provider_knows_is_told_the_code_is_wrong(monkeypatch):
    TokenEndpoint(monkeypatch, "invalid_grant", "invalid_client")
    signin.checked("google", "id", "secret", RETURN.format("google"))
    with pytest.raises(Failed) as refused:
        signin.checked("google", "id", "wrong", RETURN.format("google"))
    assert refused.value.code == "oauth_client"


def test_microsoft_is_given_a_code_shaped_like_its_own_so_it_looks_at_the_client(monkeypatch):
    endpoint = TokenEndpoint(monkeypatch, "invalid_client")
    with pytest.raises(Failed) as refused:
        signin.checked("microsoft", "id", "secret id", RETURN.format("microsoft"))
    assert refused.value.code == "oauth_client"
    assert endpoint.asked[0]["code"].startswith("M.")


@pytest.fixture
def administrator(client):
    user = User.objects.create_user("admin@example.com", "Kamen-Most-Rijeka-71", is_staff=True)
    client.force_login(user)
    return user


def test_an_administrator_enters_the_client_checked_with_the_provider_never_seeing_its_secret(
    client, administrator, monkeypatch
):
    asked = []
    monkeypatch.setattr(signin, "checked", lambda *given: asked.append(given))
    given = {"client_id": "id", "secret": "s3cret-value", "expires": "2028-10-24"}
    response = client.patch("/api/mail/clients/microsoft", given, content_type="application/json")
    described = response.json()
    assert described["redirect"] == RETURN.format("microsoft")
    assert (described["client_id"], described["hint"], described["expires"]) == (
        "id",
        "alue",
        "2028-10-24",
    )
    assert asked == [("microsoft", "id", "s3cret-value", RETURN.format("microsoft"))]
    assert sealed.opened("oauth client", Client.objects.get().secret) == "s3cret-value"
    client.patch(
        "/api/mail/clients/microsoft", {"client_id": "id2"}, content_type="application/json"
    )
    assert asked[-1][1:3] == ("id2", "s3cret-value")
    listed = client.get("/api/mail/clients").json()["clients"]
    assert [each["provider"] for each in listed] == ["google", "microsoft"]
    assert "s3cret" not in json.dumps(listed)
    providers = client.get("/api/mail/accounts").json()["providers"]
    assert providers == {"microsoft": "outlook.office365.com"}
    assert client.delete("/api/mail/clients/microsoft").status_code == 204
    assert not Client.objects.exists()


def test_a_client_the_provider_refuses_is_not_kept(client, administrator, monkeypatch):
    def refused(*given):
        raise Failed("oauth_client")

    monkeypatch.setattr(signin, "checked", refused)
    given = {"client_id": "id", "secret": "wrong"}
    response = client.patch("/api/mail/clients/google", given, content_type="application/json")
    assert (response.status_code, response.json()) == (422, {"error": "oauth_client"})
    response = client.patch(
        "/api/mail/clients/google", {"client_id": "id"}, content_type="application/json"
    )
    assert response.json() == {"error": "invalid_secret"}
    assert not Client.objects.exists()


def test_only_an_administrator_sees_or_enters_the_clients(client, ivo):
    assert client.get("/api/mail/clients").status_code == 403
    given = {"client_id": "id", "secret": "s"}
    response = client.patch("/api/mail/clients/google", given, content_type="application/json")
    assert response.status_code == 403


def test_a_mailbox_is_known_by_its_provider_or_its_domain():
    assert provider_name("ime@gmail.com") == "Gmail"
    assert provider_name("ime@googlemail.com") == "Gmail"
    assert provider_name("ime@outlook.com") == "Outlook.com"
    assert provider_name("ime@hotmail.co.uk") == "Outlook.com"
    assert provider_name("ivo@brezik.test") == "Brezik"
    assert provider_name("ivo@mail.fsb.test") == "Fsb"
