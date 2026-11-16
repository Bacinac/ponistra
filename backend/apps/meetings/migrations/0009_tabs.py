from django.db import migrations, models

from apps.collab.changes import followed


class Migration(migrations.Migration):
    dependencies = [("meetings", "0008_no_relay")]

    operations = [
        migrations.AddField(model_name="meeting", name="tabs", field=models.JSONField(default=list)),
        followed("meetings_meeting", "meetings", "r:id"),
    ]
