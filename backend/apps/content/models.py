from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone

from apps.search.text import Words


class Element(models.Model):
    """A block of a tab, or a filled cell of one of its tables, as the tab's content
    last read: its text, formatting and address, queryable without the Yjs state."""

    tab = models.ForeignKey("documents.Tab", on_delete=models.DB_CASCADE, related_name="elements")
    position = models.PositiveIntegerField()
    block = models.TextField(blank=True)
    row = models.TextField(blank=True)
    col = models.TextField(blank=True)
    type = models.CharField(max_length=40)
    text = models.TextField(blank=True)
    words = models.GeneratedField(
        expression=Words("text"), output_field=SearchVectorField(), db_persist=True
    )
    content = models.JSONField(default=dict)
    address = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tab", "position"], name="one_element_per_place")
        ]
        indexes = [GinIndex(fields=["words"], name="element_words")]

    def __str__(self) -> str:
        return f"{self.tab_id} {self.type} {self.address}"


class DocumentBlob(models.Model):
    """An image or a PDF a document shows. The link lasts as long as the document, so every
    version can show them again, and it keeps the bytes from being collected."""

    document = models.ForeignKey(
        "documents.Node", on_delete=models.DB_CASCADE, related_name="shown"
    )
    blob = models.ForeignKey("blobs.Blob", on_delete=models.DO_NOTHING, related_name="shown_in")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "blob"], name="one_link_per_blob")
        ]

    def __str__(self) -> str:
        return f"{self.document_id} {self.blob_id}"


class Grid(models.Model):
    """What a table keeps beside its rows (D16): the table block's id in its document, the
    tab whose text holds it, none for a header's or footer's, its name, its columns in order,
    each with its width in Excel's characters where it has one of its own, its look's key where
    it has one and whether it is hidden, and the id of the last row that stays at the top of
    the view, empty where none does. The text is what places it: a table taken out keeps its
    grid, so bringing the block back brings its cells. When it was last changed tells the
    readers of a tab that it changed, as its updates do of its text; how its values were
    calculated, empty until they are, has them calculated whole again by another engine or in
    another locale."""

    document = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    tab = models.ForeignKey(
        "documents.Tab", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="grids"
    )
    table = models.CharField(max_length=64)
    name = models.CharField(max_length=31, blank=True)
    cols = models.JSONField(default=list)
    frozen = models.CharField(max_length=64, blank=True)
    calculated = models.CharField(max_length=16, blank=True)
    edited_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "table"], name="one_grid_per_table")
        ]
        indexes = [models.Index(fields=["tab", "edited_at"], name="grid_edited")]

    def __str__(self) -> str:
        return f"{self.document_id} {self.table}"


class GridRow(models.Model):
    """A row of a table: its id, where it stands among the table's rows (spaced, so a row
    put in between moves no other), its height in points where it has one of its own, the
    key of its look where it has one, whether it is hidden, and by column id what its cells
    hold, the value of each that holds something as the engine reads it (engine.values.stored)
    and the text each shows where that is not the text typed in it or a number format writes
    it."""

    grid = models.ForeignKey(Grid, on_delete=models.DB_CASCADE, related_name="rows")
    row = models.CharField(max_length=64)
    position = models.BigIntegerField()
    height = models.FloatField(null=True, blank=True)
    look = models.CharField(max_length=16, blank=True)
    hidden = models.BooleanField(default=False)
    cells = models.JSONField(default=dict)
    values = models.JSONField(default=dict)
    shown = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["grid", "row"], name="one_row_per_id"),
            models.UniqueConstraint(
                fields=["grid", "position"],
                name="one_row_per_position",
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]
        indexes = [
            models.Index(
                fields=["grid", "position"], condition=models.Q(hidden=False), name="shown_rows"
            )
        ]

    def __str__(self) -> str:
        return f"{self.grid_id} {self.position} {self.row}"


class TableFilter(models.Model):
    """The rows of a table a user sees (D22, E3): a view, not a change, each user's own and
    kept for each table, the table's other users seeing all its rows. Each condition takes a
    column by id and either the texts its cells show that are let through, empty for an empty
    cell, or a comparison with a value (`filtering.CONDITIONS`)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    document = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    table = models.CharField(max_length=64)
    conditions = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document", "table"], name="one_filter_per_table"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.document_id} {self.table}"


class KeptRow(models.Model):
    """A row a change to a table keeps, so that taking the change back finds it in Postgres
    rather than in the change (D22, E3): under the change's key, in the order the rows stood,
    a row taken out as its `GridRow` held it, or a row reordered with the position it had.
    Kept while a book or a run can still take the change back."""

    document = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    key = models.CharField(max_length=32)
    ordinal = models.IntegerField()
    row = models.CharField(max_length=64)
    position = models.BigIntegerField()
    height = models.FloatField(null=True, blank=True)
    look = models.CharField(max_length=16, blank=True)
    hidden = models.BooleanField(default=False)
    cells = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "ordinal"], name="one_kept_row_per_ordinal")
        ]
        indexes = [models.Index(fields=["document", "key"], name="kept_rows")]

    def __str__(self) -> str:
        return f"{self.key} {self.ordinal} {self.row}"


class GridRowWords(models.Model):
    """The words search finds in a row of a table, what its cells show. They are kept apart
    from the row, so that writing a column of values writes no search index; a trigger on
    the rows queues each one written (StaleGridRow) and words.py reads them again in the
    background."""

    grid_row = models.OneToOneField(
        GridRow, primary_key=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    words = SearchVectorField()

    class Meta:
        indexes = [GinIndex(fields=["words"], name="grid_row_words")]

    def __str__(self) -> str:
        return str(self.grid_row_id)


class StaleGridRow(models.Model):
    """A row whose words are to be read again."""

    grid_row = models.OneToOneField(
        GridRow, primary_key=True, on_delete=models.DB_CASCADE, related_name="+"
    )

    def __str__(self) -> str:
        return str(self.grid_row_id)


class Name(models.Model):
    """A defined name of a document (D16): its id, the name formulas use, unique in its scope
    ignoring case, the formula it stands for in pieces by row and column id, and the table it
    is in force in alone, empty where it is in force in the whole document."""

    document = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    pieces = models.JSONField(default=list)
    table = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "key"], name="one_name_per_key")]

    def __str__(self) -> str:
        return f"{self.document_id} {self.name}"


class Shared(models.Model):
    """What cells of a document's tables share (D16), kept once and referred to by its key, a
    digest of it: a formula's pieces, its references to its own row and column written as
    such, or a look. Each row of a grid names those of its cells by key."""

    document = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    key = models.CharField(max_length=16)
    value = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "key"], name="one_shared_per_key")
        ]

    def __str__(self) -> str:
        return f"{self.document_id} {self.key}"
