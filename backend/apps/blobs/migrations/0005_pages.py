from django.db import migrations

from apps.blobs import store


def told_again(apps, schema_editor):
    """Pages of HTML were kept as text, or as an SVG picture where one sat near the top; a board
    (D36) is told by its kind, and searched by the text it shows rather than by its source."""
    Blob = apps.get_model("blobs", "Blob")
    BlobText = apps.get_model("search", "BlobText")
    for blob in Blob.objects.filter(media_type__in=(store.TEXT, "image/svg+xml")).iterator():
        with store.path_of(blob.sha256).open("rb") as kept:
            sample = kept.read(store.SAMPLE)
        if store.sniff(sample) == store.HTML:
            Blob.objects.filter(pk=blob.pk).update(media_type=store.HTML)
            BlobText.objects.filter(blob=blob.pk).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("blobs", "0004_preview"),
        ("search", "0004_blob_text"),
    ]

    operations = [
        migrations.RunPython(told_again, migrations.RunPython.noop),
    ]
