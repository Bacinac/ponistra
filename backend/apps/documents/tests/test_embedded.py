import io

import pikepdf
import pypdfium2 as pdfium
import pytest
from pikepdf import Array, Dictionary, Name

from apps.access.tests.test_access import create
from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.content.models import DocumentBlob
from apps.documents.models import Node
from apps.exports import embedded
from apps.jobs.tests.handed import refused, saved
from apps.search.tests.test_search import pdf_bytes

pytestmark = pytest.mark.django_db

PLACE = (72, 400, 300, 700)


def printed(*uris: str) -> bytes:
    """A page as the printer leaves it, with a link of each address over the same place."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    links = [
        pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Link,
                Rect=list(PLACE),
                A=Dictionary(S=Name.URI, URI=pikepdf.String(uri)),
            )
        )
        for uri in uris
    ]
    pdf.pages[0].obj.Annots = Array(links)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def showing(api, data: bytes) -> tuple[Node, str]:
    document = Node.objects.get(pk=create(api, "document", "Ponuda"))
    blob = store.put(io.BytesIO(data))
    DocumentBlob.objects.create(document=document, blob=blob)
    return document, blob.sha256


def text_in(data: bytes, place=None) -> str:
    pdf = pdfium.PdfDocument(data)
    try:
        text = pdf[0].get_textpage()
        return text.get_text_bounded(*place) if place else text.get_text_range()
    finally:
        pdf.close()


def addresses(data: bytes) -> list[str]:
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return [str(annot.A.URI) for annot in pdf.pages[0].obj.get("/Annots", [])]


def test_each_marked_place_holds_its_page_as_text_and_other_links_stay(api):
    document, sha256 = showing(api, pdf_bytes("Ugovor o najmu", "Potpisi stranaka"))
    data = embedded.placed(
        document,
        printed(
            f"ponistra-pdf:{sha256}/2",
            "https://example.com/uvjeti",
            f"ponistra-pdf:{'ab' * 32}/1",
            f"ponistra-pdf:{sha256}/9",
        ),
    )
    assert addresses(data) == ["https://example.com/uvjeti"]
    assert "Potpisi stranaka" in text_in(data, PLACE)
    assert "Ugovor" not in text_in(data)


def test_a_print_without_marks_or_shown_pdfs_is_given_as_it_came(api):
    plain = printed("https://example.com/uvjeti")
    document, _ = showing(api, pdf_bytes("Ugovor o najmu"))
    assert embedded.placed(document, plain) == plain
    other = Node.objects.get(pk=create(api, "document", "Narudžba"))
    assert embedded.placed(other, b"not a pdf") == b"not a pdf"


def test_a_marked_pdf_that_cannot_be_read_is_refused_aloud(api, printer):
    document, sha256 = showing(api, b"%PDF-1.7\n" + bytes(64))
    with pytest.raises(embedded.Unreadable):
        embedded.placed(document, printed(f"ponistra-pdf:{sha256}/1"))
    printer.printed(printed(f"ponistra-pdf:{sha256}/1"))
    assert refused(api, "pdf", document=document.pk) == (422, "unreadable_pdf")


def test_the_printed_document_holds_the_pages_its_pdfs_show(api, printer):
    document, sha256 = showing(api, pdf_bytes("Ugovor o najmu"))
    printer.printed(printed(f"ponistra-pdf:{sha256}/1"))
    data = content(saved(api, "pdf", document=document.pk))
    assert "Ugovor o najmu" in text_in(data, PLACE)
    assert addresses(data) == []
