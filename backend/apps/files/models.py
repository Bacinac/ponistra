from django.conf import settings
from django.db import models


class Bookmark(models.Model):
    """A folder of any source of Files a user keeps at hand, by the source's key and the path
    within it, under the name they gave it."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="file_bookmarks"
    )
    source = models.CharField(max_length=200)
    path = models.TextField(blank=True)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return self.name
