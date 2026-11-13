"""The user's address book over CardDAV (RFC 6352, RFC 6578), which an iPhone reads by itself and
an Android phone through DAVx5: one book of every contact, changes found by revision. A card a
phone writes back keeps as the user's own only what it changed of what it read. Each shared
mailbox the user reaches has a book of its own beside it, read only where the user's role only
reads."""

from xml.etree import ElementTree as ET

from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseNotFound
from django.utils.http import http_date, parse_etags

from apps.access.models import RANK, Role
from apps.dav.protocol import (
    Bad,
    Properties,
    answer,
    asked,
    bare,
    card,
    common,
    cs,
    d,
    dav,
    depth,
    element,
    href,
    member,
    multistatus,
    parsed,
    privileges,
    quoted,
    refused,
    unpatched,
    unsupported,
)
from apps.mail import sharing
from apps.users.models import User

from . import cards, vcard
from .models import Contact

TOKEN = "urn:x-ponistra:sync:"
VCARD = "text/vcard; charset=utf-8"
# The most a phone may write as one card, its photo included.
LARGEST = 10 * 1024 * 1024
HREF = 255
WRITE = ("read", "write", "write-content", "bind", "unbind")
COLLATIONS = {"i;unicode-casemap", "i;ascii-casemap", "i;octet"}
REPORTS = (card("addressbook-multiget"), card("addressbook-query"), d("sync-collection"))
OWN = "book"
BOX = "box-"


def home(user) -> str:
    return f"/dav/contacts/{user.pk}/"


class Book:
    """An address book in the user's home: their own, or a shared mailbox's they reach."""

    def __init__(self, user, owner, write: bool):
        self.user, self.owner, self.write = user, owner, write
        mine = owner.pk == user.pk
        self.path = f"{home(user)}{OWN if mine else f'{BOX}{owner.pk}'}/"
        self.name = "Ponistra" if mine else owner.first_name


def _books(user) -> list[Book]:
    reached = {} if user.visitor else sharing.roles(user)
    boxes = User.everyone.filter(pk__in=reached, mailbox=True).order_by("pk")
    return [
        Book(user, user, True),
        *(Book(user, box, RANK[reached[box.pk]] >= RANK[Role.EDIT]) for box in boxes),
    ]


def _found(user, pk, name: str) -> Book | None:
    if int(pk) != user.pk:
        return None
    return next((each for each in _books(user) if each.path == f"{home(user)}{name}/"), None)


def homes(user) -> Properties:
    """What the user's principal says of where their address books are."""
    return {card("addressbook-home-set"): lambda: [href(home(user))]}


def _etag(contact: Contact) -> str:
    return f'"{contact.revision}"'


def _home(user) -> Properties:
    return {
        **common(user),
        d("resourcetype"): lambda: [element(d("collection"))],
        d("displayname"): lambda: "Ponistra",
        d("current-user-privilege-set"): lambda: privileges("read"),
    }


def _book(held: Book) -> Properties:
    revision = cards.latest(held.owner)
    return {
        **common(held.user),
        d("resourcetype"): lambda: [element(d("collection")), element(card("addressbook"))],
        d("displayname"): lambda: held.name,
        card("addressbook-description"): lambda: held.name,
        d("sync-token"): lambda: f"{TOKEN}{revision}",
        cs("getctag"): lambda: f"{TOKEN}{revision}",
        d("current-user-privilege-set"): lambda: privileges(*(WRITE if held.write else ("read",))),
        d("supported-report-set"): lambda: [
            element(d("supported-report"), element(d("report"), element(name))) for name in REPORTS
        ],
        card("supported-address-data"): lambda: [_address_data_type()],
        card("max-resource-size"): lambda: str(LARGEST),
    }


def _address_data_type() -> ET.Element:
    made = element(card("address-data-type"))
    made.set("content-type", "text/vcard")
    made.set("version", "3.0")
    return made


def _card(contact: Contact) -> Properties:
    return {
        d("getetag"): lambda: _etag(contact),
        d("getcontenttype"): lambda: VCARD,
        d("resourcetype"): lambda: [],
        d("getlastmodified"): lambda: http_date(contact.changed_at.timestamp()),
    }


def _with_data(contact: Contact) -> Properties:
    return {**_card(contact), card("address-data"): lambda: vcard.written(cards.card(contact))}


def _contacts(held: Book):
    return (
        Contact.objects.filter(owner=held.owner)
        .select_related("entry", "photo")
        .prefetch_related("points")
    )


def _propfound(request, held: Book) -> HttpResponse:
    names = asked(parsed(request))
    found = [answer(held.path, _book(held), names)]
    if depth(request):
        found += [
            answer(held.path + each.href, _card(each), names)
            for each in Contact.objects.filter(owner=held.owner).order_by("pk")
        ]
    return multistatus(found)


def _multiget(held: Book, root) -> HttpResponse:
    names = asked(root)
    wanted = [member(each.text or "", held.path) for each in root.iter(d("href"))]
    found = {each.href: each for each in _contacts(held).filter(href__in=[w for w in wanted if w])}
    responses = []
    for given, name in zip(root.iter(d("href")), wanted, strict=True):
        if name in found:
            responses.append(answer(held.path + name, _with_data(found[name]), names))
        else:
            responses.append(bare(given.text or "", 404, "Not Found"))
    return multistatus(responses)


def _matches(text: str, rule) -> bool:
    collation = rule.get("collation", "i;unicode-casemap")
    if collation not in COLLATIONS:
        raise Unsupported
    wanted = rule.text or ""
    if collation != "i;octet":
        text, wanted = text.casefold(), wanted.casefold()
    how = rule.get("match-type", "contains")
    found = {
        "equals": text == wanted,
        "starts-with": text.startswith(wanted),
        "ends-with": text.endswith(wanted),
    }.get(how, wanted in text)
    return found != (rule.get("negate-condition") == "yes")


class Unsupported(Exception):
    """A filter asks for a collation PONISTRA does not compare by."""


def _all_or_any(rule, tests: list[bool]) -> bool:
    return all(tests) if rule.get("test") == "allof" else any(tests)


def _passes(lines: list[vcard.Line], rule) -> bool:
    """Whether the card's lines pass one prop-filter."""
    name = rule.get("name", "").upper()
    held = [each for each in lines if each.name == name]
    if rule.find(card("is-not-defined")) is not None:
        return not held
    tests = []
    for each in rule:
        if each.tag == card("text-match"):
            tests.append(any(_matches(vcard.unescaped(line.value), each) for line in held))
        elif each.tag == card("param-filter"):
            tests.append(any(_param_passes(line, each) for line in held))
    return bool(held) if not tests else _all_or_any(rule, tests)


def _param_passes(line: vcard.Line, rule) -> bool:
    name = rule.get("name", "").upper()
    values = line.params.get(name, [])
    if rule.find(card("is-not-defined")) is not None:
        return not values
    match = rule.find(card("text-match"))
    if match is None:
        return bool(values)
    return any(_matches(value, match) for value in values)


def _query(held: Book, root) -> HttpResponse:
    names = asked(root)
    rules = root.find(card("filter"))
    limit = root.findtext(f"{card('limit')}/{card('nresults')}")
    most = int(limit) if limit and limit.strip().isdigit() else None
    responses, truncated = [], False
    try:
        for each in _contacts(held).order_by("pk"):
            if rules is not None and len(rules):
                lines = vcard.lines(vcard.written(cards.card(each, photo=False)))
                if not _all_or_any(rules, [_passes(lines, rule) for rule in rules]):
                    continue
            if most is not None and len(responses) == most:
                truncated = True
                break
            responses.append(answer(held.path + each.href, _with_data(each), names))
    except Unsupported:
        return refused(403, element(card("supported-collation")))
    if truncated:
        responses.append(bare(held.path, 507, "Insufficient Storage"))
    return multistatus(responses)


def _synced(held: Book, root) -> HttpResponse:
    """What changed in the book since the token the phone holds, and the token it now holds."""
    given = (root.findtext(d("sync-token")) or "").strip()
    since = 0
    if given:
        number = given.removeprefix(TOKEN)
        if not given.startswith(TOKEN) or not number.isdigit():
            return refused(403, element(d("valid-sync-token")))
        since = int(number)
    now = cards.latest(held.owner)
    if since > now:
        return refused(403, element(d("valid-sync-token")))
    names = asked(root)
    changed = _contacts(held).filter(revision__gt=since, revision__lte=now).order_by("revision")
    responses = [answer(held.path + each.href, _with_data(each), names) for each in changed]
    if since:
        gone = cards.gone(held.owner, since, now)
        responses += [bare(held.path + each, 404, "Not Found") for each in gone]
    return multistatus(responses, element(d("sync-token"), text=f"{TOKEN}{now}"))


def _reported(request, held: Book) -> HttpResponse:
    root = parsed(request)
    if root is None:
        raise Bad
    if root.tag == card("addressbook-multiget"):
        return _multiget(held, root)
    if root.tag == card("addressbook-query"):
        return _query(held, root)
    if root.tag == d("sync-collection"):
        return _synced(held, root)
    return refused(403, element(d("supported-report")))


@dav
def contacts_home(request, user, pk):
    if int(pk) != user.pk:
        return HttpResponseNotFound()
    if request.method == "PROPPATCH":
        return unpatched(request, home(user))
    if request.method != "PROPFIND":
        return unsupported()
    names = asked(parsed(request))
    found = [answer(home(user), _home(user), names)]
    if depth(request):
        found += [answer(each.path, _book(each), names) for each in _books(user)]
    return multistatus(found)


@dav
def address_book(request, user, pk, book):
    held = _found(user, pk, book)
    if held is None:
        return HttpResponseNotFound()
    match request.method:
        case "PROPFIND":
            return _propfound(request, held)
        case "REPORT":
            return _reported(request, held)
        case "PROPPATCH":
            return unpatched(request, held.path)
    return unsupported()


def _failed_precondition(request, found: Contact | None) -> bool:
    if match := request.headers.get("If-Match"):
        tags = parse_etags(match)
        if found is None or ("*" not in tags and _etag(found) not in tags):
            return True
    if none := request.headers.get("If-None-Match"):
        tags = parse_etags(none)
        if found is not None and ("*" in tags or _etag(found) in tags):
            return True
    return False


def _put(request, held: Book, name: str, found: Contact | None) -> HttpResponse:
    given = request.read(LARGEST + 1)
    if len(given) > LARGEST:
        return refused(413, element(card("max-resource-size")))
    try:
        written = vcard.parsed(given.decode("utf-8-sig"))
    except UnicodeDecodeError, vcard.Malformed:
        return refused(415, element(card("valid-address-data")))
    if found is not None:
        written.uid = found.uid
        cards.saved(found, written, phone=True)
        return HttpResponse(status=204)
    if written.uid and (other := Contact.objects.filter(owner=held.owner, uid=written.uid).first()):
        return refused(409, element(card("no-uid-conflict"), href(quoted(held.path + other.href))))
    try:
        cards.made(held.owner.pk, written, href=name)
    except IntegrityError:
        return refused(409, element(card("no-uid-conflict")))
    return HttpResponse(status=201)


@dav
def address_card(request, user, pk, book, name):
    held = _found(user, pk, book)
    if held is None or len(name) > HREF:
        return HttpResponseNotFound()
    found = _contacts(held).filter(href=name).first()
    if request.method in ("PUT", "DELETE"):
        if not held.write:
            return HttpResponse(status=403)
        if _failed_precondition(request, found):
            return HttpResponse(status=412)
    match request.method:
        case "GET" | "HEAD":
            if found is None:
                return HttpResponseNotFound()
            return HttpResponse(
                vcard.written(cards.card(found)),
                content_type=VCARD,
                headers={"ETag": _etag(found)},
            )
        case "PROPFIND":
            if found is None:
                return HttpResponseNotFound()
            return multistatus([answer(held.path + name, _card(found), asked(parsed(request)))])
        case "PUT":
            return _put(request, held, name, found)
        case "DELETE":
            if found is None:
                return HttpResponseNotFound()
            cards.deleted(found)
            return HttpResponse(status=204)
    return unsupported()
