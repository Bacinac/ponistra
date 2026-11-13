"""What a board keeps (D36-2): its own documents of JSON by collection and key, read by the page
as whoever opens it reads the board, written as whoever may edit it writes it."""

import json
import re
from typing import Any

from django.db import transaction
from django.db.models import Count

from apps.core.api import Refused

from .models import BoardEntry, Node

NAME = re.compile(r"[\w.~:@+-]{1,200}")
MOST_BYTES = 256 * 1024
MOST_ROWS = 10_000
MOST_WRITES = 500
REMOVED = {"__delete__": True}


def name_of(value: Any) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise Refused(400, "invalid_board_name")
    return value


def described(entry: BoardEntry) -> dict:
    return {
        "collection": entry.collection,
        "key": entry.key,
        "data": entry.data,
        "version": entry.version,
        "updated_at": entry.updated_at,
    }


def collections(node: Node) -> list[dict]:
    return list(
        node.board_entries.values("collection").annotate(count=Count("pk")).order_by("collection")
    )


def entry(node: Node, collection: Any, key: Any) -> BoardEntry:
    found = node.board_entries.filter(collection=name_of(collection), key=name_of(key)).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


def entries(
    node: Node,
    collection: Any,
    where: dict[str, Any] | None = None,
    limit: int = MOST_ROWS,
    after: str | None = None,
) -> list[BoardEntry]:
    """A collection in the order of its keys, `after` the key given; `where` keeps those whose
    fields hold these values."""
    found = node.board_entries.filter(collection=name_of(collection))
    if where:
        found = found.filter(data__contains=where)
    if after:
        found = found.filter(key__gt=name_of(after))
    return list(found.order_by("key")[: max(1, min(limit, MOST_ROWS))])


def _merged(kept: dict, given: dict) -> dict:
    merged = dict(kept)
    for field, value in given.items():
        if value == REMOVED:
            merged.pop(field, None)
        elif isinstance(value, dict) and isinstance(merged.get(field), dict):
            merged[field] = _merged(merged[field], value)
        else:
            merged[field] = value
    return merged


def _written(node: Node, write: dict, user, agent: str) -> dict:
    if not isinstance(write, dict) or write.get("op") not in ("set", "update", "delete"):
        raise Refused(400, "invalid_board_write")
    collection, key = name_of(write.get("collection")), name_of(write.get("key"))
    expected = write.get("if_version")
    place = node.board_entries.select_for_update()
    if write["op"] == "delete":
        found = place.filter(collection=collection, key=key).first()
        if expected is not None and (found.version if found else 0) != expected:
            raise Refused(409, "version_conflict")
        if found:
            found.delete()
        return {"collection": collection, "key": key, "data": None, "version": 0}
    data = write.get("data")
    if not isinstance(data, dict):
        raise Refused(400, "invalid_board_write")
    found, made = place.get_or_create(
        collection=collection,
        key=key,
        defaults={"node": node, "data": {}, "version": 0},
    )
    if made and node.board_entries.filter(collection=collection).count() > MOST_ROWS:
        raise Refused(413, "board_data_too_large")
    if expected is not None and found.version != expected:
        raise Refused(409, "version_conflict")
    found.data = _merged(found.data if write["op"] == "update" else {}, data)
    if len(json.dumps(found.data).encode()) > MOST_BYTES:
        raise Refused(413, "board_data_too_large")
    found.version += 1
    found.updated_by = user
    found.agent = agent
    found.save()
    return described(found)


def written(node: Node, writes: list[dict], user, agent: str = "") -> list[dict]:
    """The writes, all of them or none: each sets a document, merges fields into it (a field given
    as `{"__delete__": true}` leaves) or deletes it, `if_version` refusing one that moved on."""
    if not isinstance(writes, list) or not 0 < len(writes) <= MOST_WRITES:
        raise Refused(400, "invalid_board_write")
    with transaction.atomic():
        # Two writers at a full collection would each count room for the row of its own.
        Node.objects.select_for_update().get(pk=node.pk)
        return [_written(node, write, user, agent) for write in writes]


def read(request, node: Node) -> dict:
    """What a page asks by address: a document, a collection, or which collections there are."""
    collection, key = request.GET.get("collection"), request.GET.get("key")
    if collection is None:
        return {"collections": collections(node)}
    if key is None:
        return {"entries": [described(each) for each in entries(node, collection)]}
    return described(entry(node, collection, key))
