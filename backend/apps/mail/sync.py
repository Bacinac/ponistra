"""Every connected account's new mail taken while the backend runs (D15, "the mail is ours"):
from INBOX at once through IDLE, from every other folder each LOOK, and what each folder held
before the account was connected taken in between, newest first."""

import threading
from contextlib import contextmanager
from datetime import timedelta
from functools import partial
from itertools import batched
from logging import getLogger
from time import monotonic, time

from anyio import CancelScope, CapacityLimiter, create_task_group, sleep, to_thread
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from imapclient import ANSWERED, FLAGGED, SEEN
from imapclient.exceptions import IMAPClientAbortError, IMAPClientError

from apps.core.asyncdb import database, drain

from . import imap, signin, taking
from .activesync import sync as activesync
from .models import Account, Folder, Source

log = getLogger(__name__)

CHANNEL = "mail"
SWEEP = timedelta(minutes=1)
LOOK = timedelta(minutes=5)
STEP = 20
RETRY = timedelta(minutes=1)
LONGEST = timedelta(minutes=30)
# Not tried again until the user signs in again.
STOPPED = {"mail_lost", "activesync_wiped"}
# The server refused a token the provider has just given, so the sign-in itself stands: Outlook.com
# refuses one now and then, and the account is tried again rather than stopped.
REFUSED_TOKEN = "imap_oauth_login"
HEADS = 200
# The most of whole messages fetched at once.
WHOLE = 32 * 1024 * 1024
KINDS = {
    b"\\Sent": Source.Kind.SENT,
    b"\\Drafts": Source.Kind.DRAFTS,
    b"\\Archive": Source.Kind.ARCHIVE,
    b"\\Junk": Source.Kind.JUNK,
    b"\\Trash": Source.Kind.TRASH,
    b"\\All": Source.Kind.ALL,
}
# Gmail's Starred and Important hold no message of their own: one is a flag, the other a guess.
LEFT = {b"\\Noselect", b"\\NonExistent", b"\\Flagged", b"\\Important"}
FLAGS = {"seen": SEEN, "flagged": FLAGGED, "answered": ANSWERED}
CHANGES = {b"EXISTS"}
HEADERS = "BODY.PEEK[HEADER.FIELDS (MESSAGE-ID X-MICROSOFT-ORIGINAL-MESSAGE-ID SUBJECT)]"
HEADED = b"BODY[HEADER.FIELDS (MESSAGE-ID X-MICROSOFT-ORIGINAL-MESSAGE-ID SUBJECT)]"


class Gone(Exception):
    """The account was removed while its thread still worked on it."""


@transaction.atomic
def sources(client, account: Account) -> list[Source]:
    """The account's folders as the server lists them now, in the order they are taken in."""
    listed = {}
    for flags, delimiter, name in client.list_folders():
        if LEFT & set(flags):
            continue
        kind = Source.Kind.INBOX if name.upper() == "INBOX" else ""
        kind = kind or next((KINDS[flag] for flag in flags if flag in KINDS), "")
        listed[name] = (kind, (delimiter or b"").decode())
    # Outlook.com marks no folder as the archive and knows its own by name.
    if not {Source.Kind.ARCHIVE, Source.Kind.ALL} & {kind for kind, _ in listed.values()}:
        for name, (kind, delimiter) in listed.items():
            if not kind and name.lower() == "archive":
                listed[name] = (Source.Kind.ARCHIVE, delimiter)
    account.sources.exclude(name__in=listed).delete()
    kept = {source.name: source for source in account.sources.all()}
    for name, (kind, delimiter) in listed.items():
        source = kept.get(name)
        if source is None or (source.kind, source.delimiter) != (kind, delimiter):
            path = name.split(delimiter) if delimiter else [name]
            was = source and source.folder_id
            source = source or Source(account=account, name=name)
            source.kind, source.delimiter = kind, delimiter
            source.folder = taking.folder(account, kind, path)
            source.save()
            kept[name] = source
            if was and was != source.folder_id:
                Folder.objects.filter(pk=was, messages=None, children=None, sources=None).delete()
    return sorted(kept.values(), key=taking.first)


def _flags(found: dict) -> dict[str, bool]:
    flags = set(found[b"FLAGS"])
    return {field: flag in flags for field, flag in FLAGS.items()}


def _taken(client, source: Source, uids: list[int], fresh: bool = False) -> None:
    """Keeps the messages under the UIDs: those the user has already only as having arrived
    here too, and the others fetched whole, a few at a time."""
    heads = client.fetch(uids, ["FLAGS", "INTERNALDATE", "RFC822.SIZE", HEADERS])
    keys = {uid: taking.keyed(found.get(HEADED) or b"") for uid, found in heads.items()}
    messages, deleted = taking.known(source.account.owner_id, keys.values())
    wanted = []
    for uid in sorted(heads, reverse=True):
        if keys[uid] in messages:
            taking.arrived(source, messages[keys[uid]], uid=uid)
        elif keys[uid] not in deleted:
            wanted.append(uid)
    group, size = [], 0
    for uid in [*wanted, None]:
        if group and (uid is None or size + heads[uid][b"RFC822.SIZE"] > WHOLE):
            for found_uid, found in client.fetch(group, ["BODY.PEEK[]"]).items():
                head = heads[found_uid]
                when = imap.aware(head[b"INTERNALDATE"])
                taking.took(
                    source, found[b"BODY[]"], _flags(head), when, uid=found_uid, fresh=fresh
                )
            group, size = [], 0
        if uid is not None:
            group.append(uid)
            size += heads[uid][b"RFC822.SIZE"]


def _selected(client, source: Source) -> dict:
    """Selects the folder; one the server gives out again from nothing, or seen for the first
    time, is taken from its newest message down."""
    selected = client.select_folder(source.name, readonly=True)
    validity = selected[b"UIDVALIDITY"]
    if source.uidvalidity != validity:
        following = selected.get(b"UIDNEXT")
        top = following - 1 if following else max(imap.searched(client, "ALL"), default=0)
        source.uidvalidity, source.low, source.high = validity, top + 1, top
        source.save(update_fields=["uidvalidity", "low", "high"])
    return selected


@contextmanager
def _vanishing(client, source: Source):
    """Lets go of a folder another client removed after it was listed, as the next listing would.
    Servers word the refusal each their own way, so a refusal without RFC 5530's NONEXISTENT is
    checked against a listing, which may still show the folder while its removal finishes."""
    try:
        yield
    except IMAPClientAbortError:
        raise
    except IMAPClientError as error:
        if "[NONEXISTENT]" not in str(error) and client.folder_exists(source.name):
            raise
        source.delete()


def caught_up(client, source: Source) -> None:
    """Takes the folder's new mail, oldest first, so that what is taken is always every UID up
    to `high`."""
    if not _selected(client, source)[b"EXISTS"]:
        return
    found = imap.searched(client, "UID", f"{source.high + 1}:*")
    for uids in batched(sorted(uid for uid in found if uid > source.high), HEADS, strict=False):
        _taken(client, source, list(uids), fresh=True)
        source.high = uids[-1]
        source.save(update_fields=["high"])


def older(client, source: Source) -> bool:
    """Takes some of what the folder held before it was first seen, newest first; whether it has
    more."""
    _selected(client, source)
    found = imap.searched(client, "UID", f"1:{source.low - 1}") if source.low > 1 else []
    found = sorted((uid for uid in found if uid < source.low), reverse=True)
    if uids := found[:HEADS]:
        _taken(client, source, uids)
    source.low = uids[-1] if len(found) > HEADS else 1
    source.save(update_fields=["low"])
    return source.low > 1


def _older(client, account: Account) -> bool:
    """Takes some older mail of the first folder that has any left; whether any folder does."""
    left = [source for source in sorted(account.sources.all(), key=taking.first) if source.low > 1]
    if not left:
        return False
    with _vanishing(client, left[0]):
        return older(client, left[0]) or len(left) > 1
    return len(left) > 1


def everything(client, account: Account) -> None:
    for source in sources(client, account):
        with _vanishing(client, source):
            caught_up(client, source)
    Account.objects.filter(pk=account.pk).update(
        state=Account.State.READY, error="", synced_at=timezone.now()
    )


def _inbox_changed(client, inbox: Source, stop: threading.Event) -> bool:
    """Waits in IDLE on INBOX until the server says it changed (true), LOOK passes or the
    account stops following (false)."""
    following = _selected(client, inbox).get(b"UIDNEXT")
    # IDLE tells only of what comes after it: mail that came while the rest was being taken,
    # announced to the commands before, would otherwise wait for LOOK.
    if (following is None or following > inbox.high + 1) and any(
        uid > inbox.high for uid in imap.searched(client, "UID", f"{inbox.high + 1}:*")
    ):
        return True
    client.idle()
    try:
        until = monotonic() + LOOK.total_seconds()
        while not stop.is_set() and monotonic() < until:
            said = client.idle_check(timeout=STEP)
            if any(len(each) > 1 and each[1] in CHANGES for each in said):
                return True
        return False
    finally:
        client.idle_done()


def _imap(account: Account, stop: threading.Event) -> None:
    """Follows the account on one connection until it stops, or until the access token it signed
    in with is about to end: everything new once, then INBOX at once and the rest each LOOK, with
    the older mail in between."""
    login, ends = signin.login(account)
    server = (account.imap_host, account.imap_port, account.imap_security)
    with imap.imap(*server, login) as client:
        everything(client, account)
        while not stop.is_set() and (ends is None or time() < ends):
            if _older(client, account):
                caught_up(client, account.sources.get(kind=Source.Kind.INBOX))
                continue
            inbox = account.sources.get(kind=Source.Kind.INBOX)
            # IDLE lasts up to LOOK: the pooled connection goes back for the requests meanwhile.
            connection.close()
            if _inbox_changed(client, inbox, stop):
                caught_up(client, inbox)
            elif not stop.is_set():
                everything(client, account)


def keep(account_id: int, stop: threading.Event) -> None:
    """Follows the account by its protocol until it stops."""
    try:
        account = Account.objects.get(pk=account_id)
        if account.protocol == Account.Protocol.ACTIVESYNC:
            activesync.keep(account, signin.password(account), stop)
        else:
            while not stop.is_set():
                try:
                    _imap(account, stop)
                except imap.Failed as refused:
                    if refused.code == REFUSED_TOKEN:
                        signin.forget(account)
                    raise
    except Account.DoesNotExist, Source.DoesNotExist:
        raise Gone from None
    finally:
        connection.close()


def failed(account_id: int, code: str) -> None:
    Account.objects.filter(pk=account_id).update(state=Account.State.FAILED, error=code)


def _stops(code: str) -> bool:
    return code in STOPPED or (code.endswith("_login") and code != REFUSED_TOKEN)


def followed() -> set[int]:
    """The accounts to follow: all but those whose server refused their sign-in or wiped them,
    until the user gives the sign-in again."""
    stopped = (Q(error__in=STOPPED) | Q(error__endswith="_login")) & ~Q(error=REFUSED_TOKEN)
    return set(
        Account.objects.exclude(stopped, state=Account.State.FAILED).values_list("pk", flat=True)
    )


async def follow(account_id: int, lines: CapacityLimiter) -> None:
    """Keeps the account followed through lost connections; returns only once it is gone or its
    server refuses its sign-in."""
    wait = RETRY
    while True:
        stop = threading.Event()
        started = monotonic()
        try:
            await to_thread.run_sync(
                partial(keep, account_id, stop), abandon_on_cancel=True, limiter=lines
            )
        except Gone:
            return
        except imap.Failed as refused:
            code = refused.code
        except (OSError, IMAPClientError) as lost:
            log.warning("mail: account %s lost its connection: %s", account_id, lost)
            code = "imap_unreachable"
        except Exception:
            log.exception("mail: following account %s failed", account_id)
            code = "unexpected"
        else:
            return
        finally:
            stop.set()
        # Raised here it would end every account's loop, and the backend's other loops with them.
        try:
            await database(failed)(account_id, code)
        except Exception:
            log.exception("mail: account %s could not be marked %s", account_id, code)
        if _stops(code):
            return
        if monotonic() - started > LONGEST.total_seconds():
            wait = RETRY
        await sleep(wait.total_seconds())
        wait = min(wait * 2, LONGEST)


async def mail() -> None:
    """Starts following each account as it is connected, and stops as it is removed."""
    # One thread for each account, waiting in IDLE: they must not take the threads every other
    # call into the database shares.
    lines = CapacityLimiter(10_000)
    following: dict[int, CancelScope] = {}

    async with create_task_group() as group:

        async def run(account_id: int, scope: CancelScope) -> None:
            with scope:
                await follow(account_id, lines)
            following.pop(account_id, None)

        async def step() -> bool:
            wanted = await database(followed)()
            for account_id in set(following) - wanted:
                following.pop(account_id).cancel()
            for account_id in wanted - set(following):
                following[account_id] = CancelScope()
                group.start_soon(run, account_id, following[account_id])
            return False

        await drain(CHANNEL, step, SWEEP, log)
