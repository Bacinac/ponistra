import gc
import io
from contextlib import AsyncExitStack
from inspect import isawaitable
from uuid import uuid4

import pytest
from anyio import (
    BrokenResourceError,
    ClosedResourceError,
    EndOfStream,
    create_memory_object_stream,
    create_task_group,
    fail_after,
    sleep,
)
from asgiref.sync import sync_to_async
from django.test import Client
from django.utils import timezone
from pycrdt import (
    Awareness,
    Doc,
    Map,
    Provider,
    Text,
    YMessageType,
    YSyncMessageType,
    create_sync_message,
    create_update_message,
    read_message,
)

from apps.access.models import Grant, Role
from apps.blobs import store
from apps.collab import server as collab_server
from apps.collab.models import Update
from apps.collab.server import REFUSED, CollabServer, Connection, Signed, changes
from apps.content import grids
from apps.content.blocks import Block, Run, key_of, read
from apps.content.operations import carry_out, take_back
from apps.content.sheets import Refused
from apps.content.tests.helpers import written
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab
from apps.users import sessions
from apps.users.models import User
from apps.versions.models import Contribution

pytestmark = [pytest.mark.anyio, pytest.mark.django_db(transaction=True)]

CLOSED = {"type": "websocket.close", "code": REFUSED}


class Endpoint:
    signed = None
    user = None
    role = None

    def __init__(self, path, outbox, inbox):
        self.path = path
        self._outbox = outbox
        self._inbox = inbox

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self._inbox.receive()
        except EndOfStream:
            raise StopAsyncIteration from None

    async def recv(self) -> bytes:
        return await self._inbox.receive()

    async def send(self, message: bytes) -> None:
        try:
            await self._outbox.send(message)
        except BrokenResourceError, ClosedResourceError:
            pass

    async def close(self) -> None:
        self._outbox.close()


class Peer:
    def __init__(self, server: CollabServer, room: str, task_group, signed=None, role=None):
        to_server = create_memory_object_stream[bytes](256)
        to_client = create_memory_object_stream[bytes](256)
        served = Endpoint(room, to_client[0], to_server[1])
        served.signed, served.user, served.role = signed, signed and signed.user, role
        task_group.start_soon(server.serve, served)
        self.endpoint = Endpoint(room, to_server[0], to_client[1])
        self.doc = Doc()
        self.text = self.doc.get("text", type=Text)

    async def __aenter__(self):
        self._provider = await Provider(self.doc, self.endpoint).__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self._provider.__aexit__(*exc)
        await self.endpoint.close()

    def cut_off(self) -> bool:
        return self.endpoint._inbox.statistics().open_send_streams == 0


async def until(condition) -> None:
    with fail_after(5):
        while True:
            result = condition()
            if isawaitable(result):
                result = await result
            if result:
                return
            await sleep(0.01)


async def stored(room: str) -> int:
    return await Update.objects.filter(room=room).acount()


async def tab(**fields) -> str:
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Bilješka", **fields)
    return str((await Tab.objects.acreate(document=document, position=0)).room)


async def signed(user: User) -> Signed:
    return Signed(user.pk, await sync_to_async(sessions.opened)(user, 3600))


async def grant(room: str, user: User, role: Role) -> Grant:
    document = await Node.objects.aget(tabs__room=room)
    return await Grant.objects.acreate(node=document, user=user, role=role)


async def modified(room: str):
    return (await Node.objects.aget(tabs__room=room)).updated_at


async def test_two_clients_converge_and_the_room_survives_a_restart():
    memo = await tab()
    async with CollabServer() as server, create_task_group() as tg:
        async with AsyncExitStack() as stack:
            a = await stack.enter_async_context(Peer(server, memo, tg))
            b = await stack.enter_async_context(Peer(server, memo, tg))
            a.text += "Dobar dan"
            await until(lambda: str(b.text) == "Dobar dan")
            b.text += ", svima"
            await until(lambda: str(a.text) == "Dobar dan, svima")
            await until(lambda: stored(memo))
        await until(lambda: not server.rooms)

    assert await stored(memo) == 1

    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, memo, tg) as c:
            await until(lambda: str(c.text) == "Dobar dan, svima")


async def test_rooms_are_isolated():
    first, second = await tab(), await tab()
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, first, tg) as one, Peer(server, second, tg) as two:
            one.text += "prvi"
            await until(lambda: stored(first))
            assert str(two.text) == ""
        await until(lambda: not server.rooms)


async def test_a_visit_that_changes_nothing_writes_nothing():
    memo = await tab()
    before = await modified(memo)
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, memo, tg):
            await until(lambda: server.rooms)
        await until(lambda: not server.rooms)
    assert await stored(memo) == 0
    assert await modified(memo) == before


async def test_closing_an_edited_room_marks_the_document_modified():
    memo = await tab()
    before = await modified(memo)
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, memo, tg) as peer:
            peer.text += "x"
            await until(lambda: stored(memo))
        await until(lambda: not server.rooms)
    assert await modified(memo) > before


async def test_a_session_that_only_rewrites_the_tallies_leaves_the_document_unmodified():
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Bilješka")
    own = str(document.room)

    async def written() -> bool:
        return await stored(own) > 1

    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, own, tg) as peer:
            peer.doc.get("styles", type=Map)["x"] = {"size": 12}
            await until(lambda: stored(own))
        await until(lambda: not server.rooms)
    styled = (await Node.objects.aget(pk=document.pk)).updated_at
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, own, tg) as peer:
            await until(lambda: "x" in peer.doc.get("styles", type=Map))
            peer.doc.get("pages", type=Map)["t"] = 2
            peer.doc.get("styles", type=Map)["x"] = {"size": 12}
            await until(written)
        await until(lambda: not server.rooms)
    assert (await Node.objects.aget(pk=document.pk)).updated_at == styled
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, own, tg) as peer:
            await until(lambda: "x" in peer.doc.get("styles", type=Map))
            peer.doc.get("styles", type=Map)["x"] = {"size": 14}
            await until(written)
        await until(lambda: not server.rooms)
    assert (await Node.objects.aget(pk=document.pk)).updated_at > styled


async def test_revoking_closes_rooms_of_trashed_documents_and_deleted_or_moved_tabs():
    trashed, deleted, moved, kept = await tab(), await tab(), await tab(), await tab()
    async with CollabServer() as server, create_task_group() as tg:
        async with AsyncExitStack() as stack:
            a, b, c, d = [
                await stack.enter_async_context(Peer(server, room, tg))
                for room in (trashed, deleted, moved, kept)
            ]
            await until(lambda: len(server.rooms) == 4)
            await Node.objects.filter(tabs__room=trashed).aupdate(trashed_at=timezone.now())
            await Tab.objects.filter(room=deleted).adelete()
            await Tab.objects.filter(room=moved).aupdate(room=uuid4())
            await server.revoke()
            await until(lambda: a.cut_off() and b.cut_off() and c.cut_off())
            assert not d.cut_off()
        await until(lambda: not server.rooms)


async def own_room(tab_room: str) -> str:
    return str((await Node.objects.aget(tabs__room=tab_room)).room)


async def test_a_documents_own_room_keeps_its_state_apart_from_its_tabs():
    memo = await tab()
    own = await own_room(memo)
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, own, tg) as a, Peer(server, own, tg) as b:
            a.text += "tema"
            await until(lambda: str(b.text) == "tema")
        await until(lambda: not server.rooms)

    row = await Update.objects.aget(room=own)
    assert row.tab_id is None and str(row.document_id) == str(
        (await Node.objects.aget(room=own)).pk
    )
    assert await stored(memo) == 0
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, own, tg) as c:
            await until(lambda: str(c.text) == "tema")


async def test_a_documents_own_room_hears_of_changed_comments_and_tabs_and_stores_nothing():
    own = await own_room(await tab())
    async with CollabServer() as server, create_task_group() as tg:
        to_server = create_memory_object_stream[bytes](256)
        to_client = create_memory_object_stream[bytes](256)
        tg.start_soon(server.serve, Endpoint(own, to_client[0], to_server[1]))
        assert (await to_client[1].receive())[0] == YMessageType.SYNC
        await server.announce(str(uuid4()), "comments")
        await server.announce(own, "comments")
        await server.announce(own, "tabs")
        await server.announce(own, "comments")
        heard = Awareness(Doc())
        for _ in range(3):
            message = await to_client[1].receive()
            assert message[0] == YMessageType.AWARENESS
            heard.apply_awareness_update(read_message(message[1:]), "server")
        told = [state for client, state in heard.states.items() if client != heard.client_id]
        assert told == [{"comments": 2, "tabs": 1}]
        to_server[0].close()
        await until(lambda: not server.rooms)
    assert await stored(own) == 0


async def test_revoking_closes_a_documents_own_room_once_trashed_or_moved():
    trashed, moved, kept = [await own_room(await tab()) for _ in range(3)]
    async with CollabServer() as server, create_task_group() as tg:
        async with AsyncExitStack() as stack:
            a, b, c = [
                await stack.enter_async_context(Peer(server, room, tg))
                for room in (trashed, moved, kept)
            ]
            await until(lambda: len(server.rooms) == 3)
            await Node.objects.filter(room=trashed).aupdate(trashed_at=timezone.now())
            await Node.objects.filter(room=moved).aupdate(room=uuid4())
            await server.revoke()
            await until(lambda: a.cut_off() and b.cut_off())
            assert not c.cut_off()
        await until(lambda: not server.rooms)


async def test_a_room_its_tab_has_left_neither_shows_nor_keeps_what_it_writes():
    old = await tab()
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, old, tg) as peer:
            peer.text += "zamijenjeno"
            await until(lambda: stored(old))
            new = str(uuid4())
            await Tab.objects.filter(room=old).aupdate(room=new)
            peer.text += " i kasnije"

            async def written_after_the_move():
                return await stored(old) == 2

            await until(written_after_the_move)
        await until(lambda: not server.rooms)
        assert await stored(old) == 0
        async with Peer(server, new, tg) as fresh:
            await until(lambda: server.rooms)
            assert str(fresh.text) == ""
        await until(lambda: not server.rooms)


async def test_cyclic_garbage_is_collected_on_the_event_loop_only_while_serving():
    async with CollabServer():
        assert not gc.isenabled()
    assert gc.isenabled()


async def test_a_connection_drops_what_the_room_sends_once_it_is_gone():
    sent = []

    async def send(message):
        sent.append(message)

    async def disconnected(message):
        raise OSError("client disconnected")

    closing = Connection(None, send, "room")
    await closing.close()
    await closing.close()
    await closing.send(b"late")
    assert sent == [{"type": "websocket.close"}]
    await Connection(None, disconnected, "room").send(b"late")


def update_of(text: str) -> bytes:
    doc = Doc()
    doc.get("text", type=Text).insert(0, text)
    return doc.get_update()


async def test_a_change_waits_for_the_edits_it_comes_after_and_is_refused_once_they_lag(
    monkeypatch,
):
    room, browser = Doc(), Doc()
    browser.get("text", type=Text).insert(0, "ab")
    reached = []

    async def change():
        await collab_server._reached(room, browser.client_id, 2)
        reached.append(True)

    async with create_task_group() as tg:
        tg.start_soon(change)
        await sleep(0.05)
        assert not reached
        room.apply_update(browser.get_update())
    assert reached
    monkeypatch.setattr(collab_server, "BEHIND", 0.05)
    with pytest.raises(Refused) as refused:
        await collab_server._reached(room, browser.client_id, 3)
    assert refused.value.code == "behind"


@pytest.mark.parametrize(
    "message, edits",
    [
        (create_update_message(update_of("a")), True),
        (create_sync_message(Doc()), False),
        (bytes([0, 1, 2, 0, 0]), False),
        (bytes([1, 3, 1, 2, 3]), False),
        (b"", False),
    ],
)
def test_changes_are_updates_and_sync_replies_with_content(message, edits):
    assert changes(message) == edits


async def test_a_connection_records_an_edit_once_a_minute_at_most():
    memo = await tab()
    tab_row = await Tab.objects.aget(room=memo)
    user = await User.objects.acreate(email="ana@example.com")
    inbox = iter([create_update_message(update_of("a")), create_update_message(update_of("b"))])

    async def receive():
        return {"type": "websocket.receive", "bytes": next(inbox)}

    connection = Connection(receive, None, memo, tab_row.document_id, Signed(user.pk, "key"))
    await connection.recv()
    first = (await Contribution.objects.aget()).edited_at
    await connection.recv()
    assert (await Contribution.objects.aget(user=user)).edited_at == first


async def test_a_reader_is_heard_only_asking_and_in_presence():
    asking = create_sync_message(Doc())
    presence = bytes([YMessageType.AWARENESS, 1, 0])
    inbox = iter(
        [
            create_update_message(update_of("a")),
            bytes([YMessageType.SYNC, YSyncMessageType.SYNC_STEP2]) + asking[2:],
            asking,
            create_update_message(update_of("b")),
            presence,
        ]
    )

    async def receive():
        return {"type": "websocket.receive", "bytes": next(inbox)}

    reader = Connection(receive, None, str(uuid4()), None, None, Role.READ)
    assert [await reader.recv(), await reader.recv()] == [asking, presence]
    assert not await Contribution.objects.aexists()


async def test_revoking_closes_clients_whose_role_has_changed():
    room = await tab()
    ana = await User.objects.acreate(email="ana@example.com")
    ivo = await User.objects.acreate(email="ivo@example.com")
    marko = await User.objects.acreate(email="marko@example.com")
    kept = await grant(room, ana, Role.EDIT)
    changed = await grant(room, ivo, Role.EDIT)
    removed = await grant(room, marko, Role.READ)
    async with CollabServer() as server, create_task_group() as tg:
        async with (
            Peer(server, room, tg, await signed(ana), Role.EDIT) as a,
            Peer(server, room, tg, await signed(ivo), Role.EDIT) as b,
            Peer(server, room, tg, await signed(marko), Role.READ) as c,
        ):
            await until(lambda: room in server.rooms and len(server.rooms[room].clients) == 3)
            await Grant.objects.filter(pk=changed.pk).aupdate(role=Role.READ)
            await removed.adelete()
            await server.revoke()
            await until(lambda: b.cut_off() and c.cut_off())
            assert not a.cut_off()
            assert await Grant.objects.filter(pk=kept.pk).aexists()


async def test_revoking_closes_the_clients_of_a_session_that_has_ended():
    room = await tab()
    ana = await User.objects.acreate(email="ana@example.com")
    await grant(room, ana, Role.EDIT)
    laptop, phone = await signed(ana), await signed(ana)
    async with CollabServer() as server, create_task_group() as tg:
        async with (
            Peer(server, room, tg, laptop, Role.EDIT) as a,
            Peer(server, room, tg, phone, Role.EDIT) as b,
        ):
            await until(lambda: room in server.rooms and len(server.rooms[room].clients) == 2)
            await sync_to_async(sessions.ended)(ana, sessions.numbered(phone.session))
            await server.revoke()
            await until(b.cut_off)
            assert not a.cut_off()


@pytest.mark.parametrize("path", ["/api/collab/", "/api/collab/a/b", "/api/collab/memo"])
async def test_a_malformed_room_path_is_refused(path):
    sent = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    async with CollabServer() as server:
        await server({"type": "websocket", "path": path}, receive, send)
    assert sent == [{"type": "websocket.close"}]


@database
def session_cookie() -> str:
    client = Client()
    client.force_login(User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71"))
    return f"sessionid={client.cookies['sessionid'].value}"


async def readable() -> str:
    room = await tab()
    await grant(room, await User.objects.aget(email="ivo@example.com"), Role.READ)
    return room


async def handshake(origin: str, cookie: str, room: str | None = None) -> dict:
    messages = iter([{"type": "websocket.connect"}, {"type": "websocket.disconnect", "code": 1000}])
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    headers = [
        (b"host", b"ponistra.example"),
        (b"origin", origin.encode()),
        (b"cookie", cookie.encode()),
    ]
    room = room or await tab()
    scope = {"type": "websocket", "path": f"/api/collab/{room}", "headers": headers}
    async with CollabServer() as server:
        await server(scope, receive, send)
    closed = [message for message in sent[:2] if message["type"] == "websocket.close"]
    return closed[0] if closed else sent[0]


async def test_a_signed_in_browser_on_the_same_origin_is_accepted():
    cookie = await session_cookie()
    accepted = await handshake("https://ponistra.example", cookie, await readable())
    assert accepted == {"type": "websocket.accept"}


async def test_a_documents_own_room_takes_the_same_rights_as_its_tabs():
    cookie = await session_cookie()
    accepted = await handshake("https://ponistra.example", cookie, await own_room(await readable()))
    refused = await handshake("https://ponistra.example", cookie, await own_room(await tab()))
    assert (accepted, refused) == ({"type": "websocket.accept"}, CLOSED)


@database
def a_file() -> Node:
    blob = store.put(io.BytesIO(b"%PDF-1.7\n%%EOF\n"))
    return Node.objects.create(kind=Node.Kind.FILE, title="Ugovor", blob=blob)


async def test_a_files_room_keeps_its_notes_beside_it_for_whoever_reads_it():
    cookie = await session_cookie()
    file, other = await a_file(), await a_file()
    await Grant.objects.acreate(
        node=file, user=await User.objects.aget(email="ivo@example.com"), role=Role.READ
    )
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, str(file.room), tg) as a, Peer(server, str(file.room), tg) as b:
            a.text += "istaknuto"
            await until(lambda: str(b.text) == "istaknuto")
        await until(lambda: not server.rooms)
    row = await Update.objects.aget(room=file.room)
    assert (row.tab_id, row.document_id) == (None, file.pk)
    accepted = await handshake("https://ponistra.example", cookie, str(file.room))
    refused = await handshake("https://ponistra.example", cookie, str(other.room))
    assert (accepted, refused) == ({"type": "websocket.accept"}, CLOSED)


async def test_a_user_without_a_grant_is_closed_once_accepted():
    refused = await handshake("https://ponistra.example", await session_cookie())
    assert refused == CLOSED


async def test_an_anonymous_browser_is_closed_once_accepted():
    assert await handshake("https://ponistra.example", "sessionid=forged") == CLOSED


@pytest.mark.parametrize("origin", ["https://elsewhere.example", ""])
async def test_a_foreign_handshake_is_refused(origin):
    assert await handshake(origin, await session_cookie()) == {"type": "websocket.close"}


@pytest.mark.parametrize("state", ["document_id", "trashed", "trashed_parent", "missing"])
async def test_only_a_tab_or_own_state_of_a_live_document_is_a_room(state):
    cookie = await session_cookie()
    ivo = await User.objects.aget(email="ivo@example.com")
    if state == "missing":
        room = "00000000-0000-4000-8000-000000000000"
    elif state == "document_id":
        room = str((await Tab.objects.aget(room=await readable())).document_id)
    elif state == "trashed":
        room = await tab(trashed_at=timezone.now())
        await grant(room, ivo, Role.OWN)
    else:
        parent = await Node.objects.acreate(
            kind=Node.Kind.FOLDER, title="Mapa", trashed_at=timezone.now()
        )
        await Grant.objects.acreate(node=parent, user=ivo, role=Role.OWN)
        room = await tab(parent=parent)
    refused = await handshake("https://ponistra.example", cookie, room)
    assert refused == CLOSED


def running(*operations: dict):
    return lambda doc, sheets: carry_out(doc, sheets, list(operations), "hr", "run")


async def test_a_run_opens_an_idle_room_and_leaves_it_stored_with_its_tables_computed():
    memo = await tab()
    document = await Node.objects.aget(tabs__room=memo)
    old, _ = written([Block("paragraph", "a", runs=[Run("Cijene")])])
    await Update.objects.acreate(document=document, room=memo, data=old.get_update())
    rows = [[2], [{"formula": "A1*3"}]]
    async with CollabServer() as server, create_task_group():
        done = await server.perform(
            memo, running({"op": "table", "at": {"end": "body"}, "rows": rows})
        )
        assert not server.rooms
    made = done.made[0]
    state = Doc()
    async for data in Update.objects.filter(room=memo).values_list("data", flat=True):
        state.apply_update(bytes(data))
    held = await database(grids.of_tab)(await Tab.objects.aget(room=memo))
    typed, computed = (key_of(row, made["cols"][0]) for row in made["rows"])
    assert held[made["table"]].told() == {
        typed: {"text": "2", "kind": "number"},
        computed: {"text": "6", "kind": "number"},
    }
    assert [block.id for block in read(state, held)] == ["a", made["table"]]


async def test_a_run_is_taken_back_with_what_it_deleted_once_its_room_has_closed():
    memo = await tab()
    document = await Node.objects.aget(tabs__room=memo)
    old, _ = written([Block("paragraph", "a", runs=[Run("Prvi")]), Block("paragraph", "b")])
    await Update.objects.acreate(document=document, room=memo, data=old.get_update())
    async with CollabServer() as server, create_task_group():
        done = await server.perform(memo, running({"op": "delete", "from": "a"}))
        await server.perform(memo, lambda doc, sheets: take_back(done.change))
        assert not server.rooms
    state = Doc()
    async for data in Update.objects.filter(room=memo).values_list("data", flat=True):
        state.apply_update(bytes(data))
    assert [(block.id, block.text) for block in read(state, {})] == [("a", "Prvi"), ("b", "")]


async def test_a_run_reaches_the_clients_of_a_live_room_and_leaves_it_open():
    memo = await tab()
    insert = {"op": "insert", "at": {"end": "body"}, "blocks": [{"type": "paragraph"}]}
    text = {"type": "text", "text": "Novo"}
    async with CollabServer() as server, create_task_group() as tg:
        async with Peer(server, memo, tg) as peer:
            await until(lambda: server.rooms)
            done = await server.perform(memo, running(insert))
            (id,) = done.made[0]["blocks"]
            replace = {"op": "text", "range": {"block": id}, "content": [text]}
            await server.perform(memo, running(replace))
            assert memo in server.rooms
            await until(lambda: [block.text for block in read(peer.doc, {})] == ["Novo"])
        await until(lambda: not server.rooms)
