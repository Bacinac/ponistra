from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models.functions import Coalesce

from apps.access.models import Role as AccessRole
from apps.search.text import Folded, MailWords, TranslationWords


class Security(models.TextChoices):
    TLS = "tls"
    STARTTLS = "starttls"
    # Only towards a host the installation names in PONISTRA_MAIL_PLAIN_HOSTS: the test server.
    NONE = "none"


class Provider(models.TextChoices):
    """The providers whose accounts sign in through OAuth with the installation's own client."""

    GOOGLE = "google"
    MICROSOFT = "microsoft"


class Account(models.Model):
    """A mailbox the user already has at a provider (D15). The provider carries mail in and out:
    each message is taken from it whole once, and what PONISTRA keeps stays the user's when the
    account goes."""

    class Protocol(models.TextChoices):
        IMAP = "imap"
        # Exchange, HCL Traveler and the others phones sync with, where IMAP is not let out.
        ACTIVESYNC = "activesync"

    class Login(models.TextChoices):
        PASSWORD = "password"
        GOOGLE = Provider.GOOGLE.value
        MICROSOFT = Provider.MICROSOFT.value

    class State(models.TextChoices):
        SYNCING = "syncing"
        READY = "ready"
        FAILED = "failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_accounts"
    )
    address = models.EmailField()
    # The name recipients see on its mail; the label is what the interface calls the account.
    name = models.CharField(max_length=150, blank=True)
    label = models.CharField(max_length=200, blank=True)
    username = models.CharField(max_length=320)
    # Its password, or the refresh token of an account that signs in through OAuth, sealed.
    secret = models.BinaryField()
    login = models.CharField(max_length=9, choices=Login, default=Login.PASSWORD)
    protocol = models.CharField(max_length=10, choices=Protocol, default=Protocol.IMAP)
    imap_host = models.CharField(max_length=253, blank=True)
    imap_port = models.PositiveIntegerField(null=True)
    imap_security = models.CharField(max_length=8, choices=Security, blank=True)
    smtp_host = models.CharField(max_length=253, blank=True)
    smtp_port = models.PositiveIntegerField(null=True)
    smtp_security = models.CharField(max_length=8, choices=Security, blank=True)
    activesync_host = models.CharField(max_length=253, blank=True)
    # The account's device on the ActiveSync server, the key of the policy it took there and
    # where its last FolderSync left the folder list.
    device = models.CharField(max_length=32, blank=True)
    policy_key = models.CharField(max_length=20, blank=True)
    folder_key = models.CharField(max_length=64, blank=True)
    # The account's place in the interface's palette of account colours, wrapping past its end.
    color = models.PositiveSmallIntegerField(default=0)
    # The account a new message goes from where the user has not chosen one.
    default = models.BooleanField(default=False)
    # Whether its mail shows in the folders every account shares; it is taken either way.
    together = models.BooleanField(default=True)
    state = models.CharField(max_length=8, choices=State, default=State.SYNCING)
    error = models.CharField(max_length=40, blank=True)
    synced_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "address"], name="mail_account_once"),
            models.UniqueConstraint(
                fields=["owner"], condition=models.Q(default=True), name="mail_account_default"
            ),
        ]

    def __str__(self) -> str:
        return self.address


class Grant(models.Model):
    """A role in a shared mailbox (S3-6) for a colleague, a group, or everyone (neither): reading
    its mail, also acting on it and sending from its accounts, or also changing its accounts and
    whom it is shared with. The mailbox is a user of its own, whom no one signs in as."""

    mailbox = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_shared"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_CASCADE,
        related_name="mail_grants",
    )
    group = models.ForeignKey(
        "auth.Group", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="mail_grants"
    )
    role = models.CharField(max_length=8, choices=AccessRole)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=True) | models.Q(group__isnull=True),
                name="mail_grant_has_one_grantee",
            ),
            models.UniqueConstraint(
                fields=["mailbox", "user", "group"],
                nulls_distinct=False,
                name="mail_grant_once",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id or self.group_id or 'everyone'}: {self.role} in {self.mailbox_id}"


class Signature(models.Model):
    """What closes the user's mail, under a new message and above what a reply quotes: the one
    every account takes, or an account's own in its place, empty for none. HTML as the composer
    writes it, made safe the same way."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_signatures"
    )
    account = models.OneToOneField(
        Account, null=True, on_delete=models.DB_CASCADE, related_name="own_signature"
    )
    html = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner"], condition=models.Q(account=None), name="mail_signature_shared"
            )
        ]

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.account_id}"


class SignatureImage(models.Model):
    """An image a signature shows, its bytes kept while the signature has it."""

    signature = models.ForeignKey(Signature, on_delete=models.DB_CASCADE, related_name="images")
    blob = models.ForeignKey("blobs.Blob", on_delete=models.DO_NOTHING, related_name="signed")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["signature", "blob"], name="mail_signature_image_once")
        ]

    def __str__(self) -> str:
        return self.blob_id


class Role(models.TextChoices):
    INBOX = "inbox"
    # Where a message waits for the moment it comes back (D40), PONISTRA's own: no provider has it.
    SNOOZED = "snoozed"
    SENT = "sent"
    DRAFTS = "drafts"
    ARCHIVE = "archive"
    JUNK = "junk"
    TRASH = "trash"


class Priority(models.IntegerChoices):
    """How important the sender marked a message, by ActiveSync's values."""

    LOW = 0
    NORMAL = 1
    HIGH = 2


class Folder(models.Model):
    """A folder of the user's one tree: each role once, whichever accounts the mail came to, and
    a provider's other folders under the node named after their account."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_folders"
    )
    parent = models.ForeignKey(
        "self", null=True, on_delete=models.DB_CASCADE, related_name="children"
    )
    name = models.CharField(max_length=1000)
    role = models.CharField(max_length=7, choices=Role, blank=True)
    # The node an account's own folders are under; it stays, named, once the account goes.
    account = models.OneToOneField(
        Account, null=True, on_delete=models.DB_SET_NULL, related_name="node"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "parent", "name"], nulls_distinct=False, name="mail_folder_once"
            ),
            models.UniqueConstraint(
                fields=["owner", "role"], condition=~models.Q(role=""), name="mail_role_once"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Source(models.Model):
    """A folder at the provider, with how far its mail has been taken. IMAP: every UID from `low`
    to `high`, the first taking going down from the newest; ActiveSync: its key."""

    class Kind(models.TextChoices):
        INBOX = "inbox"
        SENT = "sent"
        DRAFTS = "drafts"
        ARCHIVE = "archive"
        JUNK = "junk"
        TRASH = "trash"
        # Gmail's All Mail: what no other of its labels holds is archived.
        ALL = "all"

    account = models.ForeignKey(Account, on_delete=models.DB_CASCADE, related_name="sources")
    name = models.CharField(max_length=1000)
    delimiter = models.CharField(max_length=1, blank=True)
    kind = models.CharField(max_length=7, choices=Kind, blank=True)
    folder = models.ForeignKey(Folder, on_delete=models.DB_CASCADE, related_name="sources")
    uidvalidity = models.PositiveBigIntegerField(null=True)
    low = models.PositiveBigIntegerField(null=True)
    high = models.PositiveBigIntegerField(null=True)
    # ActiveSync's own: the folder's id and its parent's, and where its last Sync left it.
    server_id = models.CharField(max_length=64, blank=True)
    parent = models.CharField(max_length=64, blank=True)
    sync_key = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            # Deferred: an ActiveSync FolderSync may hand two folders each other's names.
            models.UniqueConstraint(
                fields=["account", "name"],
                name="mail_source_once",
                deferrable=models.Deferrable.DEFERRED,
            )
        ]

    def __str__(self) -> str:
        return self.name


class Sealed(models.TextChoices):
    SIGNED = "signed"
    ENCRYPTED = "encrypted"


class Message(models.Model):
    """A message of the user's, however many of their accounts it came to: its envelope, flags
    and text, and the whole of it in the blob store, its attachments cut out into blobs of their
    own (`mime.cut`)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_messages"
    )
    folder = models.ForeignKey(Folder, on_delete=models.DO_NOTHING, related_name="messages")
    # The account it came to first, whose colour it shows, and the one a reply goes from.
    account = models.ForeignKey(
        Account, null=True, on_delete=models.DB_SET_NULL, related_name="messages"
    )
    # The same message delivered to another account or folder: its Message-ID with its subject,
    # the same wherever it is delivered, or the hash of its bytes where it has no Message-ID.
    key = models.CharField(max_length=64)
    raw = models.ForeignKey("blobs.Blob", on_delete=models.DO_NOTHING, related_name="mail")
    message_id = models.CharField(max_length=998, blank=True)
    in_reply_to = models.CharField(max_length=998, blank=True)
    # The thread's Message-IDs, oldest first, as the References header gives them.
    references = models.TextField(blank=True)
    subject = models.TextField(blank=True)
    sender = models.JSONField(default=dict)
    to = models.JSONField(default=list)
    cc = models.JSONField(default=list)
    reply_to = models.JSONField(default=list)
    date = models.DateTimeField()
    size = models.PositiveIntegerField(default=0)
    attachments = models.BooleanField(default=False)
    text = models.TextField(blank=True)
    preview = models.CharField(max_length=200, blank=True)
    seen = models.BooleanField(default=False)
    flagged = models.BooleanField(default=False)
    answered = models.BooleanField(default=False)
    priority = models.PositiveSmallIntegerField(choices=Priority, default=Priority.NORMAL)
    # What the message is made of (`taking.fingerprint`): its copies where a provider gives no
    # Message-ID to know them by, as HCL Traveler does, are the same message by it.
    fingerprint = models.CharField(max_length=64, blank=True)
    # When its owner first opened it, which the sender of a colleague's message sees.
    opened_at = models.DateTimeField(null=True)
    # The emoji the message reacts with (`reactions`), and the message it reacts to while the
    # owner has that one; `in_reply_to` then holds its Message-ID alone.
    reaction = models.CharField(max_length=32, blank=True)
    reacts_to = models.ForeignKey(
        "self", null=True, on_delete=models.DB_SET_NULL, related_name="reactions"
    )
    # Set while it is put away, and when it last came back to the top of the inbox (`snoozing`).
    snoozed_until = models.DateTimeField(null=True)
    returned_at = models.DateTimeField(null=True)
    # The date by which a message sent expects an answer, and whether it came back without one.
    awaited_until = models.DateTimeField(null=True)
    unanswered = models.BooleanField(default=False)
    automatic = models.BooleanField(default=False)
    # Whether it travels signed or encrypted (`sealing`), which only the browser can check or open.
    sealed = models.CharField(max_length=9, choices=Sealed, blank=True)
    # Where a list sorted by date shows it: by the moment it came back, not by its own date.
    placed = models.GeneratedField(
        expression=Coalesce("returned_at", "date"),
        output_field=models.DateTimeField(),
        db_persist=True,
    )
    words = models.GeneratedField(
        expression=MailWords("subject", "sender", "to", "cc", "text"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "key"], name="mail_message_once"),
        ]
        indexes = [
            models.Index(fields=["folder", "-placed", "-id"], name="mail_message_placed"),
            models.Index(
                fields=["snoozed_until"],
                condition=models.Q(snoozed_until__isnull=False),
                name="mail_message_snoozed",
            ),
            models.Index(
                fields=["awaited_until"],
                condition=models.Q(awaited_until__isnull=False),
                name="mail_message_awaited",
            ),
            models.Index(fields=["folder"], condition=models.Q(seen=False), name="mail_unseen"),
            models.Index(fields=["key"], name="mail_message_key"),
            models.Index(fields=["owner", "message_id"], name="mail_message_id"),
            models.Index(
                fields=["owner", "in_reply_to"],
                condition=models.Q(reacts_to=None) & ~models.Q(reaction=""),
                name="mail_reaction_waiting",
            ),
            models.Index(fields=["fingerprint", "date"], name="mail_message_fingerprint"),
            GinIndex(fields=["words"], name="mail_message_words"),
            GinIndex(OpClass(Folded("subject"), name="gin_trgm_ops"), name="mail_subject_trigrams"),
        ]

    def __str__(self) -> str:
        return self.subject


class Opening(models.Model):
    """When a colleague sharing a mailbox first opened one of its messages, which the sender of a
    colleague's message sees (S3-6)."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="openings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_openings"
    )
    at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "user"], name="mail_opening_once"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.message_id}"


class Key(models.Model):
    """A certificate or public key that encrypts mail to an address and checks its signatures:
    one of the user's own, which colleagues encrypt to as well, or one met on a signed message.
    The private keys live only in the vault."""

    class Kind(models.TextChoices):
        SMIME = "smime"
        PGP = "pgp"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_keys"
    )
    kind = models.CharField(max_length=5, choices=Kind)
    address = models.CharField(max_length=320)
    fingerprint = models.CharField(max_length=64)
    # A certificate in DER, or an OpenPGP public key in its binary form.
    data = models.BinaryField()
    own = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True)
    seen_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "kind", "address", "fingerprint"], name="mail_key_once"
            ),
        ]
        indexes = [models.Index(fields=["address", "kind"], name="mail_key_address")]

    def __str__(self) -> str:
        return f"{self.kind} {self.address}"


class Translation(models.Model):
    """A message written by the model in a language its owner reads (D35): its subject, each of
    its blocks by what the block says in the original (`translating.blocks`), so that it is put
    back into the message however its images are shown, and its text for the search."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="translations")
    language = models.CharField(max_length=3)
    subject = models.TextField(blank=True)
    blocks = models.JSONField(default=dict)
    text = models.TextField(blank=True)
    run = models.ForeignKey(
        "actions.ActionRun", null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    made_at = models.DateTimeField(auto_now_add=True)
    words = models.GeneratedField(
        expression=TranslationWords("subject", "text"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "language"], name="mail_translated_once"),
        ]
        indexes = [GinIndex(fields=["words"], name="mail_translation_words")]

    def __str__(self) -> str:
        return f"{self.message_id} {self.language}"


class Arrival(models.Model):
    """The message as a folder at the provider holds it, under its UID or the item id ActiveSync
    gives it: where old mail is deleted from the provider."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="arrivals")
    source = models.ForeignKey(Source, on_delete=models.DB_CASCADE, related_name="arrivals")
    uid = models.PositiveBigIntegerField(null=True)
    item = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "uid"], name="mail_arrival_once"),
            models.UniqueConstraint(
                fields=["source", "item"], condition=~models.Q(item=""), name="mail_item_once"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source} {self.uid or self.item}"


class Attachment(models.Model):
    """A file the message carries, or an image its HTML shows, by its IMAP part number. Where
    `offset` is set its bytes were cut out of the message's blob at that offset, as base64 in
    lines of `line` letters ending in `newline`, and go back there to make the message whole."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="files")
    blob = models.ForeignKey("blobs.Blob", on_delete=models.DO_NOTHING, related_name="mailed")
    part = models.CharField(max_length=100)
    name = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=255)
    cid = models.CharField(max_length=998, blank=True)
    inline = models.BooleanField(default=False)
    offset = models.PositiveBigIntegerField(null=True)
    line = models.PositiveIntegerField(null=True)
    newline = models.CharField(max_length=2, blank=True)
    # Whether the last line ends in `newline` too.
    ended = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "part"], name="mail_attachment_once"),
        ]

    def __str__(self) -> str:
        return self.name


class Fetched(models.Model):
    """An image from elsewhere that a message's HTML shows, fetched once by PONISTRA when its
    reader let the images in, by the SHA-256 of its address. Without a blob, the server answered
    with nothing to show, and is not asked again."""

    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="fetched")
    key = models.CharField(max_length=64)
    blob = models.ForeignKey(
        "blobs.Blob", null=True, on_delete=models.DO_NOTHING, related_name="fetched"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "key"], name="mail_fetched_once"),
        ]

    def __str__(self) -> str:
        return self.key


class Decided(models.Model):
    """A domain whose senders' images the user decided on once: shown, or kept out, without
    asking."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_decided"
    )
    domain = models.CharField(max_length=253)
    shown = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "domain"], name="mail_decided_once"),
        ]

    def __str__(self) -> str:
        return self.domain


class Rule(models.Model):
    """Where the mail of a sender goes, named by their address or by a domain they write from:
    to Junk, which blocks them, or to a folder of the user's."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_rules"
    )
    # An address, or a domain, which takes its subdomains in too.
    sender = models.CharField(max_length=320)
    folder = models.ForeignKey(Folder, on_delete=models.DB_CASCADE, related_name="rules")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "sender"], name="mail_rule_once"),
        ]

    def __str__(self) -> str:
        return self.sender


class Deleted(models.Model):
    """A message the user deleted for good, by its key and what it is made of, so that a provider
    which gives a folder out again from nothing does not bring it back."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_deleted"
    )
    key = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64, blank=True)
    date = models.DateTimeField(null=True)
    # Whether it had a Message-ID to know its copies by.
    keyed = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "key"], name="mail_deleted_once"),
        ]

    def __str__(self) -> str:
        return self.key


class Client(models.Model):
    """The installation's registration with a provider, which its administrator makes there and
    enters here: the client ID, and its secret sealed, of which only the last four characters are
    shown again."""

    provider = models.CharField(max_length=9, choices=Provider, primary_key=True)
    client_id = models.CharField(max_length=255)
    secret = models.BinaryField()
    hint = models.CharField(max_length=4)
    # Microsoft's secrets end on a date set when they are made; Google's do not.
    expires = models.DateField(null=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.provider


class Named(models.Model):
    """A person as HCL Traveler names one inside a Domino organisation, `Ana Horvat/Firma`, with
    the address the directory of its server gives them; none where it did not know them when last
    asked."""

    host = models.CharField(max_length=253)
    name = models.CharField(max_length=998)
    address = models.EmailField(blank=True)
    asked_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["host", "name"], name="mail_named_once"),
        ]

    def __str__(self) -> str:
        return self.name


class Correspondent(models.Model):
    """Someone the user's mail was written to or by, kept apart from contacts, as Google keeps its
    Other contacts, to complete addresses while the user writes: once noted, they stay, whatever
    becomes of the mail."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_correspondents"
    )
    address = models.EmailField()
    name = models.CharField(max_length=998, blank=True)
    # Messages the user wrote to them, and messages they wrote to the user.
    written = models.PositiveIntegerField(default=0)
    heard = models.PositiveIntegerField(default=0)
    last = models.DateTimeField()
    # The account the user last wrote to them from, and the one they last wrote to: a new message
    # to them goes from the first, else the second.
    sent_from = models.ForeignKey(
        Account, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    reached = models.ForeignKey(Account, null=True, on_delete=models.DB_SET_NULL, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "address"], name="mail_correspondent_once"),
        ]

    def __str__(self) -> str:
        return self.address


class Setting(models.Model):
    """The installation's mail, in one row: whether the sender of a message sees which of their
    colleagues opened it, and when."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    opened = models.BooleanField(default=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_mail_setting")]

    def __str__(self) -> str:
        return str(self.opened)


class Draft(models.Model):
    """A reply or forward an outside agent drafted for the user to send (D18): the user opens it
    in the composer over the message, reads it, and sends or drops it; nothing goes out by the
    agent's hand."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_drafts"
    )
    message = models.ForeignKey(Message, on_delete=models.DB_CASCADE, related_name="drafts")
    way = models.CharField(max_length=7)
    text = models.TextField()
    grant = models.ForeignKey(
        "agents.Grant", null=True, blank=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.way} to {self.message_id}"


class Unsent(models.Model):
    """A message the user began and has not sent, kept as they left the composer so they go on
    with it later, or waiting for the moment they chose for it to leave (D40). It stays in
    PONISTRA: nothing PONISTRA does to the mail reaches the servers' folders, and an ActiveSync
    server before 16.0 takes no drafts at all."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="mail_unsent"
    )
    # None once the account it was to go from is removed: what was written stays the user's.
    account = models.ForeignKey(
        Account, null=True, on_delete=models.DB_SET_NULL, related_name="unsent"
    )
    # The composer's fields as the send request carries them, but the account.
    written = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)
    send_at = models.DateTimeField(null=True)
    # Set while it is being handed to the provider: it may have left, so it is never tried again
    # by itself, and a restart that cuts it off leaves the user to decide (`later.interrupted`).
    sending = models.BooleanField(default=False)
    # Why it did not leave at its time, as the code a request would have been refused with.
    failed = models.CharField(max_length=40, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["owner", "-updated_at"], name="mail_unsent_latest"),
            models.Index(
                fields=["send_at"],
                condition=models.Q(send_at__isnull=False, sending=False, failed=""),
                name="mail_unsent_due",
            ),
        ]

    def __str__(self) -> str:
        return self.written.get("subject", "")


class UnsentFile(models.Model):
    """A file or image an unsent message carries, its bytes kept for as long as it waits."""

    unsent = models.ForeignKey(Unsent, on_delete=models.DB_CASCADE, related_name="held")
    blob = models.ForeignKey("blobs.Blob", on_delete=models.DO_NOTHING, related_name="unsent")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["unsent", "blob"], name="mail_unsent_file_once")
        ]

    def __str__(self) -> str:
        return self.blob_id


class Away(models.Model):
    """The user's time away: PONISTRA answers from their accounts, and their colleagues see it."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="away"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    text_hr = models.TextField(blank=True)
    text_en = models.TextField(blank=True)
    # Why the last answer did not leave, until one does.
    failed = models.CharField(max_length=40, blank=True)

    def __str__(self) -> str:
        return f"{self.owner_id}: {self.starts_at} - {self.ends_at}"


class AwayAnswer(models.Model):
    """The answer of the period to one sender: `due` until it has been tried, and kept after so
    that the sender is not answered twice."""

    away = models.ForeignKey(Away, on_delete=models.DB_CASCADE, related_name="answers")
    address = models.CharField(max_length=320)
    message = models.ForeignKey(Message, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    due = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["away", "address"], name="mail_away_answer_once")
        ]
        indexes = [
            models.Index(fields=["id"], condition=models.Q(due=True), name="mail_away_answer_due")
        ]

    def __str__(self) -> str:
        return self.address
