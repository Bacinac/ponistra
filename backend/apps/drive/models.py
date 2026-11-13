from django.conf import settings
from django.db import models


class Drive(models.Model):
    """A user's Google account whose My Drive, and the shared drives it sees, are copied into
    PONISTRA and followed while Google stays the original, until the user finishes leaving it
    (D44)."""

    class State(models.TextChoices):
        COPYING = "copying"
        READY = "ready"

    account = models.OneToOneField(
        "mail.Account", on_delete=models.DB_CASCADE, related_name="drive"
    )
    # The account's owner, whom what it copies and how far it came are told to.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    state = models.CharField(max_length=8, choices=State, default=State.COPYING)
    error = models.CharField(max_length=40, blank=True)
    # Asked to take what changed last and leave the copies PONISTRA's.
    finishing = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"drive of {self.account_id}"


class Space(models.Model):
    """One of Google's trees copied once into a folder at the top of its taker's documents: a
    user's My Drive, or a shared drive, whichever of its members' drives reaches it first
    following it."""

    google_id = models.CharField(max_length=100, unique=True)
    shared = models.BooleanField(default=False)
    drive = models.ForeignKey(Drive, null=True, on_delete=models.DB_SET_NULL, related_name="spaces")
    folder = models.OneToOneField(
        "documents.Node", on_delete=models.DB_CASCADE, related_name="drive_space"
    )
    # Where Google's changes since the last whole pass begin, empty until one is complete.
    changes = models.CharField(max_length=200, blank=True)
    # Who the shared drive's members are, as user id and role, granted on its folder.
    granted = models.JSONField(default=dict)
    # Files, folders and bytes copied, and what stays out with why.
    found = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True)

    def __str__(self) -> str:
        return self.google_id


class Item(models.Model):
    """A file or folder of Google's as it was last copied, and the node it was copied into."""

    space = models.ForeignKey(Space, on_delete=models.DB_CASCADE, related_name="items")
    google_id = models.CharField(max_length=100, unique=True)
    parent = models.CharField(max_length=100)
    node = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    folder = models.BooleanField(default=False)
    # The content's checksum, or for Google's own formats when it last changed.
    stamp = models.CharField(max_length=64, blank=True)
    # Google's ids of who may open it, which its children's are compared with.
    permissions = models.JSONField(default=list)
    # Who it was shared with beyond its folder, as user id and role, granted on its node.
    granted = models.JSONField(default=dict)
    # Why an Office file was kept as the file it is, which the import could not read.
    kept = models.CharField(max_length=20, blank=True)

    def __str__(self) -> str:
        return self.google_id
