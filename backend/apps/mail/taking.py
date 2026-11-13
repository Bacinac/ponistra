"""A message as the provider gives it, taken whole into what PONISTRA keeps of the user's mail
(D15, "the mail is ours"): its envelope, flags and text in Postgres, its bytes and files in the
blob store, in the folder of the user's tree its provider folder maps to."""

import io
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import Message as Parsed
from email.utils import getaddresses, parsedate_to_datetime
from hashlib import sha256
from itertools import batched, chain

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.blobs import store
from apps.push import notices as push
from apps.push.models import Notice
from apps.search import extraction

from . import absence, automatic, correspondents, imap, mime, reactions, sealing, sorting
from .mime import header
from .models import (
    Account,
    Arrival,
    Attachment,
    Deleted,
    Folder,
    Message,
    Priority,
    Role,
    Source,
)

# A person as Traveler writes one inside a Domino organisation: the common name, the units of
# the organisation after it, and the Notes domain, which has no dot, where the mail goes on to
# another.
NOTES = re.compile(
    r"(?:CN=)?([^/@<>\",]+)(?:/(?:[A-Z]{1,2}=)?[^/@<>\",]+)+(?:@[^/@<>\",\s.]+)?", re.I
)

# Where a message names its people.
PEOPLE = {"sender": "From", "to": "To", "cc": "Cc", "reply_to": "Reply-To"}
# Told of each message kept, with the files it carries, by whoever asked (the calendar, of the
# calendar part a message may carry).
ARRIVED: list[Callable[[Message, list[tuple[dict, bytes]]], None]] = []

# Copies of one message that no Message-ID ties together bear the moment each was posted or
# filed, seconds apart (Domino dates the sent copy a second after the delivered one); a large
# upload takes longer.
WINDOW = timedelta(minutes=2)
UNKEYED = ~Q(message_id__contains="@")
EVERY = Q()

# The order an account's folders are taken in: a message in several of them, as Gmail's labels
# put it, stays in the first.
FIRST = [
    Source.Kind.TRASH,
    Source.Kind.JUNK,
    Source.Kind.INBOX,
    Source.Kind.SENT,
    Source.Kind.DRAFTS,
    "",
    Source.Kind.ARCHIVE,
    Source.Kind.ALL,
]


def first(source: Source) -> tuple[int, str]:
    return FIRST.index(source.kind), source.name


def _people(value: str) -> list[dict]:
    return [
        {"name": imap.words(each), "address": address}
        for each, address in getaddresses([value])
        if "@" in address
    ]


def addresses(message: Parsed, name: str) -> list[dict]:
    value = header(message, name)
    if "<" in value or '"' in value:
        return _people(value)
    found = []
    for each in filter(None, (piece.strip() for piece in value.split(","))):
        if notes := NOTES.fullmatch(each):
            found.append({"name": notes[1].strip(), "address": each})
        elif "@" in each or each.endswith(";"):
            found += _people(each)
        else:
            # A server names itself so, as Domino's "Mail Router" does: no one to answer.
            found.append({"name": imap.words(each), "address": ""})
    return found


def priority(message: Parsed) -> Priority:
    """How important the sender marked the message. Traveler, whose messages carry X-IBM-UNID,
    writes Domino's own scale into X-Priority: 1 high, 2 normal, 3 low."""
    given = header(message, "X-Priority").strip()[:1]
    if given in ("1", "2", "3", "4", "5"):
        if message.get("X-IBM-UNID"):
            return {"1": Priority.HIGH, "3": Priority.LOW}.get(given, Priority.NORMAL)
        return Priority.HIGH if given < "3" else Priority.LOW if given > "3" else Priority.NORMAL
    for name in ("Importance", "Priority", "X-MSMail-Priority"):
        word = header(message, name).strip().lower()
        if word in ("high", "urgent"):
            return Priority.HIGH
        if word in ("low", "non-urgent"):
            return Priority.LOW
    return Priority.NORMAL


def key(message: Parsed) -> str | None:
    """The message's key where it has a Message-ID: the same wherever it is delivered."""
    # Exchange Online gives what it sends a Message-ID of its own and keeps the writer's in this
    # header, so the copy in Sent is the message PONISTRA kept on sending.
    message_id = header(message, "X-Microsoft-Original-Message-ID") or header(message, "Message-ID")
    if not message_id:
        return None
    return sha256(f"{message_id}\n{header(message, 'Subject')}".encode()).hexdigest()


def keyed(headers: bytes) -> str | None:
    """The key of a message by its Message-ID and Subject headers alone."""
    return key(mime.parsed(headers))


def node(account: Account) -> Folder:
    """The folder the account's own folders are under; an account connected again finds the one
    its mail stayed in."""
    if found := Folder.objects.filter(account=account).first():
        return found
    found, _ = Folder.objects.get_or_create(
        owner_id=account.owner_id, parent=None, name=account.address, role=""
    )
    if found.account_id is None:
        found.account = account
        found.save(update_fields=["account"])
    return found


def folder(account: Account, kind: str, path: list[str]) -> Folder:
    """The folder of the user's tree that a provider folder of the kind, at the path, maps to."""
    role = Role.ARCHIVE if kind == Source.Kind.ALL else kind
    if role:
        return Folder.objects.get_or_create(
            owner_id=account.owner_id, role=role, defaults={"name": role}
        )[0]
    # Some servers keep every folder inside INBOX.
    if len(path) > 1 and path[0].upper() == "INBOX":
        path = path[1:]
    found = node(account)
    for name in path:
        found = Folder.objects.get_or_create(
            owner_id=account.owner_id, parent=found, name=name[:1000]
        )[0]
    return found


def pruned(folder: Folder) -> bool:
    """Deletes what of the folder and the folders inside it holds no mail; whether the folder
    itself went."""
    kept = [child for child in folder.children.all() if not pruned(child)]
    if kept or folder.messages.exists():
        return False
    folder.delete()
    return True


def known(owner_id: int, keys) -> tuple[dict[str, int], set[str]]:
    """Of the keys, the user's messages by key, and those the user deleted."""
    keys = [each for each in keys if each]
    messages = dict(
        Message.objects.filter(owner_id=owner_id, key__in=keys).values_list("key", "pk")
    )
    deleted = set(
        Deleted.objects.filter(owner_id=owner_id, key__in=keys).values_list("key", flat=True)
    )
    return messages, deleted


def arrived(source: Source, message_id: int, uid: int | None = None, item: str = "") -> None:
    Arrival.objects.bulk_create(
        [Arrival(message_id=message_id, source=source, uid=uid, item=item)],
        ignore_conflicts=True,
    )


def _text(message: Parsed, described: dict) -> str:
    shown = described.get("plain") or described.get("html")
    if shown is None:
        return ""
    data = mime.raw(message, shown["part"]) or b""
    text = imap.decoded(data, shown["encoding"], shown["charset"])
    return (text if "plain" in described else imap.plain(text))[: imap.TEXT]


def _date(message: Parsed, when: datetime | None) -> datetime:
    try:
        found = parsedate_to_datetime(header(message, "Date"))
    except TypeError, ValueError, IndexError:
        found = None
    return imap.aware(found) or when or timezone.now()


def real(message_id: str) -> bool:
    """Whether a Message-ID is one. HCL Traveler gives its own item ids, `4:8870020`, which
    differ between the copies of a message."""
    return "@" in message_id


def common(address: str) -> str | None:
    """The common name of a person Traveler names as Domino does, or None for an address."""
    found = NOTES.fullmatch(address)
    return found[1].strip() if found else None


def fingerprint(
    sender: str, subject: str, text: str, people: Iterable[dict], files: Iterable[str]
) -> str:
    """What a message is made of, the same in each copy of it however its provider renders it:
    the addresses of its sender and of the people it went to, the subject and text with their
    spacing evened out, and the hashes of the files it carries."""
    to = sorted({each["address"].casefold() for each in people if each.get("address")})
    made = [sender.casefold(), " ".join(subject.split()), " ".join(text.split()), *to]
    return sha256("\n".join([*made, *sorted(files)]).encode()).hexdigest()


def fingerprinted(message: Message) -> str:
    files = (each.blob_id for each in message.files.all() if not each.inline)
    sender = message.sender.get("address", "")
    people = [*message.to, *message.cc]
    return fingerprint(sender, message.subject, message.text, people, files)


def same(message_id: str, key: str, made: str, date: datetime, unkeyed: Q, apart: Q = EVERY) -> Q:
    """The rows that are the message: by its key, or by what it is made of around its moment
    where it, or the row (`unkeyed`), has no Message-ID to know it by and is `apart`."""
    alike = Q(fingerprint=made, date__range=(date - WINDOW, date + WINDOW)) & apart
    return Q(key=key) | (alike if not real(message_id) else alike & unkeyed)


@dataclass
class _Taken:
    """A message read from its bytes, before anything of it is kept."""

    raw: bytes
    message: Parsed
    described: dict
    kept: bytes
    cuts: dict[str, dict]
    files: list[tuple[dict, bytes]]
    people: dict[str, list[dict]]
    text: str
    date: datetime
    key: str
    fingerprint: str
    reaction: str
    reacts_to: str
    sealed: str

    @property
    def message_id(self) -> str:
        return header(self.message, "Message-ID")[:998]

    @property
    def sender(self) -> str:
        return self.people["sender"][0]["address"] if self.people["sender"] else ""

    def same(self, unkeyed: Q, apart: Q = EVERY) -> Q:
        return same(self.message_id, self.key, self.fingerprint, self.date, unkeyed, apart)


def _taken(raw: bytes, when: datetime | None, named: Callable[[str], str] | None) -> _Taken:
    """`named` gives the address of a person Traveler names as Domino does, if it can."""
    message = mime.parsed(raw)
    described = mime.described(message)
    files = [*described["inline"], *described["attachments"]]
    kept, cuts = mime.cut(raw, message, {each["part"] for each in files})
    data = [
        (
            each,
            cut["data"]
            if (cut := cuts.get(each["part"]))
            else imap.content(mime.raw(message, each["part"]) or b"", each["encoding"]),
        )
        for each in files
    ]
    people = {field: addresses(message, name) for field, name in PEOPLE.items()}
    for each in chain.from_iterable(people.values()) if named else ():
        if common(each["address"]) and (found := named(each["address"])):
            each["address"] = found
    text = _text(message, described)
    inline = {each["part"] for each in described["inline"]}
    sender = people["sender"][0]["address"] if people["sender"] else ""
    hashes = (sha256(given).hexdigest() for each, given in data if each["part"] not in inline)
    reaction, reacts_to = reactions.of(message, described)
    return _Taken(
        raw=raw,
        message=message,
        described=described,
        kept=kept,
        cuts=cuts,
        files=data,
        people=people,
        text=text,
        date=_date(message, when),
        key=key(message) or sha256(raw).hexdigest(),
        fingerprint=fingerprint(
            sender, header(message, "Subject"), text, [*people["to"], *people["cc"]], hashes
        ),
        reaction=reaction,
        reacts_to=reacts_to,
        sealed=sealing.sealed_state(raw, message),
    )


def _kept(account: Account, folder: Folder, taken: _Taken, flags: dict) -> Message:
    message, people = taken.message, taken.people
    answered = header(message, "In-Reply-To")[:998]
    if taken.reaction:
        # Seen as the message it reacts to shows it, it is no news of its own.
        answered, flags = taken.reacts_to, flags | {"seen": True}
    made = Message.objects.create(
        owner_id=account.owner_id,
        folder=folder,
        account=account,
        key=taken.key,
        raw=store.put(io.BytesIO(taken.kept)),
        message_id=taken.message_id,
        in_reply_to=answered,
        references=imap.references(header(message, "References")),
        subject=header(message, "Subject"),
        sender=people["sender"][0] if people["sender"] else {},
        to=people["to"],
        cc=people["cc"],
        reply_to=people["reply_to"],
        priority=priority(message),
        date=taken.date,
        size=len(taken.raw),
        attachments=bool(taken.described["attachments"]),
        sealed=taken.sealed,
        text=taken.text,
        preview=imap.preview(taken.text),
        fingerprint=taken.fingerprint,
        automatic=automatic.by_program(message, taken.sender),
        reaction=taken.reaction,
        reacts_to=reactions.target(account.owner_id, answered) if taken.reaction else None,
        **flags,
    )
    reactions.attach(made)
    inline = {each["part"] for each in taken.described["inline"]}
    attachments = []
    for each, data in taken.files:
        cut = taken.cuts.get(each["part"])
        attachments.append(
            Attachment(
                message=made,
                blob=store.put(io.BytesIO(data)),
                part=each["part"],
                name=each.get("name", "")[:255],
                type=each["type"][:255],
                cid=each["cid"][:998],
                inline=each["part"] in inline,
                offset=cut and cut["offset"],
                line=cut and cut["line"],
                newline=cut["newline"] if cut else "",
                ended=bool(cut and cut["ended"]),
            )
        )
    Attachment.objects.bulk_create(attachments)
    if any(not each.inline and each.blob.media_type == store.PDF for each in attachments):
        extraction.wake()
    correspondents.kept(made, folder.role)
    for told in ARRIVED:
        told(made, taken.files)
    return made


def _once(
    account: Account, folder: Folder, taken: _Taken, flags: dict, source: Source | None = None
) -> tuple[Message, bool]:
    """The message, and whether it was kept now rather than found: in the folder the user's rules
    send its sender's mail to, if any."""
    owned = Message.objects.filter(owner_id=account.owner_id)
    # Two items of one provider folder are two messages, however alike.
    apart = ~Exists(Arrival.objects.filter(message=OuterRef("pk"), source=source))
    with transaction.atomic():
        if found := owned.filter(taken.same(UNKEYED, apart)).order_by("pk").first():
            return found, False
        try:
            with transaction.atomic():
                kept = sorting.arriving(account.owner_id, taken.sender, folder)
                return _kept(account, kept, taken, flags), True
        except IntegrityError:
            # Delivered to another of the user's accounts, and taken from it meanwhile.
            return owned.get(key=taken.key), False


def announced(message: Message) -> None:
    """Reaches the user's browsers with a message that just came unread into their inbox."""
    push.tell(
        [message.owner_id],
        Notice.Kind.MAIL,
        {
            "name": message.sender.get("name", ""),
            "address": message.sender.get("address", ""),
            "subject": message.subject,
            "folder": message.folder_id,
            "message": message.pk,
        },
        tag=push.topic("mail", message.pk),
    )


def took(
    source: Source,
    raw: bytes,
    flags: dict[str, bool],
    when: datetime | None = None,
    uid: int | None = None,
    item: str = "",
    named: Callable[[str], str] | None = None,
    fresh: bool = False,
) -> Message | None:
    """Keeps the message the provider folder gives, unless the user has it already or deleted
    it; the message it is, if kept. One `fresh` to the provider, kept now, unread and in the
    inbox, reaches the user's browsers."""
    account = source.account
    taken = _taken(raw, when, named)
    deleted = Deleted.objects.filter(owner_id=account.owner_id)
    if deleted.filter(taken.same(Q(keyed=False))).exists():
        return None
    with transaction.atomic():
        found, kept = _once(account, source.folder, taken, flags, source)
        arrived(source, found.pk, uid, item)
        if fresh and kept and not found.seen and found.folder.role == Role.INBOX:
            announced(found)
            absence.noted(found, taken.message)
    return found


def sent(account: Account, raw: bytes) -> Message:
    """Keeps what the user sent in their Sent folder; the provider's copy, once taken, is the
    same message."""
    folder = Folder.objects.get_or_create(
        owner_id=account.owner_id, role=Role.SENT, defaults={"name": Role.SENT}
    )[0]
    return _once(account, folder, _taken(raw, timezone.now(), None), {"seen": True})[0]


def renamed(owner_id: int, found: dict[str, str]) -> int:
    """Writes the addresses the directory gave for Domino names into the user's mail that names
    those people so, and what each message is made of again; how many messages changed."""
    changed, before = {}, {}
    mine = correspondents.own(owner_id)
    for names in batched(found, 50, strict=False):
        named = Q()
        for name in names:
            within = [{"address": name}]
            named |= Q(sender__address=name) | Q(to__contains=within)
            named |= Q(cc__contains=within) | Q(reply_to__contains=within)
        mail = Message.objects.filter(owner_id=owner_id).filter(named).exclude(pk__in=changed)
        for message in mail.select_related("folder").prefetch_related("files"):
            before[message.pk] = correspondents.of(message, mine, message.folder.role)
            for each in [message.sender, *message.to, *message.cc, *message.reply_to]:
                if each.get("address") in found:
                    each["address"] = found[each["address"]]
            message.fingerprint = fingerprinted(message)
            changed[message.pk] = message
    fields = ["sender", "to", "cc", "reply_to", "fingerprint"]
    for chunk in batched(changed.values(), 500, strict=False):
        Message.objects.bulk_update(chunk, fields)
    correspondents.counted(changed.values(), mine, before)
    return len(changed)


def whole(message: Message) -> bytes:
    """The message as it came, its files put back where they were cut from."""
    kept = store.path_of(message.raw_id).read_bytes()
    cuts = [
        (
            each.offset,
            store.path_of(each.blob_id).read_bytes(),
            each.line,
            each.newline.encode(),
            each.ended,
        )
        for each in message.files.exclude(offset=None)
    ]
    return mime.whole(kept, cuts)
