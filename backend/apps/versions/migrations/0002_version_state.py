import hashlib

import django.db.models.deletion
from django.db import migrations, models
from pycrdt import Doc


def give_each_version_its_document_state(apps, schema_editor):
    Update = apps.get_model("collab", "Update")
    State = apps.get_model("versions", "State")
    Version = apps.get_model("versions", "Version")
    for document in Version.objects.values_list("document", flat=True).distinct():
        doc = Doc()
        own = Update.objects.filter(document=document, tab=None).order_by("id")
        for data in own.values_list("data", flat=True):
            doc.apply_update(bytes(data))
        data = doc.get_update()
        state, _ = State.objects.get_or_create(
            document_id=document,
            sha256=hashlib.sha256(data).hexdigest(),
            defaults={"data": data},
        )
        Version.objects.filter(document=document).update(state=state)
    # Pending foreign key checks would block the column change that follows.
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [
        ("versions", "0001_initial"),
        ("collab", "0004_update_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="version",
            name="state",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="versions",
                to="versions.state",
            ),
        ),
        migrations.RunPython(give_each_version_its_document_state, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="version",
            name="state",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="versions",
                to="versions.state",
            ),
        ),
    ]
