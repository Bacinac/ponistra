"""A user's way out of Google (D44): their Google accounts, each Drive copied in and followed until
they finish leaving."""

from django.db import transaction
from django.http import HttpResponse, JsonResponse

from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.documents.models import Node
from apps.mail import signin
from apps.mail.models import Account, Provider
from apps.retention import kept as retention

from . import sync
from .models import Drive, Space


def _space(space: Space) -> dict:
    return {
        "folder": space.folder_id,
        "title": space.folder.title,
        "shared": space.shared,
        "found": {key: value for key, value in space.found.items() if key != "permissions"},
        "read_at": space.read_at,
    }


def describe(drive: Drive) -> dict:
    spaces = drive.spaces.select_related("folder").order_by("shared", "folder__title")
    return {
        "id": drive.pk,
        "state": drive.state,
        "error": drive.error,
        "finishing": drive.finishing,
        "read_at": drive.read_at,
        "spaces": [_space(each) for each in spaces],
    }


def _accounts(user) -> list[dict]:
    found = (
        user.mail_accounts.filter(login=Account.Login.GOOGLE)
        .select_related("drive")
        .order_by("address")
    )
    return [
        {
            "account": account.pk,
            "address": account.address,
            "drive": describe(account.drive) if hasattr(account, "drive") else None,
        }
        for account in found
    ]


def _drive(request, pk) -> Drive:
    found = Drive.objects.filter(pk=pk, user=request.user).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


@api("GET", "POST")
def drives(request):
    """The user's Google accounts with how far each one's Drive came, and a Drive begun."""
    if request.method == "GET":
        return JsonResponse(
            {
                "ready": Provider.GOOGLE in signin.ready(),
                "accounts": _accounts(request.user),
            }
        )
    given = body(request).get("account")
    account = request.user.mail_accounts.filter(
        pk=given if isinstance(given, int) else None, login=Account.Login.GOOGLE
    ).first()
    if account is None:
        raise Refused(404, "not_found")
    with transaction.atomic():
        drive, made = Drive.objects.get_or_create(account=account, defaults={"user": request.user})
        if not made:
            raise Refused(409, "begun")
        sync.wake()
    return JsonResponse(describe(drive), status=201)


@api("GET", "PATCH", "DELETE", confirmed=("DELETE",))
def drive(request, pk):
    """A Drive as it is; asked again once its user signed in to the account anew; or let go of,
    the copies it made taken away with it."""
    found = _drive(request, pk)
    if request.method == "GET":
        return JsonResponse(describe(found))
    if request.method == "PATCH":
        Drive.objects.filter(pk=found.pk).update(error="")
        sync.wake()
        found.refresh_from_db()
        return JsonResponse(describe(found))
    with transaction.atomic():
        locked = Drive.objects.select_for_update().get(pk=found.pk)
        folders = Node.objects.filter(pk__in=list(locked.spaces.values_list("folder", flat=True)))
        retention.refuse_nodes(folders)
        locked.spaces.all().delete()
        folders.delete()
        locked.delete()
        sync.wake()
    revoke()
    return HttpResponse(status=204)


@api("POST")
def finish(request, pk):
    """What changed last taken from Google, then the copies left the user's, no longer followed."""
    with transaction.atomic():
        found = Drive.objects.select_for_update().filter(pk=_drive(request, pk).pk).first()
        if found is None:
            raise Refused(404, "not_found")
        if found.state != Drive.State.READY:
            raise Refused(409, "not_copied")
        found.finishing = True
        found.save(update_fields=["finishing"])
        sync.wake()
    return JsonResponse(describe(found))
