from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.calendar import availability, events, taking
from apps.calendar.ical import Found

from .company import Seeded

ZONE = "Europe/Zagreb"

# Day from the month's first Monday, start (or the hr account's and the en one's), minutes,
# summary, the rooms booked by the hr account and by the en one (each its own, as both accounts
# share the company's rooms), the colleagues asked with their answers, and a rule.
WORK = [
    (
        0,
        time(9),
        60,
        ("Tjedni sastanak tima", "Weekly team meeting"),
        ("Sava", "Drava"),
        (
            ("marija", "accepted"),
            ("ivan", "accepted"),
            ("ana", "accepted"),
            ("tomislav", "tentative"),
        ),
        "FREQ=WEEKLY",
    ),
    (
        1,
        time(11),
        90,
        ("Pregled ponude za namještaj", "Furniture quote review"),
        ("Kupa", "Drava"),
        (("ivan", "accepted"), ("marta", "needs-action")),
        "",
    ),
    (
        3,
        time(14),
        60,
        ("Sastanak s dobavljačem", "Supplier meeting"),
        ("Drava", "Sava"),
        (("ivan", "accepted"),),
        "",
    ),
    (
        8,
        time(10),
        120,
        ("Radionica: novi postupci nabave", "Workshop: new purchasing steps"),
        ("Sava", "Drava"),
        (("ivan", "accepted"), ("marta", "accepted"), ("maja", "declined")),
        "",
    ),
    (
        10,
        time(13),
        30,
        ("Razgovor s kandidatom", "Interview with a candidate"),
        ("Kupa", "Drava"),
        (("marija", "accepted"),),
        "",
    ),
    (
        11,
        (time(8), time(13)),
        240,
        ("Obilazak gradilišta Meridian", "Meridian site visit"),
        ("Van ZG 1001 LS", "Van ZG 1001 LS"),
        (("tomislav", "accepted"), ("dino", "accepted")),
        "",
    ),
    (
        15,
        time(9, 30),
        60,
        ("Zaključak mjeseca", "Month-end close"),
        ("Drava", "Sava"),
        (("marta", "accepted"), ("marija", "accepted")),
        "",
    ),
]

PERSONAL = [
    (2, time(18), 60, ("Trening", "Training")),
    (12, time(17, 30), 45, ("Zubar", "Dentist")),
]


def seed(seeded: Seeded) -> None:
    say, user, company = seeded.say, seeded.user, seeded.company
    which = 0 if seeded.language == "hr" else 1
    zone = ZoneInfo(ZONE)
    today = timezone.localdate()
    first = today.replace(day=1)
    first += timedelta(days=-first.weekday() % 7)
    work = taking.own(user.pk, say("Posao", "Work"))
    personal = taking.own(user.pk, say("Osobno", "Personal"))
    organizer = {"email": user.email, "name": user.get_full_name()}
    for day, at, minutes, summary, rooms, asked, rule in WORK:
        at = at[which] if isinstance(at, tuple) else at
        starts = datetime.combine(first + timedelta(days=day), at, zone)
        room = company.rooms[rooms[which]]
        attendees = [{**organizer, "status": "accepted", "role": "chair"}] + [
            {
                "email": company.address(key),
                "name": company.name(key),
                "status": status,
                "role": "required",
            }
            for key, status in asked
        ]
        event = events.made(
            work,
            Found(
                summary=say(*summary),
                location=room.name,
                starts=starts,
                ends=starts + timedelta(minutes=minutes),
                zone=ZONE,
                rrule=rule,
                organizer=organizer,
                attendees=attendees,
            ),
        )
        availability.booked(event, [room])
    for day, at, minutes, summary in PERSONAL:
        starts = datetime.combine(first + timedelta(days=day), at, zone)
        events.made(
            personal,
            Found(
                summary=say(*summary),
                starts=starts,
                ends=starts + timedelta(minutes=minutes),
                zone=ZONE,
            ),
        )
    holiday = first + timedelta(days=4)
    events.made(
        work,
        Found(
            summary=say("Godišnji odmor – Ana", "Annual leave – Ana"),
            all_day=True,
            starts=datetime.combine(holiday, time(), UTC),
            ends=datetime.combine(holiday + timedelta(days=3), time(), UTC),
            zone=ZONE,
            busy=False,
        ),
    )
