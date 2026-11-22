from django.db import migrations

from apps.blobs import store


def sniffed(apps, schema_editor):
    """Bytes of no kind known before pictures Pillow reads, archives and Outlook messages were
    told (D23)."""
    Blob = apps.get_model("blobs", "Blob")
    for blob in Blob.objects.filter(media_type=store.UNKNOWN).iterator():
        path = store.path_of(blob.sha256)
        try:
            with path.open("rb") as file:
                sample = file.read(store.SAMPLE)
        except FileNotFoundError:
            continue
        media_type = store.sniff(sample)
        if sample.startswith(store.OLE):
            media_type = store.sniff_ole(path) or media_type
        if media_type != store.UNKNOWN:
            Blob.objects.filter(pk=blob.pk).update(media_type=media_type)


class Migration(migrations.Migration):
    dependencies = [("blobs", "0005_pages")]

    operations = [migrations.RunPython(sniffed, migrations.RunPython.noop)]
