"""A meeting held last week: its call in the calendar, what was said in it and its recording,
whose minutes are the document the projects folder keeps."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.calendar import events
from apps.calendar.ical import Found
from apps.calendar.models import Calendar
from apps.chat import conversations
from apps.chat.models import Conversation, Message
from apps.meetings.models import Meeting, Recording

from .company import Seeded

PRESENT = ("marija", "ana", "ivan")
ZONE = "Europe/Zagreb"

SAID = (
    ("marija", 3, ("Dijelim ponudu na ekranu.", "I am sharing the proposal on the screen.")),
    (
        "ana",
        12,
        ("Slike sale su u prezentaciji, slajd 2.", "The pictures of the room are on slide 2."),
    ),
    ("ivan", 41, ("Uzorke naručujem danas.", "I am ordering the samples today.")),
)


def seed(seeded: Seeded) -> None:
    say, user, company = seeded.say, seeded.user, seeded.company
    title = say("Priprema ponude za Meridian", "Meridian proposal kick-off")
    meeting = Meeting.objects.made(title, user)
    people = [company.people[key] for key in PRESENT]
    conversations.added(meeting.conversation, people)
    day = timezone.localdate() - timedelta(days=7 + timezone.localdate().weekday() - 1)
    starts = datetime.combine(day, time(10), ZoneInfo(ZONE))
    ends = starts + timedelta(minutes=50)
    work = Calendar.objects.filter(owner=user).order_by("pk").first()
    events.made(
        work,
        Found(
            summary=title,
            starts=starts,
            ends=ends,
            zone=ZONE,
            conference=meeting.link,
            organizer={"email": user.email, "name": user.get_full_name()},
            attendees=[
                {
                    "email": each.email,
                    "name": each.get_full_name(),
                    "status": "accepted",
                    "role": "required",
                }
                for each in people
            ],
        ),
    )
    for key, minute, words in SAID:
        message = Message.objects.create(
            conversation=meeting.conversation,
            author=company.people[key],
            body=say(*words),
            meeting=meeting,
        )
        Message.objects.filter(pk=message.pk).update(created_at=starts + timedelta(minutes=minute))
    Conversation.objects.filter(pk=meeting.conversation_id).update(
        created_at=starts, changed_at=ends
    )
    Meeting.objects.filter(pk=meeting.pk).update(created_at=starts)
    recording = Recording.objects.create(
        meeting=meeting,
        started_by=user,
        state=Recording.State.DONE,
        ended_at=ends,
        folder=seeded.made["projects"],
        minutes=seeded.made["minutes"],
    )
    Recording.objects.filter(pk=recording.pk).update(started_at=starts + timedelta(minutes=1))
