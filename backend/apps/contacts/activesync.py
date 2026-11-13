"""An ActiveSync account's contacts (D15, S4): each folder of contacts its hierarchy lists taken by
Sync as its mail is, on the account's one connection; its new contacts only."""

import base64
import binascii
from datetime import datetime, timedelta
from email.utils import parseaddr

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from apps.mail.activesync.client import Session
from apps.mail.activesync.wbxml import Element
from apps.mail.activesync.wbxml import element as e
from apps.mail.imap import Failed
from apps.mail.models import Account

from . import cards, taking
from .models import Book, Contact, Taken
from .vcard import Card, address_text

# MS-ASCMD 2.2.3.186.3: the default folder of contacts, and one the user made.
KINDS = {"9", "14"}
WINDOW = 100
OPTIONS = e(
    "AirSync:Options",
    e(
        "AirSyncBase:BodyPreference",
        e("AirSyncBase:Type", "1"),
        e("AirSyncBase:TruncationSize", "32768"),
    ),
)
NAMES = {
    "FirstName": "given",
    "LastName": "family",
    "MiddleName": "middle",
    "Title": "prefix",
    "Suffix": "suffix",
    "NickName": "nickname",
    "CompanyName": "organisation",
    "Department": "department",
    "JobTitle": "title",
}
PHONES = [
    ("MobilePhoneNumber", "mobile"),
    ("BusinessPhoneNumber", "work"),
    ("Business2PhoneNumber", "work"),
    ("CompanyMainPhone", "main"),
    ("HomePhoneNumber", "home"),
    ("Home2PhoneNumber", "home"),
    ("BusinessFaxNumber", "fax"),
    ("HomeFaxNumber", "fax"),
    ("PagerNumber", "pager"),
    ("CarPhoneNumber", "other"),
    ("RadioPhoneNumber", "other"),
    ("AssistantPhoneNumber", "other"),
]
ADDRESSES = [("Business", "work"), ("Home", "home"), ("Other", "other")]


def held(account: Account, changes: Element | None, whole: bool) -> None:
    """Keeps the account's address books as its hierarchy says they are now: `whole` where it
    listed every folder, else what changed since."""
    listed = set()
    for change in changes or ():
        server_id = change.text("ServerId")
        if change.name in ("Add", "Update") and change.text("Type") in KINDS:
            listed.add(server_id)
            Book.objects.update_or_create(
                account=account, server_id=server_id, defaults={"name": change.text("DisplayName")}
            )
        elif change.name in ("Add", "Update", "Delete"):
            account.contact_books.filter(server_id=server_id).delete()
    if whole:
        account.contact_books.exclude(server_id__in=listed).delete()


def _day(value: str) -> str:
    """A birthday's day: Exchange keeps it as the midnight of the user's zone, in UTC."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if moment.hour >= 12:
        moment += timedelta(days=1)
    return moment.date().isoformat()


def card(data: Element) -> tuple[Card, dict]:
    """The contact as PONISTRA reads it, and what the server gave, the picture left out."""
    given = {}
    for child in data:
        if child.name == "Body":
            given["Body"] = child.text("Data")
        elif child.children:
            given[child.name] = [each.string for each in child]
        elif child.name != "Picture":
            given[child.name] = child.string
    found = Card()
    for name, field in NAMES.items():
        found.fields[field] = given.get(name, "").strip()
    found.fields["birthday"] = _day(given.get("Birthday", ""))
    found.fields["note"] = given.get("Body", "").strip()
    if not any(found.fields[key] for key in ("given", "family", "organisation")):
        found.fields["name"] = given.get("FileAs", "").strip()
    for number in ("Email1Address", "Email2Address", "Email3Address"):
        address = parseaddr(given.get(number, ""))[1].strip()
        if "@" in address:
            found.points.append({"kind": "email", "label": "", "value": address, "parts": []})
    for name, label in PHONES:
        if number := given.get(name, "").strip():
            found.points.append({"kind": "phone", "label": label, "value": number, "parts": []})
    for prefix, label in ADDRESSES:
        parts = ["", ""] + [
            given.get(f"{prefix}Address{part}", "").strip()
            for part in ("Street", "City", "State", "PostalCode", "Country")
        ]
        if any(parts):
            found.points.append(
                {"kind": "address", "label": label, "value": address_text(parts), "parts": parts}
            )
    if page := given.get("WebPage", "").strip():
        found.points.append({"kind": "url", "label": "", "value": page, "parts": []})
    picture = data.find("Picture")
    if picture is not None and picture.value:
        try:
            found.photo = base64.b64decode(picture.string)
        except binascii.Error, ValueError:
            found.photo = None
    return found, given


def _sync(book: Book, key: str, *more: Element) -> Element:
    return e(
        "AirSync:Sync",
        e(
            "AirSync:Collections",
            e(
                "AirSync:Collection",
                e("AirSync:SyncKey", key),
                e("AirSync:CollectionId", book.server_id),
                *more,
            ),
        ),
    )


def caught_up(client: Session, book: Book) -> None:
    """Takes every contact the server has new in the folder."""
    account = book.account
    while True:
        more = ()
        if book.key:
            window = e("AirSync:WindowSize", str(WINDOW))
            more = (e("AirSync:GetChanges", "1"), window, OPTIONS)
        answer = client.command("Sync", _sync(book, book.key or "0", *more))
        collection = answer.find("Collections/Collection")
        if collection is None:
            return
        status = collection.text("Status")
        if status == "3":
            # The server no longer knows the key: the folder is taken again from nothing, and the
            # contacts taken before are not taken twice.
            Book.objects.filter(pk=book.pk).update(key="")
            book.key = ""
            continue
        if status != "1":
            raise Failed("activesync_unreachable")
        for add in collection.findall("Commands/Add"):
            data = add.find("ApplicationData")
            if data is not None:
                found, given = card(data)
                item = f"{book.server_id}/{add.text('ServerId')}"
                taking.taken(
                    account.owner_id,
                    account,
                    Taken.Kind.ACTIVESYNC,
                    account.address,
                    item,
                    found,
                    given,
                )
        book.key = collection.text("SyncKey")
        Book.objects.filter(pk=book.pk).update(key=book.key)
        if more and collection.find("MoreAvailable") is None:
            return


@transaction.atomic
def wiped(account: Account) -> None:
    """What came through the account goes when its server's administrator wipes the device: its
    address books, and the contacts it alone gave, its directory's colleagues among them."""
    account.contact_books.all().delete()
    through = Q(account=account) | Q(kind=Taken.Kind.DIRECTORY, source=account.activesync_host)
    other = Taken.objects.filter(contact=OuterRef("pk")).exclude(through)
    brought = Taken.objects.filter(through)
    alone = Contact.objects.filter(owner_id=account.owner_id, taken__in=brought)
    for contact in alone.exclude(Exists(other)).distinct():
        cards.deleted(contact)
