from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import JsonResponse
from pycrdt import Doc

from apps.collab.models import Update
from apps.content import operations
from apps.content.models import Element
from apps.content.sheets import Sheets
from apps.core.api import Refused, api, body

from .launcher import new_place
from .models import Favourite, Node
from .naming import first_line
from .views import created, describe, listing, title_of

# As much of a note's text after its first line as its card shows.
EXCERPT = 240


def folder_of(user) -> Node | None:
    return Node.objects.filter(created_by=user, notes=True, trashed_at=None).first()


def excerpts(ids: list) -> dict:
    """The text of each document's first tab after its first line, as much as a card shows."""
    texts: dict = {}
    for each in (
        Element.objects.filter(tab__document__in=ids, tab__parent=None, tab__position=0)
        .exclude(text="")
        .order_by("tab__document", "position")
        .values("tab__document", "text")
    ):
        texts.setdefault(each["tab__document"], []).append(each["text"])
    shown = {}
    for pk, lines in texts.items():
        joined = " ".join(" ".join(lines[1:]).split())
        shown[pk] = joined[:EXCERPT]
    return shown


def paragraphs(text: str, link: str) -> list:
    """A paragraph for each line of the text, and the link as one of its own."""
    lines = [line.rstrip() for line in text.splitlines()]
    made = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}] if line else []}
        for line in lines
    ]
    if link:
        mark = {"type": "link", "attrs": {"href": link}}
        made.append(
            {"type": "paragraph", "content": [{"type": "text", "text": link, "marks": [mark]}]}
        )
    return [operations.block_of(each) for each in made]


def given(data: dict, name: str, longest: int) -> str:
    value = data.get(name, "")
    if not isinstance(value, str) or len(value) > longest:
        raise Refused(400, f"invalid_{name}")
    return value.strip()


@api("GET", "POST")
def notes(request):
    if request.method == "GET":
        place = folder_of(request.user)
        if place is None:
            return JsonResponse({"folder": None, "notes": []})
        children = list(
            Node.objects.filter(parent=place, trashed_at=None).order_by(
                Exists(Favourite.objects.filter(user=request.user, node=OuterRef("pk"))).desc(),
                "-updated_at",
            )
        )
        shown = excerpts([child.pk for child in children])
        return JsonResponse(
            {
                "folder": place.pk,
                "notes": [
                    {**each, "excerpt": shown.get(each["id"], "")}
                    for each in listing(request, [[place, child] for child in children])
                ],
            }
        )
    data = body(request)
    text = given(data, "text", 100_000)
    link = given(data, "link", 2_000)
    title = first_line(text) or link[:200] or title_of(data)
    with transaction.atomic():
        place = folder_of(request.user)
        if place is None:
            place = new_place(request.user, "notes")
        note = created(place, Node.Kind.DOCUMENT, title, None, request.user)
        note.follows_text = True
        note.save(update_fields=["follows_text"])
        if text or link:
            tab = note.tabs.get()
            written = operations.write(Doc(), Sheets({}), paragraphs(text, link))
            Update.objects.create(document=note, tab=tab, room=tab.room, data=written.update)
    return JsonResponse(describe(note), status=201)
