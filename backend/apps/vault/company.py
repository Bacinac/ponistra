"""What an administrator does in the vault: lays out the company's collections for groups without
a key to read them, keeps the company's recovery key while the policy is on, and with it hands a
user who lost both password and recovery code a one-time code to their vault."""

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.http import HttpResponse, JsonResponse

from apps.access.company import audience_of
from apps.access.models import Role
from apps.access.rights import grantee
from apps.core.api import Refused, api, body
from apps.users.accounts import administrator
from apps.users.models import User
from apps.users.views import describe as describe_user

from .models import Collection, Escrow, Event, Holder, Member, Recovery, Vault
from .views import PUBLIC, audience, decoded, encoded, logged, name_of


def describe(collection: Collection) -> dict:
    members = sorted(
        collection.members.all(),
        key=lambda member: (member.group is not None, member.group and member.group.name),
    )
    return {
        "id": collection.pk,
        "name": collection.name,
        "grants": [
            {
                "group": member.group and {"id": member.group.pk, "name": member.group.name},
                "role": member.role,
            }
            for member in members
        ],
    }


def given(collection: Collection, roles: dict[int | None, Role], by) -> None:
    """The collection's members made those the roles name, each change logged; the keys of whom
    it no longer reaches are taken back."""
    held = {member.group_id: member for member in collection.members.select_related("group")}
    for group, member in held.items():
        if group not in roles:
            logged(Event.Kind.SHARED, collection, by, grantee=grantee(member), role=None)
            member.delete()
    for group, role in roles.items():
        member = held.get(group)
        if member is None:
            member = Member.objects.create(
                collection=collection, group_id=group, role=role, created_by=by
            )
        elif member.role == role:
            continue
        else:
            member.role = role
            member.save(update_fields=["role"])
        logged(Event.Kind.SHARED, collection, by, grantee=grantee(member), role=role)
    collection.keys.exclude(user__in=audience(collection)).delete()


@api("GET", "POST")
def collections(request):
    administrator(request)
    if request.method == "GET":
        found = Collection.objects.filter(kind=Collection.Kind.COMPANY).prefetch_related(
            "members__group"
        )
        return JsonResponse(
            {"collections": [describe(collection) for collection in found.order_by(Lower("name"))]}
        )
    data = body(request)
    name, roles = name_of(data), audience_of(data)
    with transaction.atomic():
        made = Collection.objects.create(
            kind=Collection.Kind.COMPANY, name=name, created_by=request.user
        )
        given(made, roles, request.user)
    return JsonResponse(describe(made), status=201)


@api("PATCH", "DELETE")
def collection(request, pk):
    administrator(request)
    found = Collection.objects.filter(pk=pk, kind=Collection.Kind.COMPANY).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        if found.items.exists():
            raise Refused(409, "collection_not_empty")
        found.delete()
        return HttpResponse(status=204)
    data = body(request)
    with transaction.atomic():
        if "name" in data:
            found.name = name_of(data)
            found.save(update_fields=["name"])
        if "grants" in data:
            given(found, audience_of(data), request.user)
    return JsonResponse(describe(found))


def describe_recovery(user) -> dict:
    recovery = Recovery.objects.select_related("created_by").first()
    if recovery is None:
        return {"on": False}
    holding = Holder.objects.filter(
        recovery=recovery, user__is_staff=True, user__is_active=True
    ).select_related("user")
    held = {holder.user_id: holder for holder in holding}
    waiting = (
        Vault.objects.filter(user__is_staff=True, user__is_active=True)
        .exclude(user__in=list(held))
        .select_related("user")
    )
    return {
        "on": True,
        "public_key": encoded(recovery.public_key),
        "sealed": user.pk in held and encoded(held[user.pk].sealed) or None,
        "created_by": recovery.created_by and describe_user(recovery.created_by),
        "created_at": recovery.created_at,
        "holders": sorted(
            (describe_user(holder.user) for holder in held.values()),
            key=lambda person: person["name"].casefold(),
        ),
        "waiting": [
            {**describe_user(found.user), "public_key": encoded(found.public_key)}
            for found in waiting
        ],
        "escrowed": Escrow.objects.filter(recovery=recovery, user__is_active=True).count(),
        "vaults": Vault.objects.filter(user__is_active=True).count(),
    }


@api("GET", "PUT", "DELETE", confirmed=("PUT", "DELETE"))
def recovery(request):
    """The policy of recovery through the company. Turned on by an administrator with a vault,
    whose browser made the key pair and sealed its private half to them; turned off, every
    vault key sealed to it goes with it."""
    administrator(request)
    if request.method == "PUT":
        if not Vault.objects.filter(user=request.user).exists():
            raise Refused(400, "no_vault")
        data = body(request)
        public_key, sealed = decoded(data, "public_key", exact=PUBLIC), decoded(data, "sealed")
        try:
            with transaction.atomic():
                made = Recovery.objects.create(public_key=public_key, created_by=request.user)
                Holder.objects.update_or_create(
                    user=request.user,
                    defaults={"recovery": made, "sealed": sealed, "confirmed_by": request.user},
                )
        except IntegrityError:
            raise Refused(409, "recovery_on") from None
    elif request.method == "DELETE":
        Recovery.objects.all().delete()
    return JsonResponse(describe_recovery(request.user))


@api("POST")
def holders(request):
    """Administrators confirmed by one who holds the recovery key: its private half sealed to
    each."""
    administrator(request)
    recovery = Recovery.objects.first()
    if recovery is None:
        raise Refused(404, "no_recovery")
    if not Holder.objects.filter(user=request.user, recovery=recovery).exists():
        raise Refused(403, "no_key")
    entries = body(request).get("holders")
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise Refused(400, "invalid_holders")
    can = set(
        Vault.objects.filter(user__is_staff=True, user__is_active=True)
        .exclude(user__in=recovery.holders.values("user"))
        .values_list("user", flat=True)
    )
    with transaction.atomic():
        for entry in entries:
            if entry.get("user") not in can:
                raise Refused(400, "invalid_holders")
            Holder.objects.create(
                user_id=entry["user"],
                recovery=recovery,
                sealed=decoded(entry, "sealed"),
                confirmed_by=request.user,
            )
    return JsonResponse(describe_recovery(request.user))


@api("GET", "POST", confirmed=("POST",))
def recover(request, pk):
    """A user's vault key as the company's recovery key sealed it, for an administrator who holds
    that key; then wrapped by them with a one-time code they hand the user, who sets a new
    password with it. The user's vault shows who recovered it and when."""
    administrator(request)
    target = User.objects.filter(pk=pk).first()
    if target is None:
        raise Refused(404, "not_found")
    found = Vault.objects.filter(user=target).first()
    escrow = Escrow.objects.filter(user=target).first()
    if request.method == "GET":
        return JsonResponse(
            {"vault": found is not None, "escrow": escrow and encoded(escrow.sealed)}
        )
    if found is None or escrow is None:
        raise Refused(400, "not_escrowed")
    if not Holder.objects.filter(user=request.user, recovery=escrow.recovery_id).exists():
        raise Refused(403, "no_key")
    with transaction.atomic():
        found.handed = decoded(body(request), "handed")
        found.save(update_fields=["handed"])
        logged(Event.Kind.RECOVERED, None, request.user, subject=target.pk)
    return HttpResponse(status=204)
