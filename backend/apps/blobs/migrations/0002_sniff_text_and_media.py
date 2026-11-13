from django.db import migrations

from apps.blobs import store


def sniffed(apps, schema_editor):
    Blob = apps.get_model("blobs", "Blob")
    for blob in Blob.objects.filter(media_type=store.UNKNOWN).iterator():
        try:
            with store.path_of(blob.sha256).open("rb") as file:
                sample = file.read(store.SAMPLE)
        except FileNotFoundError:
            continue
        media_type = store.sniff(sample)
        if media_type != store.UNKNOWN:
            Blob.objects.filter(pk=blob.pk).update(media_type=media_type)


class Migration(migrations.Migration):
    dependencies = [("blobs", "0001_initial")]

    operations = [migrations.RunPython(sniffed, migrations.RunPython.noop)]
