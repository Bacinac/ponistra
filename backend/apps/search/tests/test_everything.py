from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.access.tests.test_access import create, person, share
from apps.calendar.models import Calendar, Event
from apps.contacts.models import Contact, Directory, Entry, Point
from apps.content.blocks import Block, Grid, Run, light_cell
from apps.content.tests.helpers import fill
from apps.documents.models import Node
from apps.mail.models import Account
from apps.tasks.models import Task
from apps.users.models import User
from apps.versions import history

from .test_search import END, MARK

pytestmark = pytest.mark.django_db


def found(client, q, **params) -> dict:
    response = client.get("/api/search", {"q": q, "zone": "Europe/Zagreb", **params})
    assert response.status_code == 200, response.json()
    return response.json()


def event(calendar, summary, day, **fields) -> Event:
    starts = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return Event.objects.create(
        calendar=calendar,
        uid=f"{summary}-{day}",
        href=f"{summary}-{day}.ics",
        summary=summary,
        starts=starts,
        ends=starts + timedelta(hours=1),
        **fields,
    )


@pytest.fixture
def calendar(api):
    return Calendar.objects.create(owner=api.user, name="Moj", color=2)


def test_an_event_is_found_by_a_stem_a_typo_or_its_place_and_people(api, calendar):
    event(calendar, "Zamjena guma", "2026-11-03T08:00", location="Vulkanizer Jurić")
    event(
        calendar,
        "Sastanak",
        "2026-11-04T08:00",
        attendees=[{"name": "Ana Kovač", "email": "ana@firma.test"}],
    )
    event(calendar, "Otkazano", "2026-11-05T08:00", status=Event.Status.CANCELLED)
    assert [each["summary"] for each in found(api, "gume")["events"]] == ["Zamjena guma"]
    assert [each["summary"] for each in found(api, "zamjna")["events"]] == ["Zamjena guma"]
    hit = found(api, "jurić")["events"][0]
    assert hit["summary"] == "Zamjena guma" and hit["snippet"] == f"Vulkanizer {MARK}Jurić{END}"
    assert hit["calendar"]["name"] == "Moj" and hit["start"] == "2026-11-03T09:00:00+01:00"
    assert hit["marked"] == "Zamjena guma" and hit["recurring"] is False
    assert [each["summary"] for each in found(api, "kovač")["events"]] == ["Sastanak"]
    assert found(api, "otkazano")["events"] == []
    assert found(api, "gume")["people"] == [] and found(api, "gume")["tasks"] == []


def test_a_series_is_one_hit_by_its_best_occurrence_and_the_nearest_comes_first(api, calendar):
    far = event(calendar, "Kolegij", "2020-01-06T09:00", rrule="FREQ=WEEKLY;COUNT=3")
    Event.objects.create(
        calendar=calendar,
        uid=far.uid,
        href=far.href,
        master=far,
        recurrence_id=far.starts + timedelta(days=7),
        summary="Kolegij pomaknut",
        starts=far.starts + timedelta(days=8),
        ends=far.starts + timedelta(days=8, hours=1),
    )
    near = event(calendar, "Kolegij uprave", timezone.now().strftime("%Y-%m-%dT%H:%M"))
    hits = found(api, "kolegij")["events"]
    assert [each["id"] for each in hits] == [near.pk, far.pk]
    assert hits[1]["hits"] == 2 and hits[1]["recurring"] is True


def test_filters_narrow_events_by_kind_organiser_and_when_they_take_place(api, calendar):
    event(calendar, "Gume", "2024-05-13T08:00", organizer={"name": "Ivo", "email": "ivo@x.test"})
    event(calendar, "Gume", "2026-05-14T08:00")
    assert [each["start"][:10] for each in found(api, "gume datum:2024")["events"]] == [
        "2024-05-13"
    ]
    assert [each["start"][:10] for each in found(api, "gume od:ivo")["events"]] == ["2024-05-13"]
    listed = found(api, "vrsta:događaj datum:2026")
    assert [each["start"][:10] for each in listed["events"]] == ["2026-05-14"]
    assert listed["documents"] == [] and listed["mail"] == []
    assert found(api, "gume mapa:ponude")["events"] == []
    assert found(api, "gume vrsta:pošta")["events"] == []


def test_a_task_is_found_marked_open_ones_first_and_by_its_due_day(api):
    Task.objects.create(owner=api.user, text="Nazvati vulkanizera", due="2026-11-02")
    Task.objects.create(owner=api.user, text="Vulkanizer plaćen", done_at=timezone.now())
    Task.objects.create(owner=person("drugi@example.com").user, text="Vulkanizer tuđi")
    hits = found(api, "vulkanizer")["tasks"]
    assert [each["marked"] for each in hits] == [
        f"Nazvati {MARK}vulkanizera{END}",
        f"{MARK}Vulkanizer{END} plaćen",
    ]
    assert [each["done"] for each in hits] == [False, True]
    assert [each["text"] for each in found(api, "vrsta:zadatak datum:11.2026.")["tasks"]] == [
        "Nazvati vulkanizera"
    ]
    assert found(api, "vulkanizer od:ana")["tasks"] == []


def test_people_are_contacts_then_colleagues_and_the_directory_without_doubles(api):
    account = Account.objects.create(
        owner=api.user,
        address="ivo@brezik.test",
        username="ivo",
        secret=b"",
        protocol=Account.Protocol.ACTIVESYNC,
        activesync_host="traveler.example.com",
        device="5c1d" * 8,
    )
    Directory.objects.create(account=account)
    contact = Contact.objects.create(owner=api.user, name="Ana Kovač", organisation="Firma")
    Point.objects.create(
        contact=contact, kind=Point.Kind.EMAIL, value="ana@firma.test", key="ana@firma.test"
    )
    User.objects.create_user(
        "ana@firma.test", "Kamen-Most-Rijeka-71", first_name="Ana", last_name="K"
    )
    User.objects.create_user(
        "anamarija@example.com", "Kamen-Most-Rijeka-71", first_name="Anamarija"
    )
    Entry.objects.create(
        host=account.activesync_host,
        address="ana.horvat@example.com",
        name="Ana Horvat",
        company="Brezik",
        asked_at=timezone.now(),
    )
    Entry.objects.create(
        host=account.activesync_host,
        address="anamarija@example.com",
        name="Anamarija",
        asked_at=timezone.now(),
    )
    hits = found(api, "ana")["people"]
    assert [(each["kind"], each["name"]) for each in hits] == [
        ("contact", "Ana Kovač"),
        ("colleague", "Anamarija"),
        ("directory", "Ana Horvat"),
    ]
    assert hits[0]["organisation"] == "Firma" and hits[2]["email"] == "ana.horvat@example.com"
    assert found(api, '"ana" -x')["people"][0]["name"] == "Ana Kovač"
    assert [each["name"] for each in found(api, "vrsta:osoba")["people"]] == ["Ana Kovač"]
    assert found(api, "ana datum:2026")["people"] == []


def test_a_folder_narrows_the_search_to_its_documents(api, calendar):
    folder = create(api, "folder", "Mapa")
    event(calendar, "Mapa sastanak", "2026-11-03T08:00")
    Task.objects.create(owner=api.user, text="Mapa zadatak")
    everywhere = found(api, "mapa")
    assert len(everywhere["events"]) == 1 and len(everywhere["tasks"]) == 1
    within = found(api, "mapa", **{"in": folder})
    assert within["events"] == [] and within["tasks"] == [] and within["people"] == []


def test_versions_say_what_a_document_said_earlier_asked_for_by_kind(api):
    document = create(api, "document", "Ponuda")
    node = Node.objects.get(pk=document)
    tab = node.tabs.get()
    fill(tab, [Block("paragraph", "p1", runs=[Run("Cijena bez popusta 100 kuna")])])
    first = history.take(node, api.user, "Prije popusta")
    fill(tab, [Block("paragraph", "p1", runs=[Run("Cijena s popustom 80 kuna")])])
    second = history.take(node, api.user)
    fill(tab, [Block("paragraph", "p1", runs=[Run("Konačna cijena 80 kuna")])])
    history.take(node)
    assert found(api, "popust")["versions"] == []
    [hit] = found(api, "vrsta:verzija popust")["versions"]
    assert (hit["id"], hit["number"], hit["hits"]) == (str(second.id), 2, 2)
    assert (hit["document"]["id"], hit["document"]["title"]) == (document, "Ponuda")
    assert (hit["tab"]["id"], hit["snippet"]) == (
        str(tab.pk),
        f"Cijena s {MARK}popustom{END} 80 kuna",
    )
    [titled] = found(api, 'vrsta:verzija "bez popusta"')["versions"]
    assert (titled["id"], titled["title"]) == (str(first.id), "Prije popusta")
    [named] = found(api, "vrsta:verzija prije")["versions"]
    assert (named["id"], named["tab"]) == (str(first.id), None)
    [latest] = found(api, "vrsta:verzija")["versions"]
    assert latest["number"] == 3
    assert found(api, "vrsta:verzija popust od:ivo")["versions"] != []
    assert found(api, "vrsta:verzija popust od:ana")["versions"] == []
    other = person("ana@example.com")
    assert found(other, "vrsta:verzija popust")["versions"] == []
    assert share(api, document, "read", id=other.user.pk).status_code == 201
    assert len(found(other, "vrsta:verzija popust")["versions"]) == 1


def test_a_version_s_table_is_searched_by_what_was_typed_into_its_cells(api):
    document = create(api, "document", "Troškovnik")
    node = Node.objects.get(pk=document)
    tab = node.tabs.get()
    cells = [light_cell("r1:c2", "Dostava u Rijeku")]
    table = Block(
        "table", "t", {"name": "Rute"}, grid=Grid(["r1", "r2"], ["c1", "c2"]), cells=cells
    )
    fill(tab, [table])
    version = history.take(node, api.user, "Rute")
    fill(tab, [Block("paragraph", "p1", runs=[Run("Bez tablice")])])
    history.take(node, api.user)
    [hit] = found(api, "vrsta:verzija rijeka")["versions"]
    assert (hit["id"], hit["tab"]["id"]) == (str(version.id), str(tab.pk))
    assert hit["snippet"] == f"Dostava u {MARK}Rijeku{END}"
