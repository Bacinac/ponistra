import json
import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.documents.models import Node, depth_first
from apps.search.text import Words


class State(models.Model):
    """A room's whole Yjs state, kept once per document however many versions hold it, with
    the text of a tab's blocks as it stood, which the search over versions reads."""

    document = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="+")
    sha256 = models.CharField(max_length=64)
    data = models.BinaryField()
    text = models.TextField(blank=True, default="")
    words = models.GeneratedField(
        expression=Words("text"), output_field=SearchVectorField(), db_persist=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "sha256"], name="one_copy_of_a_state")
        ]
        indexes = [GinIndex(fields=["words"], name="state_words")]

    def __str__(self) -> str:
        return self.sha256


class Version(models.Model):
    """The whole document at one moment: its own state (theme and styles), every tab with its
    place, title and content, its defined names, by id, and what its grids' cells share, by
    key. Without a title it is automatic and thinned with age."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField()
    checked_at = models.DateTimeField()
    restored_from = models.PositiveIntegerField(null=True, blank=True)
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="VersionEditor", related_name="+"
    )
    state = models.ForeignKey(State, on_delete=models.DO_NOTHING, related_name="versions")
    names = models.JSONField(default=dict)
    shared = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "number"], name="one_number_per_version")
        ]

    def __str__(self) -> str:
        return f"{self.document_id} v{self.number}"

    def content(self) -> tuple[str, set[tuple], set[tuple], str]:
        tabs = self.tabs.values_list("tab", "parent", "position", "title", "state__sha256")
        grids = {
            (tab, table, name, json.dumps(cols), frozen, tuple(pieces))
            for tab, table, name, cols, frozen, pieces in self.grids.values_list(
                "tab", "table", "name", "cols", "frozen", "pieces"
            )
        }
        return self.state.sha256, set(tabs), grids, json.dumps(self.names, sort_keys=True)

    def tabs_in_order(self) -> list[VersionTab]:
        return depth_first(
            self.tabs.order_by("position"), lambda part: part.tab, lambda part: part.parent
        )


class VersionEditor(models.Model):
    version = models.ForeignKey(Version, on_delete=models.DB_CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE)

    class Meta:
        db_table = "versions_version_editors"
        unique_together = [("version", "user")]

    def __str__(self) -> str:
        return f"{self.version} {self.user}"


class VersionTab(models.Model):
    """A tab as a version holds it. The ids are values, not foreign keys, so deleting a
    tab keeps its history."""

    version = models.ForeignKey(Version, on_delete=models.DB_CASCADE, related_name="tabs")
    tab = models.UUIDField()
    parent = models.UUIDField(null=True, blank=True)
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=200, blank=True)
    state = models.ForeignKey(State, on_delete=models.DO_NOTHING, related_name="version_tabs")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "tab"], name="a_tab_once_per_version")
        ]

    def __str__(self) -> str:
        return f"{self.version} {self.title or self.tab}"


class Piece(models.Model):
    """Rows of a grid as a version holds them, each its id, height, cells and what they were
    calculated to, their formulas and looks by key, kept once per document however many versions
    and grids hold them, with how many rows they are and how many of those are not hidden."""

    document = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="+")
    sha256 = models.CharField(max_length=64)
    rows = models.JSONField()
    size = models.PositiveIntegerField(default=0)
    shown = models.PositiveIntegerField(default=0)
    text = models.TextField(blank=True, default="")
    words = models.GeneratedField(
        expression=Words("text"), output_field=SearchVectorField(), db_persist=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "sha256"], name="one_copy_of_a_piece")
        ]
        indexes = [GinIndex(fields=["words"], name="piece_words")]

    def __str__(self) -> str:
        return self.sha256


class VersionGrid(models.Model):
    """A table's grid as a version holds it: its name, columns, last frozen row and its rows'
    pieces in order, of a tab, or of the document's headers and footers without one, with how
    many rows it has, what lays it out by row id (`outline`: heights, looks, hidden, merges)
    and where the rows stand that the outline or a formula names (`at`), so that a browser
    reading it by windows and the text of its formulas need no pass over its rows."""

    version = models.ForeignKey(Version, on_delete=models.DB_CASCADE, related_name="grids")
    tab = models.UUIDField(null=True, blank=True)
    table = models.CharField(max_length=64)
    name = models.CharField(max_length=31, blank=True)
    cols = models.JSONField(default=list)
    frozen = models.CharField(max_length=64, blank=True)
    pieces = models.JSONField(default=list)
    size = models.PositiveIntegerField(default=0)
    outline = models.JSONField(default=dict)
    at = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "table"], name="a_grid_once_per_version")
        ]

    def __str__(self) -> str:
        return f"{self.version} {self.table}"


class Contribution(models.Model):
    """When a user last changed a document: a version's editors are those who did
    since the version before it."""

    document = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="+"
    )
    edited_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "user"], name="one_contribution_per_user")
        ]

    def __str__(self) -> str:
        return f"{self.user_id} → {self.document_id}"


class FileVersion(models.Model):
    """What a file held from one write to the next, the first as it was made: a board (D36)
    keeps every page an agent wrote over it, and the one taken back is written again."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="file_versions")
    number = models.PositiveIntegerField()
    blob = models.ForeignKey("blobs.Blob", on_delete=models.DO_NOTHING, related_name="versions")
    created_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    # The outside agent that wrote it for the user (D18), by the name its client gave.
    agent = models.CharField(max_length=200, blank=True)
    restored_from = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["node", "number"], name="one_number_per_file_version")
        ]

    def __str__(self) -> str:
        return f"{self.node_id} v{self.number}"
