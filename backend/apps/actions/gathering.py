"""Gathering (A5): the same data out of several documents and PDF files into one table, a row
for each, in a document made beside them. What the model is asked of each, what it reads of
it and the table the rows make."""

from apps.access import rights
from apps.access.models import Role
from apps.ai.model import Choice, Prompt
from apps.ai.reading import text_of
from apps.collab import server
from apps.content import blocks
from apps.content.operations import Refused
from apps.documents.models import Node
from apps.documents.printing import compact
from apps.search.models import BlobText

LONGEST = 400_000
SOURCE = {
    "hr": "Dokument",
    "en": "Document",
    "en-GB": "Document",
    "de": "Dokument",
    "fr": "Document",
    "it": "Documento",
    "es": "Documento",
}
ROUTES = {Node.Kind.DOCUMENT: "d", Node.Kind.FILE: "p"}
GATHER = """You pull data out of one document in PONISTRA, an office suite, into a row of a \
table that gathers the same data from several documents, a row for each. The user's message \
is the document: each block on a line of its own after its id in brackets and its kind, a \
table's rows after it, or a PDF's text page by page.

Give the row with one call to the row tool. {columns} Take only what the document says, in \
the language it is written in, and leave a cell empty where it says nothing. Write numbers, \
amounts and dates as the table's language ({locale}) types them, so the table computes with \
them, without the currency or the unit a column's name carries."""
FIXED = "Its cells are, in this order: {names}."
CHOSEN = """Choose the table's columns from what the document holds that documents of its \
kind hold too, such as a contract's parties, dates, amounts and terms: at most twelve, each \
with a short name in the table's language, the currency or the unit in it where its values \
have one, and the value this document gives it."""


def _row(columns: list[str]) -> Choice:
    if columns:
        cells = {
            "type": "array",
            "items": {"type": "string"},
            "minItems": len(columns),
            "maxItems": len(columns),
        }
        description = "Gives the row: the value of each column, in their order."
    else:
        cells = {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "column": {"type": "string", "minLength": 1, "maxLength": 100},
                    "value": {"type": "string"},
                },
                "required": ["column", "value"],
                "additionalProperties": False,
            },
        }
        description = "Gives the table's columns, each with its value in this document."
    return Choice(
        description,
        {
            "type": "object",
            "properties": {"cells": cells},
            "required": ["cells"],
            "additionalProperties": False,
        },
    )


def extract(content: str, columns: list[str], locale: str) -> Prompt:
    """The row of one document, of the columns given or, with none, of those the model chooses
    from it for the rest to follow."""
    named = FIXED.format(names="; ".join(columns)) if columns else CHOSEN
    return Prompt(
        GATHER.format(columns=named, locale=locale), content, {"row": _row(columns)}, steps=3
    )


def row_of(answer: dict, columns: list[str]) -> tuple[list[str], list[str]]:
    """The columns and the row the model gave."""
    if columns:
        return columns, answer["cells"]
    return [cell["column"] for cell in answer["cells"]], [cell["value"] for cell in answer["cells"]]


def readable(node: Node | None, user) -> None:
    """Refuses a node gone or one the user may no longer read."""
    ancestry = node.ancestry() if node else []
    if node is None or not node.is_live(ancestry):
        raise Refused("not_found")
    if not rights.covers(rights.reach(user, ancestry).role, Role.READ):
        raise Refused("not_found")


def text_in(node: Node | None, user) -> str:
    """What the model reads of a document, tab by tab, or of a PDF file, page by page, while
    the user may still read it."""
    readable(node, user)
    if node.kind == Node.Kind.FILE:
        found = BlobText.objects.filter(blob_id=node.blob_id).first()
        pages = found.pages.order_by("number") if found else []
        text = "\n\n".join(f"[page {page.number}]\n{page.text}" for page in pages if page.text)
    else:
        tabs = node.tabs_in_order()
        read = [
            text_of(server.read_grids(tab.room, lambda doc, held: blocks.read(doc, held.grids())))
            for tab in tabs
        ]
        text = "\n\n".join(
            f"[tab {tab.title or at}]\n{each}" if len(tabs) > 1 else each
            for at, (tab, each) in enumerate(zip(tabs, read, strict=True), start=1)
            if each
        )
    if not text.strip():
        raise Refused("empty")
    if len(text) > LONGEST:
        raise Refused("too_big", str(len(text)))
    return text


def table(rows: list[tuple[Node | None, str, list[str]]], columns: list[str], locale: str) -> dict:
    """The table the rows make, after a header of the columns, each row's first cell its
    document's title, linked to it while it is there."""

    def source(node: Node | None, title: str) -> dict:
        text = {"type": "text", "text": title}
        if node is not None:
            href = f"/{ROUTES[node.kind]}/{compact(node.pk)}"
            text["marks"] = [{"type": "link", "attrs": {"href": href}}]
        return {"blocks": [{"type": "paragraph", "content": [text]}]}

    return {
        "op": "table",
        "at": {"start": "body"},
        "rows": [
            [SOURCE[locale], *columns],
            *(
                [source(node, title), *(value or None for value in found)]
                for node, title, found in rows
            ),
        ],
    }
