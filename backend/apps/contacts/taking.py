"""A source's contacts taken into the user's address book (D15, S4), one way: each item once, a
person once. What a source gives joins the contact holding one of its addresses, else the one
person holding one of its numbers, else the one person of the same name; two items of one source
are never one contact. Google's name
stands in front of another source's, as Google holds the names as the user wrote them on their
phone, diacritics and all; a name the user wrote here stays."""

import io
import uuid

from django.db import transaction
from django.db.models import Exists, OuterRef

from apps.blobs import store
from apps.mail.models import Account

from . import cards
from .models import Contact, Entry, Point, Taken, ordered, revised
from .vcard import FIELDS, Card

NAMES = ("name", "prefix", "given", "middle", "family", "suffix")


def data(card: Card, given: dict) -> dict:
    """What a source gave, as it came and as PONISTRA reads it."""
    return {"given": given, "fields": card.fields, "points": card.points}


def _of(owner_id: int, kind: str, source: str):
    taken = Taken.objects.filter(contact=OuterRef("pk"), kind=kind, source=source)
    return Contact.objects.filter(owner_id=owner_id, group=False).exclude(Exists(taken))


def _found(owner_id: int, kind: str, source: str, card: Card) -> Contact | None:
    others = _of(owner_id, kind, source)
    keyed = [(each["kind"], cards.key(each["kind"], each["value"])) for each in card.points]
    addresses = {value for point, value in keyed if point == Point.Kind.EMAIL and value}
    if addresses:
        held = Point.objects.filter(kind=Point.Kind.EMAIL, key__in=addresses)
        found = others.filter(Exists(held.filter(contact=OuterRef("pk")))).order_by("pk").first()
        if found:
            return found
    for number in dict.fromkeys(value for point, value in keyed if point == Point.Kind.PHONE):
        if not number:
            continue
        holders = list(
            Point.objects.filter(contact__owner_id=owner_id, kind=Point.Kind.PHONE, key=number)
            .values_list("contact_id", flat=True)
            .distinct()[:2]
        )
        if len(holders) == 1 and (found := others.filter(pk=holders[0]).first()):
            return found
    if (wanted := cards.person(card.fields)) and len(alike := _named(owner_id, wanted)) == 1:
        return others.filter(pk=alike[0]).first()
    return None


def _named(owner_id: int, wanted: str) -> list[int]:
    """The owner's people of the name, the directory's name standing for a colleague's own where
    they have none."""
    alike = []
    for each in Contact.objects.filter(owner_id=owner_id, group=False).select_related("entry"):
        fields = {name: getattr(each, name) for name in NAMES}
        given, _ = cards.listed(each.entry)
        for name in NAMES:
            if not fields[name] and given.get(name):
                fields[name] = given[name]
        if cards.person(fields) == wanted:
            alike.append(each.pk)
    return alike


def _named_elsewhere(contact: Contact) -> bool:
    """Whether the contact's name is one a source other than Google gave it, unchanged since."""
    taken = list(contact.taken.all())
    if any(each.kind == Taken.Kind.GOOGLE for each in taken):
        return False
    given = [each.data.get("fields", {}) for each in taken]
    return all(
        any(fields.get(name) == value for fields in given)
        for name in NAMES
        if (value := getattr(contact, name))
    )


def joined(contact: Contact, card: Card, foremost: bool = False) -> None:
    """Fills what the contact leaves out with what the card gives, and adds the card's ways to
    reach them that the contact has not. A foremost card's name replaces one another source
    gave."""
    changed = False
    named = foremost and any(card.fields.get(name) for name in NAMES) and _named_elsewhere(contact)
    for name in FIELDS:
        value = card.fields.get(name, "")[: Contact._meta.get_field(name).max_length]
        if (named and name in NAMES and value != getattr(contact, name)) or (
            value and not getattr(contact, name)
        ):
            setattr(contact, name, value)
            changed = True
    if card.photo and contact.photo_id is None:
        cards.pictured(contact, store.put(io.BytesIO(card.photo)))
        changed = True
    held = {(each.kind, each.key or each.value) for each in contact.points.all()}
    position = contact.points.count()
    for each in card.points:
        found = cards.key(each["kind"], each["value"])
        if (each["kind"], found or each["value"]) in held:
            continue
        held.add((each["kind"], found or each["value"]))
        Point.objects.create(
            contact=contact,
            kind=each["kind"],
            label=each.get("label", "")[:100],
            value=cards.kept(each["kind"], each["value"]),
            parts=each.get("parts") or [],
            key=found[:320],
            position=position,
        )
        position += 1
        changed = True
    if changed:
        contact.revision = revised()
        contact.save()


def _entry(owner_id: int, contact: Contact) -> None:
    """Links the contact to the directory entry one of its addresses has, at a server one of its
    owner's accounts reaches."""
    if contact.entry_id is not None:
        return
    hosts = Account.objects.filter(
        owner_id=owner_id, protocol=Account.Protocol.ACTIVESYNC
    ).values_list("activesync_host", flat=True)
    addresses = contact.points.filter(kind=Point.Kind.EMAIL).values_list("key", flat=True)
    entry = Entry.objects.filter(host__in=hosts, address__in=addresses, listed=True).first()
    if entry is not None:
        Contact.objects.filter(pk=contact.pk).update(entry=entry, revision=revised())
        contact.refresh_from_db(fields=["entry", "revision"])


@transaction.atomic
def taken(
    owner_id: int, account, kind: str, source: str, item: str, card: Card, given: dict
) -> Contact | None:
    """The contact the source's item joined or made; None where the item was taken before."""
    ordered(owner_id)
    taking = Taken(
        owner_id=owner_id,
        account=account,
        kind=kind,
        source=source,
        item=item[:500],
        data=data(card, given),
    )
    if Taken.objects.filter(owner_id=owner_id, kind=kind, source=source, item=taking.item).exists():
        return None
    found = _found(owner_id, kind, source, card)
    if found is None:
        uid = str(uuid.uuid4())
        card.uid, card.extra, card.group = uid, [], False
        found = cards.saved(Contact(owner_id=owner_id, uid=uid, href=f"{uid}.vcf"), card)
    else:
        joined(found, card, foremost=kind == Taken.Kind.GOOGLE)
    taking.contact = found
    taking.save()
    _entry(owner_id, found)
    return found


@transaction.atomic
def colleague(owner_id: int, entry: Entry, chosen: bool = False) -> Contact | None:
    """The contact a colleague the directory confirmed became, or joined; None where the
    directory gave them to the user before, whether or not the user kept them, unless the user
    chose them now."""
    ordered(owner_id)
    given = Taken.objects.filter(
        owner_id=owner_id, kind=Taken.Kind.DIRECTORY, source=entry.host, item=entry.address
    ).first()
    if given is not None and (not chosen or given.contact_id is not None):
        return given.contact if chosen else None
    points = [{"kind": "email", "label": "work", "value": entry.address, "parts": []}]
    card = Card(points=points)
    found = _found(owner_id, Taken.Kind.DIRECTORY, entry.host, card)
    if found is None:
        uid = str(uuid.uuid4())
        card.uid = uid
        found = cards.saved(Contact(owner_id=owner_id, uid=uid, href=f"{uid}.vcf"), card)
    Contact.objects.filter(pk=found.pk).update(entry=entry, revision=revised())
    found.refresh_from_db(fields=["entry", "revision"])
    if given is not None:
        Taken.objects.filter(pk=given.pk).update(contact=found)
        return found
    Taken.objects.create(
        owner_id=owner_id,
        contact=found,
        kind=Taken.Kind.DIRECTORY,
        source=entry.host,
        item=entry.address,
        data={"given": {"address": entry.address, "name": entry.name}},
    )
    return found


@transaction.atomic
def revise(entry: Entry) -> None:
    """Gives each contact the directory's changed entry stands beside a new revision, by which
    phones learn it changed."""
    ordered(*entry.contacts.values_list("owner_id", flat=True))
    entry.contacts.update(revision=revised())
