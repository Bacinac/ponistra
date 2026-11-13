"""Moving the mail of one account into another at its provider (S3-8), as a firm leaving
Microsoft 365 takes its mail along: each message the account brought, as it came, into the same
place in the other mailbox, by IMAP APPEND, with its read, flag and answered marks and its date.
What the account's own folders hold goes into the same folders of the other account, made where
it has none, and in PONISTRA too; the shared folders (Inbox, Sent, Archive) and the user's own
keep their mail where it is. Trash, Junk and Drafts stay behind. A moved message belongs to the
other account from then on, which is how a move cut off goes on where it stopped."""

from contextlib import ExitStack
from time import time

from django.db.models import Exists, OuterRef
from imapclient.exceptions import IMAPClientError

from apps.core.api import Refused

from . import imap, signin, taking
from .models import Account, Arrival, Folder, Message, Role, Source

LEFT_BEHIND = (Role.TRASH, Role.JUNK, Role.DRAFTS)
# The provider folders the shared folders go into, by the kinds they may be listed as.
KINDS = {
    Role.INBOX: (Source.Kind.INBOX,),
    Role.SNOOZED: (Source.Kind.INBOX,),
    Role.SENT: (Source.Kind.SENT,),
    Role.ARCHIVE: (Source.Kind.ARCHIVE, Source.Kind.ALL),
}
MADE = {Role.SENT: "Sent", Role.ARCHIVE: "Archive"}
FLAGS = (("seen", b"\\Seen"), ("flagged", b"\\Flagged"), ("answered", b"\\Answered"))


def moving(owner, given: dict) -> tuple[Account, Account]:
    """The account mail moves from and the one it moves to, both the owner's: any kind from, as
    PONISTRA keeps what it brought whole, and into one reached over IMAP."""
    found = {}
    for name in ("from", "to"):
        pk = given.get(name)
        account = owner.mail_accounts.filter(pk=pk).first() if type(pk) is int else None
        if account is None:
            raise Refused(404, "not_found")
        found[name] = account
    if found["from"] == found["to"] or found["to"].protocol != Account.Protocol.IMAP:
        raise Refused(400, "invalid_to")
    return found["from"], found["to"]


def left(source: Account, into: Account):
    """The messages the account brought that are still to move: but those the other account has
    at its provider already, and those left behind."""
    there = Arrival.objects.filter(message=OuterRef("pk"), source__account=into)
    return (
        Message.objects.filter(owner_id=source.owner_id, account=source)
        .exclude(folder__role__in=LEFT_BEHIND)
        .exclude(Exists(there))
    )


class _Places:
    """Where each message goes: the provider folder of the other account, made the first time,
    and the folder of PONISTRA's tree it is kept in from then on."""

    def __init__(self, client, source: Account, into: Account):
        self.client, self.source, self.into = client, source, into
        self.folders = {each.pk: each for each in Folder.objects.filter(owner_id=into.owner_id)}
        self.node = Folder.objects.filter(account=source).values_list("pk", flat=True).first()
        listed = client.list_folders()
        self.delimiter = next((each[1] for each in listed if each[1]), b"/").decode()
        self.names = {name for _, _, name in listed}
        self.found: dict[int, tuple[str, Folder]] = {}

    def _path(self, folder: Folder) -> tuple[list[str], bool]:
        """The names from the top of the tree down to the folder, and whether it is under the
        account's own node, which the path then starts below."""
        names: list[str] = []
        while folder is not None:
            if folder.pk == self.node:
                return names, True
            names.insert(0, folder.name)
            folder = self.folders.get(folder.parent_id)
        return names, False

    def _made(self, name: str) -> str:
        if name not in self.names:
            self.client.create_folder(name)
            self.names.add(name)
        return name

    def _shared(self, role: str) -> str:
        kinds = KINDS[role]
        named = self.into.sources.filter(kind__in=kinds).values_list("name", flat=True).first()
        return named or self._made(MADE[role])

    def of(self, folder: Folder) -> tuple[str, Folder]:
        if folder.pk not in self.found:
            if folder.role:
                self.found[folder.pk] = (self._shared(folder.role), folder)
            else:
                path, own = self._path(folder)
                name = self._made(self.delimiter.join(path))
                kept = taking.folder(self.into, "", path) if own else folder
                self.found[folder.pk] = (name, kept)
        return self.found[folder.pk]


def _batches(source: Account, into: Account, size: int = 200):
    pending = left(source, into).select_related("folder").order_by("pk")
    last = 0
    while batch := list(pending.filter(pk__gt=last)[:size]):
        yield from batch
        last = batch[-1].pk


def moved(owner, parameters: dict) -> dict:
    """Moves what is left of the mail, connecting again as a token signed in with is about to
    end; how many messages moved."""
    source, into = moving(owner, parameters)
    server = (into.imap_host, into.imap_port, into.imap_security)
    count = 0
    try:
        with ExitStack() as connection:
            ends = None
            places = None
            for message in _batches(source, into):
                if places is None or (ends is not None and time() >= ends):
                    connection.close()
                    login, ends = signin.login(into)
                    client = connection.enter_context(imap.imap(*server, login))
                    places = _Places(client, source, into)
                name, kept = places.of(message.folder)
                flags = [flag for field, flag in FLAGS if getattr(message, field)]
                places.client.append(name, taking.whole(message), flags, message.date)
                Message.objects.filter(pk=message.pk).update(account=into, folder=kept)
                count += 1
    except imap.Failed as failed:
        if failed.code == "imap_oauth_login":
            signin.forget(into)
        raise Refused(502, failed.code) from None
    except IMAPClientError, OSError:
        raise Refused(502, "imap_failed") from None
    return {"moved": count}
