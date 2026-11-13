from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage

import pytest

from apps.calendar import invitations, notes
from apps.calendar.models import Calendar, Event, Feed, Gone, Invitation
from apps.calendar.tests.test_invitations import answered
from apps.calendar.tests.test_sources import zone_blob
from apps.mail.activesync.wbxml import element as e
from apps.mail.models import Message
from apps.mail.tests.eas import USER, appointment, everything, item

pytestmark = pytest.mark.django_db

UNID = "B6B6805EACBE40A5C1258E9D002DC789"
UID = notes.GLOBAL_ID + UNID
ENTRY = {
    "unid": UNID,
    "start": "20261029T100000,00+01",
    "end": "20261029T110000,00+01",
    "texts": ["Invitation: BankConnect", "Odra", "Eva Kovac"],
}


def notice(box, unid=UNID, icon="133"):
    """The notice Traveler delivers of an invitation: its calendar part the text of a byte
    array."""
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = "Eva Kovac <eva@example.org>"
    message["To"] = USER
    message["Subject"] = "Invitation: BankConnect (29 Oct 10:00 CET in Odra)"
    message["Date"] = "Tue, 27 Oct 2026 09:20:47 +0100"
    message["X-IBM-UNID"] = unid
    message["X-IBM-FORM"] = "Notice"
    message["X-IBM-NOTICEICON"] = icon
    message.set_content("")
    message.add_alternative("[B@fb90beff", subtype="calendar", params={"method": "REQUEST"})
    return box.put("1", item("Invitation", message))


def standing_in():
    return Event.objects.get(uid=UID, master__isnull=True)


def test_an_invitation_traveler_only_tells_of_awaits_the_answer_as_the_mail_file_has_it(
    signed_in, account, box
):
    box.domino = [ENTRY]
    server_id = notice(box)
    everything(account)
    event = standing_in()
    assert notes.standing(event) and event.calendar.kind == Calendar.Kind.ORGANISATION
    assert (event.summary, event.location, event.response) == (
        "Invitation: BankConnect",
        "Odra",
        "needs-action",
    )
    assert (event.starts, event.ends) == (
        datetime(2026, 10, 29, 9, tzinfo=UTC),
        datetime(2026, 10, 29, 10, tzinfo=UTC),
    )
    assert event.organizer == {"name": "Eva Kovac", "email": "eva@example.org"}
    shown = invitations.described(Message.objects.get(), "Europe/Zagreb")
    assert shown["event"]["location"] == "Odra" and shown["held"]["id"] == event.pk

    answer = answered(signed_in, event.pk, "accepted")
    assert answer.status_code == 200 and answer.json()["response"] == "accepted"
    assert box.responses == [{"UserResponse": "1", "CollectionId": "1", "RequestId": server_id}]
    assert answered(signed_in, event.pk, "accepted").status_code == 200
    assert len(box.responses) == 1

    box.put(
        "4",
        appointment(
            UID=UID,
            Subject="BankConnect",
            Location="Odra",
            TimeZone=zone_blob(),
            StartTime="20261029T090000Z",
            EndTime="20261029T100000Z",
            AllDayEvent="0",
            BusyStatus="2",
            MeetingStatus="3",
            ResponseType="3",
            OrganizerEmail="eva@example.org",
            OrganizerName="Eva Kovac",
            Attendees=[
                e(
                    "Calendar:Attendee",
                    e("Calendar:Email", USER),
                    e("Calendar:Name", "Ana"),
                    e("Calendar:AttendeeStatus", "5"),
                    e("Calendar:AttendeeType", "1"),
                )
            ],
        ),
    )
    everything(account)
    meeting = Event.objects.get()
    assert meeting.pk == event.pk and not notes.standing(meeting)
    assert (meeting.summary, meeting.response, meeting.busy) == ("BankConnect", "accepted", True)
    assert [each["status"] for each in meeting.attendees] == ["accepted"]
    assert Gone.objects.filter(href=event.href).exists()


def test_an_invitation_the_mail_file_no_longer_holds_leaves_the_calendar(account, box):
    box.domino = [ENTRY]
    notice(box)
    everything(account)
    href = standing_in().href
    box.domino = []
    everything(account)
    assert not Event.objects.exists() and Gone.objects.filter(href=href).exists()


def test_a_notice_of_another_kind_or_a_server_that_is_not_domino_stands_in_for_nothing(
    account, box
):
    notice(box, unid="C6560CB9F4573673C1258E84002E6D12", icon="33")
    notice(box)
    everything(account)
    assert Invitation.objects.get().uid == UID
    assert invitations.described(Invitation.objects.get().message, "Europe/Zagreb") is None
    assert not Event.objects.exists() and Feed.objects.get().error == ""


def test_a_mail_file_domino_does_not_open_is_told_on_the_calendar_and_the_mail_still_comes(
    account, box
):
    box.domino, box.sealed = [ENTRY], True
    notice(box)
    everything(account)
    assert Feed.objects.get().error == "notes_unreachable"
    assert Message.objects.count() == 1 and not Event.objects.exists()
    box.sealed = False
    everything(account)
    assert Feed.objects.get().error == "" and standing_in().location == "Odra"


@pytest.mark.parametrize(
    ("raw", "moment", "all_day"),
    [
        ("20261029T100000,00+01", datetime(2026, 10, 29, 9, tzinfo=UTC), False),
        ("20260720T143000,00+0530", datetime(2026, 7, 20, 9, tzinfo=UTC), False),
        ("20261029T100000,00Z", datetime(2026, 10, 29, 10, tzinfo=UTC), False),
        ("20261029", datetime(2026, 10, 29, tzinfo=UTC), True),
    ],
)
def test_a_domino_time_is_read_with_its_offset(raw, moment, all_day):
    assert notes._moment(raw) == (moment, all_day)
