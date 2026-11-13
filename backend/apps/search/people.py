"""People found by the search box (D21): the user's contacts, then the installation's people
and the organisation's directory where no contact already names them."""

from apps.contacts import search
from apps.contacts.views import summary

from .query import Asked


def plain(text: str) -> str:
    """The words without the search operators, which a name is never typed with."""
    words = text.replace('"', " ").split()
    return " ".join(each for each in words if not each.startswith("-") and each.lower() != "or")


def _colleague(user) -> dict:
    name = f"{user.first_name} {user.last_name}".strip()
    return {
        "kind": "colleague",
        "id": user.pk,
        "name": name or user.email,
        "organisation": "",
        "title": "",
        "email": user.email,
        "phone": "",
        "photo": None,
    }


def _listed(entry) -> dict:
    return {
        "kind": "directory",
        "id": entry.pk,
        "name": entry.name or " ".join(filter(None, [entry.given, entry.family])) or entry.address,
        "organisation": entry.company,
        "title": entry.title,
        "email": entry.address,
        "phone": entry.phone or entry.mobile,
        "photo": None,
    }


def found_people(user, wanted: Asked, limit: int) -> list[dict]:
    typed = plain(wanted.text)
    contacts = search.matching(user.pk, typed)
    if not typed:
        contacts = contacts.order_by("-changed_at")
    found = [{"kind": "contact", **summary(each)} for each in contacts[:limit]]
    if not typed:
        return found
    known = {each["email"].lower() for each in found if each["email"]}
    for make, people in (
        (_colleague, search.colleagues(user, typed)),
        (_listed, search.listed(user, typed)),
    ):
        for person in people[: limit - len(found) + len(known)]:
            if len(found) >= limit:
                break
            made = make(person)
            if made["email"].lower() in known:
                continue
            known.add(made["email"].lower())
            found.append(made)
    return found
