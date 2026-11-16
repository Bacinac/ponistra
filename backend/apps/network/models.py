from django.conf import settings
from django.db import models


class Dns(models.Model):
    """Where Cloudflare keeps the names pointing straight at the installation (DIRECT_NAMES), the
    token of their zone that keeps them on its public address as it changes, in one row. The token
    is sealed with the installation's secret, of which only its last four characters are shown
    again; `error` is what Cloudflare answered at the last look, empty while the names follow."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    token = models.BinaryField(default=bytes)
    hint = models.CharField(max_length=4, blank=True)
    error = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_network_dns")]

    def __str__(self) -> str:
        return f"…{self.hint}" if self.hint else "none"
