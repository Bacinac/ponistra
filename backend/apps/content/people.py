"""The users a document's content names. A proposed change carries its author's name and, made
here, their user id, by which its author goes on writing in it; on another installation the
same id is someone else."""

from collections.abc import Iterator

from pycrdt import Array, Doc, Map, XmlElement, XmlFragment, XmlText

from . import blocks, pages

CHANGES = ("insertion", "deletion", "formatting")


def tab_roots(doc: Doc) -> list:
    return [blocks.body_of(doc)]


def own_roots(own: Doc) -> list:
    return [own.get(part, type=XmlFragment) for part in pages.PARTS] + [
        own.get(pages.TABS, type=Map)
    ]


def _texts(shared) -> Iterator[XmlElement | XmlText]:
    if isinstance(shared, (Map, Array)):
        for value in shared.values() if isinstance(shared, Map) else shared:
            yield from _texts(value)
    elif isinstance(shared, (XmlFragment, XmlElement)):
        if isinstance(shared, XmlElement):
            yield shared
        for child in shared.children:
            yield from _texts(child)
    elif isinstance(shared, XmlText):
        yield shared


def _user(change) -> int | None:
    user = change.get("user") if isinstance(change, dict) else None
    return int(user) if isinstance(user, (int, float)) else None


def _changes(shared) -> Iterator[tuple[XmlElement | XmlText, str, dict, int, int]]:
    """Each change naming a user: where it is held, under what name, and over which bytes of a
    text."""
    for each in _texts(shared):
        if isinstance(each, XmlElement):
            for name in CHANGES:
                change = each.attributes.get(name)
                if _user(change) is not None:
                    yield each, name, change, 0, 0
            continue
        at = 0
        for part, attributes in each.diff():
            size = len(part.encode())
            for name, change in (attributes or {}).items():
                if blocks.mark_name(name) in CHANGES and _user(change) is not None:
                    yield each, name, change, at, at + size
            at += size


def users(roots: list) -> set[int]:
    return {_user(change) for root in roots for _, _, change, _, _ in _changes(root)}


def renamed(roots: list, by: dict[int, int | None]) -> None:
    """Each change's user made the one they are here, or none where they have no account."""
    found = [each for root in roots for each in _changes(root)]
    for holder, name, change, start, end in found:
        user = by.get(_user(change))
        if user == _user(change):
            continue
        made = {key: value for key, value in change.items() if key != "user"}
        if user is not None:
            made["user"] = user
        if isinstance(holder, XmlElement):
            holder.attributes[name] = made
        else:
            holder.format(start, end, {name: made})
