import io
import shutil

import numpy as np
import pikepdf
import pytest
from PIL import Image, ImageDraw

from apps.blobs.tests.uploads import uploaded
from apps.documents.models import Node
from apps.imports import scanned
from apps.jobs.tests.handed import done, refused
from apps.search.tests.test_search import pdf_bytes

pytestmark = pytest.mark.django_db

DRAWN = ((0.2, 0.15), (0.78, 0.22), (0.72, 0.9), (0.16, 0.82))
JSON = "application/json"


def photo(size=(1200, 1600), corners=DRAWN, background=60) -> bytes:
    """A sheet of paper, shaded from left to right and lined with writing, lying askew on a desk."""
    image = Image.new("RGB", size, (background, background - 10, background - 20))
    quad = [(x * size[0], y * size[1]) for x, y in corners]
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(quad, fill=255)
    shade = np.linspace(170, 245, size[0], dtype=np.uint8)
    paper = Image.fromarray(np.repeat(np.tile(shade, (size[1], 1))[..., None], 3, axis=2))
    image.paste(paper, mask=mask)
    draw = ImageDraw.Draw(image)
    for line in range(8):
        y = 0.3 + line * 0.06
        draw.line([(0.3 * size[0], y * size[1]), (0.62 * size[0], (y + 0.01) * size[1])], 0, 6)
    written = io.BytesIO()
    image.save(written, "JPEG", quality=90)
    return written.getvalue()


class Sent:
    def __init__(self, into):
        self.into = into

    def file(self, path):
        shutil.copy(path, self.into)


def test_the_corners_of_a_sheet_lying_askew_are_found(api):
    blob = uploaded(api, photo())["sha256"]
    response = api.post("/api/scans/corners", {"blob": blob}, content_type=JSON)
    assert response.status_code == 200, response.json()
    found = response.json()["corners"]
    assert np.abs(np.subtract(found, DRAWN)).max() < 0.02


def test_a_photo_where_no_sheet_stands_out_is_taken_whole(tmp_path):
    path = tmp_path / "flat.png"
    Image.new("RGB", (400, 300), (128, 128, 128)).save(path)
    assert scanned.corners(path) == scanned.WHOLE


def test_only_a_photo_has_corners(api):
    blob = uploaded(api, pdf_bytes("Naslov"))["sha256"]
    response = api.post("/api/scans/corners", {"blob": blob}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (415, "not_a_photo")


def test_each_page_is_straightened_and_its_paper_made_white(tmp_path):
    path = tmp_path / "page.jpg"
    path.write_bytes(photo())
    target = tmp_path / "scan.pdf"
    assert scanned.made([path, path], [DRAWN, scanned.WHOLE], Sent(target)) == 2
    with pikepdf.open(target) as pdf:
        assert len(pdf.pages) == 2
        first = pdf.pages[0]
        width, height = float(first.MediaBox[2]), float(first.MediaBox[3])
        assert round(height, 2) == scanned.A4_LONG and 0.6 < width / height < 0.8
        image = pikepdf.PdfImage(first.Resources.XObject.Scan).as_pil_image()
    pixels = np.asarray(image)
    paper = pixels[: pixels.shape[0] // 10, : pixels.shape[1] // 10].reshape(-1, 3)
    assert (paper.mean(axis=0) > 245).all()
    assert pixels.min() < 40


@pytest.mark.parametrize(
    "corners",
    [
        [[0, 0], [1, 0], [1, 1]],
        [[0, 0], [0, 1], [1, 1], [1, 0]],
        [[0, 0], [1, 1], [1, 0], [0, 1]],
        [[0, 0], [0.05, 0], [0.05, 0.05], [0, 0.05]],
        [[0, 0], [1.2, 0], [1, 1], [0, 1]],
        [[0, 0], [True, 0], [1, 1], [0, 1]],
    ],
)
def test_corners_that_make_no_page_are_refused(api, corners):
    blob = uploaded(api, photo())["sha256"]
    pages = [{"blob": blob, "corners": corners}]
    assert refused(api, "scan", pages=pages, title="Sken") == (400, "invalid_corners")


def test_the_pages_land_in_the_folder_as_one_file_with_their_text_read(api, service):
    service.append((200, pdf_bytes("Prva", "Druga")))
    folder = api.post("/api/nodes", {"kind": "folder", "title": "Skenovi"}, content_type=JSON)
    blob = uploaded(api, photo())["sha256"]
    pages = [{"blob": blob, "corners": DRAWN}, {"blob": blob, "corners": scanned.WHOLE}]
    made = done(api, "scan", pages=pages, title="Račun", parent=folder.json()["id"])
    node = Node.objects.get(pk=made["id"])
    assert (node.title, str(node.parent_id), node.blob.media_type) == (
        "Račun",
        folder.json()["id"],
        "application/pdf",
    )


def test_pages_scanned_for_a_mail_come_back_as_a_file_to_attach(api, service):
    service.append((200, pdf_bytes("Prva")))
    blob = uploaded(api, photo())["sha256"]
    made = done(api, "scan", pages=[{"blob": blob, "corners": DRAWN}], title="Račun", attached=True)
    assert (made["name"], made["media_type"]) == ("Račun.pdf", "application/pdf")
    assert not Node.objects.filter(title="Račun").exists()


def test_text_the_ocr_service_cannot_read_fails_the_scan(api, service):
    service.append((422, b"broken"))
    blob = uploaded(api, photo())["sha256"]
    pages = [{"blob": blob, "corners": DRAWN}]
    assert refused(api, "scan", pages=pages, title="Sken") == (422, "unreadable")
