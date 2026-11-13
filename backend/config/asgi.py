import os
from contextlib import suppress

from anyio import create_task_group
from django.core.asgi import get_asgi_application
from starlette.requests import ClientDisconnect

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()

# Imported after get_asgi_application(), which fills the app registry the models need.
from apps.actions.batches import batches  # noqa: E402
from apps.actions.runs import interrupted  # noqa: E402
from apps.agents import server as agents  # noqa: E402
from apps.backups.backups import nightly  # noqa: E402
from apps.backups.offsite import follow as offsite  # noqa: E402
from apps.blobs.edits import follow as edit  # noqa: E402
from apps.blobs.previews import draw  # noqa: E402
from apps.blobs.store import collecting  # noqa: E402
from apps.calendar.sync import calendars  # noqa: E402
from apps.collab import live  # noqa: E402
from apps.collab.server import collab  # noqa: E402
from apps.collab.watch import GRID_PATH, watch  # noqa: E402
from apps.contacts.sync import contacts  # noqa: E402
from apps.content.elements import follow  # noqa: E402
from apps.content.words import follow as words  # noqa: E402
from apps.core import address  # noqa: E402
from apps.core.asyncdb import database  # noqa: E402
from apps.documents import links  # noqa: E402
from apps.documents.paging import paginate  # noqa: E402
from apps.drive.sync import drives  # noqa: E402
from apps.health.watch import watch as health  # noqa: E402
from apps.identity.directories import directories  # noqa: E402
from apps.jobs.work import interrupted as jobs_interrupted  # noqa: E402
from apps.jobs.work import work  # noqa: E402
from apps.mail.later import interrupted as mail_interrupted  # noqa: E402
from apps.mail.later import later  # noqa: E402
from apps.mail.sync import mail  # noqa: E402
from apps.meetings import lobby  # noqa: E402
from apps.memory.night import nightly as memory  # noqa: E402
from apps.push.notices import deliver  # noqa: E402
from apps.retention.sweep import sweeping  # noqa: E402
from apps.search.extraction import extract  # noqa: E402
from apps.search.ocr import recognise  # noqa: E402
from apps.shares.sync import shares  # noqa: E402
from apps.versions.history import keep  # noqa: E402
from apps.workspace import terminal  # noqa: E402

mcp_application = agents.application()


async def refused_stream(scope, receive, send) -> None:
    """A GET on the MCP path asks for a stream of the server's own notifications, which a
    stateless server never sends; the SDK would hold it open for ever, and an open stream
    holds uvicorn's shutdown, so a reload or an upgrade would wait on the agent's client."""
    await send(
        {
            "type": "http.response.start",
            "status": 405,
            "headers": [(b"allow", b"POST, DELETE"), (b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


async def application(scope, receive, send) -> None:
    match scope["type"]:
        case "http" if agents.serves(scope["path"]):
            if agents.streams(scope):
                await refused_stream(scope, receive, send)
            else:
                # The SDK reads a request's body without minding a client gone half way; there
                # is nobody left to answer.
                with suppress(ClientDisconnect):
                    await mcp_application(scope, receive, send)
        case "http":
            await django_application(scope, receive, send)
        case "websocket" if GRID_PATH.fullmatch(scope["path"]):
            await watch(scope, receive, send)
        case "websocket" if scope["path"] == live.PATH:
            await live.socket(scope, receive, send)
        case "websocket" if scope["path"] == lobby.PATH:
            await lobby.socket(scope, receive, send)
        case "websocket" if scope["path"] == terminal.PATH:
            await terminal.socket(scope, receive, send)
        case "websocket":
            await collab(scope, receive, send)
        case "lifespan":
            await lifespan(receive, send)


async def lifespan(receive, send) -> None:
    await receive()
    await database(interrupted)()
    await database(jobs_interrupted)()
    await database(mail_interrupted)()
    async with collab, agents.server.session_manager.run(), create_task_group() as background:
        background.start_soon(keep)
        background.start_soon(live.listen)
        background.start_soon(extract)
        background.start_soon(recognise)
        background.start_soon(draw)
        background.start_soon(collecting)
        background.start_soon(links.follow)
        background.start_soon(edit)
        background.start_soon(follow)
        background.start_soon(words)
        background.start_soon(paginate)
        background.start_soon(batches)
        background.start_soon(work)
        background.start_soon(nightly)
        background.start_soon(offsite)
        background.start_soon(mail)
        background.start_soon(later)
        background.start_soon(contacts)
        background.start_soon(calendars)
        background.start_soon(shares)
        background.start_soon(drives)
        background.start_soon(deliver)
        background.start_soon(address.follow)
        background.start_soon(health)
        background.start_soon(directories)
        background.start_soon(sweeping)
        background.start_soon(memory)
        await send({"type": "lifespan.startup.complete"})
        await receive()
        background.cancel_scope.cancel()
    await send({"type": "lifespan.shutdown.complete"})
