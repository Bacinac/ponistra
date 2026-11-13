import json

from django.conf import settings
from django.db import migrations


def metric_equals_unreported(apps, schema_editor):
    families = json.loads(settings.FONTS.read_text())["families"]
    kept = {
        name.lower()
        for family in families
        for name in [family["name"], *family.get("replaces", [])]
    }
    Node = apps.get_model("documents", "Node")
    for node in Node.objects.filter(imported__isnull=False).only("id", "imported"):
        reported = node.imported.get("fonts", [])
        found = [each for each in reported if each["from"].strip().lower() not in kept]
        if found != reported:
            node.imported["fonts"] = found
            node.save(update_fields=["imported"])


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0015_company_and_confined"),
    ]

    operations = [
        migrations.RunPython(metric_equals_unreported, migrations.RunPython.noop),
    ]
