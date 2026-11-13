from django.conf import settings
from django.db import models


class Offsite(models.Model):
    """The installation's off-site copy, in one row: the bucket its snapshots are mirrored to, the
    secret access key sealed with the installation's secret, and how the last mirroring, check
    and trial restore went."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    endpoint = models.URLField()
    bucket = models.CharField(max_length=63)
    access_key = models.CharField(max_length=128)
    secret = models.BinaryField()
    hint = models.CharField(max_length=4)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField()
    generation = models.CharField(max_length=10, blank=True)
    mirrored_at = models.DateTimeField(null=True)
    protected = models.BooleanField(null=True)
    error = models.TextField(blank=True)
    checked_at = models.DateTimeField(null=True)
    check_error = models.TextField(blank=True)
    tried_at = models.DateTimeField(null=True)
    trial = models.JSONField(null=True)
    trial_error = models.TextField(blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_offsite")]

    def __str__(self) -> str:
        return f"{self.endpoint}/{self.bucket}"


class Migrated(models.Model):
    """The version that last migrated this database, in one row: a database restored to a moment
    names by it the version to run it with."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    version = models.CharField(max_length=32)
    at = models.DateTimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_migrated")]

    def __str__(self) -> str:
        return self.version
