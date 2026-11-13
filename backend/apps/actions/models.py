import uuid

from django.conf import settings
from django.db import models


class ActionRun(models.Model):
    """One run of an action on a document, or of one with none, as the search's translation of
    a sentence: who started it, the action, the address of its target and its parameters, how
    it went and how long it took. A model's run can be asked to stop, and one a restart cut off
    is marked interrupted; either keeps what it wrote. A run that writes into a tab it opens
    closes it when it is taken back or fails. It keeps what its model said at the end where the
    action keeps it, the answers it offered the user to choose from, and the operations it
    called by name, which the next turn of a conversation reads. A model's run records the
    model that answered, the tokens it read and wrote, with and without the cache, what they
    cost in dollars, unknown where a model has no price, and who let the text out to it, this
    once, for the whole document or for all of the user's own. A run over several documents
    goes through them as its items, and writes into the document it made for what it
    gathers."""

    class State(models.TextChoices):
        RUNNING = "running"
        STOPPING = "stopping"
        STOPPED = "stopped"
        INTERRUPTED = "interrupted"
        DONE = "done"
        FAILED = "failed"
        UNDONE = "undone"

    class Consented(models.TextChoices):
        ONCE = "once"
        DOCUMENT = "document"
        USER = "user"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_CASCADE, related_name="runs"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=100)
    target = models.JSONField()
    parameters = models.JSONField(default=dict)
    state = models.CharField(max_length=12, choices=State, default=State.RUNNING)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_SET_NULL,
        related_name="+",
    )
    undone_at = models.DateTimeField(null=True, blank=True)
    opened = models.ForeignKey(
        "documents.Tab", null=True, blank=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    reply = models.TextField(blank=True)
    offers = models.JSONField(default=list)
    calls = models.JSONField(default=list)
    model = models.CharField(max_length=100, blank=True)
    input_tokens = models.PositiveBigIntegerField(default=0)
    output_tokens = models.PositiveBigIntegerField(default=0)
    cache_read_tokens = models.PositiveBigIntegerField(default=0)
    cache_write_tokens = models.PositiveBigIntegerField(default=0)
    cost = models.DecimalField(max_digits=14, decimal_places=8, null=True, default=0)
    consent = models.CharField(max_length=8, choices=Consented, blank=True)
    consented_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_SET_NULL,
        related_name="+",
    )
    # The outside agent that started it, where one did, acting as the user (D18).
    grant = models.ForeignKey(
        "agents.Grant", null=True, blank=True, on_delete=models.DB_SET_NULL, related_name="runs"
    )

    class Meta:
        indexes = [models.Index(fields=["document", "-started_at"])]

    def __str__(self) -> str:
        return f"{self.action} {self.state}"


class RunChange(models.Model):
    """What a run changed in one room, a tab's or, with no tab, its document's own, by the Yjs
    ids of that room's state, and the patches it made to the room's grids, each with its
    before, to take it back later."""

    run = models.ForeignKey(ActionRun, on_delete=models.DB_CASCADE, related_name="changes")
    tab = models.ForeignKey(
        "documents.Tab", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    room = models.UUIDField()
    insertions = models.BinaryField()
    deletions = models.BinaryField()
    grids = models.JSONField(default=list)

    def __str__(self) -> str:
        return f"{self.run_id} {self.tab_id or 'own'}"


class RunItem(models.Model):
    """One of the documents or PDF files a run goes through, or one page of the file it
    translates, in its order: its title when the run began, the page's number, whether it is
    waiting, done or missed and why, and what the model found in it."""

    class State(models.TextChoices):
        WAITING = "waiting"
        DONE = "done"
        FAILED = "failed"
        SKIPPED = "skipped"

    run = models.ForeignKey(ActionRun, on_delete=models.DB_CASCADE, related_name="items")
    node = models.ForeignKey(
        "documents.Node", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    state = models.CharField(max_length=7, choices=State, default=State.WAITING)
    found = models.JSONField(default=list)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "position"], name="one_item_a_position")
        ]
        indexes = [models.Index(fields=["state", "run", "position"])]

    def __str__(self) -> str:
        return f"{self.run_id} {self.position} {self.state}"
