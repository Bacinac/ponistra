"""Outside agents (D18): the clients that registered to sign a user in, what each user let in
and the tokens it holds. An agent acts as the user who let it in, so each grant is one user's
and goes with the user; revoking it keeps it for the history of what the agent did."""

import uuid

from django.conf import settings
from django.db import models


class Client(models.Model):
    """An MCP client as it registered itself (RFC 7591): its id, the name it gave, the rest of
    its metadata, and the digest of its secret where it asked for one."""

    client_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200, blank=True)
    registered = models.JSONField()
    secret_digest = models.CharField(max_length=64, blank=True)
    address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name or self.client_id


class Authorization(models.Model):
    """One sign-in under way: the client's request as it came, waiting for the user's consent,
    then the code the client exchanges, once, before it expires."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.DB_CASCADE, related_name="authorizations")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_CASCADE,
        related_name="+",
    )
    params = models.JSONField()
    code = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.client} {self.pk}"


class Grant(models.Model):
    """A client let in by a user: what it signed in as, when, when it last called, and when the
    user revoked it, after which no token of it opens anything."""

    client = models.ForeignKey(Client, on_delete=models.DB_CASCADE, related_name="grants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="agent_grants"
    )
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.client} via {self.user}"


class Token(models.Model):
    """An access or refresh token of a grant, kept as its digest, until it expires or is
    revoked."""

    class Kind(models.TextChoices):
        ACCESS = "access"
        REFRESH = "refresh"

    grant = models.ForeignKey(Grant, on_delete=models.DB_CASCADE, related_name="tokens")
    kind = models.CharField(max_length=7, choices=Kind)
    digest = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list)
    expires_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.kind} of {self.grant}"
