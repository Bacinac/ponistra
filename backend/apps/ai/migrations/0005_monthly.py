from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0004_reading")]

    operations = [
        migrations.AddField(
            model_name="setting",
            name="monthly",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
