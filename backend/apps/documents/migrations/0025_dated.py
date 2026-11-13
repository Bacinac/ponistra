import re
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import olefile
import pikepdf
from django.conf import settings
from django.db import migrations
from django.db.models import F, Q
from lxml import etree
from PIL import Image, UnidentifiedImageError

# Uploaded before the upload told when the file was last changed, and nobody changed it since:
# such a document or file takes the date its file keeps of itself.
ARRIVING = timedelta(minutes=1)
EARLIEST = datetime(1980, 1, 1, tzinfo=UTC)
PDF_DATE = re.compile(
    r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(?:(Z)|([+-])(\d{2})'?(\d{2})?'?)?"
)
FRACTION = re.compile(r"(\.\d{6})\d+")
CORE = "{http://purl.org/dc/terms/}modified"
ODF = "{http://purl.org/dc/elements/1.1/}date"


def _local(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))


def _iso(text: str | None) -> datetime | None:
    return _local(datetime.fromisoformat(FRACTION.sub(r"\1", text.strip()))) if text else None


def _zipped(path: Path) -> datetime | None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for member, tag in (("docProps/core.xml", CORE), ("meta.xml", ODF)):
            if member in names:
                found = etree.fromstring(archive.read(member)).find(f".//{tag}")
                return _iso(found.text if found is not None else None)
    return None


def _ole(path: Path) -> datetime | None:
    with olefile.OleFileIO(str(path)) as ole:
        told = ole.get_metadata()
        saved = told.last_saved_time or told.create_time
    return saved.replace(tzinfo=UTC) if saved else None


def _pdf(path: Path) -> datetime | None:
    with pikepdf.open(path) as pdf:
        info = pdf.docinfo
        given = info.get("/ModDate") or info.get("/CreationDate")
    found = PDF_DATE.match(str(given)) if given is not None else None
    if found is None:
        return None
    year, month, day, hour, minute, second, zulu, sign, hours, minutes = found.groups()
    moment = datetime(
        int(year), int(month or 1), int(day or 1), int(hour or 0), int(minute or 0), int(second or 0)
    )
    if zulu:
        return moment.replace(tzinfo=UTC)
    if sign:
        offset = timedelta(hours=int(hours), minutes=int(minutes or 0))
        return (moment - offset if sign == "+" else moment + offset).replace(tzinfo=UTC)
    return _local(moment)


def _picture(path: Path) -> datetime | None:
    with Image.open(path) as image:
        exif = image.getexif()
    given = exif.get(0x0132) or exif.get_ifd(0x8769).get(0x9003)
    return _local(datetime.strptime(given.strip(), "%Y:%m:%d %H:%M:%S")) if given else None


def _changed(path: Path, media_type: str) -> datetime | None:
    try:
        if media_type == "application/pdf":
            return _pdf(path)
        if media_type.startswith("image/") and media_type != "image/svg+xml":
            return _picture(path)
        if zipfile.is_zipfile(path):
            return _zipped(path)
        if olefile.isOleFile(str(path)):
            return _ole(path)
    except (
        ValueError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        etree.XMLSyntaxError,
        pikepdf.PdfError,
        UnidentifiedImageError,
    ):
        return None
    return None


def date_from_files(apps, schema_editor):
    Node = apps.get_model("documents", "Node")
    untouched = Node.objects.filter(
        Q(kind="document", source__isnull=False) | Q(kind="file", blob__isnull=False),
        updated_at__lt=F("created_at") + ARRIVING,
    ).select_related("source", "blob")
    for node in untouched.iterator(chunk_size=200):
        original = node.source if node.kind == "document" else node.blob
        sha256 = original.sha256
        path = Path(settings.BLOB_ROOT) / sha256[:2] / sha256[2:4] / sha256
        changed = _changed(path, original.media_type)
        if changed is not None and EARLIEST <= changed <= node.created_at:
            Node.objects.filter(pk=node.pk).update(updated_at=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("blobs", "0005_pages"),
        ("documents", "0024_copied"),
    ]

    operations = [migrations.RunPython(date_from_files, migrations.RunPython.noop)]
