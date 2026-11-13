import base64
import datetime
import time
import zlib
from urllib.parse import parse_qs, urlsplit

import httpx2
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.contrib.auth.models import Group
from django.test import Client
from lxml import etree
from signxml import XMLSigner, methods

from apps.identity import directory, oidc, saml
from apps.identity.backends import Directory
from apps.identity.models import Attempt, Identity, Kept, Provider
from apps.users import sessions
from apps.users.models import Policy, User

pytestmark = pytest.mark.django_db

ISSUER = "https://idp.example.com"
CLIENT_ID = "ponistra"
PASSWORD = "Kamen-Most-Rijeka-71"
A = saml.ASSERTION
P = saml.PROTOCOL


@pytest.fixture
def owner():
    return User.objects.create_user("ivo@example.com", PASSWORD, is_staff=True)


@pytest.fixture
def administrator(client, owner):
    client.force_login(owner)
    return client


def made(administrator, **given) -> dict:
    answer = administrator.post("/api/identity/providers", given, content_type="application/json")
    assert answer.status_code == 201, answer.content
    return answer.json()


# OpenID Connect


@pytest.fixture
def idp(monkeypatch):
    """An OpenID Connect provider answering over a mock transport."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    state = {"claims": {}, "asked": []}

    def answer(request: httpx2.Request) -> httpx2.Response:
        state["asked"].append(request)
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx2.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "userinfo_endpoint": f"{ISSUER}/userinfo",
                    "jwks_uri": f"{ISSUER}/jwks",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if path == "/jwks":
            return httpx2.Response(200, json={"keys": [{**public, "kid": "k1"}]})
        if path == "/token":
            now = int(time.time())
            claims = {
                "iss": ISSUER,
                "aud": CLIENT_ID,
                "iat": now,
                "exp": now + 300,
                **state["claims"],
            }
            token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})
            return httpx2.Response(200, json={"id_token": token, "access_token": "a"})
        return httpx2.Response(404)

    monkeypatch.setattr(
        oidc, "client", lambda: httpx2.Client(transport=httpx2.MockTransport(answer))
    )
    return state


@pytest.fixture
def connected(administrator, idp) -> dict:
    return made(
        administrator,
        kind="oidc",
        name="Entra",
        issuer=ISSUER,
        client_id=CLIENT_ID,
        secret="s3cret",
        domains=["example.com"],
        creates=True,
        groups=True,
    )


def started(browser: Client, provider_id: int, **query) -> tuple[Attempt, dict]:
    answer = browser.get(f"/api/identity/providers/{provider_id}/start", query)
    assert answer.status_code == 302, answer.content
    return Attempt.objects.get(provider_id=provider_id), parse_qs(
        urlsplit(answer["Location"]).query
    )


def test_oidc_signs_in_and_makes_the_account(connected, idp):
    browser = Client()
    attempt, asked = started(browser, connected["id"], next="/documents")
    assert asked["state"] == [attempt.state]
    assert asked["redirect_uri"] == [connected["here"]["redirect_uri"]]
    assert asked["code_challenge_method"] == ["S256"]
    idp["claims"] = {
        "sub": "u-1",
        "nonce": attempt.nonce,
        "email": "Ana@Example.com",
        "given_name": "Ana",
        "family_name": "Horvat",
        "groups": ["Prodaja"],
    }
    back = browser.get(
        f"/api/identity/providers/{connected['id']}/back", {"code": "c", "state": attempt.state}
    )
    assert back.status_code == 302 and back["Location"] == "/documents"
    ana = User.objects.get(email="ana@example.com")
    assert (ana.first_name, ana.has_usable_password()) == ("Ana", False)
    assert list(ana.groups.values_list("name", flat=True)) == ["Prodaja"]
    assert Kept.objects.get(group__name="Prodaja").provider_id == connected["id"]
    assert browser.get("/api/auth/session").json()["user"]["email"] == "ana@example.com"
    token = [each for each in idp["asked"] if each.url.path == "/token"][0]
    assert parse_qs(token.content.decode())["code_verifier"] == [attempt.verifier]
    assert not Attempt.objects.exists()


def test_oidc_links_an_existing_account_by_address(connected, idp, owner):
    browser = Client()
    attempt, _ = started(browser, connected["id"])
    idp["claims"] = {"sub": "u-ivo", "nonce": attempt.nonce, "email": owner.email}
    browser.get(
        f"/api/identity/providers/{connected['id']}/back", {"code": "c", "state": attempt.state}
    )
    assert Identity.objects.get(subject="u-ivo").user == owner
    assert browser.get("/api/auth/session").json()["user"]["id"] == owner.pk


@pytest.mark.parametrize(
    ("claims", "error"),
    [
        ({"sub": "x", "email": "eve@elsewhere.test"}, "outside_domains"),
        ({"sub": "x", "email": "eve@example.com", "email_verified": False}, "unverified_email"),
        ({"sub": "x", "email": "eve@example.com", "nonce": "wrong"}, "invalid_token"),
    ],
)
def test_oidc_refuses(connected, idp, claims, error):
    browser = Client()
    attempt, _ = started(browser, connected["id"])
    idp["claims"] = {"nonce": attempt.nonce, **claims}
    back = browser.get(
        f"/api/identity/providers/{connected['id']}/back", {"code": "c", "state": attempt.state}
    )
    assert back["Location"] == f"/?sign_in={error}"
    assert browser.get("/api/auth/session").json()["user"] is None
    assert not User.objects.filter(email__startswith="eve").exists()


def test_oidc_answer_only_counts_in_the_browser_that_asked(connected, idp):
    attempt, _ = started(Client(), connected["id"])
    idp["claims"] = {"sub": "u-1", "nonce": attempt.nonce, "email": "ana@example.com"}
    other = Client()
    back = other.get(
        f"/api/identity/providers/{connected['id']}/back", {"code": "c", "state": attempt.state}
    )
    assert back["Location"] == "/?sign_in=unknown_attempt"
    assert other.get("/api/auth/session").json()["user"] is None


def test_oidc_confirms_the_session(connected, idp, owner):
    Identity.objects.create(provider_id=connected["id"], user=owner, subject="u-ivo")
    browser = Client()
    browser.force_login(owner)
    session = browser.session
    del session[sessions.CONFIRMED]
    session.save()
    offered = browser.get("/api/auth/confirm").json()
    assert offered["providers"] == [{"id": connected["id"], "name": "Entra"}]
    attempt, asked = started(browser, connected["id"], confirm="1", next="/users")
    assert asked["prompt"] == ["login"]
    idp["claims"] = {"sub": "u-ivo", "nonce": attempt.nonce, "email": owner.email}
    back = browser.get(
        f"/api/identity/providers/{connected['id']}/back", {"code": "c", "state": attempt.state}
    )
    assert back["Location"] == "/users"
    assert sessions.CONFIRMED in browser.session


def test_public_providers_need_domains_to_make_accounts(administrator, idp):
    answer = administrator.post(
        "/api/identity/providers",
        {
            "kind": "oidc",
            "name": "Google",
            "issuer": ISSUER,
            "client_id": CLIENT_ID,
            "secret": "s",
            "creates": True,
        },
        content_type="application/json",
    )
    assert answer.json()["error"] == "domains_required"


def test_provider_saved_off_learns_its_addresses_first(administrator, idp):
    oidc = made(administrator, kind="oidc", name="Entra", issuer=ISSUER, enabled=False)
    assert oidc["here"]["redirect_uri"].endswith(f"/api/identity/providers/{oidc['id']}/back")
    saml = made(administrator, kind="saml", name="ADFS", enabled=False)
    assert saml["here"]["acs_url"].endswith(f"/api/identity/providers/{saml['id']}/saml")
    answer = administrator.patch(
        f"/api/identity/providers/{oidc['id']}",
        {"name": "Entra", "issuer": ISSUER, "client_id": CLIENT_ID},
        content_type="application/json",
    )
    assert answer.json()["error"] == "secret_required"
    assert Client().get("/api/auth/session").json()["providers"] == []


def test_sign_in_page_lists_providers(connected):
    assert Client().get("/api/auth/session").json()["providers"] == [
        {"id": connected["id"], "name": "Entra"}
    ]


# SAML


@pytest.fixture
def signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return (
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        certificate.public_bytes(serialization.Encoding.PEM),
        base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode(),
    )


def idp_metadata(der: str) -> str:
    return (
        f'<md:EntityDescriptor xmlns:md="{saml.METADATA}" xmlns:ds="{saml.SIGNATURE}" '
        f'entityID="https://adfs.example.com/adfs"><md:IDPSSODescriptor '
        f'protocolSupportEnumeration="{P}"><md:KeyDescriptor use="signing"><ds:KeyInfo>'
        f"<ds:X509Data><ds:X509Certificate>{der}</ds:X509Certificate></ds:X509Data>"
        f'</ds:KeyInfo></md:KeyDescriptor><md:SingleSignOnService Binding="{saml.REDIRECT}" '
        f'Location="https://adfs.example.com/adfs/ls"/></md:IDPSSODescriptor>'
        f"</md:EntityDescriptor>"
    )


@pytest.fixture
def adfs(administrator, signer) -> Provider:
    found = made(
        administrator,
        kind="saml",
        name="ADFS",
        metadata=idp_metadata(signer[2]),
        domains=["example.com"],
        creates=True,
        groups=True,
    )
    return Provider.objects.get(pk=found["id"])


def response(provider, attempt, signer, name_id="ana", **change) -> str:
    when = datetime.datetime.now(datetime.UTC)
    later = (when + datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issuer = change.get("issuer", provider.settings["entity_id"])
    audience = change.get("audience", saml.entity_of(provider))
    answered = change.get("in_response_to", attempt.request_id)
    document = etree.fromstring(
        f'<samlp:Response xmlns:samlp="{P}" xmlns:saml="{A}" ID="_r" Version="2.0">'
        f"<saml:Issuer>{issuer}</saml:Issuer><samlp:Status>"
        f'<samlp:StatusCode Value="{saml.SUCCESS}"/></samlp:Status>'
        f'<saml:Assertion ID="_a" Version="2.0"><saml:Issuer>{issuer}</saml:Issuer>'
        f"<saml:Subject><saml:NameID>{name_id}</saml:NameID>"
        f'<saml:SubjectConfirmation Method="{saml.BEARER}"><saml:SubjectConfirmationData '
        f'NotOnOrAfter="{later}" Recipient="{saml.consumer_of(provider)}" '
        f'InResponseTo="{answered}"/></saml:SubjectConfirmation></saml:Subject>'
        f'<saml:Conditions NotOnOrAfter="{later}"><saml:AudienceRestriction>'
        f"<saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>"
        f"</saml:Conditions><saml:AttributeStatement>"
        f'<saml:Attribute Name="{saml.EMAIL[3]}"><saml:AttributeValue>ana@example.com'
        f'</saml:AttributeValue></saml:Attribute><saml:Attribute Name="{saml.GROUPS[2]}">'
        f"<saml:AttributeValue>Nabava</saml:AttributeValue></saml:Attribute>"
        f"</saml:AttributeStatement></saml:Assertion></samlp:Response>"
    )
    assertion = document.find(f"{{{A}}}Assertion")
    signed = XMLSigner(
        method=methods.enveloped, c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"
    ).sign(assertion, key=signer[0], cert=signer[1], reference_uri="_a")
    document.replace(assertion, signed)
    if change.get("wrapped"):
        document.insert(
            2,
            etree.fromstring(
                f'<saml:Assertion xmlns:saml="{A}" ID="_e"><saml:Issuer>{issuer}</saml:Issuer>'
                f"<saml:Subject><saml:NameID>{change['wrapped']}</saml:NameID></saml:Subject>"
                f"</saml:Assertion>"
            ),
        )
    text = etree.tostring(document)
    if change.get("tampered"):
        text = text.replace(b"ana@example.com", b"ivo@example.com")
    return base64.b64encode(text).decode()


def test_saml_metadata_is_read(adfs):
    assert adfs.settings["entity_id"] == "https://adfs.example.com/adfs"
    assert adfs.settings["sso_url"] == "https://adfs.example.com/adfs/ls"
    assert adfs.settings["certificates"][0].startswith("-----BEGIN CERTIFICATE-----")
    found = Client().get(f"/api/identity/providers/{adfs.pk}/metadata")
    assert saml.consumer_of(adfs).encode() in found.content


def test_saml_signs_in(adfs, signer):
    browser = Client()
    attempt, asked = started(browser, adfs.pk)
    assert asked["RelayState"] == [attempt.state]
    packed = base64.b64decode(asked["SAMLRequest"][0])
    request = etree.fromstring(zlib.decompress(packed, -15))
    assert request.get("ID") == attempt.request_id
    posted = browser.post(
        f"/api/identity/providers/{adfs.pk}/saml",
        {"SAMLResponse": response(adfs, attempt, signer), "RelayState": attempt.state},
    )
    assert posted.status_code == 302 and posted["Location"] == "/"
    ana = User.objects.get(email="ana@example.com")
    assert list(ana.groups.values_list("name", flat=True)) == ["Nabava"]
    assert browser.get("/api/auth/session").json()["user"]["id"] == ana.pk


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"tampered": True}, "invalid_signature"),
        ({"audience": "https://elsewhere.example.com"}, "invalid_response"),
        ({"in_response_to": "_other"}, "invalid_response"),
        ({"issuer": "https://evil.example.com"}, "invalid_response"),
    ],
)
def test_saml_refuses(adfs, signer, change, error):
    browser = Client()
    attempt, _ = started(browser, adfs.pk)
    posted = browser.post(
        f"/api/identity/providers/{adfs.pk}/saml",
        {"SAMLResponse": response(adfs, attempt, signer, **change), "RelayState": attempt.state},
    )
    assert posted["Location"] == f"/?sign_in={error}"
    assert browser.get("/api/auth/session").json()["user"] is None


def test_saml_believes_only_the_signed_assertion(adfs, signer, owner):
    Identity.objects.create(provider=adfs, user=owner, subject="ivo")
    browser = Client()
    attempt, _ = started(browser, adfs.pk)
    browser.post(
        f"/api/identity/providers/{adfs.pk}/saml",
        {
            "SAMLResponse": response(adfs, attempt, signer, wrapped="ivo"),
            "RelayState": attempt.state,
        },
    )
    assert browser.get("/api/auth/session").json()["user"]["email"] == "ana@example.com"


def test_saml_answer_is_taken_once(adfs, signer):
    browser = Client()
    attempt, _ = started(browser, adfs.pk)
    given = {"SAMLResponse": response(adfs, attempt, signer), "RelayState": attempt.state}
    browser.post(f"/api/identity/providers/{adfs.pk}/saml", given)
    again = Client()
    again.cookies = browser.cookies
    replayed = again.post(f"/api/identity/providers/{adfs.pk}/saml", given)
    assert replayed["Location"] == "/?sign_in=unknown_attempt"


# SCIM


@pytest.fixture
def scim(administrator):
    found = made(administrator, kind="scim", name="Entra provisioning", groups=True)
    assert found["creates"] and found["here"]["scim_url"].endswith("/api/scim/v2")
    directory_client = Client(HTTP_AUTHORIZATION=f"Bearer {found['token']}")
    return found, directory_client


def scim_call(browser, method, path, data=None):
    return getattr(browser, method)(
        f"/api/scim/v2{path}", data, content_type="application/scim+json"
    )


def test_scim_needs_its_token(scim):
    assert Client().get("/api/scim/v2/Users").status_code == 401
    wrong = Client(HTTP_AUTHORIZATION="Bearer nope")
    assert wrong.get("/api/scim/v2/Users").status_code == 401


def test_scim_provisions_people_and_groups(scim, owner):
    provider, directory_client = scim
    made_user = scim_call(
        directory_client,
        "post",
        "/Users",
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "marko@example.com",
            "externalId": "e-marko",
            "name": {"givenName": "Marko", "familyName": "Marić"},
            "active": True,
        },
    )
    assert made_user.status_code == 201, made_user.content
    marko = made_user.json()
    assert marko["externalId"] == "e-marko"
    found = scim_call(directory_client, "get", '/Users?filter=userName eq "marko@example.com"')
    assert found.json()["totalResults"] == 1
    group = scim_call(
        directory_client,
        "post",
        "/Groups",
        {"displayName": "Uprava", "members": [{"value": marko["id"]}]},
    ).json()
    assert group["members"] == [{"value": marko["id"], "display": "Marko Marić"}]
    scim_call(
        directory_client,
        "patch",
        f"/Groups/{group['id']}",
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "Remove", "path": f'members[value eq "{marko["id"]}"]'}],
        },
    )
    assert not Group.objects.get(pk=group["id"]).user_set.exists()
    patched = scim_call(
        directory_client,
        "patch",
        f"/Users/{marko['id']}",
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "Replace", "path": "active", "value": "False"}],
        },
    )
    assert patched.json()["active"] is False
    assert scim_call(directory_client, "delete", f"/Users/{marko['id']}").status_code == 204
    assert not User.objects.get(pk=marko["id"]).is_active
    assert scim_call(directory_client, "get", f"/Users/{owner.pk}").status_code == 404
    assert scim_call(directory_client, "delete", f"/Users/{owner.pk}").status_code == 404
    assert User.objects.get(pk=owner.pk).is_active


def test_scim_keeps_what_the_administrator_may_change(scim, administrator):
    _, directory_client = scim
    marko = scim_call(directory_client, "post", "/Users", {"userName": "marko@example.com"}).json()
    group = scim_call(directory_client, "post", "/Groups", {"displayName": "Uprava"}).json()
    accounts = administrator.get("/api/users").json()
    listed = next(each for each in accounts["users"] if each["id"] == int(marko["id"]))
    assert listed["kept_by"] == "Entra provisioning"
    refused = administrator.patch(
        f"/api/users/{marko['id']}", {"first_name": "Netko"}, content_type="application/json"
    )
    assert refused.json()["error"] == "kept_by_directory"
    renamed = administrator.patch(
        f"/api/groups/{group['id']}", {"name": "Druga"}, content_type="application/json"
    )
    assert renamed.json()["error"] == "kept_by_directory"
    mine = Group.objects.create(name="Moja")
    administrator.patch(
        f"/api/users/{marko['id']}", {"groups": [mine.pk]}, content_type="application/json"
    )
    scim_call(
        directory_client,
        "patch",
        f"/Groups/{group['id']}",
        {"Operations": [{"op": "add", "path": "members", "value": [{"value": marko["id"]}]}]},
    )
    administrator.patch(
        f"/api/users/{marko['id']}", {"groups": []}, content_type="application/json"
    )
    assert list(User.objects.get(pk=marko["id"]).groups.values_list("name", flat=True)) == [
        "Uprava"
    ]


# LDAP


class Fake:
    """A directory answering one page of each search."""

    def __init__(self, people, groups):
        self.people, self.groups, self.asked = people, groups, {}

    def search_ext(self, base, scope, condition, attributes, serverctrls):
        self.asked[len(self.asked)] = "cn" in attributes
        return len(self.asked) - 1

    def result3(self, asked):
        return 101, self.groups if self.asked[asked] else self.people, asked, []

    def unbind_s(self):
        pass


def guid(number: int) -> bytes:
    return number.to_bytes(16, "little")


@pytest.fixture
def ad(administrator, monkeypatch):
    monkeypatch.setattr(directory, "tried", lambda provider: None)
    found = made(
        administrator,
        kind="ldap",
        name="AD",
        url="ldaps://dc.example.com",
        bind_dn="CN=ponistra,DC=example,DC=com",
        secret="bind",
        base_dn="DC=example,DC=com",
        creates=True,
        groups=True,
        sign_in=True,
    )
    return Provider.objects.get(pk=found["id"])


def entry(number, email, control="512"):
    return (
        f"CN=P{number},DC=example,DC=com",
        {
            "mail": [email.encode()],
            "givenName": [f"P{number}".encode()],
            "sn": [b"Test"],
            "userAccountControl": [control.encode()],
            "objectGUID": [guid(number)],
        },
    )


def test_ldap_reads_people_and_groups(ad, monkeypatch, owner):
    people = [
        entry(1, "dino@example.com"),
        entry(2, owner.email),
        entry(3, "off@example.com", "514"),
    ]
    groups = [
        (
            "CN=Skladiste,DC=example,DC=com",
            {
                "cn": [b"Skladiste"],
                "member": [b"cn=p1,dc=example,dc=com", b"CN=Unknown,DC=example,DC=com"],
                "objectGUID": [guid(9)],
            },
        )
    ]
    monkeypatch.setattr(directory, "bound", lambda provider: Fake(people, groups))
    directory.synced(ad.pk)
    dino = User.objects.get(email="dino@example.com")
    assert not dino.has_usable_password()
    assert owner.identities.get().detail == {"dn": "CN=P2,DC=example,DC=com"}
    assert User.objects.get(pk=owner.pk).has_usable_password()
    assert not User.objects.get(email="off@example.com").is_active
    assert list(dino.groups.values_list("name", flat=True)) == ["Skladiste"]
    monkeypatch.setattr(directory, "bound", lambda provider: Fake(people[1:], []))
    directory.synced(ad.pk)
    assert not User.objects.get(pk=dino.pk).is_active
    assert not Group.objects.filter(name="Skladiste").exists()
    assert Provider.objects.get(pk=ad.pk).synced_at is not None


def test_ldap_checks_the_password(ad, monkeypatch):
    Policy.objects.update_or_create(pk=1, defaults={"passkeys": Policy.Passkeys.NOBODY})
    monkeypatch.setattr(
        directory, "bound", lambda provider: Fake([entry(1, "dino@example.com")], [])
    )
    directory.synced(ad.pk)
    checked = []

    def check(provider, name, password):
        checked.append(name)
        return password == "ad-password"

    monkeypatch.setattr(directory, "checked", check)
    browser = Client()
    refused = browser.post(
        "/api/auth/login",
        {"email": "dino@example.com", "password": "wrong"},
        content_type="application/json",
    )
    assert refused.status_code == 400
    signed = browser.post(
        "/api/auth/login",
        {"email": "dino@example.com", "password": "ad-password"},
        content_type="application/json",
    )
    assert signed.json()["user"]["email"] == "dino@example.com"
    assert checked == ["CN=P1,DC=example,DC=com"] * 2
    changed = browser.post(
        "/api/auth/password", {"password": "Novi-Kamen-Most-88"}, content_type="application/json"
    )
    assert changed.json()["error"] == "password_in_directory"


def test_empty_password_is_never_checked(ad):
    assert Directory().authenticate(None, email="dino@example.com", password="") is None
    assert directory.checked(ad, "CN=P1,DC=example,DC=com", "") is False


def test_unencrypted_directory_is_refused(administrator):
    answer = administrator.post(
        "/api/identity/providers",
        {
            "kind": "ldap",
            "name": "AD",
            "url": "ldap://dc.example.com",
            "bind_dn": "x",
            "secret": "y",
            "base_dn": "z",
        },
        content_type="application/json",
    )
    assert answer.json()["error"] == "unencrypted_directory"
