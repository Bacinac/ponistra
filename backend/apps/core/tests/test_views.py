import json

import pytest
from django.test import Client

from apps.core import views
from apps.core.views import shipped


@pytest.fixture(autouse=True)
def nothing_reported_yet():
    views._reported.clear()


@pytest.mark.django_db
def test_ping_reaches_the_database(client):
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_version_reads_the_revision_file(client, settings, tmp_path):
    revision = tmp_path / "revision.json"
    revision.write_text(
        json.dumps({"version": "0.1.7", "sha": "abc12345", "committed_at": "2026-11-10"})
    )
    settings.REVISION_FILE = revision
    assert client.get("/api/version").json() == {"version": "0.1.7"}


def test_shipped_names_the_release_and_nothing_without_a_revision_file(settings, tmp_path):
    revision = tmp_path / "revision.json"
    settings.REVISION_FILE = revision
    assert shipped() == ""
    revision.write_text(json.dumps({"version": "0.1.7"}))
    assert shipped() == "0.1.7"


@pytest.mark.django_db
def test_a_crashed_page_is_logged_with_its_stack(api, settings, tmp_path, caplog):
    revision = tmp_path / "revision.json"
    revision.write_text(json.dumps({"version": "0.1.7", "sha": "abc12345"}))
    settings.REVISION_FILE = revision
    response = api.post(
        "/api/crashes",
        {
            "path": "/mail",
            "message": "Cannot read properties of undefined (reading 'reduce')",
            "stack": "TypeError\n    at useWaiting (index-abc.js:1:2345)" + "x" * 20000,
            "components": "\n    at Shell",
        },
        content_type="application/json",
    )
    assert response.status_code == 204
    [record] = [each for each in caplog.records if each.name == "apps.core.views"]
    assert record.levelname == "ERROR"
    text = record.getMessage()
    assert f"page crashed at /mail for user {api.user.pk}" in text
    assert "(server 0.1.7): Cannot read properties of undefined (reading 'reduce')" in text
    assert "index-abc.js:1:2345" in text
    assert "components:\n    at Shell" in text
    assert len(text) < 20000


@pytest.mark.django_db
def test_a_guest_page_reports_its_crash_too(client, caplog):
    response = client.post(
        "/api/crashes", {"path": "/meet/x", "message": "boom"}, content_type="application/json"
    )
    assert response.status_code == 204
    assert "for user guest" in caplog.text


def test_version_without_revision_file_fails_loud(client, settings, tmp_path):
    settings.REVISION_FILE = tmp_path / "missing.json"
    response = client.get("/api/version")
    assert response.status_code == 503
    assert "install-hooks.sh" in response.json()["error"]


@pytest.mark.django_db
def test_a_crash_report_begins_no_line_of_the_log_but_its_own(client, caplog):
    client.post(
        "/api/crashes",
        {
            "path": "/x\nFAKE ERROR page crashed at /admin for user 1",
            "message": "boom\r\nFAKE",
            "stack": "TypeError: boom\n    at a (index.js:1:2)\u2028FAKE\n",
            "queries": "12 tree,favourites success {children}",
        },
        content_type="application/json",
        HTTP_USER_AGENT="Edge\nFAKE",
    )
    [text] = [each.getMessage() for each in caplog.records if each.name == "apps.core.views"]
    first, *rest = text.splitlines()
    assert first.startswith("page crashed at /x FAKE ERROR page crashed at /admin for user 1 for")
    assert "on Edge FAKE" in first and first.endswith(": boom FAKE")
    assert all(each.startswith("    ") or each.endswith(":") for each in rest)
    assert "    at a (index.js:1:2)" in rest
    assert "queries:" in rest and "    12 tree,favourites success {children}" in rest


@pytest.mark.django_db
def test_crash_reports_are_counted_by_user_and_for_all_guests_together(api):
    client = Client()
    report = {"path": "/", "message": "boom"}
    for _ in range(views.CRASHES_A_USER[0]):
        assert api.post("/api/crashes", report, content_type="application/json").status_code == 204
    refused = api.post("/api/crashes", report, content_type="application/json")
    assert refused.status_code == 429
    assert refused.json() == {"error": "too_many_crashes"}
    for _ in range(views.CRASHES_OF_GUESTS[0]):
        assert (
            client.post("/api/crashes", report, content_type="application/json").status_code == 204
        )
    assert client.post("/api/crashes", report, content_type="application/json").status_code == 429


def test_every_answer_names_the_request_it_answers(client):
    response = client.get("/api/version?a=%C5%A1")
    assert response["Answered-For"] == "/api/version?a=%C5%A1"


@pytest.mark.django_db
def test_a_crossed_answer_is_logged(api, caplog):
    response = api.post(
        "/api/crossed",
        {"asked": "/api/nodes/n", "answered": "/api/nodes/favourites\nforged line"},
        content_type="application/json",
    )
    assert response.status_code == 204
    [record] = [each for each in caplog.records if each.name == "apps.core.views"]
    assert record.getMessage().endswith(
        "asked /api/nodes/n, answered /api/nodes/favourites forged line"
    )
