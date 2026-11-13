"""What the people of a conversation share as it happens: a message wakes its members' tabs
through the live channel, whose part `conversations` holds the user's conversations with the
last message of each and how many they have not read. A meeting's conversation nobody has
written to is not among them, as a meeting made and left unused says nothing; one started from
people is, from its start."""

from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce, Lower
from django.utils import timezone

from apps.collab import live
from apps.push import notices as push
from apps.push.models import Notice
from apps.retention import kept as retention
from apps.users.models import User

from . import files
from .models import Attachment, Conversation, Follower, Member, Mention, Message, Reaction

# How much of the last message a conversation's row shows.
GLIMPSE = 200
# How a message names everyone in a channel, in any of the interface's languages.
EVERYONE = ("@svi", "@all")


def name_of(user) -> str:
    return (user.get_full_name() or user.email) if user else ""


def writer_of(message: Message) -> str:
    """Who wrote the message: a member, or a guest in a call of the conversation's meeting."""
    return message.guest.name if message.guest else name_of(message.author)


def colleague(user, address: str) -> User | None:
    """Another person of the installation by their sign-in or any mail address of theirs."""
    found = (
        User.objects.filter(is_active=True)
        .filter(Q(email__iexact=address) | Q(mail_accounts__address__iexact=address))
        .exclude(pk=user.pk)
        .first()
    )
    return found


def _unread(user: int) -> Coalesce:
    """How many messages of the others a membership of the user's has not read."""
    found = (
        Message.objects.filter(
            conversation=OuterRef("conversation"), parent=None, id__gt=OuterRef("read")
        )
        .exclude(author_id=user)
        .order_by()
        .values("conversation")
        .annotate(count=Count("id"))
        .values("count")
    )
    return Coalesce(Subquery(found), 0)


def _mentions(user: int) -> Coalesce:
    """How many unread messages of a membership of the user's name them."""
    found = (
        Mention.objects.filter(
            user_id=user,
            message__conversation=OuterRef("conversation"),
            message__parent=None,
            message_id__gt=OuterRef("read"),
        )
        .order_by()
        .values("message__conversation")
        .annotate(count=Count("id"))
        .values("count")
    )
    return Coalesce(Subquery(found), 0)


def _unread_replies(user: int):
    """The replies of the others in the threads the user follows, past where they have read."""
    return Message.objects.filter(
        parent__followers__user_id=user, id__gt=F("parent__followers__read")
    ).exclude(author_id=user)


def _threads(user: int) -> Coalesce:
    """How many unread replies a membership of the user's holds in the threads they follow."""
    found = (
        _unread_replies(user)
        .filter(conversation=OuterRef("conversation"))
        .order_by()
        .values("conversation")
        .annotate(count=Count("id"))
        .values("count")
    )
    return Coalesce(Subquery(found), 0)


def unread(user: int) -> int:
    """What waits for the user: every unread message of the others, but in a channel only those
    that name them and the replies in the threads they follow."""
    members = Member.objects.filter(user_id=user)
    plain = members.exclude(conversation__kind=Conversation.Kind.CHANNEL).annotate(
        unread=_unread(user)
    )
    named = members.filter(conversation__kind=Conversation.Kind.CHANNEL).annotate(
        unread=_mentions(user) + _threads(user)
    )
    return sum(found.aggregate(total=Sum("unread"))["total"] or 0 for found in (plain, named))


def removable(found: Conversation, user: int, staff: bool) -> bool:
    return found.open and (found.created_by_id == user or staff)


def summaries(user: int) -> list[dict]:
    """The user's conversations, the latest written to first, each with its last message, how
    many messages of the others the user has not read and who else is in it, which names a
    conversation without a title."""
    latest = Message.objects.filter(conversation=OuterRef("conversation"), parent=None).order_by(
        "-id"
    )
    members = list(
        Member.objects.filter(user_id=user)
        .select_related("conversation")
        .annotate(
            last=Subquery(latest.values("id")[:1]),
            unread=_unread(user),
            mentions=_mentions(user),
            threads=_threads(user),
        )
    )
    members = [
        each for each in members if each.last or each.conversation.kind != Conversation.Kind.MEETING
    ]
    last = (
        Message.objects.select_related("author", "guest")
        .annotate(files=Count("attachments"))
        .in_bulk([each.last for each in members if each.last])
    )
    staff = User.objects.filter(pk=user, is_staff=True).exists()
    others = defaultdict(list)
    here = defaultdict(list)
    online = live.online()
    beside = Member.objects.filter(conversation__in=[each.conversation_id for each in members])
    for each in beside.exclude(user_id=user).select_related("user"):
        others[each.conversation_id].append(name_of(each.user))
        if each.user_id in online:
            here[each.conversation_id].append(name_of(each.user))
    members.sort(key=lambda each: (each.last or 0, each.conversation.created_at), reverse=True)
    return [
        {
            "id": str(each.conversation_id),
            "kind": each.conversation.kind,
            "title": each.conversation.title,
            "private": each.conversation.private,
            "removable": removable(each.conversation, user, staff),
            "people": sorted(others[each.conversation_id]),
            "online": sorted(here[each.conversation_id]),
            "unread": each.unread,
            "mentions": each.mentions,
            "threads": each.threads,
            "changed": each.conversation.changed_at.isoformat(),
            "last": {
                "id": last[each.last].pk,
                "by": writer_of(last[each.last]),
                "text": last[each.last].body[:GLIMPSE],
                "files": last[each.last].files,
                "meeting": last[each.last].meeting_id is not None,
                "at": last[each.last].created_at.isoformat(),
            }
            if each.last
            else None,
        }
        for each in members
    ]


def added(conversation: Conversation, users) -> None:
    """Brings the users into the conversation; those already in stay as they are."""
    new = [
        each.pk
        for each in users
        if Member.objects.get_or_create(conversation=conversation, user=each)[1]
    ]
    if new:
        files.granted(conversation.pk)
        _moved(conversation.pk)


@transaction.atomic
def started(user, others: list, title: str) -> tuple[Conversation, bool]:
    """A conversation among the user and the others: between two people the one they have,
    started once; among more a group under the title given, which may be none."""
    if len(others) == 1 and not title:
        kind = Conversation.Kind.DIRECT
        found = (
            Conversation.objects.filter(kind=kind, members__user=user)
            .filter(members__user=others[0])
            .first()
        )
        if found is not None:
            return found, False
    else:
        kind = Conversation.Kind.GROUP
    made = Conversation.objects.create(kind=kind, title=title)
    added(made, [user, *others])
    return made, True


@transaction.atomic
def founded(user, title: str, private: bool, others: list) -> Conversation:
    """A channel under the title, its founder and the others given in it."""
    made = Conversation.objects.create(
        kind=Conversation.Kind.CHANNEL, title=title, private=private, created_by=user
    )
    added(made, [user, *others])
    return made


def channels(user) -> list[dict]:
    """Every open channel of the installation, by name, and whether the user is in it."""
    found = (
        Conversation.objects.filter(kind=Conversation.Kind.CHANNEL, private=False)
        .annotate(
            count=Count("members"),
            joined=Exists(Member.objects.filter(conversation=OuterRef("pk"), user=user)),
        )
        .order_by(Lower("title"))
    )
    return [
        {"id": str(each.pk), "title": each.title, "count": each.count, "joined": each.joined}
        for each in found
    ]


def readers(conversation: Conversation, user) -> list[dict]:
    """How far each of the others has read: by name, within the installation; a channel's
    readers are nobody's to count."""
    if conversation.kind == Conversation.Kind.CHANNEL:
        return []
    others = conversation.members.exclude(user=user).select_related("user")
    return [{"name": name_of(each.user), "read": each.read} for each in others if each.read]


def _everyone(conversation_id):
    return Member.objects.filter(conversation_id=conversation_id).values_list("user_id", flat=True)


def concerned(key: str) -> list[int] | None:
    """Whom a change to a conversation concerns: its members, or everyone when it is an open
    channel or gone, as nobody can then say who it was shown to."""
    found = Conversation.objects.filter(pk=key).first()
    if found is None or found.open:
        return None
    return list(_everyone(found.pk))


def _moved(conversation_id) -> None:
    """Wakes the tabs of the conversation's members and of the guests let into its meetings."""
    # Imported here: meetings.models makes its conversations through this module.
    from apps.meetings.models import Guest

    Conversation.objects.filter(pk=conversation_id).update(changed_at=timezone.now())
    live.tell(*_everyone(conversation_id))
    guests = Guest.objects.filter(
        meeting__conversation_id=conversation_id, state=Guest.State.ADMITTED
    )
    live.tell_guests(*guests.values_list("pk", flat=True))


def _file_names(message: Message) -> str:
    return ", ".join(message.attachments.values_list("name", flat=True))


def _carrying(message: Message, attached: list[Attachment], by) -> None:
    for position, each in enumerate(attached):
        each.message = message
        each.position = position
    Attachment.objects.bulk_create(attached)
    if any(each.node_id for each in attached):
        files.granted(message.conversation_id, by)


def _heard(message: Message, by: str, users) -> None:
    conversation = message.conversation
    push.tell(
        users,
        Notice.Kind.MESSAGE,
        {
            "by": by,
            "text": push.cut(message.body or _file_names(message)),
            "title": conversation.title,
            "conversation": str(conversation.pk),
        },
        tag=push.topic("chat", conversation.pk),
    )


def _meant(message: Message, mentioned: set[int]):
    """Whom a new message is for: in a channel the ones it names, elsewhere everyone in it but
    its author."""
    if message.conversation.kind == Conversation.Kind.CHANNEL:
        return mentioned
    return _everyone(message.conversation_id).exclude(user_id=message.author_id)


def announced(message: Message, by: str, mentioned: set[int] | None = None) -> None:
    """A message just written, which everyone in its conversation sees come and those it is for
    hear of on their phones."""
    _moved(message.conversation_id)
    _heard(message, by, _meant(message, mentioned or set()))


def _named(message: Message, named: list[int], everyone: bool) -> set[int]:
    """Keeps who the message names now, members other than its author whose @name stands in its
    text, or all of them where it names everyone in a channel, and gives those it did not name
    before."""
    others = set(_everyone(message.conversation_id).exclude(user_id=message.author_id))
    everyone = (
        everyone
        and message.conversation.kind == Conversation.Kind.CHANNEL
        and any(each in message.body for each in EVERYONE)
    )
    if everyone:
        kept = others
    else:
        found = User.objects.filter(pk__in=others.intersection(named))
        kept = {each.pk for each in found if f"@{name_of(each)}" in message.body}
    before = set(message.mentions.values_list("user_id", flat=True))
    message.mentions.exclude(user_id__in=kept).delete()
    Mention.objects.bulk_create(Mention(message=message, user_id=each) for each in kept - before)
    if message.everyone != everyone:
        message.everyone = everyone
        message.save(update_fields=["everyone"])
    return kept - before


@transaction.atomic
def written(
    member: Member,
    text: str,
    named: list[int] = (),
    everyone: bool = False,
    attached: list[Attachment] = (),
) -> Message:
    message = Message.objects.create(
        conversation=member.conversation, author_id=member.user_id, body=text
    )
    _carrying(message, list(attached), member.user)
    Member.objects.filter(pk=member.pk).update(read=message.pk)
    announced(message, name_of(member.user), _named(message, list(named), everyone))
    return message


@transaction.atomic
def meeting_opened(member: Member, meeting) -> Message:
    """A meeting opened in a channel: a message anyone there may join it from, ringing nobody."""
    message = Message.objects.create(
        conversation=member.conversation, author_id=member.user_id, body="", meeting=meeting
    )
    Member.objects.filter(pk=member.pk).update(read=message.pk)
    _moved(message.conversation_id)
    return message


@transaction.atomic
def replied(
    member: Member,
    root: Message,
    text: str,
    named: list[int] = (),
    everyone: bool = False,
    attached: list[Attachment] = (),
) -> Message:
    """A reply in the thread of a channel's message. The thread then concerns its author, the one
    replying and whoever the reply names, who are the ones to hear of it."""
    message = Message.objects.create(
        conversation=member.conversation, author_id=member.user_id, body=text, parent=root
    )
    _carrying(message, list(attached), member.user)
    new = _named(message, list(named), everyone)
    users = {member.user_id, *new}
    if root.author_id:
        users.add(root.author_id)
    Follower.objects.bulk_create(
        [Follower(root=root, user_id=each) for each in users], ignore_conflicts=True
    )
    Follower.objects.filter(root=root, user_id=member.user_id).update(read=message.pk)
    _moved(message.conversation_id)
    told = Follower.objects.filter(
        root=root, user__memberships__conversation=member.conversation_id
    ).exclude(user_id=member.user_id)
    _heard(message, name_of(member.user), set(told.values_list("user_id", flat=True)))
    return message


def thread_read(root: Message, user: int, upto: int) -> None:
    """Marks the thread read up to the reply, never past its last one nor back."""
    last = (
        Message.objects.filter(parent=root, id__lte=upto)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
    )
    if last and Follower.objects.filter(root=root, user_id=user, read__lt=last).update(read=last):
        live.tell(user)


def threads_of(roots: list[int], user: int | None) -> dict[int, dict]:
    """For each of the messages, how many replies its thread has and how many of them wait for
    the user."""
    replies = Message.objects.filter(parent__in=roots).values("parent").annotate(count=Count("id"))
    found = {each["parent"]: {"replies": each["count"], "unread": 0} for each in replies.order_by()}
    if user is not None and found:
        waiting = _unread_replies(user).filter(parent__in=found)
        for each in waiting.values("parent").annotate(count=Count("id")).order_by():
            found[each["parent"]]["unread"] = each["count"]
    return found


@transaction.atomic
def edited(message: Message, text: str, named: list[int] = (), everyone: bool = False) -> Message:
    """The author's message said otherwise, marked as edited for everyone; someone it newly names
    in a channel hears of it."""
    retention.refuse_chat(Message.objects.filter(pk=message.pk), editing=True)
    message.body = text
    message.edited_at = timezone.now()
    message.save(update_fields=["body", "edited_at"])
    new = _named(message, list(named), everyone) if message.author_id else set()
    _moved(message.conversation_id)
    if new and message.conversation.kind == Conversation.Kind.CHANNEL:
        _heard(message, name_of(message.author), new)
    return message


@transaction.atomic
def taken_back(message: Message) -> None:
    """The author's message gone for everyone."""
    retention.refuse_chat(Message.objects.filter(pk=message.pk))
    conversation = message.conversation_id
    by = message.author
    message.delete()
    files.granted(conversation, by)
    _moved(conversation)


@transaction.atomic
def reacted(message: Message, emoji: str, on: bool, *, user=None, guest=None) -> None:
    """The emoji put on the message or taken off it, by a member or a guest, for everyone in its
    conversation to see."""
    if on:
        given = Reaction(message=message, user=user, guest=guest, emoji=emoji)
        Reaction.objects.bulk_create([given], ignore_conflicts=True)
    else:
        Reaction.objects.filter(message=message, user=user, guest=guest, emoji=emoji).delete()
    _moved(message.conversation_id)


@transaction.atomic
def renamed(conversation: Conversation, title: str) -> None:
    Conversation.objects.filter(pk=conversation.pk).update(title=title)
    live.tell(*_everyone(conversation.pk))


@transaction.atomic
def left(member: Member) -> None:
    """The member out of the conversation; the last one out takes it with them, but for an open
    channel, whose history stays for whoever joins it next, and one whose messages are kept, which
    stays until a rule removes the last of them."""
    conversation = member.conversation
    user = member.user_id
    member.delete()
    files.granted(conversation.pk, member.user)
    if conversation.open or _everyone(conversation.pk).exists():
        _moved(conversation.pk)
    elif not retention.chat_reason(conversation.messages.all()):
        conversation.delete()
    live.tell(user)


@transaction.atomic
def removed(conversation: Conversation) -> None:
    """The channel and its messages gone for everyone."""
    retention.refuse_chat(conversation.messages.all())
    told = list(_everyone(conversation.pk))
    files.withdrawn(conversation.pk)
    conversation.delete()
    live.tell(*told)


def read(member: Member, upto: int) -> None:
    """Marks the conversation read up to the message, never past its last one nor back."""
    last = (
        Message.objects.filter(conversation_id=member.conversation_id, id__lte=upto)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
    )
    if not last or not Member.objects.filter(pk=member.pk, read__lt=last).update(read=last):
        return
    if member.conversation.kind == Conversation.Kind.CHANNEL:
        live.tell(member.user_id)
    else:
        _moved(member.conversation_id)
