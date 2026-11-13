import uuid
from collections.abc import Callable

from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.http import HttpResponse, JsonResponse

from apps.blobs import previews, store
from apps.blobs.views import serve
from apps.comments.views import text_of
from apps.contacts import search
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.core.emoji import qualified
from apps.meetings import talk
from apps.meetings.models import Guest
from apps.retention import kept as retention

from . import attaching, conversations
from .models import Attachment, Conversation, Member, Message, Reaction

# Messages a page brings, the latest first.
PAGE = 50
TITLE = 1000
CHANNEL_TITLE = 200
# Colleagues offered as the user types.
OFFERED = 20


def _member(user, pk: uuid.UUID) -> Member:
    found = Member.objects.filter(conversation_id=pk, user=user).select_related("conversation")
    if (member := found.first()) is None:
        raise Refused(404, "no_conversation")
    return member


def _readable(user, pk: uuid.UUID) -> Conversation | None:
    """The conversation for one of its members or, an open channel, for any colleague."""
    readable = Q(members__user=user) | Q(kind=Conversation.Kind.CHANNEL, private=False)
    return Conversation.objects.filter(readable, pk=pk).distinct().first()


def _reading(user, pk: uuid.UUID) -> Conversation:
    if (found := _readable(user, pk)) is None:
        raise Refused(404, "no_conversation")
    return found


def _mine(member: Member, mid: int) -> Message:
    found = Message.objects.filter(conversation_id=member.conversation_id, pk=mid).first()
    if found is None:
        raise Refused(404, "no_message")
    if found.author_id != member.user_id:
        raise Refused(403, "not_yours")
    return found


def _title(data: dict) -> str:
    return " ".join(str(data.get("title") or "").split())[:TITLE]


def _named(data: dict) -> str:
    """The title a channel must have."""
    title = _title(data)
    if not title or len(title) > CHANNEL_TITLE:
        raise Refused(400, "invalid_title")
    return title


def _colleagues(user, data: dict) -> list:
    """The colleagues the request names by address; anyone else is no_colleague."""
    given = data.get("people")
    if not isinstance(given, list) or not given:
        raise Refused(400, "invalid_recipient")
    found = {}
    for each in given:
        address = each.get("address") if isinstance(each, dict) else None
        if not isinstance(address, str) or not address.strip():
            raise Refused(400, "invalid_recipient")
        if (colleague := conversations.colleague(user, address.strip())) is None:
            raise Refused(400, "no_colleague")
        found[colleague.pk] = colleague
    return list(found.values())


def _reactions(message: Message, own: Callable[[Reaction], bool]) -> list[dict]:
    """The message's reactions by emoji, first given first, each with who gave it and whether
    the reader is among them."""
    found: dict[str, dict] = {}
    for each in message.reactions.all():
        given = found.setdefault(each.emoji, {"emoji": each.emoji, "people": [], "mine": False})
        given["people"].append(each.guest.name if each.guest else conversations.name_of(each.user))
        given["mine"] = given["mine"] or own(each)
    return list(found.values())


def _mentioned(message: Message, me: int | None) -> list[dict]:
    return [
        {"id": each.user_id, "name": conversations.name_of(each.user), "mine": each.user_id == me}
        for each in message.mentions.all()
    ]


# A message without a thread, and one just written.
NO_THREAD = {"replies": 0, "unread": 0}


def describe(
    message: Message,
    mine: bool,
    own: Callable[[Reaction], bool],
    me: int | None = None,
    thread: dict = NO_THREAD,
    carried: dict = attaching.NOTHING,
    kept: str | None = None,
) -> dict:
    return {
        "id": message.pk,
        "by": conversations.writer_of(message),
        "guest": message.guest_id is not None,
        "mine": mine,
        "text": message.body,
        "at": message.created_at.isoformat(),
        "edited": message.edited_at is not None,
        "reactions": _reactions(message, own),
        "mentions": _mentioned(message, me),
        "everyone": message.everyone,
        "thread": thread,
        "meeting": message.meeting_id and str(message.meeting_id),
        "kept": kept,
        **carried,
    }


def _page(
    request,
    found,
    mine: Callable[[Message], bool],
    own: Callable[[Reaction], bool],
    at: str,
    me: int | None = None,
    beside: dict | None = None,
) -> JsonResponse:
    """A page of the messages found, the latest first, before the one the request names."""
    given = Reaction.objects.select_related("user", "guest").order_by("pk")
    found = found.select_related("author", "guest").annotate(kept=retention.chat_kept())
    found = found.order_by("-id")
    found = found.prefetch_related(
        Prefetch("reactions", queryset=given), "mentions__user", "attachments__blob"
    )
    if before := request.GET.get("before"):
        if not before.isdigit():
            raise Refused(400, "invalid_before")
        found = found.filter(id__lt=int(before))
    page = list(found[: PAGE + 1])
    shown = page[:PAGE]
    threads = conversations.threads_of([each.pk for each in shown], me)
    reader = request.user if me is not None else None
    carried = attaching.carried(shown, reader, at, attaching.hosts_of(request))
    return JsonResponse(
        {
            "messages": [
                describe(
                    each,
                    mine(each),
                    own,
                    me,
                    threads.get(each.pk, NO_THREAD),
                    carried[each.pk],
                    each.kept,
                )
                for each in reversed(shown)
            ],
            "more": len(page) > PAGE,
            **(beside or {}),
        }
    )


def _upto(request) -> int:
    upto = body(request).get("message")
    if not isinstance(upto, int) or isinstance(upto, bool):
        raise Refused(400, "invalid_message")
    return upto


def shown(found: Conversation, user) -> dict:
    """The conversation as the user sees it: who is in it, the meeting it holds lately and what
    they may do with it."""
    meeting = found.meetings.order_by("-created_at").first()
    members = list(found.members.select_related("user"))
    people = sorted(conversations.name_of(each.user) for each in members)
    return {
        "id": str(found.id),
        "kind": found.kind,
        "title": found.title,
        "private": found.private,
        "people": people,
        "joined": any(each.user_id == user.pk for each in members),
        "removable": conversations.removable(found, user.pk, user.is_staff),
        "meeting": str(meeting.id) if meeting else None,
    }


@api("GET")
def people(request):
    """The colleagues a conversation may be started with, by the start of a name or address."""
    typed = request.GET.get("q", "").strip()[:200]
    found = search.colleagues(request.user, typed)[:OFFERED] if typed else []
    return JsonResponse(
        {
            "people": [{"name": each.get_full_name(), "address": each.email} for each in found],
            "unanswered": [],
        }
    )


@api("POST")
def started(request):
    """A conversation with the colleagues named: with one and no title, the one the two have."""
    data = body(request)
    others = _colleagues(request.user, data)
    made, new = conversations.started(request.user, others, _title(data))
    return JsonResponse(shown(made, request.user), status=201 if new else 200)


@api("GET", "POST")
def channels(request):
    """The installation's open channels, or a channel founded by the user, with the colleagues
    named if any."""
    if request.method == "GET":
        return JsonResponse({"channels": conversations.channels(request.user)})
    data = body(request)
    title = _named(data)
    others = _colleagues(request.user, data) if data.get("people") else []
    try:
        made = conversations.founded(request.user, title, bool(data.get("private")), others)
    except IntegrityError:
        raise Refused(409, "channel_taken") from None
    return JsonResponse(shown(made, request.user), status=201)


@api("POST")
def join(request, pk):
    """The user into an open channel, by themselves."""
    found = _reading(request.user, pk)
    conversations.added(found, [request.user])
    return JsonResponse(shown(found, request.user))


def _renamed(found: Conversation, data: dict) -> None:
    if found.kind == Conversation.Kind.CHANNEL:
        try:
            conversations.renamed(found, _named(data))
        except IntegrityError:
            raise Refused(409, "channel_taken") from None
    elif found.kind == Conversation.Kind.GROUP:
        conversations.renamed(found, _title(data))
    else:
        raise Refused(400, "not_group")


@api("GET", "PATCH", "DELETE")
def conversation(request, pk):
    if request.method == "PATCH":
        found = _member(request.user, pk).conversation
        _renamed(found, body(request))
        found.refresh_from_db()
        return JsonResponse(shown(found, request.user))
    if request.method == "DELETE":
        found = _reading(request.user, pk)
        if not conversations.removable(found, request.user.pk, request.user.is_staff):
            raise Refused(403, "channel_not_yours")
        conversations.removed(found)
        return HttpResponse(status=204)
    # A page asks again the moment its user leaves or its conversation is deleted.
    found = _readable(request.user, pk)
    return JsonResponse(found and shown(found, request.user), safe=False)


@api("POST", "DELETE")
def members(request, pk):
    """People brought into a group or a meeting's conversation, or the user out of it; the
    conversation between two people is theirs as it is."""
    member = _member(request.user, pk)
    if member.conversation.kind == Conversation.Kind.DIRECT:
        raise Refused(400, "not_group")
    if request.method == "DELETE":
        conversations.left(member)
        return HttpResponse(status=204)
    conversations.added(member.conversation, _colleagues(request.user, body(request)))
    return JsonResponse(shown(member.conversation, request.user))


def _users_own(user: int) -> Callable[[Reaction], bool]:
    return lambda reaction: reaction.user_id == user


def _guests(guest: Guest) -> Callable[[Reaction], bool]:
    return lambda reaction: reaction.guest_id == guest.pk


def _text(data: dict, carrying: bool) -> str:
    """What the message says, which may be nothing where it carries a file."""
    if carrying and not str(data.get("body") or "").strip():
        return ""
    return text_of(data)


def _described(request, made: Message, own, at: str) -> dict:
    """A message just written or changed, as its author reads it."""
    hosts = attaching.hosts_of(request)
    carried = attaching.carried([made], request.user, at, hosts)[made.pk]
    kept = retention.chat_message_kept(made.pk)
    return describe(made, True, own, request.user.pk, carried=carried, kept=kept)


def _attachment(found, aid: int) -> Attachment:
    attachment = Attachment.objects.select_related("blob").filter(message__in=found, pk=aid).first()
    if attachment is None or attachment.blob is None:
        raise Refused(404, "no_attachment")
    return attachment


def _served(request, attachment: Attachment) -> HttpResponse:
    """The bytes of the attachment: shown where a browser can do so safely, else saved."""
    blob = attachment.blob
    shown = attaching.shown_inline(blob)
    response = serve(request, blob, attachment.name, shown=shown)
    if blob.media_type != store.PDF:
        response["Content-Security-Policy"] = "sandbox"
    return response


def _pictured(request, attachment: Attachment) -> HttpResponse:
    """The attachment's picture, drawn now the first time it is asked for."""
    drawn = previews.drawn(attachment.blob)
    if drawn is None or drawn.picture is None:
        raise Refused(404, "no_attachment")
    return serve(request, drawn.picture, f"{attachment.name}.webp")


def _emoji(given: str) -> str:
    if not given or qualified(given) != given:
        raise Refused(400, "invalid_emoji")
    return given


def _said(data: dict) -> tuple[list[int], bool]:
    """Whom the message says it names: members by id, and everyone in a channel."""
    named = data.get("mentions") or []
    if not isinstance(named, list) or not all(
        isinstance(each, int) and not isinstance(each, bool) for each in named
    ):
        raise Refused(400, "invalid_mentions")
    return named, bool(data.get("everyone"))


@api("GET")
def mentionable(request, pk):
    """Whom the user may name in the conversation: its members but them, and everyone at once in
    a channel."""
    member = _member(request.user, pk)
    others = member.conversation.members.exclude(user=request.user).select_related("user")
    people = [{"id": each.user_id, "name": conversations.name_of(each.user)} for each in others]
    return JsonResponse(
        {
            "people": sorted(people, key=lambda each: each["name"]),
            "everyone": member.conversation.kind == Conversation.Kind.CHANNEL,
        }
    )


@api("GET", "POST")
def messages(request, pk):
    own = _users_own(request.user.pk)
    at = f"/api/conversations/{pk}"
    if request.method == "POST":
        data = body(request)
        member = _member(request.user, pk)
        attached = attaching.given(request.user, data)
        text = _text(data, bool(attached))
        if (parent := data.get("parent")) is not None:
            root = _root(member.conversation, parent)
            made = conversations.replied(member, root, text, *_said(data), attached)
        else:
            made = conversations.written(member, text, *_said(data), attached)
        return JsonResponse(_described(request, made, own, at), status=201)
    conversation = _reading(request.user, pk)
    found = Message.objects.filter(conversation_id=pk, parent=None)
    beside = {"readers": conversations.readers(conversation, request.user)}
    return _page(
        request,
        found,
        lambda each: each.author_id == request.user.pk,
        own,
        at,
        request.user.pk,
        beside,
    )


def _root(found: Conversation, mid: object) -> Message:
    """The channel's message whose thread is meant; a thread has one level."""
    if found.kind != Conversation.Kind.CHANNEL:
        raise Refused(400, "no_threads_here")
    if not isinstance(mid, int) or isinstance(mid, bool):
        raise Refused(400, "invalid_message")
    root = Message.objects.filter(conversation=found, pk=mid, parent=None).first()
    if root is None:
        raise Refused(404, "no_message")
    return root


@api("GET")
def replies(request, pk, mid):
    """A page of the thread's replies, the latest first."""
    root = _root(_reading(request.user, pk), mid)
    me = request.user.pk
    found = Message.objects.filter(parent=root)
    at = f"/api/conversations/{pk}"
    return _page(request, found, lambda each: each.author_id == me, _users_own(me), at, me)


@api("POST")
def thread_read(request, pk, mid):
    root = _root(_member(request.user, pk).conversation, mid)
    conversations.thread_read(root, request.user.pk, _upto(request))
    return HttpResponse(status=204)


@api("PATCH", "DELETE")
def message(request, pk, mid):
    """The user's own message said otherwise or taken back."""
    member = _member(request.user, pk)
    found = _mine(member, mid)
    if request.method == "DELETE":
        conversations.taken_back(found)
        return HttpResponse(status=204)
    data = body(request)
    conversations.edited(found, _text(data, found.attachments.exists()), *_said(data))
    return JsonResponse(
        _described(request, found, _users_own(member.user_id), f"/api/conversations/{pk}")
    )


@api("GET")
def attachment(request, pk, aid):
    """The bytes of a file a message of the conversation carries."""
    _reading(request.user, pk)
    return _served(request, _attachment(Message.objects.filter(conversation_id=pk), aid))


@api("GET")
def attachment_picture(request, pk, aid):
    _reading(request.user, pk)
    return _pictured(request, _attachment(Message.objects.filter(conversation_id=pk), aid))


@api("PUT", "DELETE")
def reaction(request, pk, mid, emoji):
    """The user's emoji put on a message of the conversation, or taken off it."""
    member = _member(request.user, pk)
    found = Message.objects.filter(conversation_id=pk, pk=mid).first()
    if found is None:
        raise Refused(404, "no_message")
    on = request.method == "PUT"
    conversations.reacted(found, _emoji(emoji), on, user=member.user)
    return HttpResponse(status=204)


@api("POST")
def read(request, pk):
    member = _member(request.user, pk)
    conversations.read(member, _upto(request))
    return HttpResponse(status=204)


def _guests_own(guest: Guest, mid: int) -> Message:
    found = talk.window(guest).filter(pk=mid).first()
    if found is None:
        raise Refused(404, "no_message")
    if found.guest_id != guest.pk:
        raise Refused(403, "not_yours")
    return found


@database
def _guest_messages(request, guest: Guest) -> JsonResponse:
    if request.method == "POST":
        made = talk.written(guest, text_of(body(request)))
        kept = retention.chat_message_kept(made.pk)
        return JsonResponse(describe(made, True, _guests(guest), kept=kept), status=201)
    window = talk.window(guest)
    at = f"/api/meetings/{guest.meeting_id}/guests/{guest.key}"
    return _page(request, window, lambda each: each.guest_id == guest.pk, _guests(guest), at)


@database
def _guest_message(request, guest: Guest, mid: int) -> HttpResponse:
    found = _guests_own(guest, mid)
    if request.method == "DELETE":
        conversations.taken_back(found)
        return HttpResponse(status=204)
    conversations.edited(found, text_of(body(request)))
    kept = retention.chat_message_kept(found.pk)
    return JsonResponse(describe(found, True, _guests(guest), kept=kept))


@database
def _guest_reaction(request, guest: Guest, mid: int, emoji: str) -> HttpResponse:
    found = talk.window(guest).filter(pk=mid).first()
    if found is None:
        raise Refused(404, "no_message")
    conversations.reacted(found, _emoji(emoji), request.method == "PUT", guest=guest)
    return HttpResponse(status=204)


@database
def _guest_read(request, guest: Guest) -> HttpResponse:
    talk.read(guest, _upto(request))
    return HttpResponse(status=204)


# A guest in a meeting's call (S2-2) reads and writes its conversation by the key of their link,
# as a member does by their account.


@database
def _guest_attachment(request, guest: Guest, aid: int) -> HttpResponse:
    return _served(request, _attachment(talk.window(guest), aid))


@database
def _guest_picture(request, guest: Guest, aid: int) -> HttpResponse:
    return _pictured(request, _attachment(talk.window(guest), aid))


@api("GET", "POST", signed_in=False)
async def guest_messages(request, pk, key):
    return await _guest_messages(request, await talk.in_call(pk, key))


@api("PATCH", "DELETE", signed_in=False)
async def guest_message(request, pk, key, mid):
    return await _guest_message(request, await talk.in_call(pk, key), mid)


@api("PUT", "DELETE", signed_in=False)
async def guest_reaction(request, pk, key, mid, emoji):
    return await _guest_reaction(request, await talk.in_call(pk, key), mid, emoji)


@api("POST", signed_in=False)
async def guest_read(request, pk, key):
    return await _guest_read(request, await talk.in_call(pk, key))


@api("GET", signed_in=False)
async def guest_attachment(request, pk, key, aid):
    return await _guest_attachment(request, await talk.in_call(pk, key), aid)


@api("GET", signed_in=False)
async def guest_attachment_picture(request, pk, key, aid):
    return await _guest_picture(request, await talk.in_call(pk, key), aid)
