from django.db import migrations
from django.db.models.functions import Lower


def lowered(apps, schema_editor):
    points = apps.get_model("contacts", "Point").objects.filter(kind="email")
    points.exclude(value=Lower("value")).update(value=Lower("value"))


class Migration(migrations.Migration):
    dependencies = [("contacts", "0001_address_book")]

    operations = [migrations.RunPython(lowered, migrations.RunPython.noop)]
