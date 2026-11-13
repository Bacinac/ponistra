"""The installation's journal (U6): what happened to the installation as a whole, which its
administrators read, beside the logs a document and the vault keep of themselves."""

from django.conf import settings
from django.db import models


class Entry(models.Model):
    class Kind(models.TextChoices):
        SIGNED_IN = "signed_in"
        SIGN_IN_FAILED = "sign_in_failed"
        LOCKED_OUT = "locked_out"
        SIGNED_OUT = "signed_out"
        SESSIONS_ENDED = "sessions_ended"
        INSTALLED = "installed"
        USER_ADDED = "user_added"
        USER_CHANGED = "user_changed"
        USER_ERASED = "user_erased"
        GROUP_ADDED = "group_added"
        GROUP_RENAMED = "group_renamed"
        GROUP_REMOVED = "group_removed"
        POLICY_CHANGED = "policy_changed"
        PASSWORD_CHANGED = "password_changed"
        PASSKEY_ADDED = "passkey_added"
        PASSKEY_REMOVED = "passkey_removed"
        APP_PASSWORD_ADDED = "app_password_added"
        APP_PASSWORD_REMOVED = "app_password_removed"
        APPLICATION_ADDED = "application_added"
        APPLICATION_CHANGED = "application_changed"
        APPLICATION_REMOVED = "application_removed"
        APPLICATION_SECRET = "application_secret"
        APPLICATION_SIGNED_IN = "application_signed_in"
        PROVIDER_ADDED = "provider_added"
        PROVIDER_CHANGED = "provider_changed"
        PROVIDER_REMOVED = "provider_removed"
        PROVIDER_SECRET = "provider_secret"
        SETTING_CHANGED = "setting_changed"
        PROBLEM = "problem"
        RESOLVED = "resolved"

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=24, choices=Kind)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    address = models.GenericIPAddressField(null=True)
    detail = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["kind", "-id"])]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.kind}"
