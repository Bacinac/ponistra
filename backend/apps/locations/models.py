import uuid

from django.conf import settings
from django.db import models

from apps.access.models import Role


class Location(models.Model):
    """A folder on a server of the network a user reaches with their own account there (D54):
    read live from where it stands, nothing of it kept until someone copies it into PONISTRA.
    Its secret, the account's password or the key PONISTRA made for it, is sealed."""

    class Kind(models.TextChoices):
        SMB = "smb"
        SFTP = "sftp"

    class Auth(models.TextChoices):
        PASSWORD = "password"
        KEY = "key"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="locations"
    )
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=4, choices=Kind)
    host = models.CharField(max_length=253)
    port = models.PositiveIntegerField()
    # SMB: the share and the folders below it, by backslashes. SFTP: the folder the location
    # opens at, from the account's home where it is not absolute.
    path = models.CharField(max_length=1000, blank=True)
    username = models.CharField(max_length=320)
    auth = models.CharField(max_length=8, choices=Auth)
    secret = models.BinaryField()
    # The public half of the key PONISTRA made, for the server's authorized_keys.
    public_key = models.TextField(blank=True)
    # SFTP through another host first, as `user@host:port`, signed in to with the same secret.
    jump = models.CharField(max_length=600, blank=True)
    # The installation's VPN tunnel the server stands behind; none reaches it straight. A tunnel
    # some location goes through is not removed: the database refuses, rather than the location
    # reaching for the same address on the installation's own network.
    tunnel = models.ForeignKey(
        "network.Tunnel",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="locations",
    )
    # The server's host keys as the first connection found them; another one later is refused.
    known_hosts = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class Grant(models.Model):
    """A role on a location for a user, a group, or everyone (neither), as a folder is shared:
    read lists and reads it, edit changes its files too, own also changes and shares it."""

    location = models.ForeignKey(Location, on_delete=models.DB_CASCADE, related_name="grants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_CASCADE,
        related_name="location_grants",
    )
    group = models.ForeignKey(
        "auth.Group",
        null=True,
        blank=True,
        on_delete=models.DB_CASCADE,
        related_name="location_grants",
    )
    role = models.CharField(max_length=8, choices=Role)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=True) | models.Q(group__isnull=True),
                name="location_grant_has_one_grantee",
            ),
            models.UniqueConstraint(
                fields=["location", "user", "group"],
                nulls_distinct=False,
                name="one_location_grant_per_grantee",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role} on {self.location_id}"
