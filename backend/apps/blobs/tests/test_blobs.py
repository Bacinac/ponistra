import hashlib
import io
import os
import uuid
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.blobs import store
from apps.blobs.models import Blob, Upload
from apps.blobs.views import Unsatisfiable, byte_range, serve
from apps.documents.models import Node
from apps.users.models import User

from .office import FILLER, odf, ole, ooxml

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n" + bytes(range(256)) * 8
JSON = "application/json"


def content(response) -> bytes:
    async def read():
        return b"".join([part async for part in response.streaming_content])

    return async_to_sync(read)()


def test_upload_needs_a_session(client):
    assert client.post("/api/uploads", {"size": 3}, content_type=JSON).status_code == 401
    assert client.get(f"/api/uploads/{uuid.uuid4()}").status_code == 401


def test_bytes_are_stored_under_their_sha256(upload):
    sha256 = hashlib.sha256(PDF).hexdigest()
    assert upload(PDF) == {"sha256": sha256, "size": len(PDF), "media_type": "application/pdf"}
    assert store.path_of(sha256).read_bytes() == PDF
    assert store.path_of(sha256).relative_to(store.root()).parts[:2] == (sha256[:2], sha256[2:4])
    assert list(store.root().glob("uploads/*")) == []


def test_the_same_bytes_are_stored_once_and_their_upload_renewed(upload):
    first = upload(PDF)["sha256"]
    Blob.objects.update(uploaded_at=timezone.now() - timedelta(days=1))
    assert upload(PDF)["sha256"] == first
    assert Blob.objects.get().uploaded_at > timezone.now() - timedelta(minutes=1)
    assert list(store.root().glob("incoming/*")) == []


def test_the_type_comes_from_the_bytes_not_the_client(upload):
    assert upload(b"<html>")["media_type"] == "text/html"
    assert upload(b"\x00\x01binary")["media_type"] == "application/octet-stream"


def test_an_empty_file_is_uploaded_in_one_empty_piece(upload):
    assert upload(b"") == {
        "sha256": hashlib.sha256(b"").hexdigest(),
        "size": 0,
        "media_type": "application/octet-stream",
    }


def piece(client, upload: dict, data: bytes, offset: int):
    return client.put(
        f"/api/uploads/{upload['id']}",
        data,
        content_type="application/octet-stream",
        headers={"Upload-Offset": str(offset)},
    )


def test_a_file_arrives_in_pieces_each_at_the_offset_received_so_far(api, settings):
    settings.UPLOAD_CHUNK_BYTES = 1000
    upload = api.post("/api/uploads", {"size": len(PDF)}, content_type=JSON).json()
    assert upload == {
        "id": upload["id"],
        "size": len(PDF),
        "received": 0,
        "chunk": 1000,
        "blob": None,
    }
    assert piece(api, upload, PDF[:1000], 0).json()["received"] == 1000
    lost = piece(api, upload, PDF[:1000], 0)
    assert (lost.status_code, lost.json()) == (409, {"error": "wrong_offset"})
    assert api.get(f"/api/uploads/{upload['id']}").json()["received"] == 1000
    longer = piece(api, upload, PDF[1000:2001], 1000)
    assert (longer.status_code, longer.json()) == (413, {"error": "too_large"})
    assert piece(api, upload, PDF[1000:2000], 1000).json()["received"] == 2000
    done = piece(api, upload, PDF[2000:], 2000).json()
    assert done["received"] == len(PDF)
    assert store.path_of(done["blob"]["sha256"]).read_bytes() == PDF
    assert piece(api, upload, PDF[2000:], 2000).json() == done
    assert api.get(f"/api/uploads/{upload['id']}").json() == done


def test_a_piece_names_its_offset(api):
    upload = api.post("/api/uploads", {"size": 3}, content_type=JSON).json()
    response = api.put(f"/api/uploads/{upload['id']}", b"abc", content_type="text/plain")
    assert (response.status_code, response.json()) == (400, {"error": "invalid_offset"})


def test_an_upload_is_its_uploaders_alone(api, client):
    upload = api.post("/api/uploads", {"size": 3}, content_type=JSON).json()
    client.force_login(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72"))
    assert client.get(f"/api/uploads/{upload['id']}").status_code == 404
    assert piece(client, upload, b"abc", 0).status_code == 404


@pytest.mark.parametrize("size", [-1, "3", True, 1.5, None])
def test_an_upload_names_its_size(api, size):
    response = api.post("/api/uploads", {"size": size}, content_type=JSON)
    assert (response.status_code, response.json()) == (400, {"error": "invalid_size"})


def test_an_upload_over_the_limit_or_the_free_disk_is_refused(api, settings):
    settings.BLOB_MAX_BYTES = len(PDF) - 1
    response = api.post("/api/uploads", {"size": len(PDF)}, content_type=JSON)
    assert (response.status_code, response.json()) == (413, {"error": "too_large"})
    settings.BLOB_MAX_BYTES = len(PDF)
    settings.UPLOAD_RESERVE_BYTES = 10**18
    response = api.post("/api/uploads", {"size": len(PDF)}, content_type=JSON)
    assert (response.status_code, response.json()) == (507, {"error": "no_room"})
    assert not Upload.objects.exists()


@pytest.mark.parametrize(
    "head, media_type",
    [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff\xe0", "image/jpeg"),
        (b"GIF89a", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"\x00\x00\x00\x1cftypavif", "image/avif"),
        (b'<?xml version="1.0"?>\n<SVG xmlns="http://www.w3.org/2000/svg">', "image/svg+xml"),
        (b"%PDF-1.7", "application/pdf"),
        (b"{\\rtf1\\ansi", "application/rtf"),
        (b"BEGIN:VCALENDAR\r\nVERSION:2.0", "text/calendar"),
        (b"\xef\xbb\xbfBEGIN:VCARD\r\nVERSION:4.0", "text/vcard"),
        (b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00", "video/mp4"),
        (b"\x00\x00\x00\x18ftypmp42", "video/mp4"),
        (b"\x00\x00\x00\x14ftypqt  ", "video/quicktime"),
        (b"\x00\x00\x00\x20ftypM4A ", "audio/mp4"),
        (b"\x00\x00\x00\x18ftypheic", "application/octet-stream"),
        (b"\x1a\x45\xdf\xa3\xa3\x42\x82\x84webm\x42\x87", "video/webm"),
        (b"\x1a\x45\xdf\xa3\xa3\x42\x82\x88matroska", "video/x-matroska"),
        (b"OggS\x00\x02" + bytes(22) + b"\x13OpusHead", "audio/ogg"),
        (b"OggS\x00\x02" + bytes(22) + b"\x80theora", "application/octet-stream"),
        (b"fLaC\x00\x00\x00\x22", "audio/flac"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", "audio/wav"),
        (b"RIFF\x24\x00\x00\x00AVI LIST", "application/octet-stream"),
        (b"ID3\x04\x00\x00", "audio/mpeg"),
        (b"\xff\xfb\x90\x64", "audio/mpeg"),
        (b"\xff\xf1\x50\x80", "audio/aac"),
        (b"<html>", "text/html"),
        (b"<div>Prodaja</div>", "text/plain"),
        (b"G21 G90\nN10 G00 X0 Y0\r\n", "text/plain"),
        ("Šifra;Količina\r\nŽičana mreža;12\r\n".encode("cp1250"), "text/plain"),
        ("Write-Host 'Zdravo'".encode("utf-16"), "text/plain"),
        (b"\x1b[1mlog\x1b[0m\n", "text/plain"),
        (b"MZ\x90\x00\x03", "application/octet-stream"),
        (b"\x01\x02\x03abc", "application/octet-stream"),
        (b"", "application/octet-stream"),
    ],
)
def test_sniff(head, media_type):
    assert store.sniff(head) == media_type


@pytest.mark.parametrize(
    "data, media_type",
    [
        (odf(store.ODT), store.ODT),
        (odf(store.ODS), store.ODS),
        (odf(store.ODP), store.ODP),
        (ooxml("xl/workbook.xml"), store.XLSX),
        (
            ooxml("xl/workbook.xml", "application/vnd.ms-excel.sheet.macroEnabled.main+xml"),
            store.XLSM,
        ),
        (
            ooxml(
                "xl/workbook.xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml",
            ),
            store.XLTX,
        ),
        (
            ooxml(
                "word/document.xml",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
            ),
            store.DOCX,
        ),
        (
            ooxml(
                "word/document.xml",
                "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
            ),
            store.DOTM,
        ),
        (ooxml("ppt/presentation.xml"), store.PPTX),
        (
            ooxml(
                "ppt/presentation.xml",
                "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml",
            ),
            store.PPTM,
        ),
        (
            ooxml(
                "ppt/presentation.xml",
                "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml",
            ),
            store.PPSX,
        ),
        (ole({"WordDocument": FILLER}), store.DOC),
        (ole({"Workbook": FILLER}), store.XLS),
        (ole({"PowerPoint Document": FILLER}), store.PPT),
        (store.OLE + b"\0" * 100, "application/octet-stream"),
    ],
)
def test_a_container_is_typed_by_what_it_holds(data, media_type):
    assert store.put(io.BytesIO(data)).media_type == media_type


def test_what_is_put_over_the_limit_is_refused_and_leaves_nothing(settings):
    settings.BLOB_MAX_BYTES = len(PDF) - 1
    with pytest.raises(store.TooLarge):
        store.put(io.BytesIO(PDF))
    assert not Blob.objects.exists()
    assert list(store.root().glob("??/??/*")) == []
    assert list(store.root().glob("incoming/*")) == []


@pytest.mark.parametrize(
    "header, expected",
    [
        ("bytes=0-99", (0, 99)),
        ("bytes=100-", (100, 999)),
        ("bytes=900-5000", (900, 999)),
        ("bytes=-100", (900, 999)),
        ("bytes=-5000", (0, 999)),
        ("bytes=5-4", None),
        ("bytes=-", None),
        ("bytes=0-1,5-6", None),
        ("items=0-1", None),
    ],
)
def test_byte_range(header, expected):
    assert byte_range(header, 1000) == expected


@pytest.mark.parametrize(
    "header, size", [("bytes=1000-", 1000), ("bytes=-0", 1000), ("bytes=-1", 0)]
)
def test_unsatisfiable_byte_range(header, size):
    with pytest.raises(Unsatisfiable):
        byte_range(header, size)


@pytest.fixture
def blob():
    return store.put(io.BytesIO(PDF))


def test_serve_the_whole_file(rf, blob):
    response = serve(rf.get("/"), blob, "Ponuda.pdf")
    assert response.status_code == 200
    assert response["Accept-Ranges"] == "bytes"
    assert response["ETag"] == f'"{blob.sha256}"'
    assert content(response) == PDF


def test_serve_a_range(rf, blob):
    response = serve(rf.get("/", headers={"Range": "bytes=9-12"}), blob, "Ponuda.pdf")
    assert response.status_code == 206
    assert response["Content-Range"] == f"bytes 9-12/{len(PDF)}"
    assert response["Content-Length"] == "4"
    assert content(response) == PDF[9:13]


def test_serve_refuses_a_range_past_the_end(rf, blob):
    response = serve(rf.get("/", headers={"Range": f"bytes={len(PDF)}-"}), blob, "x.pdf")
    assert response.status_code == 416
    assert response["Content-Range"] == f"bytes */{len(PDF)}"


def test_serve_ignores_a_range_for_other_bytes(rf, blob):
    request = rf.get("/", headers={"Range": "bytes=0-3", "If-Range": '"other"'})
    response = serve(request, blob, "x.pdf")
    assert response.status_code == 200
    assert content(response) == PDF


def test_serve_answers_a_known_etag_with_304(rf, blob):
    response = serve(rf.get("/", headers={"If-None-Match": f'"{blob.sha256}"'}), blob, "x.pdf")
    assert response.status_code == 304


def test_serve_fails_loud_when_the_bytes_do_not_match_the_row(rf, blob):
    store.path_of(blob.sha256).write_bytes(PDF[:10])
    with pytest.raises(OSError, match="holds 10 bytes"):
        serve(rf.get("/"), blob, "x.pdf")


def test_collect_spares_fresh_and_referenced_bytes_and_sweeps_leftovers(blob):
    old = timezone.now() - timedelta(days=1)
    stale = store.put(io.BytesIO(b"stale"))
    fresh = store.put(io.BytesIO(b"fresh"))
    Blob.objects.filter(pk__in=[blob.pk, stale.pk]).update(uploaded_at=old)
    Node.objects.create(kind=Node.Kind.FILE, title="Ponuda", blob=blob)
    orphan = store.path_of("ab" * 32)
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"left by a crash")
    (store.root() / "incoming" / "tmp123").write_bytes(b"half")

    store.collect()

    assert set(Blob.objects.values_list("pk", flat=True)) == {blob.pk, fresh.pk}
    assert sorted(path.name for path in store.root().glob("??/??/*")) == sorted([blob.pk, fresh.pk])
    assert list(store.root().glob("incoming/*")) == []


def test_collected_bytes_wait_in_dead_as_long_as_a_restore_reaches_back(blob):
    Blob.objects.filter(pk=blob.pk).update(uploaded_at=timezone.now() - timedelta(days=1))
    expired = store.dead() / (timezone.localdate() - store.KEPT - timedelta(days=1)).isoformat()
    expired.mkdir(parents=True)
    (expired / ("cd" * 32)).write_bytes(b"long gone")

    store.collect()

    assert not store.path_of(blob.sha256).exists()
    assert [path.name for path in store.dead().glob("*/*")] == [blob.sha256]
    assert store.dead_bytes() == blob.size
    assert store.revive(blob.sha256)
    assert store.path_of(blob.sha256).read_bytes() == PDF
    assert not store.revive("cd" * 32)


def test_collect_sweeps_uploads_abandoned_for_a_day(api):
    old = timezone.now() - timedelta(days=2)
    abandoned = Upload.objects.create(user=api.user, size=10, received=4, touched_at=old)
    going = Upload.objects.create(user=api.user, size=10, received=4, touched_at=timezone.now())
    for upload in (abandoned, going):
        store.part_of(upload.pk).parent.mkdir(parents=True, exist_ok=True)
        store.part_of(upload.pk).write_bytes(b"half")
    os.utime(store.part_of(abandoned.pk), (old.timestamp(), old.timestamp()))
    begun = store.part_of(uuid.uuid4())
    begun.write_bytes(b"just begun")

    store.collect()

    assert list(Upload.objects.values_list("pk", flat=True)) == [going.pk]
    assert sorted(store.root().glob("uploads/*")) == sorted([store.part_of(going.pk), begun])
