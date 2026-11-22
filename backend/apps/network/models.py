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


class Tunnel(models.Model):
    """A VPN tunnel of the installation, kept up by the service `tunnel`, through which what
    stands behind it is reached (D54). What lets it in, WireGuard's configuration or SoftEther's
    password, is sealed with the installation's secret; `shown` is what the settings show of it.
    `state`, `error` and `detail` are what the service told at its last change, `address` the
    installation's own on the far side, `since` when the state last changed."""

    class Kind(models.TextChoices):
        WIREGUARD = "wireguard"
        SOFTETHER = "softether"

    class State(models.TextChoices):
        CONNECTING = "connecting"
        UP = "up"
        FAILED = "failed"
        OFF = "off"
        # The service itself does not answer.
        UNREACHED = "unreached"

    name = models.CharField(max_length=150, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    enabled = models.BooleanField(default=True)
    shown = models.JSONField(default=dict)
    sealed = models.BinaryField(default=bytes)
    state = models.CharField(max_length=16, choices=State.choices, default=State.CONNECTING)
    error = models.CharField(max_length=32, blank=True)
    detail = models.TextField(blank=True)
    address = models.CharField(max_length=64, blank=True)
    since = models.DateTimeField(null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name
