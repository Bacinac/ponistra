"""What a document's own room keeps for each of its tabs, under the tab's id: its settings and
pages of its own, the count of its pages and slides, the tally of its numbers and notes, and
its headings."""

from pycrdt import Array, Doc, Map, XmlElement, XmlFragment, XmlText

from . import numbering, pages, tallies
from .operations import copy_text

KEPT = (
    pages.TABS,
    pages.COUNTS,
    numbering.NUMBERS,
    tallies.NOTES,
    tallies.HEADINGS,
    tallies.SLIDES,
)
SHARED = (Map, Array, XmlFragment)


def _made(value):
    return type(value)() if isinstance(value, SHARED) else value


def _copy(source, target) -> None:
    """The source's content into the target, an empty shared type of its kind."""
    if isinstance(source, Map):
        for key, value in source.items():
            target[key] = _made(value)
            if isinstance(value, SHARED):
                _copy(value, target[key])
    elif isinstance(source, Array):
        for value in source:
            target.append(_made(value))
            if isinstance(value, SHARED):
                _copy(value, target[len(target) - 1])
    else:
        for child in source.children:
            if isinstance(child, XmlText):
                copy_text(child, target.children.append(XmlText()))
            else:
                made = XmlElement(child.tag, dict(child.attributes))
                _copy(child, target.children.append(made))


def _put(kept: Map, key: str, value) -> None:
    kept[key] = _made(value)
    if isinstance(value, SHARED):
        _copy(value, kept[key])


def rekeyed(own: Doc, by: dict[str, str]) -> None:
    """What the room keeps for each tab moved to the tab's new id; what it kept for a tab the
    ids do not name is left behind."""
    with own.transaction():
        for name in KEPT:
            kept = own.get(name, type=Map)
            found = list(kept.items())
            for key, value in found:
                if key in by:
                    _put(kept, by[key], value)
            for key, _ in found:
                del kept[key]


def carried(source: Doc, target: Doc, tabs: list[str], names: tuple[str, ...]) -> None:
    """What the source room keeps under these names for the tabs, into the target's."""
    with target.transaction():
        for name in names:
            kept, into = source.get(name, type=Map), target.get(name, type=Map)
            for tab in tabs:
                if tab in kept:
                    _put(into, tab, kept[tab])
