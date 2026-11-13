from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.sessions.base_session import AbstractBaseSession
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **fields):
        fields.setdefault("is_staff", False)
        fields.setdefault("is_superuser", False)
        return self._create(email, password, **fields)

    def create_superuser(self, email, password=None, **fields):
        return self._create(email, password, **fields, is_staff=True, is_superuser=True)

    def _create(self, email, password, **fields):
        if not email:
            raise ValueError("email is required")
        user = self.model(email=email, **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class MemberManager(UserManager):
    """The installation's own people, without anyone visiting from outside (D39) or the shared
    mailboxes (S3-6)."""

    use_in_migrations = False

    def get_queryset(self):
        return super().get_queryset().filter(visitor=False, mailbox=False)


LANGUAGES = ("", "hr", "en")
THEMES = ("", "system", "light", "dark")
PAGE_THEMES = ("", "ponistra", "light", "dark")
SIGN_INS = ("", "password", "passkey")
# What a call does with the camera and the microphone (S2-9): the background left, blurred or
# replaced by a picture, the frame following the face, a dark picture lit, and the browser's own
# processing of the sound.
CALL = {
    "background": ("none", "soft", "strong", "petrol", "sage", "paper", "evening", "own"),
    "framing": (True, False),
    "light": (True, False),
    "noise": (True, False),
    "echo": (True, False),
    "gain": (True, False),
}


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    language = models.CharField(max_length=2, blank=True, default="")
    theme = models.CharField(max_length=6, blank=True, default="")
    projects_theme = models.CharField(max_length=8, blank=True, default="")
    meetings_theme = models.CharField(max_length=8, blank=True, default="")
    sign_in = models.CharField(max_length=8, blank=True, default="")
    call = models.JSONField(default=dict, blank=True)
    backdrop = models.ForeignKey(
        "blobs.Blob", null=True, blank=True, on_delete=models.DO_NOTHING, related_name="backdrops"
    )
    # Someone outside the installation who reads or edits what was shared with them by address
    # (D39): signed in only by their link, reached by no grant to everyone or a group.
    visitor = models.BooleanField(default=False)
    # A shared mailbox (S3-6): whom its accounts and mail belong to, signed in by no one, reached
    # by the colleagues the mail's grants name.
    mailbox = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    everyone = UserManager()
    objects = MemberManager()

    class Meta(AbstractUser.Meta):
        default_manager_name = "everyone"

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class Passkey(models.Model):
    user = models.ForeignKey(User, on_delete=models.DB_CASCADE, related_name="passkeys")
    credential = models.BinaryField(unique=True)
    public_key = models.BinaryField()
    sign_count = models.PositiveBigIntegerField(default=0)
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True)

    def __str__(self) -> str:
        return self.name


class AppPassword(models.Model):
    """A password a device's own app signs in with where it cannot use the browser's sign-in, such
    as a phone's contacts over CardDAV: random, shown once, kept only as its digest."""

    user = models.ForeignKey(User, on_delete=models.DB_CASCADE, related_name="app_passwords")
    name = models.CharField(max_length=150)
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True)

    def __str__(self) -> str:
        return self.name


class Session(AbstractBaseSession):
    """A signed-in browser: whose it is, what it told us it was, and when it was last seen. A
    session the server opens for its printer has no sign-in and is not listed."""

    user = models.ForeignKey(User, null=True, on_delete=models.DB_CASCADE, related_name="sessions")
    agent = models.CharField(max_length=300, blank=True)
    address = models.GenericIPAddressField(null=True)
    signed_in_at = models.DateTimeField(null=True)
    seen_at = models.DateTimeField(null=True)
    # The browser keeps documents to work without the network (D45), and empties itself once the
    # session ends.
    offline = models.BooleanField(default=False, db_default=False)

    @classmethod
    def get_session_store_class(cls):
        from .sessions import SessionStore

        return SessionStore


class Policy(models.Model):
    """How the installation's users sign in and share, in one row: whom it holds to passkeys and
    who may make a link for someone outside it (D39)."""

    class Passkeys(models.TextChoices):
        NOBODY = "nobody"
        ADMINISTRATORS = "administrators"
        EVERYONE = "everyone"

    class Outside(models.TextChoices):
        NOBODY = "nobody"
        ADMINISTRATORS = "administrators"
        EVERYONE = "everyone"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    passkeys = models.CharField(max_length=16, choices=Passkeys, default=Passkeys.EVERYONE)
    outside = models.CharField(
        max_length=16, choices=Outside, default=Outside.EVERYONE, db_default=Outside.EVERYONE
    )
    changed_by = models.ForeignKey(User, null=True, on_delete=models.DB_SET_NULL, related_name="+")
    changed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="one_policy")]

    def __str__(self) -> str:
        return self.passkeys

    def holds(self, user: User) -> bool:
        """Whether the user signs in with a passkey only."""
        return self.passkeys == Policy.Passkeys.EVERYONE or (
            self.passkeys == Policy.Passkeys.ADMINISTRATORS and user.is_staff
        )

    def links_outside(self, user: User) -> bool:
        """Whether the user may make a link for someone outside the installation."""
        return self.outside == Policy.Outside.EVERYONE or (
            self.outside == Policy.Outside.ADMINISTRATORS and user.is_staff
        )
