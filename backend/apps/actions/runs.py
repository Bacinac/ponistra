"""Running an action on a tab, and taking a run back."""

from collections.abc import Callable
from datetime import UTC
from logging import getLogger

from django.db.models import F
from django.utils import timezone

from apps.ai import installation, model
from apps.ai.installation import Unavailable
from apps.ai.model import Prompt
from apps.collab import server
from apps.content import operations
from apps.content.operations import Change, Proposer, Refused
from apps.core.asyncdb import database
from apps.documents import tabs
from apps.documents.models import Node, Tab
from apps.users.views import describe

from .models import ActionRun, RunChange, RunItem
from .registry import Action

log = getLogger(__name__)
UNDOABLE = [ActionRun.State.DONE, ActionRun.State.STOPPED, ActionRun.State.INTERRUPTED]


def finish(run: ActionRun, state: ActionRun.State, error: str = "") -> None:
    run.state, run.error, run.finished_at = state, error, timezone.now()
    run.save(update_fields=["state", "error", "finished_at"])


def _take_back(change: RunChange) -> None:
    given = Change(bytes(change.insertions), bytes(change.deletions), change.grids)
    if change.tab is None:
        operations.undo_own(change.run.document, change.room, given)
    else:
        operations.undo(change.tab, change.room, given)


def _carry(run: ActionRun, tab: Tab, planned, propose: Proposer | None) -> list[dict]:
    """Carries out the run in the tab's room; a change that cannot be kept is taken back."""
    performed = operations.perform(tab, planned, str(run.pk), propose)
    if performed.change is not None:
        change = RunChange(run=run, tab=tab, room=tab.room, **vars(performed.change))
        try:
            change.save()
        except BaseException:
            _take_back(change)
            raise
    return performed.made


def via(run: ActionRun) -> str | None:
    """The outside agent a run was started by, where one was."""
    return run.grant.client.name if run.grant_id else None


def author_of(run: ActionRun) -> str:
    name = describe(run.user)["name"]
    return f"{agent} via {name}" if (agent := via(run)) else name


def _proposer(action: Action, run: ActionRun) -> Proposer | None:
    if action.review != "propose":
        return None
    date = run.started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    author = action.author(run.parameters) if action.author else author_of(run)
    return Proposer(author, run.user.pk, date)


def plan(action: Action, tab: Tab, user, target: dict, parameters: dict):
    """What the action plans for the tab; a plan that fails is kept as a run with why."""
    try:
        if action.reads:
            return action.plan(tab, target, parameters, user)
        return action.plan(tab, target, parameters)
    except BaseException as error:
        run = ActionRun.objects.create(
            document=tab.document, user=user, action=action.id, target=target, parameters=parameters
        )
        finish(
            run, ActionRun.State.FAILED, str(error) if isinstance(error, Refused) else repr(error)
        )
        raise


def start(
    action: Action, tab: Tab, user, target: dict, parameters: dict, planned, grant=None
) -> tuple[ActionRun, list[dict]]:
    """Carries out what the action planned for the tab, shown in its room while it runs, as one
    transaction marked with the run, and returns what its operations made; a run that fails is
    kept with why, having changed nothing."""
    run = ActionRun.objects.create(
        document=tab.document,
        user=user,
        action=action.id,
        target=target,
        parameters=parameters,
        grant=grant,
    )
    mark = str(run.pk)
    server.attend(tab.room, mark, {"action": action.id, "user": describe(user), "via": via(run)})
    try:
        made = _carry(run, tab, planned, _proposer(action, run))
    except Refused as refused:
        finish(run, ActionRun.State.FAILED, str(refused))
        raise
    except BaseException as error:
        finish(run, ActionRun.State.FAILED, repr(error))
        raise
    finally:
        server.attend(tab.room, mark, None)
    finish(run, ActionRun.State.DONE)
    return run, made


def begin(
    action: Action,
    tab: Tab,
    user,
    target: dict,
    parameters: dict,
    prompt: Prompt,
    consent: tuple[ActionRun.Consented, object],
    grant=None,
):
    """Starts the action's model on what it planned from the tab, under the consent that lets
    the text out to it and the user who gave it, and returns its run at once, the model working
    on in the background."""
    consented, by = consent
    run = ActionRun.objects.create(
        document=tab.document,
        user=user,
        action=action.id,
        target=target,
        parameters=parameters,
        model=action.model,
        consent=consented,
        consented_by=by,
        grant=grant,
    )
    into = tab
    if prompt.opens is not None:
        into = run.opened = tabs.open_copy(prompt.opens, user)
        run.save(update_fields=["opened"])
    server.launch(lambda: _think(run, action, tab, into, prompt))
    return run


def spending(run: ActionRun) -> Callable[[model.Spent], None]:
    """Adds what each of the model's answers took to the run, as it comes."""

    def spend(spent: model.Spent) -> None:
        ActionRun.objects.filter(pk=run.pk).update(
            model=spent.model,
            input_tokens=F("input_tokens") + spent.input_tokens,
            output_tokens=F("output_tokens") + spent.output_tokens,
            cache_read_tokens=F("cache_read_tokens") + spent.cache_read_tokens,
            cache_write_tokens=F("cache_write_tokens") + spent.cache_write_tokens,
            cost=None if spent.cost is None else F("cost") + spent.cost,
        )

    return spend


async def decided(run: ActionRun, name: str, prompt: Prompt) -> dict:
    """The last answer the model gives through the prompt's choice, outside any document, what it
    took added to the run, which ends done or failed with the code of what stopped it."""
    answers: list[dict] = []
    spent: list[model.Spent] = []
    try:
        await database(installation.allowed)(run.user_id)
        # A model takes its time, which would hold the thread every request shares.
        await database(model.converse, own_thread=True)(
            name, prompt, answers.append, lambda: False, spent.append
        )
        if not answers:
            raise model.Failed("no_answer")
    except (model.Failed, Unavailable) as failed:
        await database(_decided)(run, spent, ActionRun.State.FAILED, failed.code)
        raise
    await database(_decided)(run, spent, ActionRun.State.DONE)
    return answers[-1]


def _decided(
    run: ActionRun, spent: list[model.Spent], state: ActionRun.State, error: str = ""
) -> None:
    spend = spending(run)
    for each in spent:
        spend(each)
    ActionRun.objects.filter(pk=run.pk).update(state=state, error=error, finished_at=timezone.now())


def _think(run: ActionRun, action: Action, tab: Tab, into: Tab, prompt: Prompt) -> None:
    """Lets the model carry out the run from the tab, in the tab it opened or in its own, each
    of its calls one transaction marked with the run; a run that fails takes back what it
    wrote."""
    mark, propose = str(run.pk), _proposer(action, run)
    kept: list[RunChange] = []
    prior: list[RunChange] = []
    called: list[str] = []
    offered: dict = {}

    def call(operation: dict) -> list[dict]:
        if isinstance(prompt.tools.get(operation["op"]), model.Choice):
            offered.update(operation)
            return []
        called.append(operation["op"])
        if operation["op"] in operations.OWN_OPERATIONS:
            if change := operations.perform_own(into.document, [operation], mark):
                kept.append(
                    RunChange.objects.create(run=run, room=into.document.room, **vars(change))
                )
            return []
        performed = operations.perform(into, [operation], mark, propose)
        if performed.change is not None:
            kept.append(
                RunChange.objects.create(
                    run=run, tab=into, room=into.room, **vars(performed.change)
                )
            )
        return performed.made

    def stopping() -> bool:
        return ActionRun.objects.filter(pk=run.pk, state=ActionRun.State.STOPPING).exists()

    presence = {
        "action": action.id,
        "user": describe(run.user),
        "model": action.model,
        "via": via(run),
    }
    shown = list(dict.fromkeys([tab.room, into.room]))
    for room in shown:
        server.attend(room, mark, presence)
    try:
        installation.allowed(run.user_id)
        if prompt.before:
            performed = operations.perform(tab, prompt.before, mark)
            if performed.change is not None:
                prior.append(
                    RunChange.objects.create(
                        run=run, tab=tab, room=tab.room, **vars(performed.change)
                    )
                )
        said = model.converse(action.model, prompt, call, stopping, spending(run))
        if prompt.replies:
            run.reply = offered.get("question") or said
        run.offers, run.calls = offered.get("options", []), called
        run.save(update_fields=["reply", "offers", "calls"])
        finish(run, ActionRun.State.STOPPED if stopping() else ActionRun.State.DONE)
    except (model.Failed, Unavailable) as failed:
        log.warning("run %s failed: %s", run.pk, failed)
        _failed(run, prior, kept, failed.code)
    except Refused as refused:
        _failed(run, prior, kept, str(refused))
    except Exception as error:
        log.exception("run %s failed", run.pk)
        _failed(run, prior, kept, repr(error))
    finally:
        for room in shown:
            server.attend(room, mark, None)


def _failed(run: ActionRun, prior: list[RunChange], kept: list[RunChange], error: str) -> None:
    """Takes back what the run wrote: the tab it opened closed, and what it changed before the
    model began and since."""
    if run.opened is not None:
        tabs.close(run.opened)
        run.opened = None
        kept = []
    taken = [*prior, *kept]
    for change in reversed(taken):
        _take_back(change)
    RunChange.objects.filter(pk__in=[change.pk for change in taken]).delete()
    finish(run, ActionRun.State.FAILED, error)


def stop(run: ActionRun) -> None:
    """Asks the run's model to stop after the call it is on; what it wrote so far stays."""
    claimed = ActionRun.objects.filter(pk=run.pk, state=ActionRun.State.RUNNING).update(
        state=ActionRun.State.STOPPING
    )
    if not claimed:
        raise Refused("not_running", str(run.pk))
    run.refresh_from_db()


def interrupted() -> None:
    """Marks the runs the server's last stop cut off: what they wrote stays, for Undo. A run
    that goes through items carries on from its queue, the item it was on waiting again."""
    ActionRun.objects.filter(
        state__in=[ActionRun.State.RUNNING, ActionRun.State.STOPPING], items=None
    ).update(state=ActionRun.State.INTERRUPTED, finished_at=timezone.now())
    RunItem.objects.filter(state=RunItem.State.WAITING).exclude(started_at=None).update(
        started_at=None
    )


def discard(run: ActionRun) -> None:
    """Puts the document the run made in the trash."""
    Node.objects.filter(pk=run.document_id).update(trashed_at=timezone.now())
    server.revoke()


def undo(run: ActionRun, user) -> None:
    """Takes back what the run changed, leaving what others wrote since, and closes the tab it
    opened; a run over several documents puts the document it made in the trash. A run is
    taken back once."""
    claimed = ActionRun.objects.filter(pk=run.pk, state__in=UNDOABLE).update(
        state=ActionRun.State.UNDONE, undone_by=user, undone_at=timezone.now()
    )
    if not claimed:
        raise Refused("not_done", str(run.pk))
    try:
        if run.items.exists():
            discard(run)
        else:
            if run.opened is not None:
                tabs.close(run.opened, user)
            for change in run.changes.select_related("run__document", "tab").order_by("-pk"):
                _take_back(change)
    except BaseException:
        ActionRun.objects.filter(pk=run.pk).update(state=run.state, undone_by=None, undone_at=None)
        raise
    run.refresh_from_db()
