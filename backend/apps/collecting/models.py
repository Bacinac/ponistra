from django.conf import settings
from django.db import models


class Collection(models.Model):
    """What a user gathers out of their mail as it comes (ZB): the messages it takes, by the
    accounts, senders and words of their subject, with a file or without, or with the model
    deciding which are bills; each month's files in a folder of their own beside a table of
    whom, when and how much, sent on a day of the next month as a draft or by itself."""

    class Sends(models.TextChoices):
        DRAFT = "draft"
        SEND = "send"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    name = models.CharField(max_length=200)
    # The ids of the owner's accounts it reads; none, every one of them.
    accounts = models.JSONField(default=list)
    # Addresses or domains, as a rule names a sender; none, anyone.
    senders = models.JSONField(default=list)
    # Any of them in the subject; none, any subject.
    words = models.JSONField(default=list)
    attached = models.BooleanField(default=True)
    # The model decides which messages are bills and reads what they ask for; turning it on is
    # the owner's consent to let those messages out to it.
    recognise = models.BooleanField(default=False)
    since = models.DateField()
    folder = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    to = models.JSONField(default=list)
    account = models.ForeignKey(
        "mail.Account", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    day = models.PositiveSmallIntegerField(default=1)
    hour = models.PositiveSmallIntegerField(default=9)
    sends = models.CharField(max_length=5, choices=Sends, default=Sends.DRAFT)
    text = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    # The highest message read through, from which the next look goes on.
    mark = models.BigIntegerField(default=0)
    error = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "name"], name="collecting_owner")]

    def __str__(self) -> str:
        return self.name


class Month(models.Model):
    """A collection's month by the date its messages came: the folder its files are in, the
    table made of them, and the message that took them to whom the collection sends them."""

    collection = models.ForeignKey(Collection, on_delete=models.DB_CASCADE, related_name="months")
    month = models.DateField()
    folder = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    table = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # A month whose day came before the collection was made, sent only when the owner asks.
    past = models.BooleanField(default=False)
    asked_at = models.DateTimeField(null=True)
    delivered_at = models.DateTimeField(null=True)
    unsent = models.ForeignKey(
        "mail.Unsent", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    failed = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["collection", "month"], name="collecting_month_once")
        ]

    def __str__(self) -> str:
        return f"{self.collection_id} {self.month:%Y-%m}"


class Item(models.Model):
    """A message a collection took: waiting to be read, kept with what it says, passed over as
    no bill, or failed with why."""

    class State(models.TextChoices):
        WAITING = "waiting"
        KEPT = "kept"
        PASSED = "passed"
        FAILED = "failed"

    collection = models.ForeignKey(Collection, on_delete=models.DB_CASCADE, related_name="items")
    month = models.ForeignKey(Month, on_delete=models.DB_CASCADE, related_name="items")
    message = models.ForeignKey(
        "mail.Message", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # Added by the owner's hand, kept whatever the model says of it.
    chosen = models.BooleanField(default=False)
    state = models.CharField(max_length=7, choices=State, default=State.WAITING)
    error = models.CharField(max_length=40, blank=True)
    subject = models.TextField(blank=True)
    sender = models.CharField(max_length=320, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    date = models.DateField(null=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    currency = models.CharField(max_length=3, blank=True)
    # The ids of the files it put in its month's folder.
    files = models.JSONField(default=list)
    run = models.ForeignKey(
        "actions.ActionRun", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    tried_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["collection", "message"], name="collecting_item_once")
        ]
        indexes = [
            models.Index(
                fields=["created_at"],
                condition=models.Q(state="waiting"),
                name="collecting_item_waiting",
            )
        ]

    def __str__(self) -> str:
        return self.subject
