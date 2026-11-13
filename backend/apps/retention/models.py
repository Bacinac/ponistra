"""The installation's rules of retention and its legal holds (U4): how long each kind of content
must be kept before anyone may delete it, when it is removed by itself, and the people and
folders nothing may be deleted of while a matter is open."""

from django.conf import settings
from django.db import models


class What(models.TextChoices):
    DOCUMENTS = "documents"
    FILES = "files"
    MAIL = "mail"
    CHAT = "chat"


# The kinds a folder holds, which a rule may be narrowed to a folder for.
IN_FOLDERS = (What.DOCUMENTS, What.FILES)


class Rule(models.Model):
    what = models.CharField(max_length=16, choices=What)
    # Narrowed to what lies in the folder, at any depth; a rule nearer the content decides when it
    # is removed, while the longest of the rules above it decides how long it is kept.
    folder = models.ForeignKey(
        "documents.Node", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    # Nothing younger may be deleted, by anyone.
    keep_days = models.PositiveIntegerField(null=True, blank=True)
    # Older than this, it is removed for good by itself.
    remove_days = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["what", "folder"], name="retention_rule_once", nulls_distinct=False
            ),
            models.CheckConstraint(
                condition=models.Q(keep_days__isnull=False) | models.Q(remove_days__isnull=False),
                name="retention_rule_says_something",
            ),
            models.CheckConstraint(
                condition=models.Q(keep_days__isnull=True)
                | models.Q(remove_days__isnull=True)
                | models.Q(remove_days__gte=models.F("keep_days")),
                name="retention_rule_removes_after_keeping",
            ),
            models.CheckConstraint(
                condition=models.Q(folder__isnull=True) | models.Q(what__in=IN_FOLDERS),
                name="retention_rule_folder_holds_it",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.what} {self.folder_id or '*'}"


class Hold(models.Model):
    """A legal hold: of a person, everything that is theirs or that they wrote or were written in,
    or of a folder, everything in it, kept from deletion until the hold is released."""

    name = models.CharField(max_length=200)
    # Neither may go while held: the erasure and the purge refuse, and the database with them.
    person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    folder = models.ForeignKey(
        "documents.Node", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(person__isnull=False, folder__isnull=True)
                | models.Q(person__isnull=True, folder__isnull=False),
                name="retention_hold_one_subject",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Removal(models.Model):
    """What the rules removed in one pass, for the administrators to see."""

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    documents = models.PositiveIntegerField(default=0)
    files = models.PositiveIntegerField(default=0)
    mail = models.PositiveIntegerField(default=0)
    chat = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M}"
