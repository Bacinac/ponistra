from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("documents", "0029_favourites")]

    operations = [
        migrations.AddField(
            model_name="node",
            name="agent_folder",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
