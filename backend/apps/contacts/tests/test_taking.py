import pytest
from django.utils import timezone

from apps.contacts import cards, directory, taking
from apps.contacts.models import Contact, Entry, Taken
from apps.contacts.vcard import Card, parsed, written

pytestmark = pytest.mark.django_db

KIND, SOURCE = Taken.Kind.MICROSOFT, "ime@outlook.com"


def card(name="", **points) -> Card:
    made = Card(
        points=[{"kind": k, "label": "", "value": v, "parts": []} for k, v in points.items()]
    )
    made.fields["name"] = name
    return made


def take(owner, item, made, kind=KIND, source=SOURCE):
    return taking.taken(owner.pk, None, kind, source, item, made, {"id": item})


def test_an_item_joins_the_person_another_source_brought_by_address_once(owner):
    first = take(owner, "1", card("Ana Horvat", email="Ana@Firma.test"), Taken.Kind.ACTIVESYNC, "a")
    given = card("Ana", email="ana@firma.test", phone="091 234 5678")
    given.fields["title"] = "Voditeljica"
    assert take(owner, "2", given) == first
    first.refresh_from_db()
    assert (first.name, first.title) == ("Ana Horvat", "Voditeljica")
    assert [each.value for each in first.points.all()] == ["ana@firma.test", "+385 91 234 5678"]
    assert take(owner, "2", card("Ana", email="ana@firma.test")) is None
    assert Contact.objects.count() == 1


def test_two_items_of_one_source_stay_two_people_however_alike(owner):
    one = take(owner, "1", card("Ana", email="ured@firma.test"))
    other = take(owner, "2", card("Marko", email="ured@firma.test"))
    assert one != other


def test_a_number_joins_only_the_one_person_holding_it_whatever_its_spelling(owner):
    ana = take(owner, "1", card("Ana", phone="+385 91 234 5678"), Taken.Kind.ACTIVESYNC, "a")
    assert take(owner, "2", card("Ana H.", phone="091/234-5678")) == ana
    take(owner, "3", card("Ured", phone="01 2345 678"), Taken.Kind.ACTIVESYNC, "a")
    take(owner, "4", card("Recepcija", phone="012345678"), Taken.Kind.ACTIVESYNC, "a")
    assert take(owner, "5", card("Firma", phone="+38512345678")) not in (None, ana)
    assert Contact.objects.count() == 4


def test_a_name_joins_the_one_person_of_it_whatever_its_accents_and_case(owner):
    listed = entry(name="Mario Juric", given="Mario", family="Juric", address="mj@f.test")
    mario = taking.colleague(owner.pk, listed)
    given = card("Mario Jurić", email="mario.juruc@f.test", phone="091 665 1202")
    assert take(owner, "1", given, Taken.Kind.GOOGLE, "g") == mario
    mario.refresh_from_db()
    assert mario.name == "Mario Jurić"
    assert [each.value for each in mario.points.all()] == [
        "mj@f.test",
        "mario.juruc@f.test",
        "+385 91 665 1202",
    ]
    ana = take(owner, "2", card("ana horvat"), Taken.Kind.ACTIVESYNC, "a")
    assert take(owner, "3", card("Ana Horvat")) == ana
    take(owner, "4", card("Ana Horvat"), Taken.Kind.ACTIVESYNC, "a")
    assert take(owner, "5", card("ANA HORVAT"), Taken.Kind.GOOGLE, "g") != ana
    office = take(owner, "6", card("Ured"))
    assert office != take(owner, "7", card("Ured"), Taken.Kind.ACTIVESYNC, "a")
    assert Contact.objects.count() == 6


def test_every_number_is_kept_written_the_one_way_however_it_came(owner):
    given = card("Ana", phone="0912345678")
    given.points += [
        {"kind": "phone", "label": "work", "value": "01/2345-678", "parts": []},
        {"kind": "phone", "label": "other", "value": "0049 30 1234567", "parts": []},
        {"kind": "phone", "label": "other", "value": "1987", "parts": []},
    ]
    ana = take(owner, "1", given)
    assert [each.value for each in ana.points.all()] == [
        "+385 91 234 5678",
        "+385 1 2345 678",
        "+49 30 1234567",
        "1987",
    ]


def named(name: str, given: str, family: str, **points) -> Card:
    made = card(name, **points)
    made.fields.update(given=given, family=family)
    return made


def test_googles_name_stands_in_front_of_another_sources_but_not_of_the_users(owner):
    outlook = named("Zarko Babic", "Zarko", "Babic", email="zarko@firma.test")
    zarko = take(owner, "1", outlook)
    google = named("Žarko Babić", "Žarko", "Babić", email="zarko@firma.test")
    take(owner, "g1", google, Taken.Kind.GOOGLE, "ime@gmail.com")
    zarko.refresh_from_db()
    assert (zarko.name, zarko.given, zarko.family) == ("Žarko Babić", "Žarko", "Babić")
    other = named("Zeljko A.", "Zarko", "A.", email="zarko@firma.test")
    take(owner, "g2", other, Taken.Kind.GOOGLE, "ivo@firma.test")
    zarko.refresh_from_db()
    assert zarko.family == "Babić"

    vesna = take(owner, "2", named("Vesna Boskovic", "Vesna", "Boskovic", phone="091 111 2222"))
    cards.saved(vesna, named("", "Vesna", "Bošković Horvat", phone="091 111 2222"))
    google = named("Vesna Bošković", "Vesna", "Bošković", phone="+385911112222")
    take(owner, "g3", google, Taken.Kind.GOOGLE, "ime@gmail.com")
    vesna.refresh_from_db()
    assert vesna.family == "Bošković Horvat"


def entry(**given) -> Entry:
    values = {"host": "traveler.firma.test", "address": "ana@firma.test", "name": "Ana Horvat"}
    values["asked_at"] = timezone.now()
    return Entry.objects.create(**{**values, **given})


def test_a_colleague_shows_the_directorys_work_details_beside_their_own(owner):
    listed = entry(
        given="Ana", family="Horvat", title="Direktorica", company="Firma", mobile="0912"
    )
    contact = taking.colleague(owner.pk, listed)
    contact.title, contact.note = "Voditeljica", "Kći Lana"
    contact.save()
    shown = cards.card(Contact.objects.get())
    assert (shown.fields["title"], shown.fields["organisation"]) == ("Direktorica", "Firma")
    assert (shown.fields["name"], shown.fields["note"]) == ("Ana Horvat", "Kći Lana")
    assert [each["value"] for each in shown.points] == ["ana@firma.test", "0912"]
    assert taking.colleague(owner.pk, listed) is None
    assert taking.colleague(owner.pk, listed, chosen=True) == contact


def test_what_a_phone_gives_back_of_a_colleague_keeps_only_what_it_changed(owner):
    listed = entry(given="Ana", family="Horvat", title="Direktorica", mobile="0912")
    contact = taking.colleague(owner.pk, listed)
    back = parsed(written(cards.card(contact)))
    back.fields["note"] = "Kći Lana"
    back.points.append({"kind": "phone", "label": "home", "value": "01 111", "parts": []})
    cards.saved(contact, back, phone=True)
    contact.refresh_from_db()
    assert (contact.given, contact.family, contact.title, contact.note) == ("", "", "", "Kći Lana")
    assert [each.value for each in contact.points.all()] == ["ana@firma.test", "01 111"]


def test_a_colleague_the_directory_no_longer_lists_keeps_what_it_said_last(owner):
    listed = entry(given="Ana", family="Horvat", title="Direktorica", mobile="0912")
    contact = taking.colleague(owner.pk, listed)
    before = Contact.objects.get().revision
    directory._left(listed)
    contact.refresh_from_db()
    assert (contact.entry, contact.given, contact.title) == (None, "Ana", "Direktorica")
    assert contact.revision > before
    assert [each.value for each in contact.points.all()] == ["ana@firma.test", "0912"]
    assert Entry.objects.get().listed is False


def test_a_colleague_the_user_removed_comes_back_only_when_they_choose_them(owner):
    listed = entry()
    cards.deleted(taking.colleague(owner.pk, listed))
    assert taking.colleague(owner.pk, listed) is None
    again = taking.colleague(owner.pk, listed, chosen=True)
    assert Taken.objects.get().contact == again
