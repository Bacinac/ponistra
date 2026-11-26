import base64
import io
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.models import Group
from django.db import connections
from django.test import AsyncClient

from apps.access.tests.test_access import JSON, person
from apps.blobs.tests.uploads import uploaded
from apps.locations import reach, sftp, smbfiles
from apps.locations.models import Location
from apps.locations.remote import Entry, Failed
from apps.network.models import Tunnel
from apps.network.tests.far import HELD
from apps.users.models import Policy, User

pytestmark = pytest.mark.django_db

SERVER = {"host": "sftp", "username": "sftp", "password": "sftpsftp"}


def target(path: str, **changed) -> sftp.Target:
    fields = {
        "host": "sftp",
        "port": 22,
        "user": "sftp",
        "path": path,
        "password": "sftpsftp",
        "key": None,
        "jump": "",
        "known_hosts": "",
    }
    return sftp.Target(**(fields | changed))


async def _on_server(path: str, work):
    link = reach.over_ssh(target(path))
    await link.open()
    try:
        return await work(sftp.Sftp(link))
    finally:
        link.end(Failed("location_closed"))


def on_server(work, path: str = "files"):
    return async_to_sync(_on_server)(path, work)


@pytest.fixture
def spot():
    """A folder of the test server for one test alone, as workers share the server."""
    name = uuid.uuid4().hex
    on_server(lambda server: server.mkdir(name))
    yield f"files/{name}"
    on_server(lambda server: server.remove(name))


@pytest.fixture
def ana():
    return person("ana@example.com", first_name="Ana")


def post(client, path: str, data: dict):
    return client.post(path, data, content_type=JSON)


def added(client, spot: str, **changed) -> dict:
    given = {"kind": "sftp", "name": "Poslužitelj", "auth": "password", "path": spot}
    response = post(client, "/api/locations", given | SERVER | changed)
    assert response.status_code == 201, response.json()
    return response.json()


def names(client, location: dict, path: str = "") -> list[str]:
    listed = client.get(f"/api/locations/{location['id']}/files", {"path": path})
    assert listed.status_code == 200, listed.json()
    return [entry["name"] for entry in listed.json()["entries"]]


def put(client, location: dict, path: str, name: str, data: bytes):
    blob = uploaded(client, data)
    sent = {"path": path, "name": name, "blob": blob["sha256"]}
    return post(client, f"/api/locations/{location['id']}/put", sent)


def test_a_location_is_added_once_its_account_signs_in_and_keeps_the_servers_keys(api, spot):
    location = added(api, spot)
    assert location["role"] == "own"
    assert location["address"] == f"sftp:{spot}"
    assert "password" not in location
    kept = Location.objects.get()
    assert kept.known_hosts.startswith("sftp ssh-")
    assert b"sftpsftp" not in bytes(kept.secret)
    assert api.get("/api/locations").json() == {
        "locations": [location],
        "adds": True,
        "tunnels": [],
    }


def test_an_account_the_server_refuses_adds_nothing(api, spot):
    refused = post(
        api,
        "/api/locations",
        {"kind": "sftp", "name": "Poslužitelj", "auth": "password", "path": spot}
        | SERVER
        | {"password": "wrong"},
    )
    assert (refused.status_code, refused.json()) == (409, {"error": "location_login"})
    assert not Location.objects.exists()


@pytest.mark.parametrize(
    ("changed", "error"),
    [
        ({"kind": "ftp"}, "invalid_kind"),
        ({"name": ""}, "invalid_location_name"),
        ({"host": "-oProxyCommand=id"}, "invalid_host"),
        ({"username": "-l root"}, "invalid_username"),
        ({"port": 70000}, "invalid_port"),
        ({"jump": "a b"}, "invalid_jump"),
        ({"auth": "agent"}, "invalid_auth"),
        ({"password": ""}, "invalid_password"),
    ],
)
def test_what_a_location_is_set_to_is_checked_before_any_server_is_asked(api, changed, error):
    given = {"kind": "sftp", "name": "Poslužitelj", "auth": "password"} | SERVER | changed
    refused = post(api, "/api/locations", given)
    assert (refused.status_code, refused.json()) == (400, {"error": error})


def test_files_are_listed_made_renamed_moved_and_deleted_on_the_server(api, spot):
    location = added(api, spot)
    files = f"/api/locations/{location['id']}"
    assert post(api, f"{files}/folder", {"path": "", "name": "Ponude"}).status_code == 201
    assert post(api, f"{files}/folder", {"path": "", "name": "Ponude"}).json() == {
        "error": "file_exists"
    }
    assert put(api, location, "", "b.txt", b"drugi").status_code == 201
    assert put(api, location, "", "a10.txt", b"deseti").status_code == 201
    assert put(api, location, "", "a2.txt", b"prvi").status_code == 201
    assert put(api, location, "", "a2.txt", b"opet").json() == {"error": "file_exists"}
    assert names(api, location) == ["Ponude", "a2.txt", "a10.txt", "b.txt"]
    listed = api.get(f"{files}/files").json()["entries"]
    assert (listed[0]["kind"], listed[0]["size"]) == ("folder", None)
    assert (listed[1]["kind"], listed[1]["size"]) == ("file", 4)

    moved = post(api, f"{files}/rename", {"path": "a2.txt", "to": "Ponude/prva.txt"})
    assert moved.json() == {"path": "Ponude/prva.txt"}
    taken = post(api, f"{files}/rename", {"path": "b.txt", "to": "a10.txt"})
    assert taken.json() == {"error": "file_exists"}
    assert names(api, location, "Ponude") == ["prva.txt"]
    assert post(api, f"{files}/remove", {"paths": ["Ponude", "b.txt"]}).status_code == 204
    assert names(api, location) == ["a10.txt"]
    assert api.get(f"{files}/files", {"path": "none"}).status_code == 404


@pytest.mark.parametrize("path", ["../etc", "a/../../b", "a\\b", "a\0b"])
def test_a_path_never_leaves_the_locations_folder(api, spot, path):
    location = added(api, spot)
    refused = api.get(f"/api/locations/{location['id']}/files", {"path": path})
    assert (refused.status_code, refused.json()) == (400, {"error": "invalid_path"})


def test_a_text_file_is_written_back_only_while_it_is_what_was_read(api, spot):
    location = added(api, spot)
    text = f"/api/locations/{location['id']}/text"
    put(api, location, "", "bilješka.txt", b"Prvi redak\n")
    read = api.get(text, {"path": "bilješka.txt"}).json()
    assert (read["kind"], read["text"], read["size"]) == ("text", "Prvi redak\n", 11)
    written = post(
        api, text, {"path": "bilješka.txt", "text": "Drugi redak\n", "hash": read["hash"]}
    )
    assert written.status_code == 200, written.json()
    stale = post(api, text, {"path": "bilješka.txt", "text": "Treći\n", "hash": read["hash"]})
    assert (stale.status_code, stale.json()) == (409, {"error": "changed"})
    assert api.get(text, {"path": "bilješka.txt"}).json()["text"] == "Drugi redak\n"
    put(api, location, "", "slika.bin", b"\0\1\2")
    assert api.get(text, {"path": "slika.bin"}).json()["kind"] == "binary"


def test_a_location_is_shared_as_a_folder_is(api, ana, spot):
    location = added(api, spot)
    files = f"/api/locations/{location['id']}"
    assert ana.get("/api/locations").json()["locations"] == []
    assert ana.get(f"{files}/files").status_code == 404

    shared = post(api, f"{files}/grants", {"kind": "user", "id": ana.user.pk, "role": "read"})
    assert [grant["grantee"]["name"] for grant in shared.json()["grants"]] == ["Ana"]
    seen = ana.get("/api/locations").json()["locations"]
    assert [(each["name"], each["role"]) for each in seen] == [("Poslužitelj", "read")]
    assert "host" not in seen[0] and "username" not in seen[0]
    assert names(ana, location) == []
    assert post(ana, f"{files}/folder", {"path": "", "name": "Moje"}).status_code == 403
    assert ana.patch(files, {"name": "Njezin"}, JSON).status_code == 403
    assert ana.get(f"{files}/grants").status_code == 403

    team = Group.objects.create(name="Prodaja")
    ana.user.groups.add(team)
    post(api, f"{files}/grants", {"kind": "group", "id": team.pk, "role": "edit"})
    assert post(ana, f"{files}/folder", {"path": "", "name": "Moje"}).status_code == 201

    for grant in api.get(f"{files}/grants").json()["grants"]:
        assert api.delete(f"{files}/grants/{grant['id']}").status_code == 204
    assert ana.get(f"{files}/files").status_code == 404
    assert reach.concerned(location["id"]) == {api.user.pk}


def test_an_administrator_decides_who_adds_locations(api, ana, spot):
    location = added(api, spot)
    Policy.objects.update_or_create(defaults={"locations": Policy.Outside.NOBODY})
    assert api.get("/api/locations").json()["adds"] is False
    refused = post(api, "/api/locations", {"kind": "sftp"})
    assert (refused.status_code, refused.json()) == (403, {"error": "locations_off"})
    assert names(api, location) == []

    Policy.objects.update(locations=Policy.Outside.ADMINISTRATORS)
    assert api.get("/api/locations").json()["adds"] is False
    User.objects.filter(pk=api.user.pk).update(is_staff=True)
    assert api.get("/api/locations").json()["adds"] is True


def test_a_location_changed_signs_in_anew_and_a_deleted_one_is_gone(api, spot):
    location = added(api, spot)
    path = f"/api/locations/{location['id']}"
    refused = api.patch(path, {"password": "wrong"}, JSON)
    assert (refused.status_code, refused.json()) == (409, {"error": "location_login"})
    renamed = api.patch(path, {"name": "Arhiva", "jump": "sftp@sftp:22"}, JSON)
    assert (renamed.status_code, renamed.json()["name"]) == (200, "Arhiva")
    assert renamed.json()["jump"] == "sftp@sftp:22"
    assert names(api, location) == []
    assert api.delete(path).status_code == 204
    assert api.get(f"{path}/files").status_code == 404


@pytest.mark.xdist_group("sftp")
def test_a_location_signs_in_with_a_key_made_for_it_once_the_server_knows_it(api, spot):
    location = added(api, spot, auth="key", password=None)
    public = location["public_key"]
    assert public.startswith("ssh-ed25519 ") and " ponistra@" in public
    files = api.get(f"/api/locations/{location['id']}/files")
    assert (files.status_code, files.json()) == (409, {"error": "location_login"})

    async def keys():
        yield f"{public}\n".encode()

    async def trusted(server):
        if not any(entry.name == ".ssh" for entry in await server.listed("")):
            await server.mkdir(".ssh")
        if any(entry.name == "authorized_keys" for entry in await server.listed(".ssh")):
            await server.remove(".ssh/authorized_keys")
        await server.put(".ssh/authorized_keys", keys())

    on_server(trusted, "")
    assert names(api, location) == []
    assert b"PRIVATE KEY" not in bytes(Location.objects.get().secret)


class Shelf:
    """An SMB share as the tests lay it out."""

    reached: list[tuple] = []

    async def listed(self, path: str) -> list[Entry]:
        return [Entry("Ugovori", "folder", None, datetime(2026, 1, 5, tzinfo=UTC))]

    async def close(self) -> None:
        pass


def test_an_smb_location_is_reached_by_its_address(api, monkeypatch):
    async def reached(*given):
        Shelf.reached.append(given)
        if given[4] != "lozinka":
            raise Failed("location_login")
        return Shelf()

    monkeypatch.setattr(smbfiles, "reached", reached)
    given = {"kind": "smb", "name": "Zajednička", "username": "TVRTKA\\ivo"}
    bad = post(api, "/api/locations", given | {"address": "smb://nas", "password": "lozinka"})
    assert (bad.status_code, bad.json()) == (400, {"error": "invalid_address"})
    wrong = post(api, "/api/locations", given | {"address": "\\\\nas\\dokumenti", "password": "x"})
    assert (wrong.status_code, wrong.json()) == (409, {"error": "location_login"})
    location = post(
        api,
        "/api/locations",
        given | {"address": "\\\\nas\\dokumenti\\2026", "password": "lozinka"},
    ).json()
    assert (location["address"], location["port"]) == ("\\\\nas\\dokumenti\\2026", 445)
    assert names(api, location) == ["Ugovori"]
    assert Shelf.reached[-1] == ("nas", 445, "dokumenti\\2026", "TVRTKA\\ivo", "lozinka", None)


def tunnel(pk: int = HELD, **changed) -> Tunnel:
    fields = {"pk": pk, "name": f"Ured {pk}", "kind": "wireguard", "state": "up"}
    return Tunnel.objects.create(**(fields | changed))


@pytest.mark.xdist_group("sftp")
def test_a_location_behind_a_tunnel_is_reached_through_the_tunnel_service(api, spot, far):
    through = tunnel()
    location = added(api, spot, tunnel=through.pk)
    assert location["tunnel"] == {"id": through.pk, "name": "Ured 7"}
    assert far == [("sftp", 22)]
    put(api, location, "", "ponuda.txt", b"Kroz tunel")
    assert names(api, location) == ["ponuda.txt"]
    listed = api.get("/api/locations").json()
    assert listed["tunnels"] == [{"id": through.pk, "name": "Ured 7"}]
    sftp.ended("")


@pytest.mark.xdist_group("sftp")
def test_the_first_hop_goes_through_the_tunnel_and_the_jump_takes_the_rest(api, spot, far):
    location = added(api, spot, tunnel=tunnel().pk, jump="sftp@sftp:22")
    assert names(api, location) == []
    assert far[-1] == ("sftp", 22)
    config = sftp._config(target(spot, jump="sftp@sftp:22", tunnel=7), Path("/x"))
    jump = config.index("Host jump")
    assert config.index("ProxyCommand") > jump
    assert config.count("ProxyCommand") == 1
    assert "ProxyUseFdpass yes" in config
    sftp.ended("")


def test_a_location_behind_a_tunnel_that_is_down_says_so(api, spot, far):
    through = tunnel(state="connecting")
    refused = post(
        api,
        "/api/locations",
        {"kind": "sftp", "name": "Poslužitelj", "auth": "password", "path": spot}
        | SERVER
        | {"tunnel": through.pk},
    )
    assert (refused.status_code, refused.json()) == (409, {"error": "location_tunnel_down"})
    assert far == []


@pytest.mark.parametrize("chosen", ["7", 99, "off"])
def test_a_location_goes_only_through_a_tunnel_switched_on(api, chosen):
    off = tunnel(8, enabled=False, state="off")
    chosen = off.pk if chosen == "off" else chosen
    given = {"kind": "sftp", "name": "Poslužitelj", "auth": "password", "tunnel": chosen}
    refused = post(api, "/api/locations", given | SERVER)
    assert (refused.status_code, refused.json()) == (400, {"error": "invalid_tunnel"})
    assert api.get("/api/locations").json()["tunnels"] == []


@pytest.mark.xdist_group("sftp")
def test_a_tunnel_a_location_goes_through_is_not_removed(api, client, spot, far):
    through = tunnel()
    added(api, spot, tunnel=through.pk)
    client.force_login(User.objects.create_superuser("admin@example.com", "Kamen-Most-Rijeka-71"))
    removed = client.delete(f"/api/network/tunnels/{through.pk}")
    assert (removed.status_code, removed.json()) == (409, {"error": "tunnel_in_use"})
    assert Tunnel.objects.filter(pk=through.pk).exists()
    sftp.ended("")


def test_smb_connects_through_the_tunnel_only_for_a_location_behind_one(far, answering):
    routed = smbfiles.Routed("127.0.0.1", answering, 5)
    smbfiles._through(HELD, routed.connect)
    assert routed._sock.recv(8) == b"far side"
    routed._sock.close()
    assert far == [("127.0.0.1", answering)]
    straight = smbfiles.Routed("127.0.0.1", answering, 5)
    straight.connect()
    assert straight._sock.recv(8) == b"far side"
    straight._sock.close()
    assert len(far) == 1
    down = smbfiles.Routed("127.0.0.1", answering, 5)
    with pytest.raises(ValueError, match="holds no tunnel 8"):
        smbfiles._through(8, down.connect)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_file_is_served_whole_or_by_the_range_a_player_asks_for(spot):
    user = await sync_to_async(User.objects.create_user)("ivo@example.com", "Kamen-Most-Rijeka-71")
    browser = AsyncClient()
    await browser.aforce_login(user)
    given = {"kind": "sftp", "name": "Poslužitelj", "auth": "password", "path": spot} | SERVER
    location = (await browser.post("/api/locations", given, content_type=JSON)).json()
    data = bytes(range(256)) * 600

    async def parts():
        yield data

    await _on_server(spot, lambda server: server.put("zapis.bin", parts()))
    raw = f"/api/locations/{location['id']}/raw"
    try:
        whole = await browser.get(raw, {"path": "zapis.bin"})
        assert whole["Content-Type"] == "application/octet-stream"
        assert whole["Content-Disposition"] == 'attachment; filename="zapis.bin"'
        assert b"".join([part async for part in whole.streaming_content]) == data
        ranged = await browser.get(raw, {"path": "zapis.bin"}, headers={"Range": "bytes=100-299"})
        assert (ranged.status_code, ranged["Content-Range"]) == (206, f"bytes 100-299/{len(data)}")
        assert b"".join([part async for part in ranged.streaming_content]) == data[100:300]
        beyond = await browser.get(raw, {"path": "zapis.bin"}, headers={"Range": "bytes=999999-"})
        assert beyond.status_code == 416
        folder = await browser.get(raw, {"path": ""})
        assert folder.status_code == 400
    finally:
        sftp.ended("")
        # As after `live`: the thread Django shares outside a request keeps its connection open.
        await sync_to_async(connections.close_all)()


def _segment(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


CARD = b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ana Horvat\r\nEMAIL:ana@example.com\r\nEND:VCARD\r\n"


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_what_a_file_holds_is_shown_and_a_folder_zipped_as_the_server_sends_it(spot):
    user = await sync_to_async(User.objects.create_user)("ivo@example.com", "Kamen-Most-Rijeka-71")
    browser = AsyncClient()
    await browser.aforce_login(user)
    given = {"kind": "sftp", "name": "Poslužitelj", "auth": "password", "path": spot} | SERVER
    location = (await browser.post("/api/locations", given, content_type=JSON)).json()

    async def written(server):
        for name, data in (("kartica.vcf", CARD), ("upute.md", b"# Upute\n\nx")):

            async def parts(data=data):
                yield data

            await server.put(name, parts())
        await server.mkdir("mapa")

        async def inner():
            yield b"a"

        await server.put("mapa/a.txt", inner())

    await _on_server(spot, written)
    at = f"/api/locations/{location['id']}"
    try:
        shown = (await browser.get(f"{at}/held/{_segment('kartica.vcf')}/shown")).json()
        assert (shown["kind"], shown["count"]) == ("cards", 1)
        assert shown["people"][0]["name"] == "Ana Horvat"
        text = await browser.get(f"{at}/held/{_segment('upute.md')}/text", {"most": 7})
        assert text.json()["text"] == "# Upute"
        folder = await browser.get(f"{at}/held/{_segment('mapa')}/shown")
        assert folder.status_code == 400

        whole = await browser.get(f"{at}/zip", {"path": ""})
        assert whole["Content-Disposition"] == "attachment; filename*=utf-8''Poslu%C5%BEitelj.zip"
        packed = b"".join([part async for part in whole.streaming_content])
        archive = zipfile.ZipFile(io.BytesIO(packed))
        assert archive.namelist() == [
            "Poslužitelj/",
            "Poslužitelj/mapa/",
            "Poslužitelj/mapa/a.txt",
            "Poslužitelj/kartica.vcf",
            "Poslužitelj/upute.md",
        ]
        assert archive.read("Poslužitelj/kartica.vcf") == CARD
        chosen = await browser.get(f"{at}/zip", {"path": ["mapa/a.txt"]})
        assert chosen["Content-Disposition"] == 'attachment; filename="a.txt.zip"'
        packed = b"".join([part async for part in chosen.streaming_content])
        assert zipfile.ZipFile(io.BytesIO(packed)).namelist() == ["a.txt"]
    finally:
        sftp.ended("")
        await sync_to_async(connections.close_all)()
