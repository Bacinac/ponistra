import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class Job(models.Model):
    """Work a user hands the server that can take longer than the proxies in front of it give a
    request: a document saved as a file, or a file or pages made into a document. It waits in a
    queue the backend goes through in its own process, and is kept for JOBS_KEPT once it ends,
    with what it made: the bytes of a file, or the answer the browser reads, or why it failed,
    as the status and code a request would have been refused with. The file it reads it holds,
    so that the bytes outlive the wait."""

    class State(models.TextChoices):
        WAITING = "waiting"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"
        CANCELLED = "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    kind = models.CharField(max_length=20)
    parameters = models.JSONField(default=dict)
    source = models.ForeignKey(
        "blobs.Blob", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="read_by"
    )
    state = models.CharField(max_length=10, choices=State, default=State.WAITING)
    attempts = models.PositiveSmallIntegerField(default=0)
    status = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=40, blank=True)
    answer = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    file = models.ForeignKey(
        "blobs.Blob", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="made_by"
    )
    name = models.CharField(max_length=220, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "queued_at"]),
            models.Index(fields=["finished_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.pk}"
