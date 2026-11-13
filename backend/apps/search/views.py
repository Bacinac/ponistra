import json

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.http import JsonResponse

from apps.access import rights
from apps.actions.models import ActionRun
from apps.ai import installation
from apps.ai.models import SearchConsent
from apps.blobs import store
from apps.calendar.views import zone_of
from apps.content.elements import column
from apps.content.models import GridRow
from apps.core.api import Refused, api, body, optional_id
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab
from apps.documents.views import along, described, folder, live_pdf
from apps.help import library
from apps.mail import sharing
from apps.mail.models import Attachment, Message, Role
from apps.mail.views import listed

from . import ocr, pdf, translation
from .agenda import found_events, found_tasks
from .people import found_people
from .query import Asked, asked
from .talks import found_messages
from .text import (
    CONFIG,
    HEADLINE,
    INSIDE,
    LIKENESS,
    NAMED,
    OPERATORS,
    PEOPLE,
    TAIL,
    UNDER,
    WHOLE,
    matching,
    period_of,
)
from .versions import found_versions

User = get_user_model()
SHOWN, MOST, LONGEST = 8, 50, 200
SNIPPET = (
    f"regexp_replace(ts_headline('{CONFIG}'::regconfig, best.text || ' {TAIL}', q.query, %s),"
    f" ' {TAIL}$', '')"
)
HIDDEN = [Role.JUNK, Role.TRASH]

SEARCH = """
WITH found AS MATERIALIZED (
    SELECT node.id FROM documents_node node
    WHERE node.id IN ({readable}) AND NOT (node.notes OR node.links OR node.boards){filters}
),
q AS (
    SELECT {query} AS query, search_fold(%s) AS folded
),
hits AS (
    SELECT node.id AS node, 'title' AS source, NULL::uuid AS tab, NULL::integer AS page,
        NULL::text AS block, NULL::jsonb AS address, NULL::uuid AS thread, node.title AS text,
        3 + GREATEST(
            ts_rank_cd(to_tsvector('{config}'::regconfig, node.title), q.query, 32),
            word_similarity(q.folded, search_fold(node.title))
        ) AS rank,
        NULL::bigint AS cell_row, NULL::text AS cell_col
    FROM documents_node node JOIN found ON found.id = node.id CROSS JOIN q
    WHERE to_tsvector('{config}'::regconfig, node.title) @@ q.query
        OR q.folded <%% search_fold(node.title)
    UNION ALL
    SELECT node.id, 'link', NULL, NULL, NULL, NULL, NULL, node.href || ' ' || node.description,
        2 + GREATEST(
            ts_rank_cd(to_tsvector('{config}'::regconfig, node.description), q.query, 32),
            word_similarity(q.folded, search_fold(node.href))
        ),
        NULL, NULL
    FROM documents_node node JOIN found ON found.id = node.id CROSS JOIN q
    WHERE node.kind = 'link' AND (
        to_tsvector('{config}'::regconfig, node.description) @@ q.query
        OR q.folded <%% search_fold(node.href)
    )
    UNION ALL
    SELECT tab.document_id, 'tab', tab.id, NULL, NULL, NULL, NULL, tab.title,
        2 + GREATEST(
            ts_rank_cd(to_tsvector('{config}'::regconfig, tab.title), q.query, 32),
            word_similarity(q.folded, search_fold(tab.title))
        ),
        NULL, NULL
    FROM documents_tab tab JOIN found ON found.id = tab.document_id CROSS JOIN q
    WHERE to_tsvector('{config}'::regconfig, tab.title) @@ q.query
        OR q.folded <%% search_fold(tab.title)
    UNION ALL
    SELECT tab.document_id, 'block', tab.id, NULL, element.block, element.address, NULL,
        element.text, 1 + ts_rank_cd(element.words, q.query, 32), NULL, NULL
    FROM content_element element
    JOIN documents_tab tab ON tab.id = element.tab_id
    JOIN found ON found.id = tab.document_id
    CROSS JOIN q
    WHERE element.words @@ q.query
    UNION ALL
    SELECT tab.document_id, 'block', tab.id, NULL, grid."table", tabled.address, NULL,
        cell.text, 1 + ts_rank_cd(searched.words, q.query, 32), line.id, cell.col
    FROM content_gridrowwords searched
    JOIN content_gridrow line ON line.id = searched.grid_row_id
    JOIN content_grid grid ON grid.id = line.grid_id
    JOIN documents_tab tab ON tab.id = grid.tab_id
    JOIN found ON found.id = tab.document_id
    CROSS JOIN q
    CROSS JOIN LATERAL (
        SELECT key AS col, coalesce(line.shown ->> key, line.cells -> key ->> 'text')
        FROM (
            SELECT jsonb_object_keys(line.cells) UNION SELECT jsonb_object_keys(line.shown)
        ) AS keys(key)
    ) AS cell(col, text)
    LEFT JOIN content_element tabled
        ON tabled.tab_id = tab.id AND tabled.block = grid."table" AND tabled.type = 'table'
    WHERE searched.words @@ q.query AND to_tsvector('{config}'::regconfig, cell.text) @@ q.query
    UNION ALL
    SELECT COALESCE(tab.document_id, thread.file_id), 'comment', tab.id, NULL, NULL, NULL,
        thread.id, comment.body, 1 + ts_rank_cd(comment.words, q.query, 32), NULL, NULL
    FROM comments_comment comment
    JOIN comments_thread thread ON thread.id = comment.thread_id
    LEFT JOIN documents_tab tab ON tab.id = thread.tab_id
    JOIN found ON found.id = COALESCE(tab.document_id, thread.file_id)
    CROSS JOIN q
    WHERE comment.words @@ q.query
    UNION ALL
    SELECT tab.document_id, 'block', tab.id, page.number, element.block, element.address, NULL,
        page.text, 1 + ts_rank_cd(page.words, q.query, 32), NULL, NULL
    FROM content_element element
    JOIN documents_tab tab ON tab.id = element.tab_id
    JOIN found ON found.id = tab.document_id
    JOIN search_blobpage page ON page.source_id = element.content->'attrs'->>'blob'
        AND page.number >= COALESCE((element.content->'attrs'->>'first')::numeric, 1)
        AND page.number <= COALESCE((element.content->'attrs'->>'last')::numeric, page.number)
    CROSS JOIN q
    WHERE element.type = 'pdf' AND page.words @@ q.query
    UNION ALL
    SELECT node.id, 'page', NULL, page.number, NULL, NULL, NULL, page.text,
        1 + ts_rank_cd(page.words, q.query, 32), NULL, NULL
    FROM search_blobpage page
    JOIN documents_node node ON node.blob_id = page.source_id
    JOIN found ON found.id = node.id
    CROSS JOIN q
    WHERE page.words @@ q.query
    UNION ALL
    SELECT entry.node_id, 'data', NULL, NULL, NULL, NULL, NULL, board_text(entry.data),
        1 + ts_rank_cd(entry.words, q.query, 32), NULL, NULL
    FROM documents_boardentry entry
    JOIN found ON found.id = entry.node_id
    CROSS JOIN q
    WHERE entry.words @@ q.query
),
best AS (
    SELECT DISTINCT ON (node) *, count(*) OVER (PARTITION BY node) AS hits
    FROM hits ORDER BY node, rank DESC, page
)
SELECT best.node, best.source, best.tab, best.page, best.block, best.address, best.thread,
    best.hits,
    {snippet},
    best.cell_row, best.cell_col
FROM best JOIN documents_node node ON node.id = best.node CROSS JOIN q
ORDER BY best.rank DESC, node.updated_at DESC, node.title
LIMIT %s
"""

LISTED = """
SELECT node.id, 'title', NULL, NULL, NULL, NULL, NULL, 1, node.title, NULL, NULL
FROM documents_node node
WHERE node.id IN ({readable}) AND NOT (node.notes OR node.links OR node.boards){filters}
ORDER BY node.{date} DESC, node.title
LIMIT %s
"""

MAIL = """
WITH q AS (
    SELECT {query} AS query, search_fold(%s) AS folded
),
hits AS (
    SELECT message.id AS message, NULL::bigint AS attachment, NULL::integer AS page,
        message.text AS text,
        1 + GREATEST(
            ts_rank_cd(message.words, q.query, 32),
            word_similarity(q.folded, search_fold(message.subject))
        ) AS rank
    FROM mail_message message CROSS JOIN q
    WHERE message.owner_id = ANY(%s){filters}
        AND (message.words @@ q.query OR q.folded <%% search_fold(message.subject))
    UNION ALL
    SELECT message.id, attachment.id,
        CASE WHEN blob.media_type = '{pdf}' THEN page.number END, page.text,
        1 + ts_rank_cd(page.words, q.query, 32)
    FROM mail_attachment attachment
    JOIN mail_message message ON message.id = attachment.message_id
    JOIN blobs_blob blob ON blob.sha256 = attachment.blob_id
    JOIN search_blobpage page ON page.source_id = attachment.blob_id
    CROSS JOIN q
    WHERE message.owner_id = ANY(%s){filters} AND NOT attachment.inline AND page.words @@ q.query
    UNION ALL
    SELECT message.id, NULL, NULL, translation.text, 1 + ts_rank_cd(translation.words, q.query, 32)
    FROM mail_translation translation
    JOIN mail_message message ON message.id = translation.message_id
    CROSS JOIN q
    WHERE message.owner_id = ANY(%s){filters} AND translation.words @@ q.query
),
best AS (
    SELECT DISTINCT ON (message) *, count(*) OVER (PARTITION BY message) AS hits
    FROM hits ORDER BY message, rank DESC, page
)
SELECT best.message, best.attachment, best.page, best.hits,
    {snippet},
    ts_headline('{config}'::regconfig, message.subject, q.query, %s)
FROM best JOIN mail_message message ON message.id = best.message CROSS JOIN q
ORDER BY best.rank DESC, message.date DESC, message.id DESC
LIMIT %s
"""

MAIL_LISTED = """
SELECT message.id, NULL, NULL, 1, message.preview, message.subject
FROM mail_message message WHERE message.owner_id = ANY(%s){filters}
ORDER BY message.date DESC, message.id DESC
LIMIT %s
"""

FOLDERS = f"SELECT id FROM mail_folder WHERE owner_id = ANY(%s) AND {NAMED.format(name='name')}"


def _documents(user, wanted: Asked, within) -> tuple[str, list]:
    """The conditions on `node` the filters ask for."""
    conditions, params = [], []
    if wanted.kind:
        conditions.append("node.kind = %s")
        params.append(wanted.kind)
    if within:
        conditions.append("node.id = ANY(%s)")
        params.append([node.pk for node in within.descendants()])
    for value in wanted.sender:
        people = PEOPLE.format(name="first_name, last_name", address="email")
        conditions.append(f"node.created_by_id IN (SELECT id FROM users_user WHERE {people})")
        params.append(value)
    for value in wanted.folder:
        conditions.append(UNDER.format(column="node.id", table="documents_node", first=INSIDE))
        params.append(value)
    if wanted.period:
        made = "node.updated_at" if wanted.period.changed else "node.created_at"
        conditions.extend(period_of(made, wanted, params))
    return "".join(f" AND {condition}" for condition in conditions), params


def _mail(owners: list[int], wanted: Asked) -> tuple[str, list]:
    """The conditions on `message` the filters ask for; the junk and the trash only when a
    folder filter asks for them."""
    conditions, params = ["message.reacts_to_id IS NULL"], []
    for value in wanted.sender:
        conditions.append(
            PEOPLE.format(name="message.sender ->> 'name'", address="message.sender ->> 'address'")
        )
        params.append(value)
    for value in wanted.account:
        people = PEOPLE.format(name="account.name", address="account.address")
        conditions.append(
            "EXISTS (SELECT 1 FROM mail_account account"
            f" WHERE account.owner_id = message.owner_id AND {people}"
            " AND (account.id = message.account_id OR EXISTS ("
            "SELECT 1 FROM mail_arrival arrival JOIN mail_source source"
            " ON source.id = arrival.source_id"
            " WHERE arrival.message_id = message.id AND source.account_id = account.id)))"
        )
        params.append(value)
    for value in wanted.folder:
        conditions.append(
            UNDER.format(column="message.folder_id", table="mail_folder", first=FOLDERS)
        )
        params.extend([owners, value])
    if wanted.roles:
        conditions.append(
            "message.folder_id IN"
            " (SELECT id FROM mail_folder WHERE owner_id = ANY(%s) AND role = ANY(%s))"
        )
        params.extend([owners, wanted.roles])
    elif not wanted.folder:
        conditions.append(
            "message.folder_id NOT IN"
            " (SELECT id FROM mail_folder WHERE owner_id = ANY(%s) AND role = ANY(%s))"
        )
        params.extend([owners, HIDDEN])
    if wanted.attachment:
        conditions.append("message.attachments")
    if wanted.period:
        conditions.extend(period_of("message.date", wanted, params))
    return "".join(f" AND {condition}" for condition in conditions), params


def limit_of(request) -> int:
    try:
        limit = int(request.GET.get("limit", SHOWN))
    except ValueError:
        raise Refused(400, "invalid_limit") from None
    if not 1 <= limit <= MOST:
        raise Refused(400, "invalid_limit")
    return limit


def _cell(row: int, col: str) -> dict:
    """The cell's place as its table shows it, D7, by the row's key and the column's id, and
    the name of its table, by which an address leads to a table after the tab's first."""
    line = GridRow.objects.select_related("grid").get(pk=row)
    y = GridRow.objects.filter(grid=line.grid_id, position__lt=line.position).count()
    x = [each["id"] for each in line.grid.cols].index(col)
    name = line.grid.name
    return {"cell": f"{column(x)}{y + 1}", **({"name": name} if name else {})}


def found(user, rows: list[tuple]) -> list[dict]:
    """Each hit with its node, where the user finds it, and what matched: of a cell, its
    table's place with the cell's."""
    nodes = Node.objects.in_bulk([row[0] for row in rows])
    rows = [row for row in rows if row[0] in nodes]
    tabs = Tab.objects.in_bulk([row[2] for row in rows if row[2]])
    reaches = rights.reaches(user, nodes)
    results = []
    for (pk, source, tab, page, block, address, thread, hits, snippet, row, col), node in zip(
        rows, described([nodes[row[0]] for row in rows]), strict=True
    ):
        # Django has psycopg hand jsonb over as text, for JSONField to decode.
        place = address and json.loads(address)
        if row is not None:
            place = {**(place or {}), **_cell(row, col)}
        reach = reaches[pk]
        results.append(
            {
                **node,
                **along(reach),
                "source": source,
                "tab": tab and {"id": tab, "title": tabs[tab].title if tab in tabs else ""},
                "page": page,
                "block": block,
                "address": place,
                "thread": thread,
                "hits": hits,
                "snippet": snippet,
            }
        )
    return results


def found_documents(user, wanted: Asked, within, limit: int) -> list[dict]:
    readable, readable_params = rights.readable(user)
    filters, params = _documents(user, wanted, within)
    with transaction.atomic(), connection.cursor() as cursor:
        if not wanted.text:
            date = "updated_at" if not wanted.period or wanted.period.changed else "created_at"
            sql = LISTED.format(readable=readable, filters=filters, date=date)
            cursor.execute(sql, [*readable_params, *params, limit])
            return found(user, cursor.fetchall())
        query, query_params = matching(wanted.text)
        fuzzy = "" if OPERATORS.search(wanted.text) else wanted.text
        sql = SEARCH.format(
            readable=readable, filters=filters, query=query, config=CONFIG, snippet=SNIPPET
        )
        cursor.execute(
            "SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)", [str(LIKENESS)]
        )
        cursor.execute(sql, [*readable_params, *params, *query_params, fuzzy, HEADLINE, limit])
        return found(user, cursor.fetchall())


def _boxes(user) -> dict:
    """The shared mailboxes the user reads, by their ids."""
    held = [] if user.visitor else list(sharing.roles(user))
    return User.everyone.filter(pk__in=held, mailbox=True).in_bulk()


def _listed(user, boxes: dict, ids: list[int]) -> dict[int, dict]:
    """The messages as a list shows each, with the shared mailbox it is in, none in the user's
    own."""
    owners = dict(Message.objects.filter(pk__in=ids).values_list("pk", "owner_id"))
    found: dict[int, dict] = {}
    for owner in {*owners.values()}:
        box = boxes.get(owner)
        whose = [pk for pk, of in owners.items() if of == owner]
        shown = box and {"id": box.pk, "name": box.first_name}
        found |= {pk: each | {"box": shown} for pk, each in listed(box or user, whose).items()}
    return found


def found_mail(user, wanted: Asked, limit: int) -> list[dict]:
    """The user's mail and that of the shared mailboxes they read, ranked together."""
    boxes = _boxes(user)
    owners = [user.pk, *boxes]
    filters, params = _mail(owners, wanted)
    with transaction.atomic(), connection.cursor() as cursor:
        if not wanted.text:
            cursor.execute(MAIL_LISTED.format(filters=filters), [owners, *params, limit])
        else:
            query, query_params = matching(wanted.text)
            fuzzy = "" if OPERATORS.search(wanted.text) else wanted.text
            cursor.execute(
                "SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)",
                [str(LIKENESS)],
            )
            cursor.execute(
                MAIL.format(
                    query=query, filters=filters, config=CONFIG, pdf=store.PDF, snippet=SNIPPET
                ),
                [
                    *query_params,
                    fuzzy,
                    owners,
                    *params,
                    owners,
                    *params,
                    owners,
                    *params,
                    HEADLINE,
                    WHOLE,
                    limit,
                ],
            )
        rows = cursor.fetchall()
    messages = _listed(user, boxes, [row[0] for row in rows])
    names = dict(
        Attachment.objects.filter(pk__in=[row[1] for row in rows if row[1]]).values_list(
            "pk", "name"
        )
    )
    return [
        {
            **messages[pk],
            "attachment": attachment
            and {"id": attachment, "name": names[attachment], "page": page},
            "hits": hits,
            "snippet": snippet,
            "marked": subject,
        }
        for pk, attachment, page, hits, snippet, subject in rows
        if pk in messages
    ]


@api("GET")
def search(request):
    """Documents, mail, events, tasks and people apart, each ranked within its own, and the
    filters typed among the words as the box shows them. A folder narrows it to documents."""
    q = request.GET.get("q", "").strip()
    if len(q) > LONGEST:
        raise Refused(400, "query_too_long")
    limit = limit_of(request)
    zone = zone_of(request.GET.get("zone"))
    within, _ = folder(request.user, optional_id(request.GET.get("in")))
    wanted = asked(q)
    found = {
        "filters": wanted.filters,
        "documents": [],
        "mail": [],
        "conversations": [],
        "events": [],
        "tasks": [],
        "people": [],
        "versions": [],
        "help": [],
    }
    if wanted.invalid or (len(wanted.text) < 2 and not (wanted.narrowed and not wanted.text)):
        return JsonResponse(found)
    user = request.user
    if wanted.documents:
        found["documents"] = found_documents(user, wanted, within, limit)
    if wanted.versions:
        found["versions"] = found_versions(user, wanted, within, limit)
    if within is None:
        if wanted.mail:
            found["mail"] = found_mail(user, wanted, limit)
        if wanted.conversations:
            found["conversations"] = found_messages(user, wanted, limit)
        if wanted.events:
            found["events"] = found_events(user, wanted, zone, limit)
        if wanted.tasks:
            found["tasks"] = found_tasks(user, wanted, limit)
        if wanted.people:
            found["people"] = found_people(user, wanted, limit)
        if not wanted.narrowed:
            language = library.language_of(request.GET.get("lang"), user)
            found["help"] = library.found(user, wanted.text, language, limit)
    return JsonResponse(found)


@api("POST")
async def translate(request):
    """The words and filters the model reads in a sentence, once the installation's AI is on
    and the user lets the sentence out to it, this once or for all of their searches."""
    data = body(request)
    sentence = data.get("sentence")
    if not isinstance(sentence, str) or not sentence.strip():
        raise Refused(400, "invalid_sentence")
    if len(sentence) > LONGEST:
        raise Refused(400, "query_too_long")
    if data.get("consent") not in (None, "once"):
        raise Refused(400, "invalid_consent")
    if not await database(installation.enabled)():
        raise Refused(409, "ai_off")
    if data.get("consent") == "once":
        consent = ActionRun.Consented.ONCE
    elif await SearchConsent.objects.filter(user=request.user, translate=True).aexists():
        consent = ActionRun.Consented.USER
    else:
        raise Refused(428, "consent_needed")
    try:
        found = await translation.translate(request.user, sentence.strip(), consent)
    except translation.Untranslated as untranslated:
        raise Refused(502, untranslated.code) from None
    return JsonResponse({"translated": found})


MOST_HITS = 10_000


@api("GET", visitors=True)
def found_in(request, pk):
    """Each place a file's text holds the query, as its page and the rectangles it covers."""
    node, _ = live_pdf(request.user, pk)
    text = request.GET.get("q", "")
    if len(text) > LONGEST:
        raise Refused(400, "query_too_long")
    if not text.strip():
        return JsonResponse({"hits": []})
    found = pdf.found(store.path_of(ocr.readable(node.blob).sha256), text, MOST_HITS)
    if found is None:
        raise Refused(422, "too_many_hits")
    return JsonResponse({"hits": [{"page": page, "rects": rects} for page, rects in found]})
