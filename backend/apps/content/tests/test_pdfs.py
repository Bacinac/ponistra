import hashlib
import io

import pikepdf
import pytest
from django.utils import timezone

from apps.access.tests.test_access import JSON, create, person, share
from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.content.models import DocumentBlob
from apps.content.tests.test_images import PNG
from apps.documents.models import Node
from apps.exports.tests.test_noted import encrypted
from apps.search.models import BlobText, PdfOcr
from apps.search.tests.test_search import extract_all, pdf_bytes, upload_file

pytestmark = pytest.mark.django_db

PDF = pdf_bytes("Ugovor o najmu", "Potpisi")
SHA = hashlib.sha256(PDF).hexdigest()


@pytest.fixture
def ana():
    return person("ana@example.com")


def put(client, document, data=PDF, content_type="application/pdf"):
    return client.post(f"/api/nodes/{document}/pdfs", data, content_type=content_type)


def link(client, document, **data):
    return client.post(f"/api/nodes/{document}/pdfs", data, content_type=JSON)


def saved(data: bytes, **options) -> bytes:
    out = io.BytesIO()
    with pikepdf.open(io.BytesIO(data)) as pdf:
        pdf.save(out, **options)
    return out.getvalue()


def test_a_pdf_from_the_computer_goes_into_its_document_only(api):
    document = create(api, "document", "Ponuda")
    response = put(api, document)
    assert (response.status_code, response.json()) == (201, {"blob": SHA})
    assert DocumentBlob.objects.filter(document=document, blob=SHA).exists()
    assert not Node.objects.filter(kind=Node.Kind.FILE).exists()

    served = api.get(f"/api/pdfs/{SHA}")
    assert served.status_code == 200
    assert served["Content-Type"] == "application/pdf"
    assert content(served) == PDF


def test_a_file_of_the_tree_goes_in_as_its_text_was_read(api):
    file = upload_file(api, "Najam", PDF)
    document = create(api, "document", "Ponuda")
    assert link(api, document, file=file).json() == {"blob": SHA}

    read = store.put(io.BytesIO(pdf_bytes("Ugovor o najmu", "Procitani potpisi")))
    PdfOcr.objects.create(
        blob_id=SHA, state=PdfOcr.State.DONE, readable=read, queued_at=timezone.now()
    )
    other = create(api, "document", "Narudžba")
    assert link(api, other, file=file).json() == {"blob": read.sha256}
    assert Node.objects.filter(kind=Node.Kind.FILE).count() == 1


def test_a_pdf_another_readable_document_shows_goes_in_by_its_hash(api, ana):
    source = create(api, "document", "Ponuda")
    put(api, source)
    target = create(api, "document", "Narudžba")
    assert link(api, target, blob=SHA).status_code == 201

    own = create(ana, "document", "Bilješke")
    assert link(ana, own, blob=SHA).status_code == 404
    share(api, source, "read", id=ana.user.pk)
    assert link(ana, own, blob=SHA).status_code == 201


@pytest.mark.parametrize(
    ("data", "content_type", "status", "error"),
    [
        (PNG, "image/png", 415, "not_a_pdf"),
        (encrypted("vlasnik", "tajna"), "application/pdf", 409, "locked"),
        (
            saved(
                PDF,
                encryption=pikepdf.Encryption(
                    owner="vlasnik", user="", allow=pikepdf.Permissions(modify_assembly=False)
                ),
            ),
            "application/pdf",
            409,
            "assembly_forbidden",
        ),
        (b"%PDF-1.7\n" + bytes(64), "application/pdf", 422, "unreadable"),
    ],
)
def test_a_pdf_whose_pages_cannot_go_into_another_is_refused(
    api, data, content_type, status, error
):
    document = create(api, "document", "Ponuda")
    response = put(api, document, data, content_type)
    assert (response.status_code, response.json()) == (status, {"error": error})
    assert not DocumentBlob.objects.exists()


def test_what_is_not_a_readable_file_is_refused(api, ana):
    document = create(api, "document", "Ponuda")
    other = create(api, "document", "Narudžba")
    assert link(api, document, file=other).json() == {"error": "not_a_file"}
    assert link(api, document).json() == {"error": "no_pdf"}
    file = upload_file(api, "Najam", PDF)
    own = create(ana, "document", "Bilješke")
    assert link(ana, own, file=file).status_code == 404
    assert link(ana, own, blob=SHA).status_code == 404


def test_adding_a_pdf_needs_the_right_to_edit(api, ana):
    document = create(api, "document", "Ponuda")
    share(api, document, "read", id=ana.user.pk)
    assert put(ana, document).status_code == 403


def test_a_pdf_is_served_to_whoever_can_read_a_document_showing_it(api, ana):
    document = create(api, "document", "Ponuda")
    put(api, document)
    for path in (f"/api/pdfs/{SHA}", f"/api/pdfs/{SHA}/pages"):
        assert ana.get(path).status_code == 404
    share(api, document, "read", id=ana.user.pk)
    assert ana.get(f"/api/pdfs/{SHA}").status_code == 200

    Node.objects.filter(pk=document).update(trashed_at=timezone.now())
    assert ana.get(f"/api/pdfs/{SHA}").status_code == 404


def test_an_image_is_not_served_as_a_pdf(api):
    document = create(api, "document", "Ponuda")
    sha256 = api.post(f"/api/nodes/{document}/images", PNG, content_type="image/png").json()
    assert api.get(f"/api/pdfs/{sha256['blob']}").status_code == 404


def test_the_pages_are_measured_as_they_show_turned(api):
    turned = io.BytesIO()
    with pikepdf.open(io.BytesIO(PDF)) as pdf:
        pdf.pages[1].rotate(90, relative=True)
        pdf.save(turned)
    document = create(api, "document", "Ponuda")
    sha256 = put(api, document, turned.getvalue()).json()["blob"]
    assert api.get(f"/api/pdfs/{sha256}/pages").json() == {"pages": [[595, 842], [842, 595]]}


def test_the_text_of_a_shown_pdf_is_extracted_but_its_pages_are_not_read(api):
    document = create(api, "document", "Ponuda")
    sha256 = put(api, document, pdf_bytes("Ugovor", "")).json()["blob"]
    extract_all()
    assert BlobText.objects.get(blob=sha256).page_count == 2
    assert not PdfOcr.objects.exists()
