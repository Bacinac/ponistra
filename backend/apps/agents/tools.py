"""What an outside agent can do in PONISTRA (D18), each tool acting as the user whose grant the
bearer token names: reading what they read, writing into documents as proposals, running the
registry's actions as runs of their own, drafting and sorting mail, theirs and that of the
shared mailboxes they reach, and keeping their calendar, tasks and contacts. Nothing here
deletes."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from email.utils import parseaddr
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError

from apps.access import rights
from apps.access.models import Role
from apps.actions import runs
from apps.actions.models import ActionRun
from apps.actions.registry import ACTIONS, TAB_TARGETS, TARGETS, Action, invalid
from apps.actions.views import described
from apps.ai import installation
from apps.ai.model import Prompt
from apps.ai.reading import text_of
from apps.blobs import text
from apps.calendar.models import Calendar
from apps.calendar.views import LONGEST, created_event, describe_calendar, occurrences_of, zone_of
from apps.collab import server as rooms
from apps.contacts import search as contacts
from apps.contacts.views import summary
from apps.content import blocks, schema
from apps.content.operations import OPERATIONS
from apps.content.operations import Refused as OperationRefused
from apps.core.api import Refused, optional_id
from apps.core.asyncdb import database
from apps.documents import board_data, boards, boards_place, launcher, links
from apps.documents.models import Node
from apps.documents.printing import compact
from apps.documents.views import (
    created,
    describe,
    describe_tab,
    extension_of,
    folder,
    live,
    live_document,
    live_tab,
    title_of,
)
from apps.help import library
from apps.mail import acting, reactions, sharing
from apps.mail.models import Account, Draft, Message
from apps.mail.models import Role as FolderRole
from apps.mail.sending import WAYS
from apps.mail.views import (
    agent_mail,
    describe_draft,
    describe_files,
    describe_message,
    described_unsent,
    listing,
    loaded,
    quoted_text,
)
from apps.memory import ledger as memory
from apps.search import extraction
from apps.search.agenda import found_events, found_tasks
from apps.search.models import PdfOcr
from apps.search.people import found_people
from apps.search.query import asked
from apps.search.versions import found_versions
from apps.search.views import found_documents, found_mail
from apps.tasks.models import Task
from apps.tasks.views import describe as describe_task
from apps.tasks.views import filled
from apps.tasks.views import listed as listed_tasks
from apps.users.views import describe as describe_user

from .models import Grant
from .server import server

MOST = 50
# How much of a file's text one reading carries.
PAGE_TEXT = 200_000
EDIT = Action(
    "agent.edit",
    "document",
    lambda tab, target, parameters: parameters["operations"],
    review="propose",
)
# The registry's actions an agent runs: those on a tab, not the review of proposals, which is
# the user's, nor the gathering over several documents.
REVIEWING = {"proposal.accept", "proposal.reject", "document.accept", "document.reject"}
RUNNABLE = {
    action.id: action
    for action in ACTIONS.values()
    if action.target in TAB_TARGETS and action.id not in REVIEWING
}
# What an agent does to mail, in the words its tools tell it. Not deleting it for good, as
# nothing here deletes, nor triage: the agent is a model itself, and letting mail out to the
# installation's is the user's consent to give.
MAIL_DOES = {
    "mail.seen": "Marks the messages read.",
    "mail.unseen": "Marks the messages unread.",
    "mail.flagged": "Flags the messages.",
    "mail.unflagged": "Takes the flag off the messages.",
    "mail.move": (
        "Moves the messages to the folder `to`: one of the mailbox's by its id, or the folder of"
        ' a role ("inbox", "archive", "junk", "trash"...), made where there is none yet.'
        " Taken out of Junk into the inbox, their senders are blocked no more."
    ),
    "mail.snooze": (
        "Puts the messages away until `at`, a moment ahead in ISO 8601 with its offset, when they"
        " come back to the inbox."
    ),
    "mail.unsnooze": "Brings snoozed messages back to the inbox now.",
    "mail.await": (
        "Waits for an answer to messages the user sent until `at`, a moment ahead in ISO 8601"
        " with its offset, and reminds them then if none came."
    ),
    "mail.unawait": "Stops waiting for an answer to the messages.",
    "mail.block": (
        "Sends the mail of the messages' senders to Junk from now on, each sender by `by`: its"
        ' "address" or the "domain" it writes from; what of it is here already goes too.'
    ),
    "mail.always": (
        "Sends the mail of the messages' senders to the folder `to` from now on (as mail_move"
        ' names it), each sender by `by`: its "address" or the "domain" it writes from;'
        " what of it is here already goes too."
    ),
}


async def _signed() -> Grant:
    token = get_access_token()
    if token is None:
        raise ToolError("not signed in")
    found = await database(
        Grant.objects.select_related("user", "client").filter(pk=token.claims["grant"]).first
    )()
    if found is None or found.revoked_at or not found.user.is_active:
        raise ToolError("access revoked")
    return found


async def call[R](fn: Callable[..., R], *args) -> R:
    """The work on a worker thread, a refusal as the tool's error for the agent to read."""
    try:
        return await database(fn)(*args)
    except Refused as refused:
        raise ToolError(refused.error) from None
    except OperationRefused as refused:
        raise ToolError(f"{refused.code}: {refused.detail}") from None


def _id(given: str):
    try:
        return optional_id(given)
    except Refused:
        raise ToolError("invalid id") from None


def _listed(chains: list[list[Node]]) -> list[dict]:
    return [
        {"id": str(node.pk), "kind": node.kind, "title": node.title, "updated_at": node.updated_at}
        for node in (chain[-1] for chain in chains)
    ]


def _folder(user, given: str | None, root: str) -> dict[str, Any]:
    if given is None:
        if root == "shared":
            return {"folder": None, "children": _listed(rights.shared_with(user))}
        if root == "company":
            return {"folder": None, "children": _listed([[n] for n in rights.company(user)])}
        return {"folder": None, "children": _listed([[n] for n in rights.mine(user)])}
    parent, reach = folder(user, _id(given))
    children = Node.objects.filter(parent=parent, trashed_at=None).order_by("kind", "title")
    return {
        "folder": describe(parent),
        "children": _listed([[*reach.ancestry, c] for c in children]),
    }


def _hit(each: dict) -> dict[str, Any]:
    return {
        "id": str(each["id"]),
        "kind": each["kind"],
        "title": each["title"],
        "source": each["source"],
        "tab": each["tab"],
        "page": each["page"],
        "block": each["block"],
        "snippet": each["snippet"],
    }


def _mail_hit(each: dict) -> dict[str, Any]:
    return {
        "id": each["id"],
        "subject": each["subject"],
        "sender": each["sender"],
        "date": each["date"],
        "attachment": each["attachment"],
        "snippet": each["snippet"],
        "mailbox": each["box"] and each["box"]["id"],
    }


def _search(user, query: str, within: str | None, limit: int) -> dict[str, Any]:
    wanted = asked(query)
    if wanted.invalid or len(wanted.text) < 2 and not wanted.narrowed:
        raise ToolError("the query needs at least two letters or a filter")
    place, _ = folder(user, _id(within) if within else None)
    documents = found_documents(user, wanted, place, limit) if wanted.documents else []
    versions = found_versions(user, wanted, place, limit) if wanted.versions else []
    beyond = place is None
    mail = found_mail(user, wanted, limit) if wanted.mail and beyond else []
    events = (
        found_events(user, wanted, settings.TIME_ZONE, limit) if wanted.events and beyond else []
    )
    tasks = found_tasks(user, wanted, limit) if wanted.tasks and beyond else []
    people = found_people(user, wanted, limit) if wanted.people and beyond else []
    return {
        "filters": wanted.filters,
        "documents": [_hit(each) for each in documents],
        "mail": [_mail_hit(each) for each in mail],
        "events": [_event_hit(each) for each in events],
        "tasks": [_task_hit(each) for each in tasks],
        "people": [_person_hit(each) for each in people],
        "versions": [_version_hit(each) for each in versions],
    }


def _version_hit(each: dict) -> dict[str, Any]:
    return {
        "id": str(each["id"]),
        "number": each["number"],
        "title": each["title"],
        "created_at": each["created_at"],
        "document": each["document"]["id"],
        "document_title": each["document"]["title"],
        "tab": each["tab"] and str(each["tab"]["id"]),
        "hits": each["hits"],
        "snippet": each["snippet"],
    }


def _event_hit(each: dict) -> dict[str, Any]:
    return {
        "id": each["id"],
        "calendar": each["calendar"]["id"],
        "summary": each["summary"],
        "start": each["start"],
        "end": each["end"],
        "all_day": each["all_day"],
        "location": each["location"],
        "recurring": each["recurring"],
        "snippet": each["snippet"],
    }


def _task_hit(each: dict) -> dict[str, Any]:
    return {"id": each["id"], "text": each["text"], "due": each["due"], "done": each["done"]}


def _person_hit(each: dict) -> dict[str, Any]:
    return {
        "kind": each["kind"],
        "id": each["id"],
        "name": each["name"],
        "organisation": each["organisation"],
        "title": each["title"],
        "email": each["email"],
        "phone": each["phone"],
    }


def _file_text(blob) -> dict[str, Any]:
    """A file's text by its pages, and what keeps a reading from being all of it: `unread` where
    there is no text to give, `cut` where it runs past what one reading carries, `ocr` where the
    pages without text are not read yet or could not be."""
    extracted = getattr(blob, "text", None)
    if extracted is None:
        waiting = extraction.waiting().filter(pk=blob.pk).exists()
        return {"pages": [], "unread": "waiting" if waiting else "not_text"}
    if extracted.failed:
        return {"pages": [], "unread": "failed"}
    pages = []
    left = PAGE_TEXT
    cut = False
    for page in extracted.pages.order_by("number"):
        if left <= 0:
            cut = True
            break
        pages.append({"page": page.number, "text": page.text[:left]})
        left -= len(page.text)
    shown: dict[str, Any] = {"pages": pages, "page_count": extracted.page_count}
    if cut or left < 0:
        shown["cut"] = True
    reading = getattr(blob, "ocr", None)
    if reading is not None and reading.state != PdfOcr.State.DONE:
        shown["ocr"] = reading.state
    return shown


def _document(user, given: str) -> dict[str, Any]:
    node, _ = live(user, _id(given))
    shown = {"id": str(node.pk), "kind": node.kind, "title": node.title, "locale": node.locale}
    if node.kind == Node.Kind.FOLDER:
        return shown | _folder(user, given, "mine")
    if node.kind == Node.Kind.LINK:
        return shown | {"href": node.href, "description": node.description}
    if node.kind == Node.Kind.FILE:
        shown["media_type"] = node.blob.media_type
        shown["extension"] = extension_of(node)
        if boards.is_board(node):
            found = text.read(node.blob, boards.MOST)
            return shown | {"board": True, "html": found.text}
        return shown | _file_text(node.blob)
    tabs = node.tabs.order_by("position")
    return shown | {"tabs": [describe_tab(tab) | {"id": str(tab.pk)} for tab in tabs]}


def _tab(user, given: str) -> dict[str, Any]:
    tab = live_tab(user, _id(given), Role.READ)

    def reading(doc, held):
        whole = held.grids(cut=True)
        return blocks.read(doc, whole), whole.parted

    found, parted = rooms.read_grids(tab.room, reading, settled=True)
    return {
        "id": str(tab.pk),
        "title": tab.title,
        "document": str(tab.document_id),
        "text": text_of(found),
        **({"only_first_rows_of": parted} if parted else {}),
    }


def _created_document(user, title: str, within: str | None) -> dict[str, Any]:
    parent, _ = folder(user, _id(within) if within else None, Role.EDIT)
    node = created(parent, Node.Kind.DOCUMENT, title_of({"title": title}), None, user)
    return {"id": str(node.pk), "title": node.title, "tab": str(node.tabs.get().pk)}


def _board_said(node: Node) -> dict[str, Any]:
    return {
        "id": str(node.pk),
        "title": node.title,
        "group": node.parent.title if node.parent else None,
        "version": node.file_versions.aggregate(last=Max("number"))["last"],
        "url": f"{settings.PUBLIC_URL}/p/{compact(node.pk)}",
    }


def _board(grant: Grant, html: str, title: str | None, group: str | None, given: str | None):
    user, agent = grant.user, str(grant.client)
    named = title_of({"title": title}) if title else None
    grouped = title_of({"title": group}) if group else None
    if given:
        node, reach = live(user, _id(given), Role.EDIT)
        if grouped:
            boards_place.filed(user, node, reach, grouped)
        node = boards.rewritten(node, html, user, agent, named)
    else:
        if named is None:
            raise ToolError("a new board needs a title")
        if grouped is None:
            raise ToolError("a new board needs a group")
        blob = boards.page(html)
        with transaction.atomic():
            into = boards_place.group_of(user, grouped)
            node = created(into, Node.Kind.FILE, named, blob, user, "html")
            boards.begun(node, user, agent)
        extraction.wake()
    return _board_said(node)


def _board_moved(user, given: str, group: str) -> dict[str, Any]:
    node, reach = live(user, _id(given), Role.EDIT)
    boards_place.filed(user, node, reach, title_of({"title": group}))
    return _board_said(node)


def _kept_board(user, given: str, needs: Role) -> Node:
    node, _ = live(user, _id(given), needs)
    if not boards.is_board(node):
        raise Refused(400, "not_a_board")
    return node


def _board_read(
    user,
    given: str,
    collection: str | None,
    key: str | None,
    where: dict[str, Any] | None,
    limit: int,
    after: str | None,
) -> dict[str, Any]:
    node = _kept_board(user, given, Role.READ)
    if collection is None:
        return {"collections": board_data.collections(node)}
    if key is not None:
        return board_data.described(board_data.entry(node, collection, key))
    found = board_data.entries(node, collection, where, limit + 1, after)
    shown = found[:limit]
    return {
        "entries": [board_data.described(each) for each in shown],
        "next": shown[-1].key if len(found) > limit else None,
    }


def _board_written(grant: Grant, given: str, writes: list[dict[str, Any]]) -> dict[str, Any]:
    node = _kept_board(grant.user, given, Role.EDIT)
    done = board_data.written(node, writes, grant.user, str(grant.client))
    return {
        "written": [
            {"collection": each["collection"], "key": each["key"], "version": each["version"]}
            for each in done
        ]
    }


def _link(user, url: str, title: str | None, group: str | None) -> dict[str, Any]:
    address = links.address_of({"href": url})
    named = title_of({"title": title or ""}, required=False)
    node, fresh = launcher.added(
        user, address, named, title_of({"title": group}) if group else None
    )
    return {
        "id": str(node.pk),
        "title": node.title,
        "href": node.href,
        "group": node.parent.title if group else None,
        "added": fresh,
    }


def _edited(grant: Grant, given: str, operations: list[dict]) -> dict[str, Any]:
    tab = live_tab(grant.user, _id(given), Role.EDIT)
    run, made = runs.start(EDIT, tab, grant.user, {}, {"operations": operations}, operations, grant)
    return {"run": described(run), "made": made}


def _ran(
    grant: Grant, action: Action, given: str, target: dict, parameters: dict
) -> dict[str, Any]:
    user = grant.user
    tab = live_tab(user, _id(given), Role.EDIT)
    if why := invalid(action, target, parameters):
        raise ToolError(why)
    if action.model is not None and not installation.enabled():
        raise Refused(409, "ai_off")
    planned = runs.plan(action, tab, user, target, parameters)
    if isinstance(planned, Prompt):
        consent = (ActionRun.Consented.ONCE, user)
        run = runs.begin(action, tab, user, target, parameters, planned, consent, grant)
        return {"run": described(run)}
    run, made = runs.start(action, tab, user, target, parameters, planned, grant)
    return {"run": described(run), "made": made}


def _run(user, given: str) -> dict[str, Any]:
    run = ActionRun.objects.filter(pk=_id(given)).first()
    if run is None or run.document_id is None:
        raise Refused(404, "not_found")
    live_document(user, run.document_id)
    return described(run)


def _box(user, given: int | None, needs: Role):
    """The user, or the shared mailbox they name, where their grant covers what the tool does."""
    return user if given is None else sharing.mailbox(user, str(given), needs)


def _whose(user, pks: list[int], needs: Role):
    """Whose mail the messages are: the user's, or the one shared mailbox's they are in."""
    owners = set(Message.objects.filter(pk__in=pks).values_list("owner_id", flat=True))
    if len(owners) > 1:
        raise Refused(400, "several_mailboxes")
    owner = next(iter(owners), user.pk)
    return user if owner == user.pk else _box(user, owner, needs)


def _message(user, pk: int) -> dict[str, Any]:
    owner = _whose(user, [pk], sharing.READ)
    found = loaded(owner, pk)
    return (
        describe_message(found)
        | {"mailbox": None if owner is user else owner.pk}
        | {"cc": found.cc, "reply_to": found.reply_to, "attachments": describe_files(found)}
        | {"text": quoted_text(found)}
        | {"drafts": [describe_draft(each) for each in found.drafts.filter(owner=owner)]}
    )


def _attachment(user, pk: int, part: str) -> dict[str, Any]:
    found = loaded(_whose(user, [pk], sharing.READ), pk)
    found = found.files.select_related("blob").filter(part=part, inline=False).first()
    if found is None:
        raise Refused(404, "not_found")
    described = {"part": found.part, "name": found.name, "media_type": found.blob.media_type}
    return described | _file_text(found.blob)


def _letter_text(text: str) -> None:
    if not text.strip() or len(text) > 100_000:
        raise ToolError("the text is empty or too long")


def _drafted(grant: Grant, pk: int, way: str, text: str, replaces: int | None) -> dict[str, Any]:
    if way not in WAYS:
        raise ToolError(f"way must be one of {', '.join(WAYS)}")
    _letter_text(text)
    owner = _whose(grant.user, [pk], sharing.EDIT)
    found = loaded(owner, pk)
    if replaces is None:
        made = Draft.objects.create(owner=owner, message=found, way=way, text=text, grant=grant)
        return describe_draft(made)
    own = found.drafts.filter(owner=owner, pk=replaces, grant=grant).first()
    if own is None:
        raise Refused(404, "not_found")
    own.way, own.text = way, text
    own.save(update_fields=["way", "text"])
    return describe_draft(own)


def _people(given: list[str]) -> list[dict[str, str]]:
    return [{"name": named, "address": address} for named, address in map(parseaddr, given)]


def _new_mail(
    grant: Grant,
    to: list[str],
    subject: str,
    text: str,
    cc: list[str],
    account: int | None,
    replaces: int | None,
) -> dict[str, Any]:
    _letter_text(text)
    if not to:
        raise ToolError("the message needs a recipient")
    people = {"to": _people(to), "cc": _people(cc)}
    return described_unsent(agent_mail(grant, people, subject, text, account, replaces))


def _moment(given: str) -> datetime:
    try:
        moment = datetime.fromisoformat(given)
    except ValueError:
        raise ToolError("since must be a date or a moment in ISO 8601") from None
    return moment if moment.tzinfo else moment.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))


def _mailbox(
    user,
    folder: str,
    unread: bool,
    since: str | None,
    account: int | None,
    mailbox: int | None,
    limit: int,
) -> dict[str, Any]:
    if not folder or folder not in FolderRole.values:
        raise ToolError(f"folder must be one of {', '.join(filter(None, FolderRole.values))}")
    moment = None if since is None else _moment(since)
    owner = _box(user, mailbox, sharing.READ)
    found = listing(owner, folder, unread, moment, account, min(limit, MOST))
    accounts = Account.objects.filter(owner=owner).order_by("pk")
    roles = sharing.roles(user)
    boxes = (
        get_user_model().everyone.filter(pk__in=roles, mailbox=True).order_by("first_name", "pk")
    )
    return {
        "mailboxes": [
            {"id": box.pk, "name": box.first_name, "role": roles[box.pk]} for box in boxes
        ],
        "accounts": list(accounts.values("id", "address", "name", "default")),
        "messages": [describe_message(each) for each in found],
    }


def _acted(grant: Grant, action, messages: list[int], parameters: dict) -> dict[str, Any]:
    """Does the action to the messages, all of one mailbox, as the list does it, kept as a run of
    the agent's."""
    if why := invalid(action, {"messages": messages}, parameters):
        raise ToolError(why)
    owner = _whose(grant.user, messages, sharing.EDIT)
    found = Message.objects.filter(owner=owner, pk__in=messages).exclude(reactions.ATTACHED)
    if found.count() != len(messages):
        raise Refused(404, "not_found")
    from_junk = not found.exclude(folder__role=FolderRole.JUNK).exists()
    with transaction.atomic():
        changed = action.plan(acting.Acting(owner, grant.user, from_junk), found, parameters)
        ActionRun.objects.create(
            user=grant.user,
            action=action.id,
            target={"messages": messages},
            parameters=parameters,
            state=ActionRun.State.DONE,
            finished_at=timezone.now(),
            grant=grant,
        )
    return {"changed": changed}


def _calendars(user) -> dict[str, Any]:
    found = (
        Calendar.objects.filter(owner=user)
        .select_related("account")
        .prefetch_related("feeds__account")
        .order_by("pk")
    )
    return {"calendars": [describe_calendar(each) for each in found]}


def _events(user, first: str, last: str, zone: str) -> dict[str, Any]:
    clock = ZoneInfo(zone_of(zone))
    try:
        start, end = datetime.fromisoformat(first), datetime.fromisoformat(last)
    except ValueError:
        raise ToolError("from and to are dates, YYYY-MM-DD") from None
    if end < start or end - start > timedelta(days=LONGEST):
        raise ToolError(f"to is before from or more than {LONGEST} days after it")
    since = start.replace(tzinfo=clock)
    until = (end + timedelta(days=1)).replace(tzinfo=clock)
    visible = Calendar.objects.filter(owner=user)
    return {"events": occurrences_of(visible, since, until, zone)}


def _created_event(user, zone: str, data: dict) -> dict[str, Any]:
    made, _, _ = created_event(user, zone_of(zone), data)
    return made


def _tasks(user) -> dict[str, Any]:
    return {"tasks": [describe_task(each) for each in listed_tasks(user)]}


def _added_task(user, text: str, due: str | None) -> dict[str, Any]:
    made = Task(owner=user)
    filled(made, {"text": text, "due": due})
    made.save()
    return describe_task(made)


def _contacts(user, query: str) -> dict[str, Any]:
    found = [summary(each) for each in contacts.matching(user.pk, query[:200])][:MOST]
    return {"contacts": found}


def _schemas() -> dict[str, Any]:
    return {name: schema.validator(spec).schema for name, spec in OPERATIONS.items()}


@server.tool()
async def me() -> dict[str, Any]:
    """Who you act as: the user who let you in, and the name you were let in under."""
    grant = await _signed()
    return {"user": describe_user(grant.user), "client": grant.client.name}


def _help_language(user) -> str:
    return library.language_of(None, user)


@server.tool()
async def search_help(query: str, limit: int = 8) -> dict[str, Any]:
    """Articles of PONISTRA's own help matching the words: how a function works and where it is.
    Look here before telling the user how the suite behaves."""
    grant = await _signed()
    user = grant.user
    found = library.found(user, query, _help_language(user), min(limit, MOST))
    return {"articles": found}


@server.tool()
async def read_help(article: str) -> dict[str, Any]:
    """One article of the help, by the id search_help gave, as Markdown in the user's language."""
    grant = await _signed()
    user = grant.user
    page = library.article(user, article, _help_language(user))
    if page is None:
        raise ToolError("no such article")
    return {"id": article, "title": page.title, "text": page.reading}


@server.tool()
async def search(query: str, folder: str | None = None, limit: int = 8) -> dict[str, Any]:
    """Documents, files, mail, calendar events, tasks and people matching the words, as the
    search box finds them, with the filters it takes typed among the words: "kind:event",
    "from:ana", "date:2025", "has:attachment". A folder id narrows it to that folder's
    documents; the rest is searched only without one."""
    grant = await _signed()
    return await call(_search, grant.user, query, folder, max(1, min(limit, MOST)))


@server.tool()
async def list_folder(folder: str | None = None, root: str = "mine") -> dict[str, Any]:
    """What a folder holds, by its id; without one, the top of the user's own documents
    ("mine"), what is shared with them ("shared") or the company's folders ("company")."""
    grant = await _signed()
    return await call(_folder, grant.user, folder, root)


@server.tool()
async def read_document(document: str) -> dict[str, Any]:
    """A document's tabs, a file's text page by page, a board's page, or a folder's content,
    by id."""
    grant = await _signed()
    return await call(_document, grant.user, document)


@server.tool()
async def read_tab(tab: str) -> dict[str, Any]:
    """A tab's text as a model reads it: each block on a line after its id in brackets and its
    kind, a table's rows after it. The ids are what operations address."""
    grant = await _signed()
    return await call(_tab, grant.user, tab)


@server.tool()
async def create_document(title: str, folder: str | None = None) -> dict[str, Any]:
    """A new, empty document, in the folder given or at the top of the user's own documents;
    returns its id and the id of its one tab, to write into with edit_tab."""
    grant = await _signed()
    return await call(_created_document, grant.user, title, folder)


@server.tool()
async def write_board(
    html: str, title: str | None = None, group: str | None = None, board: str | None = None
) -> dict[str, Any]:
    """Writes a board: a whole page of HTML, from <!doctype html>, that the user opens in
    PONISTRA as it is. Without `board` it is a new one, titled, in the group given on the user's
    page of boards: the project or subject it belongs to, matched whatever its case and made if
    missing. With `board`, that board's page is replaced (and renamed, given a title; and moved,
    given a group) and the page before kept as a version. read_document gives a board's page back.
    The page runs sandboxed in an origin of its own: no storage, no cookies, nothing of PONISTRA,
    no links or windows that open, no forms that send. Scripts, styles and fonts load only from
    cdnjs.cloudflare.com, cdn.jsdelivr.net, unpkg.com, cdn.tailwindcss.com, code.jquery.com and
    Google Fonts, and fetch only from those CDNs: the data it shows belongs in the page itself or
    in what the board keeps. A page that loads <script src="/api/boards/runtime.js"></script> finds
    window.ponistra.db (null where the page has no board around it, as in a file on its own):
    db.collection(name).onSnapshot(next, failed) calls next({docs, size, empty}) at once and each
    time the collection changes, a doc giving its id, version and data(); .get() reads once;
    db.collection(name).doc(key) has get, set, update, delete and onSnapshot. Whoever can read the
    board reads, whoever can edit it writes; someone holding an outside link only reads, and
    db.canWrite() tells the page which, so that it disables what would be refused.
    Returns its id, title, group, version number and the address the user opens it at."""
    grant = await _signed()
    return await call(_board, grant, html, title, group, board)


@server.tool()
async def move_board(board: str, group: str) -> dict[str, Any]:
    """Moves a board, leaving its page as it is, into the group of that name on the user's page of
    boards, matched whatever its case and made if missing. Returns what write_board returns."""
    grant = await _signed()
    return await call(_board_moved, grant.user, board, group)


@server.tool()
async def read_board_data(
    board: str,
    collection: str | None = None,
    key: str | None = None,
    where: dict[str, Any] | None = None,
    limit: int = 100,
    after: str | None = None,
) -> dict[str, Any]:
    """What a board keeps: without a collection the collections and how many documents each holds,
    with one its documents in the order of their keys, up to `limit` (at most 1000), after the key
    `after` (`next` in the answer goes there), keeping those whose fields hold the values in
    `where`; with a key too, that one document."""
    grant = await _signed()
    if not 0 < limit <= 1000:
        raise ToolError("a limit from 1 to 1000")
    return await call(_board_read, grant.user, board, collection, key, where, limit, after)


@server.tool()
async def write_board_data(board: str, writes: list[dict[str, Any]]) -> dict[str, Any]:
    """Writes what a board keeps, all of it or none of it, and pages that show it follow at once.
    Each write is {op, collection, key, data, if_version}: op `set` replaces the document, `update`
    merges fields into it at any depth (a field given as {"__delete__": true} leaves) and `delete`
    removes it; if_version, when given, refuses a document that is no longer at that version, 0
    being one that does not exist. Names are of letters, digits and _ - . ~ : @ +; a document holds
    at most 256 kB, a call at most 500 writes. The page stays as it is, with no new version."""
    grant = await _signed()
    return await call(_board_written, grant, board, writes)


@server.tool()
async def add_link(url: str, title: str | None = None, group: str | None = None) -> dict[str, Any]:
    """Puts a link on the user's page of links, in the group named, which is made where there is
    none and matched regardless of case, or without a group. Without a title the link takes the
    page's own. An address already in that place stays as the user left it and returns with
    `added` false, so asking twice adds nothing."""
    grant = await _signed()
    return await call(_link, grant.user, url, title, group)


@server.tool()
async def operations_schema() -> dict[str, Any]:
    """The JSON Schema of each operation edit_tab takes, by its name."""
    await _signed()
    return _schemas()


@server.tool()
async def edit_tab(tab: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Writes into a tab with the editor's operations (see operations_schema), as one run the
    user can take back as a whole: what it inserts, replaces or deletes lands as proposals the
    user accepts or rejects, so write only what belongs in the document. Read the tab first:
    operations address blocks and cells by the ids its text shows."""
    grant = await _signed()
    if not operations or len(operations) > 200:
        raise ToolError("one to 200 operations")
    return await call(_edited, grant, tab, operations)


@server.tool()
async def get_run(run: str) -> dict[str, Any]:
    """How a run went, by its id: its state, what its model said, and whether it changed
    anything."""
    grant = await _signed()
    return await call(_run, grant.user, run)


@server.tool()
async def list_mail(
    folder: str = "inbox",
    unread: bool = False,
    since: str | None = None,
    account: int | None = None,
    mailbox: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """The newest messages of a kind of folder ("inbox", "sent", "archive"...), each with the id
    read_message takes, the accounts of the mailbox listed and the shared mailboxes the user
    reaches, with their role in each. `unread` keeps those not read yet, `since` those from a date
    or moment on, in ISO 8601. Without `account`, mail of accounts the user keeps out of the
    shared folders is not listed; without `mailbox`, it is the user's own mail."""
    grant = await _signed()
    return await call(_mailbox, grant.user, folder, unread, since, account, mailbox, limit)


@server.tool()
async def read_message(message: int) -> dict[str, Any]:
    """A mail message by its id, with its text, attachments, the drafts waiting on it and the
    shared mailbox it is in, none in the user's own."""
    grant = await _signed()
    return await call(_message, grant.user, message)


@server.tool()
async def read_attachment(message: int, part: str) -> dict[str, Any]:
    """The text of a file a message carries, page by page, by the part read_message lists it
    under: its text only, never the file. Where there is no text `unread` says why: "waiting"
    (not read yet), "not_text" (a kind of file whose text is not read, as an archive or an image)
    or "failed". `cut` means the text runs past what one reading carries; `ocr` gives the state
    of the reading of pages without text, where it is not done."""
    grant = await _signed()
    return await call(_attachment, grant.user, message, part)


@server.tool()
async def draft_reply(
    message: int, text: str, way: str = "reply", replaces: int | None = None
) -> dict[str, Any]:
    """Drafts a reply to a message ("reply", "all") or a forward ("forward") for the user to
    send: they open it over the message, read it and send or drop it. Nothing is sent here.
    `replaces` is the id of a draft you wrote over this message, to correct it in place."""
    grant = await _signed()
    return await call(_drafted, grant, message, way, text, replaces)


@server.tool()
async def draft_mail(
    to: list[str],
    subject: str,
    text: str,
    cc: list[str] | None = None,
    account: int | None = None,
    replaces: int | None = None,
) -> dict[str, Any]:
    """Drafts a new message for the user to send, among those they began and have not sent. `to`
    and `cc` are addresses, or "Name <address>"; `text` is plain, a paragraph a line, and the
    account's signature is added. Without `account` it goes from the account the user last wrote
    to the first recipient from, else their default (list_mail names the accounts). `replaces` is
    the id of a draft you wrote that the user has not touched, to correct it in place. Nothing is
    sent here."""
    grant = await _signed()
    return await call(_new_mail, grant, to, subject, text, cc or [], account, replaces)


@server.tool()
async def list_calendars() -> dict[str, Any]:
    """The user's calendars, their ids and which take new events."""
    grant = await _signed()
    return await call(_calendars, grant.user)


@server.tool()
async def list_events(from_day: str, to_day: str, zone: str = settings.TIME_ZONE) -> dict[str, Any]:
    """The user's events from one day to another, both YYYY-MM-DD, in the time zone given."""
    grant = await _signed()
    return await call(_events, grant.user, from_day, to_day, zone)


@server.tool()
async def create_event(
    calendar: int,
    summary: str,
    start: str,
    end: str,
    all_day: bool = False,
    location: str = "",
    description: str = "",
    zone: str = settings.TIME_ZONE,
) -> dict[str, Any]:
    """A new event in one of the user's calendars: start and end as YYYY-MM-DDTHH:MM in the
    time zone given, or as YYYY-MM-DD for an all-day event. Attendees are the user's to add."""
    grant = await _signed()
    data = {
        "calendar": calendar,
        "summary": summary,
        "start": start,
        "end": end,
        "all_day": all_day,
        "location": location,
        "description": description,
        "zone": zone,
    }
    return await call(_created_event, grant.user, zone, data)


def _memory_owner(user) -> None:
    from apps.workspace.views import owns

    if not owns(user):
        raise Refused(403, "not_the_workspace_owner")


def _memory_proposed(user, store, file, reason, edits, text, remove) -> dict[str, Any]:
    _memory_owner(user)
    proposal = memory.proposed(store, file, reason, edits=edits, text=text, remove=remove)
    return {"proposal": proposal.pk, "state": proposal.state}


@server.tool()
async def propose_memory(
    store: str,
    file: str,
    reason: str,
    edits: list[dict[str, str]] | None = None,
    text: str | None = None,
    remove: bool = False,
) -> dict[str, Any]:
    """Proposes a change to one file of the agent's memory in the owner's code workspace, for them
    to accept or reject on the Projects page; nothing is written here. `store` is the folder under
    `~/.claude/projects/` (`-mnt-docker-ponistra`) or `global` for `~/.claude/CLAUDE.md`, `file`
    its name (`MEMORY.md`, `project_x.md`). Give one of: `edits`, each {old_text, new_text} with
    old_text found exactly once in the file as it is now; `text`, the file's whole new text (a new
    file too); or `remove` true. `reason` says why, in the owner's language."""
    grant = await _signed()
    return await call(_memory_proposed, grant.user, store, file, reason, edits, text, remove)


def _memory_waiting(user) -> dict[str, Any]:
    _memory_owner(user)
    return {"proposals": memory.opened()}


def _memory_advised(user, groups) -> dict[str, Any]:
    _memory_owner(user)
    return {"groups": len(memory.advised(groups))}


@server.tool()
async def memory_proposals() -> dict[str, Any]:
    """The open proposals for the agent's memory in the owner's code workspace, each with its id,
    store, file, kind, reason and what it changes: each changed line as only its changed words
    with the text around them, at most six changes and how many more."""
    grant = await _signed()
    return await call(_memory_waiting, grant.user)


@server.tool()
async def advise_memory(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Sorts the open memory proposals into groups for the owner to accept or reject each group of
    at once, replacing the groups sent before. Each group is {title, reason, action, proposals}:
    a short title and a one-sentence reason in the owner's language, `action` one of `accept`,
    `reject` or `look` (the owner decides each), and the ids of its proposals, each in one group
    at most."""
    grant = await _signed()
    return await call(_memory_advised, grant.user, groups)


@server.tool()
async def list_tasks() -> dict[str, Any]:
    """The user's tasks: what is open, and what was done lately."""
    grant = await _signed()
    return await call(_tasks, grant.user)


@server.tool()
async def add_task(text: str, due: str | None = None) -> dict[str, Any]:
    """A new task for the user, due on a day (YYYY-MM-DD) or on none."""
    grant = await _signed()
    return await call(_added_task, grant.user, text, due)


@server.tool()
async def find_contacts(query: str = "") -> dict[str, Any]:
    """The user's contacts matching the words, by name, organisation or address; all of them
    for no words."""
    grant = await _signed()
    return await call(_contacts, grant.user, query)


def _action_tool(action: Action) -> Callable:
    target = json.dumps(TARGETS[action.target])
    parameters = json.dumps(action.parameters)
    writes = (
        "What it writes lands as proposals the user accepts or rejects."
        if action.review == "propose"
        else "What it writes is applied at once, as one run the user can take back."
    )
    model = (
        " The installation's own model carries it out in the background; get_run tells when it"
        " is done."
        if action.model
        else ""
    )

    async def tool(
        tab: str, target: dict[str, Any] | None = None, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        grant = await _signed()
        return await call(_ran, grant, action, tab, target or {}, parameters or {})

    tool.__name__ = action.id.replace(".", "_")
    tool.__doc__ = (
        f"Runs the action {action.id} on a tab. target: {target}. parameters: {parameters}."
        f" {writes}{model}"
    )
    return tool


for each in RUNNABLE.values():
    server.add_tool(_action_tool(each))


def _mail_tool(action: Action) -> Callable:
    parameters = json.dumps(action.parameters)

    async def tool(messages: list[int], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        grant = await _signed()
        return await call(_acted, grant, action, messages, parameters or {})

    tool.__name__ = action.id.replace(".", "_")
    tool.__doc__ = (
        f"{MAIL_DOES[action.id]} `messages` are ids as list_mail and search give them, all of one"
        f" mailbox, the user's own or a shared one where they may change its mail. parameters:"
        f" {parameters}. It is done at once, in PONISTRA only; `changed` says to how many."
    )
    return tool


for each in MAIL_DOES:
    server.add_tool(_mail_tool(ACTIONS[each]))
