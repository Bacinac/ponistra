"""PONISTRA as the identity other applications sign their users in with (D38, OpenID Connect):
the applications an administrator registered, the codes a sign-in hands them, and the keys the
installation signs its tokens with."""

from django.conf import settings
from django.db import models


class Application(models.Model):
    """An application that signs its users in here: where it may be sent back to, who may sign
    in to it, and the digest of its secret."""

    name = models.CharField(max_length=150)
    client_id = models.CharField(max_length=64, unique=True)
    secret_digest = models.CharField(max_length=64)
    redirect_uris = models.JSONField(default=list)
    everyone = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class Code(models.Model):
    """One sign-in's code, kept as its digest with what it was given for, until the application
    exchanges it once or it expires."""

    application = models.ForeignKey(Application, on_delete=models.DB_CASCADE, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    digest = models.CharField(max_length=64, unique=True)
    redirect_uri = models.TextField()
    scopes = models.JSONField(default=list)
    nonce = models.TextField(blank=True)
    challenge = models.CharField(max_length=128, blank=True)
    expires_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.application} for {self.user}"


class Key(models.Model):
    """A key the installation signs tokens with, its private half sealed."""

    kid = models.CharField(max_length=32, unique=True)
    sealed = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.kid


class Provider(models.Model):
    """Where the installation's people come from besides its own accounts (U1): an identity
    provider they sign in at (OpenID Connect, SAML), or a directory that lists them and their
    groups (LDAP read on a schedule, SCIM written by the directory itself)."""

    class Kind(models.TextChoices):
        OIDC = "oidc"
        SAML = "saml"
        LDAP = "ldap"
        SCIM = "scim"

    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=4, choices=Kind)
    settings = models.JSONField(default=dict)
    sealed = models.BinaryField(null=True)
    token_digest = models.CharField(max_length=64, blank=True)
    # Email domains whose people it may sign in or bring in; empty takes any address.
    domains = models.JSONField(default=list)
    creates = models.BooleanField(default=False)
    groups = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True)
    error = models.CharField(max_length=300, blank=True)

    def __str__(self) -> str:
        return self.name

    @staticmethod
    def offered(user=None) -> list[dict]:
        """The providers the sign-in page offers, or those the user can show who they are at
        again."""
        found = Provider.objects.filter(
            enabled=True, kind__in=(Provider.Kind.OIDC, Provider.Kind.SAML)
        )
        if user is not None:
            found = found.filter(identities__user=user)
        return [{"id": each.pk, "name": each.name} for each in found.order_by("name", "pk")]

    @property
    def signs_in(self) -> bool:
        return self.kind in (Provider.Kind.OIDC, Provider.Kind.SAML)

    @property
    def lists(self) -> bool:
        """Whether it keeps the people it knows: their names, addresses and whether they may
        sign in follow it, not the administrator."""
        return self.kind in (Provider.Kind.LDAP, Provider.Kind.SCIM)


class Identity(models.Model):
    """Who a person is at a provider: the subject it names them by, and what else it said of
    them that a later call needs (an LDAP entry's DN)."""

    provider = models.ForeignKey(Provider, on_delete=models.DB_CASCADE, related_name="identities")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="identities"
    )
    subject = models.CharField(max_length=255)
    detail = models.JSONField(default=dict)
    seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="one_subject"),
            models.UniqueConstraint(fields=["provider", "user"], name="one_identity"),
        ]

    def __str__(self) -> str:
        return f"{self.user} at {self.provider}"


class Kept(models.Model):
    """A group a provider keeps: its name and members follow the provider."""

    group = models.OneToOneField("auth.Group", on_delete=models.DB_CASCADE, related_name="kept")
    provider = models.ForeignKey(Provider, on_delete=models.DB_CASCADE, related_name="kept")
    subject = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="one_kept_subject")
        ]

    def __str__(self) -> str:
        return f"{self.group} at {self.provider}"


class Attempt(models.Model):
    """A sign-in sent to a provider, until it comes back once or expires: what binds the answer to
    the browser that asked (the digest of its cookie) and to the request (nonce, verifier, SAML
    request id), and, for a confirmation, the session it confirms."""

    provider = models.ForeignKey(Provider, on_delete=models.DB_CASCADE, related_name="+")
    digest = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=64, unique=True)
    nonce = models.CharField(max_length=64, blank=True)
    verifier = models.CharField(max_length=128, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    following = models.CharField(max_length=500, blank=True)
    confirming = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    session_key = models.CharField(max_length=40, blank=True)
    expires_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.provider} {self.state[:8]}"
