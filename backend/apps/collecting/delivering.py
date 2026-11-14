"""A collection's month as it goes to whom it is for: a table of whom, when and how much, kept as
a document in the month's folder and carried as a workbook beside the month's files, in a
message the owner finds among those they began, or that leaves by itself."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from html import escape
from logging import getLogger

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from pycrdt import XmlElement

from apps.blobs import store
from apps.content import blocks, operations
from apps.core.api import Refused
from apps.core.asyncdb import notify
from apps.documents.models import Node
from apps.documents.views import BY_TITLE, created
from apps.exports import xlsx
from apps.mail import sending
from apps.mail import views as mail
from apps.mail.models import Account, Unsent

from . import converting, months
from .models import Collection, Item, Month

log = getLogger(__name__)

# How long a month whose day came waits for the messages still being read.
LATE = timedelta(hours=6)
EPOCH = date(1899, 12, 30)
LOCK = 0x5C21B10E
WIDTHS = (28, 12, 14, 9, 40, 50)
CONVERTED = 14
WORDS = {
    "hr": {
        "columns": ("Dobavljač", "Datum", "Iznos", "Valuta", "Datoteke", "Predmet"),
        "converted": "Iznos u {currency}",
        "total": "Ukupno",
        "months": (
            "siječanj veljača ožujak travanj svibanj lipanj srpanj kolovoz rujan listopad "
            "studeni prosinac"
        ).split(),
        "date": "d.m.yyyy.",
        "amount": "#,##0.00",
    },
    "en": {
        "columns": ("Supplier", "Date", "Amount", "Currency", "Files", "Subject"),
        "converted": "Amount in {currency}",
        "total": "Total",
        "months": (
            "January February March April May June July August September October November December"
        ).split(),
        "date": "yyyy-mm-dd",
        "amount": "#,##0.00",
    },
}
ACCOUNT_GONE = "mail_account_gone"
UNRATED = "collecting_unrated"


def words_of(owner) -> dict:
    language = owner.language or settings.LANGUAGE_CODE
    return WORDS.get(language[:2], WORDS["en"])


def named(collection: Collection, month: date) -> str:
    """The month as its message is titled: the collection's name and the month in words."""
    spoken = words_of(collection.owner)["months"][month.month - 1]
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


def _totals(items: list[Item]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for item in items:
        if item.amount is not None:
            totals[item.currency] = totals.get(item.currency, Decimal(0)) + item.amount
    return totals


def _file_names(item: Item, titles: dict[str, str]) -> str:
    return ", ".join(titles[each] for each in item.files if each in titles)


def _text(value: str, strong: bool = False) -> dict | None:
    if not value:
        return None
    text = {"type": "text", "text": value}
    if strong:
        text["marks"] = [{"type": "strong"}]
    return {"blocks": [{"type": "paragraph", "content": [text]}]}


def _serial(value: date | None, words: dict) -> dict | None:
    if value is None:
        return None
    return {"value": (value - EPOCH).days, "format": words["date"]}


def _amount(value: Decimal | None, words: dict) -> dict | None:
    if value is None:
        return None
    return {"value": float(value), "format": words["amount"]}


def _columns(words: dict, into: str) -> list[str]:
    """The table's columns, the amount in the collection's currency after the bill's own."""
    columns = list(words["columns"])
    if into:
        columns.insert(4, words["converted"].format(currency=into))
    return columns


def _converted_total(items: list[Item]) -> Decimal:
    return sum((item.converted for item in items if item.converted is not None), Decimal(0))


def tabled(items: list[Item], titles: dict[str, str], words: dict, into: str = "") -> dict:
    """The month's table: a row for each bill, then a total in each currency and in the
    collection's own. Text goes in as text, never as typed, so a subject that reads as a number
    or a formula stays what it is."""
    widths = list(WIDTHS)
    if into:
        widths.insert(4, CONVERTED)
    rows = [[_text(column, strong=True) for column in _columns(words, into)]]
    for item in items:
        row = [
            _text(item.supplier),
            _serial(item.date, words),
            _amount(item.amount, words),
            _text(item.currency),
            _text(_file_names(item, titles)),
            _text(item.subject),
        ]
        if into:
            row.insert(4, _amount(item.converted, words))
        rows.append(row)
    totals = _totals(items)
    if totals or into:
        rows.append([None] * len(widths))
    for currency, total in sorted(totals.items()):
        rows.append(
            [_text(words["total"], strong=True), None, _amount(total, words), _text(currency)]
            + [None] * (len(widths) - 4)
        )
    if into:
        rows.append(
            [_text(words["total"], strong=True), None, None, _text(into)]
            + [_amount(_converted_total(items), words)]
            + [None] * (len(widths) - 5)
        )
    return {"op": "table", "at": {"start": "body"}, "widths": widths, "rows": rows}


def _written_table(month: Month, folder: Node, title: str, operation: dict) -> Node:
    """The month's table document, written anew in the one made before, which keeps its place,
    links and versions."""
    old = month.table if month.table is not None and month.table.is_live() else None
    node = old or created(folder, Node.Kind.DOCUMENT, title[:200], None, month.collection.owner)

    def written(doc, sheets) -> list[dict]:
        before = [
            element.attributes.get("id")
            for element in blocks.body_of(doc).children
            if isinstance(element, XmlElement)
        ]
        taken = [{"op": "delete", "from": before[0], "to": before[-1]}] if before else []
        return [operation, *taken]

    operations.perform(node.tabs.get(), written, f"collecting:{month.pk}")
    return node


def letter(collection: Collection, items: list[Item], titles: dict, account: Account) -> str:
    """The message's text: the collection's words, the table, and the account's signature."""
    words = words_of(collection.owner)
    language = (collection.owner.language or settings.LANGUAGE_CODE)[:2]
    lines = [f"<p>{escape(line)}</p>" for line in collection.text.rstrip("\n").split("\n") if line]
    cell = 'style="border:1px solid #c8d0d0;padding:4px 8px"'
    right = 'style="border:1px solid #c8d0d0;padding:4px 8px;text-align:right"'
    into = collection.currency
    shown = 6 if into else 5
    head = "".join(f"<th {cell}>{escape(name)}</th>" for name in _columns(words, into)[:shown])

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
        + f"<td {cell}>{escape(_file_names(item, titles))}</td>"
        "</tr>"
        for item in items
    ]
    rows += [
        f"<tr><th {cell}>{escape(words['total'])}</th>{blank}"
        f"<th {right}>{_number(total, language)}</th><td {cell}>{escape(currency)}</td>"
        + blank * (shown - 4)
        + "</tr>"
        for currency, total in sorted(_totals(items).items())
    ]
    if into:
        rows.append(
            f"<tr><th {cell}>{escape(words['total'])}</th>{blank}{blank}"
            f"<td {cell}>{escape(into)}</td>"
            f"<th {right}>{_number(_converted_total(items), language)}</th>{blank}</tr>"
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


def _file_name(node: Node) -> str:
    return f"{node.title}.{node.extension}" if node.extension else node.title


def delivered(month: Month) -> None:
    """Makes the month's table and the message that takes it, with the files in the month's
    folder as they are now, to the collection's people: kept among the owner's messages begun,
    or leaving at once."""
    collection = month.collection
    owner = collection.owner
    items = list(
        month.items.filter(state=Item.State.KEPT)
        .select_related("collection")
        .order_by("date", "pk")
    )
    folder = months.folder_for(month)
    files = list(
        Node.objects.filter(parent=folder, kind=Node.Kind.FILE, trashed_at=None)
        .exclude(pk=month.table_id)
        .select_related("blob")
        .order_by(BY_TITLE)
    )
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
    words = words_of(owner)
    title = f"{collection.name} {month.month:%Y-%m}"
    titles = {str(node.pk): _file_name(node) for node in files}
    operation = tabled(items, titles, words, collection.currency)
    sheet = _written_table(month, folder, title, operation)
    with xlsx.workbook(sheet) as book:
        blob = store.put(book)
    attached = [
        {"sha256": node.blob_id, "name": _file_name(node)[:255], "size": node.blob.size}
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
    the session rather than of a transaction: writing its table opens the document's own."""
    found = due()
    if found is None:
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [LOCK, found.pk])
        if not cursor.fetchone()[0]:
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
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [LOCK, found.pk])
    return True
