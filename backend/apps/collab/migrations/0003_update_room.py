from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def file_updates_under_their_tab_room(apps, schema_editor):
    Tab = apps.get_model("documents", "Tab")
    Update = apps.get_model("collab", "Update")
    Update.objects.update(room=Subquery(Tab.objects.filter(pk=OuterRef("tab")).values("room")))


class Migration(migrations.Migration):
    dependencies = [
        ("collab", "0002_update_tab"),
        ("documents", "0004_tab_room"),
    ]

    operations = [
        migrations.AddField(model_name="update", name="room", field=models.UUIDField(null=True)),
        migrations.RunPython(file_updates_under_their_tab_room, migrations.RunPython.noop),
        migrations.AlterField(model_name="update", name="room", field=models.UUIDField()),
        migrations.RemoveIndex(model_name="update", name="collab_upda_tab_id_511cb7_idx"),
        migrations.AddIndex(
            model_name="update",
            index=models.Index(fields=["room", "id"], name="collab_upda_room_5d0338_idx"),
        ),
    ]
