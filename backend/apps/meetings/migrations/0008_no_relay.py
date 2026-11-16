from django.db import migrations

from apps.collab.changes import followed

before = followed("meetings_relay", "meetings", "*")


class Migration(migrations.Migration):
    dependencies = [
        ("meetings", "0007_relay"),
    ]

    operations = [
        migrations.RunSQL(before.reverse_sql, before.sql),
        migrations.DeleteModel(name="Relay"),
    ]
