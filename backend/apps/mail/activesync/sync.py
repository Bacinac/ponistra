"""An ActiveSync account's new mail taken while the backend runs: each folder's messages once,
then each folder's new ones as soon as Ping says it changed. A message comes whole, as its MIME;
what the server says changed about it later is not taken."""

import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from django.db import connection, transaction
from django.utils import timezone

from apps.calendar import activesync as calendars
from apps.calendar import notes
from apps.contacts import activesync as contacts

from .. import taking
from ..imap import Failed
from ..models import Account, Message, Source
from . import directory
from .client import Interrupted, Session, Wiped
from .wbxml import Element
from .wbxml import element as e

# Each message comes whole, attachments and all.
WINDOW = 25
# How long the server holds a Ping open; MS-ASCMD lets it ask for another within its limits.
HEARTBEAT = 480
# MS-ASCMD 2.2.3.186.3: the folder types holding mail, with the kind each is here.
KINDS = {
    "2": Source.Kind.INBOX,
    "3": Source.Kind.DRAFTS,
    "4": Source.Kind.TRASH,
    "5": Source.Kind.SENT,
    "12": "",
}
OPTIONS = e(
    "AirSync:Options",
    e("AirSync:FilterType", "0"),
    e("AirSyncBase:BodyPreference", e("AirSyncBase:Type", "4")),
    e("AirSync:MIMESupport", "2"),
)

_locks: dict[int, threading.Lock] = {}
_guard = threading.Lock()


@contextmanager
def syncing(account_id: int):
    """One Sync at a time for the account: each takes the folder's key the last one left."""
    with _guard:
        lock = _locks.setdefault(account_id, threading.Lock())
    with lock:
        yield


def session(account: Account, password: str) -> Session:
    def remember(key: str) -> None:
        Account.objects.filter(pk=account.pk).update(policy_key=key)

    return Session(
        account.activesync_host,
        account.username,
        password,
        account.device,
        account.policy_key,
        remember,
    )


def _paths(folders: dict[str, dict]) -> dict[str, list[str]]:
    """Each folder's path, its parents' names before its own; a path two folders share is told
    apart by a number."""

    def path(server_id: str, seen: frozenset = frozenset()) -> list[str]:
        found = folders[server_id]
        parent = found["parent"]
        if parent in folders and parent not in seen:
            return [*path(parent, seen | {server_id}), found["name"]]
        return [found["name"]]

    paths, taken = {}, set()
    for server_id in folders:
        found, number = path(server_id), 1
        while "/".join(found).casefold() in taken:
            number += 1
            found = [*path(server_id)[:-1], f"{path(server_id)[-1]} ({number})"]
        paths[server_id] = found
        taken.add("/".join(found).casefold())
    return paths


@transaction.atomic
def _hierarchy(account: Account, key: str, changes: Element | None) -> None:
    stored = {source.server_id: source for source in account.sources.all()}
    known = {}
    for server_id, source in stored.items():
        parent = stored.get(source.parent)
        inside = parent is not None and source.name.startswith(f"{parent.name}/")
        known[server_id] = {
            "parent": source.parent,
            "name": source.name[len(parent.name) + 1 :] if inside else source.name,
            "kind": source.kind,
        }
    for change in changes or ():
        server_id = change.text("ServerId")
        if change.name in ("Add", "Update") and change.text("Type") in KINDS:
            known[server_id] = {
                "parent": change.text("ParentId"),
                "name": change.text("DisplayName"),
                "kind": KINDS[change.text("Type")],
            }
        elif change.name in ("Add", "Update", "Delete"):
            known.pop(server_id, None)
    account.sources.exclude(server_id__in=known).delete()
    for server_id, path in _paths(known).items():
        given = known[server_id]
        source = stored.get(server_id) or Source(account=account, server_id=server_id)
        name = "/".join(path)
        if source.pk is None or (source.name, source.parent, source.kind) != (
            name,
            given["parent"],
            given["kind"],
        ):
            source.name, source.parent, source.kind = name, given["parent"], given["kind"]
            source.delimiter = "/"
            source.folder = taking.folder(account, given["kind"], path)
            source.save()
    contacts.held(account, changes, whole=not account.folder_key)
    calendars.held(account, changes, whole=not account.folder_key)
    Account.objects.filter(pk=account.pk).update(folder_key=key)
    account.folder_key = key


def hierarchy(client: Session, account: Account) -> None:
    """The account's mail folders as the server has them now."""
    answer = client.command(
        "FolderSync",
        e("FolderHierarchy:FolderSync", e("FolderHierarchy:SyncKey", account.folder_key or "0")),
    )
    status = answer.text("Status")
    if status == "9" and account.folder_key:
        # The server no longer knows the key: every folder is taken again from nothing, and what
        # the user has already is not taken twice.
        with transaction.atomic():
            account.sources.all().delete()
            Account.objects.filter(pk=account.pk).update(folder_key="")
        account.folder_key = ""
        return hierarchy(client, account)
    if status != "1":
        raise Failed("activesync_unreachable")
    _hierarchy(account, answer.text("SyncKey"), answer.find("Changes"))


def _moment(raw: str) -> datetime:
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return timezone.now()
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _flags(data: Element) -> dict[str, bool]:
    flag = data.find("Flag")
    return {
        "seen": data.text("Read") == "1",
        "flagged": flag is not None and flag.text("Status") == "2",
        "answered": data.text("LastVerbExecuted") in ("1", "2"),
    }


def _applied(
    client: Session, source: Source, key: str, commands: Element | None, fresh: bool
) -> None:
    named = directory.named(client, source.account.activesync_host)
    for command in commands or ():
        data = command.find("ApplicationData")
        mime = data.find("Body/Data") if command.name == "Add" and data is not None else None
        if mime is None or not isinstance(mime.value, bytes):
            continue
        when = _moment(data.text("DateReceived"))
        item = command.text("ServerId")
        taking.took(source, mime.value, _flags(data), when, item=item, named=named, fresh=fresh)
    Source.objects.filter(pk=source.pk).update(sync_key=key)
    source.sync_key = key


def _sync(source: Source, key: str, *more: Element) -> Element:
    return e(
        "AirSync:Sync",
        e(
            "AirSync:Collections",
            e(
                "AirSync:Collection",
                e("AirSync:SyncKey", key),
                e("AirSync:CollectionId", source.server_id),
                *more,
            ),
        ),
    )


def caught_up(client: Session, source: Source) -> None:
    """Takes every message the server has new in the folder."""
    while True:
        with syncing(source.account_id):
            source.refresh_from_db(fields=["sync_key"])
            # The first sync of a folder brings what it held; each later one, what arrived.
            fresh = bool(source.sync_key)
            if not source.sync_key:
                more = ()
            else:
                window = e("AirSync:WindowSize", str(WINDOW))
                more = (e("AirSync:GetChanges", "1"), window, OPTIONS)
            answer = client.command("Sync", _sync(source, source.sync_key or "0", *more))
            collection = answer.find("Collections/Collection")
            if collection is None:
                return
            status = collection.text("Status")
            if status == "3":
                # The server no longer knows the key: the folder is taken again from nothing, and
                # what the user has already is not taken twice.
                Source.objects.filter(pk=source.pk).update(sync_key="")
                continue
            if status != "1":
                raise Failed("activesync_unreachable")
            _applied(client, source, collection.text("SyncKey"), collection.find("Commands"), fresh)
            if more and collection.find("MoreAvailable") is None:
                return


def everything(client: Session, account: Account) -> None:
    hierarchy(client, account)
    for source in sorted(account.sources.all(), key=taking.first):
        caught_up(client, source)
    for book in account.contact_books.all():
        contacts.caught_up(client, book)
    for feed in account.calendar_feeds.all():
        calendars.caught_up(client, feed)
    notes.followed(client.host, client.username, client.password, account)
    directory.again(client, account)
    Account.objects.filter(pk=account.pk).update(
        state=Account.State.READY, error="", synced_at=timezone.now()
    )


def pinged(client: Session, account: Account, heartbeat: int, most: int) -> Element:
    """Waits until the server says which of the account's folders (the first `most`, INBOX
    first, its contacts and calendars last) changed, or the heartbeat passes."""
    sources = sorted(account.sources.all(), key=lambda each: each.kind != Source.Kind.INBOX)
    watched = (
        [
            e("Ping:Folder", e("Ping:Id", source.server_id), e("Ping:Class", "Email"))
            for source in sources
        ]
        + [
            e("Ping:Folder", e("Ping:Id", book.server_id), e("Ping:Class", "Contacts"))
            for book in account.contact_books.all()
        ]
        + [
            e("Ping:Folder", e("Ping:Id", feed.server_id), e("Ping:Class", "Calendar"))
            for feed in account.calendar_feeds.all()
        ]
    )
    watched = watched[:most]
    # The server holds a Ping up to the heartbeat: the pooled connection goes back meanwhile.
    connection.close()
    return client.command(
        "Ping",
        e("Ping:Ping", e("Ping:HeartbeatInterval", str(heartbeat)), e("Ping:Folders", *watched)),
        timeout=heartbeat + 60,
    )


def keep(account: Account, password: str, stop: threading.Event) -> None:
    """Follows the account until it stops: every folder once, then each as it changes."""
    try:
        with session(account, password) as client:
            everything(client, account)
            heartbeat = HEARTBEAT
            most = (
                len(account.sources.all())
                + len(account.contact_books.all())
                + len(account.calendar_feeds.all())
            )
            while not stop.is_set():
                try:
                    answer = pinged(client, account, heartbeat, most)
                except Interrupted:
                    continue
                status = answer.text("Status")
                # MS-ASCMD 2.2.3.177.11: 1 nothing changed, 2 these folders did, 5 and 6 the
                # heartbeat or the folders beyond what the server allows, 7 the folder list.
                if status == "2":
                    changed = [each.string for each in answer.findall("Folders/Folder")]
                    for source in account.sources.filter(server_id__in=changed):
                        caught_up(client, source)
                    for book in account.contact_books.filter(server_id__in=changed):
                        contacts.caught_up(client, book)
                    for feed in account.calendar_feeds.filter(server_id__in=changed):
                        calendars.caught_up(client, feed)
                    notes.followed(client.host, client.username, client.password, account)
                elif status == "5":
                    heartbeat = int(answer.text("HeartbeatInterval") or heartbeat)
                elif status == "6":
                    most = int(answer.text("MaxFolders") or most)
                elif status == "7":
                    everything(client, account)
                elif status != "1":
                    raise Failed("activesync_unreachable")
    except Wiped:
        # The company's administrator wants its mail off the device: what came through it goes.
        with transaction.atomic():
            account.sources.all().delete()
            Message.objects.filter(account=account).delete()
            contacts.wiped(account)
            calendars.wiped(account)
        raise Failed("activesync_wiped") from None
