"""A task is a note: a line with an owner, a due date where it has one, and done. It is made
from a mail, a meeting, a line of a document or a message and leads back to it. There is no
hierarchy, no project and no workflow (D17): the one list, the day in the calendar, Today."""

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.search.text import Folded, TaskWords


class Task(models.Model):
    class Source(models.TextChoices):
        MAIL = "mail"
        EVENT = "event"
        DOCUMENT = "document"
        MESSAGE = "message"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="tasks"
    )
    text = models.CharField(max_length=1000)
    due = models.DateField(null=True)
    done_at = models.DateTimeField(null=True)
    source_kind = models.CharField(max_length=8, choices=Source, blank=True)
    # What the task was made from, as the user saw it named, and PONISTRA's own page of it.
    source_label = models.CharField(max_length=300, blank=True)
    source_link = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)
    words = models.GeneratedField(
        expression=TaskWords("text", "source_label"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["owner", "done_at", "due"], name="tasks_task_listed"),
            GinIndex(fields=["words"], name="tasks_task_words"),
            GinIndex(OpClass(Folded("text"), name="gin_trgm_ops"), name="tasks_text_trigrams"),
        ]

    def __str__(self) -> str:
        return self.text
