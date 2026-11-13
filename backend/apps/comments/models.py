import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.search.text import Words


class Thread(models.Model):
    """A conversation about a stretch of a tab's text, or about a place on a file's page. In a
    tab the anchor holds the stretch's ends as Yjs relative positions, so it follows the text's
    edits without a mark in it; on a page it holds the rectangles of the chosen text, or the
    point, in the page's own coordinates. The quote is what the stretch said, kept for when it
    is gone."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tab = models.ForeignKey(
        "documents.Tab",
        null=True,
        blank=True,
        on_delete=models.DB_CASCADE,
        related_name="threads",
    )
    file = models.ForeignKey(
        "documents.Node",
        null=True,
        blank=True,
        on_delete=models.DB_CASCADE,
        related_name="threads",
    )
    anchor = models.JSONField()
    quote = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_SET_NULL,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tab__isnull=False, file__isnull=True)
                | models.Q(tab__isnull=True, file__isnull=False),
                name="a_thread_is_on_a_tab_or_a_file",
            ),
        ]

    def __str__(self) -> str:
        return self.quote[:40]

    @property
    def node(self):
        """The document or the file the thread is about."""
        return self.file if self.tab_id is None else self.tab.document


class Comment(models.Model):
    """One message of a thread; the first one opens it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.DB_CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # Who wrote a comment that came in with an imported file, as the file names them.
    outside_author = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    words = models.GeneratedField(
        expression=Words("body"), output_field=SearchVectorField(), db_persist=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [GinIndex(fields=["words"], name="comment_words")]

    def __str__(self) -> str:
        return self.body[:40]
