import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="kind",
            field=models.CharField(
                choices=[("meeting", "Meeting"), ("direct", "Direct"), ("group", "Group")],
                default="meeting",
                max_length=8,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="conversation",
            name="changed_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="message",
            name="edited_at",
            field=models.DateTimeField(null=True),
        ),
    ]
