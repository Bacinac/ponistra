from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0007_preferences")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="sign_in",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
    ]
