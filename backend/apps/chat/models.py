"""Conversations among the people of the installation (D15, S2-3): a meeting's, which stays once
the call has ended, one between two people and a group started from people, then channels. A
message is plain text, as a comment is, and may carry files."""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models.functions import Lower

from apps.search.text import Words


class Conversation(models.Model):
    class Kind(models.TextChoices):
        MEETING = "meeting"
        DIRECT = "direct"
        GROUP = "group"
        CHANNEL = "channel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=8, choices=Kind)
    title = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    # When a message was last written, edited or taken back: a tab reads the messages again
    # when it moves.
    changed_at = models.DateTimeField(auto_now_add=True)
    # Of a channel: a private one exists only for its members.
    private = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("title"),
                condition=models.Q(kind="channel", private=False),
                name="one_open_channel_a_name",
            )
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def open(self) -> bool:
        return self.kind == self.Kind.CHANNEL and not self.private


class Member(models.Model):
    """Someone in a conversation, with the last message they have read."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.DB_CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="memberships"
    )
    read = models.BigIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="one_member_a_person")
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.conversation}"


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.DB_CASCADE, related_name="messages"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # Or a guest in a call of the conversation's meeting (S2-2), who writes under their own name.
    guest = models.ForeignKey(
        "meetings.Guest", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # The message of a channel this one answers, in its thread.
    parent = models.ForeignKey(
        "self", null=True, on_delete=models.DB_CASCADE, related_name="replies"
    )
    body = models.TextField()
    words = models.GeneratedField(
        expression=Words("body"), output_field=SearchVectorField(), db_persist=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True)
    # Named everyone in the channel at once, whose members are also its mentions.
    everyone = models.BooleanField(default=False)
    # The meeting a channel's message opens, which rings nobody.
    meeting = models.ForeignKey(
        "meetings.Meeting", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [
            models.Index(fields=["conversation", "id"]),
            models.Index(fields=["parent", "id"]),
            GinIndex(fields=["words"], name="message_words"),
        ]

    def __str__(self) -> str:
        return self.body[:40]


class Attachment(models.Model):
    """A file a message carries: bytes of its own, which go with the conversation, or a file of
    the tree, of which there stays one original; its name stays once that is gone."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="attachments")
    position = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=255)
    blob = models.ForeignKey(
        "blobs.Blob", null=True, on_delete=models.DO_NOTHING, related_name="chat_attachments"
    )
    node = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["message", "position"], name="one_attachment_a_place"),
            models.CheckConstraint(
                condition=models.Q(blob__isnull=True) | models.Q(node__isnull=True),
                name="attachment_of_one_source",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Given(models.Model):
    """A right to read a file of the tree that the conversation gave its member, which goes when
    neither the file nor the member is left in it."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.DB_CASCADE, related_name="given"
    )
    grant = models.ForeignKey("access.Grant", on_delete=models.DB_CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "grant"], name="given_once")]

    def __str__(self) -> str:
        return f"{self.grant_id} by {self.conversation_id}"


class Mention(models.Model):
    """Someone a message names with @. In a channel only these hear of it."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="mentions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mentions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "user"], name="one_mention_a_person")
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.message_id}"


class Follower(models.Model):
    """Someone a thread concerns, with the last reply they have read."""

    root = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="followers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="followed_threads"
    )
    read = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["root", "user"], name="one_follower_a_person")
        ]

    def __str__(self) -> str:
        return f"{self.user} on {self.root_id}"


class Reaction(models.Model):
    """An emoji a member, or a guest in a call of the conversation's meeting, put on a message."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="reactions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    guest = models.ForeignKey(
        "meetings.Guest", null=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "emoji"],
                condition=models.Q(user__isnull=False),
                name="chat_reaction_once",
            ),
            models.UniqueConstraint(
                fields=["message", "guest", "emoji"],
                condition=models.Q(guest__isnull=False),
                name="chat_guest_reaction_once",
            ),
            models.CheckConstraint(
                condition=models.Q(user__isnull=False, guest__isnull=True)
                | models.Q(user__isnull=True, guest__isnull=False),
                name="chat_reaction_by_one",
            ),
        ]

    def __str__(self) -> str:
        return self.emoji
