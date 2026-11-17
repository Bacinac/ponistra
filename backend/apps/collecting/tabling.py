"""The tables a collection keeps in its folders as its bills come and go: each month's, of whom,
when and how much and whether it was sent, and one of every month by supplier. Each is written
again only when what it shows changed."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from logging import getLogger

from django.db.models import F, Q
from django.utils import timezone
from pycrdt import Map, XmlElement

from apps.collab.models import Update
from apps.content import blocks, designs, operations, styles
from apps.core import locks
from apps.documents.models import Node
from apps.documents.views import BY_TITLE, created
from apps.engine import numformat

from . import months
from .models import Collection, Item, Month

log = getLogger(__name__)

LOCK = 0x5C21B10F
# Read again now and then though nothing said it changed, as a file renamed in a month's folder.
STALE = timedelta(hours=1)
EPOCH = date(1899, 12, 30)
# The characters a line of the landscape page holds, a column's room beside its text, the least
# a column takes, and the most a column of text takes before it wraps: a column as short as SHORT
# never does.
LINE = 150
SIDES = 4
NARROWEST = 9
LONGEST = 40
SHORT = 16
TEXT = {"size": 10, "line": 1.2, "after": 6}
PAGE = {"width": 29.7, "height": 21.0, "top": 1.5, "right": 1.5, "bottom": 1.5, "left": 1.5}
_HEADER = designs.ours("header")
DESIGN = {
    **_HEADER,
    "parts": {**_HEADER["parts"], "header": {**_HEADER["parts"]["header"], "valign": "center"}},
    "on": {"header": True},
}
TOTALS = "#dceaea"
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
        "recap": "Rekapitulacija",
        "month": "Mjesec",
        "currency": "Valuta",
        "sent": "Poslano",
        "sentAt": "Poslano {when}",
        "drafted": "Skica od {when}, nije poslana",
        "draftedShort": "Ne (skica od {when})",
        "unsent": "Nije poslano",
        "no": "Ne",
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
        "recap": "Summary",
        "month": "Month",
        "currency": "Currency",
        "sent": "Sent",
        "sentAt": "Sent {when}",
        "drafted": "Draft of {when}, not sent",
        "draftedShort": "No (draft of {when})",
        "unsent": "Not sent",
        "no": "No",
    },
}


def words_of(collection: Collection) -> dict:
    return WORDS[collection.language]


def totals(items: list[Item]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for item in items:
        if item.amount is not None:
            totals[item.currency] = totals.get(item.currency, Decimal(0)) + item.amount
    return totals


def file_names(item: Item, titles: dict[str, str]) -> str:
    return ", ".join(titles[each] for each in item.files if each in titles)


def file_name(node: Node) -> str:
    return f"{node.title}.{node.extension}" if node.extension else node.title


def _paragraph(value: str, strong: bool = False, align: str = "") -> dict:
    text = {"type": "text", "text": value}
    if strong:
        text["marks"] = [{"type": "strong"}]
    paragraph = {"type": "paragraph", "content": [text]}
    if align:
        paragraph["attrs"] = {"align": align}
    return paragraph


def _text(value: str, strong: bool = False, align: str = "") -> dict | None:
    return {"blocks": [_paragraph(value, strong, align)]} if value else None


def _shown(cell: dict | str | None, language: str) -> str:
    if cell is None or isinstance(cell, str):
        return cell or ""
    if "blocks" in cell:
        return " ".join(
            each.get("text", "") for block in cell["blocks"] for each in block.get("content", [])
        )
    return str(numformat.shown(cell["value"], cell.get("format", "General"), language))


def _shares(rows: list[list], language: str) -> list[float]:
    """Each column's share of the page in per cent, as wide as its longest text, its head's longest
    word, as a head wraps between words: what is short keeps its width, and what is long shares
    the line's rest, wrapping past LONGEST."""
    count = max(len(row) for row in rows)
    needs = [
        max(
            NARROWEST,
            round(max(map(len, _shown(rows[0][x], language).split()), default=0) * 1.2) + SIDES,
            *(len(_shown(row[x], language)) + SIDES for row in rows[1:] if x < len(row)),
        )
        for x in range(count)
    ]
    long = [x for x, need in enumerate(needs) if need > SHORT]
    rest = LINE - sum(need for x, need in enumerate(needs) if x not in long)
    wanted = sum(min(needs[x], LONGEST) for x in long)
    if long and wanted > rest:
        for x in long:
            needs[x] = max(min(needs[x], LONGEST) * rest / wanted, SHORT)
    whole = sum(needs)
    return [round(need * 100 / whole, 2) for need in needs]


def laid(
    heading: str,
    lines: list[str],
    rows: list[list],
    totals: int,
    language: str,
    aligned: dict[int, str],
) -> dict:
    """A table as it is to be written: the heading and lines above it, its rows under a centred
    head, the last `totals` rows bold and tinted, and the columns aligned as given."""
    head = [_text(name, strong=True, align="center") for name in rows[0]]
    return {
        "heading": heading,
        "lines": lines,
        "designs": [DESIGN],
        "rows": [head, *rows[1:]],
        "widths": _shares(rows, language),
        "totals": totals,
        "aligned": sorted(aligned.items()),
    }


def operations_of(table: dict) -> list[dict]:
    """The operations that write the laid table at the top of the body, with ids of its own."""
    id = blocks.new_id()
    rows = [blocks.new_id() for _ in table["rows"]]
    cols = [blocks.new_id() for _ in table["widths"]]
    made = [
        {
            "op": "table",
            "at": {"start": "body"},
            "id": id,
            "designs": table["designs"],
            "widths": table["widths"],
            "rows": table["rows"],
            "rowIds": rows,
            "colIds": cols,
        }
    ]
    made += [
        {
            "op": "looks",
            "table": id,
            "axis": "cols",
            "from": cols[x],
            "to": cols[x],
            "attrs": {"align": align},
        }
        for x, align in table["aligned"]
    ]
    made.append(
        {
            "op": "looks",
            "table": id,
            "axis": "rows",
            "from": rows[0],
            "to": rows[0],
            "attrs": {"align": "center"},
        }
    )
    if table["totals"]:
        made.append(
            {
                "op": "looks",
                "table": id,
                "axis": "rows",
                "from": rows[-table["totals"]],
                "to": rows[-1],
                "marks": {"strong": {}},
                "fill": TOTALS,
            }
        )
    if table["totals"] > 1:
        made.append(
            {
                "op": "cells",
                "table": id,
                "cells": [
                    {
                        "row": rows[-table["totals"]],
                        "col": cols[0],
                        "span": {"rows": table["totals"]},
                    }
                ],
            }
        )
    above = [
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": table["heading"]}],
        },
        *(_paragraph(line, strong=True) for line in table["lines"]),
    ]
    made.append({"op": "insert", "at": {"start": "body"}, "blocks": above})
    return made


def _serial(value: date | None, words: dict) -> dict | None:
    if value is None:
        return None
    return {"value": (value - EPOCH).days, "format": words["date"]}


def _amount(value: Decimal | None, words: dict) -> dict | None:
    if value is None:
        return None
    return {"value": float(value), "format": words["amount"]}


def columns(words: dict, into: str) -> list[str]:
    """The table's columns, the amount in the collection's currency after the bill's own."""
    columns = list(words["columns"])
    if into:
        columns.insert(4, words["converted"].format(currency=into))
    return columns


def converted_total(items: list[Item]) -> Decimal:
    return sum((item.converted for item in items if item.converted is not None), Decimal(0))


def tabled(items: list[Item], titles: dict[str, str], words: dict, into: str = "") -> tuple:
    """The month's rows: one for each bill, then a total in each currency and in the
    collection's own, with how many rows are totals. Text goes in as text, never as typed, so a
    subject that reads as a number or a formula stays what it is."""
    width = 7 if into else 6
    rows = [columns(words, into)]
    for item in items:
        row = [
            _text(item.supplier),
            _serial(item.date, words),
            _amount(item.amount, words),
            _text(item.currency),
            _text(file_names(item, titles)),
            _text(item.subject),
        ]
        if into:
            row.insert(4, _amount(item.converted, words))
        rows.append(row)
    summed = sorted(totals(items).items())
    for currency, total in summed:
        rows.append(
            [_text(words["total"]), None, _amount(total, words), _text(currency)]
            + [None] * (width - 4)
        )
    if into:
        rows.append(
            [_text(words["total"]), None, None, _text(into)]
            + [_amount(converted_total(items), words)]
            + [None] * (width - 5)
        )
    return rows, len(summed) + (1 if into else 0)


def moment(value: datetime, language: str) -> str:
    local = value.astimezone(months.ZONE)
    if language == "hr":
        return f"{local.day}.{local.month}.{local.year}. u {local:%H:%M}"
    return f"{local:%Y-%m-%d %H:%M}"


def state_of(month: Month, words: dict, language: str) -> str:
    """Whether the month's message left: sent, waiting among the owner's drafts, or not at all."""
    if month.sent_at is not None:
        return words["sentAt"].format(when=moment(month.sent_at, language))
    if month.delivered_at is not None and month.unsent_id is not None:
        return words["drafted"].format(when=moment(month.delivered_at, language))
    return words["unsent"]


def _sent_cell(month: Month, words: dict, language: str) -> str:
    if month.sent_at is not None:
        return moment(month.sent_at, language)
    if month.delivered_at is not None and month.unsent_id is not None:
        return words["draftedShort"].format(when=moment(month.delivered_at, language))
    return words["no"]


def _digest(*parts) -> str:
    return sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _set_up(node: Node) -> None:
    built = styles.TEMPLATE[styles.STYLES]
    own = styles.own(styles.TEMPLATE[styles.THEME], {**built, "text": {**built["text"], **TEXT}})
    own.get("page", type=Map).update(PAGE)
    Update.objects.filter(document=node).update(data=own.get_update())


def _written(node: Node | None, folder: Node, title: str, owner, table: dict, author: str) -> Node:
    """The document written anew in the one made before, which keeps its place, links and
    versions, under the title it is to have; a new one on a landscape page in a compact text."""
    if node is None or not node.is_live():
        node = created(folder, Node.Kind.DOCUMENT, title[:200], None, owner)
        _set_up(node)
    elif node.title != title[:200]:
        node.title = title[:200]
        node.save(update_fields=["title", "updated_at"])

    def written(doc, sheets) -> list[dict]:
        before = [
            element.attributes.get("id")
            for element in blocks.body_of(doc).children
            if isinstance(element, XmlElement)
        ]
        taken = [{"op": "delete", "from": before[0], "to": before[-1]}] if before else []
        return [*operations_of(table), *taken]

    operations.perform(node.tabs.get(), written, author)
    return node


def contents(month: Month, folder: Node | None) -> tuple[list[Item], list[Node]]:
    """The month's bills kept and the files in its folder, the table aside."""
    items = list(month.items.filter(state=Item.State.KEPT).order_by("date", "pk"))
    if folder is None:
        return items, []
    files = list(
        Node.objects.filter(parent=folder, kind=Node.Kind.FILE, trashed_at=None)
        .exclude(pk=month.table_id)
        .select_related("blob")
        .order_by(BY_TITLE)
    )
    return items, files


def month_written(month: Month, items: list[Item], files: list[Node], folder: Node) -> Node:
    """The month's table under a line saying whether it was sent, written when it changed."""
    collection = month.collection
    words = words_of(collection)
    state = state_of(month, words, collection.language)
    titles = {str(node.pk): file_name(node) for node in files}
    rows, summed = tabled(items, titles, words, collection.currency)
    spoken = f"{words['months'][month.month.month - 1]} {month.month.year}"
    heading = f"{collection.name} – {spoken}"
    made = laid(heading, [state], rows, summed, collection.language, {1: "center", 3: "center"})
    title = f"{collection.name} {month.month:%Y-%m}"
    digest = _digest(title, made)
    if digest == month.tabled and month.table is not None and month.table.is_live():
        return month.table
    node = _written(month.table, folder, title, collection.owner, made, f"collecting:{month.pk}")
    Month.objects.filter(pk=month.pk).update(table=node, tabled=digest)
    month.table, month.tabled = node, digest
    return node


def _live(node: Node | None) -> Node | None:
    return node if node is not None and node.is_live() else None


def _month_kept(month: Month) -> None:
    """The month's table as it stands; a folder its owner took away is not made again here."""
    folder = _live(month.folder)
    if folder is None:
        return
    items, files = contents(month, folder)
    if items or files or _live(month.table):
        month_written(month, items, files, folder)


def recapped(collection: Collection, found: list[Month]) -> dict | None:
    """Every month in a row by the suppliers its bills came from, in the collection's currency or
    in a row of each currency the bills were in, with whether the month was sent, then the total."""
    words = words_of(collection)
    language = collection.language
    into = collection.currency
    sums: dict[tuple[date, str], dict[str, Decimal]] = {}
    names: dict[str, str] = {}
    by: dict[str, Decimal] = {}
    for item in Item.objects.filter(month__in=found, state=Item.State.KEPT).select_related("month"):
        value = item.converted if into else item.amount
        if value is None:
            continue
        currency = into or item.currency
        key = item.supplier.strip().casefold()
        names.setdefault(key, item.supplier.strip())
        row = sums.setdefault((item.month.month, currency), {})
        row[key] = row.get(key, Decimal(0)) + value
        by[key] = by.get(key, Decimal(0)) + value
    if not sums:
        return None
    suppliers = sorted(by, key=lambda key: (-by[key], names[key]))
    sent = {month.month: _sent_cell(month, words, language) for month in found}
    head = [
        words["month"],
        *(names[key] or "—" for key in suppliers),
        words["total"],
        *([] if into else [words["currency"]]),
        words["sent"],
    ]
    rows = [head]
    totals: dict[str, dict[str, Decimal]] = {}
    for (month, currency), row in sorted(sums.items()):
        whole = totals.setdefault(currency, {})
        for key, value in row.items():
            whole[key] = whole.get(key, Decimal(0)) + value
        rows.append(
            [
                {"value": (month - EPOCH).days, "format": "mmmm yyyy"},
                *(_amount(row.get(key), words) for key in suppliers),
                _amount(sum(row.values(), Decimal(0)), words),
                *([] if into else [_text(currency)]),
                _text(sent[month]),
            ]
        )
    for currency, whole in sorted(totals.items()):
        rows.append(
            [
                _text(words["total"]),
                *(_amount(whole.get(key), words) for key in suppliers),
                _amount(sum(whole.values(), Decimal(0)), words),
                *([] if into else [_text(currency)]),
                None,
            ]
        )
    heading = f"{collection.name} – {words['recap']}"
    width = len(head)
    aligned = {0: "left", width - 1: "center"} | ({} if into else {width - 2: "center"})
    return laid(heading, [], rows, len(totals), collection.language, aligned)


def _recap_kept(collection: Collection, found: list[Month]) -> None:
    folder = _live(collection.folder)
    if folder is None:
        return
    table = recapped(collection, found)
    if table is None:
        return
    title = f"{collection.name} – {words_of(collection)['recap']}"
    digest = _digest(title, table)
    if digest == collection.recapped and _live(collection.recap):
        return
    node = _written(
        collection.recap, folder, title, collection.owner, table, f"collecting:{collection.pk}"
    )
    Collection.objects.filter(pk=collection.pk).update(recap=node, recapped=digest)


def kept(collection: Collection) -> None:
    """Every table of the collection as it stands."""
    found = list(collection.months.select_related("folder", "table").order_by("month"))
    for month in found:
        month.collection = collection
        _month_kept(month)
    _recap_kept(collection, found)


def tabled_next(now: datetime | None = None) -> bool:
    """Writes the tables of the next collection that changed since they were written; False when
    none has. A change while they are written has them written again."""
    now = now or timezone.now()
    found = (
        Collection.objects.filter(
            Q(tabled_at=None) | Q(tabled_at__lt=F("changed_at")) | Q(tabled_at__lt=now - STALE)
        )
        .select_related("owner", "folder", "recap")
        .order_by(F("tabled_at").asc(nulls_first=True), "pk")
        .first()
    )
    if found is None:
        return False
    with locks.held(LOCK, found.pk) as mine:
        if not mine:
            return False
        try:
            Collection.objects.filter(pk=found.pk).update(tabled_at=now)
            kept(found)
        except Exception:
            log.exception("collection %s tables failed", found.pk)
    return True
