import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.collab.changes import followed


def pinned_become_favourites(apps, schema_editor):
    Node = apps.get_model("documents", "Node")
    Favourite = apps.get_model("documents", "Favourite")
    pinned = Node.objects.filter(pinned_at__isnull=False, created_by__isnull=False)
    Favourite.objects.bulk_create(
        Favourite(node_id=node, user_id=user) for node, user in pinned.values_list("pk", "created_by")
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("documents", "0028_places_named_by_flag"),
    ]

    operations = [
        migrations.CreateModel(
            name="Favourite",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="favourites",
                        to="documents.node",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="favourites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "node"), name="one_favourite_per_user"
                    )
                ],
            },
        ),
        followed("documents_favourite", "nodes", "u:user_id"),
        migrations.RunPython(pinned_become_favourites, migrations.RunPython.noop),
        migrations.RemoveField(model_name="node", name="pinned_at"),
    ]
