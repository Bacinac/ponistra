import json
from email import policy
from email.message import EmailMessage
from itertools import count

import pytest

from apps.calendar import events, ical
from apps.calendar.models import Calendar, Event, Invitation
from apps.calendar.tests.test_sources import zone_blob
from apps.mail import sending, taking
from apps.mail.models import Account, Source
from apps.mail.tests.eas import appointment, everything

pytestmark = pytest.mark.django_db

ORGANIZER = "ana@example.org"
numbers = count(1)


@pytest.fixture
def inbox(owner):
    account = Account.objects.create(
        owner=owner,
        address="ivo@example.com",
        name="Ivo Bošković",
        username="ivo@example.com",
        secret=b"",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        default=True,
    )
    return Source.objects.create(
        account=account,
        name="INBOX",
        kind=Source.Kind.INBOX,
        folder=taking.folder(account, "inbox", ["INBOX"]),
    )


@pytest.fixture
def delivered(monkeypatch):
    sent = []

    async def fake(account, message):
        sent.append((account, message))
        return [], True

    monkeypatch.setattr(sending, "delivered", fake)
    return sent


def ics(
    method,
    uid="m-1",
    sequence=0,
    start="20261103T090000",
    end="20261103T100000",
    recurrence_id=None,
    partstat="NEEDS-ACTION",
    attendee="ivo@example.com",
    organizer=ORGANIZER,
    rrule=None,
):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Test//EN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        "DTSTAMP:20261027T100000Z",
        f"DTSTART;TZID=Europe/Zagreb:{start}",
        f"DTEND;TZID=Europe/Zagreb:{end}",
        "SUMMARY:Kolegij",
        f"SEQUENCE:{sequence}",
        f"ORGANIZER;CN=Ana:mailto:{organizer}",
        f"ATTENDEE;CN=Ivo;PARTSTAT={partstat};ROLE=REQ-PARTICIPANT:mailto:{attendee}",
    ]
    if rrule:
        lines.append(f"RRULE:{rrule}")
    if recurrence_id:
        lines.append(f"RECURRENCE-ID;TZID=Europe/Zagreb:{recurrence_id}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def mailed(source, method, sender=ORGANIZER, **given):
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = sender
    message["To"] = "ivo@example.com"
    message["Subject"] = f"{method}: Kolegij"
    message["Date"] = "Tue, 27 Oct 2026 10:00:00 +0100"
    message["Message-ID"] = f"<{next(numbers)}@example.org>"
    message.set_content("Dođi.")
    message.add_alternative(ics(method, **given), subtype="calendar", params={"method": method})
    return taking.took(source, message.as_bytes(), {"seen": False})


def answered(client, pk, response):
    return client.post(
        f"/api/calendar/events/{pk}/response?zone=Europe/Zagreb",
        json.dumps({"response": response, "language": "hr"}),
        content_type="application/json",
    )


def test_an_invitation_by_mail_awaits_the_users_answer_in_a_calendar_of_their_own(
    signed_in, inbox, delivered
):
    message = mailed(inbox, "REQUEST")
    held = Calendar.objects.get()
    assert (held.kind, held.name) == ("own", "ivo@example.com")
    event = Event.objects.get()
    assert (event.summary, event.response, event.organizer["email"]) == (
        "Kolegij",
        "needs-action",
        ORGANIZER,
    )
    assert Invitation.objects.get(message=message).method == "request"
    read = signed_in.get(f"/api/mail/messages/{message.pk}?zone=Europe/Zagreb").json()
    assert read["invitation"]["method"] == "request"
    assert read["invitation"]["event"]["start"] == "2026-11-03T09:00:00+01:00"
    assert read["invitation"]["held"] == {
        "id": event.pk,
        "calendar": held.pk,
        "response": "needs-action",
        "status": "confirmed",
        "day": "2026-11-03",
        "outdated": False,
    }
    answer = answered(signed_in, event.pk, "accepted")
    assert answer.status_code == 200 and answer.json()["response"] == "accepted"
    assert Event.objects.get(pk=event.pk).attendees[0]["status"] == "accepted"
    ((account, sent),) = delivered
    assert account.address == "ivo@example.com"
    assert (sent["To"], sent["Subject"]) == ("Ana <ana@example.org>", "Prihvaćeno: Kolegij")
    part = next(each for each in sent.walk() if each.get_content_type() == "text/calendar")
    assert part.get_param("method") == "REPLY"
    method, (reply,) = ical.imip(part.get_content())
    assert (method, reply.uid, reply.attendees[0]["status"]) == ("reply", "m-1", "accepted")
    copy = Invitation.objects.get(method="reply")
    assert copy.message.folder.role == "sent" and copy.attendee["email"] == "ivo@example.com"
    assert (
        signed_in.get(f"/api/mail/messages/{copy.message_id}").json()["invitation"]["held"][
            "response"
        ]
        == "accepted"
    )


def test_a_changed_invitation_moves_the_meeting_and_an_older_or_cancelled_one_is_told(
    signed_in, inbox
):
    mailed(inbox, "REQUEST")
    Event.objects.update(response="accepted")
    mailed(inbox, "REQUEST")
    assert Event.objects.get().response == "accepted"
    mailed(
        inbox,
        "REQUEST",
        sequence=1,
        start="20261104T090000",
        end="20261104T100000",
        partstat="ACCEPTED",
    )
    event = Event.objects.get()
    assert (event.starts.isoformat(), event.response, event.sequence) == (
        "2026-11-04T08:00:00+00:00",
        "accepted",
        1,
    )
    mailed(inbox, "REQUEST", sequence=0, start="20261105T090000", end="20261105T100000")
    assert Event.objects.get().starts.isoformat() == "2026-11-04T08:00:00+00:00"
    message = mailed(inbox, "CANCEL", sequence=2)
    assert Event.objects.get().status == "cancelled"
    read = signed_in.get(f"/api/mail/messages/{message.pk}").json()["invitation"]
    assert (read["method"], read["held"]["status"]) == ("cancel", "cancelled")


def test_one_occurrence_cancelled_leaves_the_series_whole(signed_in, inbox):
    mailed(inbox, "REQUEST", rrule="FREQ=WEEKLY;COUNT=4")
    mailed(inbox, "CANCEL", recurrence_id="20261110T090000")
    master = Event.objects.get(master__isnull=True)
    (override,) = master.overrides.all()
    assert (override.status, override.starts.isoformat()) == (
        "cancelled",
        "2026-11-10T08:00:00+00:00",
    )
    listed = signed_in.get(
        "/api/calendar/events?from=2026-11-03&to=2026-11-17&zone=Europe/Zagreb"
    ).json()
    assert [each["status"] for each in listed["events"]] == ["confirmed", "cancelled", "confirmed"]


def test_an_attendees_answer_reaches_the_meeting_the_user_called(signed_in, inbox, own):
    called = ical.Found(uid="ours-1", summary="Naš sastanak")
    called.organizer = {"email": "ivo@example.com", "name": "Ivo"}
    called.attendees = [
        {"email": ORGANIZER, "name": "Ana", "role": "required", "status": "needs-action"}
    ]
    called.response = "organizer"
    event = events.made(own, called)
    message = mailed(
        inbox,
        "REPLY",
        uid="ours-1",
        partstat="ACCEPTED",
        attendee=ORGANIZER,
        organizer="ivo@example.com",
    )
    assert Event.objects.get(pk=event.pk).attendees[0]["status"] == "accepted"
    read = signed_in.get(f"/api/mail/messages/{message.pk}").json()["invitation"]
    assert (read["method"], read["attendee"]["email"], read["attendee"]["status"]) == (
        "reply",
        ORGANIZER,
        "accepted",
    )
    refused = answered(signed_in, event.pk, "accepted")
    assert (refused.status_code, refused.json()["error"]) == (400, "not_invited")


def test_a_meeting_of_the_organisations_calendar_is_answered_through_its_server(
    signed_in, account, box
):
    server_id = box.put(
        "4",
        appointment(
            UID="trav-9",
            Subject="Kolegij",
            TimeZone=zone_blob(),
            StartTime="20261102T080000Z",
            EndTime="20261102T090000Z",
            AllDayEvent="0",
            BusyStatus="2",
            MeetingStatus="3",
            ResponseType="5",
            OrganizerEmail=ORGANIZER,
            OrganizerName="Ana",
        ),
    )
    everything(account)
    event = Event.objects.get()
    assert (event.response, event.calendar.read_only) == ("needs-action", True)
    answer = answered(signed_in, event.pk, "tentative")
    assert answer.status_code == 200 and answer.json()["response"] == "tentative"
    assert box.responses == [{"UserResponse": "2", "CollectionId": "4", "RequestId": server_id}]
    assert Event.objects.get().response == "tentative"


def test_what_a_message_carries_of_a_meeting_is_read_as_mail_gives_it():
    with pytest.raises(ical.Malformed):
        ical.imip("[B@3d210bb6-----atllgmuqdh2383s23bd2a_0_852894--\r\n")
    method, found = ical.imip(ics("CANCEL", recurrence_id="20261110T090000"))
    assert method == "cancel" and found[0].recurrence_id is not None
    with pytest.raises(ical.Malformed):
        ical.parsed(ics("CANCEL", recurrence_id="20261110T090000"))
    assert ical.imip(ics("PUBLISH"))[0] == ""


def kept_event(client, pk=None, scope=None, **data):
    query = "zone=Europe/Zagreb" + (f"&scope={scope}" if scope else "")
    body = json.dumps({"language": "hr", **data})
    if pk is None:
        return client.post(f"/api/calendar/events?{query}", body, content_type="application/json")
    return client.patch(f"/api/calendar/events/{pk}?{query}", body, content_type="application/json")


def carried(message):
    for part in message.walk():
        if part.get_content_type() == "text/calendar":
            return part.get_content(), part.get_param("method")
    raise AssertionError("no calendar part")


def test_the_user_calls_a_meeting_and_the_attendees_are_told_of_what_matters(
    signed_in, owner, inbox, own, delivered
):
    made = kept_event(
        signed_in,
        calendar=own.pk,
        summary="Kolegij",
        start="2026-11-03T09:00",
        end="2026-11-03T10:00",
        location="Ured",
        attendees=[{"email": ORGANIZER, "name": "Ana"}, {"email": "Ivo@Example.com"}],
    )
    assert made.status_code == 201, made.content
    event = Event.objects.get(pk=made.json()["id"])
    assert (event.response, event.organizer["email"]) == ("organizer", "ivo@example.com")
    assert [each["email"] for each in event.attendees] == [ORGANIZER]
    assert len(delivered) == 1
    message = delivered[0][1]
    text, method = carried(message)
    assert (message["Subject"], message["To"]) == ("Poziv: Kolegij", "Ana <ana@example.org>")
    assert method == "REQUEST"
    assert "METHOD:REQUEST" in text and "ORGANIZER;CN=" in text
    assert "03.11.2026. 09:00 – 10:00" in message.get_body(("plain",)).get_content()
    assert Invitation.objects.filter(method="request", uid=event.uid).exists()

    delivered.clear()
    assert kept_event(signed_in, event.pk, reminders=[10]).status_code == 200
    assert delivered == []

    kept_event(signed_in, event.pk, start="2026-11-03T10:00", end="2026-11-03T11:00")
    assert [each[1]["Subject"] for each in delivered] == ["Ažurirano: Kolegij"]
    assert "SEQUENCE:2" in carried(delivered[0][1])[0]

    delivered.clear()
    link = "https://ponistra.example/meet/0b7f6b3e-0000-4000-8000-000000000001"
    kept_event(signed_in, event.pk, conference=link)
    assert [each[1]["Subject"] for each in delivered] == ["Ažurirano: Kolegij"]
    assert link in delivered[0][1].get_body(("plain",)).get_content()
    assert "CONFERENCE;FEATURE=AUDIO,VIDEO;VALUE=URI:https:" in carried(delivered[0][1])[0]

    delivered.clear()
    kept_event(
        signed_in,
        event.pk,
        attendees=[
            {"email": ORGANIZER, "name": "Ana"},
            {"email": "iva@example.org", "name": "Iva"},
        ],
    )
    assert [(each[1]["Subject"], each[1]["To"]) for each in delivered] == [
        ("Poziv: Kolegij", "Iva <iva@example.org>")
    ]

    delivered.clear()
    kept_event(signed_in, event.pk, attendees=[{"email": "iva@example.org", "name": "Iva"}])
    assert [(each[1]["Subject"], each[1]["To"]) for each in delivered] == [
        ("Otkazano: Kolegij", "Ana <ana@example.org>")
    ]
    text, method = carried(delivered[0][1])
    assert method == "CANCEL" and "STATUS:CANCELLED" in text and "iva@example.org" not in text

    delivered.clear()
    gone = signed_in.delete(f"/api/calendar/events/{event.pk}?zone=Europe/Zagreb&language=hr")
    assert gone.status_code == 204
    assert [(each[1]["Subject"], each[1]["To"]) for each in delivered] == [
        ("Otkazano: Kolegij", "Iva <iva@example.org>")
    ]


def test_a_meeting_needs_an_account_to_send_from(signed_in, own, delivered):
    refused = kept_event(
        signed_in,
        calendar=own.pk,
        summary="Kolegij",
        start="2026-11-03T09:00",
        end="2026-11-03T10:00",
        attendees=[{"email": ORGANIZER}],
    )
    assert (refused.status_code, refused.json()["error"]) == (400, "no_account")
    assert Event.objects.count() == 0 and delivered == []
    refused = kept_event(
        signed_in,
        calendar=own.pk,
        summary="Kolegij",
        start="2026-11-03T09:00",
        end="2026-11-03T10:00",
        attendees=[{"email": "nobody"}],
    )
    assert (refused.status_code, refused.json()["error"]) == (400, "invalid_attendee")


def test_one_occurrence_of_the_series_called_is_changed_and_another_taken_back(
    signed_in, inbox, own, delivered
):
    made = kept_event(
        signed_in,
        calendar=own.pk,
        summary="Kolegij",
        start="2026-11-03T09:00",
        end="2026-11-03T10:00",
        rrule="FREQ=WEEKLY",
        attendees=[{"email": ORGANIZER, "name": "Ana"}],
    )
    event = made.json()["id"]
    delivered.clear()
    moved = kept_event(
        signed_in,
        event,
        scope="this",
        recurrence_id="2026-11-10T09:00",
        start="2026-11-10T11:00",
        end="2026-11-10T12:00",
    )
    assert moved.status_code == 200, moved.content
    text, method = carried(delivered[0][1])
    assert (delivered[0][1]["Subject"], method) == ("Ažurirano: Kolegij", "REQUEST")
    assert "RECURRENCE-ID;TZID=Europe/Zagreb:20261110T090000" in text
    assert text.count("BEGIN:VEVENT") == 1

    delivered.clear()
    gone = signed_in.delete(
        f"/api/calendar/events/{event}?zone=Europe/Zagreb&scope=this"
        "&recurrence_id=2026-11-17T09:00&language=hr"
    )
    assert gone.status_code == 204
    text, method = carried(delivered[0][1])
    assert (method, "RECURRENCE-ID;TZID=Europe/Zagreb:20261117T090000" in text) == ("CANCEL", True)
    assert "STATUS:CANCELLED" in text
