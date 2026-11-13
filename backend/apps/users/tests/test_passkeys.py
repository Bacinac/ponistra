import hashlib
import json
import os

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.test import Client
from webauthn.helpers import bytes_to_base64url

from apps.users.models import Passkey, Policy, User

pytestmark = pytest.mark.django_db

JSON = "application/json"
ORIGIN = "http://testserver"
PRESENT, VERIFIED, ATTESTED = 0x01, 0x04, 0x40


class Device:
    """An authenticator that keeps one passkey, answering as the browser hands it over."""

    def __init__(self, origin=ORIGIN):
        self.origin = origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential = os.urandom(16)
        self.user = None
        self.count = 0

    def data(self, flags: int, attested: bytes = b"") -> bytes:
        place = hashlib.sha256(b"testserver").digest()
        return place + bytes([flags]) + self.count.to_bytes(4, "big") + attested

    def client(self, kind: str, options: dict) -> bytes:
        given = {"type": kind, "challenge": options["challenge"], "origin": self.origin}
        return json.dumps(given).encode()

    def answer(self, response: dict[str, bytes]) -> dict:
        made = bytes_to_base64url(self.credential)
        encoded = {name: bytes_to_base64url(value) for name, value in response.items()}
        return {"id": made, "rawId": made, "type": "public-key", "response": encoded}

    def create(self, options: dict) -> dict:
        self.user = options["user"]["id"]
        point = self.key.public_key().public_numbers()
        key = {1: 2, 3: -7, -1: 1, -2: point.x.to_bytes(32, "big"), -3: point.y.to_bytes(32, "big")}
        attested = bytes(16) + len(self.credential).to_bytes(2, "big") + self.credential
        data = self.data(PRESENT | VERIFIED | ATTESTED, attested + cbor2.dumps(key))
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": data})
        return self.answer(
            {
                "clientDataJSON": self.client("webauthn.create", options),
                "attestationObject": attestation,
            }
        )

    def get(self, options: dict, flags: int = PRESENT | VERIFIED) -> dict:
        self.count += 1
        client = self.client("webauthn.get", options)
        data = self.data(flags)
        signature = self.key.sign(data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        answer = self.answer(
            {"clientDataJSON": client, "authenticatorData": data, "signature": signature}
        )
        answer["response"]["userHandle"] = self.user
        return answer


def post(client, path, data=None):
    return client.post(path, data or {}, content_type=JSON, headers={"Origin": ORIGIN})


def add(client, device, name="Telefon"):
    options = post(client, "/api/passkeys/options").json()
    return post(client, "/api/passkeys", {"name": name, "credential": device.create(options)})


def sign_in(client, device, **given):
    options = post(client, "/api/auth/passkey/options").json()
    return post(client, "/api/auth/passkey", {"credential": device.get(options, **given)})


@pytest.fixture
def device(api):
    made = Device()
    assert add(api, made).status_code == 201
    api.logout()
    return made


def test_a_passkey_signs_in_without_an_email_or_a_password(api, device):
    signed = sign_in(api, device)
    assert signed.json()["user"]["email"] == "ivo@example.com"
    assert api.get("/api/auth/session").json()["user"]["id"] == api.user.pk
    kept = Passkey.objects.get()
    assert (kept.sign_count, kept.used_at is not None) == (1, True)


def test_an_answer_signs_in_once(api, device):
    options = post(api, "/api/auth/passkey/options").json()
    answer = {"credential": device.get(options)}
    assert post(api, "/api/auth/passkey", answer).status_code == 200
    assert post(api, "/api/auth/passkey", answer).json() == {"error": "invalid_passkey"}


@pytest.mark.parametrize(
    "spoiled",
    [
        lambda device: setattr(device, "origin", "https://elsewhere.example"),
        lambda device: setattr(device, "key", ec.generate_private_key(ec.SECP256R1())),
        lambda device: setattr(device, "user", bytes_to_base64url(b"0")),
    ],
)
def test_a_passkey_that_does_not_answer_for_the_account_is_refused(api, device, spoiled):
    spoiled(device)
    assert sign_in(api, device).json() == {"error": "invalid_passkey"}
    assert api.get("/api/auth/session").json()["user"] is None


def test_a_device_that_did_not_verify_the_person_is_refused(api, device):
    assert sign_in(api, device, flags=PRESENT).json() == {"error": "invalid_passkey"}


def test_the_log_says_why_a_passkey_was_refused(api, device, caplog):
    sign_in(api, device, flags=PRESENT)
    assert "User verification is required" in caplog.text


def test_the_log_shows_a_user_handle_that_is_not_the_accounts(api, device, caplog):
    device.user = bytes_to_base64url(b"0")
    sign_in(api, device)
    assert "the user handle is b'0'" in caplog.text


def test_a_passkey_the_account_no_longer_keeps_is_unknown(api, device):
    Passkey.objects.all().delete()
    assert sign_in(api, device).json() == {"error": "unknown_passkey"}


def test_a_deactivated_account_does_not_sign_in_with_its_passkey(api, device):
    User.objects.filter(pk=api.user.pk).update(is_active=False)
    assert sign_in(api, device).json() == {"error": "invalid_passkey"}


def test_a_passkey_comes_from_the_options_the_account_asked_for(api):
    device = Device()
    options = post(api, "/api/passkeys/options").json()
    assert options["user"]["id"] == bytes_to_base64url(str(api.user.pk).encode())
    assert options["authenticatorSelection"]["residentKey"] == "required"
    answer = {"name": "Telefon", "credential": device.create(options)}
    assert post(api, "/api/passkeys", answer).status_code == 201
    assert post(api, "/api/passkeys", answer).json() == {"error": "invalid_passkey"}
    again = post(api, "/api/passkeys/options").json()
    assert again["excludeCredentials"][0]["id"] == bytes_to_base64url(device.credential)
    twice = {"name": "Telefon", "credential": device.create(again)}
    assert post(api, "/api/passkeys", twice).json() == {"error": "passkey_exists"}


def test_a_passkey_needs_a_name(api):
    options = post(api, "/api/passkeys/options").json()
    answer = {"name": " ", "credential": Device().create(options)}
    assert post(api, "/api/passkeys", answer).status_code == 400
    assert not Passkey.objects.exists()


def test_the_account_names_and_removes_only_its_own_passkeys(api, device):
    Policy.objects.create(passkeys=Policy.Passkeys.NOBODY)
    api.force_login(api.user)
    other = Client()
    other.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71"))
    assert add(other, Device(), "Ana").status_code == 201
    mine, hers = Passkey.objects.order_by("created_at")
    listed = api.get("/api/passkeys").json()["passkeys"]
    assert [(shown["id"], shown["name"]) for shown in listed] == [(mine.pk, "Telefon")]
    renamed = api.patch(f"/api/passkeys/{mine.pk}", {"name": "Laptop"}, content_type=JSON)
    assert renamed.json()["name"] == "Laptop"
    assert (
        api.patch(f"/api/passkeys/{hers.pk}", {"name": "x"}, content_type=JSON).status_code == 404
    )
    assert api.delete(f"/api/passkeys/{hers.pk}").status_code == 404
    assert api.delete(f"/api/passkeys/{mine.pk}").status_code == 204
    assert list(Passkey.objects.values_list("name", flat=True)) == ["Ana"]


def test_the_last_passkey_gone_ends_the_choice_of_signing_in_with_one(api, device):
    Policy.objects.update_or_create(pk=1, defaults={"passkeys": Policy.Passkeys.NOBODY})
    kept = Passkey.objects.get()
    User.objects.filter(pk=kept.user_id).update(sign_in="passkey")
    api.force_login(kept.user)
    assert api.delete(f"/api/passkeys/{kept.pk}").status_code == 204
    assert User.objects.get(pk=kept.user_id).sign_in == ""


def test_passkeys_are_the_signed_in_accounts(client):
    assert client.get("/api/passkeys").status_code == 401
    assert post(client, "/api/passkeys/options").status_code == 401
