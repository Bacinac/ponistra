import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import pytest
from django.conf import settings
from django.test import Client

from apps.identity import tokens
from apps.identity.models import Application, Code, Key
from apps.identity.views import challenge_of
from apps.users.models import User

pytestmark = pytest.mark.django_db

BACK = "https://code.example.com/oauth2/callback"
ISSUER = f"{settings.PUBLIC_URL}/api/identity"


@pytest.fixture
def owner():
    return User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )


@pytest.fixture
def administrator(client, owner):
    owner.is_staff = True
    owner.save()
    client.force_login(owner)
    return client


@pytest.fixture
def registered(administrator):
    made = administrator.post(
        "/api/identity/applications",
        {"name": "Code", "redirect_uris": [BACK]},
        content_type="application/json",
    )
    assert made.status_code == 201, made.content
    return made.json()


def signed_in_as(email: str, staff=False) -> Client:
    user = User.objects.create_user(email, "Kamen-Most-Rijeka-71", is_staff=staff)
    client = Client()
    client.force_login(user)
    return client


def asked(client_id: str, **given) -> str:
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": BACK,
        "scope": "openid email profile",
        "state": "xyz",
        "nonce": "n-1",
        **given,
    }
    return f"/api/identity/authorize?{urlencode({k: v for k, v in query.items() if v is not None})}"


def code_from(answer) -> str:
    assert answer.status_code == 200, answer.content
    back = urlsplit(answer.json()["redirect"])
    assert f"{back.scheme}://{back.netloc}{back.path}" == BACK
    query = parse_qs(back.query)
    assert query["state"] == ["xyz"]
    return query["code"][0]


def exchanged(application: dict, code: str, basic=True, **given):
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": BACK, **given}
    if basic:
        pair = f"{application['client_id']}:{application['secret']}".encode()
        headers = {"HTTP_AUTHORIZATION": f"Basic {base64.b64encode(pair).decode()}"}
    else:
        form |= {"client_id": application["client_id"], "client_secret": application["secret"]}
        headers = {}
    return Client().post("/api/identity/token", form, **headers)


def test_an_application_finds_the_doors_and_the_key_it_verifies_with():
    found = Client().get("/api/identity/.well-known/openid-configuration").json()
    assert found["issuer"] == ISSUER
    assert found["authorization_endpoint"] == f"{settings.PUBLIC_URL}/authorize"
    assert found["code_challenge_methods_supported"] == ["S256"]
    keys = Client().get(found["jwks_uri"].removeprefix(settings.PUBLIC_URL)).json()["keys"]
    assert [(key["kty"], key["alg"], key["use"], "key_ops" in key) for key in keys] == [
        ("RSA", "RS256", "sig", False)
    ]


def test_a_signed_in_user_comes_back_with_a_code_that_says_who_they_are(
    administrator, registered, owner
):
    assert administrator.get(asked(registered["client_id"])).json() == {"application": "Code"}
    code = code_from(administrator.post(asked(registered["client_id"])))
    answer = exchanged(registered, code)
    assert answer.status_code == 200, answer.content
    assert answer["Cache-Control"] == "no-store"
    given = answer.json()
    keys = jwt.PyJWKSet.from_dict({"keys": tokens.published()})
    header = jwt.get_unverified_header(given["id_token"])
    identity = jwt.decode(
        given["id_token"],
        keys[header["kid"]].key,
        algorithms=["RS256"],
        audience=registered["client_id"],
        issuer=ISSUER,
    )
    assert identity["sub"] == str(owner.pk)
    assert identity["email"] == "ivo@example.com" and identity["email_verified"] is True
    assert identity["name"] == "Ivo Bošković" and identity["nonce"] == "n-1"
    half = hashlib.sha256(given["access_token"].encode()).digest()[:16]
    assert identity["at_hash"] == base64.urlsafe_b64encode(half).decode().rstrip("=")
    profile = Client().get(
        "/api/identity/userinfo", HTTP_AUTHORIZATION=f"Bearer {given['access_token']}"
    )
    assert profile.json()["preferred_username"] == "ivo@example.com"
    assert Application.objects.get().used_at is not None


def test_a_code_opens_once_for_its_own_application_and_address(administrator, registered):
    code = code_from(administrator.post(asked(registered["client_id"])))
    assert exchanged(registered, code, basic=False).status_code == 200
    assert exchanged(registered, code).json() == {"error": "invalid_grant"}
    code = code_from(administrator.post(asked(registered["client_id"])))
    assert exchanged(registered, code, redirect_uri=f"{BACK}/elsewhere").status_code == 400
    assert not Code.objects.exists()
    wrong = {**registered, "secret": "guessed"}
    code = code_from(administrator.post(asked(registered["client_id"])))
    refused = exchanged(wrong, code)
    assert (refused.status_code, refused.json()) == (401, {"error": "invalid_client"})


def test_a_challenge_holds_the_code_to_the_verifier_that_made_it(administrator, registered):
    verifier = secrets.token_urlsafe(48)
    challenged = asked(
        registered["client_id"], code_challenge=challenge_of(verifier), code_challenge_method="S256"
    )
    code = code_from(administrator.post(challenged))
    assert exchanged(registered, code, code_verifier="another").status_code == 400
    code = code_from(administrator.post(challenged))
    assert exchanged(registered, code, code_verifier=verifier).status_code == 200
    plain = asked(registered["client_id"], code_challenge=verifier, code_challenge_method="plain")
    back = parse_qs(urlsplit(administrator.post(plain).json()["redirect"]).query)
    assert back["error"] == ["invalid_request"]


def test_an_unknown_application_or_address_is_answered_here_never_sent_on(
    administrator, registered
):
    unknown = administrator.post(asked("nobody"))
    assert (unknown.status_code, unknown.json()) == (404, {"error": "unknown_application"})
    elsewhere = administrator.post(
        asked(registered["client_id"], redirect_uri="https://evil.test/")
    )
    assert (elsewhere.status_code, elsewhere.json()) == (400, {"error": "unknown_redirect"})
    no_openid = administrator.post(asked(registered["client_id"], scope="email"))
    assert parse_qs(urlsplit(no_openid.json()["redirect"]).query)["error"] == ["invalid_scope"]


def test_only_administrators_sign_in_until_the_application_is_for_everyone(
    administrator, registered
):
    colleague = signed_in_as("ana@example.com")
    refused = colleague.post(asked(registered["client_id"]))
    assert (refused.status_code, refused.json()) == (403, {"error": "not_allowed"})
    opened = administrator.patch(
        f"/api/identity/applications/{registered['id']}",
        {"name": "Code", "redirect_uris": [BACK], "everyone": True},
        content_type="application/json",
    )
    assert opened.json()["everyone"] is True
    code = code_from(colleague.post(asked(registered["client_id"])))
    assert exchanged(registered, code).status_code == 200


def test_an_access_token_stops_answering_once_its_application_or_user_is_gone(
    administrator, registered, owner
):
    code = code_from(administrator.post(asked(registered["client_id"])))
    access = exchanged(registered, code).json()["access_token"]
    owner.is_active = False
    owner.save()
    gone = Client().get("/api/identity/userinfo", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert gone.status_code == 401
    assert Client().get(
        "/api/identity/userinfo", HTTP_AUTHORIZATION="Bearer x.y.z"
    ).status_code == (401)


def test_a_new_secret_replaces_the_old_and_only_administrators_see_the_list(
    administrator, registered
):
    renewed = administrator.post(f"/api/identity/applications/{registered['id']}/secret")
    assert renewed.status_code == 201 and renewed.json()["secret"] != registered["secret"]
    code = code_from(administrator.post(asked(registered["client_id"])))
    assert exchanged(registered, code).status_code == 401
    listed = administrator.get("/api/identity/applications").json()
    assert listed["issuer"] == ISSUER
    assert [each["name"] for each in listed["applications"]] == ["Code"]
    assert "secret" not in listed["applications"][0]
    assert signed_in_as("ana@example.com").get("/api/identity/applications").status_code == 403
    invalid = administrator.post(
        "/api/identity/applications",
        {"name": "Wiki", "redirect_uris": ["ftp://wiki"]},
        content_type="application/json",
    )
    assert invalid.json() == {"error": "redirect_invalid"}
    assert administrator.delete(f"/api/identity/applications/{registered['id']}").status_code == 204


def test_a_key_sealed_under_another_secret_key_gives_way_to_a_new_one(settings):
    first = tokens.published()[0]["kid"]
    tokens._opened.clear()
    settings.SECRET_KEY = "another"
    assert tokens.published()[0]["kid"] != first
    assert Key.objects.count() == 1
