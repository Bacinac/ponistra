import io
import secrets
from datetime import timedelta
from email.message import EmailMessage

import anyio
import pytest
from django.utils import timezone

from apps.blobs import store
from apps.blobs.models import Blob
from apps.blobs.tests.uploads import uploaded
from apps.calendar import availability
from apps.chat.models import Conversation, Member
from apps.mail import absence, automatic, later, sync, taking, views
from apps.mail.imap import imap
from apps.mail.models import Away, AwayAnswer, Folder, Message, Role, Source, Unsent
from apps.push.models import Notice, Subscription

from .mox import LOGIN, SERVER, kept_in_sent

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.xdist_group("mox")]

PDF = b"%PDF-1.7\n%later"
TO = [{"name": "", "address": "ana@example.com"}]


@pytest.fixture
def writer(client, account):
    client.force_login(account.owner)
    with imap(*SERVER, LOGIN) as connection:
        sync.sources(connection, account)
    return client


def moment(**ahead) -> str:
    return (timezone.now() + timedelta(**ahead)).isoformat()


def scheduled(client, account, at, **given):
    fields = {"account": account.pk, "to": TO, "subject": "Kasnije", "html": "<p>Tekst</p>"}
    return client.post(
        "/api/mail/later", {**fields, "at": at, **given}, content_type="application/json"
    )


def swept():
    while anyio.run(later._step):
        pass


def test_a_message_waits_for_its_moment_and_then_leaves(writer, account):
    subject = f"Kasnije {secrets.token_hex(4)}"
    made = scheduled(writer, account, moment(hours=1), subject=subject).json()
    assert made["send_at"] and not made["failed"]
    swept()
    assert writer.get("/api/mail/later").json()["later"][0]["id"] == made["id"]
    assert writer.get("/api/mail/unsent").json() == {"unsent": []}

    Unsent.objects.filter(pk=made["id"]).update(send_at=timezone.now() - timedelta(seconds=1))
    swept()
    assert writer.get("/api/mail/later").json() == {"later": []}
    assert Message.objects.filter(subject=subject, folder__role=Role.SENT).exists()
    assert kept_in_sent(subject)["To"] == "ana@example.com"


def test_what_cannot_be_sent_is_refused_when_it_is_handed_over(writer, account):
    answer = scheduled(writer, account, moment(hours=1), to=[])
    assert answer.status_code == 400 and answer.json()["error"] == "no_recipients"
    assert scheduled(writer, account, "tomorrow").json()["error"] == "invalid_at"
    assert scheduled(writer, account, "2026-11-09T08:00:00").json()["error"] == "invalid_at"


def test_a_message_that_fails_stays_with_its_reason_and_the_user_is_told(writer, account):
    Subscription.objects.create(
        user=account.owner, endpoint="https://push.example/1", p256dh=b"k", auth=b"a"
    )
    account.smtp_port = 1
    account.save(update_fields=["smtp_port"])
    made = scheduled(writer, account, moment(seconds=-1)).json()
    swept()

    (waiting,) = writer.get("/api/mail/later").json()["later"]
    assert (waiting["id"], waiting["failed"]) == (made["id"], "smtp_unreachable")
    assert not waiting["sending"]
    notice = Notice.objects.get(user=account.owner, kind=Notice.Kind.LATER)
    assert notice.data == {"event": "failed", "subject": "Kasnije"}

    swept()
    assert Notice.objects.filter(kind=Notice.Kind.LATER).count() == 1


def test_one_that_failed_leaves_when_given_a_new_moment(writer, account):
    subject = f"Ponovno {secrets.token_hex(4)}"
    account.smtp_port = 1
    account.save(update_fields=["smtp_port"])
    made = scheduled(writer, account, moment(seconds=-1), subject=subject).json()
    swept()
    account.smtp_port = 1587
    account.save(update_fields=["smtp_port"])

    answer = writer.patch(
        f"/api/mail/later/{made['id']}", {"at": moment()}, content_type="application/json"
    )
    assert answer.json()["failed"] == ""
    swept()
    assert writer.get("/api/mail/later").json() == {"later": []}
    kept_in_sent(subject)


def test_taken_off_its_moment_it_is_unfinished_again(writer, account):
    made = scheduled(writer, account, moment(seconds=-1)).json()
    writer.patch(f"/api/mail/later/{made['id']}", {"at": None}, content_type="application/json")
    swept()
    assert writer.get("/api/mail/later").json() == {"later": []}
    assert [each["id"] for each in writer.get("/api/mail/unsent").json()["unsent"]] == [made["id"]]


def test_a_message_leaving_this_moment_can_no_longer_be_changed(writer, account):
    made = scheduled(writer, account, moment(hours=1)).json()
    Unsent.objects.filter(pk=made["id"]).update(sending=True)
    url = f"/api/mail/later/{made['id']}"
    answer = writer.patch(url, {"at": None}, content_type="application/json")
    assert (answer.status_code, answer.json()["error"]) == (409, "mail_sending")
    assert writer.delete(f"/api/mail/unsent/{made['id']}").status_code == 409


def test_a_restart_never_sends_again_what_may_have_left(writer, account):
    made = scheduled(writer, account, moment(hours=1)).json()
    Unsent.objects.filter(pk=made["id"]).update(sending=True, send_at=timezone.now())
    later.interrupted()
    swept()
    (waiting,) = writer.get("/api/mail/later").json()["later"]
    assert (waiting["sending"], waiting["failed"]) == (False, "mail_interrupted")


def test_when_the_account_is_gone_the_message_stays_and_says_so(writer, account):
    made = scheduled(writer, account, moment(seconds=-1)).json()
    Unsent.objects.filter(pk=made["id"]).update(account=None)
    swept()
    (waiting,) = writer.get("/api/mail/later").json()["later"]
    assert waiting["failed"] == "mail_account_gone"
    retried = writer.patch(
        f"/api/mail/later/{made['id']}", {"at": moment()}, content_type="application/json"
    )
    assert (retried.status_code, retried.json()["error"]) == (409, "mail_account_gone")


def test_the_files_of_a_message_outlive_the_grace_of_an_upload(writer, account):
    sha256 = uploaded(writer, PDF)["sha256"]
    files = [{"sha256": sha256, "name": "ponuda.pdf"}]
    scheduled(writer, account, moment(days=3), files=files)
    Blob.objects.filter(pk=sha256).update(uploaded_at=timezone.now() - timedelta(days=1))
    store.collect()
    assert Blob.objects.filter(pk=sha256).exists()


def test_written_without_the_network_it_leaves_once_however_often_it_is_handed_over(
    writer, account
):
    subject = f"Bez mreže {secrets.token_hex(4)}"
    key = "6f1c2b8e-41d2-4a8e-9a3c-0d5e7f9b1a20"
    made = scheduled(writer, account, moment(), subject=subject, queued=key).json()
    again = scheduled(writer, account, moment(), subject=subject, queued=key)
    assert (again.status_code, again.json()["id"]) == (200, made["id"])
    swept()
    sent = Message.objects.get(subject=subject, folder__role=Role.SENT)
    assert sent.message_id == f"<{key}@{account.address.rpartition('@')[2]}>"
    assert scheduled(writer, account, moment(), subject=subject, queued=key).json() == {
        "queued": key,
        "sent": True,
    }
    swept()
    assert Message.objects.filter(subject=subject, folder__role=Role.SENT).count() == 1
    assert scheduled(writer, account, moment(), queued="nije").json()["error"] == "invalid_queued"


def test_kept_without_the_network_an_unsent_message_is_made_once_and_then_changed(writer, account):
    key = "0b9e5f3a-7c21-4d6e-8f10-2a3b4c5d6e7f"
    fields = {"account": account.pk, "to": TO, "subject": "Prvo", "html": "", "queued": key}
    made = writer.post("/api/mail/unsent", fields, content_type="application/json")
    changed = writer.post(
        "/api/mail/unsent", {**fields, "subject": "Drugo"}, content_type="application/json"
    )
    assert (made.status_code, changed.status_code) == (201, 200)
    assert changed.json()["id"] == made.json()["id"]
    assert [each["subject"] for each in writer.get("/api/mail/unsent").json()["unsent"]] == [
        "Drugo"
    ]
    handed = scheduled(writer, account, moment(), subject="Drugo", queued=key).json()
    assert handed["id"] == made.json()["id"] and handed["send_at"]
    swept()
    assert writer.get("/api/mail/unsent").json() == {"unsent": []}
    assert writer.get("/api/mail/later").json() == {"later": []}


def test_another_users_message_is_not_found(client, writer, account, django_user_model):
    made = scheduled(writer, account, moment(hours=1)).json()
    client.force_login(django_user_model.objects.create_user("drugi@example.com", "x" * 16))
    answer = client.patch(
        f"/api/mail/later/{made['id']}", {"at": None}, content_type="application/json"
    )
    assert answer.status_code == 404
    assert client.get("/api/mail/later").json() == {"later": []}


@pytest.fixture
def inbox(account):
    return Folder.objects.get_or_create(owner=account.owner, role=Role.INBOX)[0]


def kept(account, folder, subject="Stara ponuda", date=None, **fields):
    pk = secrets.token_hex(8)
    return Message.objects.create(
        owner=account.owner,
        folder=folder,
        account=account,
        key=pk,
        raw=store.put(io.BytesIO(pk.encode())),
        message_id=f"<{pk}@example.com>",
        subject=subject,
        date=date or timezone.now() - timedelta(days=30),
        **fields,
    )


def acted(client, folder, **given):
    return client.post(
        f"/api/mail/folders/{folder.pk}/chosen", given, content_type="application/json"
    )


def listing(client, folder):
    return [
        each["id"]
        for each in client.get(f"/api/mail/folders/{folder.pk}/messages").json()["messages"]
    ]


def test_a_snoozed_message_leaves_the_inbox_and_comes_back_on_top(writer, account, inbox):
    Subscription.objects.create(
        user=account.owner, endpoint="https://push.example/1", p256dh=b"k", auth=b"a"
    )
    old = kept(account, inbox, seen=True)
    newer = kept(account, inbox, subject="Novija", date=timezone.now() - timedelta(days=1))
    answer = acted(writer, inbox, action="snooze", at=moment(hours=1), where={"messages": [old.pk]})
    assert answer.json() == {"changed": 1}
    assert listing(writer, inbox) == [newer.pk]
    old.refresh_from_db()
    snoozed = old.folder
    assert snoozed.role == Role.SNOOZED and listing(writer, snoozed) == [old.pk]
    swept()
    assert listing(writer, inbox) == [newer.pk]

    Message.objects.filter(pk=old.pk).update(snoozed_until=timezone.now() - timedelta(seconds=1))
    swept()
    assert listing(writer, inbox) == [old.pk, newer.pk]
    old.refresh_from_db()
    assert (old.seen, old.snoozed_until, old.date.date()) == (
        False,
        None,
        (timezone.now() - timedelta(days=30)).date(),
    )
    notice = Notice.objects.get(user=account.owner, kind=Notice.Kind.MAIL)
    assert notice.data["message"] == old.pk and notice.data["folder"] == inbox.pk


def test_the_provider_is_not_touched_by_snoozing(writer, account, inbox, monkeypatch):
    message = kept(account, inbox)
    called = []
    monkeypatch.setattr("apps.mail.imap.imap", lambda *a: called.append(a))
    acted(writer, inbox, action="snooze", at=moment(hours=1), where={"messages": [message.pk]})
    assert called == []


def test_returned_by_hand_it_comes_to_the_top_now(writer, account, inbox):
    message = kept(account, inbox)
    newer = kept(account, inbox, subject="Novija", date=timezone.now() - timedelta(days=1))
    acted(writer, inbox, action="snooze", at=moment(days=2), where={"messages": [message.pk]})
    message.refresh_from_db()
    answer = acted(writer, message.folder, action="unsnooze", where={"messages": [message.pk]})
    assert answer.json() == {"changed": 1}
    assert listing(writer, inbox) == [message.pk, newer.pk]


def test_a_snoozed_message_moved_by_hand_stays_where_it_was_put(writer, account, inbox):
    archive = Folder.objects.get_or_create(owner=account.owner, role=Role.ARCHIVE)[0]
    message = kept(account, inbox)
    acted(writer, inbox, action="snooze", at=moment(seconds=1), where={"messages": [message.pk]})
    message.refresh_from_db()
    acted(writer, message.folder, action="move", to=archive.pk, where={"messages": [message.pk]})
    Message.objects.filter(pk=message.pk).update(returned_at=None)
    swept()
    message.refresh_from_db()
    assert (message.folder_id, message.snoozed_until) == (archive.pk, None)


def test_what_may_not_be_snoozed(writer, account, inbox):
    sent_folder = Folder.objects.get_or_create(owner=account.owner, role=Role.SENT)[0]
    message = kept(account, sent_folder)
    answer = acted(
        writer, sent_folder, action="snooze", at=moment(hours=1), where={"messages": [message.pk]}
    )
    assert answer.json() == {"changed": 0}
    other = kept(account, inbox)
    late = acted(
        writer, inbox, action="snooze", at=moment(hours=-1), where={"messages": [other.pk]}
    )
    assert late.json()["error"] == "invalid_at"
    assert (
        acted(writer, inbox, action="move", to="snoozed", where={"messages": [other.pk]}).json()[
            "error"
        ]
        == "invalid_to"
    )


def test_a_list_goes_on_past_a_message_that_came_back(writer, account, inbox):
    message = kept(account, inbox)
    filler = [
        kept(account, inbox, subject=str(at), date=timezone.now() - timedelta(minutes=at))
        for at in range(1, views.PAGE + 2)
    ]
    Message.objects.filter(pk=message.pk).update(returned_at=timezone.now())
    url = f"/api/mail/folders/{inbox.pk}/messages"
    first = writer.get(url).json()
    assert first["messages"][0]["id"] == message.pk
    second = writer.get(url, {"before": first["before"]}).json()
    seen = {each["id"] for each in first["messages"]} | {each["id"] for each in second["messages"]}
    assert seen == {message.pk, *(each.pk for each in filler)}


ANA = {"name": "Ana", "address": "ana@example.com"}


@pytest.fixture
def outgoing(account):
    return Folder.objects.get_or_create(owner=account.owner, role=Role.SENT)[0]


def awaited(account, folder, **fields):
    return kept(
        account,
        folder,
        subject="Ponuda",
        to=[ANA],
        sender={"name": "", "address": account.address},
        seen=True,
        awaited_until=timezone.now() - timedelta(seconds=1),
        **fields,
    )


def test_no_one_answering_brings_it_to_the_top_unread(writer, account, inbox, outgoing):
    Subscription.objects.create(
        user=account.owner, endpoint="https://push.example/1", p256dh=b"k", auth=b"a"
    )
    newer = kept(account, inbox, subject="Novija", date=timezone.now() - timedelta(days=1))
    message = awaited(account, outgoing)
    swept()
    assert listing(writer, inbox) == [message.pk, newer.pk]
    message.refresh_from_db()
    assert message.unanswered and not message.seen and message.awaited_until is None
    notice = Notice.objects.get(kind=Notice.Kind.LATER)
    assert notice.data["message"] == message.pk and notice.data["event"] == "unanswered"


def answer(account, folder, sender=ANA, **fields):
    return kept(account, folder, subject="Re: Ponuda", sender=sender, **fields)


@pytest.mark.parametrize("field", ["in_reply_to", "references"])
def test_an_answer_in_the_thread_leaves_it_in_sent(writer, account, inbox, outgoing, field):
    message = awaited(account, outgoing)
    answer(account, inbox, **{field: message.message_id})
    swept()
    message.refresh_from_db()
    assert message.folder == outgoing and message.awaited_until is None and not message.unanswered


def test_an_absence_notice_and_the_users_own_follow_up_are_no_answer(
    writer, account, inbox, outgoing
):
    message = awaited(account, outgoing)
    answer(account, inbox, in_reply_to=message.message_id, automatic=True)
    answer(
        account,
        outgoing,
        sender={"name": "", "address": account.address.upper()},
        in_reply_to=message.message_id,
    )
    swept()
    message.refresh_from_db()
    assert message.folder == inbox and message.unanswered


def test_under_rewritten_ids_a_recipient_answering_under_the_subject_counts(
    writer, account, inbox, outgoing
):
    message = awaited(account, outgoing)
    answer(account, inbox, date=timezone.now())
    swept()
    message.refresh_from_db()
    assert message.folder == outgoing


def test_someone_else_under_the_same_subject_is_no_answer(writer, account, inbox, outgoing):
    message = awaited(account, outgoing)
    answer(account, inbox, sender={"name": "", "address": "ivan@example.com"}, date=timezone.now())
    swept()
    message.refresh_from_db()
    assert message.folder == inbox


def test_a_deleted_message_does_not_come_back(writer, account):
    trash = Folder.objects.get_or_create(owner=account.owner, role=Role.TRASH)[0]
    message = awaited(account, trash)
    swept()
    message.refresh_from_db()
    assert message.folder == trash and message.awaited_until is None


def test_waiting_is_set_and_ended_on_a_sent_message_only(writer, account, inbox, outgoing):
    sent, received = kept(account, outgoing), kept(account, inbox)
    at = moment(days=3)
    answer_ = acted(writer, outgoing, action="await", at=at, where={"messages": [sent.pk]})
    assert answer_.json() == {"changed": 1}
    answer_ = acted(writer, inbox, action="await", at=at, where={"messages": [received.pk]})
    assert answer_.json() == {"changed": 0}
    sent.refresh_from_db()
    assert sent.awaited_until is not None
    acted(writer, outgoing, action="unawait", where={"messages": [sent.pk]})
    sent.refresh_from_db()
    assert sent.awaited_until is None
    past = acted(
        writer, outgoing, action="await", at=moment(hours=-1), where={"messages": [sent.pk]}
    )
    assert past.status_code == 400 and past.json()["error"] == "invalid_at"


def composed(account, subject, **given):
    return {
        "account": account.pk,
        "to": TO,
        "cc": [],
        "bcc": [],
        "subject": subject,
        "html": "<p>Tekst</p>",
        "files": [],
        **given,
    }


def test_a_message_sent_with_a_date_waits_for_its_answer(writer, account):
    subject = f"Čekanje {secrets.token_hex(4)}"
    answered = writer.post(
        "/api/mail/send",
        composed(account, subject, awaited=moment(days=2)),
        content_type="application/json",
    )
    assert answered.status_code == 200
    assert Message.objects.get(subject=subject).awaited_until is not None


def test_the_date_of_a_scheduled_message_comes_after_it_leaves_and_goes_with_it(writer, account):
    subject = f"Kasnije {secrets.token_hex(4)}"
    refused = writer.post(
        "/api/mail/later",
        composed(account, subject, at=moment(days=2), awaited=moment(days=1)),
        content_type="application/json",
    )
    assert refused.json()["error"] == "mail_awaited_before_sending"
    made = writer.post(
        "/api/mail/later",
        composed(account, subject, at=moment(seconds=1), awaited=moment(days=2)),
        content_type="application/json",
    )
    assert made.status_code == 201 and made.json()["awaited"]
    Unsent.objects.filter(pk=made.json()["id"]).update(send_at=timezone.now())
    swept()
    assert Message.objects.get(subject=subject).awaited_until is not None


@pytest.mark.parametrize(
    "headers,sender,expected",
    [
        ({}, "ana@example.com", False),
        ({"Auto-Submitted": "no"}, "ana@example.com", False),
        ({"Auto-Submitted": "auto-replied"}, "ana@example.com", True),
        ({"Auto-Submitted": "auto-generated; foo=bar"}, "ana@example.com", True),
        ({"X-Autoreply": "yes"}, "ana@example.com", True),
        ({"Return-Path": "<>"}, "ana@example.com", True),
        ({}, "noreply@example.com", True),
        ({}, "no-reply@example.com", True),
        ({}, "MAILER-DAEMON@example.com", True),
        ({}, "bounces+x@example.com", True),
        ({}, "list-request@example.com", True),
        ({}, "owner-list@example.com", True),
        ({}, "replynot@example.com", False),
    ],
)
def test_what_a_program_wrote(headers, sender, expected):
    message = EmailMessage()
    for name, value in headers.items():
        message[name] = value
    assert automatic.by_program(message, sender) is expected


@pytest.fixture
def away(writer, account):
    now = timezone.now()
    return Away.objects.create(
        owner=account.owner,
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(days=3),
        text_hr="Odsutan sam.",
        text_en="I am away.",
    )


def incoming(account, *headers, sender="ana@example.com", to=None, subject="Upit"):
    lines = [
        f"From: {sender}",
        f"To: {to or account.address}",
        f"Subject: {subject}",
        "Date: Sun, 08 Nov 2026 12:00:00 +0100",
        f"Message-ID: <{secrets.token_hex(8)}@example.com>",
        *headers,
        "",
        "Tekst",
    ]
    return "\r\n".join(lines).encode()


def arriving(account, raw):
    source = account.sources.get(kind=Source.Kind.INBOX)
    return taking.took(source, raw, {"seen": False}, fresh=True)


def test_someone_writing_is_answered_once_as_the_rfc_asks(writer, account, away):
    subject = f"Upit {secrets.token_hex(4)}"
    first = arriving(
        account, incoming(account, "Return-Path: <ana.bounce@example.com>", subject=subject)
    )
    swept()
    reply = kept_in_sent(f"Auto: {subject}")
    assert reply["Auto-Submitted"] == "auto-replied"
    assert reply["To"] == "ana.bounce@example.com"
    assert reply["In-Reply-To"] == first.message_id
    assert "Odsutan sam." in reply.get_body().get_content()
    assert "I am away." in reply.get_body().get_content()
    arriving(account, incoming(account, "Return-Path: <ana.bounce@example.com>", subject="Opet"))
    swept()
    assert AwayAnswer.objects.filter(away=away).count() == 1
    assert not AwayAnswer.objects.filter(due=True).exists()


@pytest.mark.parametrize(
    "header",
    [
        "Auto-Submitted: auto-replied",
        "Precedence: bulk",
        "Precedence: list",
        "List-Id: <lista.example.com>",
        "List-Unsubscribe: <mailto:x@example.com>",
        "X-Auto-Response-Suppress: OOF",
        "Return-Path: <>",
    ],
)
def test_what_is_not_answered(writer, account, away, header):
    arriving(account, incoming(account, header))
    assert not AwayAnswer.objects.exists()


@pytest.mark.parametrize("sender", ["noreply@example.com", "MAILER-DAEMON@example.com"])
def test_those_no_one_reads_are_not_answered(writer, account, away, sender):
    arriving(account, incoming(account, sender=sender))
    assert not AwayAnswer.objects.exists()


def test_a_message_not_addressed_to_the_user_is_not_answered(writer, account, away):
    arriving(account, incoming(account, to="lista@example.com"))
    assert not AwayAnswer.objects.exists()


def test_outside_the_period_nothing_is_answered(writer, account, away):
    Away.objects.filter(pk=away.pk).update(starts_at=timezone.now() + timedelta(hours=1))
    arriving(account, incoming(account))
    assert not AwayAnswer.objects.exists()


def test_a_new_period_answers_everyone_again_and_a_new_wording_does_not(writer, account, away):
    arriving(account, incoming(account))
    assert AwayAnswer.objects.count() == 1
    fields = {
        "starts_at": away.starts_at.isoformat(),
        "ends_at": away.ends_at.isoformat(),
        "text_hr": "Novo.",
        "text_en": "",
    }
    assert writer.put("/api/mail/away", fields, content_type="application/json").status_code == 200
    assert AwayAnswer.objects.count() == 1
    fields["ends_at"] = (away.ends_at + timedelta(days=1)).isoformat()
    assert writer.put("/api/mail/away", fields, content_type="application/json").status_code == 200
    assert AwayAnswer.objects.count() == 0


def test_a_period_needs_words_and_an_end_after_its_start(writer, account):
    fields = {"starts_at": moment(days=2), "ends_at": moment(days=3), "text_hr": " ", "text_en": ""}
    empty = writer.put("/api/mail/away", fields, content_type="application/json")
    assert empty.json()["error"] == "mail_away_empty"
    fields |= {"text_hr": "Odsutan", "starts_at": moment(days=4)}
    backwards = writer.put("/api/mail/away", fields, content_type="application/json")
    assert backwards.json()["error"] == "invalid_at"


def test_answers_that_fail_are_told_once_and_a_good_one_clears_it(
    writer, account, away, monkeypatch
):
    async def refused(*_):
        raise views.imap.Failed("mail_unreachable")

    Subscription.objects.create(
        user=account.owner, endpoint="https://push.example/1", p256dh=b"k", auth=b"a"
    )
    monkeypatch.setattr("apps.mail.later.sending.delivered", refused)
    arriving(account, incoming(account))
    arriving(account, incoming(account, sender="ivan@example.com"))
    swept()
    away.refresh_from_db()
    assert away.failed == "mail_unreachable"
    assert Notice.objects.filter(kind=Notice.Kind.LATER).count() == 1
    monkeypatch.undo()
    arriving(account, incoming(account, sender="sanja@example.com"))
    swept()
    away.refresh_from_db()
    assert away.failed == ""


def test_colleagues_see_it_in_free_busy_but_not_the_words(writer, account, away):
    now = timezone.now()
    found = availability.away({account.address}, now, now + timedelta(hours=1))
    assert found == {account.address.lower(): away.ends_at}
    later_on = now + timedelta(days=10)
    assert availability.away({account.address}, later_on, later_on + timedelta(hours=1)) == {}


def test_a_talk_of_a_few_says_who_is_away(writer, account, away, django_user_model):
    colleague = django_user_model.objects.create_user(email="kolega@example.com", password="x")
    talk = Conversation.objects.create(kind=Conversation.Kind.DIRECT, title="")
    Member.objects.create(conversation=talk, user=account.owner)
    Member.objects.create(conversation=talk, user=colleague)
    assert absence.in_talk(account.owner, talk.pk) == []
    named = absence.in_talk(colleague, talk.pk)
    assert [each["ends_at"] for each in named] == [away.ends_at]
    stranger = django_user_model.objects.create_user(email="stranac@example.com", password="x")
    assert absence.in_talk(stranger, talk.pk) == []
