from datetime import time

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVectorField
from django.db import connection, models
from django.db.models import BigIntegerField, Func, Q, Value

from apps.search.text import EventWords, Folded

# Each change to a calendar takes the next number, by which a phone asks what changed since.
REVISION = "calendar_revision"
LOCK = 0x5C21B10E


def revised() -> Func:
    return Func(Value(REVISION), function="nextval", output_field=BigIntegerField())


def ordered(*owner_ids: int) -> None:
    """Holds the owners' calendars until the transaction ends, so that a phone that read up to a
    number cannot have missed a smaller one committed after."""
    with connection.cursor() as cursor:
        for owner_id in sorted(set(owner_ids)):
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [LOCK, owner_id])


class Calendar(models.Model):
    """A calendar of the user's (D15, S4). One of their own holds what they write and what a
    personal account gave once; an organisation's is its ActiveSync server's calendar folder,
    read and refreshed from it, never changed here."""

    class Kind(models.TextChoices):
        OWN = "own"
        ORGANISATION = "organisation"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="calendars"
    )
    kind = models.CharField(max_length=12, choices=Kind, default=Kind.OWN)
    name = models.CharField(max_length=200)
    # Its place in the interface's palette of calendar colours, wrapping past its end.
    color = models.PositiveSmallIntegerField(default=0)
    account = models.ForeignKey(
        "mail.Account", null=True, on_delete=models.DB_CASCADE, related_name="calendars"
    )
    # The organisation calendar's folder at its server.
    server_id = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "server_id"],
                condition=Q(account__isnull=False),
                name="calendar_calendar_folder_once",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def read_only(self) -> bool:
        return self.kind == self.Kind.ORGANISATION


class Event(models.Model):
    """An event of a calendar (RFC 5545): a single one, the master of a series with its rule, or
    one occurrence of a series changed on its own (`master` and `recurrence_id`, the start the
    occurrence had). Times are instants; `zone` is the wall clock the series repeats by. An
    all-day event's `starts` and `ends` are its dates at midnight UTC, the end exclusive."""

    class Status(models.TextChoices):
        CONFIRMED = "confirmed"
        TENTATIVE = "tentative"
        CANCELLED = "cancelled"

    class DayOff(models.TextChoices):
        HELD = ""
        SKIPPED = "skip"
        BEFORE = "before"
        AFTER = "after"

    calendar = models.ForeignKey(Calendar, on_delete=models.DB_CASCADE, related_name="events")
    uid = models.CharField(max_length=255)
    # The name of the event's iCalendar in the calendar a phone reads, which a phone may choose.
    href = models.CharField(max_length=255)
    master = models.ForeignKey(
        "self", null=True, on_delete=models.DB_CASCADE, related_name="overrides"
    )
    recurrence_id = models.DateTimeField(null=True)
    summary = models.CharField(max_length=1000, blank=True)
    location = models.CharField(max_length=1000, blank=True)
    # Where the meeting is joined online: a PONISTRA meeting's link or another service's.
    conference = models.CharField(max_length=2000, blank=True)
    description = models.TextField(blank=True)
    all_day = models.BooleanField(default=False)
    starts = models.DateTimeField()
    ends = models.DateTimeField()
    zone = models.CharField(max_length=64, blank=True)
    # The RRULE's value, and the dates added to and taken from the series, as ISO 8601.
    rrule = models.CharField(max_length=500, blank=True)
    rdates = models.JSONField(default=list)
    exdates = models.JSONField(default=list)
    # What the series does with an occurrence its rule puts on a weekend or a holiday: it is held
    # anyway, skipped, or moved to the nearest working day before or after.
    day_off = models.CharField(max_length=6, choices=DayOff, blank=True)
    status = models.CharField(max_length=9, choices=Status, default=Status.CONFIRMED)
    # Whether the time counts as taken when someone asks when the user is free.
    busy = models.BooleanField(default=True)
    private = models.BooleanField(default=False)
    organizer = models.JSONField(default=dict)
    # Each {email, name, status, role, optional}.
    attendees = models.JSONField(default=list)
    # The user's own answer to an invitation: accepted, tentative, declined or needs-action.
    response = models.CharField(max_length=12, blank=True)
    # Minutes before the start at which to remind.
    reminders = models.JSONField(default=list)
    sequence = models.PositiveIntegerField(default=0)
    # The iCalendar lines a phone or a source gave that PONISTRA does not show, given back.
    extra = models.JSONField(default=list)
    revision = models.BigIntegerField(db_default=revised())
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)
    words = models.GeneratedField(
        expression=EventWords("summary", "location", "organizer", "attendees", "description"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["calendar", "href"],
                condition=models.Q(master__isnull=True),
                name="calendar_event_href_once",
            ),
            models.UniqueConstraint(
                fields=["calendar", "uid", "recurrence_id"],
                nulls_distinct=False,
                name="calendar_event_uid_once",
            ),
        ]
        indexes = [
            GinIndex(fields=["words"], name="calendar_event_words"),
            GinIndex(
                OpClass(Folded("summary"), name="gin_trgm_ops"), name="calendar_summary_trigrams"
            ),
            models.Index(fields=["calendar", "starts"]),
            models.Index(fields=["calendar", "revision"]),
        ]

    def __str__(self) -> str:
        return self.summary or self.uid


class Taken(models.Model):
    """An event as a personal account gave it (D15, S4), kept as it came. An item is taken once:
    its row stays when the event is deleted, so it does not come again."""

    class Kind(models.TextChoices):
        MICROSOFT = "microsoft"
        GOOGLE = "google"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="calendar_taken"
    )
    event = models.ForeignKey(Event, null=True, on_delete=models.DB_SET_NULL, related_name="taken")
    account = models.ForeignKey(
        "mail.Account", null=True, on_delete=models.DB_SET_NULL, related_name="calendar_taken"
    )
    kind = models.CharField(max_length=10, choices=Kind)
    source = models.CharField(max_length=320)
    item = models.CharField(max_length=500)
    data = models.JSONField(default=dict)
    # The feed the item came through, where it came through one; dropped with the feed's
    # calendar, so following the calendar again takes its events again.
    feed = models.ForeignKey("Feed", null=True, on_delete=models.DB_SET_NULL, related_name="taken")
    taken_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "kind", "source", "item"], name="calendar_taken_once"
            ),
        ]

    def __str__(self) -> str:
        return self.item


class Feed(models.Model):
    """A calendar of a connected account at its provider, and how far its events are taken: a
    CalDAV sync token, a Graph delta link, an ActiveSync folder's sync key. A personal account's
    feed fills one of the user's own calendars; an organisation's is that calendar itself."""

    account = models.ForeignKey(
        "mail.Account", on_delete=models.DB_CASCADE, related_name="calendar_feeds"
    )
    server_id = models.CharField(max_length=500, blank=True)
    name = models.CharField(max_length=1000, blank=True)
    calendar = models.ForeignKey(
        Calendar, null=True, on_delete=models.DB_SET_NULL, related_name="feeds"
    )
    key = models.TextField(blank=True)
    error = models.CharField(max_length=40, blank=True)
    # Off when the user dropped the calendar here: it stays at the provider, and nothing of it
    # is taken until they follow it again.
    followed = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "server_id"], name="calendar_feed_once"),
        ]

    def __str__(self) -> str:
        return self.name


class Gone(models.Model):
    """An event deleted from a calendar, by which a phone learns it went."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="calendar_gone"
    )
    calendar = models.ForeignKey(Calendar, on_delete=models.DB_CASCADE, related_name="gone")
    href = models.CharField(max_length=255)
    revision = models.BigIntegerField(db_default=revised())

    class Meta:
        indexes = [models.Index(fields=["calendar", "revision"])]

    def __str__(self) -> str:
        return self.href


class Invitation(models.Model):
    """What a message says of a meeting (D15, S4-3): the invitation to it, a change or the
    cancellation of it, or an attendee's answer, kept as the message gave it, by which the
    message is read and answered."""

    class Method(models.TextChoices):
        REQUEST = "request"
        CANCEL = "cancel"
        REPLY = "reply"
        COUNTER = "counter"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="invitations"
    )
    message = models.OneToOneField(
        "mail.Message", on_delete=models.DB_CASCADE, related_name="invitation"
    )
    method = models.CharField(max_length=7, choices=Method)
    uid = models.CharField(max_length=255)
    recurrence_id = models.DateTimeField(null=True)
    sequence = models.PositiveIntegerField(default=0)
    # The event as the message gives it, in the terms the interface reads.
    event = models.JSONField(default=dict)
    # Of an answer or a counter-proposal, the attendee giving it.
    attendee = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "uid"], name="calendar_invitation_uid")]

    def __str__(self) -> str:
        return f"{self.method} {self.uid}"


class Workdays(models.Model):
    """Where and when the installation works, in one row: its country, and the region within it
    where holidays differ by region, whose weekend and public holidays are its days off, and the
    hours of its working days on the installation's clock."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    # ISO 3166-1 alpha-2, and the region as python-holidays names it.
    country = models.CharField(max_length=2, default="HR")
    subdivision = models.CharField(max_length=10, blank=True)
    opens = models.TimeField(default=time(8))
    closes = models.TimeField(default=time(16))
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="one_workdays"),
            models.CheckConstraint(
                condition=Q(closes__gt=models.F("opens")), name="workdays_hours"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.country} {self.subdivision}".strip()


class Closure(models.Model):
    """Days the organisation does not work beyond its country's holidays, from `first` to `last`
    inclusive: a collective leave, a day bridging a holiday and a weekend."""

    first = models.DateField()
    last = models.DateField()
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first", "last", "pk"]
        constraints = [
            models.CheckConstraint(condition=Q(last__gte=models.F("first")), name="closure_ends")
        ]

    def __str__(self) -> str:
        return self.name


class Resource(models.Model):
    """A room, a projector or a car of the organisation: booked by being put on an event, never
    twice for one moment."""

    class Kind(models.TextChoices):
        ROOM = "room"
        EQUIPMENT = "equipment"
        VEHICLE = "vehicle"
        OTHER = "other"

    name = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=12, choices=Kind, default=Kind.ROOM)
    capacity = models.PositiveIntegerField(null=True)
    place = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self) -> str:
        return self.name


class Booking(models.Model):
    event = models.ForeignKey(Event, on_delete=models.DB_CASCADE, related_name="bookings")
    resource = models.ForeignKey(Resource, on_delete=models.DB_CASCADE, related_name="bookings")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "resource"], name="calendar_booking_once")
        ]

    def __str__(self) -> str:
        return f"{self.resource_id} on {self.event_id}"
