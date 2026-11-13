import io

import pytest
from PIL import Image

from apps.blobs import previews, store
from apps.blobs.models import Blob, Preview
from apps.blobs.tests.uploads import held
from apps.documents.tests.test_views import PNG, SVG, create, from_trash, to_trash

pytestmark = pytest.mark.django_db


def drawn(image: Image.Image, format: str, **given) -> bytes:
    out = io.BytesIO()
    image.save(out, format, **given)
    return out.getvalue()


def photo(width: int, height: int) -> bytes:
    return drawn(Image.new("RGB", (width, height), "teal"), "PNG")


def turned() -> bytes:
    """A photograph taken with the camera on its side, which says so rather than turning."""
    exif = Image.Exif()
    exif[0x0112] = 6
    return drawn(Image.new("RGB", (400, 300), "teal"), "JPEG", exif=exif)


def pdf() -> bytes:
    return drawn(Image.new("RGB", (595, 842), "white"), "PDF")


def picture(sha256: str) -> Image.Image:
    return Image.open(store.path_of(Preview.objects.get(source=sha256).picture_id))


def test_an_image_and_a_pdf_a_file_keeps_are_drawn_small_once(api, upload):
    large = upload(photo(3000, 2000))["sha256"]
    side = upload(turned())["sha256"]
    page = upload(pdf())["sha256"]
    for title, sha256 in [("Hala", large), ("Stroj", side), ("Ponuda", page)]:
        create(api, "file", title, blob=sha256)
    while previews.draw_next():
        pass
    assert not previews.draw_next()
    assert picture(large).size == (800, 533)
    assert picture(large).format == "WEBP"
    assert picture(side).size == (300, 400)
    assert max(picture(page).size) == previews.SIDE


@pytest.mark.django_db(transaction=True)
def test_a_pdf_the_extractor_holds_is_drawn_as_soon_as_it_lets_go(api, upload):
    page = upload(pdf())["sha256"]
    create(api, "file", "Ponuda", blob=page)
    with held(page):
        assert previews.draw_next()
    assert max(picture(page).size) == previews.SIDE


def test_only_what_a_file_keeps_is_drawn_and_an_image_unread_says_why(api, upload):
    upload(photo(10, 10))
    broken = upload(PNG)["sha256"]
    create(api, "file", "Slika", blob=broken)
    create(api, "file", "Logo", blob=upload(SVG)["sha256"])
    while previews.draw_next():
        pass
    preview = Preview.objects.get()
    assert (preview.source_id, preview.picture) == (broken, None)
    assert "UnidentifiedImageError" in preview.failed


def test_a_picture_is_kept_while_its_preview_refers_to_it(api, upload):
    sha256 = upload(photo(10, 10))["sha256"]
    create(api, "file", "Slika", blob=sha256)
    previews.draw_next()
    kept = Preview.objects.get().picture_id
    assert not store.unreferenced(Blob.objects.filter(pk=kept)).exists()
    Preview.objects.all().delete()
    assert store.unreferenced(Blob.objects.filter(pk=kept)).exists()


def test_a_file_is_drawn_on_the_spot_and_its_picture_kept_by_name_for_good(api, upload):
    sha256 = upload(photo(1000, 1000))["sha256"]
    file = create(api, "file", "Slika", blob=sha256)
    assert api.get(f"/api/nodes/{file}").json()["node"]["picture"] is None

    response = api.get(f"/api/nodes/{file}/picture")
    assert response.status_code == 200
    assert (response["Content-Type"], response["Cache-Control"]) == (
        "image/webp",
        "private, no-cache",
    )
    picture = Preview.objects.get(source=sha256).picture_id
    assert api.get(f"/api/nodes/{file}").json()["node"]["picture"] == picture
    assert not previews.draw_next()

    response = api.get(f"/api/nodes/{file}/picture?v={picture}")
    assert response["Cache-Control"] == "private, max-age=31536000, immutable"
    assert api.get(f"/api/nodes/{file}/picture?v={sha256}").status_code == 404


def test_the_trash_shows_a_files_picture_until_it_is_purged(api, upload):
    file = create(api, "file", "Slika", blob=upload(photo(1000, 1000))["sha256"])
    assert previews.draw_next()
    to_trash(api, file)
    (shown,) = api.get("/api/trash").json()["items"]
    assert api.get(f"/api/nodes/{file}/picture?v={shown['picture']}").status_code == 200
    from_trash(api, "purge", file)
    assert api.get(f"/api/nodes/{file}/picture").status_code == 404


def test_a_file_of_another_kind_has_no_picture(api, upload):
    text = create(api, "file", "Popis", blob=upload(b"Naziv;Kolicina\n")["sha256"], extension="csv")
    logo = create(api, "file", "Logo", blob=upload(SVG)["sha256"])
    broken = create(api, "file", "Slika", blob=upload(PNG)["sha256"])
    for file in (text, logo, broken):
        assert api.get(f"/api/nodes/{file}/picture").json() == {"error": "not_found"}
