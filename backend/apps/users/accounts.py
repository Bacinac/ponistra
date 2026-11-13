import hmac

from django.conf import settings
from django.contrib.auth import login as start_session
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.access.models import Grant
from apps.access.rights import orphaned
from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.identity.models import Identity, Kept, Provider
from apps.journal import entries
from apps.journal.entries import Kind
from apps.vault.views import orphaned_by, settle

from . import erasure, sessions
from .models import Policy, User
from .views import policy, set_password, signed


def administrator(request) -> None:
    if not request.user.is_staff:
        raise Refused(403, "forbidden")


def without_passkeys(user: User) -> None:
    """Signing in with a passkey stops being the user's choice with the last of them gone."""
    if user.sign_in == "passkey" and not user.passkeys.exists():
        user.sign_in = ""
        user.save(update_fields=["sign_in"])


def handed_password(user: User) -> None:
    """A password someone else gives the user is their way back from a lost device, which a passkey
    the policy holds them to would refuse; they add a new one at their next sign-in."""
    if policy().holds(user):
        user.passkeys.all().delete()
        without_passkeys(user)


def kept_by(user: User) -> str | None:
    """The name of the directory that keeps the user's name, address and whether they may sign
    in, which the administrator then cannot change here."""
    return (
        Identity.objects.filter(
            user=user, provider__kind__in=(Provider.Kind.LDAP, Provider.Kind.SCIM)
        )
        .values_list("provider__name", flat=True)
        .first()
    )


def describe(user: User) -> dict:
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "name": user.get_full_name() or user.email,
        "is_admin": user.is_staff,
        "is_active": user.is_active,
        "visitor": user.visitor,
        "groups": [group.pk for group in user.groups.all()],
        "last_login": user.last_login,
        "kept_by": kept_by(user),
        "providers": list(
            user.identities.values_list("provider__name", flat=True).order_by("provider__name")
        ),
    }


def group_kept_by(group: Group) -> str | None:
    return Kept.objects.filter(group=group).values_list("provider__name", flat=True).first()


def describe_group(group: Group) -> dict:
    return {"id": group.pk, "name": group.name, "kept_by": group_kept_by(group)}


def text(data: dict, field: str, limit: int, required: bool = False) -> str:
    value = str(data.get(field, "")).strip()
    if (required and not value) or len(value) > limit:
        raise Refused(400, f"invalid_{field}")
    return value


def groups_of(data: dict) -> list[Group]:
    ids = data.get("groups")
    if not isinstance(ids, list) or not all(isinstance(pk, int) for pk in ids):
        raise Refused(400, "invalid_groups")
    found = list(Group.objects.filter(pk__in=ids))
    if len(found) != len(set(ids)):
        raise Refused(400, "invalid_groups")
    return found


# What an administrator changes of an account, by the name the journal gives it.
WATCHED = {
    "email": "email",
    "first_name": "name",
    "last_name": "name",
    "is_staff": "admin",
    "is_active": "active",
}


def flag(data: dict, field: str) -> bool:
    if not isinstance(data.get(field), bool):
        raise Refused(400, f"invalid_{field}")
    return data[field]


# What a directory keeps of a person it lists.
DIRECTORY_FIELDS = ("email", "first_name", "last_name", "is_active", "password")


def fill(user: User, data: dict) -> list[Group] | None:
    """Sets the fields the request carries; returns the groups when it names them, those a
    directory keeps the user in staying as the directory says."""
    if (
        user.pk
        and kept_by(user)
        and any(
            field in data and (field == "password" or data[field] != getattr(user, field))
            for field in DIRECTORY_FIELDS
        )
    ):
        raise Refused(400, "kept_by_directory")
    if "email" in data:
        user.email = text(data, "email", 254, required=True).lower()
        try:
            validate_email(user.email)
        except ValidationError:
            raise Refused(400, "invalid_email") from None
        if User.everyone.filter(email=user.email).exclude(pk=user.pk).exists():
            raise Refused(400, "email_taken")
    for field in ("first_name", "last_name"):
        if field in data:
            setattr(user, field, text(data, field, 150))
    if "is_admin" in data:
        user.is_staff = user.is_superuser = flag(data, "is_admin")
    if "is_active" in data:
        user.is_active = flag(data, "is_active")
    if "password" in data:
        set_password(user, data, "password")
    if "groups" not in data:
        return None
    named = [group for group in groups_of(data) if not Kept.objects.filter(group=group).exists()]
    held = list(user.groups.filter(kept__isnull=False)) if user.pk else []
    return [*named, *held]


@api("GET", "POST", confirmed=("POST",))
def users(request):
    administrator(request)
    if request.method == "POST":
        data = body(request)
        if "email" not in data or "password" not in data:
            raise Refused(400, "invalid_email" if "email" not in data else "invalid_password")
        user = User()
        groups = fill(user, data)
        with transaction.atomic():
            user.save()
            if groups is not None:
                user.groups.set(groups)
            entries.wrote(Kind.USER_ADDED, request=request, subject=user, admin=user.is_staff)
        return JsonResponse(describe(user), status=201)
    listed = (
        User.everyone.exclude(mailbox=True)
        .prefetch_related("groups")
        .order_by("first_name", "last_name", "email")
    )
    return JsonResponse(
        {
            "users": [describe(user) for user in listed],
            "groups": [describe_group(group) for group in Group.objects.order_by("name")],
        }
    )


def spelled(code) -> str:
    return "".join(character for character in str(code or "").upper() if character.isalnum())


@api("POST", signed_in=False)
def setup(request):
    """The installation's first administrator, with the code ponistra install printed."""
    data = body(request)
    if not settings.SETUP_CODE:
        raise Refused(409, "no_setup_code")
    with transaction.atomic():
        # Two people setting up at once: the second waits here and then finds the first.
        with connection.cursor() as cursor:
            cursor.execute(f'LOCK TABLE "{User._meta.db_table}" IN SHARE ROW EXCLUSIVE MODE')
        if User.objects.exists():
            raise Refused(409, "already_set_up")
        if not hmac.compare_digest(
            spelled(data.get("code")).encode(), spelled(settings.SETUP_CODE).encode()
        ):
            raise Refused(400, "invalid_setup_code")
        if "email" not in data or "password" not in data:
            raise Refused(400, "invalid_email" if "email" not in data else "invalid_password")
        user = User(is_staff=True, is_superuser=True)
        fill(
            user,
            {
                field: data[field]
                for field in ("email", "first_name", "last_name", "password")
                if field in data
            },
        )
        user.save()
        entries.wrote(Kind.INSTALLED, request=request, actor=user, subject=user)
    start_session(request, user, backend="django.contrib.auth.backends.ModelBackend")
    sessions.started(request, "password", passkey_due=policy().holds(user))
    return JsonResponse(signed(request), status=201)


@api("GET", "PATCH", "DELETE", confirmed=("PATCH", "DELETE"))
def user(request, pk):
    """A user, changed, or erased with the documents only they own passed to the heir named."""
    administrator(request)
    user = User.everyone.filter(pk=pk).first()
    if user is None:
        raise Refused(404, "not_found")
    if request.method == "GET":
        return JsonResponse(describe(user))
    if request.method == "DELETE":
        if user.pk == request.user.pk:
            raise Refused(400, "self")
        pk, heir = user.pk, erasure.heir_of(user, request.GET.get("heir"))
        erasure.erase(user, heir, request.user)
        entries.wrote(Kind.USER_ERASED, request=request, subject=heir, user=pk)
        return HttpResponse(status=204)
    if user.visitor:
        raise Refused(400, "visitor")
    data = body(request)
    if user.pk == request.user.pk and (
        data.get("is_admin") is False or data.get("is_active") is False
    ):
        raise Refused(400, "self")
    leaving = user.is_active and data.get("is_active") is False
    was = {field: getattr(user, field) for field in WATCHED}
    grouped = {group.pk for group in user.groups.all()}
    groups = fill(user, data)
    changed = list(
        dict.fromkeys(name for field, name in WATCHED.items() if getattr(user, field) != was[field])
    )
    if "password" in data:
        changed.append("password")
    if groups is not None and {group.pk for group in groups} != grouped:
        changed.append("groups")
    with transaction.atomic():
        user.save()
        if groups is not None:
            user.groups.set(groups)
        if changed:
            entries.wrote(
                Kind.USER_CHANGED,
                request=request,
                subject=user,
                changed=changed,
                admin=user.is_staff,
                active=user.is_active,
            )
        if leaving:
            sessions.ended(user)
        if "password" in data and user.pk != request.user.pk:
            handed_password(user)
        settle()
    revoke()
    return JsonResponse(describe(user))


def group_name(data: dict) -> str:
    return text(data, "name", 150, required=True)


def saved(group: Group) -> Group:
    try:
        with transaction.atomic():
            group.save()
    except IntegrityError:
        raise Refused(400, "name_taken") from None
    return group


@api("POST")
def groups(request):
    administrator(request)
    group = saved(Group(name=group_name(body(request))))
    entries.wrote(Kind.GROUP_ADDED, request=request, name=group.name)
    return JsonResponse(describe_group(group), status=201)


@api("PATCH", "DELETE")
def group(request, pk):
    administrator(request)
    group = Group.objects.filter(pk=pk).first()
    if group is None:
        raise Refused(404, "not_found")
    if group_kept_by(group):
        raise Refused(400, "kept_by_directory")
    if request.method == "DELETE":
        if orphaned(Grant.objects.filter(group=group)).exists():
            raise Refused(400, "last_owner")
        if orphaned_by(group):
            raise Refused(400, "collection_owner")
        with transaction.atomic():
            group.delete()
            settle()
            entries.wrote(Kind.GROUP_REMOVED, request=request, name=group.name)
        revoke()
        return HttpResponse(status=204)
    was, group.name = group.name, group_name(body(request))
    saved(group)
    if group.name != was:
        entries.wrote(Kind.GROUP_RENAMED, request=request, name=group.name, was=was)
    return JsonResponse(describe_group(group))


def describe_policy(found: Policy) -> dict:
    return {"passkeys": found.passkeys, "outside": found.outside}


@api("GET", "PATCH", confirmed=("PATCH",))
def sign_in_policy(request):
    """Whom the installation holds to passkeys, which applies from their next sign-in, and who may
    make a link for someone outside it."""
    administrator(request)
    found = policy()
    if request.method == "PATCH":
        data = body(request)
        passkeys = data.get("passkeys", found.passkeys)
        outside = data.get("outside", found.outside)
        if passkeys not in Policy.Passkeys.values or outside not in Policy.Outside.values:
            raise Refused(400, "invalid_policy")
        if (passkeys, outside) != (found.passkeys, found.outside):
            entries.wrote(Kind.POLICY_CHANGED, request=request, passkeys=passkeys, outside=outside)
        found.passkeys = passkeys
        found.outside = outside
        found.changed_by = request.user
        found.changed_at = timezone.now()
        found.save()
    return JsonResponse(describe_policy(found))
