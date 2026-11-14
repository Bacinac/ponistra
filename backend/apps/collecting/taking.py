"""How a collection takes messages: it looks through the owner's mail for those it names, from
its first day on and then as they come, and reads each it took, by the model where the
collection recognises bills, putting the files it carries in its month's folder. A file its owner
puts in a month's folder is taken too, and joins the bill of the same amount it belongs to."""

import time
from datetime import date, timedelta
from functools import reduce
from logging import getLogger
from operator import or_

from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Q, QuerySet
from django.utils import timezone

from apps.actions import runs
from apps.actions.models import ActionRun
from apps.ai import model
from apps.ai.installation import Unavailable
from apps.blobs import previews, store
from apps.documents.models import Node
from apps.documents.views import created
from apps.imports.placed import named
from apps.mail import sorting
from apps.mail.models import Attachment, Message, Role
from apps.push import notices
from apps.push.models import Notice
from apps.search import extraction

from . import converting, months, recognising
from .models import Collection, Item

log = getLogger(__name__)

# Mail the user wrote, threw away or was spared is never a bill they received.
LEFT = (Role.SENT, Role.DRAFTS, Role.TRASH, Role.JUNK)
# How often a collection looks for new mail, how far back past its mark, as messages are not
# committed in the order they are numbered, and how many it takes at a look.
LOOK = 60.0
SLACK = 500
PAGE = 500
# How long a message waits for the text of its PDF files before it is read without it, and how
# long one the model could not read waits before it is tried again.
TEXT_WAIT = timedelta(minutes=30)
RETRY = timedelta(hours=1)
# A model's failure on one message, which leaves the others to go on.
PASSED = {"refused", "too_long", "too_many_steps", "no_answer"}
# How far apart a file's date and its bill's may be, as a receipt follows its invoice.
APART = timedelta(days=3)

_looked: dict[int, float] = {}


def forget(collection_id: int) -> None:
    """Has the collection look at once, as it was just made or changed."""
    _looked.pop(collection_id, None)


def named_by(collection: Collection) -> QuerySet[Message]:
    """The owner's messages the collection names that it has not taken yet."""
    found = Message.objects.filter(
        owner_id=collection.owner_id, date__gte=months.started(collection.since), reaction=""
    ).exclude(folder__role__in=LEFT)
    if collection.accounts:
        found = found.filter(account_id__in=collection.accounts)
    if collection.senders:
        found = found.filter(reduce(or_, (sorting.sent_by(each) for each in collection.senders)))
    if collection.words:
        found = found.filter(reduce(or_, (Q(subject__icontains=each) for each in collection.words)))
    if collection.attached:
        found = found.filter(attachments=True)
    return found.exclude(Exists(Item.objects.filter(collection=collection, message=OuterRef("pk"))))


def taken(collection: Collection, messages: list[Message], chosen: bool = False) -> int:
    """Takes the messages into their months; how many it took."""
    made = [
        Item(
            collection=collection,
            month=months.month_for(collection, message.date),
            message=message,
            chosen=chosen,
            subject=message.subject,
            sender=(message.sender or {}).get("address", "")[:320],
        )
        for message in messages
    ]
    Item.objects.bulk_create(made, ignore_conflicts=True)
    if made:
        months.touched(collection.pk)
    return len(made)


def look(collection: Collection) -> bool:
    """Takes the messages that came since the collection last looked, or from its first day at
    its first look; whether there may be more to take at once."""
    found = list(
        named_by(collection)
        .filter(pk__gt=max(collection.mark - SLACK, 0))
        .select_related("folder")
        .order_by("pk")[:PAGE]
    )
    with transaction.atomic():
        taken(collection, found)
        if len(found) == PAGE:
            mark = found[-1].pk
        else:
            mark = Message.objects.filter(owner_id=collection.owner_id).aggregate(top=Max("pk"))
            mark = mark["top"] or 0
        if mark != collection.mark:
            Collection.objects.filter(pk=collection.pk).update(mark=mark)
    return len(found) == PAGE


def filed(collection: Collection) -> int:
    """Takes the files its owner put in the folders of the collection's months, each once; how
    many it took."""
    folders, had = {}, set()
    for pk, folder, table in collection.months.exclude(folder=None).values_list(
        "pk", "folder_id", "table_id"
    ):
        folders[folder] = pk
        had.add(str(table))
    if not folders:
        return 0
    for files, node in Item.objects.filter(collection=collection).values_list("files", "node_id"):
        had.update(files)
        had.add(str(node))
    found = [
        node
        for node in Node.objects.filter(
            parent_id__in=folders, kind=Node.Kind.FILE, trashed_at=None
        ).only("pk", "parent_id", "title")
        if str(node.pk) not in had
    ]
    Item.objects.bulk_create(
        [
            Item(
                collection=collection,
                month_id=folders[node.parent_id],
                node=node,
                chosen=True,
                subject=node.title,
            )
            for node in found
        ],
        ignore_conflicts=True,
    )
    if found:
        months.touched(collection.pk)
    return len(found)


def looked() -> bool:
    """Has each collection whose time came look for new mail; whether one found a full page."""
    now = time.monotonic()
    more = False
    for collection in Collection.objects.filter(active=True).order_by("pk"):
        if now - _looked.get(collection.pk, -LOOK) < LOOK:
            continue
        filed(collection)
        if look(collection):
            more = True
        else:
            _looked[collection.pk] = now
    return more


def _unread_pdf() -> Exists:
    return Exists(
        Attachment.objects.filter(
            message=OuterRef("message"),
            inline=False,
            blob__media_type=store.PDF,
            blob__text__isnull=True,
        )
    )


def _unread_file() -> Exists:
    return Exists(
        Node.objects.filter(
            pk=OuterRef("node"), blob__media_type=store.PDF, blob__text__isnull=True
        )
    )


def claimed() -> Item | None:
    """The first message waiting to be read whose files' text is there, or that waited long
    enough for it, marked as tried."""
    now = timezone.now()
    with transaction.atomic():
        found = (
            Item.objects.filter(state=Item.State.WAITING, collection__active=True)
            .filter(Q(tried_at=None) | Q(tried_at__lt=now - RETRY))
            .filter(~(_unread_pdf() | _unread_file()) | Q(created_at__lt=now - TEXT_WAIT))
            .select_related("collection", "collection__owner", "month", "message", "node")
            .select_for_update(no_key=True, skip_locked=True, of=("self",))
            .order_by("created_at", "pk")
            .first()
        )
        if found is not None:
            Item.objects.filter(pk=found.pk).update(tried_at=now)
    return found


def _settled(item: Item, state: Item.State, error: str = "", **values) -> None:
    Item.objects.filter(pk=item.pk).update(state=state, error=error, **values)
    months.touched(item.collection_id)


def _plain(message: Message | None, node: Node | None) -> dict:
    if message is None:
        return {
            "supplier": node.title[:200],
            "date": node.created_at.astimezone(months.ZONE).date(),
            "amount": None,
            "currency": "",
        }
    sender = message.sender or {}
    address = sender.get("address", "")
    return {
        "supplier": (sender.get("name") or address.rpartition("@")[2])[:200],
        "date": message.date.astimezone(months.ZONE).date(),
        "amount": None,
        "currency": "",
    }


def placed(item: Item, files: list[Attachment], found: dict) -> list[str]:
    """The ids of the message's files in its month's folder, each file once however many
    messages carry it, named by its date so the folder lists them in order."""
    folder = months.folder_for(item.month)
    on = found["date"] or item.message.date.astimezone(months.ZONE).date()
    ids = []
    for each in files:
        node = Node.objects.filter(
            parent=folder, kind=Node.Kind.FILE, blob_id=each.blob_id, trashed_at=None
        ).first()
        if node is None:
            title, extension = named(each.name or each.part)
            node = created(
                folder,
                Node.Kind.FILE,
                f"{on:%Y-%m-%d} {title}"[:200],
                each.blob,
                item.collection.owner,
                extension,
            )
        ids.append(str(node.pk))
    if ids:
        extraction.wake()
        previews.wake()
    return ids


def _recognised(item: Item, message: Message | None, files: list[tuple[str, str]]) -> dict | None:
    collection = item.collection
    run = ActionRun.objects.create(
        user=collection.owner,
        action=recognising.ACTION,
        target={"messages": [message.pk]} if message else {"files": [str(item.node_id)]},
        parameters={"collection": collection.pk},
        model=recognising.MODEL,
        consent=ActionRun.Consented.ONCE,
        consented_by=collection.owner,
    )
    Item.objects.filter(pk=item.pk).update(run=run)
    try:
        found = recognising.read(item, message, files, runs.spending(run))
    except Unavailable as unavailable:
        runs.finish(run, ActionRun.State.FAILED, unavailable.code)
        raise
    except model.Failed as failed:
        runs.finish(run, ActionRun.State.FAILED, failed.code)
        raise
    runs.finish(run, ActionRun.State.DONE)
    return found


def _matching(item: Item, found: dict) -> Item | None:
    """The kept bill a file put in by hand belongs to: of the same amount and currency, dated
    within days of it, the nearest of those still without a file first."""
    on: date | None = found["date"]
    if found["amount"] is None or not found["currency"] or on is None:
        return None
    candidates = Item.objects.filter(
        collection_id=item.collection_id,
        state=Item.State.KEPT,
        amount=found["amount"],
        currency=found["currency"],
        date__range=(on - APART, on + APART),
    ).exclude(pk=item.pk)
    return min(
        candidates,
        key=lambda each: (bool(each.files), abs((each.date - on).days), each.pk),
        default=None,
    )


def _told(item: Item) -> None:
    """Tells the owner a bill came without a file, once, by the message that says where to
    fetch it."""
    message = item.message
    if item.files or item.told or message is None:
        return
    Item.objects.filter(pk=item.pk).update(told=True)
    notices.tell(
        [item.collection.owner_id],
        Notice.Kind.BILL,
        {
            "collection": item.collection.name,
            "supplier": item.supplier,
            "amount": None if item.amount is None else str(item.amount),
            "currency": item.currency,
            "folder": message.folder_id,
            "message": message.pk,
        },
        tag=notices.topic("bill", item.pk),
    )


def read(item: Item) -> None:
    """Reads the message or file the item took and keeps it with what it says, or passes it over
    as no bill; a model the owner cannot reach now leaves it waiting, and the collection says
    why. A file kept joins the bill it belongs to."""
    message, node = item.message, item.node
    if node is not None and not node.is_live():
        node = None
    if message is None and node is None:
        _settled(item, Item.State.FAILED, "not_found")
        return
    if message is not None:
        files = list(message.files.filter(inline=False).select_related("blob").order_by("pk"))
        named_files = [(each.name or each.part, each.blob_id) for each in files]
    else:
        files = []
        named_files = [(f"{node.title}.{node.extension}".rstrip("."), node.blob_id)]
    collection = item.collection
    plain = _plain(message, node)
    if collection.recognise:
        try:
            found = _recognised(item, message, named_files)
        except Unavailable as unavailable:
            Collection.objects.filter(pk=collection.pk).update(error=unavailable.code)
            return
        except model.Failed as failed:
            log.warning("collection %s item %s: %s", collection.pk, item.pk, failed)
            if failed.code in PASSED:
                _settled(item, Item.State.FAILED, failed.code)
            else:
                Collection.objects.filter(pk=collection.pk).update(error=failed.code)
            return
        if found is None:
            _settled(item, Item.State.PASSED)
            return
        found = {key: found[key] or plain[key] for key in ("supplier", "date")} | {
            "amount": found["amount"],
            "currency": found["currency"],
        }
    else:
        found = plain
    with transaction.atomic():
        if node is not None and (bill := _matching(item, found)) is not None:
            Item.objects.filter(pk=bill.pk).update(files=[*bill.files, str(node.pk)])
            item.delete()
            months.touched(collection.pk)
            return
        ids = placed(item, files, found) if message is not None else [str(node.pk)]
        _settled(item, Item.State.KEPT, files=ids, **found)
        if collection.error:
            Collection.objects.filter(pk=collection.pk).update(error="")
    item.refresh_from_db()
    converting.converted(item)
    _told(item)


def read_next() -> bool:
    """Reads the next message waiting; False when none is."""
    item = claimed()
    if item is None:
        return False
    try:
        read(item)
    except Exception as error:
        log.exception("collection %s item %s failed", item.collection_id, item.pk)
        _settled(item, Item.State.FAILED, type(error).__name__[:40])
    return True
