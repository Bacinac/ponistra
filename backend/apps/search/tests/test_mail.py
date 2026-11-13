import io
from datetime import UTC, datetime
from itertools import count

import pytest

from apps.access.tests.test_access import create, person
from apps.blobs import store
from apps.imports.tests.test_xlsx import book
from apps.imports.tests.word_files import p, word_file
from apps.mail import sharing
from apps.mail.models import Account, Arrival, Attachment, Folder, Grant, Message, Source
from apps.mail.tests.test_views import kept

from .test_search import END, MARK, extract_all, pdf_bytes

pytestmark = pytest.mark.django_db

KEYS = count()


@pytest.fixture
def inbox(api):
    return Folder.objects.create(owner=api.user, name="inbox", role="inbox")


@pytest.fixture
def account(api):
    return kept(api.user)


def message(account: Account, folder: Folder, subject="", **fields) -> Message:
    fields = {
        "sender": {"name": "Ana Kovač", "address": "ana.kovac@firma.test"},
        "date": datetime(2026, 10, 1, 9, tzinfo=UTC),
        **fields,
    }
    return Message.objects.create(
        owner=account.owner,
        folder=folder,
        account=account,
        key=str(next(KEYS)),
        raw=store.put(io.BytesIO(b"Subject: x\r\n\r\n")),
        subject=subject,
        **fields,
    )


def found(client, q, **params) -> dict:
    response = client.get("/api/search", {"q": q, **params})
    assert response.status_code == 200, response.json()
    return response.json()


def subjects(client, q, **params) -> list[str]:
    return [each["subject"] for each in found(client, q, **params)["mail"]]


def test_a_message_is_found_by_its_subject_text_and_people(api, account, inbox):
    message(account, inbox, "Ponuda za Rijeku", text="Šaljem cijene opreme.")
    message(
        account,
        inbox,
        "Sastanak",
        sender={"name": "Marko", "address": "marko@grad.test"},
        to=[{"name": "", "address": "nabava@brezik.test"}],
    )
    assert subjects(api, "rijeka") == ["Ponuda za Rijeku"]
    assert subjects(api, "cijena") == ["Ponuda za Rijeku"]
    assert subjects(api, "kovač") == ["Ponuda za Rijeku"]
    assert subjects(api, "brezik") == ["Sastanak"]
    assert subjects(api, "nabava@brezik.test") == ["Sastanak"]


def test_a_hit_comes_with_the_message_as_its_list_shows_it_and_a_marked_snippet(
    api, account, inbox
):
    made = message(account, inbox, "Ponuda za Rijeku", text="Šaljem cijene opreme.", seen=True)
    [hit] = found(api, "ponuda")["mail"]
    assert (hit["id"], hit["folder"], hit["accounts"], hit["seen"]) == (
        made.pk,
        inbox.pk,
        [account.pk],
        True,
    )
    assert (hit["role"], hit["to"]) == ("inbox", [])
    assert hit["marked"] == f"{MARK}Ponuda{END} za Rijeku"
    assert hit["snippet"] == "Šaljem cijene opreme."
    assert hit["attachment"] is None
    [hit] = found(api, "cijene")["mail"]
    assert hit["snippet"] == f"Šaljem {MARK}cijene{END} opreme."


def test_a_subject_ranks_above_the_text_and_a_typo_still_finds_it(api, account, inbox):
    message(account, inbox, "Sastanak", text="Donosim ugovor.")
    message(account, inbox, "Ugovor", text="U privitku.", date=datetime(2025, 1, 1, tzinfo=UTC))
    assert subjects(api, "ugovor") == ["Ugovor", "Sastanak"]
    assert subjects(api, "ugvor") == ["Ugovor"]


def test_the_text_of_a_pdf_it_carries_is_found_with_its_page(api, account, inbox):
    made = message(account, inbox, "Dokumentacija", attachments=True)
    blob = store.put(io.BytesIO(pdf_bytes("Uvod", "Jamstveni list")))
    Attachment.objects.create(
        message=made, blob=blob, part="2", name="jamstvo.pdf", type="application/pdf"
    )
    Attachment.objects.create(
        message=message(account, inbox, "Slika"),
        blob=blob,
        part="2",
        name="jamstvo.pdf",
        type="application/pdf",
        inline=True,
    )
    extract_all()
    [hit] = found(api, "jamstveni")["mail"]
    assert hit["subject"] == "Dokumentacija"
    assert hit["attachment"]["name"] == "jamstvo.pdf" and hit["attachment"]["page"] == 2
    assert hit["snippet"] == f"{MARK}Jamstveni{END} list"


def test_the_text_of_an_office_file_it_carries_is_found_without_a_page(
    api, account, inbox, tmp_path
):
    letter = store.put(io.BytesIO(word_file(p("Uvjeti") + p("Jamstveni rok dvije godine"))))
    sheets = book(tmp_path, {"Cijene": {"A1": "Dizalica", "B1": "1250"}, "Rok": {"A1": "Zima"}})
    prices = store.put(io.BytesIO(sheets.read_bytes()))
    for blob, name in [(letter, "uvjeti.docx"), (prices, "cijene.xlsx")]:
        Attachment.objects.create(
            message=message(account, inbox, name), blob=blob, part="2", name=name, type=""
        )
    extract_all()
    [hit] = found(api, "jamstveni")["mail"]
    assert (hit["attachment"]["name"], hit["attachment"]["page"]) == ("uvjeti.docx", None)
    assert hit["snippet"] == f"Uvjeti\n{MARK}Jamstveni{END} rok dvije godine"
    [hit] = found(api, "dizalica")["mail"]
    assert hit["snippet"] == f"{MARK}Dizalica{END} | 1250"
    assert subjects(api, "zima") == ["cijene.xlsx"]


def test_only_the_users_own_mail_is_searched(api, account, inbox):
    message(account, inbox, "Ponuda")
    ana = person("ana@example.com")
    assert subjects(ana, "ponuda") == []


def test_the_mail_of_a_shared_mailbox_is_searched_while_its_grant_lasts(api, account, inbox):
    ana = person("ana@example.com")
    box = sharing.made(ana.user, "Prodaja")
    held = kept(box, "prodaja@firma.test")
    its_inbox = Folder.objects.create(owner=box, name="inbox", role="inbox")
    junk = Folder.objects.create(owner=box, name="junk", role="junk")
    message(account, inbox, "Ponuda iz moje")
    message(held, its_inbox, "Ponuda iz prodaje")
    message(held, junk, "Ponuda iz neželjene prodaje")
    assert subjects(api, "ponuda") == ["Ponuda iz moje"]
    grant = Grant.objects.create(mailbox=box, user=api.user, role="read", created_by=ana.user)
    hits = {each["subject"]: each for each in found(api, "ponuda")["mail"]}
    assert set(hits) == {"Ponuda iz moje", "Ponuda iz prodaje"}
    assert hits["Ponuda iz moje"]["box"] is None
    assert hits["Ponuda iz prodaje"]["box"] == {"id": box.pk, "name": "Prodaja"}
    assert hits["Ponuda iz prodaje"]["accounts"] == [held.pk]
    assert subjects(api, "ponuda mapa:neželjena") == ["Ponuda iz neželjene prodaje"]
    assert subjects(api, "račun:prodaja") == ["Ponuda iz prodaje"]
    grant.delete()
    assert subjects(api, "ponuda") == ["Ponuda iz moje"]


def test_the_junk_and_the_trash_only_when_a_folder_asks_for_them(api, account, inbox):
    junk = Folder.objects.create(owner=api.user, name="junk", role="junk")
    trash = Folder.objects.create(owner=api.user, name="trash", role="trash")
    message(account, inbox, "Ponuda iz ulazne")
    message(account, junk, "Ponuda iz neželjene")
    message(account, trash, "Ponuda iz smeća")
    assert subjects(api, "ponuda") == ["Ponuda iz ulazne"]
    assert subjects(api, "ponuda mapa:smeće") == ["Ponuda iz smeća"]
    assert subjects(api, "ponuda folder:spam") == ["Ponuda iz neželjene"]


def test_a_folder_by_its_name_takes_the_folders_under_it(api, account, inbox):
    clients = Folder.objects.create(owner=api.user, name="Klijenti")
    rijeka = Folder.objects.create(owner=api.user, name="Rijeka", parent=clients)
    message(account, inbox, "Ponuda iz ulazne")
    message(account, rijeka, "Ponuda za Rijeku")
    assert subjects(api, "ponuda mapa:klijent") == ["Ponuda za Rijeku"]


def test_filters_narrow_by_sender_account_attachment_and_when_it_came(api, account, inbox):
    message(account, inbox, "Ponuda od Ane", attachments=True)
    message(
        account,
        inbox,
        "Ponuda od Marka",
        sender={"name": "Marko", "address": "marko@grad.test"},
        date=datetime(2025, 2, 3, 9, tzinfo=UTC),
    )
    work = kept(api.user, "posao@brezik.test")
    both = message(work, inbox, "Ponuda na dva računa")
    source = Source.objects.create(account=account, name="INBOX", folder=inbox)
    Arrival.objects.create(message=both, source=source, uid=1)
    assert sorted(subjects(api, "ponuda od:ana")) == ["Ponuda na dva računa", "Ponuda od Ane"]
    assert subjects(api, "ponuda od:grad.test") == ["Ponuda od Marka"]
    assert subjects(api, "ponuda račun:brezik") == ["Ponuda na dva računa"]
    assert len(subjects(api, "ponuda account:mox")) == 3
    assert subjects(api, "ponuda ima:privitak") == ["Ponuda od Ane"]
    assert subjects(api, "ponuda datum:2025") == ["Ponuda od Marka"]
    assert subjects(api, "ponuda izmjena:2.2025.") == ["Ponuda od Marka"]


def test_documents_and_mail_come_apart_and_a_kind_takes_one(api, account, inbox):
    message(account, inbox, "Ponuda")
    create(api, "document", "Ponuda Rijeka")
    both = found(api, "ponuda")
    assert ([each["title"] for each in both["documents"]], len(both["mail"])) == (
        ["Ponuda Rijeka"],
        1,
    )
    assert found(api, "ponuda vrsta:pošta")["documents"] == []
    assert found(api, "ponuda vrsta:dokument")["mail"] == []
    assert found(api, "ponuda ima:privitak")["documents"] == []


def test_searching_in_a_folder_of_documents_leaves_the_mail_out(api, account, inbox):
    message(account, inbox, "Ponuda")
    folder = create(api, "folder", "Ponude")
    create(api, "document", "Ponuda Rijeka", folder)
    within = found(api, "ponuda", **{"in": folder})
    assert (len(within["documents"]), within["mail"]) == (1, [])


def test_filters_alone_list_the_mail_newest_first(api, account, inbox):
    message(account, inbox, "Starija", date=datetime(2025, 1, 1, tzinfo=UTC))
    message(account, inbox, "Novija", text="Tekst poruke.", preview="Tekst poruke.")
    [newer, older] = found(api, "vrsta:pošta")["mail"]
    assert (newer["subject"], older["subject"]) == ("Novija", "Starija")
    assert (newer["marked"], newer["snippet"]) == ("Novija", "Tekst poruke.")
