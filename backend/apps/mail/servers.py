"""Which servers an address's mail is on: those of a provider PONISTRA knows, else what the
provider itself publishes as autoconfig, else IMAP under the name most providers use, else an
ActiveSync server under one of the names Exchange and HCL Traveler are usually given."""

import http.client
import ipaddress
import re
import socket
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from lxml import etree

from . import signin
from .activesync.client import PATH
from .models import Account, Provider, Security

LIMIT = 64 * 1024
TIMEOUT = 5
KNOWN = {
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com"),
    "googlemail.com": ("imap.gmail.com", "smtp.gmail.com"),
}
# Microsoft's addresses for people (outlook.com, hotmail.co.uk, live.com.au…), whose mail takes
# no password since September 2024, only a sign-in through Microsoft.
MICROSOFT = re.compile(r"(outlook|hotmail|live|msn)\.(com|[a-z]{2}|com?\.[a-z]{2})")
# Providers that refuse the account's own password for mail: where their app passwords are made.
APP_PASSWORDS = {"imap.gmail.com": "https://myaccount.google.com/apppasswords"}
SOCKETS = {"SSL": Security.TLS, "STARTTLS": Security.STARTTLS}
PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
ACTIVESYNC = ("autodiscover", "traveler", "mail", "outlook", "")


def _server(element, address: str) -> dict | None:
    security = SOCKETS.get(element.findtext("socketType", "").strip().upper())
    host = element.findtext("hostname", "").strip()
    port = element.findtext("port", "").strip()
    if security is None or not host or not port.isdigit():
        return None
    username = element.findtext("username", "%EMAILADDRESS%").strip()
    username = username.replace("%EMAILADDRESS%", address)
    username = username.replace("%EMAILLOCALPART%", address.split("@")[0])
    return {"host": host, "port": int(port), "security": security, "username": username}


def _first(config, tag: str, kind: str, address: str) -> dict | None:
    for element in config.iter(tag):
        if element.get("type") == kind and (server := _server(element, address)):
            return server
    return None


def _published(address: str, domain: str) -> dict | None:
    for url in (
        f"https://autoconfig.{domain}/mail/config-v1.1.xml?emailaddress={quote(address)}",
        f"https://{domain}/.well-known/autoconfig/mail/config-v1.1.xml?emailaddress={quote(address)}",
    ):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
                config = etree.fromstring(response.read(LIMIT), PARSER)
        except OSError, ValueError, etree.XMLSyntaxError:
            continue
        incoming = _first(config, "incomingServer", "imap", address)
        outgoing = _first(config, "outgoingServer", "smtp", address)
        if incoming and outgoing:
            return {"imap": incoming, "smtp": outgoing}
    return None


def _imap_answers(server: dict) -> bool:
    """Whether the IMAP server lets a client start: it connects and, over TLS, shows a
    certificate valid for its name. A website's host often answers for the domain with mail of
    its own the address is not on."""
    try:
        with socket.create_connection((server["host"], server["port"]), timeout=TIMEOUT) as raw:
            if server["security"] == Security.TLS:
                context = ssl.create_default_context()
                context.wrap_socket(raw, server_hostname=server["host"]).close()
    except OSError:
        return False
    return True


def _activesync_answers(host: str) -> bool:
    """Whether the host has an ActiveSync server: it asks who is there, or says it is one."""
    connection = http.client.HTTPSConnection(
        host, timeout=TIMEOUT, context=ssl.create_default_context()
    )
    try:
        connection.request("OPTIONS", PATH)
        response = connection.getresponse()
        return response.status == 401 or "MS-Server-ActiveSync" in response.headers
    except OSError, http.client.HTTPException:
        return False
    finally:
        connection.close()


def _activesync(domain: str) -> str:
    """The first of the usual names that answers as an ActiveSync server, else none."""
    hosts = [f"{name}.{domain}" if name else domain for name in ACTIVESYNC]
    with ThreadPoolExecutor(len(hosts)) as pool:
        answered = list(pool.map(_activesync_answers, hosts))
    return next((host for host, found in zip(hosts, answered, strict=True) if found), "")


def provider_name(address: str) -> str:
    """The word a person knows their mailbox by: Gmail, Outlook.com, or the organisation's name
    as its domain spells it."""
    domain = address.rsplit("@", 1)[-1].lower()
    if domain in KNOWN:
        return "Gmail"
    if MICROSOFT.fullmatch(domain):
        return "Outlook.com"
    return domain.split(".")[-2].capitalize() if "." in domain else domain.capitalize()


def known_as(account: Account) -> str:
    """The account by the user's own name for it, else by its provider's."""
    return account.label or provider_name(account.address)


def guessed(address: str) -> dict:
    domain = address.rsplit("@", 1)[-1].lower()
    incoming, outgoing = KNOWN.get(domain, (f"imap.{domain}", f"smtp.{domain}"))
    found = {
        "protocol": Account.Protocol.IMAP,
        "imap": {"host": incoming, "port": 993, "security": Security.TLS, "username": address},
        "smtp": {"host": outgoing, "port": 465, "security": Security.TLS, "username": address},
        "activesync": {"host": "", "username": address},
    }
    if MICROSOFT.fullmatch(domain):
        way = signin.WAYS[Provider.MICROSOFT]
        for kind, (host, port, security) in (("imap", way.imap), ("smtp", signin.PERSONAL_SMTP)):
            found[kind] |= {"host": host, "port": port, "security": security}
        return found | {"signin": Provider.MICROSOFT}
    try:
        ipaddress.ip_address(domain.strip("[]"))
    except ValueError:
        named = "." in domain and domain not in KNOWN
    else:
        named = False
    if not named:
        return found
    found |= _published(address, domain) or {}
    if not _imap_answers(found["imap"]) and (activesync := _activesync(domain)):
        found["protocol"], found["activesync"]["host"] = Account.Protocol.ACTIVESYNC, activesync
    return found
