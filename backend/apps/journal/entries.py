from datetime import timedelta

from django.utils import timezone

from apps.users import sessions

from .models import Entry

Kind = Entry.Kind
KEPT = timedelta(days=365)
AGENT = 300

# What the administrator narrows the journal to.
GROUPS: dict[str, tuple[str, ...]] = {
    "sign_ins": (
        Kind.SIGNED_IN,
        Kind.SIGN_IN_FAILED,
        Kind.LOCKED_OUT,
        Kind.SIGNED_OUT,
        Kind.SESSIONS_ENDED,
        Kind.APPLICATION_SIGNED_IN,
    ),
    "accounts": (
        Kind.INSTALLED,
        Kind.USER_ADDED,
        Kind.USER_CHANGED,
        Kind.USER_ERASED,
        Kind.GROUP_ADDED,
        Kind.GROUP_RENAMED,
        Kind.GROUP_REMOVED,
        Kind.PASSWORD_CHANGED,
        Kind.PASSKEY_ADDED,
        Kind.PASSKEY_REMOVED,
        Kind.APP_PASSWORD_ADDED,
        Kind.APP_PASSWORD_REMOVED,
    ),
    "settings": (
        Kind.POLICY_CHANGED,
        Kind.SETTING_CHANGED,
        Kind.APPLICATION_ADDED,
        Kind.APPLICATION_CHANGED,
        Kind.APPLICATION_REMOVED,
        Kind.APPLICATION_SECRET,
        Kind.PROVIDER_ADDED,
        Kind.PROVIDER_CHANGED,
        Kind.PROVIDER_REMOVED,
        Kind.PROVIDER_SECRET,
    ),
    "health": (Kind.PROBLEM, Kind.RESOLVED),
}

# A person's own trail, which goes with them when they are erased; what an administrator did
# stays, without the name.
OWN = (
    Kind.SIGNED_IN,
    Kind.SIGN_IN_FAILED,
    Kind.LOCKED_OUT,
    Kind.SIGNED_OUT,
    Kind.SESSIONS_ENDED,
    Kind.PASSWORD_CHANGED,
    Kind.PASSKEY_ADDED,
    Kind.PASSKEY_REMOVED,
    Kind.APP_PASSWORD_ADDED,
    Kind.APP_PASSWORD_REMOVED,
    Kind.APPLICATION_SIGNED_IN,
)


def wrote(kind: str, *, request=None, actor=None, subject=None, **detail) -> Entry:
    """Writes what happened, by whom (the request's user unless named) and to whom."""
    if actor is None and request is not None and request.user.is_authenticated:
        actor = request.user
    return Entry.objects.create(
        kind=kind,
        actor=actor,
        subject=subject,
        address=request and sessions.address_of(request),
        detail=detail,
    )


def signed_in(request, way: str) -> None:
    Entry.objects.filter(at__lt=timezone.now() - KEPT).delete()
    wrote(
        Kind.SIGNED_IN,
        request=request,
        way=way,
        agent=request.META.get("HTTP_USER_AGENT", "")[:AGENT],
    )


def forgotten(user) -> None:
    """What the journal holds of a person who is erased: their own trail, and the failures
    under their address."""
    mine = Entry.objects.filter(kind__in=OWN)
    (mine.filter(actor=user) | mine.filter(subject=user)).delete()
    Entry.objects.filter(detail__email=user.email).delete()


def failed(sender, credentials: dict, request=None, **kwargs) -> None:
    """A failed sign-in, unless axes held it, which tells of it as locked out."""
    from apps.users.models import User

    if getattr(request, "axes_locked_out", False):
        return
    email = str(credentials.get("email") or credentials.get("username") or "").strip().lower()
    email = email[:254]
    wrote(
        Kind.SIGN_IN_FAILED,
        request=request,
        subject=User.everyone.filter(email=email).first(),
        email=email,
    )


def locked(sender, request=None, username: str = "", **kwargs) -> None:
    from apps.users.models import User

    email = str(username or "").strip().lower()[:254]
    wrote(
        Kind.LOCKED_OUT,
        request=request,
        subject=User.everyone.filter(email=email).first(),
        email=email,
    )


def signed_out(sender, request, user, **kwargs) -> None:
    if user is not None:
        wrote(Kind.SIGNED_OUT, request=request, actor=user)
