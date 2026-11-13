"""The vault (D20): the passwords people use, end to end encrypted. The server keeps only what
browsers sealed, so it opens no vault, and since a collection's key reaches a member only sealed
by someone who holds it, it lets nobody in either."""

import uuid

from django.conf import settings
from django.db import models

from apps.access.models import Role

USER = settings.AUTH_USER_MODEL


class Vault(models.Model):
    """A user's key pair. The private key is sealed with the vault key, which the password, the
    recovery code and each passkey that unlocks the vault wrap in turn."""

    user = models.OneToOneField(
        USER, primary_key=True, on_delete=models.DB_CASCADE, related_name="vault"
    )
    public_key = models.BinaryField()
    private_key = models.BinaryField()
    # Argon2id's salt and costs, which turn the password into the key that opens by_password.
    kdf = models.JSONField()
    by_password = models.BinaryField()
    by_code = models.BinaryField()
    # The recovery code, sealed with the vault key, so that an unlocked vault shows it again.
    code = models.BinaryField()
    # The vault key wrapped with the one-time code an administrator handed over, until the user
    # sets a new password with it.
    handed = models.BinaryField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.user)


class Unlock(models.Model):
    """A passkey that unlocks the vault: what its PRF gives for this salt wraps the vault key."""

    passkey = models.OneToOneField(
        "users.Passkey", primary_key=True, on_delete=models.DB_CASCADE, related_name="unlock"
    )
    salt = models.BinaryField()
    wrapped = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.passkey)


class Collection(models.Model):
    class Kind(models.TextChoices):
        PERSONAL = "personal"
        SHARED = "shared"
        COMPANY = "company"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind)
    name = models.CharField(max_length=200, blank=True)
    # Whose own vault this is; only a personal collection has one.
    owner = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    created_by = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind="personal", owner__isnull=False)
                | (~models.Q(kind="personal") & models.Q(owner__isnull=True)),
                name="personal_has_owner",
            ),
            models.UniqueConstraint(
                fields=["owner"], condition=models.Q(kind="personal"), name="one_personal"
            ),
        ]

    def __str__(self) -> str:
        return self.name or f"{self.owner}"


class Member(models.Model):
    """A role in a shared or company collection, for a user, a group or everyone (neither)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, on_delete=models.DB_CASCADE, related_name="members")
    user = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    group = models.ForeignKey(
        "auth.Group", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    role = models.CharField(max_length=8, choices=Role)
    created_by = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=True) | models.Q(group__isnull=True),
                name="member_has_one_grantee",
            ),
            models.UniqueConstraint(
                fields=["collection", "user", "group"],
                nulls_distinct=False,
                name="one_member_per_grantee",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user or self.group or 'everyone'}: {self.role} in {self.collection_id}"


class Key(models.Model):
    """A collection's key sealed to one user's public key. A member without one waits for an owner
    who holds it to confirm them."""

    collection = models.ForeignKey(Collection, on_delete=models.DB_CASCADE, related_name="keys")
    user = models.ForeignKey(USER, on_delete=models.DB_CASCADE, related_name="+")
    sealed = models.BinaryField()
    confirmed_by = models.ForeignKey(
        USER, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["collection", "user"], name="one_key")]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.collection_id}"


class Folder(models.Model):
    """A folder in a collection, its name sealed with the collection's key. Deleting one takes its
    folders with it and leaves their items at the top of the collection."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, on_delete=models.DB_CASCADE, related_name="folders")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.DB_CASCADE, related_name="children"
    )
    name = models.BinaryField()
    created_by = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.pk)


class Item(models.Model):
    """A login or a note. Its contents are sealed with a key of its own, which the collection's key
    wraps, so that it moves to another collection without being sealed anew."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, on_delete=models.DB_CASCADE, related_name="items")
    folder = models.ForeignKey(
        Folder, null=True, blank=True, on_delete=models.DB_SET_NULL, related_name="items"
    )
    key = models.BinaryField()
    data = models.BinaryField()
    created_by = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    updated_by = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    trashed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return str(self.pk)


class Attachment(models.Model):
    """A file kept with an item, sealed with the item's key, as its name is."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.DB_CASCADE, related_name="attachments")
    blob = models.ForeignKey("blobs.Blob", on_delete=models.DO_NOTHING, related_name="vaulted")
    meta = models.BinaryField()
    created_by = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.pk)


class Recovery(models.Model):
    """The company's recovery key while the policy holds every vault to it; no row while it is
    off."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    public_key = models.BinaryField()
    created_by = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_recovery")]

    def __str__(self) -> str:
        return str(self.created_at)


class Holder(models.Model):
    """The recovery key's private half sealed to one administrator."""

    user = models.OneToOneField(
        USER, primary_key=True, on_delete=models.DB_CASCADE, related_name="holder"
    )
    recovery = models.ForeignKey(Recovery, on_delete=models.DB_CASCADE, related_name="holders")
    sealed = models.BinaryField()
    confirmed_by = models.ForeignKey(
        USER, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.user)


class Escrow(models.Model):
    """A vault key sealed to the company's recovery key."""

    user = models.OneToOneField(
        USER, primary_key=True, on_delete=models.DB_CASCADE, related_name="escrow"
    )
    recovery = models.ForeignKey(Recovery, on_delete=models.DB_CASCADE, related_name="escrows")
    sealed = models.BinaryField()
    at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.user)


class Event(models.Model):
    """What happened in a collection, which its owners read, or to a vault, which its user reads.
    An opening and a password seen are logged once an hour at most."""

    class Kind(models.TextChoices):
        OPENED = "opened"
        SEEN = "seen"
        SHARED = "shared"
        CONFIRMED = "confirmed"
        EXPORTED = "exported"
        RECOVERED = "recovered"

    collection = models.ForeignKey(
        Collection, null=True, on_delete=models.DB_CASCADE, related_name="+"
    )
    item = models.ForeignKey(Item, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    user = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    # Who was confirmed, or whose vault was recovered.
    subject = models.ForeignKey(USER, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    kind = models.CharField(max_length=16, choices=Kind)
    # Who was given a role and which, or which field of the item was seen.
    detail = models.JSONField(default=dict)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["collection", "-at"]),
            models.Index(fields=["subject", "-at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.kind}"
