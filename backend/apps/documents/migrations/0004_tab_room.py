import uuid

from django.db import migrations, models


def give_each_tab_its_room(apps, schema_editor):
    Tab = apps.get_model("documents", "Tab")
    for tab in Tab.objects.all():
        tab.room = uuid.uuid4()
        tab.save(update_fields=["room"])


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_one_document_kind"),
    ]

    operations = [
        migrations.AddField(model_name="tab", name="room", field=models.UUIDField(null=True)),
        migrations.RunPython(give_each_tab_its_room, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tab",
            name="room",
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
