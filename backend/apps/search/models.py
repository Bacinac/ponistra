from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from .text import Words


class BlobText(models.Model):
    """The text of a blob's bytes, extracted once per blob and deleted with it: a PDF's by its
    pages, an Office file's by its tabs."""

    blob = models.OneToOneField(
        "blobs.Blob", primary_key=True, on_delete=models.DB_CASCADE, related_name="text"
    )
    page_count = models.PositiveIntegerField()
    failed = models.TextField(blank=True)
    extracted_at = models.DateTimeField()

    def __str__(self) -> str:
        return self.blob_id


class BlobPage(models.Model):
    """One page's or tab's text; one without any has no row."""

    source = models.ForeignKey(BlobText, on_delete=models.DB_CASCADE, related_name="pages")
    number = models.PositiveIntegerField()
    text = models.TextField()
    words = models.GeneratedField(
        expression=Words("text"), output_field=SearchVectorField(), db_persist=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "number"], name="one_text_per_page")
        ]
        indexes = [GinIndex(fields=["words"], name="blob_page_words")]

    def __str__(self) -> str:
        return f"{self.source_id} p. {self.number}"


class PdfOcr(models.Model):
    """Tesseract reading the pages of a PDF's bytes that carry no text, once per blob and
    deleted with it. The copy with the text laid over those pages is a blob of its own, kept
    while this row refers to it; the bytes as they came stay untouched."""

    class State(models.TextChoices):
        WAITING = "waiting"
        DONE = "done"
        REFUSED = "refused"
        FAILED = "failed"

    blob = models.OneToOneField(
        "blobs.Blob", primary_key=True, on_delete=models.DB_CASCADE, related_name="ocr"
    )
    state = models.CharField(max_length=7, choices=State, default=State.WAITING)
    readable = models.ForeignKey(
        "blobs.Blob",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="read_from",
    )
    reason = models.TextField(blank=True)
    queued_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.blob_id
