"""WebDAV as a phone's own apps speak it (RFC 4918, RFC 5397, RFC 6578): signing in with an app
password, the properties a client asks for, and the multistatus they come back in. The address
book on top of it is `apps.contacts.carddav`, the calendars `apps.calendar.caldav`."""

import base64
import binascii
from collections.abc import Callable
from functools import wraps
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.users.app_passwords import user_of
from apps.users.models import User

DAV = "DAV:"
CARDDAV = "urn:ietf:params:xml:ns:carddav"
CALDAV = "urn:ietf:params:xml:ns:caldav"
CALENDARSERVER = "http://calendarserver.org/ns/"
APPLE = "http://apple.com/ns/ical/"
for prefix, namespace in (
    ("d", DAV),
    ("card", CARDDAV),
    ("cal", CALDAV),
    ("cs", CALENDARSERVER),
    ("apple", APPLE),
):
    ET.register_namespace(prefix, namespace)
REALM = 'Basic realm="PONISTRA", charset="UTF-8"'
METHODS = "OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, PROPPATCH, REPORT"
COMPLIANCE = "1, 3, addressbook, calendar-access"
XML = "application/xml; charset=utf-8"

# A property's value: its text, or the elements inside it.
Value = str | list[ET.Element]
Properties = dict[str, Callable[[], Value]]


class Bad(Exception):
    """The request is not one WebDAV understands."""


def d(name: str) -> str:
    return f"{{{DAV}}}{name}"


def card(name: str) -> str:
    return f"{{{CARDDAV}}}{name}"


def cal(name: str) -> str:
    return f"{{{CALDAV}}}{name}"


def cs(name: str) -> str:
    return f"{{{CALENDARSERVER}}}{name}"


def apple(name: str) -> str:
    return f"{{{APPLE}}}{name}"


def element(name: str, *children: ET.Element, text: str | None = None) -> ET.Element:
    made = ET.Element(name)
    made.extend(children)
    made.text = text
    return made


def href(path: str) -> ET.Element:
    return element(d("href"), text=path)


def quoted(path: str) -> str:
    return quote(path, safe="/@:+")


def principal(user: User) -> str:
    return f"/dav/principals/{user.pk}/"


def privileges(*names: str) -> list[ET.Element]:
    return [element(d("privilege"), element(d(name))) for name in names]


def common(user: User) -> Properties:
    """What every resource tells the user signed in."""
    return {
        d("current-user-principal"): lambda: [href(principal(user))],
        d("owner"): lambda: [href(principal(user))],
    }


def parsed(request) -> ET.Element | None:
    """The XML the request brings; None where it brings none."""
    given = request.body
    if not given.strip():
        return None
    try:
        return ET.fromstring(given)
    except ET.ParseError:
        raise Bad from None


def asked(root: ET.Element | None) -> list[str] | None:
    """The properties a PROPFIND or REPORT asks for; None where it asks for all."""
    prop = None if root is None else root.find(d("prop"))
    return None if prop is None else [child.tag for child in prop]


def depth(request) -> int:
    """How deep a PROPFIND goes: the resource, or it and its members; infinity is taken as one."""
    return 0 if request.headers.get("Depth", "infinity").strip() == "0" else 1


def status(code: int, reason: str) -> ET.Element:
    return element(d("status"), text=f"HTTP/1.1 {code} {reason}")


def answer(path: str, properties: Properties, names: list[str] | None) -> ET.Element:
    """The resource's `<response>`: the properties asked for that it has, and those it has not as
    not found; all it has where none were named."""
    found, missing = element(d("prop")), element(d("prop"))
    for name in properties if names is None else names:
        if name not in properties:
            missing.append(element(name))
            continue
        value = properties[name]()
        given = ET.SubElement(found, name)
        if isinstance(value, str):
            given.text = value
        else:
            given.extend(value)
    response = element(d("response"), href(quoted(path)))
    for prop, code, reason in ((found, 200, "OK"), (missing, 404, "Not Found")):
        if len(prop):
            response.append(element(d("propstat"), prop, status(code, reason)))
    return response


def bare(path: str, code: int, reason: str) -> ET.Element:
    """A `<response>` that is only a status, as for a member gone since a sync."""
    return element(d("response"), href(quoted(path)), status(code, reason))


def multistatus(responses: list[ET.Element], *after: ET.Element) -> HttpResponse:
    root = element(d("multistatus"), *responses, *after)
    return HttpResponse(
        ET.tostring(root, encoding="utf-8", xml_declaration=True), status=207, content_type=XML
    )


def refused(code: int, condition: ET.Element) -> HttpResponse:
    """A refusal naming the precondition the request failed."""
    root = element(d("error"), condition)
    return HttpResponse(
        ET.tostring(root, encoding="utf-8", xml_declaration=True), status=code, content_type=XML
    )


def unpatched(request, path: str) -> HttpResponse:
    """A PROPPATCH, refused for each property: what a resource shows is PONISTRA's to say."""
    root = parsed(request)
    names = [] if root is None else [prop.tag for each in root.iter(d("prop")) for prop in each]
    forbidden = element(d("prop"), *(element(name) for name in names))
    response = element(d("response"), href(quoted(path)))
    response.append(element(d("propstat"), forbidden, status(403, "Forbidden")))
    return multistatus([response])


def member(given: str, collection: str) -> str | None:
    """The name of the collection's member a client's href points at; None where it points
    elsewhere."""
    path = unquote(urlsplit(given.strip()).path)
    if not path.startswith(collection):
        return None
    name = path[len(collection) :]
    return name if name and "/" not in name else None


def signed(request) -> User | None:
    kind, _, given = request.headers.get("Authorization", "").partition(" ")
    if kind.lower() != "basic":
        return None
    try:
        email, _, secret = base64.b64decode(given.strip(), validate=True).decode().partition(":")
    except binascii.Error, UnicodeDecodeError:
        return None
    return user_of(email, secret)


def dav(view):
    """A WebDAV resource, for the user whose app password the request signs in with. The user
    is passed beside the request and never becomes its session's: a phone has none."""

    @csrf_exempt
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = signed(request)
        if user is None:
            return HttpResponse(status=401, headers={"WWW-Authenticate": REALM})
        if request.method == "OPTIONS":
            response = HttpResponse(headers={"Allow": METHODS})
        else:
            try:
                response = view(request, user, *args, **kwargs)
            except Bad:
                response = HttpResponse(status=400)
        response["DAV"] = COMPLIANCE
        return response

    return wrapper


def unsupported() -> HttpResponse:
    return HttpResponse(status=405, headers={"Allow": METHODS})
