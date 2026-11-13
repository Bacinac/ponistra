import uuid

from django.db import migrations, models


def give_each_document_its_room(apps, schema_editor):
    Node = apps.get_model("documents", "Node")
    for node in Node.objects.filter(kind="document"):
        node.room = uuid.uuid4()
        node.save(update_fields=["room"])


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0006_title_search"),
    ]

    operations = [
        migrations.AddField(
            model_name="node",
            name="room",
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
        migrations.RunPython(give_each_document_its_room, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="node",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind", "document"), ("room__isnull", False))
                | models.Q(models.Q(("kind", "document"), _negated=True), ("room__isnull", True)),
                name="a_document_has_its_room",
            ),
        ),
    ]
