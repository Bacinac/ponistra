import pytest

from apps.journal.models import Entry
from apps.network import address
from apps.network.models import Dns
from apps.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(client):
    client.force_login(User.objects.create_superuser("ivo@example.com", "Kamen-Most-Rijeka-71"))
    return client


@pytest.fixture(autouse=True)
def seen(monkeypatch, settings):
    """An installation the internet sees at 203.0.113.139, whose LiveKit answers there, and a
    Cloudflare that knows only the token `good-token`."""
    settings.TURN = "turn.example.org"
    settings.DIRECT_NAMES = ["turn.example.org"]
    settings.LIVEKIT_UDP_PORT, settings.LIVEKIT_TCP_PORT = 7882, 7881
    monkeypatch.setattr(address, "public", lambda timeout=None: "203.0.113.139")
    monkeypatch.setattr(address, "reached", lambda: True)
    monkeypatch.setattr(address, "verified", lambda token: token == "good-token")


def test_only_an_administrator_reads_the_network(api):
    assert api.get("/api/network").status_code == 403


def test_the_network_says_where_the_installation_is_seen_and_what_reaches_it(admin):
    assert admin.get("/api/network").json() == {
        "address": "203.0.113.139",
        "reached": True,
        "ports": {"udp": 7882, "tcp": 7881},
        "relay": "turn.example.org",
        "names": ["turn.example.org"],
        "dns": {"hint": "", "lost": False, "error": "", "changed_at": None},
    }


def test_no_public_address_means_not_reached(admin, monkeypatch):
    def unseen(timeout=None):
        raise OSError("timed out")

    monkeypatch.setattr(address, "public", unseen)
    shown = admin.get("/api/network").json()
    assert (shown["address"], shown["reached"]) == (None, False)


def test_a_token_is_tried_kept_sealed_and_forgotten(admin):
    refused = admin.patch("/api/network", {"token": "bad-token"}, content_type="application/json")
    assert (refused.status_code, refused.json()["error"]) == (422, "dns_token_refused")
    assert not Dns.objects.exists()

    saved = admin.patch("/api/network", {"token": " good-token "}, content_type="application/json")
    assert saved.json()["dns"]["hint"] == "oken"
    found = Dns.objects.get()
    assert b"good-token" not in bytes(found.token)
    assert address.opened(found) == "good-token"
    entry = Entry.objects.get(kind="setting_changed")
    assert entry.detail == {"setting": "network_dns", "secret": True}

    Dns.objects.update(error="Cloudflare 403")
    cleared = admin.patch("/api/network", {"token": ""}, content_type="application/json").json()
    assert cleared["dns"]["hint"] == "" and cleared["dns"]["error"] == ""
    assert address.opened(Dns.objects.get()) is None


def test_a_token_that_is_not_text_is_refused(admin):
    answer = admin.patch("/api/network", {"token": 7}, content_type="application/json")
    assert (answer.status_code, answer.json()["error"]) == (400, "invalid_dns_token")
