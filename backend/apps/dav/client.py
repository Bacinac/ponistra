"""WebDAV as PONISTRA asks it of a provider (RFC 4918): a request answered or asked again, and
the properties found in a multistatus. The address books and calendars on top of it are
`apps.contacts.google` and `apps.calendar.google`."""

import base64
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

from apps.mail import signin
from apps.mail.imap import Failed
from apps.mail.models import Account

from .protocol import XML, d, element

TIMEOUT = 30
# Google's DAV answers a share of requests with a 502 at random (7 to 30 % on 2026-10-26),
# whatever the client, and the same request asked again is answered.
AGAIN = (1, 2, 4, 8)
PASSING = {502, 503, 504}


def authorization(account: Account) -> str:
    """How the account signs in: with the token its sign-in consented to, or its password."""
    login, _ = signin.login(account)
    if login.token:
        return f"Bearer {login.token}"
    return "Basic " + base64.b64encode(f"{login.username}:{login.password}".encode()).decode()


def _answered(request: urllib.request.Request, what: str) -> ET.Element | None:
    """The server's answer; None where it failed in passing."""
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return ET.fromstring(response.read())
    except urllib.error.HTTPError as refused:
        if refused.code in (401, 403):
            raise Failed(f"{what}_refused") from None
        if refused.code in PASSING:
            return None
        raise Failed(f"{what}_unreachable") from None
    except OSError, ET.ParseError:
        raise Failed(f"{what}_unreachable") from None


def asked(
    what: str, authorization: str, method: str, url: str, body: ET.Element, depth: str
) -> ET.Element:
    """The answer to the request, asked again after each failure in passing. `what` names the
    failure a refusal is reported as."""
    request = urllib.request.Request(
        url,
        data=ET.tostring(body, encoding="utf-8", xml_declaration=True),
        method=method,
        headers={"Authorization": authorization, "Depth": depth, "Content-Type": XML},
    )
    for wait in AGAIN:
        if (answer := _answered(request, what)) is not None:
            return answer
        time.sleep(wait)
    if (answer := _answered(request, what)) is None:
        raise Failed(f"{what}_unreachable")
    return answer


def found(root: ET.Element) -> list[tuple[str, ET.Element]]:
    """Each response's path and the properties the server found for it."""
    listed = []
    for response in root.iter(d("response")):
        held = ET.Element(d("prop"))
        for propstat in response.iter(d("propstat")):
            prop = propstat.find(d("prop"))
            if prop is not None and " 200 " in propstat.findtext(d("status"), ""):
                held.extend(prop)
        listed.append((urllib.parse.unquote(response.findtext(d("href"), "")), held))
    return listed


def wanted(*names: str) -> ET.Element:
    """A PROPFIND's body asking for the properties."""
    return element(d("propfind"), element(d("prop"), *(element(name) for name in names)))
