"""Shared mailboxes (S3-6). A mailbox is a user of its own, whom no one signs in as: its accounts
and its mail, calendars and contacts are its own, so they neither mix with those of whoever
connected it nor leave with them. Colleagues reach it through its grants. A request names the
mailbox it acts in by `box`, and acts as the mailbox from there on, the colleague kept as its
person."""

import inspect
import uuid
from functools import partial, wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q

from apps.access.models import RANK, Role
from apps.core.api import Refused, body
from apps.core.asyncdb import database

from .models import Account, Draft, Folder, Grant, Message, Rule, Unsent

User = get_user_model()
NAME = 150


def _reaching(person) -> Q:
    return Q(user=person) | Q(group__in=person.groups.all()) | Q(user=None, group=None)


def roles(person) -> dict[int, Role]:
    """The mailboxes the person reaches, each with the highest role their grants give them."""
    found: dict[int, Role] = {}
    for mailbox, role in Grant.objects.filter(_reaching(person)).values_list("mailbox", "role"):
        if mailbox not in found or RANK[role] > RANK[found[mailbox]]:
            found[mailbox] = Role(role)
    return found


def role_in(person, mailbox: int) -> Role | None:
    return roles(person).get(mailbox) if not person.visitor else None


def mailbox(person, given: str, needs: Role):
    """The mailbox the request names, where the person's role covers what it does."""
    try:
        pk = int(given)
    except ValueError:
        raise Refused(400, "invalid_box") from None
    role = role_in(person, pk)
    found = User.everyone.filter(pk=pk, mailbox=True).first() if role else None
    if found is None:
        raise Refused(404, "not_found")
    if RANK[role] < RANK[needs]:
        raise Refused(403, "forbidden")
    return found


READ, EDIT, OWN = Role.READ, Role.EDIT, Role.OWN


def owned_by(model, owner: str = "owner_id"):
    """Whose the row the URL names is, for `boxed` to act in that mailbox."""

    def of(request, pk=None, **_) -> int | None:
        return model.objects.filter(pk=pk).values_list(owner, flat=True).first()

    return of


def sent_from(model, key: str = "account"):
    """Whose the row the body names by `key` is: the account it sends from, say."""

    def of(request, **_) -> int | None:
        given = body(request).get(key)
        if type(given) is not int:
            return None
        return model.objects.filter(pk=given).values_list("owner_id", flat=True).first()

    return of


MESSAGE = owned_by(Message)
FOLDER = owned_by(Folder)
ACCOUNT = owned_by(Account)
DRAFT = owned_by(Draft)
UNSENT = owned_by(Unsent)
RULE = owned_by(Rule)
SENT_FROM = sent_from(Account)


def _acting(request, acting: Role, of, kwargs) -> None:
    request.person = request.user
    given = request.GET.get("box")
    if not given and of is not None:
        owner = of(request, **kwargs)
        given = str(owner) if owner is not None and owner != request.person.pk else None
    if given:
        needs = READ if request.method == "GET" else acting
        request.user = mailbox(request.person, given, needs)


def boxed(acting: Role = EDIT, of=None):
    """A mail view acting in a shared mailbox: the one the request names by `box`, or else the
    one whose row the URL names (`of`), as `owned_by` or `sent_from` find it. Reading it on GET,
    otherwise doing what needs the role `acting`. Below `api`, which signs the person in first."""

    def decorate(view):
        act = partial(_acting, acting=acting, of=of)

        if inspect.iscoroutinefunction(view):

            @wraps(view)
            async def acting_later(request, *args, **kwargs):
                await database(act)(request, kwargs=kwargs)
                return await view(request, *args, **kwargs)

            return acting_later

        @wraps(view)
        def acting_now(request, *args, **kwargs):
            act(request, kwargs=kwargs)
            return view(request, *args, **kwargs)

        return acting_now

    return decorate


def _name(given) -> str:
    name = given.strip()[:NAME] if isinstance(given, str) else ""
    if not name:
        raise Refused(400, "invalid_name")
    return name


def made(person, name: str):
    """A new mailbox, which its maker owns."""
    with transaction.atomic():
        box = User.everyone.create_user(
            f"mailbox-{uuid.uuid4().hex}@mailbox.invalid",
            None,
            mailbox=True,
            first_name=_name(name),
        )
        Grant.objects.create(mailbox=box, user=person, role=Role.OWN, created_by=person)
    return box


def described(box, role: Role, unseen: int) -> dict:
    return {"id": box.pk, "name": box.first_name, "role": role, "unseen": unseen}


def describe_grant(grant: Grant) -> dict:
    if grant.user_id:
        grantee = {"kind": "user", "id": grant.user_id, "name": grant.user.get_full_name()}
        grantee["name"] = grantee["name"] or grant.user.email
    elif grant.group_id:
        grantee = {"kind": "group", "id": grant.group_id, "name": grant.group.name}
    else:
        grantee = {"kind": "everyone", "id": None, "name": ""}
    return {"id": grant.pk, "role": grant.role, "grantee": grantee}


def granted(box, person, data: dict) -> Grant:
    """Gives the grantee the role in the mailbox, or changes the one they hold."""
    kind, given = data.get("kind"), data.get("id")
    role = data.get("role")
    if role not in Role.values:
        raise Refused(400, "invalid_role")
    where = {"user": None, "group": None}
    if kind == "user":
        found = User.objects.filter(pk=given).first() if type(given) is int else None
        if found is None:
            raise Refused(400, "invalid_grantee")
        where["user"] = found
    elif kind == "group":
        found = Group.objects.filter(pk=given).first() if type(given) is int else None
        if found is None:
            raise Refused(400, "invalid_grantee")
        where["group"] = found
    elif kind != "everyone":
        raise Refused(400, "invalid_grantee")
    with transaction.atomic():
        grant, _ = Grant.objects.update_or_create(
            mailbox=box,
            **where,
            defaults={"role": role},
            create_defaults={"role": role, "created_by": person},
        )
        _owned(box)
    return grant


def taken_back(box, pk: int) -> None:
    with transaction.atomic():
        deleted, _ = Grant.objects.filter(mailbox=box, pk=pk).delete()
        if not deleted:
            raise Refused(404, "not_found")
        _owned(box)


def renamed(box, name: str) -> None:
    box.first_name = _name(name)
    box.save(update_fields=["first_name"])


def removed(box, person) -> None:
    """Removes the mailbox with its accounts and its mail, as the erasure of a user would, where
    no rule or hold keeps them."""
    from apps.users import erasure

    erasure.erase(box, None, person)


def _owned(box) -> None:
    """A mailbox keeps someone who owns it, or no one could share it or change its accounts."""
    if not Grant.objects.filter(mailbox=box, role=Role.OWN).exists():
        raise Refused(409, "last_owner")


def stranded(person) -> list[int]:
    """The mailboxes the person's erasure would leave without a living owner: an active user, a
    group (which an administrator can refill) or everyone."""
    owning = Grant.objects.filter(user=person, role=OWN).values("mailbox")
    living = (
        Grant.objects.filter(role=OWN, mailbox__in=owning)
        .exclude(user=person)
        .filter(Q(user=None) | Q(user__is_active=True))
    )
    return list(
        owning.exclude(mailbox__in=living.values("mailbox")).values_list("mailbox", flat=True)
    )


def inherited(boxes: list[int], heir) -> None:
    """The heir owns the stranded mailboxes."""
    for box in boxes:
        Grant.objects.update_or_create(
            mailbox_id=box,
            user=heir,
            group=None,
            defaults={"role": OWN},
            create_defaults={"role": OWN, "created_by": heir},
        )


def writers(box) -> set[int]:
    """Those who write from the mailbox: whom its grants let act on its mail."""
    grants = Grant.objects.filter(mailbox=box, role__in=(EDIT, OWN))
    if grants.filter(user=None, group=None).exists():
        return set(User.objects.values_list("pk", flat=True))
    members = User.groups.through.objects.filter(group__mail_grants__in=grants)
    direct = grants.exclude(user=None).values_list("user_id", flat=True)
    return set(direct) | set(members.values_list("user_id", flat=True))


def concerned(key: str) -> set[int] | None:
    """Whom a change to a user's mail concerns: the user, and those a mailbox is shared with, None
    where it is shared with everyone (`live`)."""
    owner = int(key)
    users: set[int] = {owner}
    groups: set[int] = set()
    for user, group in Grant.objects.filter(mailbox_id=owner).values_list("user_id", "group_id"):
        if user is None and group is None:
            return None
        if user is None:
            groups.add(group)
        else:
            users.add(user)
    members = User.groups.through.objects.filter(group_id__in=groups)
    return users | set(members.values_list("user_id", flat=True))
