import django.db.models.deletion
from django.db import migrations, models


def drop_room_updates(apps, schema_editor):
    apps.get_model("collab", "Update").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("collab", "0001_initial"),
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(drop_room_updates, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name="update", name="collab_upda_room_5d0338_idx"),
        migrations.RemoveField(model_name="update", name="room"),
        migrations.AddField(
            model_name="update",
            name="tab",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="documents.tab",
            ),
        ),
        migrations.AddIndex(
            model_name="update",
            index=models.Index(fields=["tab", "id"], name="collab_upda_tab_id_511cb7_idx"),
        ),
    ]
