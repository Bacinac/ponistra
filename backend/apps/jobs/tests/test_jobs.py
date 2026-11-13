from datetime import timedelta

import pytest
from django.utils import timezone

from apps.access.tests.test_access import JSON, create, person
from apps.blobs.models import Blob
from apps.blobs.tests.test_blobs import content
from apps.documents.models import Node
from apps.jobs import work
from apps.jobs.models import Job

from .handed import refused, saved

pytestmark = pytest.mark.django_db


def handed(client, kind: str, **data) -> dict:
    response = client.post("/api/jobs", {"kind": kind, **data}, content_type=JSON)
    assert response.status_code == 202, response.json()
    return response.json()


def seen(client, job: dict) -> dict:
    return client.get(f"/api/jobs/{job['id']}").json()


def test_a_job_waits_until_the_queue_does_it_and_its_file_is_its_owners_alone(api):
    document = create(api, "document", "Ugovor")
    job = handed(api, "docx", document=document)
    assert (job["state"], job["file"], job["cancellable"]) == ("waiting", False, True)
    assert api.get(f"/api/jobs/{job['id']}/file").status_code == 404
    work.run(work.claim())
    found = seen(api, job)
    assert (found["state"], found["file"], found["cancellable"]) == ("done", True, False)
    response = api.get(f"/api/jobs/{job['id']}/file?download=1")
    assert response["Content-Disposition"] == 'attachment; filename="Ugovor.docx"'
    assert content(response)[:2] == b"PK"
    stranger = person("ana@example.com")
    assert stranger.get(f"/api/jobs/{job['id']}").status_code == 404
    assert stranger.get(f"/api/jobs/{job['id']}/file").status_code == 404
    assert stranger.delete(f"/api/jobs/{job['id']}").status_code == 404


def test_what_a_request_would_refuse_is_refused_as_the_job_is_handed_over(api):
    document = create(api, "document", "Ugovor")
    assert refused(api, "print") == (400, "unknown_job")
    assert refused(api, "docm", document=document) == (404, "no_macros")
    assert refused(person("ana@example.com"), "docx", document=document) == (404, "not_found")
    assert not Job.objects.exists()


def test_what_changed_while_the_job_waited_is_checked_again_as_it_runs(api):
    document = create(api, "document", "Ugovor")
    job = handed(api, "docx", document=document)
    Node.objects.filter(pk=document).update(trashed_at=timezone.now())
    work.run(work.claim())
    found = seen(api, job)
    assert (found["state"], found["status"], found["error"]) == ("failed", 404, "not_found")


def test_a_job_that_fails_unexpectedly_says_so(api, monkeypatch, caplog):
    def broken(document, site):
        raise RuntimeError("the pictures are gone")

    monkeypatch.setattr("apps.exports.docx.word_file", broken)
    document = create(api, "document", "Ugovor")
    job = handed(api, "docx", document=document)
    work.run(work.claim())
    found = seen(api, job)
    assert (found["state"], found["status"], found["error"]) == ("failed", 500, "unexpected")
    assert "the pictures are gone" in caplog.text


def test_a_waiting_job_is_given_up_and_a_running_one_where_it_saves_a_file(api):
    document = create(api, "document", "Ugovor")
    waiting = handed(api, "docx", document=document)
    assert api.delete(f"/api/jobs/{waiting['id']}").status_code == 204
    assert seen(api, waiting)["state"] == "cancelled"
    assert work.claim() is None

    running = handed(api, "docx", document=document)
    claimed = work.claim()
    assert api.delete(f"/api/jobs/{running['id']}").status_code == 204
    work.run(claimed)
    assert (seen(api, running)["state"], seen(api, running)["file"]) == ("cancelled", False)

    copying = handed(api, "copy", document=document, title="Kopija")
    claimed = work.claim()
    assert seen(api, copying)["cancellable"] is False
    response = api.delete(f"/api/jobs/{copying['id']}")
    assert (response.status_code, response.json()) == (409, {"error": "not_cancellable"})
    work.run(claimed)
    assert seen(api, copying)["state"] == "done"


def test_a_job_a_restart_cut_off_runs_again_once(api):
    document = create(api, "document", "Ugovor")
    job = handed(api, "docx", document=document)
    work.claim()
    work.interrupted()
    assert seen(api, job)["state"] == "waiting"
    work.claim()
    work.interrupted()
    found = seen(api, job)
    assert (found["state"], found["status"], found["error"]) == ("failed", 500, "interrupted")


def test_ended_jobs_are_kept_for_a_while_and_their_files_then_go(api, settings):
    document = create(api, "document", "Ugovor")
    job = saved(api, "docx", document=document)
    [made] = Job.objects.values_list("file", flat=True)
    assert content(job)[:2] == b"PK"
    work.swept()
    assert Job.objects.exists()
    long_ago = timezone.now() - settings.JOBS_KEPT - timedelta(minutes=1)
    Job.objects.update(finished_at=long_ago)
    Blob.objects.filter(pk=made).update(uploaded_at=long_ago)
    work.swept()
    assert not Job.objects.exists()
    assert not Blob.objects.filter(pk=made).exists()
