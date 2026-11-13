import json

import httpx2
import pytest

from apps.health import views as health
from apps.journal.models import Entry
from apps.meetings import relay
from apps.meetings.models import Guest, Meeting, Relay
from apps.users.models import User

pytestmark = pytest.mark.django_db

KEY = "f3a9c0d1e2b4a5968778695a4b3c2d1e"
TOKEN = "cf-token-0123456789abcdef"


@pytest.fixture
def owner():
    return User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo")


@pytest.fixture
def admin(client, owner):
    owner.is_staff = True
    owner.save()
    client.force_login(owner)
    return client


@pytest.fixture
def cloudflare(monkeypatch):
    """Cloudflare's TURN service as it answers: credentials of a day for a key and its token,
    in the list it gives today, stun and port 53 among them."""
    asked = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        asked.append(request)
        if request.headers["Authorization"] != f"Bearer {TOKEN}":
            return httpx2.Response(401, json={"error": "unauthorized"})
        if request.url.path != f"/v1/turn/keys/{KEY}/credentials/generate-ice-servers":
            return httpx2.Response(404, json={"error": "not found"})
        assert json.loads(request.content) == {"ttl": relay.LASTING}
        return httpx2.Response(
            201,
            json={
                "iceServers": [
                    {"urls": ["stun:stun.cloudflare.com:3478", "stun:stun.cloudflare.com:53"]},
                    {
                        "urls": [
                            "turn:turn.cloudflare.com:3478?transport=udp",
                            "turn:turn.cloudflare.com:53?transport=udp",
                            "turn:turn.cloudflare.com:3478?transport=tcp",
                            "turns:turn.cloudflare.com:5349?transport=tcp",
                            "turns:turn.cloudflare.com:443?transport=tcp",
                        ],
                        "username": f"user{len(asked)}",
                        "credential": f"credential{len(asked)}",
                    },
                ]
            },
        )

    monkeypatch.setattr(
        relay, "client", lambda: httpx2.Client(transport=httpx2.MockTransport(answer))
    )
    relay._minted.clear()
    yield asked
    relay._minted.clear()


def sent(client, **data):
    return client.patch("/api/meetings/relay", json.dumps(data), content_type="application/json")


def joined(client, owner) -> dict:
    meeting = Meeting.objects.made("Dogovor", owner)
    return client.post(f"/api/meetings/{meeting.id}/join")


def test_without_a_relay_browsers_join_with_what_livekit_offers(admin, owner):
    assert admin.get("/api/meetings/relay").json() == {
        "provider": "",
        "addresses": [],
        "name": "",
        "hint": "",
        "lost": False,
        "changed_at": None,
    }
    answer = joined(admin, owner)
    assert answer.status_code == 200
    assert answer.json()["ice"] is None


def test_cloudflare_gives_each_joining_credentials_of_a_day(admin, owner, cloudflare):
    saved = sent(admin, provider="cloudflare", name=KEY, secret=f" {TOKEN} ")
    assert saved.status_code == 200
    assert saved.json() | {"changed_at": None} == {
        "provider": "cloudflare",
        "addresses": [],
        "name": KEY,
        "hint": TOKEN[-4:],
        "lost": False,
        "changed_at": None,
    }
    assert TOKEN not in json.dumps(saved.json())
    assert TOKEN.encode() not in bytes(Relay.objects.get().secret)
    assert Entry.objects.filter(kind="setting_changed").count() == 1

    ice = joined(admin, owner).json()["ice"]
    assert ice == [
        {"urls": ["stun:stun.cloudflare.com:3478"]},
        {
            "urls": [
                "turn:turn.cloudflare.com:3478?transport=udp",
                "turn:turn.cloudflare.com:3478?transport=tcp",
                "turns:turn.cloudflare.com:5349?transport=tcp",
                "turns:turn.cloudflare.com:443?transport=tcp",
            ],
            "username": "user2",
            "credential": "credential2",
        },
    ]
    assert joined(admin, owner).json()["ice"] == ice
    assert len(cloudflare) == 2


def test_credentials_are_minted_anew_before_a_meeting_could_outlast_them(
    admin, owner, cloudflare, monkeypatch
):
    sent(admin, provider="cloudflare", name=KEY, secret=TOKEN)
    joined(admin, owner)
    now = relay.time.time()
    monkeypatch.setattr(relay.time, "time", lambda: now + relay.LASTING - relay.LEFT + 1)
    assert joined(admin, owner).json()["ice"][1]["username"] == "user3"


def test_a_key_cloudflare_refuses_is_not_kept(admin, cloudflare):
    refused = sent(admin, provider="cloudflare", name=KEY, secret="wrong")
    assert (refused.status_code, refused.json()["error"]) == (422, "relay_refused")
    assert not Relay.objects.exists()


def test_a_guest_joins_through_the_relay_too(client, admin, owner, cloudflare):
    sent(admin, provider="cloudflare", name=KEY, secret=TOKEN)
    meeting = Meeting.objects.made("Dogovor", owner)
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.ADMITTED)
    client.logout()
    answer = client.post(
        f"/api/meetings/{meeting.id}/guests/join",
        json.dumps({"key": guest.key}),
        content_type="application/json",
    )
    assert answer.json()["ice"][1]["urls"][0] == "turn:turn.cloudflare.com:3478?transport=udp"


def test_another_provider_is_its_addresses_name_and_password(admin, owner):
    saved = sent(
        admin,
        provider="turn",
        addresses=["turn:relay.example.com:3478", " turns:relay.example.com:443?transport=tcp "],
        name="ponistra",
        secret="Lozinka-Releja-9",
    )
    assert saved.json()["addresses"] == [
        "turn:relay.example.com:3478",
        "turns:relay.example.com:443?transport=tcp",
    ]
    assert joined(admin, owner).json()["ice"] == [
        {
            "urls": ["turn:relay.example.com:3478", "turns:relay.example.com:443?transport=tcp"],
            "username": "ponistra",
            "credential": "Lozinka-Releja-9",
        }
    ]
    kept = sent(admin, provider="turn", addresses=["turn:other.example.com"], name="ponistra")
    assert kept.json()["hint"] == "ja-9"
    assert joined(admin, owner).json()["ice"][0]["credential"] == "Lozinka-Releja-9"


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({"provider": "turn", "addresses": [], "name": "a", "secret": "b"}, "relay_address_needed"),
        (
            {"provider": "turn", "addresses": ["https://x.example"], "name": "a", "secret": "b"},
            "invalid_relay_address",
        ),
        ({"provider": "turn", "addresses": ["turn:x.example"], "name": "a"}, "relay_secret_needed"),
        ({"provider": "cloudflare", "name": "", "secret": "b"}, "relay_name_needed"),
    ],
)
def test_an_incomplete_relay_is_refused(admin, data, error):
    refused = sent(admin, **data)
    assert (refused.status_code, refused.json()["error"]) == (422, error)


def test_turning_the_relay_off_forgets_its_secret(admin, owner, cloudflare):
    sent(admin, provider="cloudflare", name=KEY, secret=TOKEN)
    off = sent(admin, provider="")
    assert off.json()["provider"] == "" and off.json()["hint"] == ""
    assert bytes(Relay.objects.get().secret) == b""
    assert joined(admin, owner).json()["ice"] is None


def test_a_relay_that_cannot_be_had_stops_the_joining_loudly(admin, owner, cloudflare):
    sent(admin, provider="cloudflare", name=KEY, secret=TOKEN)
    Relay.objects.update(secret=b"sealed under another installation's secret")
    assert admin.get("/api/meetings/relay").json()["lost"] is True
    answer = joined(admin, owner)
    assert (answer.status_code, answer.json()["error"]) == (503, "relay_lost")


def test_only_an_administrator_sees_the_relay(client, owner):
    client.force_login(owner)
    assert client.get("/api/meetings/relay").status_code == 403
    assert sent(client, provider="").status_code == 403


def test_health_follows_the_external_relay_once_one_is_set(admin, cloudflare, monkeypatch):
    monkeypatch.setattr(health, "answers", lambda address: True)
    assert "outside" not in health.services()
    sent(admin, provider="cloudflare", name=KEY, secret=TOKEN)
    assert health.services()["outside"] is True
    relay._minted.clear()
    Relay.objects.update(name="revoked")
    assert health.services()["outside"] is False
