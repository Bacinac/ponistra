import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import Func, TextField

from apps.blobs import store
from apps.search.text import Folded, Words


class Node(models.Model):
    class Kind(models.TextChoices):
        FOLDER = "folder"
        DOCUMENT = "document"
        FILE = "file"
        LINK = "link"

    class Locale(models.TextChoices):
        HR = "hr"
        EN = "en"
        EN_GB = "en-GB"
        DE = "de"
        FR = "fr"
        IT = "it"
        ES = "es"

    class Holds(models.TextChoices):
        TEXT = "text"
        TABLE = "table"
        SLIDES = "slides"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="children"
    )
    kind = models.CharField(max_length=16, choices=Kind)
    title = models.CharField(max_length=200)
    locale = models.CharField(max_length=8, choices=Locale, default=Locale.HR)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    trashed_at = models.DateTimeField(null=True, blank=True)
    blob = models.ForeignKey(
        "blobs.Blob", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="nodes"
    )
    # The extension a file's name was uploaded with, which names its kind even where its bytes
    # are of another kind (an Illustrator file is a PDF) or of none PONISTRA knows.
    extension = models.CharField(max_length=10, blank=True, default="")
    # A link's page (D31), what the page says of itself and its site's icon, as last read.
    href = models.CharField(max_length=2000, blank=True, default="")
    description = models.TextField(blank=True, default="")
    icon = models.ForeignKey(
        "blobs.Blob", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="icons"
    )
    read_at = models.DateTimeField(null=True, blank=True)
    # A document's own Yjs room, its theme and styles beside its tabs' rooms; a file's, its notes.
    room = models.UUIDField(null=True, blank=True, unique=True)
    # The latest change its tabs' counts of pages were last counted after.
    paged_at = models.DateTimeField(null=True, blank=True)
    # The file a document was imported from, kept beside it, and what the import could not
    # carry over, until someone with the right to edit has read it.
    source = models.ForeignKey(
        "blobs.Blob", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="imported_as"
    )
    imported = models.JSONField(null=True, blank=True)
    # What a document's content takes as stored and what it holds, measured as its elements are
    # read: its Yjs state, its tables' rows and the images and PDFs it shows.
    content_size = models.BigIntegerField(null=True, blank=True)
    holds = models.CharField(max_length=8, choices=Holds, blank=True, default="")
    # An image file's copy with the edits its room keeps drawn in, and the latest change to the
    # room it was drawn after; none while nothing is edited.
    edited = models.ForeignKey(
        "blobs.Blob",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="edited_files",
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    # A top-level folder of the company's, which the administrator lays out and gives to groups
    # without a right to read it.
    company = models.BooleanField(default=False)
    # A folder whose documents and files leave the browser only for their owners.
    confined = models.BooleanField(default=False)
    # A top-level folder holding a copy of a file server's folder (D37) or of a Google Drive (D44)
    # until it is moved in; every role in it reads.
    copied = models.BooleanField(default=False)
    # The top-level folder of its creator's notes (D27), one live at a time.
    notes = models.BooleanField(default=False)
    # The top-level folder of its creator's links (D31), one live at a time; the folders in it are
    # the groups the page of links shows.
    links = models.BooleanField(default=False)
    # The top-level folder of its creator's boards (D47), one live at a time; the folders in it
    # are the groups the page of boards shows.
    boards = models.BooleanField(default=False)
    # Where the user laid it out among its siblings on the page of links; those never laid out
    # follow, by name.
    position = models.PositiveIntegerField(null=True, blank=True)
    # How many columns the page of links lays a group's tiles in at most; unset, as many as fit.
    columns = models.PositiveSmallIntegerField(null=True, blank=True)
    # A document whose title is its first line, a link whose title is its page's, until someone
    # names it.
    follows_text = models.BooleanField(default=False)
    # The folder of the code workspace a board's agent starts in (D34), chosen by its owner rather
    # than by the page, which could otherwise send the agent anywhere.
    agent_folder = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["parent", "title"]),
            GinIndex(Words("title"), name="node_title_words"),
            GinIndex(OpClass(Folded("title"), name="gin_trgm_ops"), name="node_title_trigrams"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(pk=models.F("parent")), name="node_is_not_its_own_parent"
            ),
            models.CheckConstraint(
                condition=models.Q(kind="file", blob__isnull=False)
                | (~models.Q(kind="file") & models.Q(blob__isnull=True)),
                name="a_file_has_its_bytes",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["document", "file"], room__isnull=False)
                | models.Q(kind__in=["folder", "link"], room__isnull=True),
                name="a_document_or_file_has_its_room",
            ),
            models.CheckConstraint(
                condition=(models.Q(kind="link") & ~models.Q(href=""))
                | (~models.Q(kind="link") & models.Q(href="", icon__isnull=True)),
                name="a_link_has_its_page",
            ),
            models.CheckConstraint(
                condition=models.Q(kind="document") | models.Q(source__isnull=True),
                name="only_a_document_is_imported",
            ),
            models.CheckConstraint(
                condition=models.Q(company=False) | models.Q(kind="folder", parent__isnull=True),
                name="a_company_folder_is_at_the_top",
            ),
            models.CheckConstraint(
                condition=models.Q(copied=False) | models.Q(kind="folder", parent__isnull=True),
                name="only_a_top_folder_is_copied",
            ),
            models.CheckConstraint(
                condition=models.Q(confined=False) | models.Q(kind="folder"),
                name="only_a_folder_is_confined",
            ),
            models.CheckConstraint(
                condition=models.Q(notes=False) | models.Q(kind="folder", parent__isnull=True),
                name="a_notes_folder_is_at_the_top",
            ),
            models.CheckConstraint(
                condition=models.Q(links=False)
                | models.Q(kind="folder", parent__isnull=True, notes=False),
                name="a_links_folder_is_at_the_top",
            ),
            models.CheckConstraint(
                condition=models.Q(boards=False)
                | models.Q(kind="folder", parent__isnull=True, notes=False, links=False),
                name="a_boards_folder_is_at_the_top",
            ),
            models.CheckConstraint(
                condition=models.Q(follows_text=False) | models.Q(kind__in=["document", "link"]),
                name="only_a_document_or_link_follows_its_text",
            ),
            models.UniqueConstraint(
                fields=["created_by"],
                condition=models.Q(notes=True, trashed_at__isnull=True),
                name="one_live_notes_folder",
            ),
            models.UniqueConstraint(
                fields=["created_by"],
                condition=models.Q(links=True, trashed_at__isnull=True),
                name="one_live_links_folder",
            ),
            models.UniqueConstraint(
                fields=["created_by"],
                condition=models.Q(boards=True, trashed_at__isnull=True),
                name="one_live_boards_folder",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if self.kind in (Node.Kind.DOCUMENT, Node.Kind.FILE) and self.room is None:
            self.room = uuid.uuid4()
        super().save(*args, **kwargs)

    def ancestry(self) -> list[Node]:
        """The node and its ancestors, root first."""
        return Node.ancestries([self.pk]).get(self.pk, [])

    @staticmethod
    def ancestries(ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[Node]]:
        """Each node's ancestry, root first, in one query."""
        chains: dict[uuid.UUID, list[Node]] = defaultdict(list)
        for node in Node.objects.raw(
            """
            WITH RECURSIVE chain AS (
                SELECT id AS start, *, 0 AS depth FROM documents_node WHERE id = ANY(%s)
                UNION ALL
                SELECT chain.start, node.*, chain.depth + 1
                FROM documents_node node JOIN chain ON node.id = chain.parent_id
            )
            SELECT * FROM chain ORDER BY start, depth DESC
            """,
            [list(ids)],
        ):
            chains[node.start].append(node)
        return dict(chains)

    def descendants(self) -> list[Node]:
        """The live nodes below this one, each after its parent."""
        below = Node.objects.raw(
            """
            WITH RECURSIVE tree AS (
                SELECT *, 1 AS depth FROM documents_node
                WHERE parent_id = %s AND trashed_at IS NULL
                UNION ALL
                SELECT node.*, tree.depth + 1
                FROM documents_node node JOIN tree ON node.parent_id = tree.id
                WHERE node.trashed_at IS NULL
            )
            SELECT * FROM tree ORDER BY depth
            """,
            [self.pk],
        )
        return list(below)

    @property
    def is_pdf(self) -> bool:
        """A file of a PDF; any other file is an image."""
        return self.kind == Node.Kind.FILE and self.blob.media_type == store.PDF

    def is_live(self, ancestry: list[Node] | None = None) -> bool:
        return all(node.trashed_at is None for node in ancestry or self.ancestry())

    def tabs_in_order(self) -> list[Tab]:
        return depth_first(
            self.tabs.order_by("position"), lambda tab: tab.id, lambda tab: tab.parent_id
        )


def depth_first[T](items: Iterable[T], key: Callable[[T], object], parent: Callable[[T], object]):
    """Depth first, siblings in the order given: the order a tab list shows them."""
    children = defaultdict(list)
    for item in items:
        children[parent(item)].append(item)

    def walk(of):
        for item in children[of]:
            yield item
            yield from walk(key(item))

    return list(walk(None))


class Tab(models.Model):
    """A chapter of a document. Its content is the Yjs state of its room; restoring a
    version moves it to a fresh room, so a browser still holding the replaced
    content cannot merge it back."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="tabs")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="children"
    )
    title = models.CharField(max_length=200, blank=True)
    position = models.PositiveIntegerField()
    room = models.UUIDField(default=uuid.uuid4, unique=True)
    derived_at = models.DateTimeField(null=True, blank=True)
    # What its elements were numbered by, to tell whether a change of the document's own
    # state numbers them anew.
    numbered_by = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["document", "position"]),
            GinIndex(Words("title"), name="tab_title_words"),
            GinIndex(OpClass(Folded("title"), name="gin_trgm_ops"), name="tab_title_trigrams"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(pk=models.F("parent")), name="tab_is_not_its_own_parent"
            ),
        ]

    def __str__(self) -> str:
        return self.title or str(self.pk)


class Favourite(models.Model):
    """A node one user keeps at hand. It is theirs alone, as a shared document is the same for all
    who hold it."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="favourites"
    )
    node = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="favourites")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "node"], name="one_favourite_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.node_id}"


class BoardEntry(models.Model):
    """A document of JSON a board keeps (D36-2), by collection and key."""

    node = models.ForeignKey(Node, on_delete=models.DB_CASCADE, related_name="board_entries")
    collection = models.CharField(max_length=200)
    key = models.CharField(max_length=200)
    data = models.JSONField(default=dict)
    # Moves with each write, so that a write can refuse a document that moved on since it read it.
    version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    agent = models.CharField(max_length=200, blank=True)
    words = models.GeneratedField(
        expression=Words(Func(models.F("data"), function="board_text", output_field=TextField())),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["node", "collection", "key"], name="one_board_entry_per_key"
            )
        ]
        indexes = [GinIndex(fields=["words"], name="board_entry_words")]

    def __str__(self) -> str:
        return f"{self.node_id}: {self.collection}/{self.key}"
