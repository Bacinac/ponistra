import pytest

from apps.contacts.models import Contact
from apps.reader.tests.test_shown import CARDS
from apps.search.tests.test_search import upload_file


@pytest.mark.django_db
def test_the_people_of_a_card_file_join_the_address_book_once(api):
    file = upload_file(api, "Kontakti", CARDS)
    assert api.post(f"/api/nodes/{file}/contacts").json() == {"made": 2, "joined": 0}
    assert api.post(f"/api/nodes/{file}/contacts").json() == {"made": 0, "joined": 2}
    ana = Contact.objects.get(owner=api.user, organisation="Lipa Studio")
    assert set(ana.points.values_list("value", flat=True)) == {
        "ana@example.com",
        "+385 91 000 0000",
    }
    assert Contact.objects.filter(owner=api.user).count() == 2


@pytest.mark.django_db
def test_only_a_card_file_joins_the_address_book(api):
    plain = upload_file(api, "Biljeska", b"Obican tekst\n")
    refused = api.post(f"/api/nodes/{plain}/contacts")
    assert (refused.status_code, refused.json()["error"]) == (400, "wrong_kind")
