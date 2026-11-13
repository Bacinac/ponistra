import base64
import re

import pytest
from asgiref.sync import async_to_sync

from apps.blobs.models import Blob
from apps.mail import fetching, sync
from apps.mail.imap import imap
from apps.mail.models import Deleted, Message, Source
from apps.users.models import User

from .mox import LOGIN, SERVER, letter, put, server, synced

pytestmark = [pytest.mark.django_db, pytest.mark.xdist_group("mox")]

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def reader(client, account):
    client.force_login(account.owner)
    return client


def opened(account, folder, message) -> Message:
    put(folder, message)
    synced(account, folder)
    return Message.objects.get(subject=message["Subject"])


def content(response) -> bytes:
    async def read():
        return b"".join([part async for part in response.streaming_content])

    return async_to_sync(read)()


def flags_on_server(folder: str) -> set[bytes]:
    with server() as client:
        client.select_folder(folder, readonly=True)
        [flags] = client.get_flags(client.search("ALL")).values()
    return set(flags)


def test_an_html_message_opens_safe_with_the_images_it_carries(reader, account, folder):
    message = letter("Ponuda")
    message.add_alternative(
        '<p onclick="steal()">Cijena <b>100 €</b>.</p><img src="cid:logo@example.com">'
        '<script>steal()</script><a href="javascript:steal()">a</a>'
        '<a href="/api/mail/accounts">b</a>',
        subtype="html",
    )
    message.get_payload()[1].add_related(PNG, "image", "png", cid="<logo@example.com>")
    kept = opened(account, folder, message)
    shown = reader.get(f"/api/mail/messages/{kept.pk}").json()
    assert (shown["subject"], shown["text"], shown["remote"]) == ("Ponuda", None, False)
    assert (shown["account"], shown["accounts"], shown["attachments"]) == (
        account.pk,
        [account.pk],
        [],
    )
    assert "<b>100 €</b>" in shown["html"]
    assert not any(bad in shown["html"] for bad in ("onclick", "script", "steal", "/api/mail/acc"))
    image = f"/api/mail/messages/{kept.pk}/parts/2.2"
    assert f'src="{image}"' in shown["html"]
    served = reader.get(image)
    assert (served["Content-Type"], content(served)) == ("image/png", PNG)
    assert served["Content-Disposition"].startswith("inline")


def test_images_from_elsewhere_wait_until_the_reader_lets_them_in_and_come_through_ponistra_once(
    reader, account, folder, monkeypatch
):
    message = letter("Novosti")
    message.add_alternative(
        '<img src="https://tracker.example/pixel.gif" width="1"><p>Ovaj tjedan.</p>', subtype="html"
    )
    kept = opened(account, folder, message)
    url = f"/api/mail/messages/{kept.pk}"
    held = reader.get(url).json()
    assert held["remote"] and "tracker.example" not in held["html"]
    assert "Ovaj tjedan." in held["html"]
    assert (held["domain"], held["images"]) == ("example.com", None)
    let_in = reader.get(url, {"images": "1"}).json()
    [image] = re.findall(r'src="([^"]+)"', let_in["html"])
    assert image.startswith(f"/api/mail/messages/{kept.pk}/fetched/")
    assert "tracker.example" not in let_in["html"]
    asked = []

    async def fetched(address):
        asked.append(address)
        return PNG, "image/png"

    monkeypatch.setattr(fetching, "fetched", fetched)
    for _ in range(2):
        served = reader.get(image)
        assert (served["Content-Type"], content(served)) == ("image/png", PNG)
    assert asked == ["https://tracker.example/pixel.gif"]
    assert reader.get(image.replace(str(kept.pk), str(kept.pk + 1), 1)).status_code == 404
    assert reader.get(image[:-2]).status_code == 404


def test_an_image_from_elsewhere_that_is_none_is_not_asked_for_again(
    reader, account, folder, monkeypatch
):
    message = letter("Bilten")
    message.add_alternative('<p style="background: url(//cdn.example/a.gif)">x</p>', subtype="html")
    kept = opened(account, folder, message)
    html = reader.get(f"/api/mail/messages/{kept.pk}", {"images": "1"}).json()["html"]
    [image] = re.findall(r"url\('([^']+)'\)", html)
    asked = []

    async def answered(address):
        asked.append(address)
        return None

    monkeypatch.setattr(fetching, "fetched", answered)
    assert [reader.get(image).status_code for _ in range(2)] == [404, 404]
    assert asked == ["https://cdn.example/a.gif"]

    async def unreachable(address):
        raise fetching.Unreachable

    other = letter("Bilten 2")
    other.add_alternative('<img src="https://down.example/b.png">', subtype="html")
    later = opened(account, folder, other)
    html = reader.get(f"/api/mail/messages/{later.pk}", {"images": "1"}).json()["html"]
    [image] = re.findall(r'src="([^"]+)"', html)
    monkeypatch.setattr(fetching, "fetched", unreachable)
    assert reader.get(image).status_code == 502
    assert not later.fetched.exists()


def test_a_domain_decided_on_has_its_images_shown_or_kept_out_without_asking(
    reader, account, folder
):
    message = letter("Ponuda tjedna")
    message.add_alternative('<img src="https://cdn.example/a.png"><p>Akcija.</p>', subtype="html")
    url = f"/api/mail/messages/{opened(account, folder, message).pk}"
    given = reader.post(
        "/api/mail/images", {"domain": " Example.COM ", "shown": True}, "application/json"
    )
    listed = [{"domain": "example.com", "shown": True}]
    assert (given.status_code, given.json()) == (201, {"images": listed})
    shown = reader.get(url).json()
    assert (shown["images"], shown["remote"]) == (True, True)
    assert f'src="/api/mail/messages/{shown["id"]}/fetched/' in shown["html"]
    assert reader.get("/api/mail/accounts").json()["images"] == listed
    kept = reader.post(
        "/api/mail/images", {"domain": "example.com", "shown": False}, "application/json"
    )
    assert kept.json() == {"images": [{"domain": "example.com", "shown": False}]}
    quiet = reader.get(url).json()
    assert (quiet["images"], quiet["remote"]) == (False, True)
    assert "cdn.example" not in quiet["html"]
    assert "/fetched/" in reader.get(url, {"images": "1"}).json()["html"]
    assert reader.delete("/api/mail/images/example.com").status_code == 204
    assert reader.get(url).json()["images"] is None
    for wrong in ("", "localhost", "ana@example.com"):
        refused = reader.post(
            "/api/mail/images", {"domain": wrong, "shown": True}, "application/json"
        )
        assert refused.json() == {"error": "invalid_domain"}
    unsaid = reader.post("/api/mail/images", {"domain": "example.com"}, "application/json")
    assert unsaid.json() == {"error": "invalid_shown"}


def test_mail_from_a_list_is_known_by_how_it_says_to_leave_it(reader, account, folder):
    listed = letter("Novosti")
    listed["List-Unsubscribe"] = "<https://example.com/odjava>"
    url = f"/api/mail/messages/{opened(account, folder, listed).pk}"
    assert reader.get(url).json()["bulk"] is True
    written = opened(account, folder, letter("Sastanak"))
    assert reader.get(f"/api/mail/messages/{written.pk}").json()["bulk"] is False


def test_flags_set_in_ponistra_stay_in_ponistra(reader, account, folder):
    url = f"/api/mail/messages/{opened(account, folder, letter('Sastanak', 'U 10 sati.')).pk}"
    shown = reader.get(url).json()
    assert (shown["text"].strip(), shown["html"], shown["seen"]) == ("U 10 sati.", None, False)
    changed = reader.patch(url, {"seen": True, "flagged": True}, content_type="application/json")
    assert (changed.json()["seen"], changed.json()["flagged"]) == (True, True)
    assert Message.objects.values_list("seen", "flagged").get() == (True, True)
    assert not {b"\\Seen", b"\\Flagged"} & flags_on_server(folder)
    refused = reader.patch(url, {"seen": "yes"}, content_type="application/json")
    assert refused.json() == {"error": "invalid_flags"}


def test_an_attachment_is_saved_or_kept_to_become_a_document(reader, account, folder):
    message = letter("Ugovor")
    message.add_attachment(
        b"%PDF-1.7\n%test", maintype="application", subtype="pdf", filename="Ugovor Šibenik.pdf"
    )
    url = f"/api/mail/messages/{opened(account, folder, message).pk}"
    [attachment] = reader.get(url).json()["attachments"]
    assert (attachment["name"], attachment["type"], attachment["size"]) == (
        "Ugovor Šibenik.pdf",
        "application/pdf",
        14,
    )
    part = f"{url}/parts/{attachment['part']}"
    saved = reader.get(part)
    assert (saved["Content-Type"], content(saved)) == (
        "application/octet-stream",
        b"%PDF-1.7\n%test",
    )
    assert saved["Content-Disposition"].startswith("attachment")
    kept = reader.post(f"{part}/blob").json()
    assert (kept["media_type"], kept["name"]) == ("application/pdf", "Ugovor Šibenik.pdf")
    assert Blob.objects.filter(pk=kept["sha256"]).exists()
    assert reader.get(f"{url}/parts/9").json() == {"error": "not_found"}


def test_an_image_that_is_not_what_it_says_is_only_saved(reader, account, folder):
    message = letter("Slika")
    message.add_attachment(
        b"<svg onload=steal()>", maintype="image", subtype="png", filename="a.png"
    )
    kept = opened(account, folder, message)
    [attachment] = reader.get(f"/api/mail/messages/{kept.pk}").json()["attachments"]
    served = reader.get(f"/api/mail/messages/{kept.pk}/parts/{attachment['part']}")
    assert served["Content-Type"] == "application/octet-stream"
    assert served["Content-Disposition"].startswith("attachment")


def test_the_message_is_read_once_the_provider_no_longer_has_it_and_only_by_its_owner(
    reader, client, account, folder
):
    url = f"/api/mail/messages/{opened(account, folder, letter('Odlazi', 'Ostaje kod nas.')).pk}"
    with server() as found:
        found.select_folder(folder)
        found.delete_messages(found.search("ALL"))
        found.expunge()
    assert reader.get(url).json()["text"].strip() == "Ostaje kod nas."
    original = reader.get(f"{url}/original")
    assert original["Content-Type"] == "message/rfc822"
    assert original["Content-Disposition"] == 'attachment; filename="Odlazi.eml"'
    assert b"Subject: Odlazi" in original.content
    client.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert client.get(url).json() == {"error": "not_found"}


def test_a_message_goes_to_trash_and_from_there_for_good(reader, account, folder):
    kept = opened(account, folder, letter("Smeće"))
    where = {"messages": [kept.pk]}
    moved = {"action": "move", "to": "trash", "where": where}
    assert reader.post(
        f"/api/mail/folders/{kept.folder_id}/chosen", moved, "application/json"
    ).json() == {"changed": 1}
    trash = Message.objects.get().folder
    assert trash.role == "trash"
    deleted = {"action": "delete", "where": where}
    assert reader.post(
        f"/api/mail/folders/{trash.pk}/chosen", deleted, "application/json"
    ).json() == {"changed": 1}
    assert not Message.objects.exists()
    assert Deleted.objects.filter(owner=account.owner, key=kept.key).exists()
    Source.objects.filter(name=folder).update(uidvalidity=None)
    with imap(*SERVER, LOGIN) as client:
        [source] = [each for each in sync.sources(client, account) if each.name == folder]
        sync.caught_up(client, source)
        while sync.older(client, source):
            pass
    assert not Message.objects.exists()
