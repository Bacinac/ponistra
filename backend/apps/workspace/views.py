"""The owner's code workspace (D34): where it is, opening the one here, and the door Caddy and
Vite ask before every request and WebSocket that reaches it. One elsewhere has a door of its own.
The workspace lists its projects, chats and rounds of chats when asked, shows a chat's transcript,
carries out what the owner asks of it from the page of code (each a `Command` it reports on as it
goes, D52), shows and writes the files of its projects (PJ6), and says when what it lists changed,
which reaches the owner's tabs as the area `workspace`. Each project it lists is matched here with
the board of its plan, `Plan <name>`."""

import base64
import hmac
import json
import logging
import re
from datetime import UTC, datetime, timedelta

import httpx2
import icu
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models.expressions import RawSQL
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.csrf import csrf_exempt

from apps.agents import oauth
from apps.agents.models import Grant, Token
from apps.blobs import store
from apps.blobs.models import Blob, Upload
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.core.sealed import seal
from apps.users.sessions import CONFIRMED as CONFIRMED_AT
from apps.users.sessions import fresh

from . import sheets
from . import spend as spending
from . import worked as measured
from .models import Aside, Command, Limits, Removal, Sheet

logger = logging.getLogger(__name__)

OPENED = "workspace_opened_at"
# A window reconnecting through a closed door cannot sign in, its WebSocket only fails.
OPEN_FOR = timedelta(days=7)
ASKED_WITHIN = 10
AREA = "workspace"
# What the workspace says of a command its owner should hear: gone, closed or busy meanwhile.
PASSED = {404, 409}
FILES_PASSED = {400, 403, 404, 409, 413}
FILE_PATH = 4096
ROUND = re.compile(r"[A-Za-z0-9._-]{1,100}")
SESSION = re.compile(r"[0-9a-f-]{36}")
PLACE = re.compile(r"\d{1,15}")
# Claude Code's short name of a model, which the workspace checks against those it offers.
MODEL = re.compile(r"[a-z0-9.-]{1,40}")
HASH = re.compile(r"[0-9a-f]{64}")
PLAN = "Plan "
BY_NAME = icu.Collator.createInstance(icu.Locale("hr"))
LISTED = 50
SAID = 20_000
TITLE = 100
NAMESPACE = re.compile(rf"-[A-Za-z0-9_-]{{0,254}}|{measured.CLOCKIFY}")
TRANSCRIPT = re.compile(r"[A-Za-z0-9-]{1,64}")
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
TRANSCRIPTS_SENT = 100
STRETCHES_SENT = 10_000
# Milliseconds since 1970 up to 2100, the bounds of a moment a transcript can hold.
LATEST = 4_102_444_800_000
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
    Kind.MOVE,
}
BY_ROUND = {Kind.START, Kind.CONSOLIDATE, Kind.PUSH, Kind.AUTO, Kind.MOVE, Kind.CANCEL}
# A start's conditions (PJ4), each with what it takes besides `pause`.
CONDITIONS = {"time", "reset", "below", "round", "red"}
REPEATS = {"day", "week"}
WAITING_ID = re.compile(r"\d{1,18}")
SPENT_SENT = 2_000
MODEL_NAME = re.compile(r"[A-Za-z0-9._:@-]{1,100}")
WINDOW_KINDS = {"session", "week", "model"}
ANSWERS = {"yes", "no"}
SWITCHES = {"on", "off"}
# What a chat's model reads as a picture, each small enough to reach it whole.
PICTURES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PICTURED = 4
PICTURE_SIZE = 3_750_000
# A command only moves on: what the workspace reports late never takes it back.
AFTER = {
    State.WAITING: [State.SENT],
    State.TAKEN: [State.SENT],
    State.DONE: [State.SENT, State.WAITING, State.TAKEN],
    State.FAILED: [State.SENT, State.WAITING, State.TAKEN],
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


def _address(path: str) -> tuple[str, dict]:
    if not settings.WORKSPACE_TOKEN:
        raise Refused(503, "workspace_not_linked")
    base = "http://workspace:8081" if kept_here() else settings.WORKSPACE_URL.rstrip("/")
    return f"{base}/ponistra/{path}", {"Authorization": f"Bearer {settings.WORKSPACE_TOKEN}"}


def _refused(method: str, path: str, answer, passed: set[int]) -> Refused:
    """The workspace's refusal as the owner's, where it is about what they asked; its token
    refused is a fault of the link instead."""
    error = answer.json().get("error", "refused") if answer.status_code in passed else None
    if error and error != "refused":
        return Refused(answer.status_code, error)
    logger.warning("the code workspace refused %s %s: %s", method, path, answer.status_code)
    return Refused(502, "workspace_unreachable")


async def _asked(
    method: str,
    path: str,
    payload: dict | None = None,
    params: dict | None = None,
    passed: set[int] = PASSED,
) -> dict:
    url, headers = _address(path)
    try:
        async with httpx2.AsyncClient(timeout=ASKED_WITHIN, trust_env=False) as client:
            answer = await client.request(method, url, headers=headers, json=payload, params=params)
    except httpx2.HTTPError as error:
        logger.warning("the code workspace did not answer %s %s: %s", method, path, error)
        raise Refused(502, "workspace_unreachable") from error
    if answer.status_code != 200:
        raise _refused(method, path, answer, set() if path == "projects" else passed)
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
    it used, latest last: its last turns, the page ending `before` a place in its transcript, or
    all `from` one."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    if not SESSION.fullmatch(session):
        raise Refused(400, "invalid_session")
    place = {}
    for name in ("before", "from"):
        value = request.GET.get(name)
        if value is None:
            continue
        if not PLACE.fullmatch(value):
            raise Refused(400, f"invalid_{name}")
        place[name] = value
    return JsonResponse(await _asked("GET", f"chats/{session}", params=place or None))


def _placed(given) -> dict:
    """A path within one of the workspace's projects, as the workspace checks it again."""
    folder, path = given.get("folder"), given.get("path", "")
    if not isinstance(folder, str) or not folder.startswith("/") or len(folder) > FILE_PATH:
        raise Refused(400, "invalid_folder")
    if not isinstance(path, str) or len(path) > FILE_PATH or "\0" in path:
        raise Refused(400, "invalid_path")
    return {"folder": folder, "path": path}


@api("GET")
async def files(request):
    """A folder's entries within a project of the workspace, folders first."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    return JsonResponse(
        await _asked("GET", "files", params=_placed(request.GET), passed=FILES_PASSED)
    )


@api("GET", "POST", confirmed=("POST",), confirmed_for=CONFIRMED_FOR)
async def file(request):
    """A file of a project with its text and its hash where it is text small enough to edit, or
    its text written anew while the file is still what that hash says (PJ6)."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    if request.method == "GET":
        placed = _placed(request.GET)
        return JsonResponse(await _asked("GET", "files/read", params=placed, passed=FILES_PASSED))
    given = body(request)
    placed = _placed(given)
    text, hash = given.get("text"), given.get("hash")
    if not isinstance(text, str):
        raise Refused(400, "invalid_text")
    if not isinstance(hash, str) or not HASH.fullmatch(hash):
        raise Refused(400, "invalid_hash")
    payload = {**placed, "text": text, "hash": hash}
    return JsonResponse(await _asked("POST", "files/write", payload, passed=FILES_PASSED))


@api("GET")
async def file_raw(request):
    """A file of a project as it is, downloaded."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    placed = _placed(request.GET)
    url, headers = _address("files/raw")
    client = httpx2.AsyncClient(timeout=httpx2.Timeout(ASKED_WITHIN, read=None), trust_env=False)
    try:
        answer = await client.send(
            client.build_request("GET", url, headers=headers, params=placed), stream=True
        )
    except httpx2.HTTPError as error:
        await client.aclose()
        logger.warning("the code workspace did not send %s: %s", placed["path"], error)
        raise Refused(502, "workspace_unreachable") from error
    if answer.status_code != 200:
        await answer.aread()
        await answer.aclose()
        await client.aclose()
        raise _refused("GET", "files/raw", answer, FILES_PASSED)

    async def sent():
        try:
            async for part in answer.aiter_bytes():
                yield part
        finally:
            await answer.aclose()
            await client.aclose()

    name = placed["path"].rstrip("/").rsplit("/", 1)[-1] or "file"
    sized = (
        {"Content-Length": answer.headers["content-length"]}
        if "content-length" in answer.headers
        else {}
    )
    return StreamingHttpResponse(
        sent(),
        content_type="application/octet-stream",
        headers={
            "Content-Disposition": content_disposition_header(True, name),
            "Cache-Control": "private, no-store",
            **sized,
        },
    )


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
        "when": command.when,
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


def _percent(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
        raise Refused(400, "invalid_when")
    return value


def _when(given, repeats: bool) -> dict:
    """A condition to start on (PJ4): a moment, once or, for a chat, every day or week; the weekly
    window beginning anew; the five-hour window below a percent; another round closed; or the
    night's run of the project's gate failing; and the weekly percent at which what it started
    stops working, if any."""
    if not isinstance(given, dict) or given.get("on") not in CONDITIONS:
        raise Refused(400, "invalid_when")
    on = given["on"]
    when: dict = {"on": on}
    if given.get("pause") is not None:
        when["pause"] = _percent(given["pause"])
    if on == "time":
        at, every = given.get("at"), given.get("every")
        try:
            moment = datetime.fromisoformat(at) if isinstance(at, str) else None
        except ValueError:
            moment = None
        if moment is None or moment.tzinfo is None:
            raise Refused(400, "invalid_when")
        if every is not None and (not repeats or every not in REPEATS):
            raise Refused(400, "invalid_when")
        when.update(at=moment.astimezone(UTC).isoformat(), every=every)
    elif on == "below":
        when["percent"] = _percent(given.get("percent"))
    elif on == "round":
        round = given.get("round")
        if not isinstance(round, str) or not ROUND.fullmatch(round):
            raise Refused(400, "invalid_when")
        when["round"] = round
    return when


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
    if kind in BY_ROUND and kind != Kind.CANCEL and not after:
        fields["round"] = _round_of(given)
    if kind in BY_SESSION or after:
        session = given.get("session")
        if not isinstance(session, str) or not SESSION.fullmatch(session):
            raise Refused(400, "invalid_session")
        fields["session"] = session
    if kind == Kind.CANCEL and "round" not in given:
        waiting = given.get("text")
        if not isinstance(waiting, str) or not WAITING_ID.fullmatch(waiting):
            raise Refused(400, "invalid_text")
        fields["text"] = waiting
    elif kind == Kind.CANCEL:
        fields["round"] = _round_of(given)
    if kind in (Kind.CHAT, Kind.START) and given.get("when") is not None:
        fields["when"] = _when(given["when"], kind == Kind.CHAT)
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


def _round_of(given: dict) -> str:
    round = given.get("round")
    if not isinstance(round, str) or not ROUND.fullmatch(round):
        raise Refused(400, "invalid_round")
    return round


def settled(pk: int, state: str, error: str = "", session=None) -> None:
    """What became of a command; a chat that waited on a condition names the session it started."""
    moved = {"state": state, "error": error[:60], "changed_at": timezone.now()}
    if isinstance(session, str) and SESSION.fullmatch(session):
        Command.objects.filter(pk=pk, kind=Kind.CHAT).exclude(session=session).update(
            session=session, changed_at=timezone.now()
        )
    Command.objects.filter(pk=pk, state__in=AFTER[state]).update(**moved)


def _withdrawn(command: Command) -> None:
    """A message or a start the workspace took back, which no later report moves on."""
    if command.kind == Kind.CANCEL and not command.round and command.state == State.DONE:
        Command.objects.filter(pk=int(command.text), kind__in=[Kind.SAY, Kind.CHAT]).update(
            state=State.FAILED, error="cancelled", changed_at=timezone.now()
        )


def _begun(pk: int, session) -> None:
    if isinstance(session, str) and SESSION.fullmatch(session):
        Command.objects.filter(pk=pk, kind=Kind.CHAT).update(session=session)


async def sent(command: Command, pictures: list[dict] | None = None) -> Command:
    """Hands the command to the workspace, which takes it at once or says why not."""
    payload = {"id": command.pk, "kind": command.kind, "auto": command.auto}
    for name in ("folder", "round", "session", "text", "when"):
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
    latest = list(Command.objects.order_by("-created_at", "-pk")[:LISTED])
    seen = {each.pk for each in latest}
    waiting = Command.objects.filter(state=Command.State.WAITING).exclude(pk__in=seen)
    return [shown(each) for each in [*latest, *waiting.order_by("-created_at", "-pk")]]


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
    command = await sent(await database(Command.objects.create)(**fields), pictures)
    await database(_withdrawn)(command)
    return JsonResponse(shown(command))


def reported(outcomes) -> None:
    """What the workspace says became of the commands it was sent."""
    if not isinstance(outcomes, list):
        return
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        pk, state, error = outcome.get("id"), outcome.get("state"), outcome.get("error")
        if isinstance(pk, int) and state in AFTER:
            settled(pk, state, error if isinstance(error, str) else "", outcome.get("session"))


def _window(given) -> dict:
    if not isinstance(given, dict) or given.get("kind") not in WINDOW_KINDS:
        raise ValueError
    name, percent, resets = given.get("name"), given.get("percent"), given.get("resets")
    if name is not None and (not isinstance(name, str) or len(name) > 100):
        raise ValueError
    if not isinstance(percent, int | float) or isinstance(percent, bool):
        raise ValueError
    if not 0 <= percent <= 1000:
        raise ValueError
    datetime.fromisoformat(resets)
    return {"kind": given["kind"], "name": name, "percent": percent, "resets": resets}


def limits_kept(given) -> None:
    """The plan's limits as the workspace measured them anew (PJ3), kept as they were."""
    if not isinstance(given, dict):
        return
    try:
        at = datetime.fromisoformat(given.get("at"))
        listed = given.get("windows")
        if not isinstance(listed, list) or len(listed) > 20 or at.tzinfo is None:
            raise ValueError
        windows = [_window(each) for each in listed]
        credits = given.get("credits")
        if credits is not None and not (
            isinstance(credits, dict)
            and isinstance(credits.get("used"), int | float)
            and isinstance(credits.get("currency"), str)
            and len(credits["currency"]) <= 10
        ):
            raise ValueError
    except TypeError, ValueError:
        logger.warning("the workspace told limits of a shape not known: %r", given)
        return
    Limits.objects.get_or_create(
        at=at, defaults={"windows": windows, "credits": credits and dict(credits)}
    )


def _from_workspace(request) -> bool:
    given = request.headers.get("Authorization", "")
    return bool(settings.WORKSPACE_TOKEN) and hmac.compare_digest(
        given.encode(), f"Bearer {settings.WORKSPACE_TOKEN}".encode()
    )


@csrf_exempt
def agent(request):
    """The key the workspace's agent reaches PONISTRA's MCP server with: the one it holds while it
    stands, else a new one in place of any the owner's workspace held before. A sign-in in the
    browser would send the code back to the browser's own machine, never to the workspace."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not _from_workspace(request):
        return JsonResponse({"error": "refused"}, status=403)
    owner = (
        get_user_model().objects.filter(email__iexact=settings.WORKSPACE, is_active=True).first()
    )
    if owner is None:
        return JsonResponse({"error": "not_found"}, status=404)
    try:
        held = json.loads(request.body or b"{}").get("key")
    except ValueError, AttributeError:
        held = None
    grants = Grant.objects.filter(
        user=owner, revoked_at=None, client__registered__key=oauth.WORKSPACE_KEY
    )
    if (
        isinstance(held, str)
        and Token.objects.filter(
            kind=Token.Kind.KEY, digest=oauth.digest(held), grant__in=grants
        ).exists()
    ):
        return JsonResponse({"key": held})
    with transaction.atomic():
        Token.objects.filter(grant__in=grants).delete()
        grants.update(revoked_at=timezone.now())
        _, secret = oauth.issued_key(owner, "Claude Code", oauth.WORKSPACE_KEY)
    return JsonResponse({"key": secret})


@csrf_exempt
def changed(request):
    """The workspace saying that what it lists changed, with the token it is asked with."""
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not _from_workspace(request):
        return JsonResponse({"error": "refused"}, status=403)
    try:
        said = json.loads(request.body or b"{}")
    except ValueError:
        said = {}
    if isinstance(said, dict):
        reported(said.get("commands"))
        limits_kept(said.get("limits"))
    # live reaches this module through the users' session, which says where the workspace is.
    from apps.collab.live import CHANGES

    owners = get_user_model().objects.filter(email__iexact=settings.WORKSPACE, is_active=True)
    with connection.cursor() as cursor:
        for owner in owners.values_list("pk", flat=True):
            cursor.execute("SELECT pg_notify(%s, %s)", [CHANGES, f"{AREA} u{owner}"])
    from apps.workspace.notices import told

    told()
    return HttpResponse(status=204)


def _moment(given) -> datetime:
    if not isinstance(given, int) or isinstance(given, bool) or not 0 <= given < LATEST:
        raise Refused(400, "invalid_stretches")
    return datetime.fromtimestamp(given // 1000, UTC) + timedelta(milliseconds=given % 1000)


def _count(given, name: str) -> int:
    value = given.get(name, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise Refused(400, "invalid_spent")
    return value


def _spent(listed) -> list[measured.Spent]:
    if listed is None:
        return []
    if not isinstance(listed, list) or len(listed) > SPENT_SENT:
        raise Refused(400, "invalid_spent")
    spent = []
    for each in listed:
        if not isinstance(each, dict):
            raise Refused(400, "invalid_spent")
        model = each.get("model")
        if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
            raise Refused(400, "invalid_spent")
        hour = _moment(each.get("hour"))
        if hour.minute or hour.second or hour.microsecond:
            raise Refused(400, "invalid_spent")
        spent.append(measured.Spent(hour, model, *(_count(each, name) for name in measured.TOKENS)))
    if len({(each.hour, each.model) for each in spent}) != len(spent):
        raise Refused(400, "invalid_spent")
    return spent


def _found(given: dict) -> measured.Found:
    chat, round, origin = given.get("chat") or "", given.get("round") or "", given.get("from", 0)
    last, title = given.get("last") or "", given.get("title") or ""
    if not isinstance(chat, str) or (chat and not TRANSCRIPT.fullmatch(chat)):
        raise Refused(400, "invalid_chat")
    if not isinstance(round, str) or (round and not ROUND.fullmatch(round)):
        raise Refused(400, "invalid_round")
    if not isinstance(origin, int) or isinstance(origin, bool) or origin < 0:
        raise Refused(400, "invalid_read")
    if not isinstance(last, str) or len(last) > 100:
        raise Refused(400, "invalid_last")
    if not isinstance(title, str):
        raise Refused(400, "invalid_title")
    return measured.Found(chat, round, origin, last, title[:200], _spent(given.get("spent")))


def _measured(
    given,
) -> tuple[str, str, str, int | None, list[tuple[datetime, datetime]], measured.Found]:
    if not isinstance(given, dict):
        raise Refused(400, "invalid_transcripts")
    namespace, session = given.get("namespace"), given.get("session")
    project, read, listed = given.get("project") or "", given.get("read"), given.get("stretches")
    if not isinstance(namespace, str) or not NAMESPACE.fullmatch(namespace):
        raise Refused(400, "invalid_namespace")
    if not isinstance(session, str) or not TRANSCRIPT.fullmatch(session):
        raise Refused(400, "invalid_session")
    if not isinstance(project, str) or len(project) > 255 or "/" in project:
        raise Refused(400, "invalid_project")
    if read is not None and (not isinstance(read, int) or isinstance(read, bool) or read < 0):
        raise Refused(400, "invalid_read")
    if not isinstance(listed, list) or len(listed) > STRETCHES_SENT:
        raise Refused(400, "invalid_stretches")
    spans = []
    for each in listed:
        if not isinstance(each, list) or len(each) != 2:
            raise Refused(400, "invalid_stretches")
        began, ended = _moment(each[0]), _moment(each[1])
        if ended < began:
            raise Refused(400, "invalid_stretches")
        spans.append((began, ended))
    return namespace, session, project, read, spans, _found(given)


@csrf_exempt
def worked(request):
    """The workspace asking how far it read each transcript, the answer it counted last in each,
    and how many days after archiving it removes a chat's transcript (VT3), or saying what
    stretches of work and tokens it found in some since (VT1, PJ3), with the token it is asked
    with."""
    if not _from_workspace(request):
        return JsonResponse({"error": "refused"}, status=403)
    if request.method == "GET":
        removal = Removal.objects.filter(pk=1).first()
        return JsonResponse({**measured.marks(), "removal": removal.after if removal else None})
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    try:
        listed = json.loads(request.body or b"{}").get("transcripts")
        if not isinstance(listed, list) or len(listed) > TRANSCRIPTS_SENT:
            raise Refused(400, "invalid_transcripts")
        found = [_measured(each) for each in listed]
    except ValueError, AttributeError:
        return JsonResponse({"error": "invalid_transcripts"}, status=400)
    except Refused as refused:
        return JsonResponse({"error": refused.error}, status=refused.status)
    for each in found:
        measured.kept(*each)
    return HttpResponse(status=204)


@api("GET")
def spend(request):
    """The tokens the workspace's chats took and what PONISTRA's own model runs cost, by month,
    and in one month by day, project, model, round and chat, with the plan's limits measured."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    month = request.GET.get("month")
    if month is not None and not MONTH.fullmatch(month):
        raise Refused(400, "invalid_month")
    return JsonResponse(spending.summed(month))


@api("GET")
def hours(request):
    """The time worked on the workspace's projects, by month and by day of one month."""
    if not owns(request.user):
        return JsonResponse({"error": "not_the_owner"}, status=403)
    month = request.GET.get("month")
    if month is not None and not MONTH.fullmatch(month):
        raise Refused(400, "invalid_month")
    return JsonResponse(measured.hours(month))


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


SHEET_KINDS = {kind.value for kind in Sheet.Kind}
SHEET_KEY = 200
SHEET_PROJECTS = 200


def _owner(request) -> None:
    if not owns(request.user):
        raise Refused(403, "not_the_owner")


def _sheet_shown(sheet: Sheet) -> dict:
    return {
        "kind": sheet.kind,
        "address": sheet.address,
        "person": sheet.person,
        "offered": sheet.offered,
        "projects": sheet.projects,
        "excluded": sheet.excluded,
        "label": sheet.label,
        "since": sheet.since.isoformat(),
        "nightly": sheet.nightly,
        "error": sheet.error or None,
        "written_at": sheet.written_at.isoformat() if sheet.written_at else None,
        "due": len(sheets.due(sheet)[1]),
    }


@api("GET", "PATCH")
def sheets_of(request):
    """What the time worked is written to and when archived chats' transcripts are removed."""
    _owner(request)
    removal = Removal.objects.filter(pk=1).first()
    if request.method == "PATCH":
        after = body(request).get("after")
        if after is not None and (
            not isinstance(after, int) or isinstance(after, bool) or not 0 <= after <= 365
        ):
            raise Refused(400, "invalid_removal")
        removal, _ = Removal.objects.update_or_create(pk=1, defaults={"after": after})
    projects = sorted({project for project, _ in measured.blocks().items()}, key=BY_NAME.getSortKey)
    return JsonResponse(
        {
            "projects": projects,
            "removal": removal.after if removal else None,
            "sheets": {sheet.kind: _sheet_shown(sheet) for sheet in Sheet.objects.all()},
        }
    )


def _sheet_text(given: dict, name: str, longest: int, required: bool = True) -> str:
    value = given.get(name, "")
    if (
        not isinstance(value, str)
        or len(value.strip()) > longest
        or (required and not value.strip())
    ):
        raise Refused(400, f"invalid_sheet_{name}")
    return value.strip()


def _sheet_changed(sheet: Sheet, given: dict) -> str | None:
    key = given.get("key")
    if key is not None:
        key = _sheet_text(given, "key", SHEET_KEY)
    elif not sheet.pk:
        raise Refused(400, "invalid_sheet_key")
    if sheet.kind == Sheet.Kind.TASKSTREAMER:
        sheet.address = _sheet_text(given, "address", 200)
        if not re.fullmatch(r"https?://[^\s/]+(/[^\s]*)?", sheet.address):
            raise Refused(400, "invalid_sheet_address")
        sheet.person = _sheet_text(given, "person", 254)
        if "@" not in sheet.person:
            raise Refused(400, "invalid_sheet_person")
    sheet.label = _sheet_text(given, "label", 100)
    since = given.get("since")
    try:
        sheet.since = datetime.strptime(since, "%Y-%m-%d").date()
    except TypeError, ValueError:
        raise Refused(400, "invalid_sheet_since") from None
    nightly = given.get("nightly")
    if not isinstance(nightly, bool):
        raise Refused(400, "invalid_sheet_nightly")
    sheet.nightly = nightly
    excluded = given.get("excluded", [])
    if (
        not isinstance(excluded, list)
        or len(excluded) > SHEET_PROJECTS
        or not all(isinstance(each, str) and len(each) <= 255 for each in excluded)
    ):
        raise Refused(400, "invalid_sheet_projects")
    sheet.excluded = sorted(set(excluded))
    projects = given.get("projects", {})
    if (
        not isinstance(projects, dict)
        or len(projects) > SHEET_PROJECTS
        or not all(
            isinstance(ours, str)
            and len(ours) <= 255
            and isinstance(theirs, str)
            and 0 < len(theirs.strip()) <= 255
            for ours, theirs in projects.items()
        )
    ):
        raise Refused(400, "invalid_sheet_projects")
    sheet.projects = {
        ours: theirs.strip() for ours, theirs in projects.items() if ours not in sheet.excluded
    }
    return key


@api("PUT", "DELETE", "POST")
def sheet_kept(request, kind):
    """One sheet: kept as given, removed, or written now."""
    _owner(request)
    if kind not in SHEET_KINDS:
        raise Refused(404, "no_sheet")
    found = Sheet.objects.filter(kind=kind).first()
    if request.method == "DELETE":
        if found:
            found.delete()
        return HttpResponse(status=204)
    if request.method == "POST":
        if not found:
            raise Refused(404, "no_sheet")
        return JsonResponse(sheets.write(found))
    given = body(request)
    changed = found or Sheet(kind=kind)
    key = _sheet_changed(changed, given)
    changed.error = ""
    try:
        if kind == Sheet.Kind.CLOCKIFY and (key is not None or given.get("refresh")):
            sheets.found(changed, key)
        elif key is not None:
            sheets.taskstreamer(
                changed,
                "GET",
                params={
                    "user": changed.person,
                    "date_from": changed.since.isoformat(),
                    "date_to": changed.since.isoformat(),
                },
                key=key,
            )
    except sheets.Unwritten as unwritten:
        # A TaskStreamer that does not yet take time sheets is kept, the sheet showing why it waits.
        if unwritten.code != "sheet_missing" or kind != Sheet.Kind.TASKSTREAMER:
            status = 400 if unwritten.code == "sheet_refused" else 502
            raise Refused(status, unwritten.code) from None
        changed.error = unwritten.code
    if kind == Sheet.Kind.CLOCKIFY:
        offered = {each["id"] for each in changed.offered}
        if any(theirs not in offered for theirs in changed.projects.values()):
            raise Refused(400, "invalid_sheet_projects")
    if key is not None:
        changed.key = seal(sheets.SEALED, key)
    changed.save()
    return JsonResponse(_sheet_shown(changed))


@api("GET")
def sheet_compared(request, kind):
    """A month as measured beside what the sheet holds."""
    _owner(request)
    found = Sheet.objects.filter(kind=kind).first() if kind in SHEET_KINDS else None
    if not found:
        raise Refused(404, "no_sheet")
    month = request.GET.get("month") or timezone.localdate().strftime("%Y-%m")
    if not MONTH.fullmatch(month):
        raise Refused(400, "invalid_month")
    try:
        return JsonResponse(sheets.compared(found, month))
    except sheets.Unwritten as unwritten:
        raise Refused(502, unwritten.code) from None
