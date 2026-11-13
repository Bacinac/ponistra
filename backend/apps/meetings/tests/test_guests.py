import json
from datetime import timedelta
from math import inf
from urllib.parse import quote

import jwt
import pytest
from anyio import create_memory_object_stream, create_task_group, fail_after
from django.test import Client
from django.utils import timezone

from apps.chat import conversations
from apps.chat.models import Message
from apps.collab import live
from apps.core.asyncdb import database
from apps.mail import sending
from apps.mail.models import Account
from apps.meetings import livekit, lobby, talk, views
from apps.meetings.models import Guest, Meeting
from apps.meetings.tests.test_rings import ORIGIN, Tab
from apps.users.models import User


@pytest.fixture
def owner():
    return User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )


def signed(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def sent(client, method, path, **data):
    return getattr(client, method)(path, json.dumps(data), content_type="application/json")


def claims(token: str, settings) -> dict:
    return jwt.decode(token, settings.LIVEKIT_SECRET, algorithms=["HS256"])


@pytest.mark.django_db
def test_someone_asked_by_mail_enters_by_a_link_of_their_own(owner, monkeypatch, settings):
    delivered = []

    async def deliver(account, message):
        delivered.append(message)
        return [], True

    monkeypatch.setattr(sending, "delivered", deliver)
    Account.objects.create(
        owner=owner,
        address="ivo@example.com",
        username="ivo@example.com",
        secret=b"",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        default=True,
    )
    meeting = Meeting.objects.made("Ponuda", owner)
    people = [
        {"name": "Eva Kovač", "address": "Eva@Drugi.test"},
        {"name": "", "address": "marko@drugi.test"},
    ]
    answer = sent(
        signed(owner), "post", f"/api/meetings/{meeting.id}/invite", people=people, language="hr"
    )
    assert answer.json() == {"rung": [], "written": ["Eva@drugi.test", "marko@drugi.test"]}
    eva, marko = Guest.objects.order_by("address")
    assert (eva.name, eva.address, eva.state, eva.by) == (
        "Eva Kovač",
        "eva@drugi.test",
        Guest.State.ADMITTED,
        owner,
    )
    assert [(each["To"], each.get_body(("plain",)).get_content()) for each in delivered] == [
        (
            "Eva Kovač <Eva@drugi.test>",
            f"Ivo Bošković vas zove u sastanak u Ponistri:\n\n{meeting.link}?guest={eva.key}"
            "\n\nZa ulaz vam ne treba račun.\n",
        ),
        (
            "marko@drugi.test",
            f"Ivo Bošković vas zove u sastanak u Ponistri:\n\n{meeting.link}?guest={marko.key}"
            "\n\nZa ulaz vam ne treba račun.\n",
        ),
    ]
    again = sent(
        signed(owner),
        "post",
        f"/api/meetings/{meeting.id}/invite",
        people=people[:1],
        language="hr",
    )
    assert again.status_code == 200
    assert Guest.objects.count() == 2
    assert f"?guest={eva.key}" in delivered[-1].get_body(("plain",)).get_content()

    outside = Client()
    door = outside.get(f"/api/meetings/{meeting.id}/door?guest={marko.key}").json()
    assert door == {
        "id": str(meeting.id),
        "title": "Ponuda",
        "guest": {"name": "", "state": "admitted"},
    }
    unnamed = sent(outside, "post", f"/api/meetings/{meeting.id}/guests", key=marko.key, name=" ")
    assert (unnamed.status_code, unnamed.json()) == (400, {"error": "no_name"})
    named = sent(outside, "post", f"/api/meetings/{meeting.id}/guests", key=marko.key, name="Marko")
    assert named.json() == {"key": marko.key, "state": "admitted"}
    joined = sent(outside, "post", f"/api/meetings/{meeting.id}/guests/join", key=marko.key)
    token = claims(joined.json()["token"], settings)
    assert token["sub"].startswith(f"guest{marko.pk}.")
    assert (token["name"], json.loads(token["metadata"]), token["video"]["room"]) == (
        "Marko",
        {"guest": True},
        str(meeting.id),
    )
    elsewhere = Meeting.objects.made("Drugi", owner)
    wrong = sent(outside, "post", f"/api/meetings/{elsewhere.id}/guests/join", key=marko.key)
    assert (wrong.status_code, wrong.json()) == (404, {"error": "no_guest"})


@pytest.mark.django_db
def test_someone_by_the_meetings_link_waits_until_someone_in_it_lets_them_in(owner, settings):
    meeting = Meeting.objects.made("Kolegij", owner)
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    outside = Client()
    door = outside.get(f"/api/meetings/{meeting.id}/door").json()
    assert door == {"id": str(meeting.id), "title": "Kolegij", "guest": None}
    nameless = sent(outside, "post", f"/api/meetings/{meeting.id}/guests", name="")
    assert nameless.json() == {"error": "no_name"}
    came = sent(outside, "post", f"/api/meetings/{meeting.id}/guests", name=" Eva  Kovač ")
    assert came.status_code == 201
    key = came.json()["key"]
    assert came.json()["state"] == "waiting"
    early = sent(outside, "post", f"/api/meetings/{meeting.id}/guests/join", key=key)
    assert (early.status_code, early.json()) == (403, {"error": "not_admitted"})

    guest = Guest.objects.get()
    assert lobby.waiting(owner.pk) == []
    Guest.objects.update(at_door=True)
    assert lobby.waiting(owner.pk) == [
        {"id": guest.pk, "meeting": str(meeting.id), "name": "Eva Kovač"}
    ]
    assert lobby.waiting(stranger.pk) == []
    path = f"/api/meetings/{meeting.id}/guests/{guest.pk}"
    assert sent(outside, "patch", path, state="admitted").status_code == 401
    refused = sent(signed(stranger), "patch", path, state="admitted")
    assert (refused.status_code, refused.json()) == (404, {"error": "no_guest"})
    assert sent(signed(owner), "patch", path, state="here").json() == {"error": "invalid_state"}

    assert sent(signed(owner), "patch", path, state="admitted").status_code == 204
    assert lobby.waiting(owner.pk) == []
    joined = sent(outside, "post", f"/api/meetings/{meeting.id}/guests/join", key=key)
    assert claims(joined.json()["token"], settings)["name"] == "Eva Kovač"

    conversations.added(meeting.conversation, [stranger])
    assert sent(signed(stranger), "patch", path, state="refused").status_code == 204
    turned = sent(outside, "post", f"/api/meetings/{meeting.id}/guests/join", key=key)
    assert (turned.status_code, turned.json()) == (403, {"error": "entry_refused"})
    assert Guest.objects.get().by == stranger


@pytest.mark.django_db
def test_the_door_holds_so_many_come_by_the_link_at_a_time(owner, monkeypatch):
    monkeypatch.setattr(views, "DOOR", 2)
    meeting = Meeting.objects.made("Kolegij", owner)
    elsewhere = Meeting.objects.made("Uprava", owner)
    outside = Client()
    path = f"/api/meetings/{meeting.id}/guests"
    assert sent(outside, "post", path, name="Ana").status_code == 201
    asked = Guest.objects.create(meeting=meeting, name="Marko", state="waiting", by=owner)
    second = sent(outside, "post", path, name="Iva")
    assert second.status_code == 201
    full = sent(outside, "post", path, name="Nina")
    assert (full.status_code, full.json()) == (429, {"error": "door_full"})
    assert sent(outside, "post", path, key=asked.key, name="Marko").status_code == 200
    assert (
        sent(outside, "post", f"/api/meetings/{elsewhere.id}/guests", name="Nina").status_code
        == 201
    )

    Guest.objects.filter(key=second.json()["key"]).update(state="admitted")
    assert sent(outside, "post", path, name="Nina").status_code == 201
    Guest.objects.filter(meeting=meeting).update(came_at=timezone.now() - timedelta(minutes=11))
    assert sent(outside, "post", path, name="Mia").status_code == 201


@pytest.mark.django_db
def test_a_guest_in_the_call_talks_in_the_meetings_conversation_since_it_began(owner, monkeypatch):
    group, _ = conversations.started(
        owner, [User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")], "Nabava"
    )
    said = conversations.written(group.members.get(user=owner), "Samo za grupu")
    meeting = Meeting.objects.made(group.title, owner, group)
    Message.objects.filter(pk=said.pk).update(created_at=meeting.created_at - timedelta(minutes=1))
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.ADMITTED)
    present: list[str] = []

    async def inside(room):
        assert room == str(meeting.id)
        return present

    monkeypatch.setattr(livekit, "inside", inside)
    outside = Client()
    at = f"/api/meetings/{meeting.id}/guests/{guest.key}"
    for there in ([], [f"guest{guest.pk}.a1"], ["3.b2"]):
        present[:] = there
        away = outside.get(f"{at}/messages")
        assert (away.status_code, away.json()) == (403, {"error": "not_in_call"})
    present[:] = [f"guest{guest.pk}.a1", f"{owner.pk}.b2"]
    unknown = outside.get(f"/api/meetings/{meeting.id}/guests/no-such-key/messages")
    assert (unknown.status_code, unknown.json()) == (404, {"error": "no_guest"})
    assert outside.get(f"{at}/messages").json() == {"messages": [], "more": False}

    wrote = sent(outside, "post", f"{at}/messages", body="Dobar dan")
    assert wrote.status_code == 201
    assert {k: wrote.json()[k] for k in ("by", "guest", "mine", "text")} == {
        "by": "Eva",
        "guest": True,
        "mine": True,
        "text": "Dobar dan",
    }
    answer = sent(signed(owner), "post", f"/api/conversations/{group.id}/messages", body="Hvala")
    seen = signed(owner).get(f"/api/conversations/{group.id}/messages").json()["messages"]
    assert [(each["by"], each["guest"], each["mine"]) for each in seen] == [
        ("Ivo Bošković", False, True),
        ("Eva", True, False),
        ("Ivo Bošković", False, True),
    ]
    theirs = outside.get(f"{at}/messages").json()["messages"]
    assert [(each["text"], each["mine"]) for each in theirs] == [
        ("Dobar dan", True),
        ("Hvala", False),
    ]
    thumbs = quote("👍")
    assert outside.put(f"{at}/messages/{answer.json()['id']}/reactions/{thumbs}").status_code == 204
    assert outside.put(f"{at}/messages/{said.pk}/reactions/{thumbs}").status_code == 404
    seen = signed(owner).get(f"/api/conversations/{group.id}/messages").json()["messages"]
    assert seen[-1]["reactions"] == [{"emoji": "👍", "people": ["Eva"], "mine": False}]
    theirs = outside.get(f"{at}/messages").json()["messages"]
    assert theirs[-1]["reactions"] == [{"emoji": "👍", "people": ["Eva"], "mine": True}]
    guest.refresh_from_db()
    assert talk.unread(guest) == 1
    assert sent(outside, "post", f"{at}/read", message=answer.json()["id"]).status_code == 204
    guest.refresh_from_db()
    assert talk.unread(guest) == 0

    mine = f"{at}/messages/{wrote.json()['id']}"
    assert sent(outside, "patch", mine, body="Dobar dan svima").json()["edited"] is True
    others = sent(outside, "patch", f"{at}/messages/{answer.json()['id']}", body="?")
    assert (others.status_code, others.json()) == (403, {"error": "not_yours"})
    group_only = outside.delete(f"{at}/messages/{said.pk}")
    assert (group_only.status_code, group_only.json()) == (404, {"error": "no_message"})
    assert outside.delete(mine).status_code == 204
    assert [each["text"] for each in outside.get(f"{at}/messages").json()["messages"]] == ["Hvala"]

    Guest.objects.filter(pk=guest.pk).update(state=Guest.State.REFUSED)
    turned = outside.get(f"{at}/messages")
    assert (turned.status_code, turned.json()) == (403, {"error": "not_admitted"})


class Door:
    """A guest's page at a meeting's door: the states its socket has been sent."""

    def __init__(self, key: str, task_group):
        self.to_server, received = create_memory_object_stream[dict](inf)
        sent, self.from_server = create_memory_object_stream[dict](inf)
        headers = [(b"host", b"ponistra.example"), (b"origin", ORIGIN.encode())]
        scope = {"type": "websocket", "path": lobby.PATH, "headers": headers}
        self.to_server.send_nowait({"type": "websocket.connect"})
        self.to_server.send_nowait({"type": "websocket.receive", "text": json.dumps({"key": key})})
        task_group.start_soon(lobby.socket, scope, received.receive, sent.send)

    async def message(self) -> dict:
        with fail_after(5):
            message = await self.from_server.receive()
            if message["type"] == "websocket.accept":
                message = await self.from_server.receive()
        return message

    async def state(self) -> str:
        message = await self.message()
        assert message["type"] == "websocket.send", message
        return json.loads(message["text"])["state"]

    async def leave(self) -> None:
        await self.to_server.send({"type": "websocket.disconnect", "code": 1000})
        with fail_after(5):
            while (await self.from_server.receive())["type"] != "websocket.close":
                pass


@database
def waiting_guest() -> tuple[str, Meeting, Guest]:
    owner = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo")
    meeting = Meeting.objects.made("Sastanak", owner)
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.WAITING)
    client = Client()
    client.force_login(owner)
    return f"sessionid={client.cookies['sessionid'].value}", meeting, guest


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_the_guest_waits_at_the_door_while_its_page_is_open_and_hears_it_open():
    cookie, meeting, guest = await waiting_guest()
    async with create_task_group() as tg:
        tg.start_soon(live.listen)
        tab = Tab(cookie, tg)
        assert (await tab.state())["lobby"] == []
        unknown = Door("no such key", tg)
        assert (await unknown.message()) == {"type": "websocket.close", "code": 4404}
        door = Door(guest.key, tg)
        assert await door.state() == "waiting"
        assert (await tab.state())["lobby"] == [
            {"id": guest.pk, "meeting": str(meeting.id), "name": "Eva"}
        ]
        await door.leave()
        assert (await tab.state())["lobby"] == []
        door = Door(guest.key, tg)
        assert await door.state() == "waiting"
        assert len((await tab.state())["lobby"]) == 1
        owner = await database(lambda: meeting.organizer)()
        await database(lobby.answered)(guest, owner, Guest.State.ADMITTED)
        assert await door.state() == "admitted"
        assert (await tab.state())["lobby"] == []
        await door.leave()
        await tab.leave()
        tg.cancel_scope.cancel()
    assert live._sockets == {}
