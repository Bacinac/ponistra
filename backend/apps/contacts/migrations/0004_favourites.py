from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contacts", "0003_avatars")]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="starred",
            field=models.BooleanField(default=False),
        ),
    ]
