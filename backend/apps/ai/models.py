from django.conf import settings
from django.db import models


class Setting(models.Model):
    """The installation's AI, in one row: whether its actions may call a model, its Anthropic
    API key sealed with the installation's secret, of which only the last four characters are
    shown again, and how many dollars each user's runs may take in a calendar month, without
    a bound where none is set."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    key = models.BinaryField(default=bytes)
    hint = models.CharField(max_length=4, blank=True)
    monthly = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_ai_setting")]

    def __str__(self) -> str:
        return "on" if self.enabled else "off"


class Consent(models.Model):
    """A document whose editors run its AI actions without being asked each time: who agreed
    to it, and when."""

    document = models.OneToOneField(
        "documents.Node",
        primary_key=True,
        on_delete=models.DB_CASCADE,
        related_name="ai_consent",
    )
    given_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    given_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.document_id)


class SearchConsent(models.Model):
    """A user's answer, given once for all of their searches, to whether a sentence typed in the
    search box goes to the model to become filters, and when it was given."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.DB_CASCADE,
        related_name="search_consent",
    )
    translate = models.BooleanField()
    given_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id} {self.translate}"


class Speech(models.Model):
    """The installation's speech to text (D28), in one row: whether spoken words may go to
    OpenAI to be written, and its OpenAI API key sealed as the Anthropic one is."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    key = models.BinaryField(default=bytes)
    hint = models.CharField(max_length=4, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_speech_setting")]

    def __str__(self) -> str:
        return "on" if self.enabled else "off"


class SpeechConsent(models.Model):
    """A user's agreement, given once, that what they say into the microphone goes to OpenAI
    to be written."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.DB_CASCADE,
        related_name="speech_consent",
    )
    given_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.user_id)


class Reading(models.Model):
    """The languages a user reads, the interface's alone until they choose, and whether a message
    in another goes to the model to be translated as it opens, without asking each time (D35)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.DB_CASCADE,
        related_name="reading",
    )
    languages = models.JSONField(null=True)
    automatic = models.BooleanField(default=False)
    changed_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id} {self.languages}"
