import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.collab.changes import followed


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("collab", "0006_changes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Dns",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("token", models.BinaryField(default=bytes)),
                ("hint", models.CharField(blank=True, max_length=4)),
                ("error", models.TextField(blank=True)),
                ("changed_at", models.DateTimeField(null=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DB_SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("id", 1)), name="one_network_dns")
                ],
            },
        ),
        followed("network_dns", "network", "*"),
    ]
