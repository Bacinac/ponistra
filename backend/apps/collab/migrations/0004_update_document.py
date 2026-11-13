import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery

from apps.content import styles


def file_updates_under_their_document(apps, schema_editor):
    Tab = apps.get_model("documents", "Tab")
    Update = apps.get_model("collab", "Update")
    Update.objects.update(
        document=Subquery(Tab.objects.filter(pk=OuterRef("tab")).values("document"))
    )
    # Pending foreign key checks would block the index this migration then creates.
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def give_each_document_its_template(apps, schema_editor):
    Node = apps.get_model("documents", "Node")
    Update = apps.get_model("collab", "Update")
    Update.objects.bulk_create(
        Update(document=node, room=node.room, data=styles.template())
        for node in Node.objects.filter(kind="document")
    )
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [
        ("collab", "0003_update_room"),
        ("documents", "0007_node_room"),
    ]

    operations = [
        migrations.AddField(
            model_name="update",
            name="document",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="documents.node",
            ),
        ),
        migrations.RunPython(file_updates_under_their_document, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="update",
            name="document",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="documents.node",
            ),
        ),
        migrations.AlterField(
            model_name="update",
            name="tab",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="documents.tab",
            ),
        ),
        migrations.RunPython(give_each_document_its_template, migrations.RunPython.noop),
    ]
