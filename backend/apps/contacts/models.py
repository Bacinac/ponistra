from django.conf import settings
from django.db import connection, models
from django.db.models import BigIntegerField, Func, Value

# Each change to an address book takes the next number, by which a phone asks what changed since.
REVISION = "contacts_revision"
LOCK = 0x5C21B10D


def revised() -> Func:
    return Func(Value(REVISION), function="nextval", output_field=BigIntegerField())


def ordered(*owner_ids: int) -> None:
    """Holds the owners' address books until the transaction ends. Numbers are taken in one
    order and committed in another, so without it a phone that read up to a number could have
    missed a smaller one committed after."""
    with connection.cursor() as cursor:
        for owner_id in sorted(set(owner_ids)):
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [LOCK, owner_id])


class Entry(models.Model):
    """A person as the directory of an organisation's ActiveSync server lists them (D15, S4):
    read and refreshed from it, never changed here. `listed` is whether it listed them when last
    asked, so an address it does not know is not asked again at once."""

    host = models.CharField(max_length=253)
    address = models.EmailField()
    listed = models.BooleanField(default=True)
    name = models.CharField(max_length=500, blank=True)
    given = models.CharField(max_length=200, blank=True)
    family = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=300, blank=True)
    company = models.CharField(max_length=300, blank=True)
    office = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=100, blank=True)
    home = models.CharField(max_length=100, blank=True)
    asked_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["host", "address"], name="contacts_entry_once"),
        ]

    def __str__(self) -> str:
        return self.address


class Contact(models.Model):
    """A person of the user's address book (D15, S4): one person once, whichever sources gave
    them. What it holds is the user's own; while the organisation's directory lists a colleague,
    their work details are read from it (`entry`)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="contacts"
    )
    uid = models.CharField(max_length=255)
    # The name of the contact's vCard in the address book a phone reads, which a phone may choose.
    href = models.CharField(max_length=255)
    name = models.CharField(max_length=500, blank=True)
    given = models.CharField(max_length=200, blank=True)
    family = models.CharField(max_length=200, blank=True)
    middle = models.CharField(max_length=200, blank=True)
    prefix = models.CharField(max_length=100, blank=True)
    suffix = models.CharField(max_length=100, blank=True)
    nickname = models.CharField(max_length=200, blank=True)
    organisation = models.CharField(max_length=300, blank=True)
    department = models.CharField(max_length=300, blank=True)
    title = models.CharField(max_length=300, blank=True)
    # ISO 8601, `--MM-DD` where the year is not known.
    birthday = models.CharField(max_length=10, blank=True)
    note = models.TextField(blank=True)
    photo = models.ForeignKey(
        "blobs.Blob", null=True, on_delete=models.DO_NOTHING, related_name="contacts"
    )
    # The photo drawn small as WebP, which the list carries itself instead of a request a name.
    avatar = models.BinaryField(null=True)
    # The vCard lines a phone gave that PONISTRA does not show, given back to it as they came.
    extra = models.JSONField(default=list)
    # A card standing for a group of contacts, as an iPhone keeps one: given back, not shown.
    group = models.BooleanField(default=False)
    starred = models.BooleanField(default=False)
    entry = models.ForeignKey(
        Entry, null=True, on_delete=models.DB_SET_NULL, related_name="contacts"
    )
    revision = models.BigIntegerField(db_default=revised())
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "uid"], name="contacts_contact_uid_once"),
            models.UniqueConstraint(fields=["owner", "href"], name="contacts_contact_href_once"),
        ]
        indexes = [models.Index(fields=["owner", "revision"])]

    def __str__(self) -> str:
        return self.name or self.uid


class Point(models.Model):
    """A way to reach the contact: an e-mail address, a phone number, a postal address or a web
    page. `key` is what tells one from another: an address in lower case, a number in E.164."""

    class Kind(models.TextChoices):
        EMAIL = "email"
        PHONE = "phone"
        ADDRESS = "address"
        URL = "url"

    contact = models.ForeignKey(Contact, on_delete=models.DB_CASCADE, related_name="points")
    kind = models.CharField(max_length=7, choices=Kind)
    # work, home, mobile, fax, pager, main or other; or the label a phone gave it.
    label = models.CharField(max_length=100, blank=True)
    value = models.TextField()
    # A postal address by its vCard parts: box, extended, street, city, region, code, country.
    parts = models.JSONField(default=list)
    key = models.CharField(max_length=320, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        indexes = [models.Index(fields=["kind", "key"])]

    def __str__(self) -> str:
        return self.value


class Taken(models.Model):
    """A contact as a source gave it (D15, S4), kept as it came, so each value's origin is known.
    An item is taken once: its row stays when the contact is deleted, so it does not come again."""

    class Kind(models.TextChoices):
        MICROSOFT = "microsoft"
        GOOGLE = "google"
        ACTIVESYNC = "activesync"
        DIRECTORY = "directory"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="contacts_taken"
    )
    contact = models.ForeignKey(
        Contact, null=True, on_delete=models.DB_SET_NULL, related_name="taken"
    )
    account = models.ForeignKey(
        "mail.Account", null=True, on_delete=models.DB_SET_NULL, related_name="contacts_taken"
    )
    kind = models.CharField(max_length=10, choices=Kind)
    # The account's address, or the directory's host, which stay when the account goes.
    source = models.CharField(max_length=320)
    item = models.CharField(max_length=500)
    data = models.JSONField(default=dict)
    taken_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "kind", "source", "item"], name="contacts_taken_once"
            ),
        ]

    def __str__(self) -> str:
        return self.item


class Book(models.Model):
    """An address book of a connected account at its provider, and how far its contacts are
    taken: an ActiveSync folder's sync key, a Graph folder's delta link. Graph's default folder
    has no id here."""

    account = models.ForeignKey(
        "mail.Account", on_delete=models.DB_CASCADE, related_name="contact_books"
    )
    server_id = models.CharField(max_length=500, blank=True)
    name = models.CharField(max_length=1000, blank=True)
    key = models.TextField(blank=True)
    error = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "server_id"], name="contacts_book_once"),
        ]

    def __str__(self) -> str:
        return self.name


class Directory(models.Model):
    """The directory of an ActiveSync account's server as the account reaches it, and when it was
    last gone through for the colleagues its owner met and the changes to those listed."""

    account = models.OneToOneField(
        "mail.Account", on_delete=models.DB_CASCADE, related_name="contact_directory"
    )
    passed_at = models.DateTimeField(null=True)
    error = models.CharField(max_length=40, blank=True)

    def __str__(self) -> str:
        return str(self.account_id)


class Gone(models.Model):
    """A contact deleted from the address book, by which a phone learns it went."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DB_CASCADE, related_name="contacts_gone"
    )
    href = models.CharField(max_length=255)
    revision = models.BigIntegerField(db_default=revised())

    class Meta:
        indexes = [models.Index(fields=["owner", "revision"])]

    def __str__(self) -> str:
        return self.href
