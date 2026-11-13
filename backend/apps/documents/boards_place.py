"""The page of boards (D47): the user's own folder of boards, whose folders are its groups, and
the boards others share from theirs. A page of HTML kept anywhere else is a file like any other."""

from django.db import transaction
from django.db.models.expressions import RawSQL
from django.http import JsonResponse

from apps.access import rights
from apps.access.models import Role
from apps.core.api import Refused, api, body, optional_id

from . import boards
from .launcher import group_named, new_place
from .models import Node
from .views import along, describe, folder, listing, live, moved_into, title_of

# The browser holds the user's language; an agent's call makes the folder in the installation's.


def _folder_of(user) -> Node | None:
    return Node.objects.filter(created_by=user, boards=True, trashed_at=None).first()


def group_of(user, name: str) -> Node:
    """The group of that name in the user's folder of boards, made where there is none."""
    with transaction.atomic():
        place = _folder_of(user) or new_place(user, "boards")
        Node.objects.select_for_update().get(pk=place.pk)
        return group_named(place, name, user)


def filed(user, node: Node, reach: rights.Reach, name: str) -> None:
    """The board in the group of that name, on the user's page from wherever it was."""
    if not boards.is_board(node):
        raise Refused(400, "not_a_board")
    group = group_of(user, name)
    if node.parent_id != group.pk:
        moved_into([(node, reach)], *folder(user, group.pk, Role.EDIT), user)


@api("GET", "POST")
def page(request):
    """The boards on the user's page, each saying the way to it and whether one on that way keeps
    it in the browser, as no one folder's listing can say that here; a POST files one in a group."""
    user = request.user
    if request.method == "POST":
        data = body(request)
        node, reach = live(user, optional_id(data.get("node")), Role.EDIT)
        filed(user, node, reach, title_of({"title": data.get("group")}))
        return JsonResponse(describe(node))
    readable, params = rights.readable(user)
    found = boards.among(Node.objects.filter(pk__in=RawSQL(readable, params)))
    reaches = {
        pk: reach
        for pk, reach in rights.reaches(user, found.values_list("pk", flat=True)).items()
        if reach.ancestry[0].boards
    }
    chains = [reach.ancestry for reach in reaches.values()]
    return JsonResponse(
        {
            "children": [
                {**node, "kept": reaches[node["id"]].confined, **along(reaches[node["id"]])}
                for node in listing(request, chains)
            ]
        }
    )
