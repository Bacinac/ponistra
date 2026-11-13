"""What a contact shows (D15, S4): its own values, and while the organisation's directory lists
the colleague, the directory's work details and numbers beside them, which are read from it and
never kept as the user's own."""

import io
import uuid
from logging import getLogger

from django.db import transaction
from django.db.models import Max
from PIL import Image, ImageOps

from apps.blobs import store
from apps.blobs.models import Blob
from apps.reader import client
from apps.search.pdf import folded

from . import numbers
from .models import Contact, Entry, Gone, Point, ordered, revised
from .vcard import FIELDS, Card, shown_name

log = getLogger(__name__)

# The directory's values a colleague's own do not stand in front of.
WORK = {"title": "title", "organisation": "company"}
# The side of the picture beside a name in the list, in pixels: its 36 points on a screen of two
# pixels a point and a little over.
AVATAR = 96


def latest(owner) -> int:
    """The newest change to the owner's address book."""
    return max(
        Contact.objects.filter(owner=owner).aggregate(last=Max("revision"))["last"] or 0,
        Gone.objects.filter(owner=owner).aggregate(last=Max("revision"))["last"] or 0,
    )


def gone(owner, since: int, now: int) -> list[str]:
    """The hrefs of the contacts deleted after the revision `since` up to `now`, and not made again
    under the same href since."""
    live = Contact.objects.filter(owner=owner).values("href")
    return list(
        Gone.objects.filter(owner=owner, revision__gt=since, revision__lte=now)
        .exclude(href__in=live)
        .values_list("href", flat=True)
        .distinct()
    )


def key(kind: str, value: str) -> str:
    if kind == Point.Kind.EMAIL:
        return value.strip().lower()
    if kind == Point.Kind.PHONE:
        return numbers.key(value)
    return ""


def kept(kind: str, value: str) -> str:
    """The value as the address book keeps it: a number written the one way, an address in lower
    case."""
    if kind == Point.Kind.PHONE:
        return numbers.written(value)
    if kind == Point.Kind.EMAIL:
        return value.strip().lower()
    return value


def person(fields: dict) -> str:
    """The name by which sources are told to mean one person: their own, else one made from its
    parts, without case or accents; empty where it is one word, which tells too little."""
    name = fields.get("name") or " ".join(
        fields.get(key, "") for key in ("prefix", "given", "middle", "family", "suffix")
    )
    words = folded(name).replace("đ", "d").split()
    return " ".join(words) if len(words) > 1 else ""


def listed(entry: Entry | None) -> tuple[dict, list[dict]]:
    """The values the directory gives of a colleague it lists."""
    if entry is None or not entry.listed:
        return {}, []
    fields = {
        "name": entry.name,
        "given": entry.given,
        "family": entry.family,
        "title": entry.title,
        "organisation": entry.company,
    }
    points = [{"kind": "email", "label": "work", "value": entry.address, "parts": []}]
    for label, number in (("work", entry.phone), ("mobile", entry.mobile), ("home", entry.home)):
        if number:
            points.append({"kind": "phone", "label": label, "value": number, "parts": []})
    return {name: value for name, value in fields.items() if value}, points


def avatar(path) -> bytes | None:
    """The photo drawn small as the list shows it, or None for one that is no picture; in the
    reader."""
    try:
        with Image.open(path) as opened:
            opened.draft("RGB", (AVATAR, AVATAR))
            image = ImageOps.fit(ImageOps.exif_transpose(opened), (AVATAR, AVATAR))
    except (OSError, Image.DecompressionBombError) as failed:
        log.warning("%s draws no avatar: %s", path, failed)
        return None
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
    out = io.BytesIO()
    image.save(out, "WEBP", quality=75)
    return out.getvalue()


def pictured(contact: Contact, photo: Blob | None) -> None:
    contact.photo = photo
    contact.avatar = None if photo is None else client.ask("avatar", store.path_of(photo.sha256))


def _photo(contact: Contact) -> bytes | None:
    if contact.photo_id is None:
        return None
    return store.path_of(contact.photo.sha256).read_bytes()


def own_points(contact: Contact) -> list[dict]:
    return [
        {"kind": each.kind, "label": each.label, "value": each.value, "parts": each.parts}
        for each in contact.points.all()
    ]


def card(contact: Contact, photo: bool = True) -> Card:
    """The contact as a phone reads it: its own values, the directory's filling what they leave
    out and standing first for a colleague's work."""
    fields = {name: getattr(contact, name) for name in FIELDS}
    points = own_points(contact)
    given, directory = listed(contact.entry)
    for name, value in given.items():
        if name in WORK or not fields[name]:
            fields[name] = value
    if given and not contact.name and (contact.given or contact.family):
        fields["name"] = ""
    held = {key(each["kind"], each["value"]) for each in points}
    points += [each for each in directory if key(each["kind"], each["value"]) not in held]
    return Card(
        fields=fields,
        points=points,
        uid=contact.uid,
        photo=_photo(contact) if photo else None,
        extra=list(contact.extra),
        group=contact.group,
    )


def _points(contact: Contact, given: list[dict]) -> None:
    contact.points.all().delete()
    Point.objects.bulk_create(
        Point(
            contact=contact,
            kind=each["kind"],
            label=each.get("label", "")[:100],
            value=kept(each["kind"], each["value"]),
            parts=each.get("parts") or [],
            key=key(each["kind"], each["value"])[:320],
            position=position,
        )
        for position, each in enumerate(given)
    )


def _own(contact: Contact, given: Card) -> tuple[dict, list[dict]]:
    """What of a card a phone gives back is the user's own: what it changed of what it read,
    and not the directory's values it read beside theirs."""
    served = card(contact, photo=False)
    fields = {}
    for name in FIELDS:
        value = given.fields.get(name, "")
        before = shown_name(served.fields, served.points) if name == "name" else served.fields[name]
        fields[name] = getattr(contact, name) if value == before else value
    _, directory = listed(contact.entry)
    theirs = {key(each["kind"], each["value"]) for each in directory}
    mine = {key(each.kind, each.value) for each in contact.points.all()}
    points = [
        each
        for each in given.points
        if (found := key(each["kind"], each["value"])) not in theirs or found in mine
    ]
    return fields, points


@transaction.atomic
def saved(
    contact: Contact,
    given: Card,
    phone: bool = False,
    photo: bool = True,
    starred: bool | None = None,
) -> Contact:
    """Keeps the card as the contact's own values: all of them as the user wrote them here, or
    what a phone changed of what it read. `photo` False leaves the photo as it is, and `starred`
    None whether it is a favourite, which no vCard tells."""
    ordered(contact.owner_id)
    if starred is not None:
        contact.starred = starred
    fields, points = _own(contact, given) if phone and contact.pk else (given.fields, given.points)
    for name, value in fields.items():
        setattr(contact, name, value[: Contact._meta.get_field(name).max_length or None])
    contact.extra = given.extra
    contact.group = given.group
    if photo:
        pictured(contact, store.put(io.BytesIO(given.photo)) if given.photo else None)
    if contact.pk:
        contact.revision = revised()
    contact.save()
    _points(contact, points)
    contact.refresh_from_db(fields=["revision"])
    return contact


def made(owner_id: int, given: Card, href: str = "", starred: bool = False) -> Contact:
    uid = given.uid or str(uuid.uuid4())
    contact = Contact(owner_id=owner_id, uid=uid[:255], href=href or f"{uid}.vcf")
    return saved(contact, given, starred=starred)


@transaction.atomic
def deleted(contact: Contact) -> None:
    ordered(contact.owner_id)
    Gone.objects.create(owner_id=contact.owner_id, href=contact.href)
    contact.delete()
