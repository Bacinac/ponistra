import hashlib
import io
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from django.utils import timezone
from PIL import Image

from apps.access.tests.test_access import JSON, create, person, share
from apps.blobs import store
from apps.blobs.models import Blob
from apps.blobs.tests.test_blobs import content
from apps.blobs.tests.test_edits import kept_mark, red, white
from apps.content.models import DocumentBlob
from apps.core import fetch
from apps.documents.models import Node

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
SHA = hashlib.sha256(PNG).hexdigest()


@pytest.fixture
def ana():
    return person("ana@example.com")


def put(client, document, data=PNG, content_type="image/png"):
    return client.post(f"/api/nodes/{document}/images", data, content_type=content_type)


def link(client, document, **data):
    return client.post(f"/api/nodes/{document}/images", data, content_type=JSON)


def test_an_uploaded_image_is_linked_to_its_document_and_served_sandboxed(api):
    document = create(api, "document", "Ponuda")
    response = put(api, document)
    assert response.status_code == 201
    assert response.json() == {"blob": SHA, "media_type": "image/png"}
    assert DocumentBlob.objects.filter(document=document, blob=SHA).exists()

    served = api.get(f"/api/images/{SHA}")
    assert served.status_code == 200
    assert served["Content-Type"] == "image/png"
    assert served["Content-Security-Policy"] == "sandbox"
    assert content(served) == PNG


def test_an_image_file_of_the_folders_goes_into_a_document(api, upload):
    document = create(api, "document", "Ponuda")
    sha256 = upload(PNG)["sha256"]
    fields = {"kind": "file", "title": "Plan", "blob": sha256}
    picture = api.post("/api/nodes", fields, content_type=JSON).json()["id"]
    assert link(api, document, file=picture).json() == {"blob": SHA, "media_type": "image/png"}
    assert DocumentBlob.objects.filter(document=document, blob=SHA).exists()
    pdf = upload(b"%PDF-1.7\n%%EOF\n")["sha256"]
    fields = {"kind": "file", "title": "Cjenik", "blob": pdf}
    other = api.post("/api/nodes", fields, content_type=JSON).json()["id"]
    refused = link(api, document, file=other)
    assert (refused.status_code, refused.json()) == (415, {"error": "not_an_image"})
    assert link(api, document, file=document).json() == {"error": "not_a_file"}


def test_only_images_are_taken(api):
    document = create(api, "document", "Ponuda")
    response = put(api, document, b"%PDF-1.7\n", "application/pdf")
    assert response.status_code == 415
    assert response.json() == {"error": "not_an_image"}
    assert not DocumentBlob.objects.exists()


def test_an_image_the_document_shows_is_edited_into_one_of_its_own(api):
    document = create(api, "document", "Ponuda")
    original = store.put(io.BytesIO(white(20, 10)))
    DocumentBlob.objects.create(document_id=document, blob=original)
    rectangle = kept_mark("rectangle", [2, 2, 8, 8], color="red", width=2)
    response = link(api, document, blob=original.sha256, edits={"turn": 90}, marks={"r": rectangle})
    assert response.status_code == 201
    drawn = response.json()["blob"]
    assert drawn != original.sha256 and response.json()["media_type"] == "image/png"
    assert set(DocumentBlob.objects.filter(document=document).values_list("blob", flat=True)) == {
        original.sha256,
        drawn,
    }
    with Image.open(store.path_of(drawn)) as image:
        assert image.size == (10, 20)
        assert red(image.convert("RGB").getpixel((8, 2)))

    unchanged = link(api, document, blob=original.sha256, edits={}, marks={})
    assert unchanged.json()["blob"] == original.sha256
    for refused in ({"edits": {"turn": 45}}, {"edits": []}, {"marks": {"r": {"kind": "arrow"}}}):
        answer = link(api, document, blob=original.sha256, **refused)
        assert (answer.status_code, answer.json()["error"]) == (400, "invalid_edits")
    gif = store.put(io.BytesIO(b"GIF89a" + bytes(32)))
    DocumentBlob.objects.create(document_id=document, blob=gif)
    answer = link(api, document, blob=gif.sha256, edits={"turn": 90})
    assert (answer.status_code, answer.json()["error"]) == (415, "not_editable")


def test_adding_an_image_needs_the_right_to_edit(api, ana):
    document = create(api, "document", "Ponuda")
    share(api, document, "read", id=ana.user.pk)
    assert put(ana, document).status_code == 403


def test_an_image_is_served_to_whoever_can_read_a_document_showing_it(api, ana):
    document = create(api, "document", "Ponuda")
    put(api, document)
    assert ana.get(f"/api/images/{SHA}").status_code == 404

    share(api, document, "read", id=ana.user.pk)
    assert ana.get(f"/api/images/{SHA}").status_code == 200

    Node.objects.filter(pk=document).update(trashed_at=timezone.now())
    assert ana.get(f"/api/images/{SHA}").status_code == 404


def test_an_image_another_readable_document_shows_is_linked_by_its_hash(api, ana):
    source = create(api, "document", "Ponuda")
    put(api, source)
    target = create(api, "document", "Narudžba")
    assert link(api, target, blob=SHA).status_code == 201
    assert DocumentBlob.objects.filter(document=target, blob=SHA).exists()

    own = create(ana, "document", "Bilješke")
    assert link(ana, own, blob=SHA).status_code == 404
    assert link(ana, own, blob="nonsense").status_code == 404


def test_a_linked_image_outlives_collection_until_its_document_goes(api):
    document = create(api, "document", "Ponuda")
    put(api, document)
    Blob.objects.update(uploaded_at=timezone.now() - timedelta(days=1))

    store.collect()
    assert Blob.objects.filter(pk=SHA).exists()

    Node.objects.filter(pk=document).delete()
    store.collect()
    assert not Blob.objects.filter(pk=SHA).exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/slika.png",
        "http://localhost/slika.png",
        "http://[::1]/slika.png",
        "http://10.0.0.7/slika.png",
        "http://192.168.1.12/slika.png",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/slika.png",
        "file:///etc/passwd",
        "http://example.com:99999/slika.png",
        "slika.png",
    ],
)
def test_an_address_that_is_not_public_is_not_fetched(api, url):
    document = create(api, "document", "Ponuda")
    response = link(api, document, url=url)
    assert response.status_code == 422
    assert response.json() == {"error": "unreachable"}


class Images(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/slika")
        elif self.path == "/inside":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/slika")
        elif self.path == "/slika":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(PNG)))
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
        self.end_headers()
        if self.path == "/slika":
            self.wfile.write(PNG)

    def log_message(self, *args):
        pass


@pytest.fixture
def host(monkeypatch):
    """A web host named slike.example that is only pretended public."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Images)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    vetted = fetch.public_address
    monkeypatch.setattr(
        fetch,
        "public_address",
        lambda name, port: "127.0.0.1" if name == "slike.example" else vetted(name, port),
    )
    yield f"http://slike.example:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_an_image_on_the_web_is_fetched_by_its_address_through_redirects(api, host):
    document = create(api, "document", "Ponuda")
    response = link(api, document, url=f"{host}/moved")
    assert response.status_code == 201
    assert response.json() == {"blob": SHA, "media_type": "image/png"}
    assert DocumentBlob.objects.filter(document=document, blob=SHA).exists()


def test_a_redirect_is_vetted_like_the_address_itself(api, host):
    document = create(api, "document", "Ponuda")
    assert link(api, document, url=f"{host}/inside").status_code == 422
    assert link(api, document, url=f"{host}/missing").status_code == 422
    assert not Blob.objects.exists()
