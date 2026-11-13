import base64
import hashlib
import io
import secrets
import zipfile
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx2 as httpx
import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.test import AsyncClient
from django.utils import timezone

from apps.actions.models import ActionRun
from apps.actions.registry import ACTIONS
from apps.agents import oauth, tools
from apps.agents import server as agents
from apps.agents.models import Client, Grant, Token
from apps.blobs import store
from apps.content.blocks import Block, Run
from apps.content.tests.helpers import Room, fill
from apps.documents.models import Tab
from apps.help.tests.test_help import shelf  # noqa: F401
from apps.mail import sharing
from apps.mail.models import Account, Attachment, Draft, Folder, Message, Unsent
from apps.mail.models import Grant as MailGrant
from apps.mail.tests.mox import letter
from apps.mail.tests.test_views import kept
from apps.search.models import BlobText, PdfOcr
from apps.search.tests.test_search import extract_all, pdf_bytes
from apps.users.models import User
from apps.versions.models import FileVersion

pytestmark = [pytest.mark.anyio, pytest.mark.django_db(transaction=True)]

JSON = "application/json"
BACK = "http://localhost:9/back"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": JSON,
    "MCP-Protocol-Version": "2025-06-18",
}


def challenge_of(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class Agent:
    """An MCP client at the doors: registers, is sent to consent, exchanges the code and calls
    the tools with the bearer token it got."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.client_id = ""
        self.client_secret = ""
        self.tokens: dict = {}

    async def register(self, name="Claude") -> dict:
        response = await self.http.post(
            "/api/agents/register",
            json={
                "client_name": name,
                "redirect_uris": [BACK],
                "token_endpoint_auth_method": "client_secret_post",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        assert response.status_code == 201, response.text
        made = response.json()
        self.client_id, self.client_secret = made["client_id"], made["client_secret"]
        return made

    async def authorize(self, verifier: str, resource: str | None = None, state="s1") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": BACK,
            "response_type": "code",
            "code_challenge": challenge_of(verifier),
            "code_challenge_method": "S256",
            "state": state,
        }
        if resource:
            params["resource"] = resource
        response = await self.http.get("/api/agents/authorize", params=params)
        assert response.status_code == 302, response.text
        return response.headers["location"]

    async def token(self, **form) -> httpx.Response:
        return await self.http.post(
            "/api/agents/token",
            data={"client_id": self.client_id, "client_secret": self.client_secret, **form},
        )

    async def exchange(self, code: str, verifier: str) -> dict:
        response = await self.token(
            grant_type="authorization_code",
            code=code,
            code_verifier=verifier,
            redirect_uri=BACK,
            resource=oauth.mcp_url(),
        )
        assert response.status_code == 200, response.text
        self.tokens = response.json()
        return self.tokens

    async def rpc(self, method: str, params: dict | None = None) -> httpx.Response:
        return await self.http.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={**MCP_HEADERS, "Authorization": f"Bearer {self.tokens['access_token']}"},
        )

    async def call(self, tool: str, **arguments) -> dict:
        response = await self.rpc("tools/call", {"name": tool, "arguments": arguments})
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert not result.get("isError"), result
        return result["structuredContent"]

    async def refused(self, tool: str, **arguments) -> str:
        response = await self.rpc("tools/call", {"name": tool, "arguments": arguments})
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result.get("isError"), result
        return result["content"][0]["text"]


@pytest.fixture
async def doors():
    app = agents.application()
    transport = httpx.ASGITransport(app=app)
    async with (
        agents.server.session_manager.run(),
        httpx.AsyncClient(transport=transport, base_url=settings.PUBLIC_URL) as http,
    ):
        yield Agent(http)
    # As after `live`: the thread Django shares outside a request keeps its connection open.
    await sync_to_async(connections.close_all)()


async def let_in(agent: Agent, browser: AsyncClient, verifier: str) -> dict:
    """The user's side: the consent page the sign-in sent them to, answered yes."""
    sent = await agent.authorize(verifier)
    assert sent.startswith(f"{oauth.CONSENT_PATH}?request=")
    request = parse_qs(urlsplit(sent).query)["request"][0]
    asked = await browser.get(f"/api/agents/consent?request={request}")
    assert asked.status_code == 200, asked.content
    assert asked.json()["client"] == "Claude"
    assert asked.json()["redirect"] == BACK
    answered = await browser.post(
        "/api/agents/consent", {"request": request, "allow": True}, content_type=JSON
    )
    assert answered.status_code == 200, answered.content
    back = urlsplit(answered.json()["redirect"])
    assert f"{back.scheme}://{back.netloc}{back.path}" == BACK
    return {key: value[0] for key, value in parse_qs(back.query).items()}


def stored(user, subject: str) -> Message:
    """A message in the user's inbox, as taking keeps one."""
    account = kept(user)
    inbox = Folder.objects.create(owner=user, name="inbox", role="inbox")
    raw = store.put(io.BytesIO(bytes(letter(subject))))
    return Message.objects.create(
        owner=user,
        folder=inbox,
        account=account,
        key="1",
        raw=raw,
        subject=subject,
        date=datetime(2026, 10, 26, 9, tzinfo=UTC),
    )


async def signed_in() -> tuple[User, AsyncClient]:
    user = await sync_to_async(User.objects.create_user)(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )
    browser = AsyncClient()
    await browser.aforce_login(user)
    return user, browser


async def test_the_metadata_names_the_installation_as_issuer_and_the_server_as_resource(doors):
    found = await doors.http.get("/.well-known/oauth-authorization-server/api/agents")
    assert found.status_code == 200
    assert found.json()["issuer"] == oauth.issuer()
    assert found.json()["token_endpoint"] == f"{oauth.issuer()}/token"
    assert found.json()["code_challenge_methods_supported"] == ["S256"]
    resource = await doors.http.get("/.well-known/oauth-protected-resource/api/mcp")
    assert resource.status_code == 200
    assert resource.json() == {
        "resource": oauth.mcp_url(),
        "authorization_servers": [oauth.issuer()],
        "bearer_methods_supported": ["header"],
    }
    unsigned = await doors.http.post(
        "/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=MCP_HEADERS
    )
    assert unsigned.status_code == 401
    assert "invalid_token" in unsigned.headers["www-authenticate"]


async def test_one_address_registers_only_so_many_clients_nobody_let_in(doors):
    for n in range(oauth.MOST_UNUSED):
        await doors.register(f"Agent {n}")
    refused = await doors.http.post("/api/agents/register", json={"redirect_uris": [BACK]})
    assert (refused.status_code, refused.json()) == (429, {"error": "too_many_registrations"})
    elsewhere = await doors.http.post(
        "/api/agents/register",
        json={"redirect_uris": [BACK]},
        headers={"X-Forwarded-For": "198.51.100.9"},
    )
    assert elsewhere.status_code == 201

    user = await sync_to_async(User.objects.create_user)("ivo@example.com", "Kamen-Most-Rijeka-71")
    first = await Client.objects.filter(address="127.0.0.1").afirst()
    await Grant.objects.acreate(client=first, user=user)
    await doors.register("Let in")
    stale = timezone.now() - oauth.UNUSED - timedelta(minutes=1)
    await Client.objects.filter(address="127.0.0.1", grants=None).aupdate(created_at=stale)
    await doors.register("After a day")
    assert await Client.objects.filter(address="127.0.0.1").acount() == 2


async def test_the_server_offers_no_stream_of_its_own_so_nothing_holds_a_shutdown():
    from config.asgi import application

    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": "/api/mcp", "headers": []}
    await application(scope, receive, send)
    assert sent[0]["status"] == 405
    assert (b"allow", b"POST, DELETE") in sent[0]["headers"]


async def test_an_agent_registers_the_user_lets_it_in_and_it_acts_as_them(doors, live):
    user, browser = await signed_in()
    await doors.register()
    client = await Client.objects.aget(client_id=doors.client_id)
    assert client.name == "Claude"
    assert client.secret_digest == oauth.digest(doors.client_secret)
    assert client.secret_digest != doors.client_secret

    verifier = secrets.token_urlsafe(48)
    back = await let_in(doors, browser, verifier)
    assert back["state"] == "s1"
    grant = await Grant.objects.select_related("client").aget(user=user, revoked_at=None)
    assert grant.client == client

    wrong = await doors.token(
        grant_type="authorization_code",
        code=back["code"],
        code_verifier="not-the-verifier",
        redirect_uri=BACK,
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "invalid_grant"
    tokens = await doors.exchange(back["code"], verifier)
    assert tokens["token_type"].lower() == "bearer"
    assert tokens["expires_in"] == int(oauth.ACCESS.total_seconds())
    assert await Token.objects.filter(grant=grant).acount() == 2
    assert not await Token.objects.filter(digest=tokens["access_token"]).aexists()
    twice = await doors.token(
        grant_type="authorization_code",
        code=back["code"],
        code_verifier=verifier,
        redirect_uri=BACK,
    )
    assert twice.status_code == 400

    listed = await doors.rpc("tools/list")
    assert listed.status_code == 200, listed.text
    tools = {each["name"]: each for each in listed.json()["result"]["tools"]}
    assert {"me", "search", "read_tab", "edit_tab", "draft_reply", "add_task"} <= set(tools)
    assert "text_summarise" in tools and "nodes_extract" not in tools
    assert tools["edit_tab"]["outputSchema"]["type"] == "object"

    who = await doors.call("me")
    assert who == {
        "user": {"id": user.pk, "name": "Ivo Bošković", "email": "ivo@example.com"},
        "client": "Claude",
    }
    grant = await Grant.objects.aget(pk=grant.pk)
    assert grant.used_at is not None

    made = await doors.call("create_document", title="Ponuda")
    tab = await Tab.objects.select_related("document").aget(pk=made["tab"])
    assert tab.document.title == "Ponuda"
    await sync_to_async(fill)(tab, [Block("paragraph", "a", runs=[Run("Najam stana")])])
    read = await doors.call("read_tab", tab=made["tab"])
    assert "Najam stana" in read["text"]
    content = [{"type": "text", "text": "kuće"}]
    edited = await doors.call(
        "edit_tab",
        tab=made["tab"],
        operations=[
            {"op": "text", "range": {"block": "a", "from": 6, "to": 11}, "content": content}
        ],
    )
    assert edited["run"]["action"] == "agent.edit"
    assert edited["run"]["via"] == "Claude"
    run = await ActionRun.objects.aget(pk=edited["run"]["id"])
    assert run.grant_id == grant.pk and run.user_id == user.pk
    (block,) = (await sync_to_async(Room.of)(tab)).read()
    assert [(each.text, set(each.marks)) for each in block.runs] == [
        ("Najam ", set()),
        ("stana", {"deletion"}),
        ("kuće", {"insertion"}),
    ]
    assert block.runs[2].marks["insertion"]["author"] == "Claude via Ivo Bošković"
    empty = await doors.refused("edit_tab", tab=made["tab"], operations=[])
    assert "one to 200 operations" in empty

    added = await doors.call("add_task", text="Nazvati Marka", due="2026-10-30")
    assert added["text"] == "Nazvati Marka"
    assert [each["text"] for each in (await doors.call("list_tasks"))["tasks"]] == ["Nazvati Marka"]

    assert "not_found" in await doors.refused("read_tab", tab=str(tab.document_id))

    message = await sync_to_async(stored)(user, "Ponuda")
    read = await doors.call("read_message", message=message.pk)
    assert read["subject"] == "Ponuda" and read["text"] == "Pozdrav iz Zagreba.\n"
    assert read["drafts"] == []
    drafted = await doors.call("draft_reply", message=message.pk, text="Hvala, javljam se.")
    assert (drafted["way"], drafted["by"]) == ("reply", "Claude")
    draft = await Draft.objects.select_related("grant").aget(pk=drafted["id"])
    assert draft.grant_id == grant.pk and draft.owner_id == user.pk
    wrong_way = await doors.refused("draft_reply", message=message.pk, text="x", way="bcc")
    assert "way must be" in wrong_way
    read = await doors.call("read_message", message=message.pk)
    assert [each["text"] for each in read["drafts"]] == ["Hvala, javljam se."]
    corrected = await doors.call(
        "draft_reply", message=message.pk, text="Hvala.", replaces=drafted["id"]
    )
    assert corrected["id"] == drafted["id"] and corrected["text"] == "Hvala."
    assert "not_found" in await doors.refused(
        "draft_reply", message=message.pk, text="x", replaces=drafted["id"] + 1
    )

    listed = await doors.call("list_mail")
    assert [each["id"] for each in listed["messages"]] == [message.pk]
    assert [each["address"] for each in listed["accounts"]] == [
        (await Account.objects.aget(owner=user)).address
    ]
    assert (await doors.call("list_mail", since="2026-10-27"))["messages"] == []
    await Message.objects.filter(pk=message.pk).aupdate(seen=True)
    assert (await doors.call("list_mail", unread=True))["messages"] == []
    assert "folder must be" in await doors.refused("list_mail", folder="nowhere")

    new = await doors.call(
        "draft_mail", to=["Ana <ana@example.com>"], subject="Ponuda", text="Pozdrav,\n\n<lp>"
    )
    assert new["to"] == [{"name": "Ana", "address": "ana@example.com"}]
    assert new["html"].startswith("<p>Pozdrav,</p><p></p><p>&lt;lp&gt;</p>")
    fixed = await doors.call(
        "draft_mail", to=["ana@example.com"], subject="Ponuda", text="lp,", replaces=new["id"]
    )
    assert fixed["id"] == new["id"] and fixed["html"].startswith("<p>lp,</p>")
    await Unsent.objects.filter(pk=new["id"]).aupdate(written={"subject": "Moje"})
    assert "not_found" in await doors.refused(
        "draft_mail", to=["ana@example.com"], subject="x", text="y", replaces=new["id"]
    )
    assert "needs a recipient" in await doors.refused("draft_mail", to=[], subject="x", text="y")


def _shared(owner: User, colleague: User, role: str) -> tuple[User, Message]:
    """A mailbox the owner made and shares with the colleague as the role, with a message in it."""
    box = sharing.made(owner, "Prodaja")
    MailGrant.objects.create(mailbox=box, user=colleague, role=role, created_by=owner)
    message = stored(box, "Upit kupca")
    return box, message


async def test_an_agent_does_to_mail_what_the_list_does_but_delete_it(doors):
    user, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    await doors.exchange((await let_in(doors, browser, verifier))["code"], verifier)
    tools_listed = {
        each["name"] for each in (await doors.rpc("tools/list")).json()["result"]["tools"]
    }
    assert {"mail_seen", "mail_move", "mail_block", "mail_always"} <= tools_listed
    assert not {"mail_delete", "mail_triage"} & tools_listed
    on_mail = {each.id for each in ACTIONS.values() if each.target == "messages" and not each.model}
    assert set(tools.MAIL_DOES) == on_mail - {"mail.delete"}
    message = await sync_to_async(stored)(user, "Ponuda")

    assert (await doors.call("mail_seen", messages=[message.pk])) == {"changed": 1}
    assert (await Message.objects.aget(pk=message.pk)).seen
    moved = await doors.call("mail_move", messages=[message.pk], parameters={"to": "archive"})
    assert moved == {"changed": 1}
    found = await Message.objects.select_related("folder").aget(pk=message.pk)
    assert found.folder.role == "archive"
    assert "invalid_parameters" in await doors.refused("mail_move", messages=[message.pk])
    assert "not_found" in await doors.refused("mail_flagged", messages=[message.pk + 1])
    run = await ActionRun.objects.filter(action="mail.move").aget()
    assert run.grant_id == (await Grant.objects.aget(user=user)).pk
    assert (run.user_id, run.target, run.state) == (user.pk, {"messages": [message.pk]}, "done")

    ana = await sync_to_async(User.objects.create_user)("ana@example.com", "Kamen-Most-Rijeka-71")
    box, shared = await sync_to_async(_shared)(ana, user, "read")
    read = await doors.call("read_message", message=shared.pk)
    assert (read["subject"], read["mailbox"]) == ("Upit kupca", box.pk)
    listed = await doors.call("list_mail", mailbox=box.pk)
    assert [each["id"] for each in listed["messages"]] == [shared.pk]
    assert listed["mailboxes"] == [{"id": box.pk, "name": "Prodaja", "role": "read"}]
    assert "forbidden" in await doors.refused("mail_flagged", messages=[shared.pk])
    assert "forbidden" in await doors.refused("draft_reply", message=shared.pk, text="Hvala.")
    await MailGrant.objects.filter(mailbox=box, user=user).aupdate(role="edit")
    assert (await doors.call("mail_flagged", messages=[shared.pk])) == {"changed": 1}
    drafted = await doors.call("draft_reply", message=shared.pk, text="Hvala.")
    assert (await Draft.objects.aget(pk=drafted["id"])).owner_id == box.pk
    both = [message.pk, shared.pk]
    assert "several_mailboxes" in await doors.refused("mail_seen", messages=both)
    await MailGrant.objects.filter(mailbox=box, user=user).adelete()
    assert "not_found" in await doors.refused("read_message", message=shared.pk)


def _carrying(message: Message, part: str, name: str, content: bytes, inline: bool = False) -> None:
    Attachment.objects.create(
        message=message,
        blob=store.put(io.BytesIO(content)),
        part=part,
        name=name,
        type="application/octet-stream",
        inline=inline,
    )


def _archive(name: str, content: str) -> bytes:
    kept_in = io.BytesIO()
    with zipfile.ZipFile(kept_in, "w") as archive:
        archive.writestr(name, content)
    return kept_in.getvalue()


async def test_an_agent_reads_the_text_of_what_a_message_carries_and_never_its_bytes(doors):
    user, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    await doors.exchange((await let_in(doors, browser, verifier))["code"], verifier)
    message = await sync_to_async(stored)(user, "Uputa")
    pdf = pdf_bytes("Uvod", "Dodaj suglasnost")
    await sync_to_async(_carrying)(message, "2", "uputa.pdf", pdf)
    await sync_to_async(_carrying)(message, "3", "vpn.zip", _archive("client.key", "TAJNI KLJUC"))
    await sync_to_async(_carrying)(message, "4", "slika.pdf", pdf_bytes("Ugradeno"), inline=True)

    before = await doors.call("read_attachment", message=message.pk, part="2")
    assert (before["pages"], before["unread"]) == ([], "waiting")

    await sync_to_async(extract_all)()
    read = await doors.call("read_attachment", message=message.pk, part="2")
    assert (read["name"], read["media_type"], read["page_count"]) == (
        "uputa.pdf",
        "application/pdf",
        2,
    )
    assert read["pages"] == [
        {"page": 1, "text": "Uvod"},
        {"page": 2, "text": "Dodaj suglasnost"},
    ]
    assert "cut" not in read and "unread" not in read

    archive = await doors.call("read_attachment", message=message.pk, part="3")
    assert (archive["pages"], archive["unread"]) == ([], "not_text")
    assert "TAJNI" not in str(archive)

    assert "not_found" in await doors.refused("read_attachment", message=message.pk, part="4")
    assert "not_found" in await doors.refused("read_attachment", message=message.pk, part="9")

    stranger = await sync_to_async(User.objects.create_user)(
        "drugi@example.com", "Kamen-Most-Rijeka-72"
    )
    theirs = await sync_to_async(stored)(stranger, "Tuđe")
    await sync_to_async(_carrying)(theirs, "2", "tude.pdf", pdf)
    assert "not_found" in await doors.refused("read_attachment", message=theirs.pk, part="2")


async def test_a_reading_of_a_file_says_what_keeps_it_from_being_all_of_its_text(
    doors, monkeypatch
):
    user, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    await doors.exchange((await let_in(doors, browser, verifier))["code"], verifier)
    message = await sync_to_async(stored)(user, "Uputa")
    await sync_to_async(_carrying)(message, "2", "uputa.pdf", pdf_bytes("Uvod", "Dodaj suglasnost"))
    await sync_to_async(_carrying)(message, "3", "krivo.pdf", pdf_bytes("Krivo"))
    await sync_to_async(extract_all)()

    monkeypatch.setattr(tools, "PAGE_TEXT", 6)
    cut = await doors.call("read_attachment", message=message.pk, part="2")
    assert cut["cut"] is True
    assert cut["pages"] == [{"page": 1, "text": "Uvod"}, {"page": 2, "text": "Do"}]
    monkeypatch.setattr(tools, "PAGE_TEXT", 4)
    cut = await doors.call("read_attachment", message=message.pk, part="2")
    assert cut["cut"] is True and cut["pages"] == [{"page": 1, "text": "Uvod"}]
    monkeypatch.setattr(tools, "PAGE_TEXT", 200_000)

    file = await Attachment.objects.select_related("blob").aget(message=message, part="2")
    await PdfOcr.objects.acreate(
        blob=file.blob, state=PdfOcr.State.FAILED, queued_at=datetime(2026, 11, 6, tzinfo=UTC)
    )
    assert (await doors.call("read_attachment", message=message.pk, part="2"))["ocr"] == "failed"

    wrong = await Attachment.objects.select_related("blob").aget(message=message, part="3")
    await BlobText.objects.filter(blob=wrong.blob).aupdate(failed="PdfiumError()")
    broken = await doors.call("read_attachment", message=message.pk, part="3")
    assert (broken["pages"], broken["unread"]) == ([], "failed")


async def test_a_refresh_rotates_the_tokens_and_a_revoked_grant_ends_them(doors):
    user, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    first = await doors.exchange((await let_in(doors, browser, verifier))["code"], verifier)
    refreshed = await doors.token(grant_type="refresh_token", refresh_token=first["refresh_token"])
    assert refreshed.status_code == 200, refreshed.text
    second = refreshed.json()
    assert second["access_token"] != first["access_token"]
    assert second["refresh_token"] != first["refresh_token"]
    again = await doors.token(grant_type="refresh_token", refresh_token=first["refresh_token"])
    assert again.status_code == 400
    assert again.json()["error"] == "invalid_grant"
    grant = await Grant.objects.aget(user=user, revoked_at=None)
    # The first access token stands until it expires; the refresh token it came with is spent.
    assert await Token.objects.filter(grant=grant).acount() == 3
    doors.tokens = first
    assert (await doors.rpc("tools/list")).status_code == 200
    doors.tokens = second
    assert (await doors.rpc("tools/list")).status_code == 200

    listed = await browser.get("/api/agents/clients")
    assert listed.json()["url"] == oauth.mcp_url()
    assert [each["client"] for each in listed.json()["clients"]] == ["Claude"]
    revoked = await browser.delete(f"/api/agents/clients/{grant.pk}")
    assert revoked.status_code == 204
    assert (await doors.rpc("tools/list")).status_code == 401
    assert not await Token.objects.filter(grant=grant).aexists()
    grant = await Grant.objects.aget(pk=grant.pk)
    assert grant.revoked_at is not None
    assert (await browser.get("/api/agents/clients")).json()["clients"] == []


async def test_a_sign_in_for_another_resource_or_with_the_wrong_secret_is_refused(doors):
    user, browser = await signed_in()
    await doors.register()
    sent = await doors.authorize("verifier", resource="https://elsewhere.example/mcp")
    assert sent.startswith(BACK)
    assert parse_qs(urlsplit(sent).query)["error"] == ["invalid_target"]
    assert not await Grant.objects.filter(user=user).aexists()

    verifier = secrets.token_urlsafe(48)
    back = await let_in(doors, browser, verifier)
    doors.client_secret = "wrong"
    forged = await doors.token(
        grant_type="authorization_code",
        code=back["code"],
        code_verifier=verifier,
        redirect_uri=BACK,
    )
    assert forged.status_code == 401
    assert forged.json()["error"] == "invalid_client"


async def test_a_refusal_at_the_consent_sends_the_agent_back_without_a_code(doors):
    user, browser = await signed_in()
    await doors.register()
    sent = await doors.authorize("verifier")
    request = parse_qs(urlsplit(sent).query)["request"][0]
    answered = await browser.post(
        "/api/agents/consent", {"request": request, "allow": False}, content_type=JSON
    )
    assert answered.status_code == 200
    back = parse_qs(urlsplit(answered.json()["redirect"]).query)
    assert back == {"error": ["access_denied"], "state": ["s1"]}
    assert not await Grant.objects.filter(user=user).aexists()
    expired = await browser.get(f"/api/agents/consent?request={request}")
    assert expired.status_code == 404
    assert expired.json()["error"] == "request_expired"


async def test_an_agent_puts_links_on_the_users_page_by_group_and_only_once(doors):
    _, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    await doors.exchange((await let_in(doors, browser, verifier))["code"], verifier)
    plan = "https://claude.ai/artifact/TgYRFP2aZw7oQ8y4KbuB9W"

    assert "invalid_href" in await doors.refused("add_link", url="ftp://claude.ai/plan")
    made = await doors.call("add_link", url=plan, title="Plan", group="Claude artefakti")
    assert (made["title"], made["href"], made["group"], made["added"]) == (
        "Plan",
        plan,
        "Claude artefakti",
        True,
    )
    again = await doors.call("add_link", url=plan, title="Drugo", group="claude ARTEFAKTI")
    assert (again["id"], again["title"], again["group"], again["added"]) == (
        made["id"],
        "Plan",
        "Claude artefakti",
        False,
    )
    other = await doors.call("add_link", url="claude.ai/artifact/drugi", group="Claude artefakti")
    loose = await doors.call("add_link", url=plan, title="Plan")
    assert (other["href"], other["title"], other["added"]) == (
        "https://claude.ai/artifact/drugi",
        "claude.ai",
        True,
    )
    assert (loose["group"], loose["added"]) == (None, True)

    page = (await browser.get("/api/links")).json()
    [group] = page["groups"]
    assert group["title"] == "Claude artefakti"
    assert {each["id"]: each["parent"] for each in page["links"]} == {
        made["id"]: group["id"],
        other["id"]: group["id"],
        loose["id"]: page["folder"],
    }


async def test_an_agent_keeps_data_on_a_board_and_reads_it_by_field(doors):
    _, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    await doors.exchange((await let_in(doors, browser, verifier))["code"], verifier)
    page = "<!doctype html><html><body>Plan</body></html>"
    made = await doors.call("write_board", html=page, title="Plan", group="Ponistra")
    writes = [
        {"op": "set", "collection": "koraci", "key": f"k{at}", "data": {"staza": staza, "n": at}}
        for at, staza in enumerate("ABA")
    ]
    written = await doors.call("write_board_data", board=made["id"], writes=writes)
    assert [each["version"] for each in written["written"]] == [1, 1, 1]

    held = await doors.call("read_board_data", board=made["id"])
    assert held["collections"] == [{"collection": "koraci", "count": 3}]
    first = await doors.call("read_board_data", board=made["id"], collection="koraci", limit=2)
    assert [each["key"] for each in first["entries"]] == ["k0", "k1"]
    assert first["next"] == "k1"
    rest = await doors.call(
        "read_board_data", board=made["id"], collection="koraci", limit=2, after=first["next"]
    )
    assert ([each["key"] for each in rest["entries"]], rest["next"]) == (["k2"], None)
    only = await doors.call(
        "read_board_data", board=made["id"], collection="koraci", where={"staza": "A"}
    )
    assert [each["key"] for each in only["entries"]] == ["k0", "k2"]
    one = await doors.call("read_board_data", board=made["id"], collection="koraci", key="k1")
    assert one["data"] == {"staza": "B", "n": 1}

    changes = [
        {"op": "update", "collection": "koraci", "key": "k1", "data": {"n": 9}, "if_version": 1},
        {"op": "delete", "collection": "koraci", "key": "k2"},
    ]
    await doors.call("write_board_data", board=made["id"], writes=changes)
    one = await doors.call("read_board_data", board=made["id"], collection="koraci", key="k1")
    assert (one["data"], one["version"]) == ({"staza": "B", "n": 9}, 2)
    assert "version_conflict" in await doors.refused(
        "write_board_data",
        board=made["id"],
        writes=[{"op": "set", "collection": "koraci", "key": "k1", "data": {}, "if_version": 1}],
    )


async def test_an_agent_writes_a_board_rewrites_it_and_reads_it_back(doors):
    user, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    await doors.exchange((await let_in(doors, browser, verifier))["code"], verifier)
    page = "<!doctype html><html><body><h1>Prodaja</h1></body></html>"

    assert "title" in await doors.refused("write_board", html=page, group="Baba")
    assert "group" in await doors.refused("write_board", html=page, title="Prodaja")
    assert "not_a_page" in await doors.refused(
        "write_board", html="<h1>x</h1>", title="Prodaja", group="Baba"
    )
    made = await doors.call("write_board", html=page, title="Prodaja", group="Baba")
    assert (made["title"], made["group"], made["version"]) == ("Prodaja", "Baba", 1)
    assert made["url"].startswith(f"{settings.PUBLIC_URL}/p/")
    read = await doors.call("read_document", document=made["id"])
    assert (read["board"], read["html"]) == (True, page)

    later = page.replace("Prodaja", "Nabava")
    again = await doors.call("write_board", html=later, board=made["id"], title="Nabava")
    assert (again["id"], again["title"], again["group"], again["version"]) == (
        made["id"],
        "Nabava",
        "Baba",
        2,
    )
    moved = await doors.call("move_board", board=made["id"], group="dida")
    assert (moved["group"], moved["version"]) == ("dida", 2)
    assert (await doors.call("move_board", board=made["id"], group="DIDA"))["group"] == "dida"
    regrouped = await doors.call("write_board", html=later, board=made["id"], group="Baba")
    assert (regrouped["group"], regrouped["version"]) == ("Baba", 2)
    versions = FileVersion.objects.filter(node=made["id"]).order_by("number")
    assert [(each.agent, each.created_by_id) async for each in versions] == [
        ("Claude", user.pk),
        ("Claude", user.pk),
    ]
    assert (await doors.call("read_document", document=made["id"]))["html"] == later
    document = await doors.call("create_document", title="Ponuda")
    assert "not_a_board" in await doors.refused("write_board", html=page, board=document["id"])
    assert "not_a_board" in await doors.refused("move_board", board=document["id"], group="Baba")


@pytest.mark.usefixtures("shelf")
async def test_an_agent_finds_and_reads_the_help_in_the_users_language(doors, live):
    _, browser = await signed_in()
    await doors.register()
    verifier = secrets.token_urlsafe(48)
    back = await let_in(doors, browser, verifier)
    await doors.exchange(back["code"], verifier)

    found = await doors.call("search_help", query="odgoda")
    assert "mail/snoozing" in [each["id"] for each in found["articles"]]
    assert "admin/users" not in [each["id"] for each in found["articles"]]
    page = await doors.call("read_help", article="mail/snoozing")
    assert page["title"] == "Odgoda poruke"
    assert "## Kako se koristi" in page["text"]
    assert "no such article" in await doors.refused("read_help", article="mail/nothing")
