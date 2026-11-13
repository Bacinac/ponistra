from datetime import datetime

from django.db.models import Count, Func, Max, Q, Sum, TextField, Value
from django.db.models.fields.json import KT
from django.db.models.functions import Lower, Trim, TruncMonth
from django.http import JsonResponse
from django.utils import timezone

from apps.access.models import Role
from apps.ai import installation
from apps.ai.model import Prompt
from apps.ai.models import Consent
from apps.content.operations import Refused
from apps.core import api as core
from apps.core.api import api, body
from apps.documents.views import (
    beside,
    kept_in,
    live_document,
    live_nodes,
    live_tab,
    title_of,
    trashed,
)
from apps.documents.views import describe as describe_node
from apps.users.accounts import administrator

from . import agent, batches, runs, translation
from .models import ActionRun, RunItem
from .registry import ACTIONS, TAB_TARGETS, invalid

MONTHS = 12
REQUESTS = 100


def described(run: ActionRun) -> dict:
    return {
        "id": str(run.pk),
        "action": run.action,
        "model": run.model or None,
        "target": run.target,
        "state": run.state,
        "error": run.error,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "reply": run.reply,
        "offers": run.offers,
        "via": runs.via(run),
        "changed": run.opened_id is not None or run.changes.exists(),
        "items": _items(run) if run.target.get("nodes") else None,
    }


def _items(run: ActionRun) -> dict:
    """How far a run over several documents is through them, and those it missed, with why."""
    missed = run.items.filter(state__in=[RunItem.State.FAILED, RunItem.State.SKIPPED]).exclude(
        error="stopped"
    )
    return {
        "of": run.items.count(),
        "through": run.items.exclude(state=RunItem.State.WAITING).count(),
        "missed": list(missed.order_by("position").values("title", "error")),
    }


def refusal(refused: Refused) -> JsonResponse:
    return JsonResponse(
        {"error": refused.code, "detail": refused.detail, "operation": refused.operation},
        status=422,
    )


@api("GET", visitors=True)
def actions(request):
    """The actions the user runs on a tab; someone outside the installation runs none."""
    if request.user.visitor:
        return JsonResponse({"actions": [], "ai": False})
    return JsonResponse(
        {
            "actions": [action.listed() for action in ACTIONS.values()],
            "ai": installation.enabled(),
        }
    )


def _consented(tab, given: object, user) -> tuple[ActionRun.Consented, object]:
    if given == "once":
        return ActionRun.Consented.ONCE, user
    standing = Consent.objects.select_related("given_by").filter(document=tab.document_id).first()
    if standing is None:
        raise core.Refused(428, "consent_needed")
    return ActionRun.Consented.DOCUMENT, standing.given_by


def _conversation(request, tab) -> JsonResponse:
    """The user's conversation with the agent on the tab's document that `thread` names, or
    their latest, turn by turn."""
    mine = ActionRun.objects.filter(
        document=tab.document_id, user=request.user, action="text.ask", parameters__has_key="thread"
    )
    thread = request.GET.get("thread")
    if thread is None:
        latest = mine.order_by("-started_at").first()
        thread = latest.parameters["thread"] if latest else None
    turns = (
        mine.filter(parameters__thread=thread).order_by("-started_at")[: agent.TURNS]
        if thread
        else []
    )
    return JsonResponse(
        {
            "thread": thread,
            "turns": [
                {**described(run), "request": run.parameters["request"]} for run in reversed(turns)
            ],
        }
    )


@api("GET", "POST")
def tab_runs(request, pk):
    """The user's conversation with the agent on the tab's document; or the action run on the
    tab: code at once, a model in the background once the installation's AI is on and the
    document lets the text out, this once or always."""
    if request.method == "GET":
        return _conversation(request, live_tab(request.user, pk, Role.EDIT))
    tab = live_tab(request.user, pk, Role.EDIT)
    data = body(request)
    action = ACTIONS.get(data.get("action"))
    if action is None or action.target not in TAB_TARGETS:
        raise core.Refused(404, "unknown_action")
    target, parameters = data.get("target"), data.get("parameters", {})
    if why := invalid(action, target, parameters):
        raise core.Refused(400, why)
    consent = data.get("consent")
    if consent not in (None, "once"):
        raise core.Refused(400, "invalid_consent")
    if action.model is not None and not installation.enabled():
        raise core.Refused(409, "ai_off")
    try:
        planned = runs.plan(action, tab, request.user, target, parameters)
        if isinstance(planned, Prompt):
            consented = _consented(tab, consent, request.user)
            run = runs.begin(action, tab, request.user, target, parameters, planned, consented)
            return JsonResponse({"run": described(run)}, status=202)
        run, made = runs.start(action, tab, request.user, target, parameters, planned)
    except Refused as refused:
        return refusal(refused)
    return JsonResponse({"run": described(run), "made": made}, status=201)


@api("POST")
def node_runs(request):
    """Runs the action over documents and PDF files, and those directly in the folders among
    them, or over the pages of the one PDF file it translates, with its model in the background,
    this once: what it finds in them goes into a new document beside them, or at the top of the
    user's documents where they are not in one folder."""
    data = body(request)
    action = ACTIONS.get(data.get("action"))
    if action is None or action.target != "nodes":
        raise core.Refused(404, "unknown_action")
    target, parameters = data.get("target"), data.get("parameters", {})
    if why := invalid(action, target, parameters):
        raise core.Refused(400, why)
    if data.get("consent") != "once":
        raise core.Refused(428, "consent_needed")
    if not installation.enabled():
        raise core.Refused(409, "ai_off")
    nodes = [node for node, _ in live_nodes(request.user, target, Role.READ)]
    if action.id != translation.ACTION:
        title = title_of(parameters)
    elif len(nodes) == 1 and nodes[0].is_pdf:
        title = translation.title_of(nodes[0], parameters["language"])
    else:
        raise core.Refused(400, "not_a_pdf")
    together = len({node.parent_id for node in nodes}) == 1
    try:
        run = batches.start(
            action,
            request.user,
            nodes,
            kept_in(request.user, nodes, beside(request.user, nodes[0]) if together else None),
            title,
            parameters,
        )
    except Refused as refused:
        return refusal(refused)
    return JsonResponse(
        {"run": described(run), "document": describe_node(run.document)}, status=202
    )


def _run(request, pk, needs: Role) -> ActionRun:
    """The run, read where its document is, or in the trash a failed run over documents put
    it in; stopped or taken back only where the document is live."""
    run = ActionRun.objects.select_related("document").filter(pk=pk, document__isnull=False).first()
    if run is None:
        raise core.Refused(404, "not_found")
    if needs == Role.READ and run.document.trashed_at is not None:
        trashed(request.user, run.document_id, needs)
    else:
        live_document(request.user, run.document_id, needs)
    return run


@api("GET")
def run(request, pk):
    return JsonResponse({"run": described(_run(request, pk, Role.READ))})


@api("POST")
def stop(request, pk):
    found = _run(request, pk, Role.EDIT)
    if (action := ACTIONS.get(found.action)) is None or action.model is None:
        raise core.Refused(409, "not_stoppable")
    try:
        runs.stop(found)
    except Refused as refused:
        return refusal(refused)
    return JsonResponse({"run": described(found)})


@api("POST")
def undo(request, pk):
    run = _run(request, pk, Role.EDIT)
    try:
        runs.undo(run, request.user)
    except Refused as refused:
        return refusal(refused)
    return JsonResponse({"run": described(run)})


def _since() -> datetime:
    now = timezone.localtime()
    year, month = divmod(now.year * 12 + now.month - MONTHS, 12)
    return now.replace(year=year, month=month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


@api("GET")
def usage(request):
    """What the installation's models took in the last twelve months, by month and action, and
    the free requests asked of them, grouped by their words, each with how often and when last;
    neither names a user or a document."""
    administrator(request)
    since = _since()
    spent = (
        ActionRun.objects.exclude(model="")
        .filter(started_at__gte=since)
        .annotate(month=TruncMonth("started_at"))
        .values("month", "action")
        .annotate(
            runs=Count("pk"),
            read=Sum("input_tokens"),
            wrote=Sum("output_tokens"),
            cached=Sum("cache_read_tokens"),
            cache_written=Sum("cache_write_tokens"),
            dollars=Sum("cost"),
            unpriced=Count("pk", filter=Q(cost__isnull=True)),
        )
        .order_by("-month", "action")
    )
    words = Lower(
        Trim(
            Func(
                KT("parameters__request"),
                Value(r"\s+"),
                Value(" "),
                Value("g"),
                function="regexp_replace",
                output_field=TextField(),
            )
        )
    )
    asked = (
        ActionRun.objects.filter(action="text.ask", started_at__gte=since)
        .annotate(words=words)
        .values("words")
        .annotate(text=Max(KT("parameters__request")), times=Count("pk"), last=Max("started_at"))
        .order_by("-times", "-last")[:REQUESTS]
    )
    return JsonResponse(
        {
            "spent": [
                {
                    "month": row["month"].strftime("%Y-%m"),
                    "action": row["action"],
                    "runs": row["runs"],
                    "input_tokens": row["read"],
                    "output_tokens": row["wrote"],
                    "cache_read_tokens": row["cached"],
                    "cache_write_tokens": row["cache_written"],
                    "cost": None if row["dollars"] is None else float(row["dollars"]),
                    "unpriced": row["unpriced"],
                }
                for row in spent
            ],
            "requests": [
                {"text": row["text"], "times": row["times"], "last": row["last"]} for row in asked
            ],
        }
    )
