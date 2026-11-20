"""The tabs a meeting means to share, named for the user who reads them: a page of this
installation by its title, a link of theirs by its name, and a board marked to go on the stage.
A page is known by the id its address ends in, whatever name the installation goes by there."""

import re
import uuid
from urllib.parse import urlsplit

from django.db.models.expressions import RawSQL

from apps.access import rights
from apps.documents import boards
from apps.documents.models import Node
from apps.documents.printing import DIGITS

PLACE = re.compile(r"/[dfp]/(?:[a-z0-9-]*-)?([0-9A-Za-z]{22})/?")


def _placed(address: str) -> uuid.UUID | None:
    found = PLACE.fullmatch(urlsplit(address).path)
    if found is None:
        return None
    value = 0
    for digit in found[1]:
        value = value * 62 + DIGITS.index(digit)
    return uuid.UUID(int=value) if value >> 128 == 0 else None


def named(user, addresses: list[str]) -> list[dict]:
    placed = {address: _placed(address) for address in addresses}
    readable, params = rights.readable(user)
    seen = Node.objects.filter(pk__in=RawSQL(readable, params))
    pages = {
        node.pk: node
        for node in seen.filter(pk__in=[pk for pk in placed.values() if pk]).select_related("blob")
    }
    links = dict(seen.filter(kind=Node.Kind.LINK, href__in=addresses).values_list("href", "title"))
    tabs = []
    for address in addresses:
        node = pages.get(placed[address])
        tabs.append(
            {
                "address": address,
                "title": node.title if node else links.get(address),
                "board": str(node.pk) if node and boards.is_board(node) else None,
            }
        )
    return tabs
