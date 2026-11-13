"""What the editors of each tab keep in the document's own state, so the tabs after it and
the contents need not load it: the tally of its numbers under `numbers`, the count of its
notes under `notes`, its headings in reading order under `headings` and the count of its
slides under `slideCounts`, each keyed by the tab's id."""

import json

from pycrdt import Array, Doc, Map, Text, XmlElement, XmlFragment, XmlText

from . import blocks
from .numbering import NUMBERS, numbered
from .pages import COUNTS, PARTS
from .slides import slides_of

NOTES = "notes"
HEADINGS = "headings"
SLIDES = "slideCounts"
KEPT = frozenset({NUMBERS, NOTES, HEADINGS, SLIDES, COUNTS})


def written(state: bytes) -> str:
    """A document's own state as its users wrote it, without what the editors keep of each tab
    on opening it: the same for the same content however its updates came about."""
    own = Doc()
    own.apply_update(state)
    read = {
        name: _plain(own.get(name, type=XmlFragment if name in PARTS else Map))
        for name in own.keys()
        if name not in KEPT
    }
    return json.dumps({name: value for name, value in read.items() if value}, sort_keys=True)


def _plain(value):
    if isinstance(value, Map):
        return {key: _plain(each) for key, each in value.items()}
    if isinstance(value, Array):
        return [_plain(each) for each in value]
    if isinstance(value, (XmlFragment, XmlElement, XmlText, Text)):
        return str(value)
    return value


def keep(own: Doc, tab: str, content: list[blocks.Block], styles: dict) -> None:
    """The tab's tallies as its editors would write them on opening it."""
    order = blocks.in_order(content)
    tally = numbered(order, {"styles": styles, "start": {}})[1]
    notes = {"foot": 0, "end": 0}
    for block in order:
        for note in block.notes:
            notes[note.kind] += 1
    headings = [
        {
            "id": block.id,
            "level": block.attrs["level"],
            "text": block.text.strip(),
            "style": block.attrs.get("style"),
            "restart": block.attrs.get("restart") is True,
        }
        for block in order
        if block.type == "heading"
    ]
    with own.transaction():
        if tally:
            own.get(NUMBERS, type=Map)[tab] = tally
        if any(notes.values()):
            own.get(NOTES, type=Map)[tab] = notes
        if headings:
            own.get(HEADINGS, type=Map)[tab] = headings
        if count := len(slides_of(content)):
            own.get(SLIDES, type=Map)[tab] = count
