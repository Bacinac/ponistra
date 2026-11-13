"""The user's address book (D15, S4): one contact a person, whichever accounts brought them, and
the colleagues the directories of their organisations find."""

import base64
import binascii
import re
from functools import partial

import icu
from django.db import transaction
from django.http import HttpResponse, JsonResponse

from apps.blobs import store
from apps.blobs.views import serve
from apps.content.views import stored
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database, waited
from apps.mail import sharing
from apps.mail.imap import Failed
from apps.mail.models import Account
from apps.users.models import User

from . import cards, directory, search
from .models import Book, Contact, Point, ordered, revised
from .models import Directory as Listing
from .vcard import FIELDS, Card, address_text, shown_name

PHOTOS = {kind: suffix for kind, suffix in store.IMAGES.items() if kind != "image/svg+xml"}
BIRTHDAY = re.compile(r"(\d{4}|-)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
POINTS = 100
LABEL = 100
VALUE = 2000
NOTE = 20000
ADDRESS_PARTS = 7
HREF = Contact._meta.get_field("href").max_length
NAMES = ("name", "prefix", "given", "middle", "family", "suffix")
BY_NAME = icu.Collator.createInstance(icu.Locale("hr"))
CONTACT = sharing.owned_by(Contact)


def summary(contact: Contact) -> dict:
    shown = cards.card(contact, photo=False)
    first = {}
    for each in shown.points:
        first.setdefault(each["kind"], each["value"])
    return {
        "id": contact.pk,
        "name": shown_name(shown.fields, shown.points),
        "organisation": shown.fields["organisation"],
        "title": shown.fields["title"],
        "email": first.get(Point.Kind.EMAIL, ""),
        "phone": first.get(Point.Kind.PHONE, ""),
        "photo": contact.photo_id,
        "colleague": contact.entry_id is not None and contact.entry.listed,
        "starred": contact.starred,
    }


def _avatar(contact: Contact) -> str | None:
    if contact.avatar is None:
        return None
    return f"data:image/webp;base64,{base64.b64encode(contact.avatar).decode()}"


def _described(contact: Contact) -> dict:
    fields, points = cards.listed(contact.entry)
    return {
        **summary(contact),
        "fields": {name: getattr(contact, name) for name in FIELDS},
        "points": cards.own_points(contact),
        "directory": {"host": contact.entry.host, "fields": fields, "points": points}
        if fields or points
        else None,
        "sources": [
            {"kind": each.kind, "source": each.source, "taken_at": each.taken_at}
            for each in contact.taken.order_by("taken_at", "pk")
        ],
        "changed_at": contact.changed_at,
    }


def _loaded(user, pk: int) -> Contact:
    found = (
        Contact.objects.select_related("entry")
        .prefetch_related("points")
        .filter(pk=pk, owner=user, group=False)
        .first()
    )
    if found is None:
        raise Refused(404, "not_found")
    return found


def _points(given) -> list[dict]:
    if not isinstance(given, list) or len(given) > POINTS:
        raise Refused(400, "invalid_points")
    found = []
    for each in given:
        if not isinstance(each, dict) or each.get("kind") not in Point.Kind.values:
            raise Refused(400, "invalid_points")
        label, value, parts = each.get("label", ""), each.get("value", ""), each.get("parts", [])
        if not isinstance(label, str) or not isinstance(value, str) or not isinstance(parts, list):
            raise Refused(400, "invalid_points")
        if each["kind"] == Point.Kind.ADDRESS:
            if len(parts) > ADDRESS_PARTS or not all(isinstance(part, str) for part in parts):
                raise Refused(400, "invalid_points")
            parts = [part.strip() for part in parts] + [""] * (ADDRESS_PARTS - len(parts))
            value = address_text(parts)
        else:
            parts = []
        value = value.strip()
        if len(label) > LABEL or len(value) > VALUE:
            raise Refused(400, "invalid_points")
        if value:
            label = label.strip()
            found.append({"kind": each["kind"], "label": label, "value": value, "parts": parts})
    return found


def _card(data: dict, contact: Contact | None) -> Card:
    given = data.get("fields")
    if not isinstance(given, dict):
        raise Refused(400, "invalid_fields")
    fields = {}
    for name in FIELDS:
        value = given.get(name, "")
        limit = Contact._meta.get_field(name).max_length or NOTE
        if not isinstance(value, str) or len(value := value.strip()) > limit:
            raise Refused(400, "invalid_fields")
        fields[name] = value
    if fields["birthday"] and not BIRTHDAY.fullmatch(fields["birthday"]):
        raise Refused(400, "invalid_birthday")
    points = _points(data.get("points", []))
    if not any(fields.values()) and not points and (contact is None or contact.entry_id is None):
        raise Refused(400, "empty_contact")
    if contact is None:
        return Card(fields=fields, points=points)
    return Card(
        fields=fields, points=points, uid=contact.uid, extra=list(contact.extra), group=False
    )


def _failed(user) -> list[dict]:
    """The accounts whose contacts or directory could not be read last time, and why."""
    found = [
        *Book.objects.filter(account__owner=user)
        .exclude(error="")
        .values_list("account__label", "account__address", "error"),
        *Listing.objects.filter(account__owner=user)
        .exclude(error="")
        .values_list("account__label", "account__address", "error"),
    ]
    return [
        {"account": label or address, "error": error}
        for label, address, error in dict.fromkeys(found)
    ]


@api("GET", "POST")
@sharing.boxed()
def contacts(request):
    """The user's contacts matching what they typed, by name, and a new one."""
    if request.method == "POST":
        made = cards.made(request.user.pk, _card(body(request), None))
        return JsonResponse(_described(_loaded(request.user, made.pk)), status=201)
    typed = request.GET.get("q", "").strip()[:200]
    found = [
        {**summary(each), "avatar": _avatar(each)}
        for each in search.matching(request.user.pk, typed)
    ]
    found.sort(key=lambda each: (not each["starred"], BY_NAME.getSortKey(each["name"]), each["id"]))
    directories = [each.address for each in _directories(request.user)]
    boxed = request.user != request.person
    return JsonResponse(
        {
            "contacts": found,
            "failed": _failed(request.user),
            "directories": directories,
            "role": sharing.role_in(request.person, request.user.pk) if boxed else None,
        }
    )


@api("GET", "PATCH", "DELETE")
@sharing.boxed(of=CONTACT)
def contact(request, pk):
    found = _loaded(request.user, pk)
    if request.method == "DELETE":
        cards.deleted(found)
        return HttpResponse(status=204)
    if request.method == "PATCH":
        cards.saved(found, _card(body(request), found), photo=False)
        found = _loaded(request.user, pk)
    return JsonResponse(_described(found))


def _chosen(user, given) -> list[Contact]:
    if not isinstance(given, list) or not given or not all(isinstance(pk, int) for pk in given):
        raise Refused(400, "invalid_contacts")
    return [_loaded(user, pk) for pk in dict.fromkeys(given)]


@api("POST")
@sharing.boxed()
def delete(request):
    with transaction.atomic():
        for found in _chosen(request.user, body(request).get("contacts")):
            cards.deleted(found)
    return HttpResponse(status=204)


@api("POST")
@sharing.boxed()
def star(request):
    """Makes the chosen contacts the user's favourites, or no longer."""
    data = body(request)
    chosen, wanted = _chosen(request.user, data.get("contacts")), data.get("starred")
    if not isinstance(wanted, bool):
        raise Refused(400, "invalid_starred")
    with transaction.atomic():
        ordered(request.user.pk)
        Contact.objects.filter(pk__in=[each.pk for each in chosen]).exclude(starred=wanted).update(
            starred=wanted, revision=revised()
        )
    return HttpResponse(status=204)


@api("GET", "PUT", "DELETE", device=True)
@sharing.boxed(of=CONTACT)
def photo(request, pk):
    found = _loaded(request.user, pk)
    if request.method == "GET":
        if found.photo_id is None:
            raise Refused(404, "not_found")
        return serve(request, found.photo, f"{pk}.{PHOTOS.get(found.photo.media_type, 'img')}")
    blob = stored(request, PHOTOS, "not_a_photo") if request.method == "PUT" else None
    with transaction.atomic():
        ordered(request.user.pk)
        cards.pictured(found, blob)
        Contact.objects.filter(pk=found.pk).update(
            photo=blob, avatar=found.avatar, revision=revised()
        )
    return JsonResponse(_described(_loaded(request.user, pk)))


def _directories(user) -> list[Account]:
    return list(user.mail_accounts.filter(protocol=Account.Protocol.ACTIVESYNC).order_by("address"))


def _known(user, people: list[dict]) -> dict[str, int]:
    """The user's contact each of the people already is, by address."""
    addresses = {each["address"].lower() for each in people}
    held = Point.objects.filter(
        contact__owner=user, contact__group=False, kind=Point.Kind.EMAIL, key__in=addresses
    ).values_list("key", "contact_id")
    linked = Contact.objects.filter(owner=user, entry__address__in=addresses).values_list(
        "entry__address", "pk"
    )
    return {**dict(linked), **dict(held)}


@api("GET", "POST")
@sharing.boxed()
async def colleagues(request):
    """The colleagues the directories of the user's organisations find by the start of a name,
    and the accounts whose directory did not answer; one of them made a contact."""
    accounts = await database(_directories)(request.user)
    if request.method == "POST":
        data = body(request)
        account = next((each for each in accounts if each.pk == data.get("account")), None)
        address, name = data.get("address"), data.get("name", "")
        if account is None or not isinstance(address, str) or "@" not in address:
            raise Refused(400, "invalid_colleague")
        if not isinstance(name, str):
            raise Refused(400, "invalid_colleague")
        try:
            made = await waited(partial(directory.chosen, account, address.strip(), name[:200]))
        except Failed as failed:
            raise Refused(502, failed.code) from None
        if made is None:
            raise Refused(404, "not_listed")
        described = await database(lambda: _described(_loaded(request.user, made.pk)))()
        return JsonResponse(described, status=201)
    typed = request.GET.get("q", "").strip()[:200]
    if len(typed) < 2:
        return JsonResponse({"people": [], "unanswered": []})
    people, unanswered = [], []
    for account in accounts:
        try:
            given = await waited(partial(directory.searched, account, typed))
        except Failed:
            given = None
        if given is None:
            unanswered.append(account.label or account.address)
            continue
        people += [{**each, "account": account.pk} for each in given]
    known = await database(_known)(request.user, people)
    for each in people:
        each["contact"] = known.get(each["address"].lower())
    return JsonResponse({"people": people, "unanswered": unanswered})


def _phone(request) -> None:
    if request.device is None:
        raise Refused(403, "app_password_required")


def _held(user):
    return (
        Contact.objects.filter(owner=user, group=False)
        .select_related("entry", "photo")
        .prefetch_related("points")
    )


def _served(contact: Contact) -> dict:
    """The contact as the phone holds it: as a phone reads it, by the href that names it there."""
    shown = cards.card(contact, photo=False)
    named = any(shown.fields[name] for name in NAMES)
    return {
        "id": contact.pk,
        "href": contact.href,
        "revision": contact.revision,
        "fields": {**shown.fields, "name": shown_name(shown.fields, []) if named else ""},
        "points": shown.points,
        "photo": str(contact.photo_id) if contact.photo_id else None,
        "starred": contact.starred,
    }


def _revision(given) -> int | None:
    if given is None:
        return None
    if not isinstance(given, int) or isinstance(given, bool):
        raise Refused(400, "invalid_revision")
    return given


def _mailboxes(person) -> list[dict]:
    """The shared mailboxes whose books the phone holds beside the user's own."""
    reached = {} if person.visitor else sharing.roles(person)
    boxes = User.everyone.filter(pk__in=reached, mailbox=True).order_by("pk")
    return [
        {"id": box.pk, "name": box.first_name, "read_only": reached[box.pk] == sharing.READ}
        for box in boxes
    ]


@api("GET", device=True)
@sharing.boxed()
def phone_book(request):
    """The address book as the phone's own app holds it (D26): every contact, or those changed
    since the revision the phone read last and the hrefs of those deleted since, and the revision
    it now holds. A revision the book never reached, as after a restore, is refused (410), and
    the phone reads the whole book again. The user's own book names the shared mailboxes whose
    books the phone reads by `box` beside it."""
    _phone(request)
    since = request.GET.get("since", "0")
    if not since.isdigit():
        raise Refused(400, "invalid_since")
    since, now = int(since), cards.latest(request.user)
    if since > now:
        raise Refused(410, "since_unknown")
    changed = _held(request.user).filter(revision__gt=since, revision__lte=now)
    served = {
        "revision": now,
        "contacts": [_served(each) for each in changed.order_by("revision")],
        "gone": cards.gone(request.user, since, now) if since else [],
    }
    if request.user == request.person:
        served["mailboxes"] = _mailboxes(request.person)
    return JsonResponse(served)


@api("PUT", "DELETE", device=True)
@sharing.boxed()
def phone_contact(request, href):
    """A contact the phone wrote, under the href the phone chose for a new one, kept as a phone's
    card is (`cards.saved`): written over only at the revision the phone read, and refused (412)
    when it changed since, as the book holds the truth and the phone reads it again. The photo is
    replaced only where the phone gives one, or null for none, and whether it is a favourite only
    where the phone tells. A shared mailbox's book, named by `box`, takes it where the user's role
    writes there."""
    _phone(request)
    if len(href) > HREF:
        raise Refused(400, "invalid_href")
    found = _held(request.user).filter(href=href).first()
    if request.method == "DELETE":
        revision = request.GET.get("revision", "")
        if found is None:
            raise Refused(404, "not_found")
        if revision != str(found.revision):
            raise Refused(412, "changed")
        cards.deleted(found)
        return HttpResponse(status=204)
    data = body(request)
    revision = _revision(data.get("revision"))
    if found is None and revision is not None:
        raise Refused(404, "not_found")
    if found is not None and found.revision != revision:
        raise Refused(412, "changed")
    given = _card(data, found)
    starred = data.get("starred")
    if starred is not None and not isinstance(starred, bool):
        raise Refused(400, "invalid_starred")
    photo = "photo" in data
    if photo and data["photo"] is not None:
        try:
            given.photo = base64.b64decode(str(data["photo"]), validate=True)
        except binascii.Error:
            raise Refused(400, "invalid_photo") from None
    if found is None:
        made = cards.made(request.user.pk, given, href=href, starred=bool(starred))
        return JsonResponse(_served(_held(request.user).get(pk=made.pk)), status=201)
    cards.saved(found, given, phone=True, photo=photo, starred=starred)
    return JsonResponse(_served(_held(request.user).get(pk=found.pk)))
