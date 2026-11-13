import base64

import pytest
from django.utils import timezone

from apps.contacts import cards, taking
from apps.contacts.models import Contact, Entry, Gone
from apps.contacts.vcard import Card, parsed
from apps.users.app_passwords import digest, made
from apps.users.models import AppPassword

pytestmark = pytest.mark.django_db

PROPS = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><d:current-user-principal/><card:addressbook-home-set/><d:resourcetype/>"
    "<d:sync-token/><d:getetag/></d:prop></d:propfind>"
)
SYNC = (
    '<?xml version="1.0"?><d:sync-collection xmlns:d="DAV:" '
    'xmlns:card="urn:ietf:params:xml:ns:carddav"><d:sync-token>{}</d:sync-token>'
    "<d:sync-level>1</d:sync-level><d:prop><d:getetag/><card:address-data/></d:prop>"
    "</d:sync-collection>"
)
ANA = "BEGIN:VCARD\r\nVERSION:3.0\r\nUID:ana-1\r\nFN:Ana Horvat\r\nN:Horvat;Ana;;;\r\n"
ANA += "EMAIL;TYPE=INTERNET:ana@firma.test\r\nX-PHONETIC-FIRST-NAME:Ana\r\nEND:VCARD\r\n"


@pytest.fixture
def phone(client, owner):
    secret = made()
    AppPassword.objects.create(user=owner, name="iPhone", digest=digest(secret))
    token = base64.b64encode(f"Ivo@Example.com:{secret.upper()}".encode()).decode()
    client.defaults["HTTP_AUTHORIZATION"] = f"Basic {token}"
    return client


def book(owner) -> str:
    return f"/dav/contacts/{owner.pk}/book/"


def dav(client, method, path, body="", **headers):
    return client.generic(method, path, body, content_type="application/xml", **headers)


def put(client, path, text, **headers):
    return client.put(path, text, content_type="text/vcard", **headers)


def token(text: str) -> str:
    return text[text.index("<d:sync-token>") + 14 : text.index("</d:sync-token>")]


def test_only_an_app_password_of_the_user_signs_a_phone_in(client, owner, phone):
    assert dav(phone, "PROPFIND", "/dav/").status_code == 207
    secret = made()
    AppPassword.objects.create(user=owner, name="stari", digest=digest(secret))
    for login in (f"ivo@example.com:{made()}", f"ana@example.com:{secret}", "ivo@example.com"):
        auth = base64.b64encode(login.encode()).decode()
        refused = dav(client, "PROPFIND", "/dav/", HTTP_AUTHORIZATION=f"Basic {auth}")
        assert refused.status_code == 401
        assert refused["WWW-Authenticate"].startswith("Basic")
    owner.is_active = False
    owner.save()
    assert dav(phone, "PROPFIND", "/dav/").status_code == 401
    assert AppPassword.objects.get(name="iPhone").used_at is not None


def test_a_phone_finds_the_book_from_the_well_known_address(client, owner, phone):
    assert client.generic("PROPFIND", "/.well-known/carddav")["Location"] == "/dav/"
    root = dav(phone, "PROPFIND", "/dav/", PROPS, HTTP_DEPTH="0").content.decode()
    assert f"<d:current-user-principal><d:href>/dav/principals/{owner.pk}/</d:href>" in root
    found = dav(phone, "PROPFIND", f"/dav/principals/{owner.pk}", PROPS).content.decode()
    assert f"<card:addressbook-home-set><d:href>/dav/contacts/{owner.pk}/</d:href>" in found
    home = dav(phone, "PROPFIND", f"/dav/contacts/{owner.pk}/", PROPS, HTTP_DEPTH="1")
    assert home["DAV"] == "1, 3, addressbook, calendar-access"
    assert "<d:collection /><card:addressbook /></d:resourcetype>" in home.content.decode()
    other = dav(phone, "PROPFIND", f"/dav/contacts/{owner.pk + 1}/book/", PROPS)
    assert other.status_code == 404


def test_a_phone_reads_the_book_then_only_what_changed_since(phone, owner):
    ana = cards.made(owner.pk, parsed(ANA))
    first = dav(phone, "REPORT", book(owner), SYNC.format("")).content.decode()
    assert first.count("<d:response>") == 1 and "FN:Ana Horvat" in first
    assert (
        dav(phone, "REPORT", book(owner), SYNC.format(token(first)))
        .content.decode()
        .count("<d:response>")
        == 0
    )
    marko = cards.made(owner.pk, Card(fields={**Card().fields, "name": "Marko"}))
    cards.deleted(Contact.objects.get(pk=ana.pk))
    later = dav(phone, "REPORT", book(owner), SYNC.format(token(first))).content.decode()
    assert f"{book(owner)}{marko.href}</d:href>" in later
    assert f"<d:href>{book(owner)}ana-1.vcf</d:href><d:status>HTTP/1.1 404" in later
    stale = dav(phone, "REPORT", book(owner), SYNC.format("urn:x-ponistra:sync:999999"))
    assert stale.status_code == 403 and "valid-sync-token" in stale.content.decode()


def test_a_phone_writes_a_card_only_over_the_version_it_read(phone, owner):
    path = book(owner) + "ana-1.vcf"
    assert put(phone, path, ANA, HTTP_IF_NONE_MATCH="*").status_code == 201
    assert put(phone, path, ANA, HTTP_IF_NONE_MATCH="*").status_code == 412
    read = phone.get(path)
    assert "X-PHONETIC-FIRST-NAME:Ana" in read.content.decode()
    changed = ANA.replace("FN:Ana Horvat", "FN:Ana Kovač")
    assert put(phone, path, changed, HTTP_IF_MATCH='"0"').status_code == 412
    kept = put(phone, path, changed, HTTP_IF_MATCH=read["ETag"])
    assert kept.status_code == 204 and "ETag" not in kept
    assert Contact.objects.get().name == "Ana Kovač"
    elsewhere = put(phone, book(owner) + "drugi.vcf", ANA)
    assert elsewhere.status_code == 409 and "no-uid-conflict" in elsewhere.content.decode()
    assert put(phone, book(owner) + "x.vcf", "FN:x").status_code == 415
    assert phone.delete(path, HTTP_IF_MATCH=phone.get(path)["ETag"]).status_code == 204
    assert list(Gone.objects.values_list("href", flat=True)) == ["ana-1.vcf"]


def test_a_phone_gets_the_cards_it_names_and_those_a_filter_finds(phone, owner):
    cards.made(owner.pk, parsed(ANA))
    multiget = (
        '<card:addressbook-multiget xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
        f"<d:prop><d:getetag/><card:address-data/></d:prop><d:href>{book(owner)}ana-1.vcf</d:href>"
        f"<d:href>{book(owner)}nema.vcf</d:href></card:addressbook-multiget>"
    )
    found = dav(phone, "REPORT", book(owner), multiget).content.decode()
    assert "FN:Ana Horvat" in found and "nema.vcf</d:href><d:status>HTTP/1.1 404" in found

    def query(rule: str) -> str:
        asked = (
            '<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
            f"<d:prop><d:getetag/></d:prop><card:filter>{rule}</card:filter>"
            "</card:addressbook-query>"
        )
        return dav(phone, "REPORT", book(owner), asked).content.decode()

    def rule(name: str, inside: str) -> str:
        return f'<card:prop-filter name="{name}">{inside}</card:prop-filter>'

    assert "ana-1.vcf" in query(rule("FN", "<card:text-match>horv</card:text-match>"))
    exact = '<card:text-match match-type="equals">ana@</card:text-match>'
    assert "ana-1.vcf" not in query(rule("EMAIL", exact))
    assert "ana-1.vcf" in query(rule("TEL", "<card:is-not-defined/>"))
    odd = '<card:text-match collation="i;x">a</card:text-match>'
    assert "supported-collation" in query(rule("FN", odd))


def test_a_phone_edits_a_colleague_without_taking_the_directorys_values_as_its_own(phone, owner):
    entry = Entry.objects.create(
        host="traveler.firma.test",
        address="ana@firma.test",
        given="Ana",
        title="Direktorica",
        asked_at=timezone.now(),
    )
    colleague = taking.colleague(owner.pk, entry)
    path = book(owner) + colleague.href
    read = phone.get(path).content.decode()
    assert "TITLE:Direktorica" in read
    back = read.replace("END:VCARD", "NOTE:Kći Lana\r\nEND:VCARD")
    assert put(phone, path, back).status_code == 204
    colleague.refresh_from_db()
    assert (colleague.title, colleague.given, colleague.note) == ("", "", "Kći Lana")


def test_what_a_resource_shows_is_not_the_phones_to_change(phone, owner):
    patch = (
        '<d:propertyupdate xmlns:d="DAV:"><d:set><d:prop><d:displayname>Moji</d:displayname>'
        "</d:prop></d:set></d:propertyupdate>"
    )
    answered = dav(phone, "PROPPATCH", book(owner), patch).content.decode()
    assert "<d:displayname /></d:prop><d:status>HTTP/1.1 403 Forbidden" in answered
    assert dav(phone, "OPTIONS", book(owner))["Allow"].startswith("OPTIONS")
