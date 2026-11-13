"""A meeting is a room anyone of the installation joins by its link (D15, S2), and anyone else as
its guest, made on its own or for an event, whose invitations carry the link as the event's
conference. LiveKit carries its sound and video and holds the room only while someone is in it."""

import secrets
import uuid

from django.conf import settings
from django.db import models, transaction

from apps.chat import conversations
from apps.chat.models import Conversation


class Meetings(models.Manager):
    def made(self, title: str, organizer=None, conversation: Conversation | None = None) -> Meeting:
        """A meeting in the conversation given, or with one of its own, which its people keep once
        the call ends."""
        with transaction.atomic():
            if conversation is None:
                conversation = Conversation.objects.create(
                    kind=Conversation.Kind.MEETING, title=title
                )
            made = self.create(title=title, organizer=organizer, conversation=conversation)
            if organizer is not None:
                conversations.added(conversation, [organizer])
        return made


class Meeting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=1000)
    conversation = models.ForeignKey(
        "chat.Conversation", on_delete=models.DB_CASCADE, related_name="meetings"
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="meetings"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = Meetings()

    def __str__(self) -> str:
        return self.title

    @property
    def link(self) -> str:
        return f"{settings.PUBLIC_URL}/meet/{self.id}"


class Ring(models.Model):
    """A colleague rung into a meeting made on its own: it rings in every PONISTRA of theirs that
    is open until they answer, or for as long as a call rings."""

    class Answer(models.TextChoices):
        JOINED = "joined"
        DECLINED = "declined"

    meeting = models.ForeignKey(Meeting, on_delete=models.DB_CASCADE, related_name="rings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="rings"
    )
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    answer = models.CharField(max_length=8, choices=Answer, blank=True)
    rung_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["user", "rung_at"]), models.Index(fields=["by", "rung_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "user"],
                condition=models.Q(answer=""),
                name="one_unanswered_ring",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.meeting}"


def _key() -> str:
    return secrets.token_urlsafe(32)


class Guest(models.Model):
    """Someone from outside the installation in a meeting (S2-2): asked by mail with a link of
    their own that lets them in, or come by the meeting's link to wait at its door until someone
    in it lets them in."""

    class State(models.TextChoices):
        WAITING = "waiting"
        ADMITTED = "admitted"
        REFUSED = "refused"

    meeting = models.ForeignKey(Meeting, on_delete=models.DB_CASCADE, related_name="guests")
    key = models.CharField(max_length=64, unique=True, default=_key)
    name = models.CharField(max_length=200, blank=True)
    address = models.CharField(max_length=254, blank=True)
    state = models.CharField(max_length=8, choices=State)
    # Whether a page of theirs waits at the door now: one closed leaves nobody to let in.
    at_door = models.BooleanField(default=False)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    came_at = models.DateTimeField(auto_now_add=True)
    # The last message of the meeting's conversation they have read, as a member's `read`.
    read = models.BigIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["meeting", "state"])]

    def __str__(self) -> str:
        return f"{self.name} → {self.meeting}"

    @property
    def link(self) -> str:
        return f"{self.meeting.link}?guest={self.key}"


class Recording(models.Model):
    """A meeting recorded by the recorder (S2-5): each participant's sound and picture, taken
    into a folder of the tree once it ends, with the minutes of what was said where speech to
    text and the installation's model are on (S2-6)."""

    class State(models.TextChoices):
        RECORDING = "recording"
        SAVING = "saving"
        DONE = "done"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.DB_CASCADE, related_name="recordings")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # What the recorder gives back as it tells the recording ended by itself.
    key = models.CharField(max_length=64, default=_key)
    state = models.CharField(max_length=9, choices=State, default=State.RECORDING)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True)
    # The identities of those who agreed, in the call, to their speech going to speech to text,
    # or refused it; a member's own consent to their speech counts without asking.
    consents = models.JSONField(default=dict)
    folder = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    minutes = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # Each track's file in the folder, with its place on the recording's time, for the meeting's
    # page to play them together.
    tracks = models.JSONField(default=list)
    error = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["meeting"],
                condition=models.Q(state="recording"),
                name="one_recording_at_a_time",
            )
        ]

    def __str__(self) -> str:
        return f"{self.meeting} {self.started_at:%Y-%m-%d %H:%M}"


class Relay(models.Model):
    """The installation's relay for meetings (S2-7), in one row: a TURN service outside that
    those joining go through where nothing reaches LiveKit inward. Cloudflare's is named by its
    key's id and its API token, from which each joining gets credentials of a day; another
    provider's by its addresses, user name and password. The token or password is sealed with
    the installation's secret, of which only the last four characters are shown again."""

    class Provider(models.TextChoices):
        NONE = ""
        CLOUDFLARE = "cloudflare"
        TURN = "turn"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    provider = models.CharField(max_length=10, choices=Provider, blank=True)
    # A TURN provider's addresses, turn: or turns: URLs, one per line.
    addresses = models.TextField(blank=True)
    # Cloudflare's key id or the TURN provider's user name.
    name = models.CharField(max_length=200, blank=True)
    secret = models.BinaryField(default=bytes)
    hint = models.CharField(max_length=4, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_meetings_relay")]

    def __str__(self) -> str:
        return self.provider or "none"
