"""What a document's content takes as stored and what it holds, measured whenever one of its
tabs is read for the element table."""

from django.db.models import BigIntegerField, Func, Sum
from pycrdt import Doc

from apps.collab.models import Update
from apps.documents.models import Node

from . import slides
from .models import DocumentBlob, Element, GridRow

# Beside a sheet's tables, a chart drawn from them and the notes still leave it a sheet.
ASIDE = ("chart", "footnote", "endnote")


class Stored(Func):
    """The bytes a value takes as Postgres keeps it, compressed where it is."""

    function = "pg_column_size"
    output_field = BigIntegerField()


def _sum(rows, value) -> int:
    return rows.aggregate(size=Sum(value))["size"] or 0


def holds(document: Node, own: Doc) -> str:
    """Slides where the document keeps slide layouts of its own, a table where its first tab
    holds tables alone, text otherwise."""
    if not slides.template_of(own).built_in:
        return Node.Holds.SLIDES
    first = document.tabs.filter(parent=None).order_by("position").first()
    found = Element.objects.filter(tab=first, row="").exclude(type__in=ASIDE)
    types = set(found.values_list("type", flat=True).distinct())
    return Node.Holds.TABLE if types == {"table"} else Node.Holds.TEXT


def measure(document: Node, own: Doc) -> None:
    size = (
        _sum(Update.objects.filter(document=document), Stored("data"))
        + _sum(GridRow.objects.filter(grid__document=document), Stored("cells") + Stored("values"))
        + _sum(DocumentBlob.objects.filter(document=document), "blob__size")
    )
    Node.objects.filter(pk=document.pk).update(content_size=size, holds=holds(document, own))
