"""Messages of conversations found by the search box (S2-3d): those of conversations the user is
in and of the open channels anyone may read."""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import connection

from apps.chat.conversations import name_of, writer_of
from apps.chat.models import Conversation, Member, Message

from .query import Asked
from .text import CONFIG, HEADLINE, PEOPLE, matching, period_of

WRITER = PEOPLE.format(
    name="coalesce(guest.name, concat_ws(' ', author.first_name, author.last_name))",
    address="author.email",
)
SOURCE = f"""
FROM chat_message message
JOIN chat_conversation conversation ON conversation.id = message.conversation_id
LEFT JOIN {get_user_model()._meta.db_table} author ON author.id = message.author_id
LEFT JOIN meetings_guest guest ON guest.id = message.guest_id
"""
READABLE = f"""(
    EXISTS (SELECT 1 FROM chat_member member
        WHERE member.conversation_id = message.conversation_id AND member.user_id = %s)
    OR (conversation.kind = '{Conversation.Kind.CHANNEL}' AND NOT conversation.private)
)"""
MATCHED = f"""
WITH q AS (SELECT {{query}} AS query)
SELECT message.id, ts_headline('{CONFIG}'::regconfig, left(message.body, 131072), q.query, %s)
{SOURCE} CROSS JOIN q
WHERE message.words @@ q.query AND {READABLE}{{filters}}
ORDER BY ts_rank_cd(message.words, q.query, 32) DESC, message.id DESC
LIMIT %s
"""
LISTED = f"""
SELECT message.id, left(message.body, 200)
{SOURCE}
WHERE message.body <> '' AND {READABLE}{{filters}}
ORDER BY message.id DESC
LIMIT %s
"""


def _filters(wanted: Asked) -> tuple[str, list]:
    conditions, params = [], []
    for value in wanted.sender:
        conditions.append(WRITER)
        params.append(value)
    if wanted.period:
        conditions.extend(period_of("message.created_at", wanted, params))
    return "".join(f" AND {condition}" for condition in conditions), params


def found_messages(user, wanted: Asked, limit: int) -> list[dict]:
    filters, params = _filters(wanted)
    with connection.cursor() as cursor:
        if wanted.text:
            query, query_params = matching(wanted.text)
            cursor.execute(
                MATCHED.format(query=query, filters=filters),
                [*query_params, HEADLINE, user.pk, *params, limit],
            )
        else:
            cursor.execute(LISTED.format(filters=filters), [user.pk, *params, limit])
        rows = cursor.fetchall()
    found = Message.objects.select_related("conversation", "author", "guest").in_bulk(
        [pk for pk, _ in rows]
    )
    others = defaultdict(list)
    members = Member.objects.filter(
        conversation_id__in={each.conversation_id for each in found.values()}
    )
    for each in members.exclude(user=user).select_related("user"):
        others[each.conversation_id].append(name_of(each.user))
    return [
        {
            "id": pk,
            "conversation": str(found[pk].conversation_id),
            "parent": found[pk].parent_id,
            "kind": found[pk].conversation.kind,
            "title": found[pk].conversation.title
            or ", ".join(sorted(others[found[pk].conversation_id])),
            "by": writer_of(found[pk]),
            "at": found[pk].created_at.isoformat(),
            "snippet": snippet,
        }
        for pk, snippet in rows
        if pk in found
    ]
