import uuid

from django.conf import settings
from django.db import models


class Blob(models.Model):
    """The bytes of a file, named by their SHA-256. The bytes live under BLOB_ROOT;
    whatever uses them refers to this row with a foreign key."""

    sha256 = models.CharField(primary_key=True, max_length=64)
    size = models.BigIntegerField()
    media_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField()

    def __str__(self) -> str:
        return self.sha256


class Upload(models.Model):
    """A file arriving in pieces, its bytes so far under BLOB_ROOT/uploads by its id; the Blob
    it became, for a client that lost the answer to its last piece."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    size = models.BigIntegerField()
    received = models.BigIntegerField(default=0)
    blob = models.ForeignKey(Blob, null=True, on_delete=models.DB_CASCADE, related_name="+")
    touched_at = models.DateTimeField()

    def __str__(self) -> str:
        return str(self.pk)


class Preview(models.Model):
    """A file's bytes drawn small enough for a glance, an image or a PDF's first page, once per
    blob and deleted with it. The picture is a blob of its own, kept while this row refers to
    it; where none could be drawn, why."""

    source = models.OneToOneField(
        Blob, primary_key=True, on_delete=models.DB_CASCADE, related_name="preview"
    )
    picture = models.ForeignKey(
        Blob, null=True, blank=True, on_delete=models.DO_NOTHING, related_name="pictured"
    )
    failed = models.TextField(blank=True)
    drawn_at = models.DateTimeField()

    def __str__(self) -> str:
        return self.source_id
