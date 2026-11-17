"""A collection's month as it goes to whom it is for: a table of whom, when and how much, kept as
a document in the month's folder and carried as a workbook beside the month's files, in a
message the owner finds among those they began, or that leaves by itself."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from html import escape
from logging import getLogger

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.blobs import store
from apps.core import locks
from apps.core.api import Refused
from apps.core.asyncdb import notify
from apps.exports import xlsx
from apps.mail import sending
from apps.mail import views as mail
from apps.mail.models import Account, Unsent

from . import converting, months, tabling
from .models import Collection, Item, Month

log = getLogger(__name__)

# How long a month whose day came waits for the messages still being read.
LATE = timedelta(hours=6)
LOCK = 0x5C21B10E
ACCOUNT_GONE = "mail_account_gone"
UNRATED = "collecting_unrated"


def named(collection: Collection, month: date) -> str:
    """The month as its message is titled: the collection's name and the month in words."""
    spoken = tabling.words_of(collection.owner)["months"][month.month - 1]
    return f"{collection.name} – {spoken} {month.year}"


def _waiting(month: Month) -> bool:
    return month.items.filter(state=Item.State.WAITING).exists()


def due(now: datetime | None = None) -> Month | None:
    """A month whose time came, asked for by its owner or on the collection's day, once the
    messages it took are read or it waited long enough for them."""
    now = now or timezone.now()
    waiting = Exists(Item.objects.filter(month=OuterRef("pk"), state=Item.State.WAITING))
    found = (
        Month.objects.filter(delivered_at=None, failed="", collection__active=True)
        .filter(Q(asked_at__isnull=False) | Q(past=False, month__lt=months.first_of(now)))
        .annotate(waiting=waiting)
        .select_related("collection", "collection__owner")
        .order_by("month", "pk")
    )
    for month in found:
        since = month.asked_at or months.moment_of(month.collection, month.month)
        if since <= now and (not month.waiting or since + LATE <= now):
            return month
    return None


def _number(value: Decimal, language: str) -> str:
    shown = f"{value:,.2f}"
    return shown.translate(str.maketrans(",.", ".,")) if language == "hr" else shown


def _day(value: date | None, language: str) -> str:
    if value is None:
        return ""
    return f"{value.day}.{value.month}.{value.year}." if language == "hr" else value.isoformat()


def letter(collection: Collection, items: list[Item], titles: dict, account: Account) -> str:
    """The message's text: the collection's words, the table, and the account's signature."""
    words = tabling.words_of(collection.owner)
    language = tabling.language_of(collection.owner)
    lines = [f"<p>{escape(line)}</p>" for line in collection.text.rstrip("\n").split("\n") if line]
    cell = 'style="border:1px solid #c8d0d0;padding:4px 8px"'
    right = 'style="border:1px solid #c8d0d0;padding:4px 8px;text-align:right"'
    into = collection.currency
    shown = 6 if into else 5
    head = "".join(
        f"<th {cell}>{escape(name)}</th>" for name in tabling.columns(words, into)[:shown]
    )

    def figure(value: Decimal | None) -> str:
        return "" if value is None else _number(value, language)

    blank = f"<td {cell}></td>"
    rows = [
        "<tr>"
        f"<td {cell}>{escape(item.supplier)}</td>"
        f"<td {cell}>{_day(item.date, language)}</td>"
        f"<td {right}>{figure(item.amount)}</td>"
        f"<td {cell}>{escape(item.currency)}</td>"
        + (f"<td {right}>{figure(item.converted)}</td>" if into else "")
        + f"<td {cell}>{escape(tabling.file_names(item, titles))}</td>"
        "</tr>"
        for item in items
    ]
    rows += [
        f"<tr><th {cell}>{escape(words['total'])}</th>{blank}"
        f"<th {right}>{_number(total, language)}</th><td {cell}>{escape(currency)}</td>"
        + blank * (shown - 4)
        + "</tr>"
        for currency, total in sorted(tabling.totals(items).items())
    ]
    if into:
        rows.append(
            f"<tr><th {cell}>{escape(words['total'])}</th>{blank}{blank}"
            f"<td {cell}>{escape(into)}</td>"
            f"<th {right}>{_number(tabling.converted_total(items), language)}</th>{blank}</tr>"
        )
    table = (
        '<table style="border-collapse:collapse">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )
    signature = mail._signature_of(account)
    signed = f'<p></p><div data-signature="">{signature}</div>' if signature else ""
    return "".join(lines) + table + signed


def _account(collection: Collection) -> Account | None:
    accounts = Account.objects.filter(owner_id=collection.owner_id)
    if collection.account_id and (found := accounts.filter(pk=collection.account_id).first()):
        return found
    return accounts.order_by("-default", "pk").first()


def delivered(month: Month) -> None:
    """Makes the month's table and the message that takes it, with the files in the month's
    folder as they are now, to the collection's people: kept among the owner's messages begun,
    or leaving at once."""
    collection = month.collection
    owner = collection.owner
    folder = months.folder_for(month)
    items, files = tabling.contents(month, folder)
    now = timezone.now()
    if not items and not files:
        Month.objects.filter(pk=month.pk).update(delivered_at=now, asked_at=None)
        months.touched(collection.pk)
        return
    account = _account(collection)
    if account is None:
        Month.objects.filter(pk=month.pk).update(failed=ACCOUNT_GONE, asked_at=None)
        months.touched(collection.pk)
        return
    if not all(converting.converted(item) for item in items):
        Month.objects.filter(pk=month.pk).update(failed=UNRATED, asked_at=None)
        months.touched(collection.pk)
        return
    title = f"{collection.name} {month.month:%Y-%m}"
    titles = {str(node.pk): tabling.file_name(node) for node in files}
    sheet = tabling.month_written(month, items, files, folder)
    with xlsx.workbook(sheet) as book:
        blob = store.put(book)
    attached = [
        {"sha256": node.blob_id, "name": tabling.file_name(node)[:255], "size": node.blob.size}
        for node in files
    ]
    attached.append({"sha256": blob.sha256, "name": f"{title}.xlsx"[:255], "size": blob.size})
    given = {
        "account": account.pk,
        "to": collection.to,
        "subject": named(collection, month.month),
        "html": letter(collection, items, titles, account),
        "files": attached,
    }
    try:
        account, written = mail._written(owner, given)
    except Refused as refused:
        Month.objects.filter(pk=month.pk).update(failed=refused.error, asked_at=None, table=sheet)
        months.touched(collection.pk)
        return
    leaves = collection.sends == Collection.Sends.SEND
    with transaction.atomic():
        unsent = Unsent.objects.create(
            owner=owner, account=account, written=written, send_at=now if leaves else None
        )
        mail._held(unsent)
        Month.objects.filter(pk=month.pk).update(
            delivered_at=now, asked_at=None, unsent=unsent, table=sheet, failed=""
        )
        months.touched(collection.pk)
        if leaves:
            notify(sending.LATER)


def deliver_next() -> bool:
    """Sends the next month whose time came; False when none has. The month is held by a lock of
    a session rather than of a transaction: writing its table opens the document's own."""
    found = due()
    if found is None:
        return False
    with locks.held(LOCK, found.pk) as mine:
        if not mine:
            return False
        try:
            month = (
                Month.objects.filter(pk=found.pk, delivered_at=None, failed="")
                .select_related("collection", "collection__owner", "folder", "table")
                .first()
            )
            if month is not None:
                delivered(month)
        except Exception:
            log.exception("collection %s month %s failed", found.collection_id, found.month)
            Month.objects.filter(pk=found.pk).update(failed="unexpected", asked_at=None)
            months.touched(found.collection_id)
    return True
