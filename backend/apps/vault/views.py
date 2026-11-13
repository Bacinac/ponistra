"""The vault's API. What browsers sealed travels as base64 and is kept as it came: the server
decides who may read and write what, and never sees what it says."""

import base64
import binascii
import uuid
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q, QuerySet
from django.db.models.functions import Lower
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.access.models import Role
from apps.access.rights import covers, grantee, reaching, strongest
from apps.ai import installation
from apps.blobs import store
from apps.blobs.models import Blob
from apps.blobs.views import serve
from apps.core.api import Refused, api, body, optional_id
from apps.core.asyncdb import database
from apps.users.models import Passkey, User
from apps.users.views import describe as describe_user

from .models import (
    Attachment,
    Collection,
    Escrow,
    Event,
    Folder,
    Holder,
    Item,
    Key,
    Member,
    Recovery,
    Unlock,
    Vault,
)
from .sorting import LANGUAGES, Unsorted, propose

# An X25519 public key; a sealed key, private key or salt; an item's sealed contents.
PUBLIC = 32
SMALL = 4096
LARGE = 1024 * 1024
# The least Argon2id may cost, so that no client weakens what guards a vault, and the most.
FLOOR = {"memory": 65536, "iterations": 3, "parallelism": 1}
CEILING = {"memory": 1048576, "iterations": 20, "parallelism": 16}
# An opening and a password seen again within this are not logged again.
QUIET = timedelta(hours=1)
LOGGED = 500
# Items made in one request, as an import makes them, and filed in one, as a sorting files them.
BATCH = 1000
LISTED = 10000
SEEN = ("password", "totp")


def encoded(value) -> str | None:
    return None if value is None else base64.b64encode(bytes(value)).decode()


def decoded(data: dict, field: str, limit: int = SMALL, exact: int | None = None) -> bytes:
    value = data.get(field)
    try:
        raw = base64.b64decode(value, validate=True) if isinstance(value, str) else None
    except binascii.Error:
        raw = None
    if not raw or len(raw) > limit or (exact is not None and len(raw) != exact):
        raise Refused(400, f"invalid_{field}")
    return raw


def kdf_of(data: dict) -> dict:
    kdf = data.get("kdf")
    if not isinstance(kdf, dict) or set(kdf) != {"salt", *FLOOR}:
        raise Refused(400, "invalid_kdf")
    for field in FLOOR:
        value = kdf[field]
        if type(value) is not int or not FLOOR[field] <= value <= CEILING[field]:
            raise Refused(400, "invalid_kdf")
    salt = decoded(kdf, "salt", limit=64)
    if len(salt) < 16:
        raise Refused(400, "invalid_kdf")
    return kdf


def name_of(data: dict) -> str:
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 200:
        raise Refused(400, "invalid_name")
    return name


def role_of(data: dict) -> Role:
    if data.get("role") not in Role.values:
        raise Refused(400, "invalid_role")
    return Role(data["role"])


def mine(user) -> Vault:
    found = Vault.objects.filter(user=user).first()
    if found is None:
        raise Refused(404, "no_vault")
    return found


def audience(collection: Collection) -> QuerySet[User]:
    """The active users the collection reaches."""
    users = User.objects.filter(is_active=True)
    if collection.kind == Collection.Kind.PERSONAL:
        return users.filter(pk=collection.owner_id)
    members = collection.members.all()
    if members.filter(user=None, group=None).exists():
        return users
    return users.filter(
        Q(pk__in=members.values("user")) | Q(groups__in=members.values("group"))
    ).distinct()


def concerned(key: str) -> list[int]:
    """Whom a change to the collection concerns (`live`)."""
    collection = Collection.objects.filter(pk=key).first()
    return list(audience(collection).values_list("pk", flat=True)) if collection else []


def role_in(user, collection: Collection) -> Role | None:
    if collection.kind == Collection.Kind.PERSONAL:
        return Role.OWN if collection.owner_id == user.pk else None
    return strongest(collection.members.filter(reaching(user)).values_list("role", flat=True))


def held(user) -> dict:
    """The strongest role the user holds in each collection beside their own."""
    roles: dict = {}
    for collection, role in Member.objects.filter(reaching(user)).values_list("collection", "role"):
        roles[collection] = strongest([roles.get(collection), role])
    return roles


def reached(user, pk, needs: Role = Role.READ) -> tuple[Collection, Role]:
    collection = Collection.objects.filter(pk=pk).first() if pk else None
    role = collection and role_in(user, collection)
    if not role:
        raise Refused(404, "not_found")
    if not covers(role, needs):
        raise Refused(403, "forbidden")
    return collection, role


def waiting(collection: Collection) -> QuerySet[User]:
    """Whom the collection reaches who have a vault and no key to it yet."""
    return (
        audience(collection)
        .filter(vault__isnull=False)
        .exclude(pk__in=collection.keys.values("user"))
    )


def owned(collection: Collection) -> None:
    """Refuses a change that would leave the collection without a living owner: an active user,
    a group or everyone."""
    living = collection.members.filter(role=Role.OWN).filter(Q(user=None) | Q(user__is_active=True))
    if not living.exists():
        raise Refused(400, "collection_owner")


def orphaned_by(group) -> bool:
    """Whether deleting the group would leave a collection without a living owner."""
    owning = Member.objects.filter(group=group, role=Role.OWN).values("collection")
    living = (
        Member.objects.filter(role=Role.OWN, collection__in=owning)
        .exclude(group=group)
        .filter(Q(user=None) | Q(user__is_active=True))
    )
    return (
        Collection.objects.filter(pk__in=owning)
        .exclude(pk__in=living.values("collection"))
        .exists()
    )


def settle() -> None:
    """Takes back what nobody it reaches holds any more: a collection's key from whom it no
    longer reaches, the recovery key from whom is no longer an administrator."""
    for collection in (
        Collection.objects.exclude(kind=Collection.Kind.PERSONAL)
        .filter(keys__isnull=False)
        .distinct()
    ):
        collection.keys.exclude(user__in=audience(collection)).delete()
    Holder.objects.filter(Q(user__is_staff=False) | Q(user__is_active=False)).delete()


def logged(kind, collection: Collection | None, user, item=None, subject=None, **detail) -> None:
    """An event, `subject` naming by id whom it was about."""
    if collection is not None and collection.kind == Collection.Kind.PERSONAL:
        return
    if kind in (Event.Kind.OPENED, Event.Kind.SEEN):
        recent = Event.objects.filter(
            kind=kind,
            collection=collection,
            item=item,
            user=user,
            detail=detail,
            at__gt=timezone.now() - QUIET,
        )
        if recent.exists():
            return
    Event.objects.create(
        kind=kind, collection=collection, item=item, user=user, subject_id=subject, detail=detail
    )


def describe_vault(found: Vault) -> dict:
    user = found.user
    recovery = Recovery.objects.first()
    recovered = (
        Event.objects.filter(subject=user, kind=Event.Kind.RECOVERED)
        .select_related("user")
        .order_by("-at")
        .first()
    )
    unlocks = Unlock.objects.filter(passkey__user=user).select_related("passkey")
    return {
        "public_key": encoded(found.public_key),
        "private_key": encoded(found.private_key),
        "kdf": found.kdf,
        "by_password": encoded(found.by_password),
        "by_code": encoded(found.by_code),
        "code": encoded(found.code),
        "handed": encoded(found.handed),
        "unlocks": [
            {
                "passkey": unlock.passkey_id,
                "name": unlock.passkey.name,
                "credential": encoded(unlock.passkey.credential),
                "salt": encoded(unlock.salt),
                "wrapped": encoded(unlock.wrapped),
            }
            for unlock in unlocks.order_by("passkey__name")
        ],
        "recovery": recovery and {"public_key": encoded(recovery.public_key)},
        "escrowed": Escrow.objects.filter(user=user).exists(),
        "recovered": recovered
        and {"by": recovered.user and describe_user(recovered.user), "at": recovered.at},
    }


@api("GET", "POST", "PATCH", "DELETE", confirmed=("PATCH", "DELETE"))
def vault(request):
    """The user's vault: made once, with their own collection; its password and recovery code
    changed; or, when both are lost, given up to start again."""
    user = request.user
    if request.method == "POST":
        data = body(request)
        fields = {
            "public_key": decoded(data, "public_key", exact=PUBLIC),
            "private_key": decoded(data, "private_key"),
            "kdf": kdf_of(data),
            "by_password": decoded(data, "by_password"),
            "by_code": decoded(data, "by_code"),
            "code": decoded(data, "code"),
        }
        sealed = decoded(data, "personal")
        try:
            with transaction.atomic():
                made = Vault.objects.create(user=user, **fields)
                own = Collection.objects.create(
                    kind=Collection.Kind.PERSONAL, owner=user, created_by=user
                )
                Key.objects.create(collection=own, user=user, sealed=sealed, confirmed_by=user)
        except IntegrityError:
            raise Refused(409, "vault_exists") from None
        return JsonResponse(describe_vault(made), status=201)
    found = Vault.objects.filter(user=user).first()
    if found is None:
        if request.method == "GET":
            return JsonResponse(None, safe=False)
        if request.method == "DELETE":
            return HttpResponse(status=204)
        raise Refused(404, "no_vault")
    if request.method == "PATCH":
        data = body(request)
        if "by_password" in data:
            found.kdf = kdf_of(data)
            found.by_password = decoded(data, "by_password")
            found.handed = None
        if "by_code" in data:
            found.by_code = decoded(data, "by_code")
            found.code = decoded(data, "code")
        found.save()
    elif request.method == "DELETE":
        if (
            Holder.objects.filter(user=user).exists()
            and not Holder.objects.exclude(user=user)
            .filter(user__is_active=True, user__is_staff=True)
            .exists()
        ):
            raise Refused(409, "last_holder")
        with transaction.atomic():
            Collection.objects.filter(kind=Collection.Kind.PERSONAL, owner=user).delete()
            Key.objects.filter(user=user).delete()
            Unlock.objects.filter(passkey__user=user).delete()
            Escrow.objects.filter(user=user).delete()
            Holder.objects.filter(user=user).delete()
            found.delete()
        store.collect_later()
        return HttpResponse(status=204)
    return JsonResponse(describe_vault(found))


@api("POST", confirmed=("POST",))
def unlocks(request):
    """One of the user's passkeys made to unlock the vault, by the key its PRF gives; the browser
    names it by its credential."""
    found = mine(request.user)
    data = body(request)
    credential = decoded(data, "credential", limit=1023)
    passkey = Passkey.objects.filter(user=request.user, credential=credential).first()
    if passkey is None:
        raise Refused(400, "invalid_credential")
    Unlock.objects.update_or_create(
        passkey=passkey,
        defaults={"salt": decoded(data, "salt", exact=32), "wrapped": decoded(data, "wrapped")},
    )
    return JsonResponse(describe_vault(found), status=201)


@api("DELETE", confirmed=("DELETE",))
def unlock(request, pk):
    Unlock.objects.filter(passkey_id=pk, passkey__user=request.user).delete()
    return HttpResponse(status=204)


@api("PUT")
def escrow(request):
    """The vault key sealed to the company's recovery key, as the policy holds every vault."""
    found = mine(request.user)
    recovery = Recovery.objects.first()
    if recovery is None:
        raise Refused(404, "no_recovery")
    data = body(request)
    if decoded(data, "public_key", exact=PUBLIC) != bytes(recovery.public_key):
        raise Refused(409, "recovery_changed")
    Escrow.objects.update_or_create(
        user=request.user, defaults={"recovery": recovery, "sealed": decoded(data, "sealed")}
    )
    return JsonResponse(describe_vault(found))


@api("GET")
def public_keys(request):
    """Whom a collection's key can be sealed to: every active user who has a vault."""
    found = Vault.objects.filter(user__is_active=True).values_list("user", "public_key")
    return JsonResponse(
        {"keys": [{"user": user, "public_key": encoded(key)} for user, key in found]}
    )


def describe_collection(collection: Collection, role: Role, user) -> dict:
    key = next((key for key in collection.keys.all() if key.user_id == user.pk), None)
    described = {
        "id": collection.pk,
        "kind": collection.kind,
        "name": collection.name,
        "role": role,
        "key": key and encoded(key.sealed),
        "items": collection.items.filter(trashed_at=None).count(),
    }
    if collection.kind != Collection.Kind.PERSONAL:
        described["keyless"] = (
            key is None and not Key.objects.filter(collection=collection).exists()
        )
    if role == Role.OWN and collection.kind != Collection.Kind.PERSONAL:
        described["waiting"] = waiting(collection).count()
    return described


@api("GET", "POST")
def collections(request):
    user = request.user
    if request.method == "POST":
        mine(user)
        data = body(request)
        name, sealed = name_of(data), decoded(data, "key")
        with transaction.atomic():
            made = Collection.objects.create(
                kind=Collection.Kind.SHARED, name=name, created_by=user
            )
            Member.objects.create(collection=made, user=user, role=Role.OWN, created_by=user)
            Key.objects.create(collection=made, user=user, sealed=sealed, confirmed_by=user)
        return JsonResponse(describe_collection(made, Role.OWN, user), status=201)
    roles = held(user)
    found = (
        Collection.objects.filter(Q(kind=Collection.Kind.PERSONAL, owner=user) | Q(pk__in=roles))
        .prefetch_related(Prefetch("keys", Key.objects.filter(user=user)))
        .order_by(Lower("name"))
    )
    return JsonResponse(
        {
            "collections": [
                describe_collection(collection, roles.get(collection.pk, Role.OWN), user)
                for collection in found
            ]
        }
    )


@api("PATCH", "DELETE")
def collection(request, pk):
    """A shared collection renamed or deleted by its owners; the company's are the
    administrator's to lay out, and one's own stays as long as the vault."""
    found, role = reached(request.user, pk, Role.OWN)
    if found.kind != Collection.Kind.SHARED:
        raise Refused(400, "not_shared")
    if request.method == "DELETE":
        found.delete()
        store.collect_later()
        return HttpResponse(status=204)
    found.name = name_of(body(request))
    found.save(update_fields=["name"])
    return JsonResponse(describe_collection(found, role, request.user))


def describe_members(collection: Collection, role: Role) -> dict:
    order = {"user": 0, "group": 1, "everyone": 2}
    members = [
        {"id": member.pk, "grantee": grantee(member), "role": member.role}
        for member in collection.members.select_related("user", "group")
    ]
    members.sort(
        key=lambda member: (
            order[member["grantee"]["kind"]],
            (member["grantee"]["name"] or "").casefold(),
        )
    )
    described = {"role": role, "members": members}
    if role == Role.OWN:
        reaching_users = list(audience(collection))
        keyed = set(collection.keys.values_list("user", flat=True))
        vaults = {
            found.user_id: found
            for found in Vault.objects.filter(user__in=[user.pk for user in reaching_users])
        }
        described["waiting"] = [
            {**describe_user(user), "public_key": encoded(vaults[user.pk].public_key)}
            for user in reaching_users
            if user.pk in vaults and user.pk not in keyed
        ]
        described["unset"] = [
            describe_user(user) for user in reaching_users if user.pk not in vaults
        ]
    return described


def grantee_of(data: dict) -> dict:
    """The user, group or everyone a role is given to, as the member's fields."""
    given = data.get("grantee")
    kind = given.get("kind") if isinstance(given, dict) else None
    pk = given.get("id") if isinstance(given, dict) else None
    if kind == "everyone":
        return {"user": None, "group": None}
    if kind == "user" and type(pk) is int:
        found = User.objects.filter(pk=pk, is_active=True).first()
        if found:
            return {"user": found, "group": None}
    if kind == "group" and type(pk) is int:
        found = Group.objects.filter(pk=pk).first()
        if found:
            return {"user": None, "group": found}
    raise Refused(400, "invalid_grantee")


def confirm(collection: Collection, by, entries) -> None:
    """The collection's key sealed to each user given, by an owner who holds it; or, for a
    company collection nobody holds a key to yet, its first, by an owner to themselves."""
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise Refused(400, "invalid_keys")
    for entry in sorted(entries, key=lambda entry: entry.get("user") != by.pk):
        user = entry.get("user")
        if not collection.keys.exists():
            if user != by.pk or not waiting(collection).filter(pk=by.pk).exists():
                raise Refused(400, "invalid_keys")
        elif not collection.keys.filter(user=by).exists():
            raise Refused(403, "no_key")
        elif type(user) is not int or not waiting(collection).filter(pk=user).exists():
            raise Refused(400, "invalid_keys")
        Key.objects.create(
            collection=collection, user_id=user, sealed=decoded(entry, "sealed"), confirmed_by=by
        )
        if user != by.pk:
            logged(Event.Kind.CONFIRMED, collection, by, subject=user)


@api("GET", "POST")
def members(request, pk):
    """Who the collection reaches and as what; to its owners also whom they still have to
    confirm. Owners of a shared collection give a role to a user, a group or everyone, sealing
    its key to whom it reaches as they do."""
    found, role = reached(request.user, pk)
    if found.kind == Collection.Kind.PERSONAL:
        raise Refused(400, "not_shared")
    if request.method == "POST":
        if role != Role.OWN:
            raise Refused(403, "forbidden")
        if found.kind == Collection.Kind.COMPANY:
            raise Refused(400, "not_shared")
        data = body(request)
        who, given = grantee_of(data), role_of(data)
        with transaction.atomic():
            member, _ = Member.objects.update_or_create(
                collection=found, **who, defaults={"role": given, "created_by": request.user}
            )
            logged(Event.Kind.SHARED, found, request.user, grantee=grantee(member), role=given)
            confirm(found, request.user, data.get("keys", []))
            owned(found)
    return JsonResponse(describe_members(found, role))


@api("PATCH", "DELETE")
def member(request, pk):
    """A member's role changed or taken away by the owners of a shared collection, or a user
    leaving it."""
    found = Member.objects.select_related("collection", "user", "group").filter(pk=pk).first()
    role = found and role_in(request.user, found.collection)
    if not role:
        raise Refused(404, "not_found")
    collection = found.collection
    leaving = request.method == "DELETE" and found.user_id == request.user.pk
    if collection.kind != Collection.Kind.SHARED:
        raise Refused(400, "not_shared")
    if role != Role.OWN and not leaving:
        raise Refused(403, "forbidden")
    with transaction.atomic():
        if request.method == "DELETE":
            logged(Event.Kind.SHARED, collection, request.user, grantee=grantee(found), role=None)
            found.delete()
        else:
            found.role = role_of(body(request))
            found.save(update_fields=["role"])
            logged(
                Event.Kind.SHARED, collection, request.user, grantee=grantee(found), role=found.role
            )
        owned(collection)
        collection.keys.exclude(user__in=audience(collection)).delete()
    now = role_in(request.user, collection)
    if not now:
        return HttpResponse(status=204)
    return JsonResponse(describe_members(collection, now))


@api("POST")
def keys(request, pk):
    """New members confirmed: the collection's key sealed to each by an owner who holds it."""
    found, role = reached(request.user, pk, Role.OWN)
    if found.kind == Collection.Kind.PERSONAL:
        raise Refused(400, "not_shared")
    with transaction.atomic():
        confirm(found, request.user, body(request).get("keys"))
    return JsonResponse(describe_members(found, role))


def describe_folder(folder: Folder) -> dict:
    return {"id": folder.pk, "parent": folder.parent_id, "name": encoded(folder.name)}


def folder_in(collection: Collection, pk) -> Folder | None:
    """The folder of the collection a request names, none for the collection's top."""
    if pk in (None, ""):
        return None
    found = Folder.objects.filter(pk=optional_id(pk), collection=collection).first()
    if found is None:
        raise Refused(400, "invalid_folder")
    return found


@api("GET", "POST")
def folders(request, pk):
    """A collection's folders, made by those who edit it, as many at once as an import or a
    sorting needs: each with the id its browser gave it, after its parent."""
    if request.method == "GET":
        found, _ = reached(request.user, pk)
        shown = found.folders.order_by("created_at")
        return JsonResponse({"folders": [describe_folder(each) for each in shown]})
    found, _ = reached(request.user, pk, Role.EDIT)
    given = body(request).get("folders")
    if not isinstance(given, list) or not 0 < len(given) <= BATCH:
        raise Refused(400, "invalid_folders")
    if not all(isinstance(each, dict) for each in given):
        raise Refused(400, "invalid_folders")
    made = []
    try:
        with transaction.atomic():
            for each in given:
                if (pk := optional_id(each.get("id"))) is None:
                    raise Refused(400, "invalid_folders")
                made.append(
                    Folder.objects.create(
                        pk=pk,
                        collection=found,
                        parent=folder_in(found, each.get("parent")),
                        name=decoded(each, "name"),
                        created_by=request.user,
                    )
                )
    except IntegrityError:
        raise Refused(409, "folder_exists") from None
    return JsonResponse({"folders": [describe_folder(each) for each in made]}, status=201)


@api("PATCH", "DELETE")
def folder(request, pk):
    """A folder renamed, moved under another of its collection's, or deleted."""
    found = Folder.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    collection, _ = reached(request.user, found.collection_id, Role.EDIT)
    if request.method == "DELETE":
        found.delete()
        return HttpResponse(status=204)
    data = body(request)
    if "name" in data:
        found.name = decoded(data, "name")
    if "parent" in data:
        parent = folder_in(collection, data["parent"])
        above = parent
        while above is not None:
            if above.pk == found.pk:
                raise Refused(400, "invalid_folder")
            above = above.parent
        found.parent = parent
    found.save()
    return JsonResponse(describe_folder(found))


def describe_item(item: Item) -> dict:
    return {
        "id": item.pk,
        "collection": item.collection_id,
        "folder": item.folder_id,
        "key": encoded(item.key),
        "data": encoded(item.data),
        "attachments": [
            {"id": attachment.pk, "meta": encoded(attachment.meta), "size": attachment.blob.size}
            for attachment in item.attachments.all()
        ],
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "updated_by": item.updated_by and describe_user(item.updated_by),
        "trashed_at": item.trashed_at,
    }


def listed(items: QuerySet[Item]) -> QuerySet[Item]:
    return items.select_related("updated_by").prefetch_related(
        Prefetch("attachments", Attachment.objects.select_related("blob").order_by("created_at"))
    )


def live_item(user, pk, needs: Role = Role.READ, trashed: bool = False) -> Item:
    found = Item.objects.filter(pk=pk, trashed_at__isnull=not trashed).first()
    if found is None:
        raise Refused(404, "not_found")
    reached(user, found.collection_id, needs)
    return found


def filing(collection: Collection):
    """The folder of the collection a request names, by a lookup of its folders made once."""
    held = set(collection.folders.values_list("pk", flat=True))

    def filed(pk) -> uuid.UUID | None:
        if pk in (None, ""):
            return None
        if (found := optional_id(pk)) not in held:
            raise Refused(400, "invalid_folder")
        return found

    return filed


@api("GET", "POST", "PATCH")
def items(request, pk):
    """A collection's items: listed, made as many at once as an import brings, or filed into its
    folders, each item into the one named for it."""
    if request.method == "PATCH":
        found, _ = reached(request.user, pk, Role.EDIT)
        given = body(request).get("folders")
        if not isinstance(given, dict) or not 0 < len(given) <= LISTED:
            raise Refused(400, "invalid_items")
        filed, into = filing(found), defaultdict(list)
        for item, folder in given.items():
            into[filed(folder)].append(optional_id(item))
        with transaction.atomic():
            for folder, chosen in into.items():
                Item.objects.filter(pk__in=chosen, collection=found, trashed_at=None).update(
                    folder=folder
                )
        return HttpResponse(status=204)
    if request.method == "POST":
        found, _ = reached(request.user, pk, Role.EDIT)
        data = body(request)
        given = data.get("items")
        if not isinstance(given, list) or not 0 < len(given) <= BATCH:
            raise Refused(400, "invalid_items")
        if not all(isinstance(each, dict) for each in given):
            raise Refused(400, "invalid_items")
        filed = filing(found)
        made = Item.objects.bulk_create(
            Item(
                collection=found,
                folder_id=filed(each.get("folder")),
                key=decoded(each, "key"),
                data=decoded(each, "data", LARGE),
                created_by=request.user,
                updated_by=request.user,
            )
            for each in given
        )
        shown = listed(Item.objects.filter(pk__in=[item.pk for item in made])).order_by(
            "created_at"
        )
        return JsonResponse({"items": [describe_item(item) for item in shown]}, status=201)
    found, _ = reached(request.user, pk)
    logged(Event.Kind.OPENED, found, request.user)
    shown = listed(found.items.filter(trashed_at=None)).order_by("created_at")
    return JsonResponse({"items": [describe_item(item) for item in shown]})


# What a sorting lets out of an item: its name and the host of its site, as long as they may be.
ENTRIES = 5000
NAMED = 200
HOST = 253


def entries_of(data: dict) -> list[tuple[str, str]]:
    given = data.get("entries")
    if not isinstance(given, list) or not 0 < len(given) <= ENTRIES:
        raise Refused(400, "invalid_entries")
    found = []
    for each in given:
        name = each.get("name") if isinstance(each, dict) else None
        host = each.get("host") if isinstance(each, dict) else None
        if not (isinstance(name, str) and isinstance(host, str)):
            raise Refused(400, "invalid_entries")
        if len(name) > NAMED or len(host) > HOST:
            raise Refused(400, "invalid_entries")
        found.append((name, host))
    return found


@api("POST")
async def sorting(request, pk):
    """Folders a model proposes for the items the browser lets out by their names and the hosts
    of their sites, which the user agrees to each time."""
    data = body(request)
    entries = entries_of(data)
    existing = data.get("existing", [])
    if not isinstance(existing, list) or len(existing) > BATCH:
        raise Refused(400, "invalid_folders")
    if not all(isinstance(name, str) and len(name) <= NAMED for name in existing):
        raise Refused(400, "invalid_folders")
    language = data.get("language")
    if language not in LANGUAGES:
        raise Refused(400, "invalid_language")
    if data.get("consent") not in (None, "once"):
        raise Refused(400, "invalid_consent")
    found, _ = await database(reached)(request.user, pk, Role.EDIT)
    if not await database(installation.enabled)():
        raise Refused(409, "ai_off")
    if data.get("consent") != "once":
        raise Refused(428, "consent_needed")
    try:
        proposal = await propose(request.user, found, entries, existing, language)
    except Unsorted as unsorted:
        raise Refused(502, unsorted.code) from None
    return JsonResponse({"folders": proposal})


@api("PATCH", "DELETE")
def item(request, pk):
    """An item changed, moved to another collection with its key wrapped for that one, or put
    in the trash."""
    found = live_item(request.user, pk, Role.EDIT)
    if request.method == "DELETE":
        found.trashed_at = timezone.now()
        found.updated_by = request.user
        found.save(update_fields=["trashed_at", "updated_by", "updated_at"])
        return HttpResponse(status=204)
    data = body(request)
    if "data" in data:
        found.data = decoded(data, "data", LARGE)
    if "collection" in data:
        target, _ = reached(request.user, optional_id(data["collection"]), Role.EDIT)
        found.collection = target
        found.key = decoded(data, "key")
        found.folder = folder_in(target, data.get("folder"))
    elif "folder" in data:
        found.folder = folder_in(found.collection, data["folder"])
    found.updated_by = request.user
    found.save()
    return JsonResponse(describe_item(listed(Item.objects).get(pk=found.pk)))


@api("POST")
def seen(request, pk):
    """A password or a one-time code shown or copied, which the collection's owners read in its
    log."""
    found = live_item(request.user, pk)
    field = body(request).get("field")
    if field not in SEEN:
        raise Refused(400, "invalid_field")
    logged(Event.Kind.SEEN, found.collection, request.user, item=found, field=field)
    return HttpResponse(status=204)


@api("POST")
def attachments(request, pk):
    """A file sealed in the browser, uploaded to the store, kept with the item."""
    found = live_item(request.user, pk, Role.EDIT)
    data = body(request)
    sha256 = data.get("blob")
    blob = Blob.objects.filter(pk=sha256).first() if isinstance(sha256, str) else None
    if blob is None:
        raise Refused(400, "invalid_blob")
    made = Attachment.objects.create(
        item=found, blob=blob, meta=decoded(data, "meta"), created_by=request.user
    )
    found.updated_by = request.user
    found.save(update_fields=["updated_by", "updated_at"])
    return JsonResponse({"id": made.pk, "meta": encoded(made.meta), "size": blob.size}, status=201)


@api("GET", "DELETE")
def attachment(request, pk):
    found = Attachment.objects.select_related("blob").filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        live_item(request.user, found.item_id, Role.EDIT)
        found.delete()
        store.collect_later()
        return HttpResponse(status=204)
    live_item(request.user, found.item_id)
    return serve(request, found.blob, "sealed")


@api("GET")
def trash(request):
    """The items put in the trash of every collection the user can edit."""
    roles = held(request.user)
    editable = [pk for pk, role in roles.items() if covers(role, Role.EDIT)]
    found = Item.objects.filter(
        Q(collection__kind=Collection.Kind.PERSONAL, collection__owner=request.user)
        | Q(collection__in=editable),
        trashed_at__isnull=False,
    )
    return JsonResponse(
        {"items": [describe_item(item) for item in listed(found).order_by("-trashed_at")]}
    )


def trashed_items(user, needs: Role, data: dict) -> list[uuid.UUID]:
    given = data.get("items")
    if not isinstance(given, list) or not 0 < len(given) <= LISTED:
        raise Refused(400, "invalid_items")
    return [live_item(user, optional_id(pk), needs, trashed=True).pk for pk in dict.fromkeys(given)]


@api("POST")
def restore(request):
    chosen = trashed_items(request.user, Role.EDIT, body(request))
    Item.objects.filter(pk__in=chosen).update(trashed_at=None, updated_at=timezone.now())
    return HttpResponse(status=204)


@api("POST")
def purge(request):
    Item.objects.filter(pk__in=trashed_items(request.user, Role.OWN, body(request))).delete()
    store.collect_later()
    return HttpResponse(status=204)


@api("POST", confirmed=("POST",))
def exported(request, pk):
    """A collection about to be exported by one of its owners, which its log keeps."""
    found, _ = reached(request.user, pk, Role.OWN)
    logged(Event.Kind.EXPORTED, found, request.user)
    return HttpResponse(status=204)


@api("GET")
def log(request, pk):
    """Who opened the collection, saw its passwords, shared, confirmed and exported it, the
    latest first."""
    found, _ = reached(request.user, pk, Role.OWN)
    if found.kind == Collection.Kind.PERSONAL:
        raise Refused(400, "not_shared")
    events = (
        Event.objects.filter(collection=found)
        .select_related("user", "subject")
        .order_by("-at")[:LOGGED]
    )
    return JsonResponse(
        {
            "events": [
                {
                    "kind": event.kind,
                    "user": event.user and describe_user(event.user),
                    "subject": event.subject and describe_user(event.subject),
                    "item": event.item_id,
                    "detail": event.detail,
                    "at": event.at,
                }
                for event in events
            ]
        }
    )
