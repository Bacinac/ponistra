"""What passes between the backend and the reader: a request is a JSON head and the file, an
answer lines of JSON, each value of a closed set of types, a line {"file": n} followed by n bytes
as they are. Never pickle: a reader that a file took over must not run code in the backend."""

import base64
import dataclasses
import json
from datetime import datetime
from enum import Enum
from functools import cache

TAG = "\x00"


@cache
def _types() -> dict[str, type]:
    from apps.blobs.edits import Edits, Mark
    from apps.content.blocks import Block, Cell, Field, Grid, Note, Placed, Run
    from apps.content.grids import Formula, Look
    from apps.exports.annotated import Discussed, Filled, Highlight, Stroke
    from apps.imports.reading import Imported, Remark, Tab, Thread

    return {
        kind.__name__: kind
        for kind in (
            *(Block, Cell, Field, Grid, Note, Placed, Run, Formula, Look),
            *(Imported, Remark, Tab, Thread),
            *(Edits, Mark),
            *(Discussed, Filled, Highlight, Stroke),
        )
    }


@cache
def _names() -> dict[type, str]:
    return {kind: name for name, kind in _types().items()}


def plain(value):
    """The value as JSON holds it, each type JSON would lose tagged; any other type is refused."""
    kind = type(value)
    if value is None or kind in (bool, int, float, str):
        return value
    if isinstance(value, Enum):
        return plain(value.value)
    if kind is list:
        return [plain(each) for each in value]
    if kind is dict:
        if all(type(key) is str for key in value):
            if TAG in value:
                raise TypeError(f"a key {TAG!r} cannot pass")
            return {key: plain(each) for key, each in value.items()}
        return {TAG: "map", "v": [[plain(key), plain(each)] for key, each in value.items()]}
    if kind is tuple:
        return {TAG: "tuple", "v": [plain(each) for each in value]}
    if kind in (set, frozenset):
        return {TAG: "set", "v": [plain(each) for each in value]}
    if kind is bytes:
        return {TAG: "bytes", "v": base64.b64encode(value).decode()}
    if kind is datetime:
        return {TAG: "datetime", "v": value.isoformat()}
    name = _names().get(kind)
    if name is None:
        raise TypeError(f"{kind.__qualname__} cannot pass to the backend")
    if dataclasses.is_dataclass(kind):
        fields = {each.name: plain(getattr(value, each.name)) for each in dataclasses.fields(kind)}
        return {TAG: name, "v": fields}
    shared = plain(list(value) if isinstance(value, list) else dict(value))
    return {TAG: name, "v": shared, "key": getattr(value, "key", None)}


def _made(found: dict):
    name = found.get(TAG)
    if name is None:
        return found
    value = found["v"]
    if name == "map":
        return {key: each for key, each in value}
    if name == "tuple":
        return tuple(value)
    if name == "set":
        return set(value)
    if name == "bytes":
        return base64.b64decode(value)
    if name == "datetime":
        return datetime.fromisoformat(value)
    kind = _types().get(name)
    if kind is None:
        raise ValueError(f"the reader sent a value of type {name!r}")
    if dataclasses.is_dataclass(kind):
        return kind(**value)
    made = kind(value)
    if found.get("key") is not None:
        made.key = found["key"]
    return made


def line(value) -> bytes:
    return json.dumps(plain(value), separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def parsed(raw: bytes):
    return json.loads(raw, object_hook=_made)
