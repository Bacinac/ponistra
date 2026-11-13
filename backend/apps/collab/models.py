from django.db import models


class Update(models.Model):
    """A change to a room: a tab's content, or without a tab its document's own state."""

    document = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    tab = models.ForeignKey(
        "documents.Tab", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    room = models.UUIDField()
    data = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["room", "id"])]

    def __str__(self) -> str:
        return f"{self.tab_id or self.document_id} #{self.pk}"
