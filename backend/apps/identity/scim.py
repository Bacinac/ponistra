"""SCIM 2.0 (RFC 7643, 7644) for a directory that writes its people and groups here itself, such
as Entra ID's or Okta's provisioning (U1). The directory signs in with the token an administrator
was shown once; what it may change is the provider's people and groups, never anyone else's."""

import hashlib
import json
import re
from functools import wraps

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.collab.server import revoke
from apps.users.models import User
from apps.vault.views import settle

from . import people
from .models import Identity, Kept, Provider
from .people import Person, Refusal

CORE_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
CORE_GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
CONFIG = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
RESOURCE_TYPE = "urn:ietf:params:scim:schemas:core:2.0:ResourceType"
TYPE = "application/scim+json"
MOST = 200
FILTER = re.compile(r'^\s*([\w.\[\]" ]+?)\s+eq\s+"((?:[^"\\]|\\.)*)"\s*$', re.IGNORECASE)
MEMBER = re.compile(r'^members\[\s*value\s+eq\s+"([^"]*)"\s*\]$', re.IGNORECASE)


class Failed(Exception):
    def __init__(self, status: int, detail: str, kind: str = ""):
        super().__init__(detail)
        self.status, self.detail, self.kind = status, detail, kind


def base() -> str:
    return f"{settings.PUBLIC_URL}/api/scim/v2"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def answered(data: dict, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status, content_type=TYPE)


def scim(view):
    """A SCIM call, by the directory whose token it carries."""

    @csrf_exempt
    @wraps(view)
    def call(request, *args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        provider = (
            Provider.objects.filter(
                kind=Provider.Kind.SCIM, enabled=True, token_digest=digest(token.strip())
            ).first()
            if scheme.lower() == "bearer" and token.strip()
            else None
        )
        try:
            if provider is None:
                raise Failed(401, "unauthorized")
            return view(request, provider, *args, **kwargs)
        except Failed as failed:
            given = {"schemas": [ERROR], "status": str(failed.status), "detail": failed.detail}
            if failed.kind:
                given["scimType"] = failed.kind
            return answered(given, failed.status)

    return call


def _body(request) -> dict:
    try:
        found = json.loads(request.body or b"{}")
    except ValueError:
        raise Failed(400, "invalid JSON", "invalidSyntax") from None
    if not isinstance(found, dict):
        raise Failed(400, "invalid JSON", "invalidSyntax")
    return found


def _flag(value) -> bool:
    # Entra ID sends booleans as the strings "True" and "False" in a patch.
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _filtered(request, names: dict) -> tuple[str, str] | None:
    given = request.GET.get("filter")
    if not given:
        return None
    found = FILTER.match(given)
    if not found:
        raise Failed(400, "only one equality is understood", "invalidFilter")
    attribute = re.sub(r"\s+", "", found.group(1))
    key = next((key for name, key in names.items() if name.lower() == attribute.lower()), None)
    if key is None:
        raise Failed(400, f"{attribute} cannot be filtered on", "invalidFilter")
    return key, found.group(2).replace('\\"', '"').replace("\\\\", "\\")


def _listed(request, found: list, describe) -> JsonResponse:
    try:
        start = max(int(request.GET.get("startIndex", 1)), 1)
        count = min(max(int(request.GET.get("count", MOST)), 0), MOST)
    except ValueError:
        raise Failed(400, "invalid paging", "invalidValue") from None
    page = found[start - 1 : start - 1 + count]
    return answered(
        {
            "schemas": [LIST],
            "totalResults": len(found),
            "startIndex": start,
            "itemsPerPage": len(page),
            "Resources": [describe(each) for each in page],
        }
    )


def _refused(refusal: Refusal) -> Failed:
    if refusal.code == "no_account":
        return Failed(409, "this directory may not add accounts", "uniqueness")
    return Failed(400, refusal.code, "invalidValue")


# Users


def _subject(provider: Provider, user: User) -> str:
    found = Identity.objects.filter(provider=provider, user=user).first()
    return found.subject if found else ""


def describe_user(provider: Provider, user: User) -> dict:
    subject = _subject(provider, user)
    given = {
        "schemas": [CORE_USER],
        "id": str(user.pk),
        "userName": user.email,
        "name": {"givenName": user.first_name, "familyName": user.last_name},
        "displayName": user.get_full_name() or user.email,
        "emails": [{"value": user.email, "type": "work", "primary": True}],
        "active": user.is_active,
        "meta": {"resourceType": "User", "location": f"{base()}/Users/{user.pk}"},
    }
    if subject and subject != user.email:
        given["externalId"] = subject
    return given


def _reached(provider: Provider):
    """The people the directory may read and write: its own, and, to take them in, those of its
    domains it has not yet named."""
    own = User.objects.filter(identities__provider=provider)
    if not provider.domains:
        return own
    domains = Q()
    for domain in provider.domains:
        domains |= Q(email__iendswith=f"@{domain}")
    return (own | User.objects.filter(domains)).distinct()


def _user(provider: Provider, pk: str, taking: bool) -> User:
    reached = _reached(provider) if taking else User.objects.filter(identities__provider=provider)
    found = reached.filter(pk=pk).first() if pk.isdigit() else None
    if found is None:
        raise Failed(404, "no such user")
    return found


def _state(provider: Provider, user: User) -> dict:
    return {
        "userName": user.email,
        "externalId": _subject(provider, user),
        "givenName": user.first_name,
        "familyName": user.last_name,
        "email": "",
        "active": user.is_active,
    }


def _taken(state: dict, given: dict) -> None:
    """What a resource written whole or in part says of the person, into the state."""
    for key in ("userName", "externalId"):
        if key in given and given[key] is not None:
            state[key] = str(given[key])
    if isinstance(given.get("name"), dict):
        for key in ("givenName", "familyName"):
            if key in given["name"]:
                state[key] = str(given["name"][key] or "")
    for key in ("name.givenName", "name.familyName"):
        if key in given:
            state[key.partition(".")[2]] = str(given[key] or "")
    emails = given.get("emails")
    if isinstance(emails, list) and emails:
        chosen = next(
            (each for each in emails if isinstance(each, dict) and each.get("primary")), None
        )
        chosen = chosen or next((each for each in emails if isinstance(each, dict)), {})
        state["email"] = str(chosen.get("value") or "")
    for key in ('emails[type eq "work"].value', "emails.value"):
        if key in given:
            state["email"] = str(given[key] or "")
    if "active" in given:
        state["active"] = _flag(given["active"])


def _person(state: dict) -> Person:
    return Person(
        subject=state["externalId"] or state["userName"],
        email=state["email"] or state["userName"],
        first_name=state["givenName"],
        last_name=state["familyName"],
        active=state["active"],
    )


def _kept(provider: Provider, user: User | None, state: dict) -> User:
    """The person written, linked to the user the call names where it names one."""
    person = _person(state)
    try:
        with transaction.atomic():
            if user is not None:
                Identity.objects.filter(provider=provider, subject=person.subject).exclude(
                    user=user
                ).delete()
                Identity.objects.update_or_create(
                    provider=provider, user=user, defaults={"subject": person.subject}
                )
            kept = people.kept(provider, person)
    except Refusal as refusal:
        raise _refused(refusal) from None
    revoke()
    return kept


def _patched(state: dict, operations) -> None:
    if not isinstance(operations, list):
        raise Failed(400, "Operations is required", "invalidSyntax")
    for operation in operations:
        if not isinstance(operation, dict):
            raise Failed(400, "invalid operation", "invalidSyntax")
        kind = str(operation.get("op", "")).lower()
        path, value = operation.get("path"), operation.get("value")
        if kind not in ("add", "replace", "remove"):
            raise Failed(400, f"unknown op {kind}", "invalidSyntax")
        if path is None:
            if not isinstance(value, dict):
                raise Failed(400, "a patch without a path takes an object", "invalidValue")
            _taken(state, value)
        elif kind == "remove":
            _taken(state, {path: "" if path != "active" else False})
        else:
            _taken(state, {path: value})


@scim
def users(request, provider: Provider):
    if request.method == "GET":
        found = _filtered(
            request,
            {
                "userName": "email",
                "emails.value": "email",
                'emails[type eq "work"].value': "email",
                "externalId": "subject",
                "id": "pk",
            },
        )
        if found is None:
            listed = User.objects.filter(identities__provider=provider)
        elif found[0] == "email":
            listed = _reached(provider).filter(email=found[1].strip().lower())
        elif found[0] == "subject":
            listed = User.objects.filter(
                identities__provider=provider, identities__subject=found[1]
            )
        else:
            listed = (
                User.objects.filter(identities__provider=provider, pk=found[1])
                if found[1].isdigit()
                else User.objects.none()
            )
        return _listed(
            request,
            list(listed.order_by("pk")),
            lambda user: describe_user(provider, user),
        )
    if request.method != "POST":
        raise Failed(405, "method not allowed")
    state = {
        "userName": "",
        "externalId": "",
        "givenName": "",
        "familyName": "",
        "email": "",
        "active": True,
    }
    _taken(state, _body(request))
    if not state["userName"]:
        raise Failed(400, "userName is required", "invalidValue")
    if User.everyone.filter(
        email=(state["email"] or state["userName"]).strip().lower(), identities__provider=provider
    ).exists():
        raise Failed(409, "userName is taken", "uniqueness")
    return answered(describe_user(provider, _kept(provider, None, state)), 201)


@scim
def user(request, provider: Provider, pk: str):
    found = _user(provider, pk, request.method in ("PUT", "PATCH"))
    if request.method == "GET":
        return answered(describe_user(provider, found))
    if request.method == "DELETE":
        people.left(provider, found)
        revoke()
        return HttpResponse(status=204)
    state = _state(provider, found)
    if request.method == "PUT":
        _taken(state, _body(request))
    elif request.method == "PATCH":
        _patched(state, _body(request).get("Operations"))
    else:
        raise Failed(405, "method not allowed")
    return answered(describe_user(provider, _kept(provider, found, state)))


# Groups


def describe_group(provider: Provider, group: Group, members: bool = True) -> dict:
    given = {
        "schemas": [CORE_GROUP],
        "id": str(group.pk),
        "displayName": group.name,
        "meta": {"resourceType": "Group", "location": f"{base()}/Groups/{group.pk}"},
    }
    kept = Kept.objects.filter(group=group, provider=provider).first()
    if kept and kept.subject != group.name:
        given["externalId"] = kept.subject
    if members:
        given["members"] = [
            {"value": str(each.pk), "display": each.get_full_name() or each.email}
            for each in group.user_set.order_by("pk")
        ]
    return given


def _group(provider: Provider, pk: str) -> Group:
    found = Group.objects.filter(pk=pk, kept__provider=provider).first() if pk.isdigit() else None
    if found is None:
        raise Failed(404, "no such group")
    return found


def _members(given) -> list[User]:
    if not isinstance(given, list):
        raise Failed(400, "members is a list", "invalidValue")
    named = {str(each.get("value", "")) for each in given if isinstance(each, dict)}
    return list(User.objects.filter(pk__in=[each for each in named if each.isdigit()]))


def _regrouped(change) -> None:
    with transaction.atomic():
        change()
        settle()
    revoke()


def _shown(request) -> bool:
    return "members" not in request.GET.get("excludedAttributes", "")


@scim
def groups(request, provider: Provider):
    if request.method == "GET":
        found = _filtered(request, {"displayName": "name", "externalId": "subject", "id": "pk"})
        listed = Group.objects.filter(kept__provider=provider)
        if found and found[0] == "name":
            listed = listed.filter(name=found[1])
        elif found and found[0] == "subject":
            listed = listed.filter(kept__subject=found[1])
        elif found:
            listed = listed.filter(pk=found[1]) if found[1].isdigit() else listed.none()
        shown = _shown(request)
        return _listed(
            request,
            list(listed.order_by("pk")),
            lambda group: describe_group(provider, group, shown),
        )
    if request.method != "POST":
        raise Failed(405, "method not allowed")
    data = _body(request)
    name = str(data.get("displayName") or "").strip()
    if not name:
        raise Failed(400, "displayName is required", "invalidValue")
    subject = str(data.get("externalId") or name)
    if Kept.objects.filter(provider=provider, subject=subject).exists():
        raise Failed(409, "the group exists", "uniqueness")
    made: list[Group] = []

    def change() -> None:
        made.append(people.group(provider, subject, name))
        if "members" in data:
            made[0].user_set.set(_members(data["members"]))

    _regrouped(change)
    return answered(describe_group(provider, made[0]), 201)


def _group_patched(provider: Provider, group: Group, operations) -> None:
    if not isinstance(operations, list):
        raise Failed(400, "Operations is required", "invalidSyntax")
    for operation in operations:
        if not isinstance(operation, dict):
            raise Failed(400, "invalid operation", "invalidSyntax")
        kind = str(operation.get("op", "")).lower()
        path = str(operation.get("path") or "")
        value = operation.get("value")
        if not path and isinstance(value, dict):
            for key, each in value.items():
                _group_patched(provider, group, [{"op": kind, "path": key, "value": each}])
            continue
        one = MEMBER.match(path)
        if path.lower() == "displayname" and kind in ("add", "replace"):
            people.group(provider, Kept.objects.get(group=group).subject, str(value or ""))
        elif path.lower() == "externalid":
            Kept.objects.filter(group=group).update(subject=str(value or group.name))
        elif path.lower() == "members" and kind == "add":
            group.user_set.add(*_members(value))
        elif path.lower() == "members" and kind == "replace":
            group.user_set.set(_members(value))
        elif path.lower() == "members" and kind == "remove":
            if value is None:
                group.user_set.clear()
            else:
                group.user_set.remove(*_members(value))
        elif one and kind == "remove":
            group.user_set.remove(
                *User.objects.filter(pk=one.group(1)) if one.group(1).isdigit() else []
            )
        else:
            raise Failed(400, f"{kind} {path} is not understood", "invalidPath")


@scim
def group(request, provider: Provider, pk: str):
    found = _group(provider, pk)
    if request.method == "GET":
        return answered(describe_group(provider, found, _shown(request)))
    if request.method == "DELETE":
        people.gone(provider, found)
        revoke()
        return HttpResponse(status=204)
    data = _body(request)
    if request.method == "PUT":

        def change() -> None:
            name = str(data.get("displayName") or found.name)
            people.group(provider, Kept.objects.get(group=found).subject, name)
            if "members" in data:
                found.user_set.set(_members(data["members"]))

    elif request.method == "PATCH":

        def change() -> None:
            _group_patched(provider, found, data.get("Operations"))

    else:
        raise Failed(405, "method not allowed")
    _regrouped(change)
    found.refresh_from_db()
    return answered(describe_group(provider, found))


# What the directory reads of the server


@scim
def configuration(request, provider: Provider):
    return answered(
        {
            "schemas": [CONFIG],
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": True, "maxResults": MOST},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "type": "oauthbearertoken",
                    "name": "Bearer",
                    "description": "The token shown once",
                }
            ],
            "meta": {"resourceType": "ServiceProviderConfig"},
        }
    )


@scim
def resource_types(request, provider: Provider):
    found = [
        {
            "schemas": [RESOURCE_TYPE],
            "id": "User",
            "name": "User",
            "endpoint": "/Users",
            "schema": CORE_USER,
        },
        {
            "schemas": [RESOURCE_TYPE],
            "id": "Group",
            "name": "Group",
            "endpoint": "/Groups",
            "schema": CORE_GROUP,
        },
    ]
    return answered(
        {
            "schemas": [LIST],
            "totalResults": 2,
            "startIndex": 1,
            "itemsPerPage": 2,
            "Resources": found,
        }
    )
