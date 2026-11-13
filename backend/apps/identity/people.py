"""The people and groups a provider brings (U1): the account found or made for whom it names, kept
in step with what it says of them, and the groups it keeps."""

from dataclasses import dataclass, field
from logging import getLogger

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from apps.access.models import Grant
from apps.access.rights import orphaned
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users import sessions
from apps.users.models import User
from apps.vault.views import orphaned_by, settle

from .models import Identity, Kept, Provider

log = getLogger(__name__)

NAME = 150


class Refusal(Exception):
    """Why a provider's person gets no account here, as the sign-in page or the directory is
    told."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Person:
    subject: str
    email: str
    first_name: str = ""
    last_name: str = ""
    active: bool = True
    # The groups it names them in, by subject and name; None where it says nothing of groups.
    groups: list[tuple[str, str]] | None = None
    detail: dict = field(default_factory=dict)
    # False only where the provider says the address is not the person's own.
    verified: bool = True


def address(given) -> str:
    email = str(given or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


def within(provider: Provider, email: str) -> bool:
    return not provider.domains or email.rpartition("@")[2] in provider.domains


def administrators_left(user: User) -> bool:
    """Whether someone else still administers the installation once the user stops."""
    return User.objects.filter(is_staff=True, is_active=True).exclude(pk=user.pk).exists()


def _linked(provider: Provider, person: Person) -> Identity:
    found = (
        Identity.objects.select_related("user")
        .filter(provider=provider, subject=person.subject)
        .first()
    )
    if found is not None:
        return found
    email = address(person.email)
    if not email:
        raise Refusal("no_email")
    if not within(provider, email):
        raise Refusal("outside_domains")
    if not person.verified:
        raise Refusal("unverified_email")
    user = User.everyone.filter(email=email).first()
    if user is not None and user.visitor:
        raise Refusal("visitor")
    if user is None:
        if not provider.creates:
            raise Refusal("no_account")
        user = User(email=email)
        user.set_unusable_password()
        user.first_name, user.last_name = person.first_name[:NAME], person.last_name[:NAME]
        user.is_active = person.active
        user.save()
        entries.wrote(Kind.USER_ADDED, subject=user, admin=False, provider=provider.name)
    # The provider names the person anew (an LDAP entry recreated, SCIM's externalId changed).
    Identity.objects.filter(provider=provider, user=user).delete()
    return Identity.objects.create(provider=provider, user=user, subject=person.subject)


def _changed(provider: Provider, user: User, person: Person) -> list[str]:
    changed = []
    first, last = person.first_name[:NAME], person.last_name[:NAME]
    if (first or last) and (first, last) != (user.first_name, user.last_name):
        user.first_name, user.last_name = first, last
        changed.append("name")
    email = address(person.email)
    if (
        email
        and email != user.email
        and within(provider, email)
        and not User.everyone.filter(email=email).exclude(pk=user.pk).exists()
    ):
        user.email = email
        changed.append("email")
    if provider.lists and person.active != user.is_active:
        if person.active or not user.is_staff or administrators_left(user):
            user.is_active = person.active
            changed.append("active")
        else:
            log.warning("identity: %s would stop the last administrator %s", provider, user)
    return changed


def kept(provider: Provider, person: Person) -> User:
    """The account of the provider's person, linked at first sight by address and made where the
    provider may make accounts, with what the provider says of them."""
    with transaction.atomic():
        identity = _linked(provider, person)
        user = identity.user
        if person.detail and person.detail != identity.detail:
            identity.detail = person.detail
        identity.save()
        changed = _changed(provider, user, person)
        if changed:
            user.save()
            entries.wrote(
                Kind.USER_CHANGED,
                subject=user,
                changed=changed,
                admin=user.is_staff,
                active=user.is_active,
                provider=provider.name,
            )
        if "active" in changed and not user.is_active:
            sessions.ended(user)
        if provider.groups and person.groups is not None:
            member_of(provider, user, person.groups)
        settle()
    return user


def group(provider: Provider, subject: str, name: str) -> Group:
    """The group the provider keeps by that subject, named as it names it. A group of the
    installation's own by the same name becomes the provider's; one another provider keeps is
    told apart by the provider's name."""
    name = name.strip()[:NAME] or subject[:NAME]
    found = Kept.objects.select_related("group").filter(provider=provider, subject=subject).first()
    if found is not None:
        if found.group.name != name and not Group.objects.filter(name=name).exists():
            was, found.group.name = found.group.name, name
            found.group.save(update_fields=["name"])
            entries.wrote(Kind.GROUP_RENAMED, name=name, was=was, provider=provider.name)
        return found.group
    same = Group.objects.filter(name=name).first()
    if same is not None and not Kept.objects.filter(group=same).exists():
        Kept.objects.create(group=same, provider=provider, subject=subject)
        return same
    if same is not None:
        name = f"{name[: NAME - len(provider.name) - 3]} ({provider.name})"
    made = Group.objects.get_or_create(name=name)[0]
    Kept.objects.create(group=made, provider=provider, subject=subject)
    entries.wrote(Kind.GROUP_ADDED, name=made.name, provider=provider.name)
    return made


def member_of(provider: Provider, user: User, named: list[tuple[str, str]]) -> None:
    """The user's groups the provider keeps become those it names; the installation's own groups
    stay as the administrator set them."""
    wanted = {group(provider, subject, name).pk for subject, name in named}
    held = set(user.groups.filter(kept__provider=provider).values_list("pk", flat=True))
    if wanted - held:
        user.groups.add(*(wanted - held))
    if held - wanted:
        user.groups.remove(*(held - wanted))


def members(provider: Provider, kept_group: Group, users: list[User]) -> None:
    """The members of a group the provider keeps become those it lists."""
    kept_group.user_set.set(users)


def gone(provider: Provider, kept_group: Group) -> None:
    """A group the provider no longer keeps leaves, unless something only it owns would be left
    without an owner: then it stays as one of the installation's own."""
    with transaction.atomic():
        if orphaned(Grant.objects.filter(group=kept_group)).exists() or orphaned_by(kept_group):
            Kept.objects.filter(group=kept_group).delete()
            log.warning("identity: %s keeps group %s, which owns alone", provider, kept_group)
            return
        name = kept_group.name
        kept_group.delete()
        entries.wrote(Kind.GROUP_REMOVED, name=name, provider=provider.name)
        settle()


def left(provider: Provider, user: User) -> None:
    """A person the provider no longer lists stops signing in; their account and what it owns
    stay for an administrator to erase with an heir."""
    with transaction.atomic():
        Identity.objects.filter(provider=provider, user=user).delete()
        if user.is_active and (not user.is_staff or administrators_left(user)):
            user.is_active = False
            user.save(update_fields=["is_active"])
            sessions.ended(user)
            entries.wrote(
                Kind.USER_CHANGED,
                subject=user,
                changed=["active"],
                admin=user.is_staff,
                active=False,
                provider=provider.name,
            )
        settle()


def kept_by(user: User) -> Provider | None:
    """The directory that keeps the user's name, address and whether they may sign in."""
    found = (
        Identity.objects.select_related("provider")
        .filter(user=user, provider__kind__in=(Provider.Kind.LDAP, Provider.Kind.SCIM))
        .first()
    )
    return found and found.provider
