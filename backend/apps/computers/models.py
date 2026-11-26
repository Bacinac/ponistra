"""Machines running Ponistra OS that joined the installation (C4.8): each enrolled with a one-time
code an administrator made, dials out to Ponistra and keeps that link up, and is managed by the
people its managers name. Its recovery key and backup password are kept sealed for them."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Computers(models.Manager):
    def managed(self, user):
        """The computers the user manages."""
        if not user.is_authenticated or not user.is_active:
            return self.none()
        return self.filter(managers=user)


class Computer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=63)
    # The sha256 of the machine's bearer token, empty once it left.
    token = models.CharField(max_length=64, blank=True, db_index=True)
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="Manager", related_name="computers_managed"
    )
    agent = models.CharField(max_length=64, blank=True)
    facts = models.JSONField(default=dict)
    alerts = models.JSONField(default=list)
    connected_at = models.DateTimeField(null=True)
    seen_at = models.DateTimeField(null=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    enrolled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    left_at = models.DateTimeField(null=True)
    recovery_key = models.BinaryField(null=True)
    recovery_key_at = models.DateTimeField(null=True)
    backup_password = models.BinaryField(null=True)
    backup_password_at = models.DateTimeField(null=True)

    objects = Computers()

    class Meta:
        ordering = [Lower("name")]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=models.Q(left_at__isnull=True),
                name="one_computer_per_name",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Manager(models.Model):
    computer = models.ForeignKey(Computer, on_delete=models.DB_CASCADE, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["computer", "user"], name="one_manager_per_computer")
        ]

    def __str__(self) -> str:
        return f"{self.user_id} manages {self.computer_id}"


class Code(models.Model):
    """A one-time code a machine enrolls with, kept as its sha256: shown once to whoever made it."""

    digest = models.CharField(max_length=64, unique=True)
    hint = models.CharField(max_length=4)
    made_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    made_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)
    computer = models.ForeignKey(
        Computer, null=True, on_delete=models.DB_SET_NULL, related_name="codes"
    )

    class Meta:
        ordering = ["-made_at"]

    def __str__(self) -> str:
        return f"…{self.hint}"


class Opening(models.Model):
    """Each time a manager read a computer's recovery key or backup password."""

    class Secret(models.TextChoices):
        RECOVERY_KEY = "recovery_key"
        BACKUP_PASSWORD = "backup_password"

    computer = models.ForeignKey(Computer, on_delete=models.DB_CASCADE, related_name="openings")
    secret = models.CharField(max_length=16, choices=Secret)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    at = models.DateTimeField(auto_now_add=True)
    address = models.GenericIPAddressField(null=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.secret} {self.at:%Y-%m-%d %H:%M}"
