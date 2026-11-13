from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0010_device_offline")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="mailbox",
            field=models.BooleanField(default=False),
        ),
    ]
