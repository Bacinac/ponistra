from django.db import migrations, models


def settled(apps, schema_editor):
    # The live modules, as the calculation they run reads the models as they are.
    from apps.versions import history
    from apps.versions.models import Version

    documents = set()
    for version in Version.objects.select_related("document").order_by("document", "number"):
        history.settle(version)
        documents.add(version.document_id)
    for document in documents:
        history.collect_pieces(document)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("content", "0016_table_filters"),
        ("versions", "0008_file_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="piece",
            name="shown",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="piece",
            name="size",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="versiongrid",
            name="at",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="versiongrid",
            name="outline",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="versiongrid",
            name="size",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(settled, migrations.RunPython.noop),
    ]
