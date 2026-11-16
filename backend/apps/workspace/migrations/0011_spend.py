import django.db.models.deletion
from django.db import migrations, models

from apps.collab.changes import followed


def read_anew(apps, schema_editor):
    # Each transcript is read once more from its start, so that the tokens of what was read
    # before they were counted are counted too; the time found again joins what is kept.
    apps.get_model("workspace", "Transcript").objects.exclude(namespace="clockify").update(read=0)


class Migration(migrations.Migration):
    dependencies = [
        ("workspace", "0010_sheets"),
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
                    ("model", "Model"),
                    ("close", "Close"),
                    ("open", "Open"),
                    ("archive", "Archive"),
                    ("restart", "Restart"),
                    ("stop", "Stop"),
                    ("move", "Move"),
                    ("cancel", "Cancel"),
                ],
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="command",
            name="state",
            field=models.CharField(
                choices=[
                    ("sent", "Sent"),
                    ("waiting", "Waiting"),
                    ("taken", "Taken"),
                    ("done", "Done"),
                    ("failed", "Failed"),
                ],
                default="sent",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="command",
            name="when",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transcript",
            name="chat",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="transcript",
            name="title",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="transcript",
            name="last",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunSQL(
            "UPDATE workspace_transcript SET chat = session WHERE namespace <> 'clockify'",
            migrations.RunSQL.noop,
        ),
        migrations.RunPython(read_anew, migrations.RunPython.noop),
        migrations.CreateModel(
            name="Spend",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("hour", models.DateTimeField()),
                ("model", models.CharField(max_length=100)),
                ("round", models.CharField(blank=True, max_length=100)),
                ("turns", models.PositiveIntegerField(default=0)),
                ("input", models.PositiveBigIntegerField(default=0)),
                ("output", models.PositiveBigIntegerField(default=0)),
                ("cache_read", models.PositiveBigIntegerField(default=0)),
                ("cache_write", models.PositiveBigIntegerField(default=0)),
                (
                    "transcript",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="spent",
                        to="workspace.transcript",
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["hour"], name="workspace_spend_hour")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("transcript", "hour", "model", "round"),
                        name="workspace_spend_once",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Limits",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("at", models.DateTimeField(unique=True)),
                ("windows", models.JSONField(default=list)),
                ("credits", models.JSONField(null=True)),
            ],
        ),
        followed("workspace_spend", "worked", "*"),
        followed("workspace_limits", "worked", "*"),
    ]
