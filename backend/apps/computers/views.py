"""Računala (C4.2, C4.8): the computers a person manages, the codes new ones enroll with, their
managers and sealed secrets, and the machine's own API reached through its link, as the person.

A manager reaches the whole of a machine's API; anyone else only the console and the snapshot
files of a guest the machine names them the owner of (decision z7), which the agent checks too."""

import json
import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.blobs import store
from apps.blobs.models import Upload
from apps.core.api import Refused, api, body, optional_id
from apps.core.asyncdb import database
from apps.core.sealed import opened
from apps.users.models import User
from apps.users.sessions import client_ip

from . import link, machine, streams
from .models import Code, Computer, Manager, Opening

CHANGES = ("POST", "DELETE")
LIFETIME = timedelta(days=7)
# Without look-alikes (0/O, 1/I/L), in groups of four: read off a screen and typed on a machine.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
GROUPS = 4
SECRETS = {
    "recovery-key": (Opening.Secret.RECOVERY_KEY, machine.RECOVERY_KEY),
    "backup-password": (Opening.Secret.BACKUP_PASSWORD, machine.BACKUP_PASSWORD),
}
GUEST = r"/v1/guests/(?P<guest>[^/?]+)"
# What a guest's owner who does not manage the machine reaches of it.
OWNED = [
    ("GET", re.compile(GUEST)),
    ("POST", re.compile(GUEST + r"/console")),
    ("GET", re.compile(GUEST + r"/snapshots")),
    ("GET", re.compile(GUEST + r"/snapshots/[^/?]+/files(\?.*)?")),
    ("POST", re.compile(GUEST + r"/snapshots/[^/?]+/files/restore")),
]


def _person(user) -> dict:
    return {"id": user.pk, "name": user.get_full_name() or user.email, "email": user.email}


def _orphaned():
    living = Manager.objects.filter(user__is_active=True).values("computer")
    return Computer.objects.exclude(pk__in=living)


def _described(found: Computer) -> dict:
    return {
        "id": str(found.pk),
        "name": found.name,
        "connected": link.connected(found),
        "connected_at": found.connected_at,
        "seen_at": found.seen_at,
        "agent": found.agent,
        "facts": found.facts,
        "alerts": found.alerts,
        "enrolled_at": found.enrolled_at,
        "left_at": found.left_at,
        "recovery_key_at": found.recovery_key_at,
        "backup_password_at": found.backup_password_at,
    }


def _code(found: Code) -> dict:
    return {
        "id": found.pk,
        "hint": found.hint,
        "made_at": found.made_at,
        "expires_at": found.expires_at,
    }


def _listed(user) -> dict:
    managed = Computer.objects.managed(user)
    codes = Code.objects.filter(made_by=user, used_at__isnull=True, expires_at__gt=timezone.now())
    return {
        "computers": [_described(each) for each in managed],
        "orphaned": [_described(each) for each in _orphaned()] if user.is_staff else [],
        "codes": [_code(each) for each in codes],
        "can_add": user.is_staff,
    }


def made_code() -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(GROUPS)) for _ in range(GROUPS))


def made(user) -> dict:
    if not user.is_staff:
        raise Refused(403, "forbidden")
    code = made_code()
    found = Code.objects.create(
        digest=machine.code_digest(code),
        hint=code[-4:],
        made_by=user,
        expires_at=timezone.now() + LIFETIME,
    )
    return {**_code(found), "code": code}


@api("GET", "POST", confirmed=("POST",))
def computers(request):
    """The computers the person manages, the codes they made that wait for a machine, and to an
    administrator the computers nobody manages any more; POST makes a code, shown only now."""
    if request.method == "POST":
        return JsonResponse(made(request.user), status=201)
    return JsonResponse(_listed(request.user))


@api("DELETE")
def code(request, pk: int):
    found = Code.objects.filter(pk=pk, made_by=request.user, used_at__isnull=True).first()
    if found is None:
        raise Refused(404, "not_found")
    found.delete()
    return HttpResponse(status=204)


def managed(user, pk) -> Computer:
    found = Computer.objects.managed(user).filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


def _detail(user, pk) -> dict:
    found = managed(user, pk)
    people = User.objects.filter(
        pk__in=Manager.objects.filter(computer=found).values("user")
    ).order_by("first_name", "last_name", "email")
    openings = Opening.objects.filter(computer=found).select_related("by")[:100]
    return {
        **_described(found),
        "managers": [_person(each) for each in people],
        "openings": [
            {
                "secret": each.secret,
                "by": each.by and _person(each.by),
                "at": each.at,
                "address": each.address,
            }
            for each in openings
        ],
    }


def _removed(user, pk) -> None:
    managed(user, pk).delete()


@api("GET", "DELETE", confirmed=("DELETE",))
async def computer(request, pk):
    """The computer, its managers and who opened its secrets; DELETE removes it from Ponistra with
    its key and password, which ends its link."""
    if request.method == "DELETE":
        await database(_removed)(request.user, pk)
        await link.dropped(pk)
        return HttpResponse(status=204)
    return JsonResponse(await database(_detail)(request.user, pk))


@api("POST", confirmed=("POST",))
def taken_over(request, pk):
    """An administrator takes over a computer nobody manages any more, as when its last manager
    was erased."""
    if not request.user.is_staff:
        raise Refused(403, "forbidden")
    found = _orphaned().filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    Manager.objects.get_or_create(computer=found, user=request.user)
    return HttpResponse(status=204)


@api("POST")
def managers(request, pk):
    found = managed(request.user, pk)
    given = body(request).get("user")
    person = (
        User.objects.filter(pk=given, is_active=True, visitor=False, mailbox=False).first()
        if type(given) is int
        else None
    )
    if person is None:
        raise Refused(400, "invalid_user")
    Manager.objects.get_or_create(computer=found, user=person)
    return HttpResponse(status=204)


@api("DELETE")
def manager(request, pk, user: int):
    found = managed(request.user, pk)
    with transaction.atomic():
        held = list(Manager.objects.select_for_update().filter(computer=found))
        if not any(each.user_id == user for each in held):
            raise Refused(404, "not_found")
        if len(held) == 1:
            raise Refused(409, "last_manager")
        Manager.objects.filter(computer=found, user_id=user).delete()
    return HttpResponse(status=204)


@api("POST", confirmed=("POST",))
def secret(request, pk, which: str):
    """The computer's recovery key or backup password, for its manager freshly confirmed; each
    opening is recorded on the computer."""
    if which not in SECRETS:
        raise Refused(404, "not_found")
    kind, purpose = SECRETS[which]
    found = managed(request.user, pk)
    field = kind.value
    sealed = getattr(found, field)
    if sealed is None:
        raise Refused(404, "not_kept")
    value = opened(purpose, sealed)
    if value is None:
        raise Refused(500, "secret_unreadable")
    Opening.objects.create(
        computer=found, secret=kind, by=request.user, address=client_ip(request) or None
    )
    return JsonResponse({"value": value, "at": getattr(found, f"{field}_at")})


def _reached(user, pk) -> tuple[Computer, bool]:
    found = Computer.objects.filter(pk=pk, left_at__isnull=True).first()
    if found is None:
        raise Refused(404, "not_found")
    return found, Computer.objects.managed(user).filter(pk=pk).exists()


def _given(request):
    if not request.body:
        return None
    try:
        return json.loads(request.body)
    except ValueError:
        raise Refused(400, "invalid_json") from None


async def _owns(found: Computer, account: str, path: str, method: str) -> bool:
    for allowed, pattern in OWNED:
        if method == allowed and (matched := pattern.fullmatch(path)):
            status, _, answer = await link.requested(
                found, "GET", f"/v1/guests/{matched['guest']}", account
            )
            if status != 200:
                return False
            try:
                return json.loads(answer).get("owner") == account
            except ValueError, AttributeError:
                return False
    return False


@api("GET", "POST", "PUT", "DELETE")
async def agent(request, pk, rest: str):
    """The machine's API at `/v1/…`, run on the machine as the person."""
    found, manages = await database(_reached)(request.user, pk)
    path = "/" + rest
    if query := request.META.get("QUERY_STRING"):
        path += "?" + query
    account = link.account(request.user)
    if not manages and not await _owns(found, account, path, request.method):
        raise Refused(403, "forbidden")
    status, content_type, answer = await link.requested(
        found, request.method, path, account, _given(request)
    )
    response = HttpResponse(answer, status=status, content_type=content_type or None)
    if not answer:
        del response["Content-Type"]
    return response


@database
def _upload(user, given) -> tuple[Upload, str]:
    found = Upload.objects.filter(pk=given, user=user, blob__isnull=False).first()
    if found is None:
        raise Refused(400, "invalid_upload")
    return found, str(store.path_of(found.blob_id))


@api("POST")
async def uploaded(request, pk, rest: str):
    """A file uploaded to Ponistra (`upload` names it) sent on as the body of the machine's
    request at `/v1/…`, through a stream of its own: an ISO is larger than a frame."""
    found, manages = await database(_reached)(request.user, pk)
    if not manages:
        raise Refused(403, "forbidden")
    given = optional_id(body(request).get("upload"))
    if given is None:
        raise Refused(400, "invalid_upload")
    held, place = await _upload(request.user, given)
    path = "/" + rest
    if query := request.META.get("QUERY_STRING"):
        path += "?" + query
    try:
        status, content_type, answer = await streams.uploaded(
            found, "POST", path, link.account(request.user), store.streamed(open(place, "rb"))
        )
    except streams.Refused as refused:
        raise Refused(refused.status, refused.error) from None
    finally:
        await database(held.delete)()
    response = HttpResponse(answer, status=status, content_type=content_type or None)
    if not answer:
        del response["Content-Type"]
    return response
