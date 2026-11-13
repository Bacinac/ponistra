"""The user's contacts found as they type (D15, S4): those a word of whose name, firm, title or
way to reach them begins with what they typed. A number is found by its E.164 as well, so `091`
finds `+385 91 234 5678`."""

import re

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import F, OuterRef, StringAgg, Subquery, TextField, Value
from django.db.models.functions import Coalesce, Concat

from apps.mail.models import Account
from apps.search.pdf import folded
from apps.search.text import Folded
from apps.users.models import User

from . import cards, numbers
from .models import Contact, Entry, Point
from .vcard import shown_name

OWN = ("name", "given", "family", "nickname", "organisation", "department", "title")
LISTED = ("name", "title", "company")
# Contacts weighed for the addresses offered while writing a message.
WEIGHED = 50
NUMBER = re.compile(r"\+?\d+")


def _words() -> Folded:
    points = (
        Point.objects.filter(contact=OuterRef("pk"))
        .values("contact")
        .annotate(joined=StringAgg(Concat("value", Value(" "), "key"), Value(" ")))
        .values("joined")
    )
    parts = [F(name) for name in OWN]
    parts += [Coalesce(F(f"entry__{name}"), Value("")) for name in LISTED]
    parts.append(Coalesce(Subquery(points), Value(""), output_field=TextField()))
    spaced = [each for part in parts for each in (part, Value(" "))][:-1]
    return Folded(Concat(*spaced, output_field=TextField()))


def narrowed(found, words, typed: str):
    """The rows whose words hold each word typed at the start of one of theirs."""
    if typed_words := folded(typed).replace("đ", "d").split():
        found = found.alias(words=words)
        for word in typed_words:
            if NUMBER.fullmatch(word):
                word = numbers.typed(word)
            found = found.filter(words__regex=rf"\m{re.escape(word)}")
    return found


def matching(owner_id: int, typed: str):
    """The owner's contacts matching what they typed, all of them where they typed nothing."""
    found = Contact.objects.filter(owner_id=owner_id, group=False)
    return narrowed(found, _words(), typed).select_related("entry").prefetch_related("points")


def colleagues(user, typed: str):
    """The installation's people matching what the user typed, by name or address."""
    found = User.objects.filter(is_active=True).exclude(pk=user.pk)
    words = Folded(
        Concat("first_name", Value(" "), "last_name", Value(" "), "email", output_field=TextField())
    )
    return narrowed(found, words, typed).order_by("first_name", "last_name", "email")


def listed(user, typed: str):
    """The people of the user's organisation's directories matching what they typed."""
    hosts = Account.objects.filter(owner=user, contact_directory__isnull=False).values_list(
        "activesync_host", flat=True
    )
    found = Entry.objects.filter(host__in=hosts, listed=True)
    parts = ("name", "given", "family", "title", "company", "address", "phone", "mobile")
    spaced = [each for name in parts for each in (F(name), Value(" "))][:-1]
    words = Folded(Concat(*spaced, output_field=TextField()))
    return narrowed(found, words, typed).order_by("name", "address")


def addresses(user, typed: str, most: int) -> list[dict]:
    """The addresses of the user's contacts matching what they typed, those they wrote to most
    first."""
    if not typed.strip():
        return []
    found = []
    for contact in matching(user.pk, typed)[:WEIGHED]:
        shown = cards.card(contact, photo=False)
        name = shown_name(shown.fields, [])
        found += [
            {"name": name, "address": each["value"]}
            for each in shown.points
            if each["kind"] == Point.Kind.EMAIL
        ]
    counted = {
        address: (written, heard)
        for address, written, heard in user.mail_correspondents.filter(
            address__in=[each["address"].lower() for each in found]
        ).values_list("address", "written", "heard")
    }
    found.sort(key=lambda each: [-count for count in counted.get(each["address"].lower(), (0, 0))])
    return found[:most]


# How alike a spoken name must be to a contact's to be them, and how far ahead of the next one
# it must be to be taken without asking.
LIKE = 0.3
AHEAD = 0.15
SPOKEN = 5


def spoken(user, name: str) -> list[dict]:
    """The user's contacts whose name is like the one said, the likest first; the likest alone
    where it is clearly them. Speech to text writes names it does not know by their sound."""
    found = list(
        Contact.objects.filter(owner=user, group=False)
        .annotate(like=TrigramSimilarity(Folded("name"), folded(name)))
        .filter(like__gte=LIKE)
        .order_by("-like", "name")[:SPOKEN]
    )
    if len(found) > 1 and found[0].like - found[1].like >= AHEAD:
        found = found[:1]
    return [{"id": each.pk, "name": each.name} for each in found]
