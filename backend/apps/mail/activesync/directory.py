"""The people HCL Traveler names as Domino does, `Ana Horvat/Firma`, found in the directory of
the organisation's server by their common name, so that a reply reaches them. Traveler answers
no ResolveRecipients; the directory's search it does answer."""

from collections.abc import Callable
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from .. import taking
from ..models import Account, Named
from .client import Session
from .wbxml import element as e

# A name the directory did not know is asked again a day later: a colleague who has just joined.
AGAIN = timedelta(days=1)
# Enough to tell one person of the name from several.
MOST = 10
# Traveler's stand-in for an entry with no internet address, a group among them: its Domino name
# in base32 at a domain no mail reaches.
UNREACHED = ".noninternet.sub"
DETAILS = {
    "given": "FirstName",
    "family": "LastName",
    "title": "Title",
    "company": "Company",
    "office": "Office",
    "phone": "Phone",
    "mobile": "MobilePhone",
    "home": "HomePhone",
}


def searched(client: Session, query: str, most: int = MOST) -> list[dict] | None:
    """The people the directory finds by the query, each a name, an address mail reaches and what
    else it gives of them; None where it did not answer the search."""
    answer = client.command(
        "Search",
        e(
            "Search:Search",
            e(
                "Search:Store",
                e("Search:Name", "GAL"),
                e("Search:Query", query),
                e("Search:Options", e("Search:Range", f"0-{most - 1}")),
            ),
        ),
    )
    store = answer.find("Response/Store")
    if answer.text("Status") != "1" or store is None or store.text("Status") != "1":
        return None
    found = []
    for each in store.findall("Result"):
        address = each.text("Properties/EmailAddress")
        if "@" in address and not address.endswith(UNREACHED):
            person = {"name": each.text("Properties/DisplayName"), "address": address}
            for key, name in DETAILS.items():
                person[key] = each.text(f"Properties/{name}").strip()
            found.append(person)
    return found


def found(client: Session, name: str) -> str | None:
    """The address of the one person the directory lists by the common name, "" where it lists
    none or several, or None where it did not answer the search."""
    people = searched(client, name)
    if people is None:
        return None
    addresses = {each["address"] for each in people if each["name"].casefold() == name.casefold()}
    return addresses.pop() if len(addresses) == 1 else ""


def named(client: Session, host: str) -> Callable[[str], str]:
    """The address of a person the server names as Domino does, from what its directory gave
    before or gives now; "" where it knows none."""

    def address(name: str) -> str:
        common = taking.common(name)
        if common is None:
            return ""
        known = Named.objects.filter(host=host, name=name).first()
        if known and (known.address or known.asked_at > timezone.now() - AGAIN):
            return known.address
        given = found(client, common)
        if given is None:
            return ""
        Named.objects.update_or_create(
            host=host, name=name, defaults={"address": given, "asked_at": timezone.now()}
        )
        return given

    return address


def unnamed(account: Account) -> list[str]:
    """The Domino names the mail taken from the account still holds in place of addresses."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT person->>'address'
            FROM mail_message m,
                jsonb_array_elements(m."to" || m.cc || m.reply_to || jsonb_build_array(m.sender))
                AS person
            WHERE m.owner_id = %s
                AND EXISTS (
                    SELECT 1 FROM mail_arrival a JOIN mail_source s ON s.id = a.source_id
                    WHERE a.message_id = m.id AND s.account_id = %s
                )
                AND person->>'address' LIKE '%%/%%'
            """,
            [account.owner_id, account.pk],
        )
        given = [address for (address,) in cursor.fetchall()]
    return [each for each in given if taking.common(each)]


def again(client: Session, account: Account) -> int:
    """Finds the addresses of the Domino names the account's mail still holds; how many messages
    changed."""
    address = named(client, account.activesync_host)
    found = {name: given for name in unnamed(account) if (given := address(name))}
    return taking.renamed(account.owner_id, found) if found else 0
