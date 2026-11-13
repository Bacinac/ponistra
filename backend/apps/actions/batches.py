"""Runs over several documents (A5): each document or PDF file an item of a queue in Postgres,
or each page of the PDF file a run translates (D35-3), which the backend goes through in its own
process, where the rooms the run writes into live; after a restart it carries on from the
queue. What the run gathers or translates goes into the document it made for it, once the items
are through or it is stopped."""

from logging import getLogger

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.ai import installation, model
from apps.ai.installation import Unavailable
from apps.blobs import store
from apps.collab import server
from apps.content import operations
from apps.content.operations import Refused
from apps.core.asyncdb import database, drain, notify
from apps.documents.models import Node, Tab
from apps.documents.views import BY_TITLE, created
from apps.users.views import describe

from . import gathering, runs, translation
from .models import ActionRun, RunChange, RunItem
from .registry import ACTIONS, Action

log = getLogger(__name__)

CHANNEL = "actions_batches"
ITEMS = 200
# A model's failure on one document, which leaves the others to go on; any other ends the run.
PASSED = {"refused", "too_long", "too_many_steps"}


def wake() -> None:
    notify(CHANNEL)


def items_of(nodes: list[Node]) -> list[Node]:
    """The documents and PDF files the nodes are, and those directly in the folders among them,
    each once, in the order the folder lists them."""
    found: dict = {}
    for node in nodes:
        if node.kind == Node.Kind.DOCUMENT or node.is_pdf:
            found.setdefault(node.pk, node)
        if node.kind != Node.Kind.FOLDER:
            continue
        inside = Node.objects.filter(parent=node, trashed_at=None).filter(
            Q(kind=Node.Kind.DOCUMENT) | Q(kind=Node.Kind.FILE, blob__media_type=store.PDF)
        )
        for child in inside.order_by(BY_TITLE):
            found.setdefault(child.pk, child)
    return list(found.values())


def start(
    action: Action, user, nodes: list[Node], parent: Node | None, title: str, parameters: dict
) -> ActionRun:
    """Queues the run of the action over the nodes, or the pages of the file it translates, into
    a document it makes in the folder, in the language it translates into."""
    translating = action.id == translation.ACTION
    if translating:
        items = [(nodes[0], number, str(number)) for number in translation.pages(nodes[0])]
    else:
        items = [(node, at, node.title) for at, node in enumerate(items_of(nodes))]
    if not items:
        raise Refused("empty")
    if len(items) > ITEMS:
        raise Refused("too_many_pages" if translating else "too_many", str(len(items)))
    with transaction.atomic():
        made = created(parent, Node.Kind.DOCUMENT, title, None, user)
        if language := parameters.get("language"):
            made.locale = language
            made.save(update_fields=["locale"])
        run = ActionRun.objects.create(
            document=made,
            user=user,
            action=action.id,
            target={"nodes": [str(node.pk) for node in nodes]},
            parameters=parameters,
            model=action.model,
            consent=ActionRun.Consented.ONCE,
            consented_by=user,
        )
        RunItem.objects.bulk_create(
            RunItem(run=run, node=node, position=at, title=title) for node, at, title in items
        )
        wake()
    _attend(run)
    return run


def _tab(run: ActionRun) -> Tab:
    return run.document.tabs_in_order()[0]


def _attend(run: ActionRun, ended: bool = False) -> None:
    counted = run.items.exclude(state=RunItem.State.WAITING).count()
    presence = {
        "action": run.action,
        "user": describe(run.user),
        "model": run.model,
        "through": counted,
        "of": run.items.count(),
    }
    server.attend(_tab(run).room, str(run.pk), None if ended else presence)


def claim() -> RunItem | None:
    """The next item waiting, first of its run's while the model has the columns to choose."""
    earlier = RunItem.objects.filter(
        run=OuterRef("run"), state=RunItem.State.WAITING, position__lt=OuterRef("position")
    )
    with transaction.atomic():
        found = (
            RunItem.objects.filter(
                state=RunItem.State.WAITING, started_at=None, run__state=ActionRun.State.RUNNING
            )
            .filter(Q(run__parameters__has_key="columns") | ~Exists(earlier))
            .order_by("run__started_at", "position")
            .select_for_update(no_key=True, skip_locked=True, of=("self",))
            .first()
        )
        if found is not None:
            found.started_at = timezone.now()
            found.save(update_fields=["started_at"])
        return found


def _settle(item: RunItem, state: RunItem.State, error: str = "", found=None) -> None:
    RunItem.objects.filter(pk=item.pk, state=RunItem.State.WAITING).update(
        state=state, error=error, found=found or [], finished_at=timezone.now()
    )


def _stopping(run: ActionRun) -> bool:
    return ActionRun.objects.filter(pk=run.pk, state=ActionRun.State.STOPPING).exists()


def gather(item: RunItem) -> None:
    """Has the model find the item's row, or translate its page; a document it cannot read is
    missed with why, and a failure of the model itself leaves the run's other items missed with
    it."""
    run = ActionRun.objects.select_related("document", "user").get(pk=item.run_id)
    action = ACTIONS[run.action]
    translating = action.id == translation.ACTION
    columns = run.parameters.get("columns", [])
    _attend(run)
    try:
        if translating:
            text, before = translation.page_in(item.node, item.position, run.user)
            prompt = action.plan(text, before, run.parameters["language"])
        else:
            content = gathering.text_in(item.node, run.user)
            prompt = action.plan(content, columns, run.document.locale)
    except Refused as refused:
        _settle(item, RunItem.State.SKIPPED, refused.code)
        return
    answers: list[dict] = []
    try:
        installation.allowed(run.user_id)
        model.converse(
            action.model, prompt, answers.append, lambda: _stopping(run), runs.spending(run)
        )
    except model.Failed as failed:
        log.warning("run %s item %s failed: %s", run.pk, item.position, failed)
        if failed.code in PASSED:
            _settle(item, RunItem.State.FAILED, failed.code)
        else:
            _missed(run, failed.code)
        return
    except Unavailable as unavailable:
        _missed(run, unavailable.code)
        return
    if not answers:
        if _stopping(run):
            RunItem.objects.filter(pk=item.pk).update(started_at=None)
        else:
            _settle(item, RunItem.State.FAILED, "no_answer")
        return
    if translating:
        _settle(item, RunItem.State.DONE, found=answers[-1])
        return
    chosen, row = gathering.row_of(answers[-1], columns)
    if not columns:
        run.parameters = {**run.parameters, "columns": chosen}
        run.save(update_fields=["parameters"])
    _settle(item, RunItem.State.DONE, found=row)


def _missed(run: ActionRun, error: str) -> None:
    RunItem.objects.filter(run=run, state=RunItem.State.WAITING).update(
        state=RunItem.State.SKIPPED, error=error, finished_at=timezone.now()
    )


def finishable() -> ActionRun | None:
    """A run whose items are through, or that was asked to stop."""
    waiting = RunItem.objects.filter(run=OuterRef("pk"), state=RunItem.State.WAITING)
    return (
        ActionRun.objects.filter(Exists(RunItem.objects.filter(run=OuterRef("pk"))))
        .annotate(pending=Exists(waiting))
        .filter(Q(state=ActionRun.State.STOPPING) | Q(state=ActionRun.State.RUNNING, pending=False))
        .select_related("document", "user")
        .order_by("started_at")
        .first()
    )


def complete(run: ActionRun) -> None:
    """Writes the rows found into the run's document as one table, or the pages translated,
    marked with the run; with none, the run fails with why the first item was missed, and a run
    that fails puts its empty document in the trash."""
    stopped = run.state == ActionRun.State.STOPPING
    _missed(run, "stopped")
    tab = _tab(run)
    try:
        done = list(
            run.items.filter(state=RunItem.State.DONE).select_related("node").order_by("position")
        )
        if not done:
            first = run.items.order_by("position").first()
            _failed(run, first.error or "empty")
            return
        if run.action == translation.ACTION:
            planned = translation.written([item.found for item in done])
        else:
            rows = [(item.node, item.title, item.found) for item in done]
            planned = [gathering.table(rows, run.parameters["columns"], run.document.locale)]
        if not planned:
            _failed(run, "empty")
            return
        performed = operations.perform(tab, planned, str(run.pk), None)
        if performed.change is not None:
            RunChange.objects.create(run=run, tab=tab, room=tab.room, **vars(performed.change))
        runs.finish(run, ActionRun.State.STOPPED if stopped else ActionRun.State.DONE)
    except Refused as refused:
        _failed(run, str(refused))
    except Exception as error:
        log.exception("run %s failed", run.pk)
        _failed(run, repr(error))
    finally:
        _attend(run, ended=True)


def _failed(run: ActionRun, error: str) -> None:
    runs.finish(run, ActionRun.State.FAILED, error)
    runs.discard(run)


def step() -> bool:
    """Finishes a run that is through, else gathers the next item; False when neither waits."""
    if (run := finishable()) is not None:
        complete(run)
        return True
    item = claim()
    if item is None:
        return False
    try:
        gather(item)
    except Exception as error:
        log.exception("run %s item %s failed", item.run_id, item.position)
        _settle(item, RunItem.State.FAILED, repr(error))
    return True


async def batches() -> None:
    """Goes through the queued items while the server runs: as soon as one is queued, and in a
    sweep every SEARCH_SWEEP for whatever a lost notification or a restart left."""
    await drain(CHANNEL, database(step, own_thread=True), settings.SEARCH_SWEEP, log)
