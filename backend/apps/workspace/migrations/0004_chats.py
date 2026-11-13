from django.db import migrations, models


def chats(apps, schema_editor):
    apps.get_model("workspace", "Command").objects.filter(kind="round").update(kind="chat")


class Migration(migrations.Migration):
    dependencies = [
        ("workspace", "0003_kinds"),
    ]

    operations = [
        migrations.AlterField(
            model_name="command",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chat", "Chat"),
                    ("start", "Start"),
                    ("consolidate", "Consolidate"),
                    ("push", "Push"),
                    ("auto", "Auto"),
                    ("say", "Say"),
                    ("answer", "Answer"),
                    ("rename", "Rename"),
                    ("close", "Close"),
                    ("open", "Open"),
                    ("archive", "Archive"),
                    ("restart", "Restart"),
                ],
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="command",
            name="images",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(chats, migrations.RunPython.noop),
    ]
