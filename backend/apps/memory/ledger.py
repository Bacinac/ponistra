"""The ledger of the agent's memory (MEM1–MEM5): what the workspace reads of its stores, the
proposals kept here until their owner accepts or rejects them, and the history of what was
written. The workspace alone touches the files; here each change is only asked of it, against the
hash of the text it was read from."""

import difflib
import hashlib
import threading
from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from apps.collab.live import CHANGES
from apps.core.api import Refused
from apps.core.asyncdb import released
from apps.push import notices as push
from apps.push.models import Notice
from apps.workspace.models import Command
from apps.workspace.views import _asked, sent

from .models import Advice, Analysed, Nightly, Proposal

AREA = "memory"
INDEX = "MEMORY.md"
GLOBAL = "global"
State = Proposal.State
Source = Proposal.Source
# Context lines around each change a proposal shows.
AROUND = 2
HISTORY = 30
# What one analysing session is given at most, so that a first analysis does not read every store
# at once; the rest waits for the next.
ANALYSED_AT_ONCE = 80
# The context an excerpt keeps around a change within a line, and the changes it shows at most.
EXCERPT = 60
EXCERPTS = 6
# Two changes heard at once would each take the other's proposals for new.
_one_at_a_time = threading.Lock()


def hash_of(text: str | None) -> str:
    return "" if text is None else hashlib.sha256(text.encode()).hexdigest()


def owners() -> list[int]:
    return list(
        get_user_model()
        .objects.filter(email__iexact=settings.WORKSPACE, is_active=True)
        .values_list("pk", flat=True)
    )


def told() -> None:
    """The owner's tabs read the memory again: the workspace's reading changed, not a row here."""
    with connection.cursor() as cursor:
        for owner in owners():
            cursor.execute("SELECT pg_notify(%s, %s)", [CHANGES, f"{AREA} u{owner}"])


def read() -> dict:
    released()
    return async_to_sync(_asked)("GET", "memory")


def synced(listed: dict) -> list[Proposal]:
    """The mechanical proposals the workspace reads now, each kept once: a new one opens, an open
    one it no longer reads goes stale, and so does any open one whose file changed since it was
    read. Returns those just opened."""
    hashes = {
        (store["store"], file): hash
        for store in listed.get("stores", [])
        for file, hash in store.get("hashes", {}).items()
    }
    hashes[(GLOBAL, "CLAUDE.md")] = listed.get("global", {}).get("hash", "")
    found = {
        (each["store"], each["file"], each["kind"], each["hash"], hash_of(each["after"])): each
        for each in listed.get("proposals", [])
    }
    opened = []
    now = timezone.now()
    with transaction.atomic():
        kept = set(
            Proposal.objects.filter(source=Source.MECHANICAL).values_list(
                "store", "file", "kind", "base_hash", "after_hash"
            )
        )
        for key, each in found.items():
            if key in kept:
                continue
            opened.append(
                Proposal(
                    store=each["store"],
                    file=each["file"],
                    source=Source.MECHANICAL,
                    kind=each["kind"],
                    reason=each.get("detail") or "",
                    before=each["before"],
                    after=each["after"],
                    base_hash=each["hash"],
                    after_hash=key[4],
                )
            )
        Proposal.objects.bulk_create(opened, ignore_conflicts=True)
        stale = []
        for proposal in Proposal.objects.filter(state=State.OPEN).only(
            "pk", "store", "file", "kind", "source", "base_hash", "after_hash"
        ):
            where = (proposal.store, proposal.file)
            gone = hashes.get(where, "") != proposal.base_hash
            unread = (
                proposal.source == Source.MECHANICAL
                and (
                    *where,
                    proposal.kind,
                    proposal.base_hash,
                    proposal.after_hash,
                )
                not in found
            )
            if gone or unread:
                stale.append(proposal.pk)
        Proposal.objects.filter(pk__in=stale).update(state=State.STALE, decided_at=timezone.now())
        return list(
            Proposal.objects.filter(
                state=State.OPEN, source=Source.MECHANICAL, created_at__gte=now
            ).order_by("pk")
        )


def diff(before: str, after: str | None) -> list[dict]:
    """The proposal's change as the lines it takes out and puts in, each run of them with the lines
    around it; `@` stands between two runs."""
    lines = []
    old = before.splitlines()
    new = (after or "").splitlines()
    for group in difflib.SequenceMatcher(None, old, new, autojunk=False).get_grouped_opcodes(
        AROUND
    ):
        if lines:
            lines.append({"op": "@", "text": ""})
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                lines.extend({"op": " ", "text": text} for text in old[i1:i2])
                continue
            lines.extend({"op": "-", "text": text} for text in old[i1:i2])
            lines.extend({"op": "+", "text": text} for text in new[j1:j2])
    return lines


def shown(proposal: Proposal, *, changes: bool = True) -> dict:
    said = {
        "id": proposal.pk,
        "store": proposal.store,
        "file": proposal.file,
        "source": proposal.source,
        "kind": proposal.kind,
        "reason": proposal.reason or None,
        "session": proposal.session or None,
        "state": proposal.state,
        "removes": proposal.removes,
        "creates": not proposal.base_hash,
        "created_at": proposal.created_at.isoformat(),
        "decided_at": proposal.decided_at and proposal.decided_at.isoformat(),
    }
    if changes:
        said["diff"] = diff(proposal.before, None if proposal.removes else proposal.after)
    return said


def overview(listed: dict) -> dict:
    open_ = list(Proposal.objects.filter(state=State.OPEN).order_by("store", "file", "pk"))
    history = Proposal.objects.filter(state__in=[State.APPLIED, State.REVERTED]).order_by(
        "-decided_at", "-pk"
    )[:HISTORY]
    waiting: dict[str, int] = {}
    for proposal in open_:
        waiting[proposal.store] = waiting.get(proposal.store, 0) + 1
    analysed = {(each.store, each.file): each.hash for each in Analysed.objects.all()}
    stores = []
    for store in listed.get("stores", []):
        hashes = store.get("hashes", {})
        stores.append(
            {
                "store": store["store"],
                "folder": store.get("folder"),
                "files": store["files"],
                "bytes": store["bytes"],
                "index": store.get("index"),
                "findings": store.get("findings", []),
                "proposals": waiting.get(store["store"], 0),
                "unanalysed": sum(
                    1
                    for file, hash in hashes.items()
                    if analysed.get((store["store"], file)) != hash
                ),
            }
        )
    nightly = Nightly.objects.get_or_create(pk=1)[0]
    return {
        "root": listed.get("root"),
        "stores": stores,
        "advice": advice(),
        "proposals": [shown(each) for each in open_],
        "history": [shown(each) for each in history],
        "nightly": nightly.on,
    }


def waiting_count() -> int:
    return Proposal.objects.filter(state=State.OPEN).count()


def _written(proposal: Proposal, text: str | None, expected: str) -> str:
    answer = async_to_sync(_asked)(
        "POST",
        "memory/write",
        {"store": proposal.store, "file": proposal.file, "hash": expected, "text": text},
    )
    return answer["hash"]


def decided(pk: int, accepted: bool) -> Proposal:
    """Accepted, the proposal is written while its file is still the one it was read from, else it
    goes stale; rejected, it stays here so that the same reading never proposes it again."""
    with transaction.atomic():
        proposal = Proposal.objects.select_for_update().filter(pk=pk).first()
        if proposal is None:
            raise Refused(404, "not_found")
        if proposal.state != State.OPEN:
            raise Refused(409, "memory_decided")
        proposal.decided_at = timezone.now()
        if not accepted:
            proposal.state = State.REJECTED
            proposal.save(update_fields=["state", "decided_at"])
            return proposal
        try:
            after = None if proposal.removes else proposal.after
            proposal.written_hash = _written(proposal, after, proposal.base_hash)
        except Refused as refused:
            if refused.status != 409:
                raise
            if not _rebased(proposal):
                proposal.state = State.STALE
                proposal.save(update_fields=["state", "decided_at"])
                return proposal
        proposal.state = State.APPLIED
        proposal.save()
    told()
    return proposal


def merged(base: str, ours: str, theirs: str) -> str | None:
    """Our change of the base laid over theirs, line by line, while the two touch different lines;
    None where they meet."""
    lines = base.splitlines(keepends=True)

    def changes(other: str) -> list[tuple[int, int, list[str]]]:
        new = other.splitlines(keepends=True)
        matcher = difflib.SequenceMatcher(None, lines, new, autojunk=False)
        return [
            (i1, i2, new[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"
        ]

    mine, others = changes(ours), changes(theirs)
    if any((a1 < b2 and b1 < a2) or a1 == b1 for a1, a2, _ in mine for b1, b2, _ in others):
        return None
    out, at = [], 0
    for i1, i2, new in sorted(mine + others, key=lambda change: change[0]):
        out += lines[at:i1] + new
        at = i2
    return "".join(out + lines[at:])


def _rebased(proposal: Proposal) -> bool:
    """A proposal whose file moved on since it was read, written over the file as it is now when
    the change since touched other lines (another proposal accepted in the same file); the
    proposal then holds the text it was written over, so that taking it back keeps that change."""
    if proposal.removes:
        return False
    where = urlencode({"store": proposal.store, "file": proposal.file})
    current = async_to_sync(_asked)("GET", f"memory/file?{where}")
    if current["text"] is None:
        return False
    after = merged(proposal.before, proposal.after, current["text"])
    if after is None:
        return False
    try:
        proposal.written_hash = _written(proposal, after, current["hash"])
    except Refused as refused:
        if refused.status != 409:
            raise
        return False
    proposal.before, proposal.base_hash = current["text"], current["hash"]
    proposal.after, proposal.after_hash = after, hash_of(after)
    return True


def reverted(pk: int) -> Proposal:
    """What an applied proposal wrote taken back, while the file is still what it wrote."""
    with transaction.atomic():
        proposal = Proposal.objects.select_for_update().filter(pk=pk).first()
        if proposal is None:
            raise Refused(404, "not_found")
        if proposal.state != State.APPLIED:
            raise Refused(409, "memory_decided")
        before = proposal.before if proposal.base_hash else None
        try:
            _written(proposal, before, proposal.written_hash)
        except Refused as refused:
            if refused.status == 409:
                raise Refused(409, "memory_changed") from None
            raise
        proposal.state = State.REVERTED
        proposal.decided_at = timezone.now()
        proposal.save(update_fields=["state", "decided_at"])
    told()
    return proposal


def _edited(text: str, edits: list) -> str:
    for edit in edits:
        if not isinstance(edit, dict):
            raise Refused(400, "invalid_edit")
        old, new = edit.get("old_text"), edit.get("new_text")
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise Refused(400, "invalid_edit")
        count = text.count(old)
        if count != 1:
            raise Refused(400, "old_text_not_found" if not count else "old_text_not_unique")
        text = text.replace(old, new)
    return text


def proposed(
    store: str,
    file: str,
    reason: str,
    *,
    edits: list | None = None,
    text: str | None = None,
    remove: bool = False,
    session: str = "",
) -> Proposal:
    """A session's proposal for one file (MEM4), read from the workspace as it is now: edits to
    it, its whole new text, or taking it away."""
    if not isinstance(reason, str) or not reason.strip():
        raise Refused(400, "invalid_reason")
    if sum((edits is not None, text is not None, remove)) != 1:
        raise Refused(400, "one_of_edits_text_remove")
    where = urlencode({"store": store, "file": file})
    current = async_to_sync(_asked)("GET", f"memory/file?{where}")
    before = current["text"]
    if remove:
        if before is None:
            raise Refused(404, "no_file")
        after = None
    elif edits is not None:
        if before is None or not isinstance(edits, list) or not edits:
            raise Refused(400, "invalid_edit")
        after = _edited(before, edits)
    else:
        if not isinstance(text, str):
            raise Refused(400, "invalid_text")
        after = text
    if after == before:
        raise Refused(400, "unchanged")
    return Proposal.objects.create(
        store=store,
        file=file,
        source=Source.SESSION,
        kind="session",
        reason=reason.strip(),
        session=session,
        before=before or "",
        after=after or "",
        removes=remove,
        base_hash=current["hash"],
        after_hash=hash_of(after),
    )


def tell_owner(opened: list[Proposal]) -> None:
    """The owner hears of new proposals on their devices (MEM5): one alone with Yes and No to it,
    several as how many."""
    if not opened:
        return
    users = owners()
    if len(opened) == 1:
        proposal = opened[0]
        data = {
            "event": "memory",
            "project": proposal.store,
            "file": proposal.file,
            "text": proposal.reason,
            "proposal": proposal.pk,
        }
    else:
        data = {"event": "memory", "project": "", "count": len(opened)}
    push.tell(users, Notice.Kind.CODE, data, tag=push.topic("memory", opened[-1].pk))


def heard() -> None:
    """The workspace says a store changed: its proposals are read again, and the owner hears of
    the new ones."""
    if not owners():
        return
    with _one_at_a_time:
        try:
            listed = read()
        except Refused:
            return
        with transaction.atomic():
            tell_owner(synced(listed))
    told()


def _files_to_analyse(listed: dict, store: str | None) -> list[tuple[str, str, str]]:
    analysed = {(each.store, each.file): each.hash for each in Analysed.objects.all()}
    files = [
        (each["store"], file, hash)
        for each in listed.get("stores", [])
        if store is None or each["store"] == store
        for file, hash in sorted(each.get("hashes", {}).items())
        if hash and analysed.get((each["store"], file)) != hash
    ]
    return files[:ANALYSED_AT_ONCE]


PROMPT = """Analyse the agent's memory for PONISTRA's Memory tab (MEM4). Do not edit any memory \
file yourself: propose every change through the ponistra MCP tool `propose_memory`, one call per \
file, its `reason` one sentence in Croatian. The owner accepts or rejects each on the Projects page.

The stores are `~/.claude/projects/<store>/memory/`; the global instructions are \
`~/.claude/CLAUDE.md` (store `global`, file `CLAUDE.md`). Read only these files, changed since \
the last analysis{more}:
{files}

Look for:
- duplicates within a store: merge them into one file (edits to the one kept, `remove` for the \
other, its line in `MEMORY.md` dropped);
- contradictions between memories, and between a memory and its project's `CLAUDE.md` (the \
repository is the truth; propose the memory's correction);
- a rule repeated in three or more stores: propose it once for the global `CLAUDE.md` and its \
removal from each store;
- lines of `MEMORY.md` longer than they need to be: shorten them, keeping what recall needs.

Propose nothing when nothing is wrong. End with a short summary in Croatian of what you proposed."""


def analyse(store: str | None) -> Command:
    """Asks the workspace for a session that analyses the memory changed since it was last
    analysed, in the store's project or over every store from the workspace's root."""
    listed = read()
    if store is not None and not any(each["store"] == store for each in listed["stores"]):
        raise Refused(404, "no_store")
    files = _files_to_analyse(listed, store)
    if not files:
        raise Refused(409, "memory_analysed")
    folder = listed.get("root") or ""
    if store is not None:
        own = next(each["folder"] for each in listed["stores"] if each["store"] == store)
        folder = own or folder
    if not folder.startswith("/"):
        raise Refused(409, "workspace_unreachable")
    text = PROMPT.format(
        files="\n".join(f"- {each_store}/{file}" for each_store, file, _hash in files),
        more="" if len(files) < ANALYSED_AT_ONCE else " (the first of more, the rest next time)",
    )
    command = Command.objects.create(kind=Command.Kind.CHAT, folder=folder, text=text)
    command = async_to_sync(sent)(command)
    if command.state != Command.State.FAILED:
        for each_store, file, hash in files:
            Analysed.objects.update_or_create(store=each_store, file=file, defaults={"hash": hash})
    return command


def _clipped(text: str, start: int, end: int) -> str:
    begin, finish = max(0, start - EXCERPT), min(len(text), end + EXCERPT)
    return ("…" if begin else "") + text[begin:finish] + ("…" if finish < len(text) else "")


def excerpts(before: str, after: str | None) -> list[dict]:
    """What a proposal changes, short enough for an analysing session to read many: each changed
    line as only its changed words with the text around them, a line taken out or put in whole."""
    old, new = before.splitlines(), (after or "").splitlines()
    said: list[dict] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace" and i2 - i1 == j2 - j1:
            for line, other in zip(old[i1:i2], new[j1:j2], strict=True):
                words = difflib.SequenceMatcher(None, line, other, autojunk=False)
                for op, a1, a2, b1, b2 in words.get_opcodes():
                    if op != "equal":
                        said.append({"old": _clipped(line, a1, a2), "new": _clipped(other, b1, b2)})
            continue
        said.extend({"old": _clipped(line, 0, 0), "new": None} for line in old[i1:i2])
        said.extend({"old": None, "new": _clipped(line, 0, 0)} for line in new[j1:j2])
    return said


def opened() -> list[dict]:
    """The open proposals as an analysing session reads them (MEM6)."""
    return [
        {
            "id": proposal.pk,
            "store": proposal.store,
            "file": proposal.file,
            "kind": proposal.kind,
            "source": proposal.source,
            "reason": proposal.reason or None,
            "removes": proposal.removes,
            "creates": not proposal.base_hash,
            "changes": (changes := excerpts(proposal.before, proposal.after))[:EXCERPTS],
            "more": max(0, len(changes) - EXCERPTS),
        }
        for proposal in Proposal.objects.filter(state=State.OPEN).order_by("store", "file", "pk")
    ]


def advice() -> list[dict]:
    """The groups the last review made, each with the proposals of it still open."""
    groups = []
    for group in Advice.objects.prefetch_related("proposals"):
        open_ = sorted(each.pk for each in group.proposals.all() if each.state == State.OPEN)
        if open_:
            groups.append(
                {
                    "id": group.pk,
                    "title": group.title,
                    "reason": group.reason,
                    "action": group.action,
                    "proposals": open_,
                }
            )
    return groups


REVIEW = """Review the open proposals for the agent's memory on PONISTRA's Memory tab (MEM6). \
Read them with the ponistra MCP tool `memory_proposals`; open a memory file \
(`~/.claude/projects/<store>/memory/<file>`, store `global` is `~/.claude/CLAUDE.md`) or the \
repository it speaks of only where an excerpt leaves the right answer in doubt. Do not edit any \
file and propose no new change.

Put the proposals into groups that share one verdict and one reason, each proposal in one group \
at most, and send all the groups at once with `advise_memory`. Each group has a short `title` and \
a one-sentence `reason`, both in Croatian, its `action` and its proposals' ids:
- `accept`: every one of them is right as it stands and safe to write unseen;
- `reject`: every one of them is wrong, a guess that misreads the memory or loses what it means;
- `look`: the owner decides each, as some are right and some not, or rightness rests on what \
only they know.

Prefer a few large groups to many small ones, but never put a wrong proposal into a group to \
accept. The mechanical kinds: `state` (git says the work a line calls uncommitted was committed \
or released), `path` (a file it names moved in the repository), `time` (a time said in UTC said \
in local time, Europe/Zagreb), `link` (a [[link]] to a memory since renamed), `index` (a line \
for a file `MEMORY.md` lacks) and `frontmatter`; `session` is an earlier analysis's own. End with \
a short summary in Croatian."""


def review() -> Command:
    """Asks the workspace for a session that sorts the open proposals into groups, each with what
    it advises doing with all of them (MEM6)."""
    if not Proposal.objects.filter(state=State.OPEN).exists():
        raise Refused(409, "memory_nothing_waiting")
    folder = read().get("root") or ""
    if not folder.startswith("/"):
        raise Refused(409, "workspace_unreachable")
    command = Command.objects.create(kind=Command.Kind.CHAT, folder=folder, text=REVIEW)
    return async_to_sync(sent)(command)


def advised(groups: object) -> list[Advice]:
    """The groups a review sends, in place of every group before; a proposal decided since the
    session read it is left out."""
    if not isinstance(groups, list) or not groups:
        raise Refused(400, "invalid_groups")
    named: list[int] = []
    for group in groups:
        if not isinstance(group, dict):
            raise Refused(400, "invalid_groups")
        title, reason, ids = group.get("title"), group.get("reason"), group.get("proposals")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
            raise Refused(400, "invalid_title")
        if not isinstance(reason, str) or not reason.strip():
            raise Refused(400, "invalid_reason")
        if group.get("action") not in Advice.Action.values:
            raise Refused(400, "invalid_action")
        if (
            not isinstance(ids, list)
            or not ids
            or not all(isinstance(each, int) and not isinstance(each, bool) for each in ids)
        ):
            raise Refused(400, "invalid_proposals")
        named += ids
    if len(named) != len(set(named)):
        raise Refused(400, "proposal_in_two_groups")
    states = dict(Proposal.objects.filter(pk__in=named).values_list("pk", "state"))
    if len(states) != len(named):
        raise Refused(400, "unknown_proposal")
    made = []
    with transaction.atomic():
        Advice.objects.all().delete()
        for position, group in enumerate(groups):
            ids = [each for each in group["proposals"] if states[each] == State.OPEN]
            if not ids:
                continue
            made.append(
                Advice.objects.create(
                    position=position,
                    title=group["title"].strip(),
                    reason=group["reason"].strip(),
                    action=group["action"],
                )
            )
            made[-1].proposals.set(ids)
    if made:
        push.tell(
            owners(),
            Notice.Kind.CODE,
            {"event": "advice", "project": "", "count": len(made)},
            tag=push.topic("advice", made[0].pk),
        )
    return made


def followed_advice(pk: int, accepted: bool) -> dict:
    """Every open proposal of a group accepted or rejected at once, in the order they were made, so
    that two in one file are written one over the other; the workspace's reading waits until all
    are, or it would take those not yet written for stale."""
    group = Advice.objects.filter(pk=pk).first()
    if group is None:
        raise Refused(404, "not_found")
    ids = list(group.proposals.filter(state=State.OPEN).order_by("pk").values_list("pk", flat=True))
    counted = {State.APPLIED: 0, State.REJECTED: 0, State.STALE: 0}
    with _one_at_a_time:
        for each in ids:
            try:
                counted[decided(each, accepted).state] += 1
            except Refused as refused:
                if refused.error != "memory_decided":
                    raise
    return {
        "applied": counted[State.APPLIED],
        "rejected": counted[State.REJECTED],
        "stale": counted[State.STALE],
    }
