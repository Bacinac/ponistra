import base64

import httpx2
import pytest
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from django.test import Client

from apps.access.tests.test_access import JSON, person
from apps.computers import install
from apps.computers.tests.test_computers import administrator, confirmed

KEY = "ssh-ed25519 " + base64.b64encode(b"\0\0\0\x0bssh-ed25519" + bytes(36)).decode() + " ana@lap"
ANSWERS = {
    "language": "hr",
    "keyboard": "hr",
    "role": "workstation",
    "hostname": "Recepcija",
    "network": "192.0.2.20/24 gateway 192.0.2.1 dns 1.1.1.1",
    "wifi": "Ured",
    "wifi_password": "lozinka-ureda",
    "ssh_key": [KEY, "https://github.com/ana.keys"],
    "password": "admin lozinka",
    "erase": True,
}


def lines_of(conf: str) -> list[tuple[str, str]]:
    found = []
    for line in conf.splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            found.append((key.strip(), value.strip()))
    return found


@pytest.mark.django_db
def test_a_stick_carries_the_answers_a_code_and_the_password_hashed(settings):
    settings.PUBLIC_URL = "https://ponistra.example.com"
    staff = administrator()
    made = staff.post("/api/computers/install", ANSWERS, content_type=JSON)
    assert made.status_code == 201, made.json()
    lines = lines_of(made.json()["conf"])
    found = dict(lines)
    assert found["ponistra_url"] == "https://ponistra.example.com/"
    assert found["ponistra_code"] == made.json()["code"]
    assert found["hostname"] == "recepcija" and found["erase"] == "all"
    assert found["network"] == ANSWERS["network"] and found["secret"] == ""
    assert [value for key, value in lines if key == "ssh_key"] == ANSWERS["ssh_key"]
    assert found["password"].startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    Argon2id.verify_phc_encoded(b"admin lozinka", found["password"])
    enrolled = Client().post(
        "/api/computers/enroll",
        {"code": found["ponistra_code"], "name": "recepcija"},
        content_type=JSON,
    )
    assert enrolled.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"language": "de"}, "invalid_language"),
        ({"hostname": "-x"}, "invalid_name"),
        ({"network": "192.0.2.0/24 gateway 192.0.2.1"}, "invalid_network"),
        ({"network": "192.0.2.20/24 gateway 10.0.0.1"}, "invalid_network"),
        ({"wifi_password": ""}, "invalid_wifi"),
        ({"wifi_password": "short"}, "invalid_wifi_password"),
        ({"role": "server"}, "wifi_server"),
        ({"ssh_key": ["ssh-ed25519 AAAA"]}, "invalid_ssh_key"),
        ({"ssh_key": ["none", KEY]}, "invalid_ssh_key"),
        ({"password": "kratka"}, "invalid_password"),
        ({"erase": "yes"}, "invalid_erase"),
    ],
)
def test_answers_the_installer_would_refuse_are_refused(settings, change, error):
    settings.PUBLIC_URL = "https://ponistra.example.com"
    given = {**ANSWERS, **change}
    answer = administrator().post("/api/computers/install", given, content_type=JSON)
    assert answer.json() == {"error": error}


@pytest.mark.django_db
def test_only_an_administrator_over_https_makes_a_stick(settings):
    plain = person("ana@example.com")
    confirmed(plain)
    assert plain.post("/api/computers/install", ANSWERS, content_type=JSON).status_code == 403
    settings.PUBLIC_URL = "http://localhost:5173"
    answer = administrator().post("/api/computers/install", ANSWERS, content_type=JSON)
    assert answer.json() == {"error": "public_url_not_https"}


class Release:
    def __init__(self, given):
        self.given = given

    def __call__(self, **_):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url):
        assert url == install.RELEASE
        return httpx2.Response(200, json=self.given, request=httpx2.Request("GET", url))


@pytest.mark.django_db
def test_the_sticks_are_the_current_release(monkeypatch):
    stick = {"url": "https://download.boskovic.biz/x.img", "size": 5, "sha256": "A" * 64}
    monkeypatch.setattr(
        install.httpx2, "Client", Release({"version": "0.2.31", "network": stick, "full": stick})
    )
    client = person("ana@example.com")
    found = client.get("/api/computers/sticks").json()
    assert found["version"] == "0.2.31" and found["full"]["sha256"] == "a" * 64
    monkeypatch.setattr(install.httpx2, "Client", Release({"version": "0.2.31"}))
    assert client.get("/api/computers/sticks").json() == {"error": "release_unreachable"}
