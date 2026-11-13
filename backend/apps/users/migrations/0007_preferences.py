from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0006_outside_policy")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="language",
            field=models.CharField(blank=True, default="", max_length=2),
        ),
        migrations.AddField(
            model_name="user",
            name="theme",
            field=models.CharField(blank=True, default="", max_length=6),
        ),
    ]
