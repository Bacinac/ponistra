"""The page of links (D31): the user's own folder of links, whose folders are its groups, beside
the links of the organisation's folders and of what others share with the user."""

from django.contrib.postgres.search import TrigramWordSimilarity
from django.db import transaction
from django.db.models.expressions import RawSQL
from django.http import JsonResponse

from apps.access import rights
from apps.core.api import api
from apps.search.pdf import folded
from apps.search.text import Folded

from . import links as readings
from .models import Node
from .views import LAID_OUT, along, arranged, created, describe, listing, new_link

MOST = 2_000
# How alike a spoken name must be to a part of a link's name to be it, and how far ahead of the
# next one it must be to be taken without asking.
LIKE = 0.6
AHEAD = 0.15
SPOKEN = 5


def folder_of(user) -> Node | None:
    return Node.objects.filter(created_by=user, links=True, trashed_at=None).first()


def new_place(user, flag: str) -> Node:
    """A place of the user's own at the top of their documents, told by the flag it raises; the
    interface names it by that flag in its own language, never by the title kept here."""
    place = created(None, Node.Kind.FOLDER, flag.capitalize(), None, user)
    setattr(place, flag, True)
    place.save(update_fields=[flag])
    return place


def group_named(place: Node, name: str, user) -> Node:
    found = (
        Node.objects.filter(
            parent=place, kind=Node.Kind.FOLDER, trashed_at=None, title__iexact=name
        )
        .order_by(*LAID_OUT)
        .first()
    )
    if found is not None:
        return found
    group = created(place, Node.Kind.FOLDER, name, None, user)
    arranged(place, [group], None)
    return group


def added(user, href: str, title: str, group: str | None) -> tuple[Node, bool]:
    """The link on the user's page, in the group of that name, made where there is none; a page
    already there stays as the user left it, and the second value is false."""
    with transaction.atomic():
        place = folder_of(user) or new_place(user, "links")
        Node.objects.select_for_update().get(pk=place.pk)
        into = group_named(place, group, user) if group else place
        found = Node.objects.filter(
            parent=into, kind=Node.Kind.LINK, href=href, trashed_at=None
        ).first()
        if found is not None:
            return found, False
        node = new_link(into, href, title, user)
        arranged(into, [node], None)
    readings.wake()
    return node, True


def _on_page(reach: rights.Reach, place: Node | None) -> bool:
    """Whether a link stands on the page: the user's own only in their folder of links."""
    return reach.root != "mine" or (place is not None and reach.ancestry[0] == place)


def _groups(place: Node) -> list[Node]:
    """The live folders in the folder of links, at any depth, each level as the user laid it out."""
    found: list[Node] = []
    level = [place.pk]
    while level:
        folders = list(
            Node.objects.filter(parent__in=level, kind=Node.Kind.FOLDER, trashed_at=None).order_by(
                *LAID_OUT
            )
        )
        found += folders
        level = [folder.pk for folder in folders]
    return found


@api("GET", "POST")
def links(request):
    """The page's groups and links; a POST makes the user's folder of links where there is none
    yet."""
    user = request.user
    if request.method == "POST":
        with transaction.atomic():
            place = folder_of(user)
            if place is not None:
                return JsonResponse(describe(place))
            place = new_place(user, "links")
        return JsonResponse(describe(place), status=201)
    place = folder_of(user)
    readable, params = rights.readable(user)
    found = list(
        Node.objects.filter(pk__in=RawSQL(readable, params), kind=Node.Kind.LINK).order_by(
            *LAID_OUT
        )[:MOST]
    )
    groups = _groups(place) if place else []
    reaches = rights.reaches(user, [node.pk for node in [*found, *groups]])
    found = [node for node in found if _on_page(reaches[node.pk], place)]

    def shown(nodes: list[Node]) -> list[dict]:
        chains = [reaches[node.pk].ancestry for node in nodes]
        return [{**each, **along(reaches[each["id"]])} for each in listing(request, chains)]

    return JsonResponse(
        {"folder": place and place.pk, "groups": shown(groups), "links": shown(found)}
    )


def spoken(user, name: str) -> list[dict]:
    """The links on the user's page whose name holds one like the name said, the likest first;
    the likest alone where it is clearly the one."""
    readable, params = rights.readable(user)
    found = list(
        Node.objects.filter(pk__in=RawSQL(readable, params), kind=Node.Kind.LINK)
        .annotate(like=TrigramWordSimilarity(folded(name), Folded("title")))
        .filter(like__gte=LIKE)
        .order_by("-like", "title")[:MOST]
    )
    place = folder_of(user)
    reaches = rights.reaches(user, [node.pk for node in found])
    found = [node for node in found if _on_page(reaches[node.pk], place)][:SPOKEN]
    if len(found) > 1 and found[0].like - found[1].like >= AHEAD:
        found = found[:1]
    return [{"id": str(node.pk), "title": node.title, "href": node.href} for node in found]
