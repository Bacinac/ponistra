from django.conf import settings
from django.db import models


class Seen(models.Model):
    """What the workspace last showed of its rounds and checks, in one row, so that its owner hears
    of each once, across restarts."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    shown = models.JSONField(default=dict)
    at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_workspace_seen")]

    def __str__(self) -> str:
        return "seen"


class Command(models.Model):
    """What the workspace's owner asked of it from the page of code, and how far it got (KR8):
    sent to the workspace, taken by whatever carries it out there, done or failed. The workspace
    has one owner, the installation's, so a command names nobody."""

    class Kind(models.TextChoices):
        CHAT = "chat"
        START = "start"
        CONSOLIDATE = "consolidate"
        PUSH = "push"
        AUTO = "auto"
        SAY = "say"
        ANSWER = "answer"
        RENAME = "rename"
        MODEL = "model"
        CLOSE = "close"
        OPEN = "open"
        ARCHIVE = "archive"
        RESTART = "restart"
        STOP = "stop"

    class State(models.TextChoices):
        SENT = "sent"
        TAKEN = "taken"
        DONE = "done"
        FAILED = "failed"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    folder = models.CharField(max_length=500, blank=True)
    round = models.CharField(max_length=100, blank=True)
    session = models.CharField(max_length=36, blank=True)
    text = models.TextField(blank=True)
    images = models.PositiveSmallIntegerField(default=0)
    # Asked by the workspace's own rule rather than the owner: a round consolidated by itself.
    auto = models.BooleanField(default=False)
    state = models.CharField(max_length=8, choices=State.choices, default=State.SENT)
    error = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["-created_at"], name="workspace_command_recent")]

    def __str__(self) -> str:
        return f"{self.kind} {self.state}"


class Aside(models.Model):
    """A project its owner put under Others, by its folder's name, and when: it stays there until
    anything in it runs after that (KR31)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=255)
    at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="workspace_aside_once")
        ]

    def __str__(self) -> str:
        return self.name
