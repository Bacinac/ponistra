import io
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone
from openpyxl import load_workbook

from apps.actions.models import ActionRun
from apps.ai import installation, model
from apps.ai.tests.recorded import Recorded, message, used
from apps.blobs import store
from apps.collecting import delivering, months, taking
from apps.collecting.models import Collection, Item, Month
from apps.core import sealed
from apps.documents.models import Node
from apps.mail.models import Account, Attachment, Folder, Message, Role, Unsent
from apps.search.models import BlobPage, BlobText
from apps.users.models import User

pytestmark = pytest.mark.django_db

JSON = "application/json"
PDF = b"%PDF-1.7\n%"
MARTA = [{"name": "Marta", "address": "marta@example.com"}]


@pytest.fixture
def owner():
    return User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")


@pytest.fixture
def account(owner):
    return Account.objects.create(
        owner=owner,
        address="ivo@example.com",
        username="ivo@example.com",
        secret=sealed.seal("mail", "x"),
        default=True,
    )


@pytest.fixture
def inbox(owner):
    return Folder.objects.get_or_create(owner=owner, role=Role.INBOX)[0]


@pytest.fixture
def browser(client, owner, account):
    client.force_login(owner)
    taking._looked.clear()
    return client


def mail(account, folder, subject, sender, when, *files: tuple[str, bytes, str]):
    pk = secrets.token_hex(8)
    found = Message.objects.create(
        owner=account.owner,
        folder=folder,
        account=account,
        key=pk,
        raw=store.put(io.BytesIO(pk.encode())),
        subject=subject,
        sender={"name": sender.split("@")[0].title(), "address": sender},
        date=when,
        text=f"{subject}, hvala",
        attachments=bool(files),
    )
    for part, (name, data, text) in enumerate(files, start=2):
        blob = store.put(io.BytesIO(data + pk.encode() + name.encode()))
        Attachment.objects.create(
            message=found, blob=blob, part=str(part), name=name, type="application/pdf"
        )
        if text is not None:
            read = BlobText.objects.create(blob=blob, page_count=1, extracted_at=timezone.now())
            BlobPage.objects.create(source=read, number=1, text=text)
    return found


def made(browser, **given):
    fields = {
        "name": "Troškovi za Martu",
        "accounts": [],
        "senders": ["anthropic.com", "cloud.example"],
        "words": ["invoice", "receipt"],
        "attached": True,
        "recognise": False,
        "since": "2026-09-01",
        "to": MARTA,
        "account": None,
        "day": 11,
        "hour": 9,
        "sends": "draft",
        "text": "Pozdrav Marta,\nšaljem troškove.",
        "active": True,
        **given,
    }
    response = browser.post("/api/collections", fields, content_type=JSON)
    return response


def drained():
    while taking.looked() or taking.read_next():
        pass


def at(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=months.ZONE)


def test_a_collection_takes_the_mail_it_names_into_its_months_folders(browser, account, inbox):
    october = mail(
        account,
        inbox,
        "Your invoice",
        "billing@anthropic.com",
        at(2026, 10, 3),
        ("Invoice-123.pdf", PDF, "Total 20.00 USD"),
    )
    mail(account, inbox, "Invoice", "billing@cloud.example", at(2026, 10, 9))
    mail(account, inbox, "Ručak", "ana@anthropic.com", at(2026, 10, 5), ("menu.pdf", PDF, ""))
    mail(account, inbox, "Receipt", "billing@anthropic.com", at(2026, 8, 30), ("r.pdf", PDF, ""))
    junk = Folder.objects.create(owner=account.owner, role=Role.JUNK, name="Junk")
    mail(account, junk, "Invoice", "x@anthropic.com", at(2026, 10, 4), ("j.pdf", PDF, ""))
    response = made(browser)
    assert response.status_code == 201, response.json()
    collection = Collection.objects.get()
    assert collection.folder.title == "Troškovi za Martu"
    drained()
    item = Item.objects.get()
    assert (item.message, item.state, item.supplier) == (october, Item.State.KEPT, "Billing")
    assert (item.date, item.amount) == (date(2026, 10, 3), None)
    month = Month.objects.get()
    assert (month.month, month.folder.parent, month.folder.title) == (
        date(2026, 10, 1),
        collection.folder,
        "2026-10",
    )
    assert month.past
    files = Node.objects.filter(parent=month.folder)
    assert [(each.title, each.extension) for each in files] == [("2026-10-03 Invoice-123", "pdf")]
    assert item.files == [str(files.get().pk)]
    later = mail(
        account, inbox, "Invoice", "billing@cloud.example", at(2026, 11, 2), ("i.pdf", PDF, "")
    )
    taking.forget(collection.pk)
    drained()
    assert Item.objects.get(message=later).month.month == date(2026, 11, 1)


def test_what_the_collection_is_set_to_is_checked(browser):
    for given, error in [
        ({"name": ""}, "invalid_name"),
        ({"senders": ["nije adresa"]}, "collecting_invalid_senders"),
        ({"to": [{"address": "marta"}]}, "collecting_invalid_to"),
        ({"day": 29}, "collecting_invalid_day"),
        ({"since": "2099-01-01"}, "collecting_invalid_since"),
        ({"accounts": [999]}, "collecting_invalid_accounts"),
        ({"sends": "send", "to": []}, "collecting_no_recipients"),
    ]:
        response = made(browser, **given)
        assert (response.status_code, response.json()["error"]) == (400, error), given
    assert not Collection.objects.exists()


def test_recognising_bills_asks_the_owners_leave_and_the_model_reads_each(
    browser, account, inbox, monkeypatch
):
    monkeypatch.setattr(installation, "enabled", lambda: False)
    assert made(browser, recognise=True).json()["error"] == "ai_off"
    monkeypatch.setattr(installation, "enabled", lambda: True)
    assert made(browser, recognise=True).status_code == 428
    bill = {"bill": True, "supplier": "Anthropic, PBC", "date": "2026-10-02"}
    recorded = Recorded(
        message("tool_use", used("u1", "bill", {**bill, "amount": "21.60", "currency": "usd"})),
        message("tool_use", used("u2", "bill", {"bill": False})),
    )
    monkeypatch.setattr(model, "answer", recorded)
    mail(
        account,
        inbox,
        "Your receipt",
        "invoice@pay.example",
        at(2026, 10, 3),
        ("Receipt-1.pdf", PDF, "Anthropic, PBC Amount paid $21.60"),
    )
    mail(
        account,
        inbox,
        "Receipt for your order",
        "x@pay.example",
        at(2026, 10, 4),
        ("o.pdf", PDF, ""),
    )
    response = made(
        browser, recognise=True, consent="once", senders=["pay.example"], words=["receipt"]
    )
    assert response.status_code == 201, response.json()
    drained()
    kept, passed = Item.objects.order_by("message__date")
    assert (kept.state, kept.supplier, kept.amount, kept.currency, kept.date) == (
        Item.State.KEPT,
        "Anthropic, PBC",
        Decimal("21.60"),
        "USD",
        date(2026, 10, 2),
    )
    assert passed.state == Item.State.PASSED and passed.files == []
    assert "Amount paid $21.60" in str(recorded.asked[0]["messages"])
    runs = ActionRun.objects.filter(action="mail.gather")
    assert runs.count() == 2 and {run.consent for run in runs} == {"once"}


def test_a_model_the_owner_cannot_reach_leaves_the_message_waiting(
    browser, account, inbox, monkeypatch
):
    monkeypatch.setattr(installation, "enabled", lambda: True)
    made(browser, recognise=True, consent="once")

    def reached(user_id):
        raise installation.Unavailable("limit_reached")

    monkeypatch.setattr(installation, "allowed", reached)
    mail(account, inbox, "Invoice", "b@anthropic.com", at(2026, 10, 3), ("i.pdf", PDF, ""))
    drained()
    assert Item.objects.get().state == Item.State.WAITING
    assert browser.get("/api/collections").json()["collections"][0]["error"] == "limit_reached"


def test_a_message_waits_for_the_text_of_its_pdf(browser, account, inbox):
    made(browser)
    mail(account, inbox, "Invoice", "b@anthropic.com", at(2026, 10, 3), ("i.pdf", PDF, None))
    drained()
    item = Item.objects.get()
    assert item.state == Item.State.WAITING and item.tried_at is None
    Item.objects.update(created_at=timezone.now() - taking.TEXT_WAIT - timedelta(minutes=1))
    drained()
    assert Item.objects.get().state == Item.State.KEPT


def delivered_at(moment):
    month = delivering.due(moment)
    assert month is not None
    delivering.delivered(month)
    return Month.objects.get(pk=month.pk)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_on_its_day_the_month_goes_as_a_draft_with_its_files_and_table(
    live, browser, account, inbox
):
    await sync_to_async(_month_on_its_day)(browser, account, inbox)


def _month_on_its_day(browser, account, inbox):
    made(browser)
    collection = Collection.objects.get()
    Collection.objects.update(created_at=at(2026, 10, 1))
    mail(
        account,
        inbox,
        "Your invoice",
        "billing@anthropic.com",
        at(2026, 10, 3),
        ("Invoice-1.pdf", PDF, ""),
    )
    mail(account, inbox, "Invoice", "billing@cloud.example", at(2026, 10, 20), ("R-7.pdf", PDF, ""))
    drained()
    Item.objects.filter(sender="billing@anthropic.com").update(amount="20.00", currency="USD")
    Item.objects.filter(sender="billing@cloud.example").update(amount="5.25", currency="USD")
    assert delivering.due(at(2026, 11, 11, 8)) is None
    month = delivered_at(at(2026, 11, 11, 9))
    assert month.table.parent == month.folder and month.table.title == "Troškovi za Martu 2026-10"
    unsent = month.unsent
    assert unsent.send_at is None and unsent.written["to"] == MARTA
    assert unsent.written["subject"] == "Troškovi za Martu – listopad 2026"
    names = [each["name"] for each in unsent.written["files"]]
    assert names == [
        "2026-10-03 Invoice-1.pdf",
        "2026-10-20 R-7.pdf",
        "Troškovi za Martu 2026-10.xlsx",
    ]
    assert unsent.held.count() == 3
    html = unsent.written["html"]
    assert "<p>Pozdrav Marta,</p>" in html and "25,25" in html and "5,25" in html
    book = load_workbook(
        io.BytesIO(store.path_of(unsent.written["files"][-1]["sha256"]).read_bytes())
    )
    rows = list(book.active.values)
    assert rows[0] == ("Dobavljač", "Datum", "Iznos", "Valuta", "Datoteke", "Predmet")
    assert rows[1][:5] == (
        "Billing",
        datetime(2026, 10, 3),
        20,
        "USD",
        "2026-10-03 Invoice-1.pdf",
    )
    assert rows[-1][:4] == ("Ukupno", None, 25.25, "USD")
    assert delivering.due(at(2026, 11, 12)) is None
    delivering.delivered(month)
    again = Month.objects.get(pk=month.pk)
    assert again.table_id == month.table_id
    rows_again = list(
        load_workbook(
            io.BytesIO(store.path_of(again.unsent.written["files"][-1]["sha256"]).read_bytes())
        ).active.values
    )
    assert rows_again == rows
    assert collection.pk == month.collection_id


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_month_that_sends_itself_leaves_through_the_mail_loop(
    live, browser, account, inbox
):
    await sync_to_async(_month_sending_itself)(browser, account, inbox)


def _month_sending_itself(browser, account, inbox):
    made(browser, sends="send")
    Collection.objects.update(created_at=at(2026, 10, 1))
    mail(account, inbox, "Invoice", "b@anthropic.com", at(2026, 10, 3), ("i.pdf", PDF, ""))
    drained()
    month = delivered_at(at(2026, 11, 11, 10))
    assert month.unsent.send_at is not None and not month.unsent.sending


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_month_past_before_the_collection_goes_only_when_asked(
    live, browser, account, inbox
):
    await sync_to_async(_month_past_asked)(browser, account, inbox)


def _month_past_asked(browser, account, inbox):
    made(browser)
    mail(account, inbox, "Invoice", "b@anthropic.com", at(2026, 9, 3), ("i.pdf", PDF, ""))
    drained()
    month = Month.objects.get()
    assert month.past and delivering.due() is None
    collection = Collection.objects.get()
    response = browser.post(f"/api/collections/{collection.pk}/months/{month.pk}/send")
    assert response.status_code == 200
    assert delivering.deliver_next()
    assert Month.objects.get().delivered_at is not None
    assert Unsent.objects.count() == 1


def test_messages_chosen_by_hand_join_a_collection(browser, account, inbox):
    made(browser, senders=[], words=["nikad"])
    collection = Collection.objects.get()
    chosen = mail(
        account, inbox, "Račun", "ured@hep.example", at(2026, 10, 7), ("hep.pdf", PDF, "")
    )
    response = browser.post(
        "/api/mail/actions/mail.gather",
        {"target": {"messages": [chosen.pk]}, "parameters": {"collection": collection.pk}},
        content_type=JSON,
    )
    assert response.json() == {"changed": 1}
    drained()
    item = Item.objects.get()
    assert item.chosen and item.state == Item.State.KEPT and item.supplier == "Ured"
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    other = Collection.objects.create(owner=stranger, name="Tuđa", since=date(2026, 1, 1))
    response = browser.post(
        "/api/mail/actions/mail.gather",
        {"target": {"messages": [chosen.pk]}, "parameters": {"collection": other.pk}},
        content_type=JSON,
    )
    assert response.status_code == 404


def test_another_users_collection_is_not_found(browser, account):
    made(browser)
    collection = Collection.objects.get()
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    browser.force_login(stranger)
    assert browser.get(f"/api/collections/{collection.pk}").status_code == 404
    assert browser.get("/api/collections").json() == {"collections": []}
