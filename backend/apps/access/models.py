import uuid

from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    READ = "read"
    EDIT = "edit"
    OWN = "own"


RANK = {Role.READ: 1, Role.EDIT: 2, Role.OWN: 3}


class Grant(models.Model):
    """A role on a node and everything below it, for a user, a group, or everyone
    (neither). Grants only add, so a node's audience is its own grants plus its
    ancestors'."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="grants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_CASCADE,
        related_name="grants",
    )
    group = models.ForeignKey(
        "auth.Group", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="grants"
    )
    role = models.CharField(max_length=8, choices=Role)
    # Whether what it reaches may leave PONISTRA: download, export and print (D20, D39).
    download = models.BooleanField(default=True)
    # The personal link of someone outside it was given to by address, which signs them in (D39).
    key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    # The link of the mail's recipients a recipient came in by: it ends with the link.
    link = models.ForeignKey(
        "OutsideLink", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="grants"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=True) | models.Q(group__isnull=True),
                name="grant_has_one_grantee",
            ),
            models.UniqueConstraint(
                fields=["node", "user", "group"],
                nulls_distinct=False,
                name="one_grant_per_grantee",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user or self.group or 'everyone'}: {self.role} on {self.node_id}"


class OutsideLink(models.Model):
    """A node that whoever holds this link reaches without an account of the installation (D39):
    anyone reads it as it is now, the recipients of a mail each come in under their own name once
    a code to their address shows who they are, or anyone puts files into a folder. The token is
    kept as it is, for its owner to copy again: the database that could give it away holds the
    node itself."""

    class Kind(models.TextChoices):
        OPEN = "open"
        PEOPLE = "people"
        UPLOAD = "upload"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=8, choices=Kind, default=Kind.OPEN)
    role = models.CharField(max_length=8, choices=Role, default=Role.READ)
    download = models.BooleanField(default=True)
    # Those a link of the PEOPLE kind lets in, by address.
    addresses = models.JSONField(default=list)
    # Whom anyone who opens a link of the OPEN kind is signed in as, made at its first opening.
    visitor = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.DB_SET_NULL,
        related_name="opened_link",
    )
    node = models.ForeignKey(
        "documents.Node", on_delete=models.DB_CASCADE, related_name="outside_links"
    )
    token = models.CharField(max_length=64, unique=True)
    password = models.CharField(max_length=256, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(default=0)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"link {self.pk} to {self.node_id}"


class Code(models.Model):
    """A code sent to one of a link's addresses, which lets its holder in under that address."""

    link = models.ForeignKey(OutsideLink, on_delete=models.DB_CASCADE, related_name="codes")
    address = models.EmailField()
    digest = models.CharField(max_length=256)
    sent_at = models.DateTimeField(auto_now_add=True)
    tries = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["link", "address"], name="one_code_per_address")
        ]

    def __str__(self) -> str:
        return f"code for {self.address} on {self.link_id}"


class Access(models.Model):
    """Who opened, downloaded or shared a node, and when; an opening once an hour at most."""

    class Kind(models.TextChoices):
        OPENED = "opened"
        DOWNLOADED = "downloaded"
        SHARED = "shared"
        UPLOADED = "uploaded"

    node = models.ForeignKey("documents.Node", on_delete=models.DB_CASCADE, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=16, choices=Kind)
    # The format downloaded, who the node was shared with and as what, the outside link used, or
    # the file put into the folder through it and the name its sender gave.
    detail = models.JSONField(default=dict)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["node", "-at"])]

    def __str__(self) -> str:
        return f"{self.user_id} {self.kind} {self.node_id}"
