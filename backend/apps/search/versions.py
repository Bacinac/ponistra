"""The versions of documents found by the search box (D21), asked for by kind: what a document
said earlier, by its tabs' text and its tables' cells as each version holds them, and by a
version's title. A document is one hit, its newest version that says the words, with the
count of those that do."""

from django.db import connection, transaction

from apps.access import rights
from apps.documents.views import along, described
from apps.versions.models import Version, VersionTab
from apps.versions.views import describe

from .query import Asked
from .text import CONFIG, HEADLINE, INSIDE, PEOPLE, TAIL, UNDER, matching, period_of

SNIPPET = (
    f"regexp_replace(ts_headline('{CONFIG}'::regconfig, best.text || ' {TAIL}', q.query, %s),"
    f" ' {TAIL}$', '')"
)
TITLE = f"to_tsvector('{CONFIG}'::regconfig, version.title)"
EDITED = (
    "EXISTS (SELECT 1 FROM versions_version_editors edited"
    " JOIN users_user editor ON editor.id = edited.user_id"
    " WHERE edited.version_id = version.id AND {people})"
)

VERSIONS = f"""
WITH found AS MATERIALIZED (
    SELECT node.id FROM documents_node node WHERE node.id IN ({{readable}}){{nodes}}
),
q AS (
    SELECT {{query}} AS query
),
hits AS (
    SELECT version.id AS version, version.document_id AS document, version.number,
        version.created_at, part.tab, state.text,
        ts_rank_cd(state.words, q.query, 32) AS rank
    FROM versions_versiontab part
    JOIN versions_state state ON state.id = part.state_id
    JOIN versions_version version ON version.id = part.version_id
    JOIN found ON found.id = version.document_id
    CROSS JOIN q
    WHERE state.words @@ q.query{{filters}}
    UNION ALL
    SELECT version.id, version.document_id, version.number, version.created_at, grid.tab,
        piece.text, ts_rank_cd(piece.words, q.query, 32)
    FROM versions_versiongrid grid
    JOIN versions_version version ON version.id = grid.version_id
    JOIN found ON found.id = version.document_id
    JOIN versions_piece piece ON piece.document_id = version.document_id
        AND piece.sha256 IN (SELECT jsonb_array_elements_text(grid.pieces))
    CROSS JOIN q
    WHERE piece.words @@ q.query{{filters}}
    UNION ALL
    SELECT version.id, version.document_id, version.number, version.created_at, NULL,
        version.title, 2 + ts_rank_cd({TITLE}, q.query, 32)
    FROM versions_version version
    JOIN found ON found.id = version.document_id
    CROSS JOIN q
    WHERE {TITLE} @@ q.query{{filters}}
),
each AS (
    SELECT DISTINCT ON (version) * FROM hits ORDER BY version, rank DESC, tab
),
best AS (
    SELECT DISTINCT ON (document) *, count(*) OVER (PARTITION BY document) AS hits
    FROM each ORDER BY document, number DESC
)
SELECT best.version, best.tab, best.hits, {SNIPPET}
FROM best CROSS JOIN q
ORDER BY best.created_at DESC, best.version
LIMIT %s
"""

LISTED = """
SELECT latest.id, NULL::uuid, 1, latest.title FROM (
    SELECT DISTINCT ON (version.document_id) version.id, version.title, version.created_at
    FROM versions_version version JOIN documents_node node ON node.id = version.document_id
    WHERE node.id IN ({readable}){nodes}{filters}
    ORDER BY version.document_id, version.number DESC
) AS latest
ORDER BY latest.created_at DESC, latest.id
LIMIT %s
"""


def _nodes(wanted: Asked, within) -> tuple[str, list]:
    """The conditions on `node` the filters ask for: which documents' versions."""
    conditions, params = [], []
    if within:
        conditions.append("node.id = ANY(%s)")
        params.append([node.pk for node in within.descendants()])
    for value in wanted.folder:
        conditions.append(UNDER.format(column="node.id", table="documents_node", first=INSIDE))
        params.append(value)
    return "".join(f" AND {condition}" for condition in conditions), params


def _versions(wanted: Asked) -> tuple[str, list]:
    """The conditions on `version` the filters ask for: a sender is one of its editors, a
    period is when it was taken."""
    conditions, params = [], []
    for value in wanted.sender:
        people = PEOPLE.format(name="editor.first_name, editor.last_name", address="editor.email")
        conditions.append(EDITED.format(people=people))
        params.append(value)
    if wanted.period:
        conditions.extend(period_of("version.created_at", wanted, params))
    return "".join(f" AND {condition}" for condition in conditions), params


def found_versions(user, wanted: Asked, within, limit: int) -> list[dict]:
    readable, readable_params = rights.readable(user)
    nodes, node_params = _nodes(wanted, within)
    filters, params = _versions(wanted)
    with transaction.atomic(), connection.cursor() as cursor:
        if not wanted.text:
            sql = LISTED.format(readable=readable, nodes=nodes, filters=filters)
            cursor.execute(sql, [*readable_params, *node_params, *params, limit])
        else:
            query, query_params = matching(wanted.text)
            sql = VERSIONS.format(readable=readable, nodes=nodes, query=query, filters=filters)
            cursor.execute(
                sql,
                [
                    *readable_params,
                    *node_params,
                    *query_params,
                    *params,
                    *params,
                    *params,
                    HEADLINE,
                    limit,
                ],
            )
        rows = cursor.fetchall()
    return found(user, rows)


def found(user, rows: list[tuple]) -> list[dict]:
    versions = (
        Version.objects.filter(pk__in=[row[0] for row in rows])
        .select_related("document")
        .prefetch_related("editors")
        .in_bulk()
    )
    rows = [row for row in rows if row[0] in versions]
    documents = [versions[row[0]].document for row in rows]
    reaches = rights.reaches(user, {node.pk for node in documents})
    titles = {
        (part.version_id, part.tab): part.title
        for part in VersionTab.objects.filter(
            version_id__in=[row[0] for row in rows if row[1]],
            tab__in=[row[1] for row in rows if row[1]],
        )
    }
    return [
        {
            **describe(versions[pk]),
            "document": {**node, **along(reaches[versions[pk].document_id])},
            "tab": tab and {"id": tab, "title": titles.get((pk, tab), "")},
            "hits": hits,
            "snippet": snippet,
        }
        for (pk, tab, hits, snippet), node in zip(rows, described(documents), strict=True)
    ]
