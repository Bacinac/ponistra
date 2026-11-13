"""A Microsoft account's contacts through Graph (D15, S4), consented to at the account's sign-in:
each folder's delta followed from where it was left, its new contacts only."""

import json
import urllib.error
import urllib.parse
import urllib.request

from apps.mail import signin
from apps.mail.imap import Failed
from apps.mail.models import Account

from . import taking
from .models import Book, Taken
from .vcard import Card, address_text

GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = 20
PAGE = 100
# Folders inside folders, as deep as Outlook lets them go in practice.
DEPTH = 5
NAMES = {
    "displayName": "name",
    "givenName": "given",
    "surname": "family",
    "middleName": "middle",
    "title": "prefix",
    "generation": "suffix",
    "nickName": "nickname",
    "companyName": "organisation",
    "department": "department",
    "jobTitle": "title",
    "personalNotes": "note",
}
ADDRESSES = [("businessAddress", "work"), ("homeAddress", "home"), ("otherAddress", "other")]


class Gone(Exception):
    """Graph no longer knows the delta link."""


def _get(token: str, url: str, raw: bool = False):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "*/*" if raw else "application/json",
            "Prefer": f"odata.maxpagesize={PAGE}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read() if raw else json.load(response)
    except urllib.error.HTTPError as refused:
        if refused.code == 404 and raw:
            return None
        if refused.code == 410:
            raise Gone from None
        if refused.code in (401, 403):
            raise Failed("contacts_refused") from None
        raise Failed("contacts_unreachable") from None
    except OSError, ValueError:
        raise Failed("contacts_unreachable") from None


def _folders(token: str, url: str, depth: int = 0) -> list[tuple[str, str]]:
    found = []
    while url:
        page = _get(token, url)
        for folder in page.get("value", []):
            found.append((folder["id"], folder.get("displayName", "")))
            if depth < DEPTH:
                quoted = urllib.parse.quote(folder["id"], safe="")
                inside = f"{GRAPH}/me/contactFolders/{quoted}/childFolders"
                found += _folders(token, inside, depth + 1)
        url = page.get("@odata.nextLink", "")
    return found


def books(account: Account, token: str) -> list[Book]:
    """The account's address books as Graph lists them now; the default one has no id."""
    listed = [("", ""), *_folders(token, f"{GRAPH}/me/contactFolders")]
    for server_id, name in listed:
        Book.objects.update_or_create(account=account, server_id=server_id, defaults={"name": name})
    account.contact_books.exclude(server_id__in=[each for each, _ in listed]).delete()
    return list(account.contact_books.order_by("server_id"))


def card(given: dict) -> Card:
    found = Card()
    for name, field in NAMES.items():
        found.fields[field] = (given.get(name) or "").strip()
    if birthday := given.get("birthday"):
        found.fields["birthday"] = birthday[:10]
    for each in given.get("emailAddresses") or []:
        if "@" in (address := (each.get("address") or "").strip()):
            found.points.append({"kind": "email", "label": "", "value": address, "parts": []})
    numbers = [(given.get("mobilePhone"), "mobile")]
    numbers += [(each, "work") for each in given.get("businessPhones") or []]
    numbers += [(each, "home") for each in given.get("homePhones") or []]
    for number, label in numbers:
        if number := (number or "").strip():
            found.points.append({"kind": "phone", "label": label, "value": number, "parts": []})
    for name, label in ADDRESSES:
        place = given.get(name) or {}
        parts = ["", ""] + [
            (place.get(key) or "").strip()
            for key in ("street", "city", "state", "postalCode", "countryOrRegion")
        ]
        if any(parts):
            found.points.append(
                {"kind": "address", "label": label, "value": address_text(parts), "parts": parts}
            )
    if page := (given.get("businessHomePage") or "").strip():
        found.points.append({"kind": "url", "label": "work", "value": page, "parts": []})
    return found


def _start(book: Book) -> str:
    if not book.server_id:
        return f"{GRAPH}/me/contacts/delta"
    return f"{GRAPH}/me/contactFolders/{urllib.parse.quote(book.server_id, safe='')}/contacts/delta"


def caught_up(account: Account, token: str, book: Book) -> int:
    """Takes the contacts new in the folder since its delta link; how many were taken."""
    count, url = 0, book.key or _start(book)
    while True:
        try:
            page = _get(token, url)
        except Gone:
            if url == _start(book):
                raise Failed("contacts_unreachable") from None
            url = _start(book)
            continue
        for given in page.get("value", []):
            if "@removed" in given or not given.get("id"):
                continue
            item = given["id"]
            if Taken.objects.filter(
                owner_id=account.owner_id,
                kind=Taken.Kind.MICROSOFT,
                source=account.address,
                item=item[:500],
            ).exists():
                continue
            found = card(given)
            quoted = urllib.parse.quote(item, safe="")
            found.photo = _get(token, f"{GRAPH}/me/contacts/{quoted}/photo/$value", raw=True)
            kept = {key: value for key, value in given.items() if not key.startswith("@")}
            if taking.taken(
                account.owner_id, account, Taken.Kind.MICROSOFT, account.address, item, found, kept
            ):
                count += 1
        if next_page := page.get("@odata.nextLink"):
            url = next_page
            continue
        book.key = page.get("@odata.deltaLink", "")
        Book.objects.filter(pk=book.pk).update(key=book.key, error="")
        return count


def taken(account: Account) -> int:
    """Takes the account's new contacts from each of its folders; how many were taken."""
    token = signin.graph(account)
    return sum(caught_up(account, token, book) for book in books(account, token))
