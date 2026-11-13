"""A document's tabs opened and closed beside what the user does in them: a copy a run opens,
and a tab closed by the user or with the run that opened it."""

from django.db import transaction

from apps.collab.models import Update
from apps.collab.server import announce, change, read_grids, revoke, rewrite
from apps.content import grids, pages
from apps.content.operations import Copy, open_tab
from apps.versions import history

from .models import Node, Tab


def tabs_changed(document: Node) -> None:
    transaction.on_commit(lambda: announce(document.room, "tabs"))


def renumbered(document: Node) -> None:
    """The tabs number on from those before them, so a new order reads them all again."""
    document.tabs.update(derived_at=None)


def open_copy(copy: Copy, user) -> Tab:
    """The copy as the last tab beside the one it copies, with that tab's own pages where it
    has them and what its sections set themselves."""
    document, source = copy.tab.document, str(copy.tab.pk)

    def write() -> Tab:
        with transaction.atomic():
            tab = open_tab(document, copy.title, copy.tab.parent)
            Update.objects.create(document=document, tab=tab, room=tab.room, data=copy.state)
            for laid in copy.grids:
                grids.put(document, str(tab.pk), laid)
            history.contributed(document.pk, user.pk)
        return tab

    tab = rewrite(document.pk, write)
    own, sections = read_grids(
        document.room,
        lambda own, held: (
            pages.read(own, held.grids(), source) if pages.owns(own, source) else None,
            pages.sections(own, held.grids(), source),
        ),
    )

    def written(doc, sheets) -> None:
        if own is not None:
            pages.write(doc, sheets, *own, str(tab.pk))
        for id, (page, parts) in sections.items():
            pages.write_section(doc, sheets, str(tab.pk), id, page, parts)

    if own is not None or sections:
        change(document.room, written)
    tabs_changed(document)
    return tab


def close(tab: Tab, by=None) -> None:
    """Deletes the tab, its grids with it, so a live book of the document reads its grids again.
    A tab a user closes is kept in a version of the document first; a failed run's copy goes
    without a trace."""
    document = tab.document

    def deleted() -> None:
        if by is not None:
            history.take(document)
        tab.delete()
        renumbered(document)

    rewrite(document.pk, deleted)
    if by is not None:
        history.contributed(document.pk, by.pk)
    tabs_changed(document)
    revoke()
