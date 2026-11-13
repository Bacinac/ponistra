"""A document's pages: the page setup and the headers and footers, the document's own under
`page` and the fragments named after the parts in its own state, and those of a tab that has
pages of its own under that tab's settings in `tabs`, and each tab's count of pages under
`pages`, by its id. A section break starts a section of the tab on a new page; what the section
sets itself is kept under the tab's settings in `sections`, by the break's id: its page setup
and each header or footer it names, an empty one blank. What it does not set it takes from the
section before, the page setup without its `start`. Lengths are in centimetres, the width and
height as the page lies; `start` is the first page's number where it does not number on from
the pages before."""

from collections.abc import Mapping
from functools import partial

from pycrdt import Doc, Map, XmlFragment

from . import blocks, operations
from .grids import Laid
from .sheets import Sheets

PAGE = "page"
TABS = "tabs"
SECTIONS = "sections"
COUNTS = "pages"
PARTS = ("header", "footer", "headerFirst", "footerFirst")
DEFAULT = {
    "width": 21.0,
    "height": 29.7,
    "top": 2.5,
    "right": 2.5,
    "bottom": 2.5,
    "left": 2.5,
    "header": 1.25,
    "footer": 1.25,
    "firstPage": False,
}


def _holder(own: Doc, tab: str | None) -> Map | None:
    if tab is None:
        return None
    settings = own.get(TABS, type=Map)
    if tab not in settings:
        settings[tab] = Map()
    return settings[tab]


def write(
    own: Doc,
    sheets: Sheets,
    page: dict,
    parts: dict[str, list[blocks.Block]],
    tab: str | None = None,
):
    """The document's pages, or the tab's own, the grids of their headers' and footers'
    tables written into the sheets of the document's own, each table a new one, as the same
    parts can be written for several tabs."""
    holder = _holder(own, tab)
    given = {name: value for name, value in page.items() if value is not None}
    if holder is None:
        own.get(PAGE, type=Map).update(given)
    else:
        holder[PAGE] = Map(given)
    for name in PARTS:
        if not parts.get(name):
            continue
        if holder is not None:
            holder[name] = XmlFragment()
        into = partial(_part, tab=tab, name=name)
        written = operations.write(own, sheets, blocks.retabled(parts[name]), into=into)
        own.apply_update(written.update)


def _part(own: Doc, tab: str | None, name: str) -> XmlFragment:
    return own.get(name, type=XmlFragment) if tab is None else own.get(TABS, type=Map)[tab][name]


def _sections(own: Doc, tab: str) -> Map:
    holder = _holder(own, tab)
    if SECTIONS not in holder:
        holder[SECTIONS] = Map()
    return holder[SECTIONS]


def write_section(
    own: Doc,
    sheets: Sheets,
    tab: str,
    section: str,
    page: dict | None,
    parts: dict[str, list[blocks.Block]],
):
    """What the section after the break sets itself: its page setup where it has one of its
    own, and the headers and footers it names."""
    kept = _sections(own, tab)
    kept[section] = Map()
    holder = kept[section]
    if page is not None:
        holder[PAGE] = Map({name: value for name, value in page.items() if value is not None})
    for name in PARTS:
        if name not in parts:
            continue
        holder[name] = XmlFragment()
        if not parts[name]:
            continue
        into = partial(_section_part, tab=tab, section=section, name=name)
        written = operations.write(own, sheets, blocks.retabled(parts[name]), into=into)
        own.apply_update(written.update)


def _section_part(own: Doc, tab: str, section: str, name: str) -> XmlFragment:
    return own.get(TABS, type=Map)[tab][SECTIONS][section][name]


def _held(holder: Map) -> list[XmlFragment]:
    return [holder[name] for name in PARTS if isinstance(holder.get(name), XmlFragment)]


def fragments(own: Doc) -> list[XmlFragment]:
    """Every header's and footer's fragment, the document's, its tabs' and their sections'."""
    found = [own.get(name, type=XmlFragment) for name in PARTS]
    for holder in own.get(TABS, type=Map).values():
        if not isinstance(holder, Map):
            continue
        found += _held(holder)
        sections = holder.get(SECTIONS)
        if isinstance(sections, Map):
            for section in sections.values():
                if isinstance(section, Map):
                    found += _held(section)
    return found


def holding(own: Doc, table: str) -> XmlFragment | None:
    """The header or footer the table is in."""
    return next((each for each in fragments(own) if table in blocks.table_ids(each)), None)


def _own(own: Doc, tab: str | None) -> Map | None:
    holder = own.get(TABS, type=Map).get(tab) if tab is not None else None
    return holder if isinstance(holder, Map) and PAGE in holder else None


def owns(own: Doc, tab: str) -> bool:
    """Whether the tab has pages of its own."""
    return _own(own, tab) is not None


def setup(own: Doc, tab: str | None = None) -> dict:
    """The page setup a tab has: its own where it has one, else the document's."""
    holder = _own(own, tab)
    found = holder[PAGE] if holder is not None else own.get(PAGE, type=Map)
    return {**DEFAULT, **dict(found)}


def read(
    own: Doc, grids: Mapping[str, Laid], tab: str | None = None
) -> tuple[dict, dict[str, list[blocks.Block]]]:
    """The pages a tab has, its own where it has them, else the document's: the setup and
    the headers and footers, their tables with the grids of the document's own."""
    holder = _own(own, tab)
    parts = {}
    for name in PARTS:
        fragment = holder.get(name) if holder is not None else own.get(name, type=XmlFragment)
        found = blocks.read(own, grids, fragment) if isinstance(fragment, XmlFragment) else []
        if found:
            parts[name] = found
    return setup(own, tab), parts


def _kept_sections(own: Doc, tab: str) -> Map | None:
    holder = own.get(TABS, type=Map).get(tab)
    sections = holder.get(SECTIONS) if isinstance(holder, Map) else None
    return sections if isinstance(sections, Map) else None


def sections(
    own: Doc, grids: Mapping[str, Laid], tab: str
) -> dict[str, tuple[dict | None, dict[str, list[blocks.Block]]]]:
    """What each section of the tab sets itself, by the id of the break it follows."""
    kept = _kept_sections(own, tab)
    return {id: section(own, grids, tab, id) for id in (kept.keys() if kept is not None else ())}


def section(
    own: Doc, grids: Mapping[str, Laid], tab: str, break_id: str
) -> tuple[dict | None, dict[str, list[blocks.Block]]]:
    """What the section after the break sets itself: its own page setup, None where it takes
    the one before, and the headers and footers it names, an empty one as no blocks."""
    found = _kept_sections(own, tab)
    kept = found.get(break_id) if found is not None else None
    if not isinstance(kept, Map):
        return None, {}
    page = kept.get(PAGE)
    parts = {
        name: blocks.read(own, grids, kept[name])
        for name in PARTS
        if isinstance(kept.get(name), XmlFragment)
    }
    return ({**DEFAULT, **dict(page)} if isinstance(page, Map) else None), parts
