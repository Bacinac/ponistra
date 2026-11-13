from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backups", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Migrated",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("version", models.CharField(max_length=32)),
                ("at", models.DateTimeField()),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("id", 1)), name="one_migrated")
                ],
            },
        ),
    ]
