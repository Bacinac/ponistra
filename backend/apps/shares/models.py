from django.conf import settings
from django.db import models


class Share(models.Model):
    """A folder on a file server of the organisation's network that a company folder is
    connected to (D37): copied in, read-only, until the administrator moves it into PONISTRA,
    or an inbox whose files move into the company folder as they arrive."""

    class Mode(models.TextChoices):
        COPY = "copy"
        INBOX = "inbox"

    class State(models.TextChoices):
        # A copy's folder read whole before anything is copied, then waiting for the
        # administrator to copy it.
        READING = "reading"
        READ = "read"
        COPYING = "copying"
        READY = "ready"
        FAILED = "failed"

    folder = models.OneToOneField(
        "documents.Node", on_delete=models.DB_CASCADE, related_name="share"
    )
    mode = models.CharField(max_length=5, choices=Mode)
    host = models.CharField(max_length=253)
    # The share and the folders below it, as the server names them, by backslashes.
    path = models.CharField(max_length=1000)
    username = models.CharField(max_length=320)
    secret = models.BinaryField()
    state = models.CharField(max_length=8, choices=State)
    error = models.CharField(max_length=40, blank=True)
    # What the last reading found: files, folders and bytes, how many were copied, what stays
    # out and what was kept as a file the import could not read.
    found = models.JSONField(default=dict)
    # Asked to copy what changed last and leave the folder PONISTRA's.
    moving = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True)
    # Who connected it, whose name what it copies carries.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return rf"\\{self.host}\{self.path}"


class Entry(models.Model):
    """A file or folder of the share's as it was last copied, by its path below the share's
    folder, and the node it was copied into."""

    share = models.ForeignKey(Share, on_delete=models.DB_CASCADE, related_name="entries")
    path = models.CharField(max_length=2000)
    node = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    size = models.BigIntegerField()
    modified = models.DateTimeField()
    # Why an Office file was kept as the file it is, which the import could not read.
    kept = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["share", "path"], name="share_entry_once"),
        ]

    def __str__(self) -> str:
        return self.path
