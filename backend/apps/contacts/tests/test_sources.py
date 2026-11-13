import base64
import io
import urllib.error
from datetime import datetime
from functools import partial
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import pytest
from django.utils import timezone

from apps.contacts import activesync, directory, google, graph, sync, taking
from apps.contacts.models import Book, Contact, Directory, Entry, Taken
from apps.contacts.vcard import Card
from apps.core import sealed
from apps.dav import client
from apps.mail import signin
from apps.mail.imap import Failed
from apps.mail.models import Account, Correspondent
from apps.mail.tests.eas import contact, everything

pytestmark = pytest.mark.django_db(transaction=True)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
G = graph.GRAPH


def test_a_traveler_accounts_contacts_are_taken_from_its_folder_of_them(account, box):
    box.put(
        "5",
        contact(
            FirstName="Ana",
            LastName="Horvat",
            Email1Address='"Ana Horvat" <ana@firma.test>',
            MobilePhoneNumber="091 234 5678",
            CompanyName="Firma",
            Birthday="1980-03-14T23:00:00.000Z",
        ),
    )
    everything(account)
    assert list(Book.objects.values_list("server_id", "name")) == [("5", "Contacts")]
    ana = Contact.objects.get()
    assert (ana.given, ana.family, ana.organisation, ana.birthday) == (
        "Ana",
        "Horvat",
        "Firma",
        "1980-03-15",
    )
    assert [each.value for each in ana.points.all()] == ["ana@firma.test", "+385 91 234 5678"]
    box.put("5", contact(FirstName="Marko", Email1Address="marko@firma.test"))
    everything(account)
    assert Contact.objects.count() == 2
    assert Taken.objects.filter(kind=Taken.Kind.ACTIVESYNC).count() == 2


def test_a_wiped_account_takes_away_the_contacts_it_alone_brought(account, box, owner):
    box.put("5", contact(FirstName="Ana", Email1Address="ana@firma.test"))
    box.put("5", contact(FirstName="Marko", Email1Address="marko@firma.test"))
    everything(account)
    marko = Card(points=[{"kind": "email", "label": "", "value": "marko@firma.test", "parts": []}])
    taking.taken(owner.pk, None, Taken.Kind.MICROSOFT, "ime@outlook.com", "1", marko, {})
    activesync.wiped(account)
    assert list(Contact.objects.values_list("given", flat=True)) == ["Marko"]
    assert not Book.objects.exists()


def test_the_correspondents_the_directory_confirms_become_colleagues_refreshed_at_night(
    account, box, owner
):
    details = {"FirstName": "Ana", "LastName": "Horvat", "Title": "Direktorica"}
    box.people = [("Ana Horvat", "ana.horvat@example.com", details)]
    now = timezone.now()
    for address, name in (
        ("ana.horvat@example.com", "Ana Horvat"),
        ("pero@example.com", "Pero"),
        ("vanjski@drugo.test", "Vanjski"),
    ):
        Correspondent.objects.create(owner=owner, address=address, name=name, written=1, last=now)
    directory.passed(account.pk)
    ana = Contact.objects.get()
    assert (ana.entry.title, ana.title) == ("Direktorica", "")
    assert Entry.objects.get(address="pero@example.com").listed is False
    assert not Entry.objects.filter(address="vanjski@drugo.test").exists()
    assert Directory.objects.get().error == ""
    searched = box.commands.count("Search")
    directory.passed(account.pk)
    assert box.commands.count("Search") == searched
    Entry.objects.update(asked_at=now - 2 * directory.FRESH)
    details["Title"] = "Predsjednica uprave"
    before = ana.revision
    directory.passed(account.pk)
    assert Entry.objects.get(listed=True).title == "Predsjednica uprave"
    assert Contact.objects.get().revision > before


def test_a_directory_never_gone_through_is_due_at_once(account):
    assert sync._due() == [account.pk]
    directory.passed(account.pk)
    assert sync._due() == []


def test_the_directory_is_gone_through_at_night_after_the_last_time(settings):
    settings.TIME_ZONE = "Europe/Zagreb"
    last = timezone.make_aware(datetime(2026, 10, 25, 9, 0))
    assert timezone.localtime(directory.due(last)).isoformat() == "2026-10-26T04:00:00+01:00"
    early = timezone.make_aware(datetime(2026, 10, 25, 1, 0))
    assert timezone.localtime(directory.due(early)).hour == 4


class Graph:
    def __init__(self, pages: dict):
        self.pages = pages

    def __call__(self, token, url, raw=False):
        answer = self.pages[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def outlook(owner, monkeypatch):
    monkeypatch.setattr(signin, "graph", lambda account: "token")
    return Account.objects.create(
        owner=owner,
        address="ime@outlook.com",
        username="ime@outlook.com",
        login=Account.Login.MICROSOFT,
        secret=sealed.seal("mail", "refresh"),
        imap_host="outlook.office365.com",
    )


def test_a_microsoft_accounts_new_contacts_come_from_each_folders_delta(outlook, monkeypatch):
    ana = {
        "id": "c1",
        "givenName": "Ana",
        "surname": "Horvat",
        "emailAddresses": [{"address": "ana@firma.test"}],
        "mobilePhone": "091 234 5678",
        "businessAddress": {"street": "Ilica 1", "city": "Zagreb", "postalCode": "10000"},
    }
    pages = {
        f"{G}/me/contactFolders": {"value": [{"id": "F1", "displayName": "Posao"}]},
        f"{G}/me/contactFolders/F1/childFolders": {"value": []},
        f"{G}/me/contacts/delta": {"value": [ana], "@odata.nextLink": "next"},
        "next": {
            "value": [{"id": "c2", "displayName": "Marko"}, {"id": "c3", "@removed": {}}],
            "@odata.deltaLink": "delta",
        },
        f"{G}/me/contactFolders/F1/contacts/delta": {"value": [], "@odata.deltaLink": "work"},
        f"{G}/me/contacts/c1/photo/$value": PNG,
        f"{G}/me/contacts/c2/photo/$value": None,
        f"{G}/me/contacts/c4/photo/$value": None,
    }
    monkeypatch.setattr(graph, "_get", Graph(pages))
    assert graph.taken(outlook) == 2
    found = Contact.objects.get(given="Ana")
    assert found.photo_id is not None
    assert [each.value for each in found.points.order_by("position")] == [
        "ana@firma.test",
        "+385 91 234 5678",
        "Ilica 1\n10000 Zagreb",
    ]
    assert dict(Book.objects.values_list("server_id", "key")) == {"": "delta", "F1": "work"}
    pages["delta"] = {"value": [ana, {"id": "c4", "givenName": "Iva"}], "@odata.deltaLink": "d2"}
    pages["work"] = graph.Gone()
    assert graph.taken(outlook) == 1
    assert Contact.objects.count() == 3


def test_contacts_a_provider_refuses_are_noted_on_the_account(outlook, monkeypatch):
    def refused(account):
        raise Failed("oauth_refused")

    monkeypatch.setattr(signin, "graph", refused)
    sync._taken(outlook)
    assert list(Book.objects.values_list("server_id", "error")) == [("", "oauth_refused")]


HOME = "/carddav/v1/principals/ime@gmail.com/lists/"
DEFAULT = HOME + "default/"


def multistatus(*responses: tuple[str, str]) -> ET.Element:
    found = "".join(
        f"<d:response><d:href>{path}</d:href><d:propstat><d:status>HTTP/1.1 200 OK</d:status>"
        f"<d:prop>{held}</d:prop></d:propstat></d:response>"
        for path, held in responses
    )
    return ET.fromstring(
        f'<d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">{found}'
        "</d:multistatus>"
    )


class Google:
    def __init__(self, cards: dict):
        self.cards, self.asked = cards, []

    def __call__(self, authorization, method, path, body, depth):
        hrefs = [each.text for each in body.iter("{DAV:}href")]
        self.asked.append((authorization, method, path, depth, hrefs))
        if path == HOME:
            book = "<d:resourcetype><d:collection/><card:addressbook/></d:resourcetype>"
            return multistatus(
                (HOME, "<d:resourcetype><d:collection/></d:resourcetype>"),
                (DEFAULT, f"{book}<d:displayname>Address Book</d:displayname>"),
            )
        if method == "PROPFIND":
            listed = [(DEFAULT + name, '<d:getetag>"1"</d:getetag>') for name in self.cards]
            return multistatus((DEFAULT, ""), *listed)
        cards = [(path, escape(self.cards[path.rsplit("/", 1)[1]])) for path in hrefs]
        return multistatus(
            *((path, f"<card:address-data>{text}</card:address-data>") for path, text in cards)
        )


@pytest.fixture
def gmail(owner):
    return Account.objects.create(
        owner=owner,
        address="ime@gmail.com",
        username="ime@gmail.com",
        secret=sealed.seal("mail", "abcd efgh ijkl mnop"),
        imap_host=google.IMAP,
    )


def test_a_google_accounts_new_contacts_come_from_its_carddav_with_its_app_password(
    gmail, monkeypatch
):
    ana = (
        "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ana Horvat\r\nN:Horvat;Ana;;;\r\n"
        "TEL;TYPE=CELL,PREF:091 234 5678\r\nBDAY;VALUE=DATE:1981-03-14\r\n"
        f"PHOTO;ENCODING=B:{base64.b64encode(PNG).decode()}\r\nEND:VCARD\r\n"
    )
    server = Google({"a1": ana, "x9": "BEGIN:VCARD\r\nFN:Nedovršen"})
    monkeypatch.setattr(google, "_asked", server)
    assert google.taken(gmail) == 1
    found = Contact.objects.get()
    assert (found.given, found.family, found.birthday) == ("Ana", "Horvat", "1981-03-14")
    assert found.photo_id is not None
    assert [(each.label, each.key) for each in found.points.all()] == [("mobile", "+385912345678")]
    basic = base64.b64encode(b"ime@gmail.com:abcd efgh ijkl mnop").decode()
    assert {each[0] for each in server.asked} == {f"Basic {basic}"}
    assert list(Book.objects.values_list("server_id", "name")) == [(DEFAULT, "Address Book")]

    before = len(server.asked)
    assert google.taken(gmail) == 0
    assert [each[1:] for each in server.asked[before:]] == [
        ("PROPFIND", HOME, "1", []),
        ("PROPFIND", DEFAULT, "1", []),
        ("REPORT", DEFAULT, "1", [DEFAULT + "x9"]),
    ]
    server.cards["m2"] = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Marko\r\nEND:VCARD\r\n"
    assert google.taken(gmail) == 1
    assert server.asked[-1][4] == [DEFAULT + "x9", DEFAULT + "m2"]
    assert Contact.objects.count() == 2
    assert Taken.objects.filter(kind=Taken.Kind.GOOGLE, item=DEFAULT + "a1").exists()


def test_google_and_microsoft_accounts_are_followed_and_a_refusal_noted(
    gmail, outlook, monkeypatch
):
    Account.objects.create(
        owner=gmail.owner, address="ivo@firma.test", username="ivo", imap_host="mail.firma.test"
    )
    assert {each.address for each in sync._followed()} == {gmail.address, outlook.address}

    def refused(*asked):
        raise Failed("contacts_refused")

    monkeypatch.setattr(google, "_asked", refused)
    sync._taken(gmail)
    assert list(gmail.contact_books.values_list("server_id", "error")) == [("", "contacts_refused")]


def test_googles_passing_failures_are_asked_again_and_a_lasting_one_reported(monkeypatch):
    answers = []

    def answered(request, timeout):
        answer = answers.pop(0)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(request.full_url, answer, "", {}, io.BytesIO())
        return io.BytesIO(answer)

    monkeypatch.setattr(client.urllib.request, "urlopen", answered)
    monkeypatch.setattr(client.time, "sleep", lambda wait: None)
    ask = partial(google._asked, "Basic x", "PROPFIND", HOME, ET.Element("propfind"), "1")
    answers[:] = [502, 503, b"<multistatus/>"]
    assert ask().tag == "multistatus" and answers == []
    answers[:] = [502] * 5
    with pytest.raises(Failed, match="contacts_unreachable"):
        ask()
    answers[:] = [401]
    with pytest.raises(Failed, match="contacts_refused"):
        ask()
