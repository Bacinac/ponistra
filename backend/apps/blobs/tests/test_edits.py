import io
from datetime import timedelta

import pytest
from django.utils import timezone
from PIL import Image
from pycrdt import Doc, Map

from apps.blobs import edits, previews, store
from apps.blobs.edits import Edits, Mark
from apps.blobs.models import Blob
from apps.collab.models import Update
from apps.documents.models import Node
from apps.documents.tests.test_views import create
from apps.versions.history import state_of

from .test_blobs import content
from .test_previews import drawn, photo, turned

pytestmark = pytest.mark.django_db

LATER = timedelta(seconds=3)


def halves() -> bytes:
    """Red on the left, blue on the right."""
    image = Image.new("RGB", (40, 20), "blue")
    image.paste("red", (0, 0, 20, 20))
    return drawn(image, "PNG")


def edit(file_id, kept_in=edits.EDITS, **changed) -> None:
    """Changes the file's edits the way its editors would, a value of None taking one back."""
    file = Node.objects.get(pk=file_id)
    doc = Doc()
    doc.apply_update(state_of(file.room))
    before = doc.get_state()
    kept = doc.get(kept_in, type=Map)
    with doc.transaction():
        for key, value in changed.items():
            if value is None:
                del kept[key]
            else:
                kept[key] = value
    Update.objects.create(document=file, room=file.room, data=doc.get_update(before))


def opened(blob) -> Image.Image:
    return Image.open(store.path_of(blob.sha256))


AT = "2026-10-28T12:00:00+01:00"


def kept_mark(kind, points, **given) -> dict:
    return {"kind": kind, "points": points, "by": 1, "at": AT, **given}


def marked(kind, points, **given) -> Mark:
    return edits._mark(kind, kept_mark(kind, points, **given))


def white(width, height) -> bytes:
    return drawn(Image.new("RGB", (width, height), "white"), "PNG")


def red(pixel) -> bool:
    return pixel[0] > 150 and pixel[1] < 100 and pixel[2] < 100


def test_edits_are_read_as_kept_and_refused_when_they_draw_nothing():
    assert edits.read({}) == Edits()
    assert edits.read(
        {"crop": {"x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0}, "turn": 270.0, "side": 800.0}
    ) == Edits(crop=(1, 2, 3, 4), turn=270, side=800)
    for kept in (
        {"turn": 45},
        {"flip": 1},
        {"side": 8},
        {"brightness": 2.5},
        {"contrast": True},
        {"crop": {"x": -1, "y": 0, "w": 3, "h": 4}},
        {"crop": {"x": 0, "y": 0, "w": 0.5, "h": 4}},
        {"blur": 3},
    ):
        with pytest.raises(edits.Unreadable):
            edits.read(kept)


def test_an_image_is_cropped_turned_mirrored_and_made_smaller(upload):
    blob = Blob.objects.get(pk=upload(halves())["sha256"])
    copy = opened(edits.drawn(blob, Edits(crop=(10, 0, 30, 20), turn=90, flip=True, side=15)))
    assert (copy.format, copy.size) == ("PNG", (10, 15))
    assert copy.getpixel((5, 1))[0] > 200
    assert copy.getpixel((5, 13))[2] > 200


def test_a_crop_is_of_the_image_upright_and_its_metadata_left_out(upload):
    blob = Blob.objects.get(pk=upload(turned())["sha256"])
    copy = opened(edits.drawn(blob, Edits(crop=(0, 0, 300, 100))))
    assert (copy.format, copy.size) == ("JPEG", (300, 100))
    assert not copy.getexif()
    with pytest.raises(edits.Unreadable):
        edits.drawn(blob, Edits(crop=(0, 0, 400, 100)))


def test_the_tone_is_the_browsers_filters_each_clamped_in_turn(upload):
    blob = Blob.objects.get(
        pk=upload(drawn(Image.new("RGBA", (1, 1), (100, 150, 200, 128)), "PNG"))["sha256"]
    )
    toned = Edits(brightness=1.2, contrast=1.5, saturation=0.5)
    assert opened(edits.drawn(blob, toned)).getpixel((0, 0)) == (153, 198, 223, 128)


def test_the_copy_follows_the_room_once_it_is_quiet(api, upload):
    sha256 = upload(photo(1000, 500))["sha256"]
    file = create(api, "file", "Hala", blob=sha256)
    edits.tend()
    assert Node.objects.get(pk=file).edited is None

    edit(file, turn=90, side=400)
    edits.tend()
    assert Node.objects.get(pk=file).edited is None
    edits.tend(timezone.now() + LATER)
    copy = Node.objects.get(pk=file).edited
    assert opened(copy).size == (200, 400)
    while previews.draw_next():
        pass
    picture = api.get(f"/api/nodes/{file}").json()["node"]["picture"]
    assert picture == copy.preview.picture_id

    edit(file, turn=None, side=None)
    edits.tend(timezone.now() + LATER)
    assert Node.objects.get(pk=file).edited is None
    picture = api.get(f"/api/nodes/{file}").json()["node"]["picture"]
    assert picture == Blob.objects.get(pk=sha256).preview.picture_id


def test_edits_the_copy_cannot_be_drawn_with_are_logged_once(api, upload, caplog):
    file = create(api, "file", "Hala", blob=upload(photo(100, 50))["sha256"])
    edit(file, crop={"x": 50, "y": 0, "w": 100, "h": 50})
    edits.tend(timezone.now() + LATER)
    edits.tend(timezone.now() + LATER)
    assert caplog.text.count("could not be drawn") == 1
    assert api.get(f"/api/nodes/{file}/edited").json() == {"error": "unreadable_edits"}


def test_the_edited_image_is_given_out_drawn_on_the_spot(api, upload):
    sha256 = upload(halves())["sha256"]
    file = create(api, "file", "Hala", blob=sha256)
    response = api.get(f"/api/nodes/{file}/edited?download=1")
    assert response["ETag"] == f'"{sha256}"'
    assert 'attachment; filename="Hala.png"' in response["Content-Disposition"]

    edit(file, crop={"x": 0, "y": 0, "w": 20, "h": 20})
    response = api.get(f"/api/nodes/{file}/edited")
    copy = Image.open(io.BytesIO(content(response)))
    assert copy.size == (20, 20)
    assert response["ETag"] == f'"{Node.objects.get(pk=file).edited_id}"'

    text = create(api, "file", "Popis", blob=upload(b"Naziv;Kolicina\n")["sha256"], extension="csv")
    assert api.get(f"/api/nodes/{text}/edited").status_code == 404


def test_marks_are_read_as_kept_in_the_order_they_were_made():
    later = kept_mark("blur", [0, 0, 4, 4], at="2026-10-28T12:00:01+01:00")
    first = kept_mark("text", [5.5, 9], color="red", size=24, text="Ulaz")
    read = edits.read({}, {"b": later, "a": first})
    assert [mark.id for mark in read.marks] == ["a", "b"]
    assert read.marks[0] == Mark(
        "a", "text", (5.5, 9), edits._mark("a", first).at, "#C4321C", size=24, text="Ulaz"
    )
    for mark in (
        kept_mark("circle", [0, 0, 4, 4]),
        kept_mark("arrow", [0, 0, 4, 4], color="pink", width=4),
        kept_mark("arrow", [0, 0, 4], color="red", width=4),
        kept_mark("stroke", [0, 0, 4, 4], color="red", width=0),
        kept_mark("rectangle", [0, 0, 4, 4], color="red", width=4, size=3),
        kept_mark("text", [0, 0], color="red", size=24, text="Dva\nretka"),
        kept_mark("text", [0, 0], color="red", size=24, text="  "),
        kept_mark("blur", [0, 0, 4, 4], at="jučer"),
    ):
        with pytest.raises(edits.Unreadable):
            edits.read({}, {"x": mark})


def test_a_mark_stays_where_it_was_drawn_as_the_image_is_cropped_turned_and_made_smaller(upload):
    blob = Blob.objects.get(pk=upload(white(40, 20))["sha256"])
    frame = marked("rectangle", [30, 5, 36, 15], color="red", width=2)
    copy = opened(edits.drawn(blob, Edits(crop=(20, 0, 20, 20), turn=90, marks=(frame,))))
    assert copy.size == (20, 20)
    assert red(copy.getpixel((10, 10))) and red(copy.getpixel((5, 13)))
    assert copy.getpixel((10, 13)) == (255, 255, 255)

    wide = marked("rectangle", [30, 5, 36, 15], color="red", width=4)
    smaller = opened(edits.drawn(blob, Edits(side=20, flip=True, marks=(wide,))))
    assert smaller.size == (20, 10)
    assert red(smaller.getpixel((2, 5))) and smaller.getpixel((17, 5)) == (255, 255, 255)


def test_an_arrow_points_and_a_line_follows_the_hand(upload):
    blob = Blob.objects.get(pk=upload(white(100, 50))["sha256"])
    arrow = marked("arrow", [10, 25, 90, 25], color="blue", width=4)
    line = marked("stroke", [10, 5, 50, 5, 50, 45], color="red", width=2)
    copy = opened(edits.drawn(blob, Edits(marks=(arrow, line))))
    assert copy.getpixel((30, 25))[2] > 150 and copy.getpixel((30, 25))[0] < 100
    assert copy.getpixel((85, 30))[2] > 150
    assert copy.getpixel((30, 33)) == (255, 255, 255)
    assert red(copy.getpixel((30, 5))) and red(copy.getpixel((50, 30)))


def test_a_blurred_part_mixes_what_it_covers_and_leaves_the_rest(upload):
    blob = Blob.objects.get(pk=upload(halves())["sha256"])
    copy = opened(edits.drawn(blob, Edits(marks=(marked("blur", [10, 0, 30, 20]),))))
    mixed = copy.getpixel((20, 10))
    assert mixed[0] > 60 and mixed[2] > 60
    assert copy.getpixel((5, 10)) == (255, 0, 0)
    assert copy.getpixel((35, 10)) == (0, 0, 255)


def test_a_text_reads_across_the_image_as_it_shows_edged_in_white(upload):
    black = drawn(Image.new("RGB", (200, 100), "black"), "PNG")
    blob = Blob.objects.get(pk=upload(black)["sha256"])
    text = marked("text", [20, 60], color="red", size=40, text="HALA")
    for turn in (0, 90):
        copy = opened(edits.drawn(blob, Edits(turn=turn, marks=(text,))))
        pixels = [copy.getpixel((x, y)) for x in range(copy.width) for y in range(copy.height)]
        assert any(red(pixel) for pixel in pixels)
        assert any(min(pixel) > 200 for pixel in pixels)
        reds = [
            (x, y)
            for x in range(copy.width)
            for y in range(copy.height)
            if red(copy.getpixel((x, y)))
        ]
        across = max(x for x, _ in reds) - min(x for x, _ in reds)
        down = max(y for _, y in reds) - min(y for _, y in reds)
        assert across > down * 2


def save(api, file_id, title):
    return api.post(
        f"/api/nodes/{file_id}/edited", {"title": title}, content_type="application/json"
    )


def test_the_copy_is_saved_as_a_new_image_beside_the_file(api, upload):
    folder = create(api, "folder", "Hale")
    file = create(
        api, "file", "Hala", parent=folder, blob=upload(halves())["sha256"], extension="png"
    )
    assert save(api, file, "Hala 2").json() == {"error": "not_edited"}

    edit(file, crop={"x": 0, "y": 0, "w": 20, "h": 20})
    copy = save(api, file, "Hala (uređeno)").json()
    saved = Node.objects.get(pk=copy["id"])
    assert (saved.title, str(saved.parent_id), saved.extension) == ("Hala (uređeno)", folder, "png")
    assert saved.blob_id == Node.objects.get(pk=file).edited_id
    assert opened(saved.blob).size == (20, 20)
