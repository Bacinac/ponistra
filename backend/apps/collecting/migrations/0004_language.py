from django.conf import settings
from django.db import migrations, models


def spoken(apps, schema_editor):
    Collection = apps.get_model("collecting", "Collection")
    for collection in Collection.objects.select_related("owner"):
        collection.language = collection.owner.language or settings.LANGUAGE_CODE
        collection.save(update_fields=["language"])


class Migration(migrations.Migration):
    dependencies = [("collecting", "0003_tabled")]

    operations = [
        migrations.AddField(
            model_name="collection",
            name="language",
            field=models.CharField(default="", max_length=8),
            preserve_default=False,
        ),
        migrations.RunPython(spoken, migrations.RunPython.noop),
    ]
