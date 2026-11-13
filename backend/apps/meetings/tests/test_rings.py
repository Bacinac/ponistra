import json
from datetime import timedelta
from math import inf

import pytest
from anyio import create_memory_object_stream, create_task_group, fail_after
from django.test import Client
from django.utils import timezone

from apps.calendar import taking
from apps.collab import live
from apps.core.asyncdb import database
from apps.core.views import shipped
from apps.mail import sending
from apps.mail.models import Account
from apps.meetings import rings
from apps.meetings.models import Meeting, Ring
from apps.users.models import User

ORIGIN = "https://ponistra.example"


@pytest.fixture
def owner():
    return User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )


@pytest.fixture
def ana():
    return User.objects.create_user(
        "ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana", last_name="Kovač"
    )


def signed(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def invited(client, meeting, *addresses, language="hr"):
    people = [{"name": "", "address": each} for each in addresses]
    return client.post(
        f"/api/meetings/{meeting.id}/invite",
        json.dumps({"people": people, "language": language}),
        content_type="application/json",
    )


def mailbox(owner, address: str, default: bool = False) -> Account:
    return Account.objects.create(
        owner=owner,
        address=address,
        username=address,
        secret=b"",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        default=default,
    )


@pytest.mark.django_db
def test_colleagues_are_rung_and_the_others_are_written_the_link(owner, ana, monkeypatch):
    delivered = []

    async def deliver(account, message):
        delivered.append((account, message))
        return [], True

    monkeypatch.setattr(sending, "delivered", deliver)
    mailbox(owner, "ivo@example.com", default=True)
    mailbox(ana, "ana.kovac@firma.test")
    meeting = Meeting.objects.made("Sastanak", owner)
    answer = invited(
        signed(owner), meeting, "Ana.Kovac@firma.test", "ivo@example.com", "marko@drugi.test"
    )
    assert answer.json() == {"rung": ["Ana Kovač"], "written": ["marko@drugi.test"]}
    ((account, message),) = delivered
    assert account.address == "ivo@example.com"
    assert (message["Subject"], message["To"]) == (
        "Ivo Bošković vas zove u sastanak",
        "marko@drugi.test",
    )
    assert meeting.link in message.get_body(("plain",)).get_content()

    (ringing,) = rings.ringing(ana.pk)
    assert ringing == {
        "id": ringing["id"],
        "meeting": str(meeting.id),
        "title": "Sastanak",
        "by": "Ivo Bošković",
        "left": 45,
    }
    assert [(each["name"], each["answer"]) for each in rings.rung(owner.pk)] == [("Ana Kovač", "")]
    assert rings.ringing(owner.pk) == []


@pytest.mark.django_db
def test_someone_outside_is_asked_only_from_an_account_that_sends(owner, ana):
    meeting = Meeting.objects.made("Sastanak", owner)
    refused = invited(signed(owner), meeting, "ana@example.com", "marko@drugi.test")
    assert (refused.status_code, refused.json()) == (400, {"error": "no_account"})
    assert not Ring.objects.exists()
    assert invited(signed(owner), meeting, "nije adresa").json() == {"error": "invalid_recipient"}


@pytest.mark.django_db
def test_an_answer_stops_the_ring_and_the_one_who_rang_sees_it(owner, ana):
    meeting = Meeting.objects.made("Sastanak", owner)
    invited(signed(owner), meeting, "ana@example.com")
    assert signed(ana).post(f"/api/meetings/{meeting.id}/decline").status_code == 204
    assert rings.ringing(ana.pk) == []
    assert [each["answer"] for each in rings.rung(owner.pk)] == ["declined"]

    invited(signed(owner), meeting, "ana@example.com")
    assert len(rings.ringing(ana.pk)) == 1
    assert signed(ana).post(f"/api/meetings/{meeting.id}/join").status_code == 200
    assert rings.ringing(ana.pk) == []
    assert [each["answer"] for each in rings.rung(owner.pk)] == ["declined", "joined"]


@pytest.mark.django_db
def test_a_ring_that_stopped_unanswered_rings_again(owner, ana):
    meeting = Meeting.objects.made("Sastanak", owner)
    invited(signed(owner), meeting, "ana@example.com")
    Ring.objects.update(rung_at=timezone.now() - timedelta(minutes=1))
    assert rings.ringing(ana.pk) == []
    assert [each["left"] for each in rings.rung(owner.pk)] == [0]
    invited(signed(owner), meeting, "ana@example.com")
    assert Ring.objects.count() == 1
    assert [each["left"] for each in rings.rung(owner.pk)] == [45]


@pytest.mark.django_db
def test_a_meeting_says_whether_an_event_plans_it(owner):
    client = signed(owner)
    meeting = Meeting.objects.made("Sastanak", owner)
    assert client.get(f"/api/meetings/{meeting.id}").json()["planned"] is False
    calendar = taking.own(owner.pk, "Moj")
    client.post(
        "/api/calendar/events",
        json.dumps(
            {
                "calendar": calendar.pk,
                "summary": "Kolegij",
                "start": "2026-11-02T09:00",
                "end": "2026-11-02T10:00",
                "conference": meeting.link,
            }
        ),
        content_type="application/json",
    )
    assert client.get(f"/api/meetings/{meeting.id}").json()["planned"] is True


class Tab:
    """A signed-in browser's live socket: the states it has been sent."""

    def __init__(self, cookie: str, task_group):
        self.to_server, received = create_memory_object_stream[dict](inf)
        sent, self.from_server = create_memory_object_stream[dict](inf)
        headers = [
            (b"host", b"ponistra.example"),
            (b"origin", ORIGIN.encode()),
            (b"cookie", cookie.encode()),
        ]
        scope = {"type": "websocket", "path": live.PATH, "headers": headers}
        self.to_server.send_nowait({"type": "websocket.connect"})
        task_group.start_soon(live.socket, scope, received.receive, sent.send)

    async def state(self) -> dict:
        with fail_after(5):
            message = await self.from_server.receive()
            if message["type"] == "websocket.accept":
                message = await self.from_server.receive()
        assert message["type"] == "websocket.send", message
        return json.loads(message["text"])

    async def leave(self) -> None:
        await self.to_server.send({"type": "websocket.disconnect", "code": 1000})
        with fail_after(5):
            while (await self.from_server.receive())["type"] != "websocket.close":
                pass


@database
def colleague_cookie() -> tuple[str, User, User]:
    owner = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo")
    ana = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    client = Client()
    client.force_login(ana)
    return f"sessionid={client.cookies['sessionid'].value}", owner, ana


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_ring_reaches_every_open_tab_of_the_colleague_and_stops_there():
    cookie, owner, ana = await colleague_cookie()
    meeting = await database(Meeting.objects.made)("Sastanak", owner)
    async with create_task_group() as tg:
        tg.start_soon(live.listen)
        tabs = [Tab(cookie, tg), Tab(cookie, tg)]
        for each in tabs:
            assert await each.state() == {
                "type": "state",
                "release": shipped(),
                "ringing": [],
                "rung": [],
                "conversations": [],
                "lobby": [],
            }
        await database(rings.ring)(owner, meeting, [ana])
        for each in tabs:
            (ringing,) = (await each.state())["ringing"]
            assert (ringing["meeting"], ringing["by"]) == (str(meeting.id), "Ivo")
        await database(rings.answered)(ana, meeting, Ring.Answer.DECLINED)
        for each in tabs:
            assert (await each.state())["ringing"] == []
            await each.leave()
        tg.cancel_scope.cancel()
    assert live._sockets == {}
