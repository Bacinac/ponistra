import json
from datetime import timedelta

import pytest
from anyio import create_memory_object_stream, create_task_group, fail_after, sleep
from asgiref.sync import sync_to_async
from django.test import AsyncClient, Client
from django.utils import timezone

from apps.access.tests.test_access import JSON, person
from apps.computers import alerts, link, streams
from apps.computers.models import Code, Computer, Opening
from apps.push.models import Notice, Subscription
from apps.users.models import User
from apps.users.sessions import CONFIRMED

FACTS = {"machine": {"hostname": "thinkpad-e14-bc1x"}, "image": {"follows": "stable"}}


def confirmed(client: Client, ago: timedelta = timedelta(0)) -> None:
    session = client.session
    session[CONFIRMED] = (timezone.now() - ago).isoformat()
    session.save()


def administrator() -> Client:
    client = person("admin@example.com", is_staff=True)
    confirmed(client)
    return client


def code_of(client: Client) -> str:
    answer = client.post("/api/computers")
    assert answer.status_code == 201, answer.json()
    return answer.json()["code"]


def enrolled(client: Client, name: str = "thinkpad-e14-bc1x") -> dict:
    answer = Client().post(
        "/api/computers/enroll",
        {"code": code_of(client), "name": name, "agent": "1.0", "facts": FACTS},
        content_type=JSON,
    )
    assert answer.status_code == 201, answer.json()
    return answer.json()


def signed(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
def test_an_administrator_alone_makes_a_code_and_only_once_confirmed():
    plain = person("ana@example.com")
    confirmed(plain)
    assert plain.post("/api/computers").status_code == 403
    staff = person("admin@example.com", is_staff=True)
    confirmed(staff, timedelta(hours=1))
    assert staff.post("/api/computers").json() == {"error": "confirm_required"}
    confirmed(staff)
    made = staff.post("/api/computers").json()
    assert len(made["code"]) == 19 and made["hint"] == made["code"][-4:]
    assert staff.get("/api/computers").json()["codes"] == [
        {key: made[key] for key in ("id", "hint", "made_at", "expires_at")}
    ]
    assert Code.objects.get().digest != made["code"]


@pytest.mark.django_db
def test_a_machine_enrolls_once_with_a_code_and_its_maker_manages_it():
    staff = administrator()
    code = code_of(staff)
    body = {"code": code.lower(), "name": "Ideapad-5", "agent": "1.0", "facts": FACTS}
    made = Client().post("/api/computers/enroll", body, content_type=JSON)
    assert made.status_code == 201
    found = Computer.objects.get()
    assert str(found.pk) == made.json()["id"] and found.name == "ideapad-5"
    assert found.token == link.digest(made.json()["token"]) and found.facts == FACTS
    assert list(Computer.objects.managed(staff.user)) == [found]
    again = Client().post("/api/computers/enroll", body, content_type=JSON)
    assert (again.status_code, again.json()) == (410, {"error": "code_used"})
    unknown = Client().post(
        "/api/computers/enroll", {**body, "code": "ABCD-EFGH"}, content_type=JSON
    )
    assert (unknown.status_code, unknown.json()) == (404, {"error": "code_unknown"})
    bad = Client().post("/api/computers/enroll", {**body, "code": "ab"}, content_type=JSON)
    assert bad.status_code == 400
    taken = {**body, "code": code_of(staff), "name": "IDEAPAD-5"}
    answer = Client().post("/api/computers/enroll", taken, content_type=JSON)
    assert (answer.status_code, answer.json()) == (409, {"error": "name_taken"})


@pytest.mark.django_db
def test_an_expired_code_is_refused():
    staff = administrator()
    code = code_of(staff)
    Code.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    answer = Client().post("/api/computers/enroll", {"code": code, "name": "pc"}, content_type=JSON)
    assert (answer.status_code, answer.json()) == (410, {"error": "code_expired"})


@pytest.mark.django_db
def test_the_machine_renames_hands_over_its_secrets_and_leaves():
    staff = administrator()
    first = enrolled(staff, "first")
    enrolled(staff, "second")
    machine = Client(**signed(first["token"]))
    clash = machine.put("/api/computers/self", {"name": "second"}, content_type=JSON)
    assert (clash.status_code, clash.json()) == (409, {"error": "name_taken"})
    assert (
        machine.put("/api/computers/self", {"name": "third"}, content_type=JSON).status_code == 204
    )
    put = machine.put("/api/computers/self/recovery-key", {"key": "1234-5678"}, content_type=JSON)
    assert put.status_code == 204
    password = {"password": "restic-secret"}
    assert (
        machine.put("/api/computers/self/backup-password", password, content_type=JSON).status_code
        == 204
    )
    assert Client().put("/api/computers/self", {"name": "x"}, content_type=JSON).status_code == 401

    other = person("ana@example.com")
    confirmed(other)
    secrets = f"/api/computers/{first['id']}/secrets"
    assert other.post(f"{secrets}/recovery-key").status_code == 404
    opened = staff.post(f"{secrets}/recovery-key").json()
    assert opened["value"] == "1234-5678"
    assert staff.post(f"{secrets}/backup-password").json()["value"] == "restic-secret"
    assert list(Opening.objects.values_list("secret", "by")) == [
        ("backup_password", staff.user.pk),
        ("recovery_key", staff.user.pk),
    ]

    assert machine.delete("/api/computers/self").status_code == 204
    assert machine.put("/api/computers/self", {"name": "y"}, content_type=JSON).status_code == 401
    left = Computer.objects.get(name="third")
    assert left.left_at and left.recovery_key
    assert staff.post(f"{secrets}/recovery-key").json()["value"] == "1234-5678"
    # The name is free again for a machine that joins anew.
    enrolled(staff, "third")


@pytest.mark.django_db
def test_managers_are_added_and_the_last_stays():
    staff = administrator()
    made = enrolled(staff)
    ana = person("ana@example.com")
    base = f"/api/computers/{made['id']}"
    assert ana.get(base).status_code == 404
    assert (
        staff.post(f"{base}/managers", {"user": ana.user.pk}, content_type=JSON).status_code == 204
    )
    assert [each["email"] for each in ana.get(base).json()["managers"]] == [
        "admin@example.com",
        "ana@example.com",
    ]
    assert ana.delete(f"{base}/managers/{staff.user.pk}").status_code == 204
    last = ana.delete(f"{base}/managers/{ana.user.pk}")
    assert (last.status_code, last.json()) == (409, {"error": "last_manager"})


@pytest.mark.django_db
def test_an_administrator_takes_over_a_computer_nobody_manages():
    staff = administrator()
    made = enrolled(staff)
    other = person("boss@example.com", is_staff=True)
    confirmed(other)
    assert other.post(f"/api/computers/{made['id']}/take").status_code == 404
    User.objects.filter(pk=staff.user.pk).update(is_active=False)
    assert [each["id"] for each in other.get("/api/computers").json()["orphaned"]] == [made["id"]]
    assert other.post(f"/api/computers/{made['id']}/take").status_code == 204
    assert other.get(f"/api/computers/{made['id']}").status_code == 200


def test_alert_changes_are_a_raise_a_severity_and_a_clear():
    warning = {"id": "disk:sda", "severity": "warning", "text": "pending sectors"}
    critical = {**warning, "severity": "critical"}
    cleared = {**critical, "cleared_at": "2026-11-26T12:00:00Z"}
    other = {"id": "units", "severity": "warning", "text": "failed units"}
    assert alerts.changes([], [warning]) == [("raised", warning)]
    assert alerts.changes([warning], [warning, other]) == [("raised", other)]
    assert alerts.changes([warning], [critical]) == [("severity", critical)]
    assert alerts.changes([critical], [cleared]) == [("cleared", cleared)]
    assert alerts.changes([cleared], [cleared]) == []


class Agent:
    """The machine's end of a link or of a stream."""

    def __init__(self, path: str, token: str, task_group, subprotocols=(link.SUBPROTOCOL,)):
        self.to_server, received = create_memory_object_stream[dict](100)
        sent, self.from_server = create_memory_object_stream[dict](100)
        headers = [(b"authorization", f"Bearer {token}".encode())]
        scope = {
            "type": "websocket",
            "path": path,
            "headers": headers,
            "subprotocols": list(subprotocols),
        }
        self.to_server.send_nowait({"type": "websocket.connect"})
        handler = streams.socket if path.startswith("/api/computers/streams/") else link.socket
        task_group.start_soon(handler, scope, received.receive, sent.send)

    async def message(self) -> dict:
        with fail_after(10):
            return await self.from_server.receive()

    async def frame(self) -> dict:
        message = await self.message()
        assert message["type"] == "websocket.send", message
        return json.loads(message["text"])

    def say(self, frame: dict) -> None:
        self.to_server.send_nowait({"type": "websocket.receive", "text": json.dumps(frame)})

    def send_bytes(self, data: bytes) -> None:
        self.to_server.send_nowait({"type": "websocket.receive", "bytes": data})

    def close(self, code: int = 1000, reason: str = "") -> None:
        self.to_server.send_nowait({"type": "websocket.disconnect", "code": code, "reason": reason})


async def _linked(token: str, tg) -> Agent:
    agent = Agent(link.PATH, token, tg)
    assert await agent.message() == {"type": "websocket.accept", "subprotocol": link.SUBPROTOCOL}
    agent.say({"type": "hello", "agent": "1.1", "facts": FACTS})
    with fail_after(10):
        while not link.connected((await sync_to_async(Computer.objects.get)()).pk):
            await sleep(0.01)
    return agent


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_request_goes_over_the_link_as_the_person_and_its_answer_comes_back():
    staff = await sync_to_async(administrator)()
    made = await sync_to_async(enrolled)(staff)
    ana = await sync_to_async(person)("Ana@Example.com")
    browser = AsyncClient()
    await browser.aforce_login(staff.user)
    async with create_task_group() as tg:
        agent = await _linked(made["token"], tg)

        async def answering():
            frame = await agent.frame()
            assert frame == {
                "type": "request",
                "id": frame["id"],
                "method": "GET",
                "path": "/v1/pressure?span=90m",
                "account": "admin@example.com",
            }
            agent.say(
                {
                    "type": "response",
                    "id": frame["id"],
                    "status": 200,
                    "content_type": "application/json",
                    "body": {"cpu": 0.5},
                }
            )

        tg.start_soon(answering)
        answer = await browser.get(f"/api/computers/{made['id']}/agent/v1/pressure?span=90m")
        assert (answer.status_code, answer.json()) == (200, {"cpu": 0.5})

        stranger = AsyncClient()
        await stranger.aforce_login(ana.user)
        forbidden = await stranger.get(f"/api/computers/{made['id']}/agent/v1/pressure")
        assert forbidden.status_code == 403

        found = await sync_to_async(Computer.objects.get)()
        assert found.agent == "1.1" and found.connected_at is not None

        await sync_to_async(Subscription.objects.create)(
            user=staff.user, endpoint="https://push.example/1", p256dh=b"", auth=b""
        )
        alert = {"id": "units", "severity": "critical", "text": "failed units", "kind": "units"}
        agent.say({"type": "alerts", "alerts": [alert]})
        with fail_after(10):
            while not await sync_to_async(Notice.objects.exists)():
                await sleep(0.01)
        notice = await sync_to_async(Notice.objects.get)()
        assert notice.kind == Notice.Kind.COMPUTER and notice.data["event"] == "raised"
        assert notice.urgency == Notice.Urgency.HIGH

        await sync_to_async(confirmed)(browser, timedelta(hours=1))
        assert (await browser.delete(f"/api/computers/{made['id']}")).status_code == 403
        await sync_to_async(confirmed)(browser)
        assert (await browser.delete(f"/api/computers/{made['id']}")).status_code == 204
        assert await agent.message() == {"type": "websocket.close", "code": link.GONE}
        agent.close(link.GONE)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_an_unknown_machine_is_refused_before_the_link_opens():
    async with create_task_group() as tg:
        agent = Agent(link.PATH, "unknown", tg)
        assert await agent.message() == {"type": "websocket.close", "code": link.GONE}


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_stream_carries_bytes_both_ways_and_a_refusal_raises():
    staff = await sync_to_async(administrator)()
    made = await sync_to_async(enrolled)(staff)
    found = await sync_to_async(Computer.objects.get)()
    async with create_task_group() as tg:
        agent = await _linked(made["token"], tg)
        opening = []

        async def opened():
            opening.append(
                await streams.opened(found, "GET", "/v1/guests/web/sftp", "ana@example.com")
            )

        tg.start_soon(opened)
        frame = await agent.frame()
        assert frame["type"] == "stream" and frame["path"] == "/v1/guests/web/sftp"
        stream = Agent(f"/api/computers/streams/{frame['id']}", made["token"], tg)
        assert (await stream.message())["type"] == "websocket.accept"
        with fail_after(10):
            while not opening:
                await sleep(0.01)
        opening[0].write(b"init")
        assert await stream.message() == {"type": "websocket.send", "bytes": b"init"}
        stream.send_bytes(b"version")
        assert await opening[0].read() == b"version"
        stream.close(1000)
        assert await opening[0].read() == b"" and opening[0].ended == (1000, "")

        async def refused():
            with pytest.raises(streams.Refused) as caught:
                await streams.opened(found, "GET", "/v1/consoles/x", "ana@example.com")
            opening.append(caught.value)

        tg.start_soon(refused)
        frame = await agent.frame()
        stream = Agent(f"/api/computers/streams/{frame['id']}", made["token"], tg)
        assert (await stream.message())["type"] == "websocket.accept"
        stream.close(1011, "not your ticket")
        with fail_after(10):
            while len(opening) < 2:
                await sleep(0.01)
        assert (opening[1].status, opening[1].error) == (502, "not your ticket")

        async def chunks():
            yield b"iso-1"
            yield b"iso-2"

        async def upload():
            opening.append(
                await streams.uploaded(
                    found, "POST", "/v1/isos?name=a", "ana@example.com", chunks()
                )
            )

        tg.start_soon(upload)
        frame = await agent.frame()
        stream = Agent(f"/api/computers/streams/{frame['id']}", made["token"], tg)
        assert (await stream.message())["type"] == "websocket.accept"
        assert (await stream.message())["bytes"] == b"iso-1"
        assert (await stream.message())["bytes"] == b"iso-2"
        assert (await stream.message())["text"] == streams.END
        stream.say(
            {
                "type": "response",
                "id": frame["id"],
                "status": 201,
                "content_type": "application/json",
                "body": {"name": "a"},
            }
        )
        assert (await stream.message())["type"] == "websocket.close"
        stream.close(1000)
        with fail_after(10):
            while len(opening) < 3:
                await sleep(0.01)
        assert opening[2] == (201, "application/json", b'{"name": "a"}')
        agent.close()
