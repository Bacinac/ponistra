"""A Google account's contacts through Google's CardDAV (RFC 6352, D15, S4), signed in as the
account's mail is: with its app password, or with the token its Google sign-in consented to. Each
address book is listed and its new cards only are taken."""

import urllib.parse
from logging import getLogger
from xml.etree import ElementTree as ET

from apps.dav import client
from apps.dav.protocol import card as c
from apps.dav.protocol import d, element
from apps.mail import signin
from apps.mail.models import Account, Provider

from . import taking
from .models import Book, Taken
from .vcard import Malformed, parsed

ROOT = "https://www.googleapis.com"
IMAP = signin.WAYS[Provider.GOOGLE].imap[0]
PAGE = 100
log = getLogger(__name__)


def _asked(authorization: str, method: str, path: str, body: ET.Element, depth: str) -> ET.Element:
    return client.asked("contacts", authorization, method, ROOT + path, body, depth)


def _propfind(authorization: str, path: str, depth: str, *names: str) -> list:
    return client.found(_asked(authorization, "PROPFIND", path, client.wanted(*names), depth))


def books(account: Account, authorization: str) -> list[Book]:
    """The account's address books as Google lists them now, each by its path."""
    home = f"/carddav/v1/principals/{urllib.parse.quote(account.username, safe='@')}/lists/"
    listed = [
        (path, held.findtext(d("displayname"), ""))
        for path, held in _propfind(authorization, home, "1", d("resourcetype"), d("displayname"))
        if held.find(f"{d('resourcetype')}/{c('addressbook')}") is not None
    ]
    for server_id, name in listed:
        Book.objects.update_or_create(account=account, server_id=server_id, defaults={"name": name})
    account.contact_books.exclude(server_id__in=[each for each, _ in listed]).delete()
    return list(account.contact_books.order_by("server_id"))


def caught_up(account: Account, authorization: str, book: Book) -> int:
    """Takes the cards new in the book; how many were taken. Google's sync token is new at every
    asking and its ctag differs between its servers, so neither tells whether the book changed."""
    listed = _propfind(authorization, book.server_id, "1", d("getetag"))
    paths = [path for path, _ in listed if not path.endswith("/")]
    given = Taken.objects.filter(
        owner_id=account.owner_id, kind=Taken.Kind.GOOGLE, source=account.address
    )
    before = set(given.filter(item__in=paths).values_list("item", flat=True))
    new, count = [path for path in paths if path not in before], 0
    for start in range(0, len(new), PAGE):
        asked = element(
            c("addressbook-multiget"),
            element(d("prop"), element(c("address-data"))),
            *(element(d("href"), text=path) for path in new[start : start + PAGE]),
        )
        for path, held in client.found(_asked(authorization, "REPORT", book.server_id, asked, "1")):
            text = held.findtext(c("address-data"), "")
            try:
                found = parsed(text)
            except Malformed as malformed:
                log.warning("contacts: %s gave %s unread: %s", account.address, path, malformed)
                continue
            if taking.taken(
                account.owner_id,
                account,
                Taken.Kind.GOOGLE,
                account.address,
                path,
                found,
                {"vcard": text},
            ):
                count += 1
    return count


def taken(account: Account) -> int:
    """Takes the account's new contacts from each of its address books; how many were taken."""
    authorization = client.authorization(account)
    return sum(caught_up(account, authorization, book) for book in books(account, authorization))
