"""Web Push (S2-4): the installation's key pair, whether it sends at all, each browser a user
let it reach, and the notices waiting to be sent."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Keys(models.Model):
    """The installation's VAPID key pair, made the first time a browser asks for it."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    private = models.BinaryField()
    public = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_push_keys")]

    def __str__(self) -> str:
        return "keys"


class Setting(models.Model):
    """Whether the installation sends notifications to browsers, in one row."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    on = models.BooleanField(default=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_push_setting")]

    def __str__(self) -> str:
        return "on" if self.on else "off"


class Subscription(models.Model):
    """A browser the user let notifications reach, by the subscription it made with the
    installation's public key, in the language it read PONISTRA in."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.BinaryField()
    auth = models.BinaryField()
    language = models.CharField(max_length=2, default="hr")
    agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return self.endpoint


class Notice(models.Model):
    """What waits to reach a user's browsers: the facts of a kind, worded for each browser in its
    language when sent."""

    class Kind(models.TextChoices):
        MAIL = "mail"
        MESSAGE = "message"
        RING = "ring"
        SECURITY = "security"
        LATER = "later"
        HEALTH = "health"
        UPLOADED = "uploaded"
        CODE = "code"

    class Urgency(models.TextChoices):
        NORMAL = "normal"
        HIGH = "high"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="push_notices"
    )
    kind = models.CharField(max_length=8, choices=Kind)
    data = models.JSONField(default=dict)
    tag = models.CharField(max_length=32, blank=True)
    urgency = models.CharField(max_length=6, choices=Urgency, default=Urgency.NORMAL)
    ttl = models.PositiveIntegerField(default=86400)
    tried = models.PositiveSmallIntegerField(default=0)
    due_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["due_at"])]

    def __str__(self) -> str:
        return f"{self.kind} for {self.user_id}"
