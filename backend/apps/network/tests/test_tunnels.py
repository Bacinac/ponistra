import socket
import threading

import pytest

from apps.core import sealed
from apps.journal.models import Entry
from apps.network import tunnels, wireguard
from apps.network.models import Tunnel
from apps.users.models import User

pytestmark = pytest.mark.django_db

PRIVATE = "yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk="
PUBLIC = "xTIBA5rboUvnH4htodjb6e697QjLERt1NAB4mZqp8Dg="
SHARED = "FpCyhws9cxwWoV4xELtfJvjJN+zQVRPISllRWgeopVE="
CONFIGURATION = f"""
[Interface]
# the office
PrivateKey = {PRIVATE}
Address = 10.8.0.2
DNS = 10.8.0.1, office.example.com
MTU = 1380
PostUp = iptables -A FORWARD -i %i -j ACCEPT

[Peer]
PublicKey = {PUBLIC}
PresharedKey = {SHARED}
Endpoint = vpn.example.com:51820
AllowedIPs = 10.8.0.0/24, 192.168.50.0/24
PersistentKeepalive = 15
"""
SOFTETHER = {
    "kind": "softether",
    "name": "Office",
    "server": "vpn.example.com",
    "hub": "VPN",
    "username": "ivob",
    "password": "se cret",
}


@pytest.fixture
def admin(client):
    client.force_login(User.objects.create_superuser("ivo@example.com", "Kamen-Most-Rijeka-71"))
    return client


class Service:
    """The service `tunnel` as the backend asks it: it holds what it was handed last and tells
    each tunnel it holds connecting."""

    def __init__(self):
        self.handed = None
        self.answering = True

    def __call__(self, method, path, body=None, timeout=None):
        if not self.answering:
            raise OSError("Name or service not known")
        if method == "PUT":
            self.handed = body
        held = self.handed["tunnels"] if self.handed else []
        return {
            "boot": "b1",
            "gen": 1,
            "applied": self.handed["digest"] if self.handed else "",
            "tunnels": {each["id"]: {"state": "connecting"} for each in held},
        }


@pytest.fixture
def service(monkeypatch):
    found = Service()
    monkeypatch.setattr(tunnels, "_asked", found)
    return found


def test_a_wireguard_configuration_is_read_as_the_service_runs_it():
    assert wireguard.parsed(CONFIGURATION) == {
        "private_key": PRIVATE,
        "addresses": ["10.8.0.2/32"],
        "dns": ["10.8.0.1"],
        "mtu": 1380,
        "peers": [
            {
                "public_key": PUBLIC,
                "preshared_key": SHARED,
                "endpoint": "vpn.example.com:51820",
                "allowed_ips": ["10.8.0.0/24", "192.168.50.0/24"],
                "keepalive": 15,
            }
        ],
    }


@pytest.mark.parametrize(
    "broken",
    [
        CONFIGURATION.replace(PRIVATE, "c2hvcnQ="),
        CONFIGURATION.replace("Endpoint = vpn.example.com:51820", ""),
        CONFIGURATION.replace("vpn.example.com:51820", "vpn.example.com"),
        CONFIGURATION.replace("Address = 10.8.0.2", "Address = ten"),
        CONFIGURATION.replace("[Peer]", "[Other]"),
        CONFIGURATION.replace("MTU = 1380", "MTU = lots"),
        "PrivateKey = " + PRIVATE,
        "",
    ],
)
def test_a_configuration_the_service_cannot_run_is_refused(broken):
    with pytest.raises(wireguard.Invalid):
        wireguard.parsed(broken)


def test_only_an_administrator_reads_the_tunnels(api):
    assert api.get("/api/network/tunnels").status_code == 403


def test_a_wireguard_tunnel_is_kept_sealed_and_handed_to_the_service(admin, service):
    made = admin.post(
        "/api/network/tunnels",
        {"kind": "wireguard", "name": " Office ", "configuration": CONFIGURATION},
        content_type="application/json",
    )
    assert made.status_code == 201, made.content
    shown = made.json()
    assert shown["name"] == "Office"
    assert shown["shown"] == {"address": "10.8.0.2", "endpoint": "vpn.example.com:51820"}
    assert shown["state"] == "connecting"
    found = Tunnel.objects.get()
    assert PRIVATE.encode() not in bytes(found.sealed)
    assert sealed.opened(tunnels.SEALED["wireguard"], found.sealed) == CONFIGURATION
    [spec] = service.handed["tunnels"]
    assert spec == {
        "id": str(found.pk),
        "kind": "wireguard",
        "wireguard": wireguard.parsed(CONFIGURATION),
    }
    entry = Entry.objects.get(kind="setting_changed")
    assert entry.detail == {"setting": "network_tunnel", "name": "Office", "change": "added"}
    assert PRIVATE not in str(admin.get("/api/network/tunnels").json())


def test_a_softether_tunnel_keeps_its_password_when_changed_without_one(admin, service):
    made = admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json").json()
    assert made["shown"] == {
        "server": "vpn.example.com",
        "hub": "VPN",
        "username": "ivob",
        "port": 443,
    }
    changed = admin.patch(
        f"/api/network/tunnels/{made['id']}",
        {"port": 5555, "password": ""},
        content_type="application/json",
    )
    assert changed.status_code == 200, changed.content
    [spec] = service.handed["tunnels"]
    assert spec["softether"] == {
        "server": "vpn.example.com",
        "port": 5555,
        "hub": "VPN",
        "username": "ivob",
        "password": "se cret",
    }


@pytest.mark.parametrize(
    ("given", "error"),
    [
        ({"server": "vpn example"}, "invalid_server"),
        ({"hub": "/HUB:other"}, "invalid_hub"),
        ({"username": ""}, "invalid_username"),
        ({"port": 70000}, "invalid_port"),
        ({"port": True}, "invalid_port"),
        ({"password": ""}, "secret_required"),
        ({"password": "one\ntwo"}, "invalid_password"),
        ({"name": ""}, "invalid_name"),
        ({"kind": "openvpn"}, "invalid_kind"),
    ],
)
def test_a_softether_tunnel_the_service_cannot_run_is_refused(admin, service, given, error):
    answer = admin.post(
        "/api/network/tunnels", {**SOFTETHER, **given}, content_type="application/json"
    )
    assert (answer.status_code, answer.json()["error"]) == (400, error)
    assert not Tunnel.objects.exists()


def test_a_broken_wireguard_configuration_is_refused(admin, service):
    answer = admin.post(
        "/api/network/tunnels",
        {"kind": "wireguard", "name": "Office", "configuration": "[Interface]\n"},
        content_type="application/json",
    )
    assert (answer.status_code, answer.json()["error"]) == (400, "invalid_wireguard")


def test_two_tunnels_take_no_one_name(admin, service):
    admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json")
    again = admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json")
    assert (again.status_code, again.json()["error"]) == (409, "tunnel_taken")


def test_a_tunnel_switched_off_leaves_the_service(admin, service):
    made = admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json").json()
    off = admin.patch(
        f"/api/network/tunnels/{made['id']}", {"enabled": False}, content_type="application/json"
    ).json()
    assert (off["enabled"], off["state"]) == (False, "off")
    assert service.handed["tunnels"] == []
    on = admin.patch(
        f"/api/network/tunnels/{made['id']}", {"enabled": True}, content_type="application/json"
    ).json()
    assert on["state"] == "connecting"
    assert len(service.handed["tunnels"]) == 1


def test_a_removed_tunnel_leaves_the_service(admin, service):
    made = admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json").json()
    assert admin.delete(f"/api/network/tunnels/{made['id']}").status_code == 204
    assert service.handed["tunnels"] == []
    assert not Tunnel.objects.exists()


def test_a_service_that_does_not_answer_is_told_and_the_tunnel_kept(admin, service):
    service.answering = False
    made = admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json")
    assert made.status_code == 201
    assert made.json()["state"] == "unreached"


def test_the_state_changes_as_the_service_tells_it(admin, service):
    made = admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json").json()
    key = str(made["id"])
    since = Tunnel.objects.get().since
    tunnels.told({"tunnels": {key: {"state": "connecting", "error": "refused", "detail": "no"}}})
    found = Tunnel.objects.get()
    assert (found.state, found.error, found.detail, found.since) == (
        "connecting",
        "refused",
        "no",
        since,
    )
    tunnels.told({"tunnels": {key: {"state": "up", "address": "192.168.1.152"}}})
    found = Tunnel.objects.get()
    assert (found.state, found.error, found.address) == ("up", "", "192.168.1.152")
    assert found.since > since


def test_a_tunnel_whose_secret_no_longer_opens_is_failed_and_not_handed(admin, service):
    admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json")
    Tunnel.objects.update(sealed=b"sealed with another key")
    assert tunnels.handed()["tunnels"] == []
    found = Tunnel.objects.get()
    assert (found.state, found.error) == ("failed", "sealed")


def test_the_digest_follows_every_tunnel(admin, service):
    admin.post("/api/network/tunnels", SOFTETHER, content_type="application/json")
    first = tunnels.handed()["digest"]
    assert tunnels.handed()["digest"] == first
    Tunnel.objects.update(shown={**Tunnel.objects.get().shown, "port": 444})
    assert tunnels.handed()["digest"] != first


class _Stopped(Exception):
    pass


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_the_service_started_again_is_handed_the_tunnels(monkeypatch, caplog):
    await Tunnel.objects.acreate(
        name="Office",
        kind="softether",
        shown={"server": "vpn.example.com", "port": 443, "hub": "VPN", "username": "ivob"},
        sealed=tunnels.seal("softether", "se cret"),
    )
    asked = []
    boots = iter(["b1", "b1", "b2", "b2"])

    def service(method, path, body=None, timeout=None):
        asked.append(method)
        if len(asked) == 5:
            raise OSError("connection refused")
        applied = body["digest"] if body else service.applied
        service.applied = applied
        return {"boot": next(boots), "gen": 1, "applied": applied, "tunnels": {}}

    service.applied = ""

    async def slept(seconds):
        raise _Stopped

    monkeypatch.setattr(tunnels, "_asked", service)
    monkeypatch.setattr(tunnels, "sleep", slept)
    with pytest.raises(_Stopped):
        await tunnels.follow()
    assert asked == ["PUT", "GET", "GET", "PUT", "GET"]
    assert (await Tunnel.objects.aget()).state == "unreached"
    assert "started again" in caplog.text
    assert "does not answer" in caplog.text


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_without_tunnels_the_service_is_not_asked(monkeypatch):
    def service(*given, **named):
        raise AssertionError("asked")

    async def slept(seconds):
        raise _Stopped

    monkeypatch.setattr(tunnels, "_asked", service)
    monkeypatch.setattr(tunnels, "sleep", slept)
    with pytest.raises(_Stopped):
        await tunnels.follow()


@pytest.fixture
def socks(monkeypatch):
    """A SOCKS5 server holding the tunnel 7, behind which every host answers `far side`."""
    listener = socket.create_server(("127.0.0.1", 0))
    asked = []

    def serve():
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                connection.recv(3)
                connection.sendall(b"\x05\x02")
                head = connection.recv(2)
                user = connection.recv(head[1]).decode()
                connection.recv(connection.recv(1)[0])
                if user != "7":
                    connection.sendall(b"\x01\x01")
                    continue
                connection.sendall(b"\x01\x00")
                request = connection.recv(5)
                name = connection.recv(request[4]).decode()
                port = int.from_bytes(connection.recv(2))
                asked.append((name, port))
                connection.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00far side")

    threading.Thread(target=serve, daemon=True).start()
    monkeypatch.setattr(tunnels, "SOCKS", listener.getsockname())
    yield asked
    listener.close()


def test_a_host_behind_a_tunnel_is_reached_through_the_service(socks):
    with tunnels.opened(7, "nas.office", 445) as connection:
        assert connection.recv(8) == b"far side"
    assert socks == [("nas.office", 445)]
    with pytest.raises(OSError, match="holds no tunnel 8"):
        tunnels.opened(8, "nas.office", 445)
