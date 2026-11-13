"""Signing in at a SAML 2.0 identity provider (U1): the provider read from its metadata, the
request sent by redirect, and the response posted back, read only from what its signature covers
so that nothing wrapped around a signed assertion is believed."""

import base64
import secrets
import zlib
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from django.conf import settings
from lxml import etree
from signxml import InvalidInput, XMLVerifier
from signxml.exceptions import InvalidSignature

from .models import Attempt, Provider
from .oidc import client
from .people import Person, Refusal

PROTOCOL = "urn:oasis:names:tc:SAML:2.0:protocol"
ASSERTION = "urn:oasis:names:tc:SAML:2.0:assertion"
METADATA = "urn:oasis:names:tc:SAML:2.0:metadata"
SIGNATURE = "http://www.w3.org/2000/09/xmldsig#"
NS = {"samlp": PROTOCOL, "saml": ASSERTION, "md": METADATA, "ds": SIGNATURE}
REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
SUCCESS = "urn:oasis:names:tc:SAML:2.0:status:Success"
BEARER = "urn:oasis:names:tc:SAML:2.0:cm:bearer"
EMAIL_FORMAT = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
UNSPECIFIED = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
SKEW = timedelta(minutes=3)
LARGEST = 1 << 20

EMAIL = (
    "email",
    "mail",
    "emailaddress",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "urn:oid:0.9.2342.19200300.100.1.3",
)
FIRST = (
    "givenName",
    "firstName",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
    "urn:oid:2.5.4.42",
)
LAST = (
    "sn",
    "surname",
    "lastName",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
    "urn:oid:2.5.4.4",
)
GROUPS = (
    "groups",
    "memberOf",
    "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
    "http://schemas.xmlsoap.org/claims/Group",
)


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True
    )


def _read(data: bytes) -> etree._Element:
    try:
        return etree.fromstring(data, _parser())
    except etree.XMLSyntaxError as error:
        raise Refusal("invalid_metadata") from error


def _text(element) -> str:
    return "".join(element.itertext()).strip() if element is not None else ""


def _pem(der: str) -> str:
    body = "".join(der.split())
    lines = [body[at : at + 64] for at in range(0, len(body), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def described(metadata: bytes) -> dict:
    """The provider's name, where it takes a sign-in by redirect, and the certificates it signs
    with, from its metadata."""
    root = _read(metadata)
    if root.tag == f"{{{METADATA}}}EntityDescriptor":
        entity = root
    else:
        entity = root.find("md:EntityDescriptor", NS)
    descriptor = None if entity is None else entity.find("md:IDPSSODescriptor", NS)
    if descriptor is None:
        raise Refusal("invalid_metadata")
    redirect = [
        each.get("Location")
        for each in descriptor.findall("md:SingleSignOnService", NS)
        if each.get("Binding") == REDIRECT
    ]
    certificates = [
        _pem(_text(each))
        for key in descriptor.findall("md:KeyDescriptor", NS)
        if key.get("use") in (None, "signing")
        for each in key.findall("ds:KeyInfo/ds:X509Data/ds:X509Certificate", NS)
    ]
    if not entity.get("entityID") or not redirect or not certificates:
        raise Refusal("invalid_metadata")
    return {
        "entity_id": entity.get("entityID"),
        "sso_url": redirect[0],
        "certificates": list(dict.fromkeys(certificates)),
    }


def fetched(url: str) -> dict:
    try:
        with client() as asking:
            answer = asking.get(url)
            answer.raise_for_status()
    except Exception as error:
        raise Refusal("provider_unreachable") from error
    if len(answer.content) > LARGEST:
        raise Refusal("invalid_metadata")
    return described(answer.content)


def entity_of(provider: Provider) -> str:
    return f"{settings.PUBLIC_URL}/api/identity/providers/{provider.pk}/metadata"


def consumer_of(provider: Provider) -> str:
    return f"{settings.PUBLIC_URL}/api/identity/providers/{provider.pk}/saml"


def _instant(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sent(provider: Provider, attempt: Attempt) -> str:
    """Where the browser goes to sign in, with the request by redirect; a confirmation asks the
    provider to ask again."""
    attempt.request_id = f"_{secrets.token_hex(20)}"
    request = etree.Element(
        f"{{{PROTOCOL}}}AuthnRequest",
        nsmap={"samlp": PROTOCOL, "saml": ASSERTION},
        ID=attempt.request_id,
        Version="2.0",
        IssueInstant=_instant(datetime.now(UTC)),
        Destination=provider.settings["sso_url"],
        AssertionConsumerServiceURL=consumer_of(provider),
        ProtocolBinding=POST,
    )
    if attempt.confirming_id:
        request.set("ForceAuthn", "true")
    etree.SubElement(request, f"{{{ASSERTION}}}Issuer").text = entity_of(provider)
    etree.SubElement(request, f"{{{PROTOCOL}}}NameIDPolicy", Format=UNSPECIFIED, AllowCreate="true")
    packer = zlib.compressobj(wbits=-15)
    packed = packer.compress(etree.tostring(request)) + packer.flush()
    asked = urlencode(
        {"SAMLRequest": base64.b64encode(packed).decode(), "RelayState": attempt.state}
    )
    joiner = "&" if "?" in provider.settings["sso_url"] else "?"
    return f"{provider.settings['sso_url']}{joiner}{asked}"


def metadata(provider: Provider) -> bytes:
    """What the identity provider is given to know this installation by."""
    entity = etree.Element(
        f"{{{METADATA}}}EntityDescriptor", nsmap={"md": METADATA}, entityID=entity_of(provider)
    )
    descriptor = etree.SubElement(
        entity,
        f"{{{METADATA}}}SPSSODescriptor",
        AuthnRequestsSigned="false",
        WantAssertionsSigned="true",
        protocolSupportEnumeration=PROTOCOL,
    )
    etree.SubElement(descriptor, f"{{{METADATA}}}NameIDFormat").text = EMAIL_FORMAT
    etree.SubElement(
        descriptor,
        f"{{{METADATA}}}AssertionConsumerService",
        Binding=POST,
        Location=consumer_of(provider),
        index="0",
        isDefault="true",
    )
    return etree.tostring(entity, xml_declaration=True, encoding="UTF-8")


def _signed(provider: Provider, data: bytes) -> etree._Element:
    """The part of the response its signature covers, by one of the provider's certificates."""
    for certificate in provider.settings.get("certificates", []):
        try:
            return XMLVerifier().verify(data, x509_cert=certificate).signed_xml
        except InvalidSignature:
            continue
        except InvalidInput as error:
            raise Refusal("invalid_response") from error
    raise Refusal("invalid_signature")


def _when(given: str | None) -> datetime | None:
    if not given:
        return None
    try:
        found = datetime.fromisoformat(given)
    except ValueError:
        raise Refusal("invalid_response") from None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def _assertion(signed: etree._Element) -> etree._Element:
    if signed.tag == f"{{{ASSERTION}}}Assertion":
        return signed
    if signed.tag != f"{{{PROTOCOL}}}Response":
        raise Refusal("invalid_response")
    found = signed.findall("saml:Assertion", NS)
    if len(found) != 1:
        raise Refusal("invalid_response")
    return found[0]


def _checked(provider: Provider, assertion: etree._Element, attempt: Attempt) -> etree._Element:
    """The assertion's subject, once the assertion is the provider's, for this installation, in
    its time, and in answer to this attempt."""
    now = datetime.now(UTC)
    if _text(assertion.find("saml:Issuer", NS)) != provider.settings["entity_id"]:
        raise Refusal("invalid_response")
    conditions = assertion.find("saml:Conditions", NS)
    if conditions is not None:
        before, after = _when(conditions.get("NotBefore")), _when(conditions.get("NotOnOrAfter"))
        if (before and now + SKEW < before) or (after and now - SKEW >= after):
            raise Refusal("expired_response")
        audiences = [_text(each) for each in conditions.findall(".//saml:Audience", NS)]
        if audiences and entity_of(provider) not in audiences:
            raise Refusal("invalid_response")
    subject = assertion.find("saml:Subject", NS)
    if subject is None:
        raise Refusal("invalid_response")
    confirmed = False
    for confirmation in subject.findall("saml:SubjectConfirmation", NS):
        data = confirmation.find("saml:SubjectConfirmationData", NS)
        if confirmation.get("Method") != BEARER or data is None:
            continue
        until = _when(data.get("NotOnOrAfter"))
        confirmed = (
            data.get("Recipient") == consumer_of(provider)
            and data.get("InResponseTo") == attempt.request_id
            and until is not None
            and now - SKEW < until
        )
        if confirmed:
            break
    if not confirmed:
        raise Refusal("invalid_response")
    return subject


def _attributes(assertion: etree._Element) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for attribute in assertion.findall("saml:AttributeStatement/saml:Attribute", NS):
        values = [_text(each) for each in attribute.findall("saml:AttributeValue", NS)]
        found.setdefault(attribute.get("Name", ""), []).extend(each for each in values if each)
    return found


def _first(attributes: dict[str, list[str]], names) -> str:
    for name in names:
        if attributes.get(name):
            return attributes[name][0]
    return ""


def person(provider: Provider, posted: str, attempt: Attempt) -> Person:
    try:
        data = base64.b64decode(posted, validate=False)
    except ValueError:
        raise Refusal("invalid_response") from None
    if not data or len(data) > LARGEST:
        raise Refusal("invalid_response")
    whole = _read(data)
    if whole.find(".//saml:EncryptedAssertion", NS) is not None:
        raise Refusal("encrypted_assertion")
    status = whole.find("samlp:Status/samlp:StatusCode", NS)
    if status is None or status.get("Value") != SUCCESS:
        raise Refusal("provider_refused")
    assertion = _assertion(_signed(provider, data))
    subject = _checked(provider, assertion, attempt)
    name_id = subject.find("saml:NameID", NS)
    named = _text(name_id)
    if not named:
        raise Refusal("invalid_response")
    attributes = _attributes(assertion)
    email = _first(attributes, (provider.settings.get("email_attribute"), *EMAIL))
    if not email and name_id.get("Format") == EMAIL_FORMAT:
        email = named
    groups = None
    if provider.groups:
        names = (provider.settings.get("groups_attribute"), *GROUPS)
        # A provider sends no groups attribute for someone in none.
        given = next((attributes[name] for name in names if name in attributes), [])
        groups = [(each, each) for each in given]
    return Person(
        subject=named,
        email=email,
        first_name=_first(attributes, FIRST),
        last_name=_first(attributes, LAST),
        groups=groups,
    )
