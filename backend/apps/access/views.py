from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponse, JsonResponse

from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.documents import views as documents
from apps.users.models import User
from apps.users.views import describe as describe_user

from . import log, rights
from .models import Access, Grant, Role

# The latest entries of a node's log shown, those of the nodes below a folder among them.
LOGGED = 200


def describe(grant: Grant) -> dict:
    return {
        "id": grant.id,
        "grantee": rights.grantee(grant),
        "role": grant.role,
        "download": grant.download,
    }


def role_of(data: dict) -> Role:
    if data.get("role") not in Role.values:
        raise Refused(400, "invalid_role")
    return Role(data["role"])


def grantee_of(data: dict) -> dict:
    grantee = data.get("grantee")
    kind = isinstance(grantee, dict) and grantee.get("kind")
    if kind == "everyone":
        return {"user": None, "group": None}
    if kind == "user":
        user = User.objects.filter(pk=grantee.get("id"), is_active=True).first()
        if user is not None:
            return {"user": user, "group": None}
    if kind == "group":
        group = Group.objects.filter(pk=grantee.get("id")).first()
        if group is not None:
            return {"user": None, "group": group}
    raise Refused(400, "invalid_grantee")


@api("GET")
def access(request, pk):
    node, reach = documents.live(request.user, pk)
    seen = {above.pk for above in reach.path}
    titles = {above.pk: above.title for above in reach.ancestry}
    grants = []
    for grant in rights.ordered(rights.visible_grants(reach.ancestry)):
        source = None
        if grant.node_id != node.pk:
            # Folders above what the user can see are never named.
            shown = grant.node_id in seen
            source = {
                "id": grant.node_id if shown else None,
                "title": titles[grant.node_id] if shown else None,
            }
        grants.append({**describe(grant), "from": source})

    below = node.descendants()
    parents = {child.pk: child.parent_id for child in below}
    named = {child.pk: child for child in below}
    on: dict = {}
    for grant in rights.visible_grants(below):
        on.setdefault(grant.node_id, []).append(grant)
    widened = []
    for child in below:
        if child.pk not in on:
            continue
        path, step = [], child.pk
        while step != node.pk:
            path.append(named[step].title)
            step = parents[step]
        widened.append(
            {
                "node": documents.describe(child),
                "path": path[::-1],
                "grants": [describe(grant) for grant in rights.ordered(on[child.pk])],
            }
        )
    return JsonResponse({"role": reach.role, "grants": grants, "below": widened})


@api("POST")
def grants(request, pk):
    node, _ = documents.live(request.user, pk, Role.OWN)
    documents.laid_out(node)
    data = body(request)
    role = role_of(data)
    grantee = grantee_of(data)
    with transaction.atomic():
        grant = Grant.objects.filter(node=node, **grantee).first()
        if grant is not None:
            change(grant, role)
        else:
            grant = Grant.objects.create(node=node, role=role, created_by=request.user, **grantee)
        log.shared(request.user, grant, role)
    revoke()
    return JsonResponse(describe(grant), status=201)


def change(grant: Grant, role: Role | None) -> None:
    """Gives a grant another role, or removes it with None; a top-level node keeps
    at least one owner."""
    if role != Role.OWN and rights.orphaned(Grant.objects.filter(pk=grant.pk)).exists():
        raise Refused(400, "last_owner")
    if role is None:
        grant.delete()
    else:
        grant.role = role
        grant.save(update_fields=["role"])


@api("PATCH", "DELETE")
def grant(request, pk):
    grant = Grant.objects.select_related("node", "user", "group").filter(pk=pk).first()
    if grant is None:
        raise Refused(404, "not_found")
    documents.live(request.user, grant.node_id, Role.OWN)
    documents.laid_out(grant.node)
    data = {} if request.method == "DELETE" else body(request)
    role = (
        None
        if request.method == "DELETE"
        else role_of(data | {"role": data.get("role", grant.role)})
    )
    if grant.user_id and grant.user.visitor and role == Role.OWN:
        raise Refused(400, "invalid_role")
    download = data.get("download", grant.download)
    if not isinstance(download, bool):
        raise Refused(400, "invalid_download")
    with transaction.atomic():
        if role != grant.role:
            log.shared(request.user, grant, role)
        change(grant, role)
        if role is not None and download != grant.download:
            grant.download = download
            grant.save(update_fields=["download"])
    revoke()
    if request.method == "DELETE":
        return HttpResponse(status=204)
    return JsonResponse(describe(grant))


@api("GET")
def people(request):
    users = User.objects.filter(is_active=True).prefetch_related("groups")
    return JsonResponse(
        {
            "users": sorted(
                (
                    {**describe_user(user), "groups": [group.pk for group in user.groups.all()]}
                    for user in users
                ),
                key=lambda user: user["name"].casefold(),
            ),
            "groups": [
                {"id": group.pk, "name": group.name} for group in Group.objects.order_by("name")
            ],
        }
    )


@api("GET")
def access_log(request, pk):
    """Who opened, downloaded and shared the node and those below it, the latest first."""
    node, _ = documents.live(request.user, pk, Role.OWN)
    named = {node.pk: node, **{below.pk: below for below in node.descendants()}}
    entries = (
        Access.objects.filter(node__in=named)
        .select_related("user__opened_link")
        .order_by("-at")[:LOGGED]
    )
    return JsonResponse(
        {
            "entries": [
                {
                    "node": {
                        "id": entry.node_id,
                        "kind": named[entry.node_id].kind,
                        "title": named[entry.node_id].title,
                        "href": named[entry.node_id].href or None,
                    },
                    "user": entry.user
                    and not hasattr(entry.user, "opened_link")
                    and describe_user(entry.user),
                    "kind": entry.kind,
                    "detail": entry.detail,
                    "at": entry.at,
                }
                for entry in entries
            ]
        }
    )
