"""The owner's code workspace (D34): where it is, opening the one here, and the door Caddy and
Vite ask before every request and WebSocket that reaches it. One elsewhere has a door of its own.
The workspace lists its projects, chats and rounds of chats when asked, shows a chat's transcript,
carries out what the owner asks of it from the page of code (each a `Command` it reports on as it
goes, D52), and says when what it lists changed, which reaches the owner's tabs as the area
`workspace`. Each project it lists is matched here with the board of its plan, `Plan <name>`."""

import base64
import hmac
import json
import logging
import re
from datetime import datetime, timedelta

import httpx2
import icu
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models.expressions import RawSQL
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.blobs import store
from apps.blobs.models import Blob, Upload
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.users.sessions import CONFIRMED as CONFIRMED_AT
from apps.users.sessions import fresh

from .models import Aside, Command

logger = logging.getLogger(__name__)

OPENED = "workspace_opened_at"
# A window reconnecting through a closed door cannot sign in, its WebSocket only fails.
OPEN_FOR = timedelta(days=7)
ASKED_WITHIN = 10
AREA = "workspace"
# What the workspace says of a command its owner should hear: gone, closed or busy meanwhile.
PASSED = {404, 409}
ROUND = re.compile(r"[A-Za-z0-9._-]{1,100}")
SESSION = re.compile(r"[0-9a-f-]{36}")
# Claude Code's short name of a model, which the workspace checks against those it offers.
MODEL = re.compile(r"[a-z0-9.-]{1,40}")
HASH = re.compile(r"[0-9a-f]{64}")
PLAN = "Plan "
BY_NAME = icu.Collator.createInstance(icu.Locale("hr"))
LISTED = 50
SAID = 20_000
TITLE = 100
Kind = Command.Kind
State = Command.State
# What only a recent confirmation of who the owner is lets through (D33), for a working day: the
# owner works on this page for hours, where the other sensitive actions are done now and then.
CONFIRMED = {Kind.PUSH, Kind.RESTART}
CONFIRMED_FOR = timedelta(hours=8)
BY_SESSION = {
    Kind.SAY,
    Kind.ANSWER,
    Kind.RENAME,
    Kind.MODEL,
    Kind.OPEN,
    Kind.CLOSE,
    Kind.ARCHIVE,
    Kind.STOP,
}
BY_ROUND = {Kind.START, Kind.CONSOLIDATE, Kind.PUSH, Kind.AUTO}
ANSWERS = {"yes", "no"}
SWITCHES = {"on", "off"}
# What a chat's model reads as a picture, each small enough to reach it whole.
PICTURES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PICTURED = 4
PICTURE_SIZE = 3_750_000
# A command only moves on: what the workspace reports late never takes it back.
AFTER = {
    State.TAKEN: [State.SENT],
    State.DONE: [State.SENT, State.TAKEN],
    State.FAILED: [State.SENT, State.TAKEN],
}


def owns(user) -> bool:
    return bool(settings.WORKSPACE) and user.is_active and user.email.lower() == settings.WORKSPACE


def kept_here() -> bool:
    return bool(settings.WORKSPACE) and not settings.WORKSPACE_URL


def workspace_of(user) -> dict | None:
    if not owns(user):
        return None
    return {"url": settings.WORKSPACE_URL or "/code/", "here": kept_here()}


@api("POST", confirmed=("POST",), confirmed_for=CONFIRMED_FOR)
def opened(request):
    if not owns(request.user) or not kept_here():
        return JsonResponse({"error": "not_the_owner"}, status=403)
    request.session[OPENED] = timezone.now().isoformat()
    return JsonResponse({"ok": True})


@api("POST", confirmed=("POST",), confirmed_for=CONFIRMED_FOR)
def terminal(request):
    """Whether the owner may open a terminal now (terminal.py), which asks them first to confirm
    who they are."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    if not settings.WORKSPACE_TOKEN:
        return JsonResponse({"error": "workspace_not_linked"}, status=503)
    return JsonResponse({"ok": True})


async def _asked(
    method: str, path: str, payload: dict | None = None, params: dict | None = None
) -> dict:
    if not settings.WORKSPACE_TOKEN:
        raise Refused(503, "workspace_not_linked")
    base = "http://workspace:8081" if kept_here() else settings.WORKSPACE_URL.rstrip("/")
    try:
        async with httpx2.AsyncClient(timeout=ASKED_WITHIN, trust_env=False) as client:
            answer = await client.request(
                method,
                f"{base}/ponistra/{path}",
                headers={"Authorization": f"Bearer {settings.WORKSPACE_TOKEN}"},
                json=payload,
                params=params,
            )
    except httpx2.HTTPError as error:
        logger.warning("the code workspace did not answer %s %s: %s", method, path, error)
        raise Refused(502, "workspace_unreachable") from error
    if answer.status_code in PASSED and path != "projects":
        raise Refused(answer.status_code, answer.json().get("error", "refused"))
    if answer.status_code != 200:
        logger.warning("the code workspace refused %s %s: %s", method, path, answer.status_code)
        raise Refused(502, "workspace_unreachable")
    return answer.json()


def _plans(user, names: list[str]) -> dict[str, dict]:
    """The board of each project's plan the owner can read, titled `Plan <name>`, the name the
    project's folder or the first part of it (`Plan OPUS` for `opus-library`)."""
    # The boards reach this module through the board's owner check.
    from apps.access import rights
    from apps.documents import boards
    from apps.documents.models import Node
    from apps.documents.printing import compact

    readable, params = rights.readable(user)
    found = {}
    for node in boards.among(
        Node.objects.filter(pk__in=RawSQL(readable, params), title__istartswith=PLAN)
    ).order_by("updated_at"):
        found[node.title[len(PLAN) :].strip().lower()] = node
    planned = {}
    for name in names:
        folder = name.lower()
        keys = [key for key in found if folder == key or folder.startswith(f"{key}-")]
        if keys:
            planned[name] = found[max(keys, key=len)]
    return {
        name: {"title": node.title, "path": f"/p/{compact(node.pk)}"}
        for name, node in planned.items()
    }


def _ran(project: dict) -> datetime | None:
    """When anything in the project last ran: a chat, or a round begun or any of its chats."""
    times = [chat.get("at") for chat in project.get("chats", [])]
    for round in project.get("rounds", []):
        members = [round.get("coordinator") or {}, *round.get("chats", [])]
        times += [round.get("created"), round.get("started"), *(each.get("at") for each in members)]
    return max((datetime.fromisoformat(each) for each in times if each), default=None)


def _aside(user, projects: list[dict]) -> None:
    """Marks each project its owner put under Others and nothing has run in since; the projects
    stand by name as Croatian orders it, the general one first."""
    put = dict(Aside.objects.filter(owner=user).values_list("name", "at"))
    for project in projects:
        name, ran = project.get("name"), _ran(project)
        project["aside"] = name in put and (ran is None or ran <= put[name])
    projects.sort(
        key=lambda project: (
            project.get("name") is not None,
            BY_NAME.getSortKey(project.get("name") or ""),
        )
    )


@api("GET", "POST")
async def projects(request):
    """The workspace's projects with their plans, or a project put under Others or back."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    if request.method == "POST":
        given = body(request)
        name, aside = given.get("name"), given.get("aside")
        if not isinstance(name, str) or not name or len(name) > 255 or "/" in name:
            raise Refused(400, "invalid_name")
        if not isinstance(aside, bool):
            raise Refused(400, "invalid_aside")
        if aside:
            await database(Aside.objects.update_or_create)(owner=request.user, name=name)
        else:
            await database(Aside.objects.filter(owner=request.user, name=name).delete)()
        return HttpResponse(status=204)
    listed = await _asked(
        "GET", "projects", params={"measured": 1} if "measured" in request.GET else None
    )
    found = listed.get("projects", [])
    named = [project["name"] for project in found if project.get("name")]
    plans = await database(_plans)(request.user, named)
    for project in found:
        project["plan"] = plans.get(project.get("name"))
    await database(_aside)(request.user, found)
    return JsonResponse(listed)


@api("GET")
async def chat(request, session):
    """What was said in a chat of the workspace, its owner's and the agent's words and the tools
    it used, latest last."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    if not SESSION.fullmatch(session):
        raise Refused(400, "invalid_session")
    return JsonResponse(await _asked("GET", f"chats/{session}"))


def shown(command: Command) -> dict:
    return {
        "id": command.pk,
        "kind": command.kind,
        "folder": command.folder or None,
        "round": command.round or None,
        "session": command.session or None,
        "text": command.text or None,
        "images": command.images,
        "auto": command.auto,
        "state": command.state,
        "error": command.error or None,
        "created_at": command.created_at.isoformat(),
        "changed_at": command.changed_at.isoformat(),
    }


def _text(given: dict, allowed: set[str] | None = None) -> str:
    text = given.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > SAID:
        raise Refused(400, "invalid_text")
    if allowed is not None and text not in allowed:
        raise Refused(400, "invalid_text")
    return text.strip()


def _pictures(user, given: dict) -> list[dict]:
    """The images the owner uploaded to go with a chat's message, as its model reads them."""
    listed = given.get("images", [])
    if not isinstance(listed, list) or len(listed) > PICTURED:
        raise Refused(400, "invalid_images")
    if not all(isinstance(sha256, str) and HASH.fullmatch(sha256) for sha256 in listed):
        raise Refused(400, "invalid_images")
    blobs = {
        blob.pk: blob
        for blob in Blob.objects.filter(
            pk__in=listed, media_type__in=PICTURES, size__lte=PICTURE_SIZE
        ).filter(pk__in=Upload.objects.filter(user=user).values("blob_id"))
    }
    if len(blobs) != len(set(listed)):
        raise Refused(400, "invalid_images")
    return [
        {
            "media_type": blobs[sha256].media_type,
            "data": base64.b64encode(store.path_of(sha256).read_bytes()).decode(),
        }
        for sha256 in listed
    ]


def _asked_of(user, given: dict) -> tuple[dict, list[dict]]:
    """The fields of a command of its kind, each checked before it reaches the workspace, and the
    images that go with it."""
    kind = given.get("kind")
    if kind not in Kind.values:
        raise Refused(400, "invalid_command")
    fields: dict = {"kind": kind}
    pictures: list[dict] = []
    # A round consolidated and closed leaves its coordinator, told to push by its session.
    after = kind == Kind.PUSH and "round" not in given
    if kind in BY_ROUND and not after:
        round = given.get("round")
        if not isinstance(round, str) or not ROUND.fullmatch(round):
            raise Refused(400, "invalid_round")
        fields["round"] = round
    if kind in BY_SESSION or after:
        session = given.get("session")
        if not isinstance(session, str) or not SESSION.fullmatch(session):
            raise Refused(400, "invalid_session")
        fields["session"] = session
    if kind == Kind.CHAT:
        folder = given.get("folder")
        if not isinstance(folder, str) or not folder.startswith("/") or len(folder) > 500:
            raise Refused(400, "invalid_folder")
        fields.update(folder=folder, text=_text(given))
    elif kind == Kind.SAY:
        fields["text"] = _text(given)
    elif kind == Kind.ANSWER:
        fields["text"] = _text(given, ANSWERS)
    elif kind == Kind.RENAME:
        title = _text(given)
        if len(title) > TITLE or "\n" in title:
            raise Refused(400, "invalid_text")
        fields["text"] = title
    elif kind == Kind.MODEL:
        model = _text(given)
        if not MODEL.fullmatch(model):
            raise Refused(400, "invalid_model")
        fields["text"] = model
    elif kind == Kind.AUTO:
        fields["text"] = _text(given, SWITCHES)
    if kind in (Kind.CHAT, Kind.SAY):
        pictures = _pictures(user, given)
        fields["images"] = len(pictures)
    return fields, pictures


def settled(pk: int, state: str, error: str = "") -> None:
    Command.objects.filter(pk=pk, state__in=AFTER[state]).update(
        state=state, error=error[:60], changed_at=timezone.now()
    )


def _begun(pk: int, session) -> None:
    if isinstance(session, str) and SESSION.fullmatch(session):
        Command.objects.filter(pk=pk, kind=Kind.CHAT).update(session=session)


async def sent(command: Command, pictures: list[dict] | None = None) -> Command:
    """Hands the command to the workspace, which takes it at once or says why not."""
    payload = {"id": command.pk, "kind": command.kind, "auto": command.auto}
    for name in ("folder", "round", "session", "text"):
        if value := getattr(command, name):
            payload[name] = value
    if pictures:
        payload["images"] = pictures
    try:
        answer = await _asked("POST", "commands", payload)
    except Refused as refused:
        await database(settled)(command.pk, State.FAILED, refused.error)
    else:
        await database(_begun)(command.pk, answer.get("session"))
        if answer.get("state") in AFTER:
            await database(settled)(command.pk, answer["state"])
    return await database(Command.objects.get)(pk=command.pk)


def _recent() -> list[dict]:
    return [shown(each) for each in Command.objects.order_by("-created_at", "-pk")[:LISTED]]


@api("GET", "POST")
async def commands(request):
    """What the owner asked of the workspace lately, and asking it something more."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    if request.method == "GET":
        return JsonResponse({"commands": await database(_recent)()})
    fields, pictures = await database(_asked_of)(request.user, body(request))
    if fields["kind"] in CONFIRMED and not fresh(
        await request.session.aget(CONFIRMED_AT), CONFIRMED_FOR
    ):
        return JsonResponse({"error": "confirm_required"}, status=403)
    command = await database(Command.objects.create)(**fields)
    return JsonResponse(shown(await sent(command, pictures)))


def reported(outcomes) -> None:
    """What the workspace says became of the commands it was sent."""
    if not isinstance(outcomes, list):
        return
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        pk, state, error = outcome.get("id"), outcome.get("state"), outcome.get("error")
        if isinstance(pk, int) and state in AFTER:
            settled(pk, state, error if isinstance(error, str) else "")


@csrf_exempt
def changed(request):
    """The workspace saying that what it lists changed, with the token it is asked with."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    given = request.headers.get("Authorization", "")
    if not settings.WORKSPACE_TOKEN or not hmac.compare_digest(
        given.encode(), f"Bearer {settings.WORKSPACE_TOKEN}".encode()
    ):
        return JsonResponse({"error": "refused"}, status=403)
    try:
        said = json.loads(request.body or b"{}")
    except ValueError:
        said = {}
    if isinstance(said, dict):
        reported(said.get("commands"))
    # live reaches this module through the users' session, which says where the workspace is.
    from apps.collab.live import CHANGES

    owners = get_user_model().objects.filter(email__iexact=settings.WORKSPACE, is_active=True)
    with connection.cursor() as cursor:
        for owner in owners.values_list("pk", flat=True):
            cursor.execute("SELECT pg_notify(%s, %s)", [CHANGES, f"{AREA} u{owner}"])
    from apps.workspace.notices import told

    told()
    return HttpResponse(status=204)


def door(request):
    since = request.session.get(OPENED)
    if (
        request.user.is_authenticated
        and owns(request.user)
        and kept_here()
        and since is not None
        and timezone.now() - datetime.fromisoformat(since) < OPEN_FOR
    ):
        return HttpResponse(status=204)
    return HttpResponse(status=403)
