from django.db import models


class Proposal(models.Model):
    """A change to one file of the agent's memory (MEM2), as the whole text it would have: found
    by the workspace's mechanical reading or proposed by an analysing session. Accepted, it is
    written only while the file is still the one it was read from (`base_hash`); otherwise it goes
    stale and is read again. An applied change is the history, taken back the same way."""

    class Source(models.TextChoices):
        MECHANICAL = "mechanical"
        SESSION = "session"

    class State(models.TextChoices):
        OPEN = "open"
        APPLIED = "applied"
        REJECTED = "rejected"
        STALE = "stale"
        REVERTED = "reverted"

    store = models.CharField(max_length=200)
    file = models.CharField(max_length=200)
    source = models.CharField(max_length=10, choices=Source.choices)
    kind = models.CharField(max_length=20)
    reason = models.TextField(blank=True)
    session = models.CharField(max_length=36, blank=True)
    before = models.TextField(blank=True)
    after = models.TextField(blank=True)
    removes = models.BooleanField(default=False)
    base_hash = models.CharField(max_length=64, blank=True)
    after_hash = models.CharField(max_length=64, blank=True)
    written_hash = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=8, choices=State.choices, default=State.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["state", "-created_at"], name="memory_proposal_state")]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "file", "kind", "base_hash", "after_hash"],
                condition=models.Q(source="mechanical"),
                name="memory_mechanical_once",
            )
        ]

    def __str__(self) -> str:
        return f"{self.store}/{self.file} {self.kind} {self.state}"


class Advice(models.Model):
    """One group of open proposals an analysing session put together (MEM6), with what it advises
    doing with all of them at once. A new review replaces every group before it."""

    class Action(models.TextChoices):
        ACCEPT = "accept"
        REJECT = "reject"
        LOOK = "look"

    position = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    reason = models.TextField()
    action = models.CharField(max_length=6, choices=Action.choices)
    proposals = models.ManyToManyField(Proposal, related_name="advice")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.title} {self.action}"


class Analysed(models.Model):
    """The text of a memory file an analysing session was last given (MEM4), so that the next
    analysis reads only what changed since."""

    store = models.CharField(max_length=200)
    file = models.CharField(max_length=200)
    hash = models.CharField(max_length=64)
    at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["store", "file"], name="memory_analysed_once")
        ]

    def __str__(self) -> str:
        return f"{self.store}/{self.file}"


class Nightly(models.Model):
    """Whether the memory is read and analysed each night (MEM5), off until its owner turns it on,
    and the night it last was."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    on = models.BooleanField(default=False)
    last = models.DateField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_memory_nightly")]

    def __str__(self) -> str:
        return "nightly"
