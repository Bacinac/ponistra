from django.db import models


class Problem(models.Model):
    """Something wrong with the installation the watch found, from when it first saw it; raised
    to the administrators once it has held for its grace, and gone when the watch no longer
    finds it."""

    key = models.CharField(max_length=40, unique=True)
    since = models.DateTimeField()
    raised_at = models.DateTimeField(null=True)
    detail = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.key
