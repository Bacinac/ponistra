"""The company's folders, which an administrator lays out and gives to groups without a right to
read what is in them."""

from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponse, JsonResponse

from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.documents.models import Node
from apps.documents.views import BY_TITLE, title_of
from apps.retention import kept as retention
from apps.shares.views import describe as describe_share
from apps.users.accounts import administrator

from . import log
from .models import Grant, Role


def describe(node: Node) -> dict:
    grants = sorted(
        node.grants.all(),
        key=lambda grant: (grant.group is not None, grant.group and grant.group.name),
    )
    return {
        "id": node.pk,
        "title": node.title,
        "confined": node.confined,
        "share": describe_share(node.share) if hasattr(node, "share") else None,
        "grants": [
            {
                "group": grant.group and {"id": grant.group.pk, "name": grant.group.name},
                "role": grant.role,
            }
            for grant in grants
        ],
    }


def audience_of(data: dict) -> dict[int | None, Role]:
    """Each group's role, None standing for everyone; at least one of them owns the folder."""
    entries = data.get("grants")
    if not isinstance(entries, list):
        raise Refused(400, "invalid_grants")
    found: dict[int | None, Role] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("role") not in Role.values:
            raise Refused(400, "invalid_grants")
        group = entry.get("group")
        if group is not None and (
            type(group) is not int or not Group.objects.filter(pk=group).exists()
        ):
            raise Refused(400, "invalid_grantee")
        found[group] = Role(entry["role"])
    if Role.OWN not in found.values():
        raise Refused(400, "owner_required")
    return found


def given(node: Node, audience: dict[int | None, Role], by) -> None:
    """The folder's grants made those of the audience, each change logged."""
    held = {grant.group_id: grant for grant in node.grants.select_related("group")}
    for group, grant in held.items():
        if group not in audience:
            log.shared(by, grant, None)
            grant.delete()
    for group, role in audience.items():
        grant = held.get(group)
        if grant is None:
            grant = Grant.objects.create(node=node, group_id=group, role=role, created_by=by)
        elif grant.role == role:
            continue
        else:
            grant.role = role
            grant.save(update_fields=["role"])
        log.shared(by, grant, role)


def confined_of(data: dict) -> bool:
    if not isinstance(data.get("confined", False), bool):
        raise Refused(400, "invalid_confined")
    return data.get("confined", False)


@api("GET", "POST")
def folders(request):
    administrator(request)
    if request.method == "GET":
        found = Node.objects.filter(company=True).select_related("share")
        found = found.prefetch_related("grants__group")
        return JsonResponse({"folders": [describe(node) for node in found.order_by(BY_TITLE)]})
    data = body(request)
    title, audience, confined = title_of(data), audience_of(data), confined_of(data)
    with transaction.atomic():
        node = Node.objects.create(
            kind=Node.Kind.FOLDER,
            title=title,
            company=True,
            confined=confined,
            created_by=request.user,
            updated_by=request.user,
        )
        given(node, audience, request.user)
    return JsonResponse(describe(node), status=201)


@api("PATCH", "DELETE")
def folder(request, pk):
    administrator(request)
    node = Node.objects.filter(pk=pk, company=True).first()
    if node is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        if Node.objects.filter(parent=node).exists():
            raise Refused(409, "not_empty")
        retention.refuse_nodes([node])
        node.delete()
        return HttpResponse(status=204)
    data = body(request)
    with transaction.atomic():
        if "title" in data:
            node.title = title_of(data)
        if "confined" in data:
            node.confined = confined_of(data)
        node.updated_by = request.user
        node.save()
        if "grants" in data:
            given(node, audience_of(data), request.user)
    revoke()
    return JsonResponse(describe(node))
