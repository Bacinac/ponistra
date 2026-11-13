import hashlib
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.blobs import store
from apps.blobs.models import Blob
from apps.blobs.tests.test_blobs import content
from apps.documents.models import Node
from apps.jobs.tests.handed import done
from apps.search import ocr
from apps.search.models import PdfOcr
from apps.search.tests.test_search import JSON, extract_all, pdf_bytes, search, upload_file

pytestmark = pytest.mark.django_db(transaction=True)

recognise = async_to_sync(ocr.recognise_next)
SCANNED = pdf_bytes("Naslov", "")
READ = pdf_bytes("Naslov", "Procitano rukom")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def described(api, file: str) -> dict:
    return api.get(f"/api/nodes/{file}").json()["pdf"]


def scanned(api) -> str:
    file = upload_file(api, "Sken", SCANNED)
    extract_all()
    return file


def test_pages_without_text_are_read_and_the_file_shown_with_what_was_read(api, service):
    file = upload_file(api, "Sken", SCANNED)
    assert described(api, file)["ocr"] == "checking"
    extract_all()
    assert described(api, file) == {
        "served": sha(SCANNED),
        "recognised": False,
        "ocr": "waiting",
        "reason": None,
        "language": None,
    }
    service.append((200, READ))
    assert recognise()
    assert not recognise()

    assert described(api, file) == {
        "served": sha(READ),
        "recognised": True,
        "ocr": "done",
        "reason": None,
        "language": "hr",
    }
    [result] = search(api, "procitano")
    assert (result["id"], result["page"]) == (file, 2)
    assert content(api.get(f"/api/nodes/{file}/file")) == READ
    assert content(api.get(f"/api/nodes/{file}/file", {"v": sha(READ)})) == READ
    assert content(api.get(f"/api/nodes/{file}/file", {"v": sha(SCANNED)})) == SCANNED
    assert api.get(f"/api/nodes/{file}/file", {"v": "0" * 64}).status_code == 404
    assert content(api.get(f"/api/nodes/{file}/original")) == SCANNED
    assert content(api.get(f"/api/nodes/{file}/noted")) == READ


def test_a_file_with_text_on_every_page_is_not_read(api):
    file = upload_file(
        api, "Tekst", pdf_bytes("Sehr geehrte Damen und Herren", "wir bieten Ihnen die Wartung an")
    )
    assert described(api, file)["language"] is None
    extract_all()
    assert not PdfOcr.objects.exists()
    assert (described(api, file)["ocr"], described(api, file)["language"]) == (None, "de")


def test_a_reading_that_finds_no_new_text_leaves_the_file_as_it_came(api, service):
    file = scanned(api)
    service.append((200, pdf_bytes("Naslov", " ")))
    assert recognise()
    assert described(api, file) == {
        "served": sha(SCANNED),
        "recognised": False,
        "ocr": "done",
        "reason": None,
        "language": None,
    }
    assert list(Blob.objects.values_list("pk", flat=True)) == [sha(SCANNED)]


def test_a_file_that_reading_would_break_keeps_the_reason(api, service):
    file = scanned(api)
    service.append((409, b"signed"))
    assert recognise()
    assert described(api, file)["ocr"] == "refused"
    assert described(api, file)["reason"] == "signed"
    response = api.post(f"/api/nodes/{file}/ocr")
    assert (response.status_code, response.json()["error"]) == (409, "not_failed")


def test_a_failed_reading_is_shown_and_tried_again_on_request(api, service, caplog):
    file = scanned(api)
    service.append((422, b"Tesseract stopped"))
    assert recognise()
    assert described(api, file)["ocr"] == "failed"
    assert "Tesseract stopped" in caplog.text

    response = api.post(f"/api/nodes/{file}/ocr")
    assert response.status_code == 200
    assert response.json()["ocr"] == "waiting"
    service.append((200, READ))
    assert recognise()
    assert described(api, file)["ocr"] == "done"


def test_a_service_that_does_not_answer_leaves_the_file_waiting(api, settings):
    scanned(api)
    settings.OCR_URL = "http://127.0.0.1:9"
    with pytest.raises(ocr.Unavailable):
        recognise()
    waiting = PdfOcr.objects.get()
    assert (waiting.state, waiting.started_at) == (PdfOcr.State.WAITING, None)


def test_a_claim_left_by_a_process_that_died_is_taken_over_after_the_lease(api):
    scanned(api)
    claimed = ocr.claim()
    assert claimed is not None
    assert ocr.claim() is None
    PdfOcr.objects.update(started_at=timezone.now() - ocr.LEASE - timedelta(seconds=1))
    assert ocr.claim() is not None
    ocr.finish(claimed, PdfOcr.State.FAILED, "late")
    assert PdfOcr.objects.get().state == PdfOcr.State.WAITING


def test_a_file_no_folder_holds_waits_uncounted_until_it_is_back(api):
    file = scanned(api)
    blob = Node.objects.get(pk=file).blob_id
    other = Node.objects.get(pk=upload_file(api, "Tekst", pdf_bytes("Jedan", "Dva"))).blob_id
    Node.objects.filter(pk=file).update(blob=other)
    assert ocr.waiting().count() == 0
    assert ocr.claim() is None
    Node.objects.filter(pk=file).update(blob=blob)
    assert ocr.waiting().count() == 1
    assert ocr.claim() is not None


def test_the_bytes_read_go_with_the_file(api, service, settings):
    file = scanned(api)
    service.append((200, READ))
    recognise()
    settings.BLOB_GRACE = timedelta(0)
    store.collect()
    assert Blob.objects.count() == 2

    api.post("/api/nodes/trash", {"nodes": [file]}, content_type=JSON)
    assert api.post("/api/trash/purge", {"nodes": [file]}, JSON).status_code == 204
    store.collect()
    assert list(Blob.objects.values_list("pk", flat=True)) == [sha(READ)]
    assert not PdfOcr.objects.exists()
    store.collect()
    assert not Blob.objects.exists()


def test_pages_taken_from_a_file_carry_what_was_read_in_them(api, service):
    file = scanned(api)
    service.append((200, READ))
    recognise()
    done(api, "compose", title="Izdvojeno", beside=file, pages=[{"file": file, "page": 2}])
    extract_all()
    assert {result["title"] for result in search(api, "procitano")} == {"Sken", "Izdvojeno"}
