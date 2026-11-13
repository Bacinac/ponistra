"""PONISTRA as an MCP server (D18): the server an outside agent calls at /api/mcp with a bearer
token, and the OAuth doors it gets the token through, all under /api/agents and the well-known
paths beside Django in the one ASGI app (config/asgi.py)."""

from types import SimpleNamespace

from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.handlers.revoke import RevocationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.routes import build_metadata
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from apps.core.asyncdb import database
from apps.users.sessions import address_of

from . import oauth

MCP_PATH = "/api/mcp"
AUTH_PATH = "/api/agents"
DOORS = {"authorize", "token", "register", "revoke"}
INSTRUCTIONS = """PONISTRA is an office suite: documents of text, tables, presentations and PDF \
files in folders, boards (pages of HTML you write for the user to open in PONISTRA, each keeping \
data of its own), mail, a \
calendar, contacts and tasks. You act as the user who let you in, with \
their rights and nothing more. Ids are UUIDs for documents, tabs and folders, numbers elsewhere. \
Read a tab before editing it: each block's id stands before its text, and operations address \
blocks and cells by those ids. What you write into a document lands as proposals the user accepts \
or rejects; a board you rewrite keeps its page before as a version; a reply or new message you \
draft waits for the user to send it; what you do to mail, marking, moving or snoozing it, is \
done at once. Mail is the user's own and that of the shared mailboxes they reach. Nothing here \
deletes, but for what a board keeps."""

provider = oauth.Provider()
registration = ClientRegistrationOptions(enabled=True)
revocation = RevocationOptions(enabled=True)
server = MCPServer(
    "ponistra",
    instructions=INSTRUCTIONS,
    token_verifier=provider,
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(oauth.issuer()),
        resource_server_url=AnyHttpUrl(oauth.mcp_url()),
        validate_token_resource=True,
        client_registration_options=registration,
        revocation_options=revocation,
    ),
    # Its tools never change, so there is nothing to listen for, and a listen stream held open
    # holds every reload and upgrade, as the GET stream would.
    subscriptions=False,
)
authenticator = oauth.Authenticator(provider)
metadata = MetadataHandler(
    build_metadata(AnyHttpUrl(oauth.issuer()), None, registration, revocation)
)
# RFC 8414: an issuer with a path is described under the well-known path with its own appended;
# the root is kept too, for a client that asks there first.
server.custom_route(f"/.well-known/oauth-authorization-server{AUTH_PATH}", ["GET"])(metadata.handle)
server.custom_route("/.well-known/oauth-authorization-server", ["GET"])(metadata.handle)
server.custom_route(f"{AUTH_PATH}/authorize", ["GET", "POST"])(
    AuthorizationHandler(provider).handle
)
server.custom_route(f"{AUTH_PATH}/token", ["POST"])(TokenHandler(provider, authenticator).handle)
registrar = RegistrationHandler(provider, options=registration)


def _address(request) -> str | None:
    meta = {
        "HTTP_CF_CONNECTING_IP": request.headers.get("cf-connecting-ip", ""),
        "HTTP_X_FORWARDED_FOR": request.headers.get("x-forwarded-for", ""),
        "REMOTE_ADDR": request.client.host if request.client else "",
    }
    return address_of(SimpleNamespace(META=meta))


@server.custom_route(f"{AUTH_PATH}/register", ["POST"])
async def register(request):
    """Anyone may register a client, as MCP's clients register themselves, but one address only
    so many that nobody has let in yet."""
    address = _address(request)
    if await database(oauth.crowded)(address):
        return JSONResponse({"error": "too_many_registrations"}, status_code=429)
    oauth.registering.set(address)
    return await registrar.handle(request)


server.custom_route(f"{AUTH_PATH}/revoke", ["POST"])(
    RevocationHandler(provider, authenticator).handle
)


def serves(path: str) -> bool:
    """Whether the path is the MCP server's or one of its OAuth doors, rather than Django's."""
    if path == MCP_PATH or path.startswith("/.well-known/oauth-"):
        return True
    return path.startswith(f"{AUTH_PATH}/") and path.removeprefix(f"{AUTH_PATH}/") in DOORS


def streams(scope) -> bool:
    """Whether the request asks the MCP server for its standalone stream of notifications."""
    return scope["path"] == MCP_PATH and scope["method"] == "GET"


def application() -> Starlette:
    """The ASGI app of the server with its tools, each request on its own: a client holds a
    token, not a session, so a restart loses it nothing."""
    from . import tools  # noqa: F401

    return server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        host="0.0.0.0",
    )
