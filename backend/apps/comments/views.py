import json
import math

from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.access.models import Role
from apps.collab.server import announce
from apps.core.api import Refused, api, body, optional_id
from apps.documents import views as documents
from apps.documents.models import Node
from apps.users.views import describe as describe_user

from .models import Comment, Thread

LONGEST_BODY = 10_000
LONGEST_QUOTE = 500
LONGEST_ANCHOR = 10_000


def describe_comment(comment: Comment) -> dict:
    return {
        "id": comment.id,
        "author": comment.author and describe_user(comment.author),
        "outside_author": comment.outside_author,
        "body": comment.body,
        "created_at": comment.created_at,
        "edited_at": comment.edited_at,
    }


def describe(thread: Thread) -> dict:
    return {
        "id": thread.id,
        "tab": thread.tab_id,
        "anchor": thread.anchor,
        "quote": thread.quote,
        "created_at": thread.created_at,
        "resolved_at": thread.resolved_at,
        "resolved_by": thread.resolved_by and describe_user(thread.resolved_by),
        "comments": [describe_comment(comment) for comment in thread.comments.all()],
    }


def listed(threads):
    in_order = Comment.objects.select_related("author").order_by("created_at", "id")
    return threads.select_related("resolved_by").prefetch_related(
        Prefetch("comments", queryset=in_order)
    )


def described(thread: Thread) -> dict:
    return describe(listed(Thread.objects).get(pk=thread.pk))


def changed(document: Node) -> None:
    transaction.on_commit(lambda: announce(document.room, "comments"))


def text_of(data: dict) -> str:
    text = data.get("body")
    if not isinstance(text, str) or not text.strip() or len(text) > LONGEST_BODY:
        raise Refused(400, "invalid_body")
    return text.strip()


def anchor_of(data: dict) -> dict:
    anchor = data.get("anchor")
    if (
        not isinstance(anchor, dict)
        or anchor.keys() != {"from", "to"}
        or not all(isinstance(end, dict) for end in anchor.values())
        or len(json.dumps(anchor)) > LONGEST_ANCHOR
    ):
        raise Refused(400, "invalid_anchor")
    return anchor


def _coordinates(value, count: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == count
        and all(
            isinstance(each, int | float) and not isinstance(each, bool) and math.isfinite(each)
            for each in value
        )
    )


def page_anchor_of(data: dict) -> dict:
    """A page and either the rectangles of its text, each as its left, bottom, right and top, or
    a point on it."""
    anchor = data.get("anchor")
    if not isinstance(anchor, dict) or len(json.dumps(anchor)) > LONGEST_ANCHOR:
        raise Refused(400, "invalid_anchor")
    page = anchor.get("page")
    rects = anchor.get("rects")
    shaped = isinstance(page, int) and not isinstance(page, bool) and page >= 1
    if anchor.keys() == {"page", "rects"}:
        shaped = (
            shaped
            and isinstance(rects, list)
            and len(rects) > 0
            and all(_coordinates(rect, 4) for rect in rects)
            and all(left <= right and bottom <= top for left, bottom, right, top in rects)
        )
    else:
        shaped = shaped and anchor.keys() == {"page", "at"} and _coordinates(anchor["at"], 2)
    if not shaped:
        raise Refused(400, "invalid_anchor")
    return anchor


def quote_of(data: dict, required: bool = True) -> str:
    quote = data.get("quote")
    if not isinstance(quote, str) or bool(quote.strip()) != required or len(quote) > LONGEST_QUOTE:
        raise Refused(400, "invalid_quote")
    return quote


def thread_of(request, pk, needs: Role) -> Thread:
    thread = Thread.objects.select_related("tab__document", "file").filter(pk=pk).first()
    if thread is None:
        raise Refused(404, "not_found")
    documents.live(request.user, thread.node.pk, needs)
    return thread


def _started(node: Node, data: dict) -> Thread:
    if node.kind == Node.Kind.FILE:
        if not node.is_pdf:
            raise Refused(400, "not_a_pdf")
        if data.get("tab") is not None:
            raise Refused(400, "invalid_tab")
        anchor = page_anchor_of(data)
        quote = quote_of(data, required="rects" in anchor)
        return Thread(file=node, anchor=anchor, quote=quote)
    tab = node.tabs.filter(pk=optional_id(data.get("tab"))).first()
    if tab is None:
        raise Refused(400, "invalid_tab")
    return Thread(tab=tab, anchor=anchor_of(data), quote=quote_of(data))


@api("GET", "POST", visitors=True)
def threads(request, pk):
    """Who reads a document or a file comments on it, starting a thread with its first comment.
    A file's thread is about the text chosen on one of its pages, or a point there."""
    node, _ = documents.live(request.user, pk)
    if node.kind == Node.Kind.FOLDER:
        raise Refused(400, "not_a_document")
    if request.method == "POST":
        data = body(request)
        thread = _started(node, data)
        text = text_of(data)
        with transaction.atomic():
            thread.save()
            Comment.objects.create(thread=thread, author=request.user, body=text)
            changed(node)
        return JsonResponse(described(thread), status=201)
    about = {"file": node} if node.kind == Node.Kind.FILE else {"tab__document": node}
    found = listed(Thread.objects.filter(**about)).order_by("created_at", "id")
    return JsonResponse({"threads": [describe(thread) for thread in found]})


@api("PATCH", visitors=True)
def thread(request, pk):
    """An editor resolves a thread, or opens it again."""
    thread = thread_of(request, pk, Role.EDIT)
    resolved = body(request).get("resolved")
    if not isinstance(resolved, bool):
        raise Refused(400, "invalid_resolved")
    if resolved != (thread.resolved_at is not None):
        thread.resolved_at = timezone.now() if resolved else None
        thread.resolved_by = request.user if resolved else None
        with transaction.atomic():
            thread.save(update_fields=["resolved_at", "resolved_by"])
            changed(thread.node)
    return JsonResponse(described(thread))


@api("POST", visitors=True)
def replies(request, pk):
    thread = thread_of(request, pk, Role.READ)
    text = text_of(body(request))
    if thread.resolved_at is not None:
        raise Refused(409, "resolved")
    with transaction.atomic():
        Comment.objects.create(thread=thread, author=request.user, body=text)
        changed(thread.node)
    return JsonResponse(described(thread), status=201)


@api("PATCH", "DELETE", visitors=True)
def comment(request, pk):
    """Only its author changes or deletes a comment; a thread goes with its last one."""
    comment = (
        Comment.objects.select_related("thread__tab__document", "thread__file")
        .filter(pk=pk)
        .first()
    )
    if comment is None:
        raise Refused(404, "not_found")
    thread = comment.thread
    documents.live(request.user, thread.node.pk, Role.READ)
    if comment.author_id != request.user.pk:
        raise Refused(403, "not_author")
    with transaction.atomic():
        if request.method == "PATCH":
            comment.body = text_of(body(request))
            comment.edited_at = timezone.now()
            comment.save(update_fields=["body", "edited_at"])
        else:
            comment.delete()
            if not thread.comments.exists():
                thread.delete()
        changed(thread.node)
    return HttpResponse(status=204)
