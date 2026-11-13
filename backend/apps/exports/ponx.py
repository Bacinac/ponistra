"""A document as PONISTRA's own file (D10), to carry it elsewhere with nothing lost: a zip
of `mimetype` first, as in OpenDocument; `manifest.json` with the format and its version;
`document.json` with the tabs, theme and styles, the comments and the people they and the
proposed changes name; the exact Yjs state of the document's own room and of each tab, beside
a readable JSON of the tab's blocks, a table over the ceiling on cells without its rows; the
grids of the tables, the headers' and footers' in `grids.json` and each tab's beside its state,
by table; the defined names in `names.json`, by
id; under `files/` its images and PDFs and the file it was imported from; its versions only when
asked for, their grids' rows in pieces."""

import dataclasses
import json
import tempfile
import zipfile
from typing import IO

from django.utils import timezone
from pycrdt import Doc, Map

from apps.blobs import store
from apps.comments.models import Thread
from apps.content import blocks, grids, names, people, styles
from apps.content import rows as stored
from apps.content.table import Table, tables_of
from apps.documents.models import Node
from apps.users.models import User
from apps.versions.history import state_of
from apps.versions.models import Piece, State

FORMAT = "ponistra"
VERSION = 4
MANIFEST = "manifest.json"
DOCUMENT = "document.json"
OWN = "own.yjs"
GRIDS = "grids.json"
NAMES = "names.json"


def tab_state(tab: str) -> str:
    return f"tabs/{tab}/state.yjs"


def tab_content(tab: str) -> str:
    return f"tabs/{tab}/content.json"


def tab_grids(tab: str) -> str:
    return f"tabs/{tab}/grids.json"


def file_of(sha256: str) -> str:
    return f"files/{sha256}"


def kept_state(sha256: str) -> str:
    return f"versions/{sha256}.yjs"


def kept_piece(sha256: str) -> str:
    return f"versions/pieces/{sha256}.json"


def _when(moment) -> str | None:
    return moment and moment.isoformat()


def _threads(document: Node) -> list[dict]:
    threads = Thread.objects.filter(tab__document=document).prefetch_related("comments")
    return [
        {
            "tab": str(thread.tab_id),
            "anchor": thread.anchor,
            "quote": thread.quote,
            "created_at": _when(thread.created_at),
            "resolved_at": _when(thread.resolved_at),
            "resolved_by": thread.resolved_by_id,
            "comments": [
                {
                    "author": comment.author_id,
                    "outside_author": comment.outside_author,
                    "body": comment.body,
                    "created_at": _when(comment.created_at),
                    "edited_at": _when(comment.edited_at),
                }
                for comment in sorted(thread.comments.all(), key=lambda each: each.created_at)
            ],
        }
        for thread in threads.order_by("created_at")
    ]


def _versions(document: Node) -> list[dict]:
    versions = document.versions.order_by("number").prefetch_related("editors", "tabs")
    return [
        {
            "number": version.number,
            "title": version.title,
            "created_at": _when(version.created_at),
            "checked_at": _when(version.checked_at),
            "restored_from": version.restored_from,
            "editors": sorted(editor.pk for editor in version.editors.all()),
            "state": version.state.sha256,
            "names": version.names,
            "shared": version.shared,
            "tabs": [
                {
                    "tab": str(part.tab),
                    "parent": part.parent and str(part.parent),
                    "position": part.position,
                    "title": part.title,
                    "state": part.state.sha256,
                }
                for part in version.tabs_in_order()
            ],
            "grids": [
                {
                    "tab": part.tab and str(part.tab),
                    "table": part.table,
                    "name": part.name,
                    "cols": part.cols,
                    "frozen": part.frozen or None,
                    "pieces": part.pieces,
                }
                for part in version.grids.order_by("pk")
            ],
        }
        for version in versions.select_related("state")
    ]


def _grids(archive: zipfile.ZipFile, name: str, document: Node, held: list[Table]) -> None:
    """The grids by table, each as a version's grid keeps it, without the tab its place in
    the file names, written row by row."""

    def text(value) -> bytes:
        return json.dumps(value, ensure_ascii=False).encode()

    with archive.open(name, "w", force_zip64=True) as out:
        out.write(b"{")
        for at, table in enumerate(held):
            out.write(b"," * bool(at) + text(table.table) + b':{"name":' + text(table.name))
            out.write(b',"cols":' + text([grids.col_line(col) for col in table.cols]))
            out.write(b',"rows":[')
            written = False
            for part in stored.parts(document, table.grid):
                for _, row in part:
                    out.write(b"," * written + text(grids.row_line(row)))
                    written = True
            out.write(b'],"frozen":' + text(table.frozen) + b"}")
        out.write(b"}")


def _doc(state: bytes) -> Doc:
    doc = Doc()
    doc.apply_update(state)
    return doc


def _people(ids: set[int]) -> dict[str, dict]:
    return {
        str(user.pk): {"name": user.get_full_name(), "email": user.email}
        for user in User.everyone.filter(pk__in=ids - {None}).order_by("pk")
    }


def packed(document: Node, versions: bool = False) -> IO[bytes]:
    """The file, written to a temporary one that goes when it is closed."""
    own_state = state_of(document.room)
    own = _doc(own_state)
    named = people.users(people.own_roots(own))
    tabs = document.tabs_in_order()
    held = list(tables_of(document).values())
    found = tempfile.TemporaryFile()
    with zipfile.ZipFile(found, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = {"format": FORMAT, "version": VERSION, "made": timezone.now().isoformat()}
        archive.writestr("mimetype", store.PONX, zipfile.ZIP_STORED)
        archive.writestr(MANIFEST, json.dumps(manifest))
        archive.writestr(OWN, own_state)
        _grids(archive, GRIDS, document, [table for table in held if not table.tab])
        archive.writestr(NAMES, json.dumps(names.of_document(document), ensure_ascii=False))
        for tab in tabs:
            state = state_of(tab.room)
            doc = _doc(state)
            named |= people.users(people.tab_roots(doc))
            archive.writestr(tab_state(str(tab.pk)), state)
            _grids(
                archive,
                tab_grids(str(tab.pk)),
                document,
                [table for table in held if table.tab == str(tab.pk)],
            )
            small = grids.small_of_tab(tab)
            content = [dataclasses.asdict(block) for block in blocks.read(doc, small)]
            archive.writestr(tab_content(str(tab.pk)), json.dumps(content, ensure_ascii=False))
        files = {}
        shown = [link.blob for link in document.shown.select_related("blob")]
        for blob in shown + ([document.source] if document.source_id else []):
            if blob.sha256 not in files:
                files[blob.sha256] = blob.media_type
                archive.write(store.path_of(blob.sha256), file_of(blob.sha256), zipfile.ZIP_STORED)
        threads = _threads(document)
        for thread in threads:
            named |= {thread["resolved_by"]} | {each["author"] for each in thread["comments"]}
        kept_versions = []
        if versions:
            kept_versions = _versions(document)
            owns = {version["state"] for version in kept_versions}
            parts = {part["state"] for version in kept_versions for part in version["tabs"]}
            pieces = {
                sha256
                for version in kept_versions
                for part in version["grids"]
                for sha256 in part["pieces"]
            }
            for sha256, rows in Piece.objects.filter(
                document=document, sha256__in=pieces
            ).values_list("sha256", "rows"):
                archive.writestr(kept_piece(sha256), json.dumps(rows, ensure_ascii=False))
            for kept in State.objects.filter(document=document, sha256__in=owns | parts):
                archive.writestr(kept_state(kept.sha256), bytes(kept.data))
                doc = _doc(bytes(kept.data))
                if kept.sha256 in owns:
                    named |= people.users(people.own_roots(doc))
                if kept.sha256 in parts:
                    named |= people.users(people.tab_roots(doc))
            named |= {editor for version in kept_versions for editor in version["editors"]}
        described = {
            "title": document.title,
            "locale": document.locale,
            "created_at": _when(document.created_at),
            "updated_at": _when(document.updated_at),
            "theme": own.get(styles.THEME, type=Map).to_py() or {},
            "styles": own.get(styles.STYLES, type=Map).to_py() or {},
            "tabs": [
                {
                    "id": str(tab.pk),
                    "parent": tab.parent_id and str(tab.parent_id),
                    "position": tab.position,
                    "title": tab.title,
                }
                for tab in tabs
            ],
            "files": files,
            "shown": [blob.sha256 for blob in shown],
            "original": document.source_id,
            "imported": document.imported,
            "threads": threads,
            "people": _people(named),
        }
        if versions:
            described["versions"] = kept_versions
        archive.writestr(DOCUMENT, json.dumps(described, ensure_ascii=False, indent=1))
    found.seek(0)
    return found
