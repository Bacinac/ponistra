import io
import zipfile

import pytest

from apps.access.models import Access
from apps.access.tests.test_access import JSON, create, person, share
from apps.blobs.tests.test_blobs import content
from apps.documents.models import Node
from apps.documents.views import file_name
from apps.exports.zipped import Zipped
from apps.search.tests.test_search import pdf_bytes, upload_file

pytestmark = pytest.mark.django_db


def zipped(client, *nodes) -> tuple[str, zipfile.ZipFile]:
    response = client.get("/api/nodes/zip", {"node": list(nodes)})
    assert response.status_code == 200, response
    assert response["Content-Type"] == "application/zip"
    return response["Content-Disposition"], zipfile.ZipFile(io.BytesIO(content(response)))


def test_a_folder_is_zipped_with_all_it_holds_each_document_in_its_office_format(api):
    folder = create(api, "folder", "Ponude")
    inner = create(api, "folder", "Arhiva", folder)
    create(api, "document", "Ugovor", folder)
    upload_file(api, "Ponuda", pdf_bytes("Ponuda"), folder)
    one = file_name(Node.objects.get(pk=upload_file(api, "bilješka", b"tekst", inner)))
    upload_file(api, "Bilješka", b"drugi", inner)
    extension = one.rpartition(".")[2]
    link = {"kind": "link", "title": "Web", "href": "https://example.com/", "parent": folder}
    assert api.post("/api/nodes", link, content_type=JSON).status_code == 201

    disposition, archive = zipped(api, folder)

    assert disposition == 'attachment; filename="Ponude.zip"'
    names = archive.namelist()
    assert set(names) == {
        "Ponude/",
        "Ponude/Arhiva/",
        f"Ponude/Arhiva/{one}",
        f"Ponude/Arhiva/Bilješka (2).{extension}",
        "Ponude/Ugovor.docx",
        "Ponude/Ponuda.pdf",
        "Ponude/Web.url",
    }
    assert names.index("Ponude/Arhiva/") < names.index(f"Ponude/Arhiva/{one}")
    assert archive.read(f"Ponude/Arhiva/{one}") == b"tekst"
    assert archive.read("Ponude/Ponuda.pdf").startswith(b"%PDF")
    assert archive.read("Ponude/Web.url") == b"[InternetShortcut]\r\nURL=https://example.com/\r\n"
    assert zipfile.ZipFile(io.BytesIO(archive.read("Ponude/Ugovor.docx"))).testzip() is None
    assert archive.testzip() is None
    taken = Access.objects.filter(kind=Access.Kind.DOWNLOADED)
    formats = sorted(taken.values_list("detail__format", flat=True))
    assert formats == sorted(["docx", "pdf", extension, extension])


def test_rows_chosen_together_are_named_after_their_folder(api):
    folder = create(api, "folder", "Ponude")
    one = upload_file(api, "a", pdf_bytes("a"), folder)
    two = upload_file(api, "b", pdf_bytes("b"), folder)
    disposition, archive = zipped(api, one, two)
    assert disposition == 'attachment; filename="Ponude.zip"'
    assert sorted(archive.namelist()) == ["a.pdf", "b.pdf"]


def test_a_folder_that_keeps_its_files_in_the_browser_is_not_zipped(api):
    ana = person("ana@example.com")
    folder = create(api, "folder", "Ponude")
    kept = create(api, "folder", "Tajno", folder)
    upload_file(api, "a", pdf_bytes("a"), kept)
    Node.objects.filter(pk=kept).update(confined=True)
    assert share(api, folder, "read", id=ana.user.pk).status_code in (200, 201)

    assert ana.get("/api/nodes/zip", {"node": folder}).status_code == 403
    assert not Access.objects.filter(kind=Access.Kind.DOWNLOADED).exists()
    assert zipped(api, folder)[1].namelist()[-1] == "Ponude/Tajno/a.pdf"


def test_what_is_not_there_or_not_reached_is_refused(api):
    ana = person("ana@example.com")
    folder = create(api, "folder", "Ponude")
    assert ana.get("/api/nodes/zip", {"node": folder}).status_code == 404
    assert api.get("/api/nodes/zip").status_code == 400
    assert api.get("/api/nodes/zip", {"node": "x"}).status_code == 400


def test_names_are_safe_on_every_system_and_none_repeats():
    archive = Zipped()
    assert archive.named("", 'a/b:c*?"<>|.') == "a_b_c______"
    assert archive.named("", "A_B_C______") == "A_B_C______ (2)"
    assert archive.named("x", "..") == "x/_"
    assert archive.named("", ".bashrc") == ".bashrc"
    assert archive.named("", ".BASHRC") == ".BASHRC (2)"
