import io
import uuid

import pikepdf
import pytest
from django.test import Client

from apps.blobs.tests.test_blobs import content
from apps.documents.printing import compact
from apps.jobs.tests.handed import refused, saved
from apps.users import sessions
from apps.users.models import User

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def document(api, title):
    fields = {"kind": "document", "title": title, "parent": None}
    return api.post("/api/nodes", fields, content_type="application/json").json()["id"]


def test_an_id_is_written_as_the_frontend_writes_it_in_an_address():
    assert compact(uuid.UUID("0192a7c4-5e1f-7b3a-9c2d-4e5f6a7b8c9d")) == "02y0rpiXRWR1UBYwrsOgMX"
    assert compact(uuid.UUID(int=1)) == "0000000000000000000001"


def run(*widths: int) -> bytes:
    """A run of pages as the printer saves it, a page of each width."""
    pdf = pikepdf.new()
    pdf.docinfo["/Title"] = f"Run {widths[0]}"
    for width in widths:
        pdf.add_blank_page(page_size=(width, 842))
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_the_printer_prints_the_documents_print_page_in_a_session_of_the_readers_own(
    api, printer, monkeypatch
):
    opened = []
    opening = sessions.opened

    def spied(user, lifetime):
        opened.append((user, key := opening(user, lifetime)))
        return key

    monkeypatch.setattr(sessions, "opened", spied)
    printer.printed(PDF)
    pk = document(api, "Ugovor o djelu")
    response = saved(api, "pdf", document=pk)
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == 'attachment; filename="Ugovor o djelu.pdf"'
    assert content(response) == PDF
    [(user, session)] = opened
    assert user == api.user
    assert printer.received == [
        {
            "path": f"/print/{compact(uuid.UUID(pk))}",
            "cookie": "sessionid",
            "session": session,
            "timezone": "Europe/Zagreb",
        }
    ]
    assert not sessions._store().exists(session)


def test_a_long_document_printed_in_runs_is_joined_in_their_order(api, printer):
    printer.printed(run(500, 501), run(502), run(503, 504, 505))
    response = saved(api, "pdf", document=document(api, "Praćenje"))
    with pikepdf.open(io.BytesIO(content(response))) as joined:
        assert [int(page.mediabox[2]) for page in joined.pages] == list(range(500, 506))
        assert joined.docinfo["/Title"] == "Run 500"


@pytest.mark.parametrize(
    "runs",
    [{}, {"X-Runs": ""}, {"X-Runs": "12"}, {"X-Runs": "0 2"}, {"X-Runs": "1, 2"}, {"X-Runs": "²"}],
)
def test_runs_that_do_not_add_up_to_the_pdf_are_refused(api, printer, runs, caplog):
    data = run(500)
    printer.replies.append((200, data, runs))
    assert refused(api, "pdf", document=document(api, "Ponuda")) == (503, "printer_unavailable")
    assert "the printer sent runs" in caplog.text


def test_a_run_that_is_no_pdf_is_refused(api, printer, caplog):
    printer.printed(run(500), b"%PDF-1.7\n" + bytes(64))
    assert refused(api, "pdf", document=document(api, "Ponuda")) == (503, "printer_unavailable")
    assert "a run that is no PDF" in caplog.text


def test_a_printer_that_fails_or_is_gone_is_reported_and_strangers_learn_nothing(
    api, printer, settings, caplog
):
    pk = document(api, "Ponuda")
    printer.replies.append((500, b"Chromium ran out of the printer's memory: Target crashed"))
    assert refused(api, "pdf", document=pk) == (503, "printer_unavailable")
    assert "500: Chromium ran out of the printer's memory" in caplog.text
    settings.PRINTER_URL = "http://127.0.0.1:9"
    assert refused(api, "pdf", document=pk) == (503, "printer_unavailable")
    stranger = Client()
    stranger.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert refused(stranger, "pdf", document=pk) == (404, "not_found")
    assert len(printer.received) == 1
